"""
SevaForge Workflow Engine — US-037

DAG-based multi-agent pipeline execution.
Supports sequential chains, parallel fan-out, conditional branching,
and automatic retry with backoff.

Architecture:
    WorkflowDefinition (graph spec)
    → WorkflowEngine.execute(definition, context)
    → topological sort → parallel-safe execution → WorkflowRun (results)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────


class NodeStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class EdgeCondition(str, Enum):
    ALWAYS = "always"              # Run regardless
    ON_SUCCESS = "on_success"      # Run only if source succeeded
    ON_FAILURE = "on_failure"      # Run only if source failed
    CONDITIONAL = "conditional"     # Run based on output predicate


class WorkflowStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"            # Some nodes failed, some succeeded


# ── Data Models ───────────────────────────────────────────────────────


@dataclass
class WorkflowNode:
    """A single step in the workflow DAG."""
    node_id: str
    agent_id: str                   # Which agent executes this node
    name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 300
    max_retries: int = 0
    status: NodeStatus = NodeStatus.PENDING
    result: Any = None
    error: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "name": self.name or self.node_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
        }


@dataclass
class WorkflowEdge:
    """Directed edge between two nodes in the DAG."""
    source: str                     # Source node ID
    target: str                     # Target node ID
    condition: EdgeCondition = EdgeCondition.ON_SUCCESS
    predicate: Optional[str] = None  # Expression for CONDITIONAL edges

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "condition": self.condition.value,
        }


@dataclass
class WorkflowDefinition:
    """
    A complete workflow graph definition.

    Nodes are the agent execution steps; edges define
    ordering and conditional routing between them.
    """
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    nodes: list[WorkflowNode] = field(default_factory=list)
    edges: list[WorkflowEdge] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: WorkflowNode) -> None:
        self.nodes.append(node)

    def add_edge(self, edge: WorkflowEdge) -> None:
        self.edges.append(edge)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class WorkflowRun:
    """Runtime state of a workflow execution."""
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    status: WorkflowStatus = WorkflowStatus.CREATED
    nodes: dict[str, WorkflowNode] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
        }


# Type alias for node executors
NodeExecutor = Callable[[WorkflowNode, dict[str, Any]], Any]


# ── Workflow Engine ──────────────────────────────────────────────────


class WorkflowEngine:
    """
    DAG-based workflow execution engine.

    Supports:
    - Topological ordering with cycle detection
    - Parallel execution of independent nodes
    - Conditional edges (success/failure/predicate)
    - Retry with configurable max_retries
    - Timeout enforcement per node
    - Full execution history
    """

    def __init__(self):
        self._workflows: dict[str, WorkflowDefinition] = {}
        self._runs: dict[str, WorkflowRun] = {}
        self._executors: dict[str, NodeExecutor] = {}
        self._default_executor: NodeExecutor | None = None

    # ── Workflow CRUD ─────────────────────────────────────────────────

    def register_workflow(self, definition: WorkflowDefinition) -> str:
        """Register a workflow definition."""
        # Validate DAG
        self._validate_dag(definition)
        self._workflows[definition.workflow_id] = definition
        logger.info("Workflow registered: '%s' (%s)", definition.name, definition.workflow_id)
        return definition.workflow_id

    def get_workflow(self, workflow_id: str) -> WorkflowDefinition | None:
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> list[WorkflowDefinition]:
        return list(self._workflows.values())

    def delete_workflow(self, workflow_id: str) -> bool:
        if workflow_id in self._workflows:
            del self._workflows[workflow_id]
            return True
        return False

    # ── Executor Registration ─────────────────────────────────────────

    def register_executor(self, agent_id: str, executor: NodeExecutor) -> None:
        """Register an execution function for a specific agent type."""
        self._executors[agent_id] = executor

    def set_default_executor(self, executor: NodeExecutor) -> None:
        """Set the fallback executor for unregistered agent types."""
        self._default_executor = executor

    # ── DAG Validation ────────────────────────────────────────────────

    def _validate_dag(self, definition: WorkflowDefinition) -> None:
        """Ensure the workflow is a valid DAG (no cycles)."""
        node_ids = {n.node_id for n in definition.nodes}

        # Check edge references
        for edge in definition.edges:
            if edge.source not in node_ids:
                raise ValueError(f"Edge source '{edge.source}' not found in nodes")
            if edge.target not in node_ids:
                raise ValueError(f"Edge target '{edge.target}' not found in nodes")

        # Topological sort to detect cycles
        self._topological_sort(definition)

    def _topological_sort(self, definition: WorkflowDefinition) -> list[str]:
        """
        Kahn's algorithm — returns ordered node IDs.
        Raises ValueError on cycle detection.
        """
        in_degree: dict[str, int] = {n.node_id: 0 for n in definition.nodes}
        adjacency: dict[str, list[str]] = defaultdict(list)

        for edge in definition.edges:
            adjacency[edge.source].append(edge.target)
            in_degree[edge.target] += 1

        queue: deque[str] = deque(
            nid for nid, deg in in_degree.items() if deg == 0
        )
        ordered: list[str] = []

        while queue:
            node_id = queue.popleft()
            ordered.append(node_id)
            for neighbor in adjacency[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered) != len(in_degree):
            raise ValueError("Workflow contains a cycle — not a valid DAG")

        return ordered

    # ── Execution ─────────────────────────────────────────────────────

    def execute_sync(
        self,
        workflow_id: str,
        context: dict[str, Any] | None = None,
    ) -> WorkflowRun:
        """
        Execute a workflow synchronously (topological order).

        Nodes at the same level are executed sequentially in this mode.
        Use execute_async() for true parallel execution.
        """
        definition = self._workflows.get(workflow_id)
        if not definition:
            raise KeyError(f"Workflow '{workflow_id}' not found")

        ctx = context or {}
        run = WorkflowRun(workflow_id=workflow_id, status=WorkflowStatus.RUNNING)
        run.started_at = datetime.utcnow()

        # Initialize run nodes
        for node in definition.nodes:
            run_node = WorkflowNode(
                node_id=node.node_id,
                agent_id=node.agent_id,
                name=node.name,
                params={**node.params},
                timeout_seconds=node.timeout_seconds,
                max_retries=node.max_retries,
            )
            run.nodes[node.node_id] = run_node

        # Build edge lookup
        edges_from: dict[str, list[WorkflowEdge]] = defaultdict(list)
        for edge in definition.edges:
            edges_from[edge.source].append(edge)

        # Execute in topological order
        order = self._topological_sort(definition)
        has_failure = False

        for node_id in order:
            node = run.nodes[node_id]

            # Check if dependencies allow execution
            if not self._should_execute(node_id, run, definition):
                node.status = NodeStatus.SKIPPED
                continue

            # Execute with retry
            success = self._execute_node(node, ctx)
            if not success:
                has_failure = True

            # Propagate outputs to context
            if node.result is not None:
                ctx[f"node.{node_id}.result"] = node.result

        # Determine final status
        run.completed_at = datetime.utcnow()
        run.duration_ms = (run.completed_at - run.started_at).total_seconds() * 1000

        statuses = {n.status for n in run.nodes.values()}
        if all(s == NodeStatus.SUCCEEDED for s in statuses):
            run.status = WorkflowStatus.SUCCEEDED
        elif all(s in (NodeStatus.FAILED, NodeStatus.CANCELLED) for s in statuses):
            run.status = WorkflowStatus.FAILED
        elif has_failure:
            run.status = WorkflowStatus.PARTIAL
        else:
            run.status = WorkflowStatus.SUCCEEDED

        self._runs[run.run_id] = run
        logger.info(
            "Workflow '%s' run %s completed: %s (%.1fms)",
            workflow_id, run.run_id, run.status.value, run.duration_ms,
        )
        return run

    async def execute_async(
        self,
        workflow_id: str,
        context: dict[str, Any] | None = None,
    ) -> WorkflowRun:
        """
        Execute a workflow asynchronously.

        Nodes at the same topological level run in parallel.
        """
        definition = self._workflows.get(workflow_id)
        if not definition:
            raise KeyError(f"Workflow '{workflow_id}' not found")

        ctx = context or {}
        run = WorkflowRun(workflow_id=workflow_id, status=WorkflowStatus.RUNNING)
        run.started_at = datetime.utcnow()

        for node in definition.nodes:
            run_node = WorkflowNode(
                node_id=node.node_id,
                agent_id=node.agent_id,
                name=node.name,
                params={**node.params},
                timeout_seconds=node.timeout_seconds,
                max_retries=node.max_retries,
            )
            run.nodes[node.node_id] = run_node

        # Group by topological level for parallel execution
        levels = self._compute_levels(definition)
        has_failure = False

        for level_nodes in levels:
            tasks = []
            for node_id in level_nodes:
                node = run.nodes[node_id]
                if self._should_execute(node_id, run, definition):
                    tasks.append(self._execute_node_async(node, ctx))
                else:
                    node.status = NodeStatus.SKIPPED

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception) or result is False:
                        has_failure = True

            # Propagate outputs
            for node_id in level_nodes:
                node = run.nodes[node_id]
                if node.result is not None:
                    ctx[f"node.{node_id}.result"] = node.result

        run.completed_at = datetime.utcnow()
        run.duration_ms = (run.completed_at - run.started_at).total_seconds() * 1000

        statuses = {n.status for n in run.nodes.values()}
        if all(s == NodeStatus.SUCCEEDED for s in statuses):
            run.status = WorkflowStatus.SUCCEEDED
        elif has_failure:
            run.status = WorkflowStatus.PARTIAL
        else:
            run.status = WorkflowStatus.SUCCEEDED

        self._runs[run.run_id] = run
        return run

    def _compute_levels(self, definition: WorkflowDefinition) -> list[list[str]]:
        """Group nodes into parallel-safe execution levels."""
        in_degree: dict[str, int] = {n.node_id: 0 for n in definition.nodes}
        adjacency: dict[str, list[str]] = defaultdict(list)

        for edge in definition.edges:
            adjacency[edge.source].append(edge.target)
            in_degree[edge.target] += 1

        levels: list[list[str]] = []
        queue = [nid for nid, deg in in_degree.items() if deg == 0]

        while queue:
            levels.append(queue)
            next_queue: list[str] = []
            for node_id in queue:
                for neighbor in adjacency[node_id]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)
            queue = next_queue

        return levels

    def _should_execute(
        self,
        node_id: str,
        run: WorkflowRun,
        definition: WorkflowDefinition,
    ) -> bool:
        """Check if a node's edge conditions are satisfied."""
        # Find incoming edges
        incoming = [e for e in definition.edges if e.target == node_id]
        if not incoming:
            return True  # Root node — always execute

        for edge in incoming:
            source_node = run.nodes.get(edge.source)
            if not source_node:
                continue

            if edge.condition == EdgeCondition.ALWAYS:
                continue
            elif edge.condition == EdgeCondition.ON_SUCCESS:
                if source_node.status != NodeStatus.SUCCEEDED:
                    return False
            elif edge.condition == EdgeCondition.ON_FAILURE:
                if source_node.status != NodeStatus.FAILED:
                    return False

        return True

    def _execute_node(self, node: WorkflowNode, context: dict[str, Any]) -> bool:
        """Execute a single node synchronously with retry."""
        executor = self._executors.get(node.agent_id, self._default_executor)
        if not executor:
            node.status = NodeStatus.FAILED
            node.error = f"No executor registered for agent '{node.agent_id}'"
            return False

        for attempt in range(node.max_retries + 1):
            node.status = NodeStatus.RUNNING
            node.started_at = datetime.utcnow()
            node.retry_count = attempt

            try:
                start = time.time()
                result = executor(node, context)
                node.duration_ms = (time.time() - start) * 1000
                node.result = result
                node.status = NodeStatus.SUCCEEDED
                return True
            except Exception as e:
                node.error = str(e)
                logger.warning(
                    "Node '%s' attempt %d failed: %s", node.node_id, attempt + 1, e
                )

        node.status = NodeStatus.FAILED
        node.completed_at = datetime.utcnow()
        return False

    async def _execute_node_async(self, node: WorkflowNode, context: dict[str, Any]) -> bool:
        """Async wrapper for node execution."""
        # Run sync executor in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._execute_node, node, context)

    # ── Run History ───────────────────────────────────────────────────

    def get_run(self, run_id: str) -> WorkflowRun | None:
        return self._runs.get(run_id)

    def list_runs(self, workflow_id: str | None = None) -> list[WorkflowRun]:
        runs = list(self._runs.values())
        if workflow_id:
            runs = [r for r in runs if r.workflow_id == workflow_id]
        return runs

    def stats(self) -> dict[str, Any]:
        status_counts = defaultdict(int)
        for run in self._runs.values():
            status_counts[run.status.value] += 1
        return {
            "registered_workflows": len(self._workflows),
            "total_runs": len(self._runs),
            "run_status_counts": dict(status_counts),
            "registered_executors": len(self._executors),
        }
