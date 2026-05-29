"""
Tests for Orchestration Layer (Layer 3): A2A Protocol, Workflow Engine, Context Memory.
"""

import pytest

from sevaforge.orchestration.a2a import (
    A2AProtocol,
    AgentMessage,
    DeliveryStatus,
    MessagePriority,
    MessageType,
)
from sevaforge.orchestration.context import ContextMemory, ConversationTurn
from sevaforge.orchestration.workflow import (
    EdgeCondition,
    NodeStatus,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowEngine,
    WorkflowNode,
    WorkflowStatus,
)


# ══════════════════════════════════════════════════════════════════════
# A2A Protocol Tests
# ══════════════════════════════════════════════════════════════════════


class TestA2AProtocol:
    def test_register_agent(self):
        a2a = A2AProtocol()
        ep = a2a.register_agent("agent-1", "Discovery Agent", ["scan", "classify"])
        assert ep.agent_id == "agent-1"
        assert ep.name == "Discovery Agent"
        assert "scan" in ep.capabilities

    def test_list_agents(self):
        a2a = A2AProtocol()
        a2a.register_agent("a", "Agent A")
        a2a.register_agent("b", "Agent B")
        assert len(a2a.list_agents()) == 2

    def test_unregister_agent(self):
        a2a = A2AProtocol()
        a2a.register_agent("a", "Agent A")
        assert a2a.unregister_agent("a") is True
        assert a2a.unregister_agent("nonexistent") is False
        assert len(a2a.list_agents()) == 0

    def test_send_message(self):
        a2a = A2AProtocol()
        a2a.register_agent("src", "Source")
        a2a.register_agent("tgt", "Target")
        msg = a2a.send("src", "tgt", {"action": "scan"})
        assert msg.status == DeliveryStatus.DELIVERED
        assert msg.source_agent == "src"
        assert msg.target_agent == "tgt"

    def test_send_to_unknown_agent_fails(self):
        a2a = A2AProtocol()
        a2a.register_agent("src", "Source")
        msg = a2a.send("src", "nonexistent", {"test": True})
        assert msg.status == DeliveryStatus.FAILED

    def test_receive_messages(self):
        a2a = A2AProtocol()
        a2a.register_agent("a", "A")
        a2a.register_agent("b", "B")
        a2a.send("a", "b", {"msg": "hello"})
        a2a.send("a", "b", {"msg": "world"})
        messages = a2a.receive("b")
        assert len(messages) == 2
        assert messages[0].payload["msg"] == "hello"

    def test_subscribe_and_publish(self):
        a2a = A2AProtocol()
        a2a.register_agent("pub", "Publisher")
        a2a.register_agent("sub1", "Subscriber 1")
        a2a.register_agent("sub2", "Subscriber 2")
        a2a.subscribe("sub1", "alerts")
        a2a.subscribe("sub2", "alerts")
        messages = a2a.publish("pub", "alerts", {"level": "critical"})
        assert len(messages) == 2

    def test_broadcast(self):
        a2a = A2AProtocol()
        a2a.register_agent("sender", "Sender")
        a2a.register_agent("r1", "R1")
        a2a.register_agent("r2", "R2")
        messages = a2a.broadcast("sender", {"notice": "shutdown"})
        assert len(messages) == 2  # All except sender

    def test_request_reply(self):
        a2a = A2AProtocol()
        a2a.register_agent("client", "Client")
        a2a.register_agent("server", "Server")
        req = a2a.request("client", "server", {"query": "status?"})
        reply = a2a.reply(req, "server", {"status": "ok"})
        assert reply.message_type == MessageType.RESPONSE
        assert reply.reply_to == req.message_id
        assert reply.correlation_id == req.correlation_id

    def test_handoff(self):
        a2a = A2AProtocol()
        a2a.register_agent("a", "A")
        a2a.register_agent("b", "B")
        msg = a2a.handoff("a", "b", {"task": "review"}, reason="escalation")
        assert msg.message_type == MessageType.HANDOFF
        assert msg.payload["reason"] == "escalation"

    def test_stats(self):
        a2a = A2AProtocol()
        a2a.register_agent("a", "A")
        a2a.register_agent("b", "B")
        a2a.send("a", "b", {"test": True})
        stats = a2a.stats()
        assert stats["messages_sent"] == 1
        assert stats["registered_agents"] == 2

    def test_handler_callback(self):
        received = []
        a2a = A2AProtocol()
        a2a.register_agent("src", "Source")
        a2a.register_agent("tgt", "Target", handler=lambda msg: received.append(msg))
        a2a.send("src", "tgt", {"data": 42})
        assert len(received) == 1
        assert received[0].payload["data"] == 42


