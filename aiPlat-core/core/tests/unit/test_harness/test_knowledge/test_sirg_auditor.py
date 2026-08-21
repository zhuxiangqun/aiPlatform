"""P1-L4b SIRG — reasoning vs rule-chain consistency audit."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

RULES = [
    {"name": "r_bleed", "premises": [{"relation": "is_anticoagulant"}],
     "conclusion": {"relation": "has_bleeding_risk"}},
    {"name": "r_bleed_2", "premises": [{"relation": "is_antiplatelet"}],
     "conclusion": {"relation": "has_bleeding_risk"}},
    {"name": "r_unrelated", "premises": [{"relation": "is_metal"}],
     "conclusion": {"relation": "has_weight"}},
]


class TestSirgAuditor:
    def test_rule_chain_extraction(self):
        from core.harness.ontology_engine.sirg_auditor import SirgAuditor

        a = SirgAuditor(RULES)
        chain = a.rule_chain_for("has_bleeding_risk")
        assert sorted(chain) == ["r_bleed", "r_bleed_2"]

    def test_missing_rule_violation(self):
        from core.harness.ontology_engine.sirg_auditor import SirgAuditor

        a = SirgAuditor(RULES)
        r = a.audit_reasoning(["r_bleed"], "has_bleeding_risk")
        assert r["consistent"] is False
        assert "r_bleed_2" in r["missing"]
        assert "跳过" in r["violation_report"]

    def test_complete_chain_consistent(self):
        from core.harness.ontology_engine.sirg_auditor import SirgAuditor

        a = SirgAuditor(RULES)
        r = a.audit_reasoning(["r_bleed", "r_bleed_2"], "has_bleeding_risk")
        assert r["consistent"] is True
        assert r["missing"] == []

    def test_from_inference(self):
        from core.harness.ontology_engine.sirg_auditor import SirgAuditor

        class StubInf:
            def __init__(self):
                self._rules = list(RULES)
            def list_rules(self):
                return self._rules

        a = SirgAuditor.from_inference(StubInf())
        assert len(a.rule_chain_for("has_bleeding_risk")) == 2
