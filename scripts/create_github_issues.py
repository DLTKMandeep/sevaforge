#!/usr/bin/env python3
"""
Create SevaForge SDLC backlog items as GitHub issues on DLTKMandeep/sevaforge.

Usage:
    # Via environment variable:
    export GITHUB_TOKEN=ghp_xxxxx
    python create_github_issues.py

    # Via command-line argument:
    python create_github_issues.py --token ghp_xxxxx

    # Dry-run (prints what would be created without touching GitHub):
    python create_github_issues.py --dry-run

Requirements:
    pip install PyGithub
"""

import argparse
import os
import sys
import time
from datetime import datetime

try:
    from github import Github, GithubException
except ImportError:
    print("ERROR: PyGithub is not installed. Run: pip install PyGithub")
    sys.exit(1)

REPO_NAME = "DLTKMandeep/sevaforge"

# ---------------------------------------------------------------------------
# Label definitions: name -> (color_hex, description)
# ---------------------------------------------------------------------------
LABELS = {
    "epic":         ("6F42C1", "Epic-level initiative"),
    "sprint-2":     ("0E8A16", "Sprint 2 — Jun 2-13 2025"),
    "sprint-3":     ("1D76DB", "Sprint 3 — Jun 16-27 2025"),
    "sprint-4":     ("D93F0B", "Sprint 4 — Jun 30 - Jul 11 2025"),
    "priority-p0":  ("B60205", "P0 — Critical path"),
    "priority-p1":  ("FF9F1C", "P1 — High priority"),
    "priority-p2":  ("FBCA04", "P2 — Medium priority"),
    "user-story":   ("0075CA", "User story"),
    "dev-task":     ("BFD4F2", "Development task"),
    "bug":          ("D73A4A", "Bug report"),
    "enhancement":  ("A2EEEF", "Enhancement"),
    "gap-1":        ("C5DEF5", "Gap 1 — LLM-augmented agents placeholder"),
    "gap-2":        ("C5DEF5", "Gap 2 — Smart execution wiring"),
    "gap-3":        ("C5DEF5", "Gap 3 — CLI AI flag missing"),
    "gap-4":        ("C5DEF5", "Gap 4 — Data ingestion pipeline"),
    "gap-5":        ("C5DEF5", "Gap 5 — Persistent vector store"),
    "gap-6":        ("C5DEF5", "Gap 6 — Feedback loop"),
    "gap-7":        ("C5DEF5", "Gap 7 — Cost governance"),
}

# ---------------------------------------------------------------------------
# Milestone definitions: title -> (description, due_date ISO str)
# ---------------------------------------------------------------------------
MILESTONES = {
    "Sprint 2": ("Sprint 2 — Jun 2-13 2025", "2025-06-13T23:59:59Z"),
    "Sprint 3": ("Sprint 3 — Jun 16-27 2025", "2025-06-27T23:59:59Z"),
    "Sprint 4": ("Sprint 4 — Jun 30 - Jul 11 2025", "2025-07-11T23:59:59Z"),
}

# Map sprint label to milestone title
SPRINT_TO_MILESTONE = {
    "sprint-2": "Sprint 2",
    "sprint-3": "Sprint 3",
    "sprint-4": "Sprint 4",
}

