"""A2: pipeline_engine sys_llm_generate bypass allowlist ratchet."""
from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check_pipeline_llm_bypass.py"


def _load_mod():
    import sys

    spec = importlib.util.spec_from_file_location("check_pipeline_llm_bypass", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # dataclasses on 3.9 needs module registered before exec
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_production_pipeline_engine_clean():
    mod = _load_mod()
    allowlist, target = mod._load_allowlist(mod.ALLOWLIST_PATH)
    violations, _warnings, sites = mod.check(allowlist, target)
    assert sites, "expected at least one sys_llm_generate call"
    assert not violations, violations


def test_missing_annotation_is_violation(tmp_path: Path):
    mod = _load_mod()
    engine = tmp_path / "pipeline_engine.py"
    engine.write_text(
        textwrap.dedent(
            """
            async def _sneaky():
                await sys_llm_generate(None, [])
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    allow = tmp_path / "allow.yaml"
    allow.write_text(
        yaml.dump(
            {
                "version": 1,
                "file": str(engine),
                "entries": [],
            }
        ),
        encoding="utf-8",
    )
    allowlist, target = mod._load_allowlist(allow)
    # file path in yaml is absolute — _load_allowlist joins WORKSPACE; write relative instead
    allow.write_text(
        "version: 1\n"
        f"file: {engine}\n"
        "entries: []\n",
        encoding="utf-8",
    )
    # Bypass WORKSPACE join by calling check directly
    violations, _, sites = mod.check({}, engine)
    assert len(sites) == 1
    assert any("missing" in v for v in violations)


def test_unlisted_id_is_violation(tmp_path: Path):
    mod = _load_mod()
    engine = tmp_path / "pe.py"
    engine.write_text(
        textwrap.dedent(
            """
            async def _run_stage_core():
                # bypass-ok: not_in_list
                await sys_llm_generate(None, [])
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    violations, _, _ = mod.check(
        {"workflow_canvas_llm": mod.AllowEntry("workflow_canvas_llm", "_run_stage_core", "keep", "x")},
        engine,
    )
    assert any("not_in_list" in v or "not in" in v for v in violations)
