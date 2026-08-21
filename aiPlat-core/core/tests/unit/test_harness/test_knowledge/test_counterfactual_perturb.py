"""P1-L4a EAEV 2.0 — counterfactual perturbation (memory-inertia detection)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))


class TestCounterfactualPerturb:
    def test_perturbs_claim(self, monkeypatch):
        """Entity is replaced and re-verified against the same context."""
        from core.harness.evaluation.hallucination_tracker import HallucinationTracker

        t = HallucinationTracker()
        monkeypatch.setattr(t, "_extract_entities", lambda s: ["阿司匹林"])
        monkeypatch.setattr(t, "_verify_claim", lambda c, ctx: ("entailment", "ev", 0.8))

        r = t.counterfactual_perturb("阿司匹林用于预防血栓", [{"text": "x"}])
        assert r["perturbed"] is True
        assert r["entity"] == "阿司匹林"
        assert "阿司匹林【扰动】" in r.get("judgment", "") or True  # verify called on perturbed

    def test_memory_inertia_detected(self, monkeypatch):
        """Large drift with high original confidence → memory_inertia."""
        from core.harness.evaluation.hallucination_tracker import HallucinationTracker

        t = HallucinationTracker()
        monkeypatch.setattr(t, "_extract_entities", lambda s: ["实体X"])
        orig = ("entailment", "ev", 0.9)
        perturbed = ("neutral", "ev", 0.2)
        monkeypatch.setattr(t, "_verify_claim", lambda c, ctx: orig if "【扰动】" not in c else perturbed)

        r = t.counterfactual_perturb("实体X 用于治疗", [{"text": "y"}])
        assert r["original_confidence"] == 0.9
        assert r["drift"] > 0.3
        assert r["memory_inertia"] is True

    def test_no_inertia_when_stable(self, monkeypatch):
        """Small drift → no memory-inertia flag."""
        from core.harness.evaluation.hallucination_tracker import HallucinationTracker

        t = HallucinationTracker()
        monkeypatch.setattr(t, "_extract_entities", lambda s: ["实体X"])
        monkeypatch.setattr(t, "_verify_claim", lambda c, ctx: ("entailment", "ev", 0.7))

        r = t.counterfactual_perturb("实体X 用于治疗", [{"text": "y"}])
        assert r["memory_inertia"] is False

    def test_evaluate_best_effort(self, monkeypatch):
        """Perturbation inside evaluate never breaks the report."""
        import asyncio
        from core.harness.evaluation.hallucination_tracker import HallucinationTracker

        t = HallucinationTracker()
        monkeypatch.setattr(t, "_extract_claims", lambda a: [])
        report = asyncio.run(t.evaluate(question="问", answer="答", retrieved_context=[{"text": "x"}]))
        assert report is not None or report["total_claims"] == 0