# ---------------------------------------------------------------------------
# Epics
# ---------------------------------------------------------------------------
EPICS = [
    {
        "id": "E1",
        "title": "E1: CLI AI Activation",
        "labels": ["epic", "sprint-2", "priority-p0", "gap-3"],
        "body": """## E1: CLI AI Activation

**Sprint:** `Sprint 2` | **Priority:** `P0` | **Gap:** Gap 3 — CLI AI flag missing

### Description

Add `--ai` flag to CLI parser and wire through to MissionControl. Config has `ai.enabled` but CLI never parses it.

### Files Affected

- `forgeflow/cli/forgeflow.py`
- `forgeflow/core/mission_control.py`
- `forgeflow/core/display.py`

### Acceptance Criteria

- [ ] `--ai` flag parsed by CLI argument parser
- [ ] `ai_enabled` passed to `MissionControl` constructor
- [ ] `ModelRouter` initialized when AI mode is active
- [ ] Rich console shows `[AI MODE]` badge when active
""",
    },
    {
        "id": "E2",
        "title": "E2: Smart Execution Path",
        "labels": ["epic", "sprint-2", "priority-p0", "gap-2"],
        "body": """## E2: Smart Execution Path

**Sprint:** `Sprint 2` | **Priority:** `P0` | **Gap:** Gap 2 — Smart execution wiring

### Description

Wire `execute_smart()` across all 18 MCP servers. Currently all hardcode `agent.execute()`.

### Files Affected

- `forgeflow/mcp_servers/*/server.py` (18 files)
- `forgeflow/core/mission_control.py`

### Acceptance Criteria

- [ ] 18 MCP servers call `execute_smart()` instead of `agent.execute()`
- [ ] `LLMConfig` propagated per stage
- [ ] Trust routing works (phase-based agent selection)
- [ ] Fallback logging on LLM failure
""",
    },
    {
        "id": "E3",
        "title": "E3: LLM-Augmented Agents — First 5",
        "labels": ["epic", "sprint-2", "priority-p0", "gap-1"],
        "body": """## E3: LLM-Augmented Agents — First 5

**Sprint:** `Sprint 2` | **Priority:** `P0` | **Gap:** Gap 1 — LLM-augmented agents placeholder

### Description

Implement `execute_with_llm()` on DiscoveryAgent, IaCAgent, SecurityAgent, DocumentationAgent, CodeReviewAgent. Each queries RAG collection, calls ModelRouter, returns `LLMResult` with telemetry.

### Acceptance Criteria

- [ ] 5 agents have LLM path via `execute_with_llm()`
- [ ] RAG queries work against respective collections
- [ ] Grounding check at confidence threshold 0.7
- [ ] All return `LLMResult` with telemetry metadata
""",
    },
    {
        "id": "E4",
        "title": "E4: Data Ingestion Pipeline",
        "labels": ["epic", "sprint-3", "priority-p1", "gap-4"],
        "body": """## E4: Data Ingestion Pipeline

**Sprint:** `Sprint 3` | **Priority:** `P1` | **Gap:** Gap 4 — Data ingestion pipeline

### Description

Build `forgeflow ingest` command + auto-ingest hook after each stage. 6 RAG collections defined but empty.

### Acceptance Criteria

- [ ] Manual ingest command (`forgeflow ingest <path> --collection <name>`)
- [ ] Auto-ingest hook triggers after each pipeline stage
- [ ] Content hash deduplication prevents re-indexing
- [ ] Seed command populates all 6 collections from existing data
""",
    },
    {
        "id": "E5",
        "title": "E5: Persistent Vector Store",
        "labels": ["epic", "sprint-3", "priority-p1", "gap-5"],
        "body": """## E5: Persistent Vector Store

**Sprint:** `Sprint 3` | **Priority:** `P1` | **Gap:** Gap 5 — Persistent vector store

### Description

Replace `InMemoryVectorStore` with SQLite-vss backend for persistence across runs.

### Acceptance Criteria

- [ ] SQLite DB created at `.sevaforge/vector_store.db`
- [ ] HNSW index for approximate nearest-neighbor search
- [ ] Data persists across process restarts
- [ ] Migration path from in-memory store to SQLite
""",
    },
    {
        "id": "E6",
        "title": "E6: Feedback Loop",
        "labels": ["epic", "sprint-4", "priority-p2", "gap-6"],
        "body": """## E6: Feedback Loop

**Sprint:** `Sprint 4` | **Priority:** `P2` | **Gap:** Gap 6 — Feedback loop

### Description

Post-run feedback collection (accept/reject/edit) and trust score adjustment.

### Acceptance Criteria

- [ ] Feedback prompt shown after each run (accept/reject/edit)
- [ ] Trust scores persisted to `.sevaforge/trust_scores.json`
- [ ] Phase auto-promotion at thresholds: Phase 1→2 at 40, 2→3 at 65, 3→4 at 85
""",
    },
    {
        "id": "E7",
        "title": "E7: Cost Governance",
        "labels": ["epic", "sprint-4", "priority-p2", "gap-7"],
        "body": """## E7: Cost Governance

**Sprint:** `Sprint 4` | **Priority:** `P2` | **Gap:** Gap 7 — Cost governance

### Description

Cost telemetry to ClickHouse/JSON + budget enforcement ($0.10/call, $5/run, $100/month).

### Acceptance Criteria

- [ ] Per-call cost logging (ClickHouse or JSON fallback)
- [ ] Budget caps enforced: $0.10/call, $5/run, $100/month
- [ ] Cost dashboard via `forgeflow dashboard`
- [ ] Automatic fallback to deterministic path when budget exceeded
""",
    },
    {
        "id": "E8",
        "title": "E8: Remaining LLM Agents",
        "labels": ["epic", "sprint-4", "priority-p2", "gap-1"],
        "body": """## E8: Remaining LLM Agents

**Sprint:** `Sprint 4` | **Priority:** `P2` | **Gap:** Gap 1 — LLM-augmented agents placeholder

### Description

Implement `execute_with_llm()` on remaining 17 agents (CIAgent, CDAgent, BridgeAgent, MonitoringAgent, ScaffoldingAgent, SecretsAgent, LifecycleAgent, etc.)

### Acceptance Criteria

- [ ] All 22 agents have LLM path via `execute_with_llm()`
- [ ] Each agent uses appropriate RAG collection
- [ ] Grounding check and fallback on all paths
""",
    },
]

