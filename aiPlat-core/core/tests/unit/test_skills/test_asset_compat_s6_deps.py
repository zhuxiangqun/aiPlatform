"""S6 A-P5/A-P4: skill dependencies.required + handler_sandbox honesty."""
from __future__ import annotations

from pathlib import Path

from core.harness.maintenance.asset_compat import (
    TIER_BLOCKED,
    TIER_PROMPT_READY,
    finalize_skill_compat,
    handler_sandbox_status,
)


def test_handler_sandbox_declared_unavailable_by_default(monkeypatch):
    monkeypatch.delenv("AIPLAT_HANDLER_SANDBOX", raising=False)
    st = handler_sandbox_status()
    assert st["status"] == "declared_unavailable"
    assert st["production_ready"] is False


def test_missing_required_dependency_not_schedulable(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "core.harness.maintenance.asset_compat.resolve_skill_dir",
        lambda _sid: None,
    )
    d = tmp_path / "needs-dep"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: needs-dep\ndescription: t\nexecution_type: prompt\n"
        "dependencies:\n  required: [missing-skill-xyz]\n---\nHi.\n",
        encoding="utf-8",
    )
    c = finalize_skill_compat(d)
    assert c["schedulable"] is False
    assert "missing-skill-xyz" in (c.get("dependencies") or {}).get("missing", [])
    assert any(i.get("code") == "missing_dependencies" for i in c.get("issues") or [])
    assert c.get("handler_sandbox", {}).get("status") == "declared_unavailable"


def test_dependency_cycle_blocks(tmp_path: Path, monkeypatch):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "SKILL.md").write_text(
        "---\nname: a\ndescription: t\nexecution_type: prompt\n"
        "dependencies:\n  required: [b]\n---\nA.\n",
        encoding="utf-8",
    )
    (b / "SKILL.md").write_text(
        "---\nname: b\ndescription: t\nexecution_type: prompt\n"
        "dependencies:\n  required: [a]\n---\nB.\n",
        encoding="utf-8",
    )

    def _resolve(sid: str):
        if sid == "a":
            return a
        if sid == "b":
            return b
        return None

    monkeypatch.setattr(
        "core.harness.maintenance.asset_compat.resolve_skill_dir",
        _resolve,
    )
    c = finalize_skill_compat(a)
    assert c["tier"] == TIER_BLOCKED
    assert c["schedulable"] is False
    assert (c.get("dependencies") or {}).get("cycle") is True


def test_no_deps_still_prompt_ready(tmp_path: Path):
    d = tmp_path / "plain"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: plain\ndescription: t\nexecution_type: prompt\n---\nHi.\n",
        encoding="utf-8",
    )
    c = finalize_skill_compat(d)
    assert c["tier"] == TIER_PROMPT_READY
    assert c["schedulable"] is True
    assert (c.get("dependencies") or {}).get("required") == []
