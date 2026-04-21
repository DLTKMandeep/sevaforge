"""
Tests for the Intelligence Maturity framework.

Covers:
- IntelligencePhase enum properties
- StageMaturity classification
- TrustScore computation and phase earning
- Pipeline maturity report generation
- RunHistory persistence, intent memory, and trust scoring
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

# Ensure forgeflow/ is importable
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.intelligence_maturity import (
    IntelligencePhase,
    StageMaturity,
    TrustScore,
    STAGE_MATURITY,
    get_pipeline_maturity,
)
from core.run_history import RunHistory


# ─────────────────────────────────────────────────────────────────────────────
# IntelligencePhase
# ─────────────────────────────────────────────────────────────────────────────

class TestIntelligencePhase:
    def test_values(self):
        assert IntelligencePhase.ASSISTED == 1
        assert IntelligencePhase.AUTOMATED == 2
        assert IntelligencePhase.AUGMENTED == 3
        assert IntelligencePhase.AGENTIC == 4

    def test_labels(self):
        assert IntelligencePhase.ASSISTED.label == "Assisted"
        assert IntelligencePhase.AGENTIC.label == "Agentic"

    def test_icons(self):
        assert IntelligencePhase.ASSISTED.icon == "👁️"
        assert IntelligencePhase.AGENTIC.icon == "🤖"

    def test_ordering(self):
        assert IntelligencePhase.ASSISTED < IntelligencePhase.AUTOMATED
        assert IntelligencePhase.AUTOMATED < IntelligencePhase.AUGMENTED
        assert IntelligencePhase.AUGMENTED < IntelligencePhase.AGENTIC

    def test_goals(self):
        assert "trust" in IntelligencePhase.ASSISTED.goal.lower()
        assert "reliability" in IntelligencePhase.AUTOMATED.goal.lower()

    def test_metrics(self):
        assert "adoption" in IntelligencePhase.ASSISTED.metric.lower()
        assert "autonomous" in IntelligencePhase.AGENTIC.metric.lower()


# ─────────────────────────────────────────────────────────────────────────────
# StageMaturity
# ─────────────────────────────────────────────────────────────────────────────

class TestStageMaturity:
    def test_gap_calculation(self):
        sm = StageMaturity("test", IntelligencePhase.ASSISTED, IntelligencePhase.AUGMENTED)
        assert sm.gap == 2
        assert not sm.at_target

    def test_at_target(self):
        sm = StageMaturity("test", IntelligencePhase.AUGMENTED, IntelligencePhase.AUGMENTED)
        assert sm.gap == 0
        assert sm.at_target

    def test_to_dict(self):
        sm = StageMaturity("discover", IntelligencePhase.ASSISTED, IntelligencePhase.AUGMENTED, "test rationale")
        d = sm.to_dict()
        assert d["stage"] == "discover"
        assert d["current_phase"] == 1
        assert d["target_phase"] == 3
        assert d["gap"] == 2
        assert "test rationale" in d["rationale"]

    def test_all_16_stages_classified(self):
        """Every pipeline stage must have a maturity classification."""
        pipeline_stages = [
            "discover", "normalize", "docs", "iac", "cd", "ci", "e2e",
            "review", "test", "scan", "deploy-intent", "deploy-design",
            "deploy-validate", "secrets", "lifecycle", "bridge",
        ]
        for stage in pipeline_stages:
            assert stage in STAGE_MATURITY, f"Stage '{stage}' missing from STAGE_MATURITY"

    def test_capabilities_are_dicts(self):
        for name, sm in STAGE_MATURITY.items():
            assert isinstance(sm.capabilities, dict), f"{name} capabilities is not a dict"


# ─────────────────────────────────────────────────────────────────────────────
# TrustScore
# ─────────────────────────────────────────────────────────────────────────────

class TestTrustScore:
    def test_empty_score(self):
        ts = TrustScore("test")
        assert ts.score >= 0
        assert ts.reliability == 0.0
        assert ts.earned_phase == IntelligencePhase.ASSISTED

    def test_perfect_score(self):
        ts = TrustScore(
            "test",
            total_runs=20,
            successful_runs=20,
            suggestions_made=10,
            suggestions_accepted=10,
            human_overrides=0,
            consecutive_successes=15,
        )
        assert ts.score >= 85
        assert ts.earned_phase == IntelligencePhase.AGENTIC

    def test_moderate_score(self):
        ts = TrustScore(
            "test",
            total_runs=10,
            successful_runs=8,
            suggestions_made=5,
            suggestions_accepted=3,
            human_overrides=1,
            consecutive_successes=6,
        )
        assert ts.score >= 40
        assert ts.earned_phase.value >= 2  # At least Automated

    def test_reliability(self):
        ts = TrustScore("test", total_runs=10, successful_runs=7)
        assert abs(ts.reliability - 0.7) < 0.01

    def test_acceptance_rate(self):
        ts = TrustScore("test", suggestions_made=10, suggestions_accepted=6)
        assert abs(ts.acceptance_rate - 0.6) < 0.01

    def test_to_dict(self):
        ts = TrustScore("scan", total_runs=5, successful_runs=5, consecutive_successes=5)
        d = ts.to_dict()
        assert d["stage"] == "scan"
        assert d["trust_score"] > 0
        assert d["reliability"] == 100.0
        assert d["total_runs"] == 5


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline maturity report
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineMaturity:
    def test_report_without_history(self):
        report = get_pipeline_maturity()
        assert report["total_stages"] == 16
        assert "overall_label" in report
        assert "phase_distribution" in report
        assert len(report["stages"]) == 16

    def test_report_with_trust_scores(self):
        scores = {
            "discover": TrustScore("discover", total_runs=5, successful_runs=5, consecutive_successes=5),
        }
        report = get_pipeline_maturity(scores)
        # discover stage should have trust info
        discover = [s for s in report["stages"] if s["stage"] == "discover"][0]
        assert discover["trust"] is not None
        assert discover["trust"]["total_runs"] == 5


# ─────────────────────────────────────────────────────────────────────────────
# RunHistory
# ─────────────────────────────────────────────────────────────────────────────

class TestRunHistory:
    @pytest.fixture
    def tmp_project(self, tmp_path):
        """Create a temporary project directory."""
        return tmp_path

    def test_empty_history(self, tmp_project):
        h = RunHistory(tmp_project)
        summary = h.summary()
        assert summary["total_runs"] == 0
        assert not summary["has_history"]

    def test_record_and_persist(self, tmp_project):
        h = RunHistory(tmp_project)
        h.record_stage("discover", "success", summary="Found 42 files")
        h.record_stage("scan", "warning", summary="3 low-severity issues")
        h.save()

        # Reload
        h2 = RunHistory(tmp_project)
        assert h2.summary()["total_runs"] == 2
        assert h2.summary()["stages_tracked"] == 2

    def test_stage_runs_list(self, tmp_project):
        h = RunHistory(tmp_project)
        h.record_stage("discover", "success")
        h.record_stage("discover", "error")
        h.record_stage("discover", "success")
        h.save()

        runs = h.get_stage_runs("discover")
        assert len(runs) == 3
        assert runs[0]["status"] == "success"
        assert runs[1]["status"] == "error"

    def test_last_run(self, tmp_project):
        h = RunHistory(tmp_project)
        h.record_stage("scan", "success", summary="clean")
        h.record_stage("scan", "warning", summary="2 issues")
        h.save()

        last = h.get_last_run("scan")
        assert last["status"] == "warning"
        assert last["summary"] == "2 issues"

    def test_intent_memory(self, tmp_project):
        h = RunHistory(tmp_project)
        h.record_intent_choices({"cloud_provider": "gcp", "compute_model": "kubernetes"})
        h.save()

        last = h.get_last_intent()
        assert last["cloud_provider"] == "gcp"

    def test_smart_defaults_stable(self, tmp_project):
        h = RunHistory(tmp_project)
        for _ in range(3):
            h.record_intent_choices({"cloud_provider": "gcp", "cloud_region": "us-central1"})
        h.save()

        defaults = h.suggest_intent_defaults()
        assert "cloud_provider" in defaults
        assert defaults["cloud_provider"]["value"] == "gcp"
        assert defaults["cloud_provider"]["confidence"] == "stable"

    def test_smart_defaults_volatile(self, tmp_project):
        h = RunHistory(tmp_project)
        h.record_intent_choices({"cloud_provider": "gcp"})
        h.record_intent_choices({"cloud_provider": "aws"})
        h.record_intent_choices({"cloud_provider": "azure"})
        h.save()

        defaults = h.suggest_intent_defaults()
        assert defaults["cloud_provider"]["confidence"] == "volatile"
        assert defaults["cloud_provider"]["value"] == "azure"  # most recent

    def test_suggestion_tracking(self, tmp_project):
        h = RunHistory(tmp_project)
        h.record_suggestion("deploy-intent", accepted=True)
        h.record_suggestion("deploy-intent", accepted=True)
        h.record_suggestion("deploy-intent", accepted=False)
        h.save()

        h2 = RunHistory(tmp_project)
        scores = h2.compute_trust_scores()
        # No stage runs yet, so no trust scores for stages
        # But suggestion data is stored
        assert h2._data["suggestions"]["deploy-intent"]["made"] == 3
        assert h2._data["suggestions"]["deploy-intent"]["accepted"] == 2

    def test_trust_score_computation(self, tmp_project):
        h = RunHistory(tmp_project)
        for i in range(8):
            h.record_stage("discover", "success")
        h.record_stage("discover", "error")
        h.record_stage("discover", "success")
        h.save()

        scores = h.compute_trust_scores()
        assert "discover" in scores
        ts = scores["discover"]
        assert ts.total_runs == 10
        assert ts.successful_runs == 9
        assert ts.consecutive_successes == 1  # only the last one after the error
        assert ts.reliability == 0.9

    def test_max_runs_trim(self, tmp_project):
        h = RunHistory(tmp_project)
        for i in range(150):
            h.record_stage("discover", "success")
        h.save()

        h2 = RunHistory(tmp_project)
        runs = h2.get_stage_runs("discover")
        assert len(runs) <= 100  # trimmed to MAX_RUNS