# ---------------------------------------------------------------------------
# User Stories
# ---------------------------------------------------------------------------
USER_STORIES = [
    # ---- Sprint 2 ----
    {
        "id": "US-001",
        "epic": "E1",
        "title": "US-001: Enable AI mode via CLI",
        "points": 3,
        "labels": ["user-story", "sprint-2", "priority-p0", "gap-3"],
        "persona": "DevOps engineer",
        "want": "run `forgeflow run-all --ai` so that agents use LLM reasoning",
        "so_that": "I can leverage AI-augmented execution across the pipeline",
        "ac": [
            "`--ai` flag parsed by argument parser",
            "`ai_enabled` passed to MissionControl",
            "ModelRouter initialized when flag is set",
        ],
    },
    {
        "id": "US-002",
        "epic": "E1",
        "title": "US-002: AI mode indicator in console",
        "points": 1,
        "labels": ["user-story", "sprint-2", "priority-p0", "gap-3"],
        "persona": "DevOps engineer",
        "want": "see visual confirmation that AI mode is active",
        "so_that": "I know which execution mode is being used",
        "ac": [
            "Rich console shows `[AI MODE]` badge",
            "Model info (name, provider) displayed at startup",
        ],
    },
    {
        "id": "US-003",
        "epic": "E2",
        "title": "US-003: Wire smart path in MCP servers",
        "points": 5,
        "labels": ["user-story", "sprint-2", "priority-p0", "gap-2"],
        "persona": "platform developer",
        "want": "MCP servers to call `execute_smart()` instead of hardcoded `agent.execute()`",
        "so_that": "the smart execution path is active across all servers",
        "ac": [
            "18 `server.py` files updated to call `execute_smart()`",
            "`execute_smart()` dispatches to LLM or deterministic path",
            "Deterministic fallback works when AI is disabled",
        ],
    },
    {
        "id": "US-004",
        "epic": "E2",
        "title": "US-004: LLMConfig propagation per stage",
        "points": 3,
        "labels": ["user-story", "sprint-2", "priority-p0", "gap-2"],
        "persona": "platform developer",
        "want": "MissionControl to pass `LLMConfig` per stage with correct collection mapping",
        "so_that": "each agent queries the right RAG collection",
        "ac": [
            "Stage-to-collection mapping works for all 16 stages",
            "`LLMConfig` includes model, collection, temperature per stage",
        ],
    },
    {
        "id": "US-005",
        "epic": "E3",
        "title": "US-005: DiscoveryAgent LLM path",
        "points": 5,
        "labels": ["user-story", "sprint-2", "priority-p0", "gap-1"],
        "persona": "DevOps engineer",
        "want": "AI-powered stack classification from the DiscoveryAgent",
        "so_that": "stack detection is more accurate and context-aware",
        "ac": [
            "RAG queries `deployment_outcomes` collection",
            "LLM classifies stack components",
            "`LLMResult` returned with telemetry",
        ],
    },
    {
        "id": "US-006",
        "epic": "E3",
        "title": "US-006: IaCAgent LLM path",
        "points": 8,
        "labels": ["user-story", "sprint-2", "priority-p0", "gap-1"],
        "persona": "DevOps engineer",
        "want": "LLM-generated Terraform from the IaCAgent",
        "so_that": "infrastructure code is generated with contextual best practices",
        "ac": [
            "RAG queries `terraform_modules` collection",
            "LLM generates Terraform HCL",
            "Grounding check validates output",
            "Output is valid HCL syntax",
        ],
    },
    {
        "id": "US-007",
        "epic": "E3",
        "title": "US-007: SecurityAgent LLM path",
        "points": 5,
        "labels": ["user-story", "sprint-2", "priority-p0", "gap-1"],
        "persona": "security engineer",
        "want": "AI-triaged security findings from the SecurityAgent",
        "so_that": "security issues are prioritized with contextual reasoning",
        "ac": [
            "RAG queries `security_policies` collection",
            "LLM triages findings by severity",
            "Confidence scoring on each finding",
            "Actionable remediation output",
        ],
    },
    {
        "id": "US-008",
        "epic": "E3",
        "title": "US-008: DocumentationAgent LLM path",
        "points": 5,
        "labels": ["user-story", "sprint-2", "priority-p0", "gap-1"],
        "persona": "DevOps engineer",
        "want": "narrative documentation generated by the DocumentationAgent",
        "so_that": "documentation reads naturally and covers architecture context",
        "ac": [
            "RAG queries `runbooks` collection",
            "LLM writes prose documentation",
            "C4 diagrams enhanced with AI-generated descriptions",
        ],
    },
    {
        "id": "US-009",
        "epic": "E3",
        "title": "US-009: CodeReviewAgent LLM path",
        "points": 5,
        "labels": ["user-story", "sprint-2", "priority-p0", "gap-1"],
        "persona": "developer",
        "want": "AI-powered code review from the CodeReviewAgent",
        "so_that": "code quality feedback is contextual and specific",
        "ac": [
            "RAG provides relevant context for review",
            "LLM analyzes code hotspots",
            "Line-specific suggestions generated",
        ],
    },
    {
        "id": "US-010",
        "epic": "E2",
        "title": "US-010: Auto-fallback logging",
        "points": 2,
        "labels": ["user-story", "sprint-2", "priority-p1", "gap-2"],
        "persona": "platform developer",
        "want": "to see why an agent fell back to deterministic mode",
        "so_that": "I can debug and improve AI execution reliability",
        "ac": [
            "Structured log entry on every fallback",
            "Log includes: reason, trust score, AI dependency status",
            "Logs written to `.sevaforge/logs/fallback.log`",
        ],
    },
    {
        "id": "US-011",
        "epic": "E3",
        "title": "US-011: LLM response validation",
        "points": 3,
        "labels": ["user-story", "sprint-2", "priority-p0", "gap-1"],
        "persona": "platform developer",
        "want": "LLM outputs validated before use in the pipeline",
        "so_that": "low-confidence or hallucinated results are rejected",
        "ac": [
            "Grounding check runs on every LLM response",
            "Confidence threshold >= 0.7 enforced",
            "Reject and fall back to deterministic on failure",
        ],
    },
    # ---- Sprint 3 ----
    {
        "id": "US-012",
        "epic": "E4",
        "title": "US-012: Manual ingest command",
        "points": 5,
        "labels": ["user-story", "sprint-3", "priority-p1", "gap-4"],
        "persona": "DevOps engineer",
        "want": "to ingest documents via `forgeflow ingest <path> --collection <name>`",
        "so_that": "I can populate RAG collections with custom data",
        "ac": [
            "CLI command parses path and collection arguments",
            "Documents chunked with configurable strategy",
            "Chunks embedded and stored in vector store",
        ],
    },
    {
        "id": "US-013",
        "epic": "E4",
        "title": "US-013: Auto-ingest after stages",
        "points": 8,
        "labels": ["user-story", "sprint-3", "priority-p1", "gap-4"],
        "persona": "platform developer",
        "want": "stage outputs automatically ingested into relevant RAG collections",
        "so_that": "the knowledge base grows with every pipeline run",
        "ac": [
            "Post-stage hook triggers auto-ingest",
            "discover stage → `deployment_outcomes` collection",
            "iac stage → `terraform_modules` collection",
            "security stage → `security_policies` collection",
        ],
    },
    {
        "id": "US-014",
        "epic": "E4",
        "title": "US-014: Incremental ingestion",
        "points": 3,
        "labels": ["user-story", "sprint-3", "priority-p1", "gap-4"],
        "persona": "platform developer",
        "want": "already-indexed documents to be skipped on re-ingest",
        "so_that": "ingestion is fast and storage-efficient",
        "ac": [
            "Content hash deduplication implemented",
            "Skip count reported in output",
            "No duplicate vectors in store",
        ],
    },
    {
        "id": "US-015",
        "epic": "E4",
        "title": "US-015: Collection seeding",
        "points": 5,
        "labels": ["user-story", "sprint-3", "priority-p1", "gap-4"],
        "persona": "DevOps engineer",
        "want": "to seed all collections via `forgeflow ingest --seed`",
        "so_that": "the system has baseline knowledge on first setup",
        "ac": [
            "`--seed` flag triggers bulk ingest across all 6 collections",
            "Each collection has > 0 documents after seeding",
            "Seed data sourced from bundled templates/examples",
        ],
    },
    {
        "id": "US-016",
        "epic": "E5",
        "title": "US-016: SQLite vector store backend",
        "points": 8,
        "labels": ["user-story", "sprint-3", "priority-p1", "gap-5"],
        "persona": "platform developer",
        "want": "a persistent SQLite-vss vector store replacing InMemoryVectorStore",
        "so_that": "embeddings survive process restarts",
        "ac": [
            "Store created at `.sevaforge/vector_store.db`",
            "HNSW index for approximate nearest-neighbor search",
            "Cosine similarity search works correctly",
            "Data persists across restarts",
        ],
    },
    {
        "id": "US-017",
        "epic": "E5",
        "title": "US-017: Vector store migration",
        "points": 3,
        "labels": ["user-story", "sprint-3", "priority-p1", "gap-5"],
        "persona": "platform developer",
        "want": "a migration path from in-memory to SQLite vector store",
        "so_that": "existing users can upgrade without data loss",
        "ac": [
            "Migration script handles in-memory → SQLite",
            "Data validation after migration",
            "Backward compatibility maintained during transition",
        ],
    },
    # ---- Sprint 4 ----
    {
        "id": "US-018",
        "epic": "E6",
        "title": "US-018: Feedback collector",
        "points": 5,
        "labels": ["user-story", "sprint-4", "priority-p2", "gap-6"],
        "persona": "DevOps engineer",
        "want": "to provide feedback (accept/reject/edit) after each pipeline run",
        "so_that": "the system learns from my corrections",
        "ac": [
            "Rich prompts shown after run completion",
            "Feedback saved to `.sevaforge/feedback.json`",
            "Three action types supported: accept (+2), reject (-5), edit (+1)",
        ],
    },
    {
        "id": "US-019",
        "epic": "E6",
        "title": "US-019: Trust score persistence",
        "points": 3,
        "labels": ["user-story", "sprint-4", "priority-p2", "gap-6"],
        "persona": "platform developer",
        "want": "trust scores saved between runs",
        "so_that": "agent trust evolves over time based on feedback",
        "ac": [
            "Scores persisted to `.sevaforge/trust_scores.json`",
            "Adjustments: accept +2, reject -5, edit +1",
            "Scores loaded on startup, initialized to 0 for new agents",
        ],
    },
    {
        "id": "US-020",
        "epic": "E6",
        "title": "US-020: Phase auto-promotion",
        "points": 3,
        "labels": ["user-story", "sprint-4", "priority-p2", "gap-6"],
        "persona": "platform developer",
        "want": "agents auto-promoted through trust phases at thresholds",
        "so_that": "agents earn more autonomy as trust grows",
        "ac": [
            "Phase 1 → 2 at trust score 40",
            "Phase 2 → 3 at trust score 65",
            "Phase 3 → 4 at trust score 85",
            "Promotion logged with timestamp",
        ],
    },
    {
        "id": "US-021",
        "epic": "E7",
        "title": "US-021: Cost telemetry",
        "points": 5,
        "labels": ["user-story", "sprint-4", "priority-p2", "gap-7"],
        "persona": "platform developer",
        "want": "per-call cost logging for all LLM interactions",
        "so_that": "spending is tracked and auditable",
        "ac": [
            "Per-call cost entries logged",
            "ClickHouse backend or JSON fallback",
            "Fields: timestamp, agent, model, tokens_in, tokens_out, cost_usd",
        ],
    },
    {
        "id": "US-022",
        "epic": "E7",
        "title": "US-022: Budget enforcement",
        "points": 3,
        "labels": ["user-story", "sprint-4", "priority-p2", "gap-7"],
        "persona": "platform developer",
        "want": "spending caps enforced at call, run, and monthly levels",
        "so_that": "costs don't exceed budget",
        "ac": [
            "$0.10 per-call cap enforced",
            "$5.00 per-run cap enforced",
            "$100.00 monthly cap enforced",
            "Automatic fallback to deterministic path when budget exceeded",
        ],
    },
    {
        "id": "US-023",
        "epic": "E7",
        "title": "US-023: Cost dashboard",
        "points": 5,
        "labels": ["user-story", "sprint-4", "priority-p2", "gap-7"],
        "persona": "DevOps engineer",
        "want": "a cost breakdown dashboard via `forgeflow dashboard`",
        "so_that": "I can see spending by model and agent",
        "ac": [
            "`forgeflow dashboard` command launches cost view",
            "Cost chart broken down by model and agent",
            "Running totals for current run and current month",
        ],
    },
    {
        "id": "US-024",
        "epic": "E8",
        "title": "US-024: CIAgent LLM path",
        "points": 5,
        "labels": ["user-story", "sprint-4", "priority-p2", "gap-1"],
        "persona": "DevOps engineer",
        "want": "AI-enhanced CI pipeline generation from CIAgent",
        "so_that": "CI configs are optimized using historical deployment data",
        "ac": [
            "`execute_with_llm()` implemented on CIAgent",
            "RAG queries `deployment_outcomes` collection",
            "Grounding check and deterministic fallback",
        ],
    },
    {
        "id": "US-025",
        "epic": "E8",
        "title": "US-025: CDAgent LLM path",
        "points": 5,
        "labels": ["user-story", "sprint-4", "priority-p2", "gap-1"],
        "persona": "DevOps engineer",
        "want": "AI-enhanced CD pipeline generation from CDAgent",
        "so_that": "deployment strategies leverage runbook knowledge",
        "ac": [
            "`execute_with_llm()` implemented on CDAgent",
            "RAG queries `runbooks` collection",
            "Grounding check and deterministic fallback",
        ],
    },
    {
        "id": "US-026",
        "epic": "E8",
        "title": "US-026: BridgeAgent LLM path",
        "points": 3,
        "labels": ["user-story", "sprint-4", "priority-p2", "gap-1"],
        "persona": "developer",
        "want": "AI-generated commit messages and PR descriptions from BridgeAgent",
        "so_that": "git workflow communication is clearer and more consistent",
        "ac": [
            "`execute_with_llm()` implemented on BridgeAgent",
            "AI-generated commit messages based on diff context",
            "AI-generated PR descriptions with summary and impact",
        ],
    },
    {
        "id": "US-027",
        "epic": "E8",
        "title": "US-027: MonitoringAgent LLM path",
        "points": 5,
        "labels": ["user-story", "sprint-4", "priority-p2", "gap-1"],
        "persona": "DevOps engineer",
        "want": "AI-generated alert rules from MonitoringAgent",
        "so_that": "monitoring is tuned using historical deployment patterns",
        "ac": [
            "`execute_with_llm()` implemented on MonitoringAgent",
            "RAG queries `deployment_outcomes` collection",
            "Grounding check and deterministic fallback",
        ],
    },
    {
        "id": "US-028",
        "epic": "E8",
        "title": "US-028: ScaffoldingAgent LLM path",
        "points": 5,
        "labels": ["user-story", "sprint-4", "priority-p2", "gap-1"],
        "persona": "developer",
        "want": "AI-enhanced project scaffolding from ScaffoldingAgent",
        "so_that": "scaffolded projects reflect team conventions",
        "ac": [
            "`execute_with_llm()` implemented on ScaffoldingAgent",
            "RAG queries `team_configs` collection",
            "Grounding check and deterministic fallback",
        ],
    },
    {
        "id": "US-029",
        "epic": "E8",
        "title": "US-029: SecretsAgent LLM path",
        "points": 5,
        "labels": ["user-story", "sprint-4", "priority-p2", "gap-1"],
        "persona": "security engineer",
        "want": "AI-enhanced secrets and IAM management from SecretsAgent",
        "so_that": "IAM policies follow organizational security standards",
        "ac": [
            "`execute_with_llm()` implemented on SecretsAgent",
            "RAG queries `security_policies` collection",
            "Grounding check and deterministic fallback",
        ],
    },
    {
        "id": "US-030",
        "epic": "E8",
        "title": "US-030: LifecycleAgent LLM path",
        "points": 5,
        "labels": ["user-story", "sprint-4", "priority-p2", "gap-1"],
        "persona": "DevOps engineer",
        "want": "AI-enhanced CI/CD lifecycle workflows from LifecycleAgent",
        "so_that": "end-to-end pipelines are optimized using past deployment data",
        "ac": [
            "`execute_with_llm()` implemented on LifecycleAgent",
            "RAG queries `deployment_outcomes` collection",
            "Grounding check and deterministic fallback",
        ],
    },
]


