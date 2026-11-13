"""Phase A: prompt schedulable; script → draft not handler; blocked not schedulable."""
from __future__ import annotations

from pathlib import Path

from core.harness.maintenance.asset_compat import (
    TIER_BLOCKED,
    TIER_NEEDS_HANDLER,
    TIER_PROMPT_READY,
    enable_handler_draft,
    finalize_skill_compat,
    is_skill_schedulable,
    skill_schedulable_error,
)
from core.management.skill_adapter import adapt_skill


def test_pure_prompt_and_script_draft(tmp_path: Path):
    d = tmp_path / "grill-me"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: grill-me\ndescription: t\nexecution_type: prompt\n---\nAsk hard questions.\n",
        encoding="utf-8",
    )
    c = (adapt_skill(d) or {}).get("compat") or finalize_skill_compat(d)
    assert c["tier"] == TIER_PROMPT_READY and c["schedulable"] is True
    s = tmp_path / "scripty"
    s.mkdir()
    (s / "scripts").mkdir()
    (s / "scripts" / "main.py").write_text("print(1)\n", encoding="utf-8")
    (s / "SKILL.md").write_text(
        "---\nname: scripty\ndescription: t\nexecution_type: prompt\n---\nRun script.\n",
        encoding="utf-8",
    )
    c2 = (adapt_skill(s) or {}).get("compat") or finalize_skill_compat(s)
    assert (s / "handler.py.draft").is_file() and not (s / "handler.py").exists()
    assert c2["schedulable"] is True and c2["upgrade"]["recommended"] == "enable_handler"
    assert enable_handler_draft(s)["ok"] is True and (s / "handler.py").is_file()


def test_blocked_and_needs_handler_not_schedulable(tmp_path: Path):
    blocked = tmp_path / "blocked-skill"
    blocked.mkdir()
    (blocked / "SKILL.md").write_text(
        "---\nname: blocked-skill\ndescription: t\nexecution_type: prompt\n"
        "block_reason: unsafe_tool\n---\nNo.\n",
        encoding="utf-8",
    )
    c = finalize_skill_compat(blocked)
    assert c["tier"] == TIER_BLOCKED and c["schedulable"] is False
    assert is_skill_schedulable(blocked) is False
    err = skill_schedulable_error(blocked, skill_id="blocked-skill")
    assert err["error"] == "skill_not_schedulable" and err["tier"] == TIER_BLOCKED

    needs = tmp_path / "needs-h"
    needs.mkdir()
    (needs / "SKILL.md").write_text(
        "---\nname: needs-h\ndescription: t\nexecution_type: handler\n---\nNeeds code.\n",
        encoding="utf-8",
    )
    c2 = finalize_skill_compat(needs)
    assert c2["tier"] == TIER_NEEDS_HANDLER and c2["schedulable"] is False
    assert is_skill_schedulable(needs) is False


def test_pre_phase_a_dir_without_compat_fail_open(tmp_path: Path):
    old = tmp_path / "legacy"
    old.mkdir()
    (old / "SKILL.md").write_text(
        "---\nname: legacy\ndescription: t\nexecution_type: prompt\n---\nHi.\n",
        encoding="utf-8",
    )
    assert not (old / "COMPAT.yaml").exists()
    assert is_skill_schedulable(old) is True


def test_missing_capabilities_not_schedulable(tmp_path: Path):
    d = tmp_path / "toolish"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: toolish\ndescription: t\nexecution_type: prompt\n"
        "tools:\n  - bash\nmissing_capabilities:\n  - bash\n---\nNeeds map.\n",
        encoding="utf-8",
    )
    c = finalize_skill_compat(d)
    assert c["tier"] == TIER_NEEDS_HANDLER and c["schedulable"] is False
    assert any(i.get("code") == "missing_capabilities" for i in c["issues"])


def test_sys_skill_call_gate_reads_filesystem_metadata(tmp_path: Path):
    """Gate must resolve skill_dir from config.metadata.filesystem (registry shape)."""
    import asyncio
    from types import SimpleNamespace

    from core.harness.interfaces import SkillResult
    from core.harness.syscalls.skill import sys_skill_call

    d = tmp_path / "gated"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: gated\ndescription: t\nexecution_type: prompt\n"
        "block_reason: denied\n---\nNo.\n",
        encoding="utf-8",
    )
    finalize_skill_compat(d)
    cfg = SimpleNamespace(
        name="gated",
        metadata={"filesystem": {"skill_dir": str(d)}},
        skill_dir=None,
    )
    skill = SimpleNamespace(name="gated", _config=cfg, skill_dir=None, root_dir=None, metadata={})

    result = asyncio.run(sys_skill_call(skill, {}, user_id="t", session_id="t"))
    assert isinstance(result, SkillResult)
    assert result.success is False
    assert result.error == "skill_not_schedulable"
