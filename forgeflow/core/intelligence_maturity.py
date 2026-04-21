"""
ForgeFlow Intelligence Maturity Framework
==========================================
Cross-cutting overlay that classifies every pipeline stage by its
intelligence level — independent of which pipeline phase (Analyse /
Build / Quality / Ship) the stage belongs to.

4 Phases of AI Maturity
-----------------------
Phase 1 — Assisted Intelligence
    Copilots that answer questions, draft content, provide recommendations.
    Goal: Build trust, gather data, learn patterns.
    Metric: Adoption rate and time saved.

Phase 2 — Automated Intelligence
    Rule-based agents for routine tasks, known workflows, clear boundaries.
    Goal: Prove reliability, establish governance.
    Metric: Tasks automated, error rate.

Phase 3 — Augmented Intelligence
    Proactive agents that suggest, identify opportunities, learn from
    human decisions.
    Goal: Demonstrate judgment, build confidence.
    Metric: Suggestion acceptance rate.

Phase 4 — Agentic Intelligence
    Self-directed agents for proven use cases — execute without approval,
    operate within guardrails, self-monitor and report.
    Goal: Scale impact, reduce friction.
    Metric: Autonomous completion rate.

Each pipeline stage has a *current* level and a *target* level.
Stages earn upgrades by accumulating trust through run history.
"""

from enum import IntEnum
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Intelligence Phase enum
# ─────────────────────────────────────────────────────────────────────────────

class IntelligencePhase(IntEnum):
    """The four intelligence maturity levels."""
    ASSISTED  = 1   # Phase 1 — observe, inform, recommend
    AUTOMATED = 2   # Phase 2 — execute known workflows within boundaries
    AUGMENTED = 3   # Phase 3 — learn, suggest, adapt from feedback
    AGENTIC   = 4   # Phase 4 — autonomous within guardrails

    @property
    def label(self) -> str:
        return {
            1: "Assisted",
            2: "Automated",
            3: "Augmented",
            4: "Agentic",
        }[self.value]

    @property
    def icon(self) -> str:
        return {
            1: "👁️",
            2: "⚙️",
            3: "🧠",
            4: "🤖",
        }[self.value]

    @property
    def color(self) -> str:
        """Rich console color name."""
        return {
            1: "cyan",
            2: "yellow",
            3: "green",
            4: "magenta",
        }[self.value]

    @property
    def goal(self) -> str:
        return {
            1: "Build trust, gather data, learn patterns",
            2: "Prove reliability, establish governance",
            3: "Demonstrate judgment, build confidence",
            4: "Scale impact, reduce friction",
        }[self.value]

    @property
    def metric(self) -> str:
        return {
            1: "Adoption rate, time saved",
            2: "Tasks automated, error rate",
            3: "Suggestion acceptance rate",
            4: "Autonomous completion rate",
        }[self.value]


# ─────────────────────────────────────────────────────────────────────────────
# Stage maturity mapping
# ─────────────────────────────────────────────────────────────────────────────

class StageMaturity:
    """Classification of a single pipeline stage's intelligence level."""

    def __init__(
        self,
        stage: str,
        current: IntelligencePhase,
        target: IntelligencePhase,
        rationale: str = "",
        capabilities: Optional[Dict[str, bool]] = None,
    ):
        self.stage = stage
        self.current = current
        self.target = target
        self.rationale = rationale
        # Feature flags that unlock as stage matures
        self.capabilities = capabilities or {}

    @property
    def gap(self) -> int:
        """How many phases away from target."""
        return self.target.value - self.current.value

    @property
    def at_target(self) -> bool:
        return self.current >= self.target

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "current_phase": self.current.value,
            "current_label": f"{self.current.icon} {self.current.label}",
            "target_phase": self.target.value,
            "target_label": f"{self.target.icon} {self.target.label}",
            "gap": self.gap,
            "at_target": self.at_target,
            "rationale": self.rationale,
            "capabilities": self.capabilities,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Default stage classifications — current state of ForgeFlow v2.2
# ─────────────────────────────────────────────────────────────────────────────