def _story_body(story: dict, epic_issue_map: dict) -> str:
    """Build markdown body for a user story issue."""
    sprint_label = next((l for l in story["labels"] if l.startswith("sprint-")), "")
    priority_label = next((l for l in story["labels"] if l.startswith("priority-")), "")
    sprint_display = sprint_label.replace("-", " ").title() if sprint_label else ""
    priority_display = priority_label.replace("priority-", "").upper() if priority_label else ""

    epic_ref = ""
    if story["epic"] in epic_issue_map:
        epic_num = epic_issue_map[story["epic"]]
        epic_ref = f"**Epic:** #{epic_num} ({story['epic']})"
    else:
        epic_ref = f"**Epic:** {story['epic']}"

    ac_lines = "\n".join(f"- [ ] {item}" for item in story["ac"])

    return f"""## {story['id']}: {story['title'].split(': ', 1)[-1]}

**Sprint:** `{sprint_display}` | **Priority:** `{priority_display}` | **Story Points:** `{story['points']}`
{epic_ref}

### User Story

> **As a** {story['persona']},
> **I want to** {story['want']},
> **So that** {story['so_that']}.

### Acceptance Criteria

{ac_lines}
"""


def get_sprint_label(labels: list) -> str:
    """Extract sprint label from labels list."""
    for label in labels:
        if label.startswith("sprint-"):
            return label
    return ""


