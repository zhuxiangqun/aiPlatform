"""F2b: factory_mode agent|code|hybrid — normalize + preferred_mode → hybrid template."""
from __future__ import annotations

import asyncio
from pathlib import Path

from core.harness.execution.team_planner import (
    FACTORY_MODES,
    mode_to_team_template,
    normalize_factory_mode,
    recommend_team_stages,
    team_template_to_mode,
)

PLANNER_PATH = (
    Path(__file__).resolve().parents[3]
    / "harness"
    / "execution"
    / "team_planner.py"
)


class TestNormalizeFactoryMode:
    def test_modes_and_aliases(self):
        assert normalize_factory_mode("hybrid") == "hybrid"
        assert normalize_factory_mode("CODE") == "code"
        assert normalize_factory_mode("agent") == "agent"
        assert normalize_factory_mode("auto") == ""
        assert normalize_factory_mode("") == ""
        assert normalize_factory_mode("default") == "agent"
        assert FACTORY_MODES == frozenset({"agent", "code", "hybrid"})

    def test_mode_template_roundtrip(self):
        assert mode_to_team_template("hybrid") == "hybrid"
        assert mode_to_team_template("agent") == "default"
        assert mode_to_team_template("code") == "code"
        assert team_template_to_mode("hybrid") == "hybrid"
        assert team_template_to_mode("default.yaml") == "agent"


class TestPreferredModeLoadsHybrid:
    def test_preferred_hybrid_skips_llm_and_sets_mode(self):
        """preferred_mode=hybrid → Path 1 loads hybrid.yaml (no LLM needed)."""
        rec = asyncio.run(
            recommend_team_stages(
                requirement={"description": "chat + video pipeline"},
                preferred_mode="hybrid",
            )
        )
        assert rec.mode == "hybrid"
        assert rec.stages, "hybrid.yaml must yield stages"
        assert "template" in rec.reasoning.lower() or "hybrid" in rec.reasoning.lower()
        aids = [s.get("agent_id") for s in rec.stages]
        assert "programmer_agent" in aids
        assert "agent_engineer" in aids

    def test_prompt_allows_hybrid(self):
        text = PLANNER_PATH.read_text(encoding="utf-8")
        assert "do not output hybrid" not in text
        assert "preferred_mode" in text
        assert "hybrid" in text.lower()