STAGE_MATURITY: Dict[str, StageMaturity] = {
    # ── Phase: Analyse ───────────────────────────────────────────────
    "discover": StageMaturity(
        stage="discover",
        current=IntelligencePhase.ASSISTED,
        target=IntelligencePhase.AUGMENTED,
        rationale="Currently scans and reports — could learn common patterns per-language "
                  "and proactively recommend project structure improvements",
        capabilities={
            "scans_repo": True,
            "reports_findings": True,
            "learns_patterns": False,       # Phase 3
            "suggests_improvements": False,  # Phase 3
        },
    ),
    "normalize": StageMaturity(
        stage="normalize",
        current=IntelligencePhase.AUTOMATED,
        target=IntelligencePhase.AUGMENTED,
        rationale="Rule-based file generation — could learn team preferences and "
                  "suggest customized standards based on past decisions",
        capabilities={
            "generates_files": True,
            "follows_rules": True,
            "learns_team_prefs": False,     # Phase 3
            "adapts_standards": False,       # Phase 3
        },
    ),
    "docs": StageMaturity(
        stage="docs",
        current=IntelligencePhase.AUTOMATED,
        target=IntelligencePhase.AUGMENTED,
        rationale="Template-based doc generation — could learn which docs are "
                  "actually read and focus effort there",
        capabilities={
            "generates_docs": True,
            "creates_diagrams": True,
            "tracks_doc_usage": False,      # Phase 3
            "prioritizes_content": False,    # Phase 3
        },
    ),

    # ── Phase: Build ─────────────────────────────────────────────────
    "iac": StageMaturity(
        stage="iac",
        current=IntelligencePhase.AUTOMATED,
        target=IntelligencePhase.AUGMENTED,
        rationale="Generates Terraform from templates — could learn from past "
                  "deployments which instance types and configs perform best",
        capabilities={
            "generates_terraform": True,
            "generates_dockerfile": True,
            "learns_from_deploys": False,    # Phase 3
            "optimizes_resources": False,     # Phase 3
        },
    ),
    "cd": StageMaturity(
        stage="cd",
        current=IntelligencePhase.AUTOMATED,
        target=IntelligencePhase.AUGMENTED,
        rationale="Template-based ArgoCD/Kustomize generation — could learn "
                  "deployment cadence and suggest rollout strategies",
        capabilities={
            "generates_manifests": True,
            "creates_kustomize": True,
            "learns_rollout_patterns": False,  # Phase 3
            "suggests_strategies": False,       # Phase 3
        },
    ),
    "ci": StageMaturity(
        stage="ci",
        current=IntelligencePhase.AUTOMATED,
        target=IntelligencePhase.AUGMENTED,
        rationale="Generates CI workflows from rules — could learn build times "
                  "and suggest parallelization or caching improvements",
        capabilities={
            "generates_workflows": True,
            "configures_dependabot": True,
            "analyzes_build_perf": False,    # Phase 3
            "optimizes_pipeline": False,      # Phase 3
        },
    ),
    "e2e": StageMaturity(
        stage="e2e",
        current=IntelligencePhase.AUTOMATED,
        target=IntelligencePhase.AUGMENTED,
        rationale="Scaffolds test templates — could learn from test results "
                  "which paths fail most and generate targeted tests",
        capabilities={
            "scaffolds_tests": True,
            "configures_framework": True,
            "learns_failure_patterns": False,  # Phase 3
            "generates_targeted_tests": False,  # Phase 3
        },
    ),

    # ── Phase: Quality ───────────────────────────────────────────────
    "review": StageMaturity(
        stage="review",
        current=IntelligencePhase.ASSISTED,
        target=IntelligencePhase.AUGMENTED,
        rationale="Reports code quality metrics — could learn which findings "
                  "developers actually fix and prioritize accordingly",
        capabilities={
            "analyzes_code": True,
            "reports_quality": True,
            "learns_fix_patterns": False,    # Phase 3
            "prioritizes_findings": False,    # Phase 3
        },
    ),
    "test": StageMaturity(
        stage="test",
        current=IntelligencePhase.AUTOMATED,
        target=IntelligencePhase.AUGMENTED,
        rationale="Runs test suite and reports — could learn flaky tests, "
                  "predict failures, and suggest test ordering",
        capabilities={
            "runs_tests": True,
            "reports_coverage": True,
            "detects_flaky": False,          # Phase 3
            "predicts_failures": False,       # Phase 3
        },
    ),
    "scan": StageMaturity(
        stage="scan",
        current=IntelligencePhase.AUTOMATED,
        target=IntelligencePhase.AUGMENTED,
        rationale="Pattern-based SAST/CVE scanning — could learn false positive "
                  "patterns per repo and suppress known-safe findings",
        capabilities={
            "detects_secrets": True,
            "scans_dependencies": True,
            "learns_false_positives": False,  # Phase 3
            "auto_suppresses": False,          # Phase 3
        },
    ),

    # ── Phase: Ship ──────────────────────────────────────────────────
    "deploy-intent": StageMaturity(
        stage="deploy-intent",
        current=IntelligencePhase.ASSISTED,
        target=IntelligencePhase.AUGMENTED,
        rationale="Interactive interview collects intent — could learn from past "
                  "runs and suggest previous choices as smart defaults",
        capabilities={
            "conducts_interview": True,
            "caches_intent": True,
            "remembers_past_choices": False,    # Phase 3 — RUN HISTORY
            "suggests_smart_defaults": False,   # Phase 3 — RUN HISTORY
        },
    ),
    "deploy-design": StageMaturity(
        stage="deploy-design",
        current=IntelligencePhase.AUTOMATED,
        target=IntelligencePhase.AGENTIC,
        rationale="Fan-out to 7 persona agents in parallel — could self-adapt "
                  "persona parameters based on observed deployment outcomes",
        capabilities={
            "fans_out_personas": True,
            "parallel_execution": True,
            "learns_from_outcomes": False,     # Phase 3
            "self_adapts_params": False,        # Phase 4
            "auto_retries_failures": False,     # Phase 4
        },
    ),
    "deploy-validate": StageMaturity(
        stage="deploy-validate",
        current=IntelligencePhase.AUTOMATED,
        target=IntelligencePhase.AGENTIC,
        rationale="7 cross-checks with pass/fail — could learn which checks fail "
                  "most often and proactively warn during design phase",
        capabilities={
            "cross_checks": True,
            "blocks_on_failure": True,
            "learns_failure_freq": False,      # Phase 3
            "proactive_warnings": False,        # Phase 3
            "self_heals": False,                # Phase 4
        },
    ),
    "secrets": StageMaturity(
        stage="secrets",
        current=IntelligencePhase.AUTOMATED,
        target=IntelligencePhase.AUGMENTED,
        rationale="Generates IAM policies and bootstrap scripts from templates — "
                  "could learn which secrets are actually used and prune stale ones",
        capabilities={
            "generates_iam": True,
            "creates_bootstrap": True,
            "tracks_secret_usage": False,     # Phase 3
            "prunes_stale_secrets": False,     # Phase 3
        },
    ),
    "lifecycle": StageMaturity(
        stage="lifecycle",
        current=IntelligencePhase.AUTOMATED,
        target=IntelligencePhase.AGENTIC,
        rationale="Wires CI→CD workflow chain — could monitor pipeline health "
                  "and autonomously adjust parallelism or add retries",
        capabilities={
            "wires_workflows": True,
            "creates_environments": True,
            "monitors_health": False,          # Phase 3
            "auto_adjusts": False,              # Phase 4
        },
    ),
    "bridge": StageMaturity(
        stage="bridge",
        current=IntelligencePhase.AUTOMATED,
        target=IntelligencePhase.AGENTIC,
        rationale="Commits and pushes to GitHub — could learn merge patterns, "
                  "autonomously handle conflicts, and self-manage PRs",
        capabilities={
            "commits_code": True,
            "creates_pr": True,
            "resolves_conflicts": False,       # Phase 3
            "self_manages_prs": False,          # Phase 4
        },
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Trust scoring
# ─────────────────────────────────────────────────────────────────────────────

class TrustScore:
    """
    Computes a per-stage trust score from run history.

    Trust is earned through:
    - Consecutive successful runs (reliability)
    - Suggestion acceptance rate (judgment)
    - Low error rate (safety)
    - Human override frequency (calibration)
    """

    def __init__(
        self,
        stage: str,
        total_runs: int = 0,
        successful_runs: int = 0,
        suggestions_made: int = 0,
        suggestions_accepted: int = 0,
        human_overrides: int = 0,
        consecutive_successes: int = 0,
    ):
        self.stage = stage
        self.total_runs = total_runs
        self.successful_runs = successful_runs
        self.suggestions_made = suggestions_made
        self.suggestions_accepted = suggestions_accepted
        self.human_overrides = human_overrides
        self.consecutive_successes = consecutive_successes

    @property
    def reliability(self) -> float:
        """Success rate (0.0 – 1.0)."""
        if self.total_runs == 0:
            return 0.0
        return self.successful_runs / self.total_runs

    @property
    def acceptance_rate(self) -> float:
        """Suggestion acceptance rate (0.0 – 1.0)."""
        if self.suggestions_made == 0:
            return 0.0
        return self.suggestions_accepted / self.suggestions_made

    @property
    def override_rate(self) -> float:
        """How often humans override the agent (lower = more trusted)."""
        if self.total_runs == 0:
            return 0.0
        return self.human_overrides / self.total_runs

    @property
    def score(self) -> float:
        """
        Composite trust score (0 – 100).

        Weights:
            40% reliability (do you succeed?)
            25% acceptance rate (do humans agree with you?)
            20% streak bonus (consecutive successes)
            15% low override rate (do humans leave you alone?)
        """
        reliability_score = self.reliability * 40
        acceptance_score = self.acceptance_rate * 25
        streak_bonus = min(self.consecutive_successes / 10, 1.0) * 20
        override_penalty = (1.0 - self.override_rate) * 15
        return round(reliability_score + acceptance_score + streak_bonus + override_penalty, 1)

    @property
    def earned_phase(self) -> IntelligencePhase:
        """Which intelligence phase this trust score warrants."""
        if self.score >= 85 and self.consecutive_successes >= 10:
            return IntelligencePhase.AGENTIC
        if self.score >= 65 and self.consecutive_successes >= 5:
            return IntelligencePhase.AUGMENTED
        if self.score >= 40 and self.total_runs >= 3:
            return IntelligencePhase.AUTOMATED
        return IntelligencePhase.ASSISTED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "trust_score": self.score,
            "earned_phase": self.earned_phase.label,
            "reliability": round(self.reliability * 100, 1),
            "acceptance_rate": round(self.acceptance_rate * 100, 1),
            "override_rate": round(self.override_rate * 100, 1),
            "consecutive_successes": self.consecutive_successes,
            "total_runs": self.total_runs,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Maturity summary
# ─────────────────────────────────────────────────────────────────────────────

def get_pipeline_maturity(trust_scores: Optional[Dict[str, TrustScore]] = None) -> Dict[str, Any]:
    """
    Return a full maturity report for the pipeline.

    If trust_scores are provided (from run history), the effective phase
    is the *minimum* of the classified phase and the earned phase.
    Without history, the classified (current) phase is used.
    """
    stages = []
    phase_counts = {p: 0 for p in IntelligencePhase}

    for stage_name, sm in STAGE_MATURITY.items():
        effective = sm.current
        trust = None

        if trust_scores and stage_name in trust_scores:
            ts = trust_scores[stage_name]
            earned = ts.earned_phase
            # Can't exceed classified current — upgrades require code changes
            effective = min(sm.current, earned)
            trust = ts.to_dict()

        phase_counts[effective] += 1
        stages.append({
            **sm.to_dict(),
            "effective_phase": effective.value,
            "effective_label": f"{effective.icon} {effective.label}",
            "trust": trust,
        })

    # Overall pipeline maturity = lowest effective phase across all stages
    min_phase = min(s["effective_phase"] for s in stages)
    overall = IntelligencePhase(min_phase)

    return {
        "overall_phase": overall.value,
        "overall_label": f"{overall.icon} {overall.label} Intelligence",
        "overall_goal": overall.goal,
        "overall_metric": overall.metric,
        "phase_distribution": {p.label: phase_counts[p] for p in IntelligencePhase},
        "stages": stages,
        "total_stages": len(stages),
    }
