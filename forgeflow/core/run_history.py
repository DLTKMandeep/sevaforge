"""
ForgeFlow Run History
=====================
Per-repo memory that persists across pipeline runs.

Stored at: .sevaforge/run-history.json

Tracks:
- Stage execution results (success/error/warning per run)
- Deploy-intent choices over time (for smart defaults)
- Suggestion acceptance / rejection (for trust scoring)
- Consecutive success streaks

This is the backbone of Phase 3 (Augmented Intelligence) — it gives
agents memory so they can learn from past decisions.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .intelligence_maturity import IntelligencePhase, TrustScore


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

HISTORY_DIR = ".sevaforge"
HISTORY_FILE = "run-history.json"
MAX_RUNS = 100        # Keep last N runs per stage to avoid unbounded growth
MAX_INTENTS = 20      # Keep last N intent snapshots


# ─────────────────────────────────────────────────────────────────────────────
# RunHistory
# ─────────────────────────────────────────────────────────────────────────────

class RunHistory:
    """
    Persistent per-repo memory for ForgeFlow pipeline runs.

    Usage:
        history = RunHistory(project_path)
        history.record_stage("discover", "success", summary="Found 42 files")
        history.record_intent_choices(captured_dict)
        history.save()

        # Later — get smart defaults for deploy-intent
        suggestions = history.suggest_intent_defaults()

        # Or — compute trust scores for maturity display
        scores = history.compute_trust_scores()
    """

    def __init__(self, project_path: str | Path):
        self.project_path = Path(project_path).resolve()
        self.history_path = self.project_path / HISTORY_DIR / HISTORY_FILE
        self._data: Dict[str, Any] = self._load()

    # ─────────────────────────────── Persistence ─────────────────────────────

    def _load(self) -> Dict[str, Any]:
        """Load existing history or create empty structure."""
        if self.history_path.exists():
            try:
                return json.loads(self.history_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return self._empty()

    @staticmethod
    def _empty() -> Dict[str, Any]:
        return {
            "version": 1,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "stage_runs": {},      # stage_name → [{"status", "summary", "timestamp"}, ...]
            "intent_history": [],   # [{"timestamp", "choices": {...}}, ...]
            "suggestions": {},      # stage_name → {"made": N, "accepted": N}
            "overrides": {},        # stage_name → N
        }

    def save(self) -> Path:
        """Persist history to disk."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self._data["updated_at"] = datetime.utcnow().isoformat() + "Z"
        self.history_path.write_text(json.dumps(self._data, indent=2, default=str))
        return self.history_path

    # ──────────────────────────── Stage recording ────────────────────────────

    def record_stage(
        self,
        stage: str,
        status: str,
        summary: str = "",
        findings_count: int = 0,
        duration_s: float = 0.0,
    ) -> None:
        """Record a single stage execution result."""
        runs = self._data["stage_runs"].setdefault(stage, [])
        runs.append({
            "status": status,
            "summary": summary[:200],
            "findings_count": findings_count,
            "duration_s": round(duration_s, 2),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })
        # Trim to MAX_RUNS
        if len(runs) > MAX_RUNS:
            self._data["stage_runs"][stage] = runs[-MAX_RUNS:]

    def get_stage_runs(self, stage: str) -> List[Dict[str, Any]]:
        """Get all recorded runs for a stage."""
        return self._data["stage_runs"].get(stage, [])

    def get_last_run(self, stage: str) -> Optional[Dict[str, Any]]:
        """Get the most recent run for a stage."""
        runs = self.get_stage_runs(stage)
        return runs[-1] if runs else None

    # ──────────────────────────── Intent memory ──────────────────────────────

    def record_intent_choices(self, captured: Dict[str, Any]) -> None:
        """
        Record a deploy-intent interview's captured answers.
        This feeds the smart-defaults engine.
        """
        self._data["intent_history"].append({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "choices": captured,
        })
        # Trim
        if len(self._data["intent_history"]) > MAX_INTENTS:
            self._data["intent_history"] = self._data["intent_history"][-MAX_INTENTS:]

    def get_last_intent(self) -> Optional[Dict[str, Any]]:
        """Get the most recent intent choices."""
        history = self._data["intent_history"]
        if history:
            return history[-1]["choices"]
        return None

    def suggest_intent_defaults(self) -> Dict[str, Any]:
        """
        Analyze past intent choices and return suggested defaults.

        Strategy:
        - For each field, use the most recent value as the suggestion.
        - If a field has been the same across 3+ runs, mark as "stable"
          (high confidence suggestion).
        - If a field changes frequently, mark as "volatile" (low confidence).

        Returns:
            {
                "field_name": {
                    "value": <suggested_value>,
                    "confidence": "stable" | "recent" | "volatile",
                    "times_used": N,
                    "last_used": "<iso_timestamp>",
                }
            }
        """
        history = self._data["intent_history"]
        if not history:
            return {}

        suggestions: Dict[str, Any] = {}
        all_keys = set()
        for entry in history:
            all_keys.update(entry["choices"].keys())

        for key in all_keys:
            values = []
            for entry in history:
                if key in entry["choices"]:
                    values.append(entry["choices"][key])

            if not values:
                continue

            latest = values[-1]
            same_count = sum(1 for v in values if v == latest)
            total = len(values)

            if same_count >= 3 and same_count == total:
                confidence = "stable"
            elif same_count >= 2:
                confidence = "recent"
            else:
                confidence = "volatile"

            suggestions[key] = {
                "value": latest,
                "confidence": confidence,
                "times_used": same_count,
                "total_runs": total,
                "last_used": history[-1]["timestamp"],
            }

        return suggestions

    # ──────────────────────────── Suggestion tracking ────────────────────────

    def record_suggestion(self, stage: str, accepted: bool) -> None:
        """Record whether a suggestion was accepted or rejected."""
        entry = self._data["suggestions"].setdefault(stage, {"made": 0, "accepted": 0})
        entry["made"] += 1
        if accepted:
            entry["accepted"] += 1

    def record_override(self, stage: str) -> None:
        """Record a human override of an agent's output."""
        self._data["overrides"][stage] = self._data["overrides"].get(stage, 0) + 1

    # ──────────────────────────── Trust scoring ──────────────────────────────

    def compute_trust_scores(self) -> Dict[str, TrustScore]:
        """
        Compute TrustScore for each stage based on accumulated history.
        """
        scores: Dict[str, TrustScore] = {}

        for stage, runs in self._data["stage_runs"].items():
            total = len(runs)
            successful = sum(1 for r in runs if r["status"] in ("success", "warning"))

            # Compute consecutive successes from the tail
            consecutive = 0
            for run in reversed(runs):
                if run["status"] in ("success", "warning"):
                    consecutive += 1
                else:
                    break

            # Suggestion stats
            sugg = self._data["suggestions"].get(stage, {"made": 0, "accepted": 0})
            overrides = self._data["overrides"].get(stage, 0)

            scores[stage] = TrustScore(
                stage=stage,
                total_runs=total,
                successful_runs=successful,
                suggestions_made=sugg["made"],
                suggestions_accepted=sugg["accepted"],
                human_overrides=overrides,
                consecutive_successes=consecutive,
            )

        return scores

    # ──────────────────────────── Summary ────────────────────────────────────

    def summary(self) -> Dict[str, Any]:
        """Quick overview of run history."""
        total_runs = sum(len(r) for r in self._data["stage_runs"].values())
        stages_tracked = len(self._data["stage_runs"])
        intents_recorded = len(self._data["intent_history"])

        return {
            "total_runs": total_runs,
            "stages_tracked": stages_tracked,
            "intents_recorded": intents_recorded,
            "history_path": str(self.history_path),
            "has_history": total_runs > 0,
        }
