"""S5: handler.py → handler_ready + execution_surface（非 prompt_ready）。"""

from __future__ import annotations

from pathlib import Path


def test_handler_py_yields_handler_ready(tmp_path: Path):
    from core.harness.maintenance.asset_compat import (
        TIER_HANDLER_READY,
        finalize_skill_compat,
    )

    d = tmp_path / "with_handler"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: with_handler\nexecution_type: handler\n---\nRun handler.\n",
        encoding="utf-8",
    )
    (d / "handler.py").write_text("def run(**kwargs):\n    return {'ok': True}\n", encoding="utf-8")
    c = finalize_skill_compat(d)
    assert c.get("tier") == TIER_HANDLER_READY
    assert c.get("execution_surface") == "handler"
    assert c.get("schedulable") is True
    assert c.get("ui_state") == "现在就能用"


def test_prompt_only_stays_prompt_ready(tmp_path: Path):
    from core.harness.maintenance.asset_compat import finalize_skill_compat

    d = tmp_path / "prompt_only"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: prompt_only\nexecution_type: prompt\n---\nAnswer briefly.\n",
        encoding="utf-8",
    )
    c = finalize_skill_compat(d)
    assert c.get("tier") == "prompt_ready"
    assert c.get("execution_surface") == "prompt"
    assert c.get("schedulable") is True