def main():
    parser = argparse.ArgumentParser(description="Create SevaForge SDLC backlog as GitHub issues")
    parser.add_argument("--token", help="GitHub personal access token")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be created without touching GitHub")
    args = parser.parse_args()

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token and not args.dry_run:
        print("ERROR: Provide a GitHub token via --token or GITHUB_TOKEN env var.")
        sys.exit(1)

    if args.dry_run:
        print("=== DRY RUN MODE ===\n")
        print(f"Repository: {REPO_NAME}")
        print(f"\nLabels to create ({len(LABELS)}):")
        for name, (color, desc) in LABELS.items():
            print(f"  - {name} (#{color}) — {desc}")
        print(f"\nMilestones to create ({len(MILESTONES)}):")
        for title, (desc, due) in MILESTONES.items():
            print(f"  - {title} (due {due[:10]})")
        print(f"\nEpics to create ({len(EPICS)}):")
        for epic in EPICS:
            print(f"  - {epic['title']} [{', '.join(epic['labels'])}]")
        print(f"\nUser Stories to create ({len(USER_STORIES)}):")
        for story in USER_STORIES:
            print(f"  - {story['title']} [{', '.join(story['labels'])}] ({story['points']} pts)")
        print(f"\nTotal issues: {len(EPICS) + len(USER_STORIES)}")
        return

    # Connect to GitHub
    g = Github(token)
    repo = g.get_repo(REPO_NAME)
    print(f"Connected to repository: {repo.full_name}")

    # ---- Step 1: Create labels ----
    print("\n--- Creating Labels ---")
    existing_labels = {l.name: l for l in repo.get_labels()}
    labels_created = 0
    labels_skipped = 0

    for name, (color, description) in LABELS.items():
        if name in existing_labels:
            print(f"  [skip] Label '{name}' already exists")
            labels_skipped += 1
        else:
            try:
                repo.create_label(name=name, color=color, description=description)
                print(f"  [created] Label '{name}' (#{color})")
                labels_created += 1
                time.sleep(0.5)
            except GithubException as e:
                print(f"  [error] Label '{name}': {e}")

    # ---- Step 2: Create milestones ----
    print("\n--- Creating Milestones ---")
    existing_milestones = {m.title: m for m in repo.get_milestones(state="all")}
    milestone_map = {}  # title -> Milestone object
    milestones_created = 0
    milestones_skipped = 0

    for title, (description, due_str) in MILESTONES.items():
        if title in existing_milestones:
            print(f"  [skip] Milestone '{title}' already exists")
            milestone_map[title] = existing_milestones[title]
            milestones_skipped += 1
        else:
            try:
                due_date = datetime.strptime(due_str, "%Y-%m-%dT%H:%M:%SZ")
                ms = repo.create_milestone(title=title, description=description, due_on=due_date)
                print(f"  [created] Milestone '{title}' (due {due_str[:10]})")
                milestone_map[title] = ms
                milestones_created += 1
                time.sleep(0.5)
            except GithubException as e:
                print(f"  [error] Milestone '{title}': {e}")

    # Refresh labels for assignment
    all_labels = {l.name: l for l in repo.get_labels()}

    # ---- Step 3: Create Epic issues ----
    print("\n--- Creating Epic Issues ---")
    epic_issue_map = {}  # epic_id -> issue_number
    epics_created = 0

    for epic in EPICS:
        sprint_label = get_sprint_label(epic["labels"])
        milestone_title = SPRINT_TO_MILESTONE.get(sprint_label)
        milestone = milestone_map.get(milestone_title) if milestone_title else None

        label_objects = [all_labels[l] for l in epic["labels"] if l in all_labels]

        try:
            kwargs = {
                "title": epic["title"],
                "body": epic["body"],
                "labels": label_objects,
            }
            if milestone:
                kwargs["milestone"] = milestone

            issue = repo.create_issue(**kwargs)
            epic_issue_map[epic["id"]] = issue.number
            print(f"  [#{issue.number}] {epic['title']}")
            epics_created += 1
            time.sleep(1)
        except GithubException as e:
            print(f"  [error] {epic['title']}: {e}")

    # ---- Step 4: Create User Story issues ----
    print("\n--- Creating User Story Issues ---")
    stories_created = 0

    for story in USER_STORIES:
        sprint_label = get_sprint_label(story["labels"])
        milestone_title = SPRINT_TO_MILESTONE.get(sprint_label)
        milestone = milestone_map.get(milestone_title) if milestone_title else None

        label_objects = [all_labels[l] for l in story["labels"] if l in all_labels]
        body = _story_body(story, epic_issue_map)

        try:
            kwargs = {
                "title": story["title"],
                "body": body,
                "labels": label_objects,
            }
            if milestone:
                kwargs["milestone"] = milestone

            issue = repo.create_issue(**kwargs)
            print(f"  [#{issue.number}] {story['title']} ({story['points']} pts)")
            stories_created += 1
            time.sleep(1)
        except GithubException as e:
            print(f"  [error] {story['title']}: {e}")

    # ---- Summary ----
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Labels:     {labels_created} created, {labels_skipped} skipped")
    print(f"  Milestones: {milestones_created} created, {milestones_skipped} skipped")
    print(f"  Epics:      {epics_created} created")
    print(f"  Stories:    {stories_created} created")
    print(f"  Total:      {epics_created + stories_created} issues created")
    print("=" * 60)


if __name__ == "__main__":
    main()
