"""P1-L3 ontology constraint compiler — pre-generation logic lock."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))


class TestOntologyConstraintCompiler:
    def test_compiles_axioms_and_fields(self):
        from core.harness.knowledge.ontology_constraint_compiler import (
            compile_ontology_constraints, compile_axiom_rules)

        out = compile_ontology_constraints()
        assert "本体业务约束" in out
        assert "MUST" in out or "应当" in out
        rules = compile_axiom_rules()
        assert isinstance(rules, list) and len(rules) > 0

    def test_prompt_assembler_opt_in_injection(self):
        """meta.inject_ontology_contract=True injects the compiled block."""
        from core.harness.assembly.prompt_assembler import MessageFormatter

        pa = MessageFormatter()
        out = pa.assemble(
            [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}],
            metadata={"inject_ontology_contract": True},
        )
        joined = str(out)
        assert "本体业务约束" in joined

    def test_default_no_injection(self):
        """Without the flag, no ontology block is injected (cache stable)."""
        from core.harness.assembly.prompt_assembler import MessageFormatter

        pa = MessageFormatter()
        out = pa.assemble([{"role": "user", "content": "hi"}], metadata={})
        assert "本体业务约束" not in str(out)