# ══════════════════════════════════════════════════════════════════════
# Workflow Engine Tests
# ══════════════════════════════════════════════════════════════════════


class TestWorkflowEngine:
    @staticmethod
    def _mock_executor(node, ctx):
        return {"executed": node.node_id, "agent": node.agent_id}

    def _build_linear_workflow(self) -> WorkflowDefinition:
        """A → B → C linear workflow."""
        wf = WorkflowDefinition(name="linear-test")
        wf.add_node(WorkflowNode(node_id="a", agent_id="agent-1", name="Step A"))
        wf.add_node(WorkflowNode(node_id="b", agent_id="agent-2", name="Step B"))
        wf.add_node(WorkflowNode(node_id="c", agent_id="agent-3", name="Step C"))
        wf.add_edge(WorkflowEdge(source="a", target="b"))
        wf.add_edge(WorkflowEdge(source="b", target="c"))
        return wf

    def test_register_workflow(self):
        engine = WorkflowEngine()
        wf = self._build_linear_workflow()
        wf_id = engine.register_workflow(wf)
        assert engine.get_workflow(wf_id) is not None

    def test_cycle_detection(self):
        engine = WorkflowEngine()
        wf = WorkflowDefinition(name="cyclic")
        wf.add_node(WorkflowNode(node_id="a", agent_id="x"))
        wf.add_node(WorkflowNode(node_id="b", agent_id="y"))
        wf.add_edge(WorkflowEdge(source="a", target="b"))
        wf.add_edge(WorkflowEdge(source="b", target="a"))
        with pytest.raises(ValueError, match="cycle"):
            engine.register_workflow(wf)

    def test_execute_linear(self):
        engine = WorkflowEngine()
        engine.set_default_executor(self._mock_executor)
        wf = self._build_linear_workflow()
        engine.register_workflow(wf)
        run = engine.execute_sync(wf.workflow_id)
        assert run.status == WorkflowStatus.SUCCEEDED
        assert all(n.status == NodeStatus.SUCCEEDED for n in run.nodes.values())
        assert run.duration_ms > 0

    def test_execute_parallel_fan_out(self):
        """A → (B, C) parallel fan-out."""
        engine = WorkflowEngine()
        engine.set_default_executor(self._mock_executor)
        wf = WorkflowDefinition(name="fan-out")
        wf.add_node(WorkflowNode(node_id="a", agent_id="x"))
        wf.add_node(WorkflowNode(node_id="b", agent_id="y"))
        wf.add_node(WorkflowNode(node_id="c", agent_id="z"))
        wf.add_edge(WorkflowEdge(source="a", target="b"))
        wf.add_edge(WorkflowEdge(source="a", target="c"))
        engine.register_workflow(wf)
        run = engine.execute_sync(wf.workflow_id)
        assert run.status == WorkflowStatus.SUCCEEDED

    def test_execute_not_found(self):
        engine = WorkflowEngine()
        with pytest.raises(KeyError, match="not found"):
            engine.execute_sync("nonexistent")

    def test_node_failure_partial(self):
        def failing_executor(node, ctx):
            if node.agent_id == "fail":
                raise RuntimeError("Simulated failure")
            return {"ok": True}

        engine = WorkflowEngine()
        engine.set_default_executor(failing_executor)
        wf = WorkflowDefinition(name="fail-test")
        wf.add_node(WorkflowNode(node_id="good", agent_id="pass"))
        wf.add_node(WorkflowNode(node_id="bad", agent_id="fail"))
        engine.register_workflow(wf)
        run = engine.execute_sync(wf.workflow_id)
        assert run.nodes["good"].status == NodeStatus.SUCCEEDED
        assert run.nodes["bad"].status == NodeStatus.FAILED

    def test_workflow_crud(self):
        engine = WorkflowEngine()
        wf = self._build_linear_workflow()
        engine.register_workflow(wf)
        assert len(engine.list_workflows()) == 1
        assert engine.delete_workflow(wf.workflow_id) is True
        assert len(engine.list_workflows()) == 0

    def test_run_history(self):
        engine = WorkflowEngine()
        engine.set_default_executor(self._mock_executor)
        wf = self._build_linear_workflow()
        engine.register_workflow(wf)
        run = engine.execute_sync(wf.workflow_id)
        assert engine.get_run(run.run_id) is not None
        assert len(engine.list_runs(wf.workflow_id)) == 1

    def test_stats(self):
        engine = WorkflowEngine()
        engine.set_default_executor(self._mock_executor)
        wf = self._build_linear_workflow()
        engine.register_workflow(wf)
        engine.execute_sync(wf.workflow_id)
        stats = engine.stats()
        assert stats["registered_workflows"] == 1
        assert stats["total_runs"] == 1


