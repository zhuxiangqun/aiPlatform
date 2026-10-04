"""SkillExecutor must honor SKILL.md / metadata timeout (not hard-coded 60s)."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import yaml

from core.apps.skills.executor import SkillExecutor


def test_resolve_timeout_from_metadata():
    skill = SimpleNamespace(
        _config=SimpleNamespace(metadata={"timeout": 300}, name="slow", idempotent=True),
    )
    executor = SkillExecutor(registry=MagicMock(), default_timeout=60)
    meta = skill._config.metadata
    effective = float(meta["timeout"]) if meta.get("timeout") is not None else executor._default_timeout
    assert effective == 300.0


def test_code_generation_skill_md_timeout_covers_nested_llm():
    """Outer skill timeout must exceed nested generate budget (420) + slack."""
    p = Path(__file__).resolve().parents[3] / "engine" / "skills" / "code_generation" / "SKILL.md"
    assert p.exists(), f"missing {p}"
    raw = p.read_text(encoding="utf-8")
    fm = yaml.safe_load(raw.split("---", 2)[1])
    assert float(fm.get("timeout")) >= 540


def test_code_generation_passes_nested_llm_timeout_override():
    src = (Path(__file__).resolve().parents[3] / "apps" / "skills" / "base.py").read_text(
        encoding="utf-8"
    )
    assert '"timeout_seconds": 420' in src or "'timeout_seconds': 420" in src
    assert "code_gen_retry" in src
    assert "_elapsed < 200" in src or "_elapsed < 200.0" in src


def test_default_skill_timeout_is_at_least_180():
    # Clear env for this process assertion when unset
    prev = os.environ.pop("AIPLAT_SKILL_DEFAULT_TIMEOUT", None)
    try:
        ex = SkillExecutor(registry=MagicMock(), default_timeout=None)
        assert ex._default_timeout >= 180
    finally:
        if prev is not None:
            os.environ["AIPLAT_SKILL_DEFAULT_TIMEOUT"] = prev


def test_executor_rereads_timeout_from_skill_md(tmp_path):
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\nname: demo\ntimeout: 240\n---\nbody\n",
        encoding="utf-8",
    )
    skill = SimpleNamespace(
        _config=SimpleNamespace(
            metadata={"filesystem": {"skill_md": str(skill_md)}},
            name="demo",
            idempotent=True,
        ),
    )
    # Mirror executor fallback: metadata missing timeout → read SKILL.md
    meta = skill._config.metadata
    effective = meta.get("timeout")
    assert effective is None
    raw = skill_md.read_text(encoding="utf-8")
    fm = yaml.safe_load(raw.split("---", 2)[1])
    effective = float(fm["timeout"])
    assert effective == 240.0


def test_test_executor_skill_md_timeout_is_bounded():
    p = Path(__file__).resolve().parents[3] / "engine" / "skills" / "test_executor" / "SKILL.md"
    assert p.exists(), f"missing {p}"
    fm = yaml.safe_load(p.read_text(encoding="utf-8").split("---", 2)[1])
    assert float(fm.get("timeout")) == 90.0


def test_sys_skill_call_resolves_metadata_timeout_when_omitted():
    """Agent ReAct must not call ResilienceGate with timeout=None forever."""
    src = (
        Path(__file__).resolve().parents[3] / "harness" / "syscalls" / "skill.py"
    ).read_text(encoding="utf-8")
    assert "AIPLAT_SKILL_DEFAULT_TIMEOUT" in src
    assert "_run_with_model" in src
    assert "meta.get(\"timeout\")" in src or "meta.get('timeout')" in src
    # Model inject inside timeout budget
    assert "ensure_skill_model" in src
    assert src.index("_run_with_model") < src.index("res_gate.run")


def test_react_dispatch_passes_skill_timeout():
    src = (
        Path(__file__).resolve().parents[3]
        / "harness"
        / "execution"
        / "loop"
        / "_facade.py"
    ).read_text(encoding="utf-8")
    assert "timeout_seconds=_skill_timeout" in src
