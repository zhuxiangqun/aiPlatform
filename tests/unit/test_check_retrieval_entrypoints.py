"""W4: retrieval entrypoint guard."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check_retrieval_entrypoints.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("check_retrieval_entrypoints", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_workspace_entrypoints_clean():
    mod = _load_mod()
    violations, n = mod.check()
    assert n >= 1
    assert violations == [], violations


def test_raw_kb_retrieve_in_agent_flagged(tmp_path: Path, monkeypatch):
    mod = _load_mod()
    # Point SCAN to a temp agent file
    agent = tmp_path / "bad_agent.py"
    agent.write_text("async def f():\n    kb_retrieve(query='x', doc_ids=[])\n", encoding="utf-8")
    monkeypatch.setattr(mod, "SCAN_GLOBS", [str(agent)])
    # check() uses WORKSPACE.glob — override by calling _scan_file directly
    v = mod._scan_file(agent)
    assert v and "kb_retrieve" in v[0]


def test_crag_call_not_flagged(tmp_path: Path):
    mod = _load_mod()
    agent = tmp_path / "good_agent.py"
    agent.write_text(
        "async def f():\n    await kb_qa_retrieve(query='x')\n",
        encoding="utf-8",
    )
    assert mod._scan_file(agent) == []