# ══════════════════════════════════════════════════════════════════════
# Context Memory Tests
# ══════════════════════════════════════════════════════════════════════


class TestContextMemory:
    def test_create_session(self):
        memory = ContextMemory()
        session = memory.create_session(user_id="user-1", tenant_id="acme")
        assert session.user_id == "user-1"
        assert session.tenant_id == "acme"

    def test_get_session(self):
        memory = ContextMemory()
        session = memory.create_session()
        fetched = memory.get_session(session.session_id)
        assert fetched is not None
        assert fetched.session_id == session.session_id

    def test_delete_session(self):
        memory = ContextMemory()
        session = memory.create_session()
        assert memory.delete_session(session.session_id) is True
        assert memory.get_session(session.session_id) is None

    def test_store_and_get_state(self):
        memory = ContextMemory()
        session = memory.create_session()
        memory.store(session.session_id, "result", {"score": 0.95})
        value = memory.get(session.session_id, "result")
        assert value["score"] == 0.95

    def test_merge_state(self):
        memory = ContextMemory()
        session = memory.create_session()
        memory.merge_state(session.session_id, {"a": 1, "b": 2})
        state = memory.get_state(session.session_id)
        assert state["a"] == 1
        assert state["b"] == 2

    def test_add_turn_and_history(self):
        memory = ContextMemory()
        session = memory.create_session()
        memory.add_turn(session.session_id, "user", "What is Python?")
        memory.add_turn(session.session_id, "assistant", "A language.", agent_id="code-review")
        history = memory.get_history(session.session_id)
        assert len(history) == 2
        assert history[0].role == "user"
        assert history[1].agent_id == "code-review"

    def test_context_window(self):
        memory = ContextMemory()
        session = memory.create_session()
        memory.store(session.session_id, "key", "value")
        memory.add_turn(session.session_id, "user", "hello")
        window = memory.get_context_window(session.session_id)
        assert len(window["history"]) == 1
        assert window["state"]["key"] == "value"

    def test_fork_session(self):
        memory = ContextMemory()
        original = memory.create_session(user_id="u1")
        memory.store(original.session_id, "data", "shared")
        memory.add_turn(original.session_id, "user", "test")
        forked = memory.fork_session(original.session_id)
        assert forked is not None
        assert forked.session_id != original.session_id
        assert forked.state["data"] == "shared"
        assert len(forked.history) == 1

    def test_merge_sessions(self):
        memory = ContextMemory()
        s1 = memory.create_session()
        s2 = memory.create_session()
        memory.store(s1.session_id, "a", 1)
        memory.store(s2.session_id, "b", 2)
        memory.add_turn(s2.session_id, "user", "from s2")
        assert memory.merge_sessions(s1.session_id, s2.session_id) is True
        state = memory.get_state(s1.session_id)
        assert state["b"] == 2

    def test_list_sessions_filter(self):
        memory = ContextMemory()
        memory.create_session(user_id="alice")
        memory.create_session(user_id="bob")
        memory.create_session(user_id="alice")
        sessions = memory.list_sessions(user_id="alice")
        assert len(sessions) == 2

    def test_lru_eviction(self):
        memory = ContextMemory(max_sessions=3)
        s1 = memory.create_session()
        s2 = memory.create_session()
        s3 = memory.create_session()
        # This should evict s1 (LRU)
        s4 = memory.create_session()
        assert memory.get_session(s1.session_id) is None
        assert memory.get_session(s4.session_id) is not None

    def test_stats(self):
        memory = ContextMemory()
        memory.create_session()
        stats = memory.stats()
        assert stats["active_sessions"] == 1
        assert stats["sessions_created"] == 1
