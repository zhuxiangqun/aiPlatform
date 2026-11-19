"""N09 K60 — agents/jobs/pipeline/tool/skill session runtime via DomainRouter.default_session()."""
from __future__ import annotations

import re
from pathlib import Path


def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")


from core.harness.knowledge.domain_router import DomainRouter

TARGETS = [
    "aiPlat-core/core/apps/agents/base.py",
    "aiPlat-core/core/apps/agents/materials_chat.py",
    "aiPlat-core/core/api/routers/agents.py",
    "aiPlat-core/core/api/routers/jobs.py",
    "aiPlat-core/core/api/routers/plugins.py",
    "aiPlat-core/core/harness/execution/pipeline_engine.py",
    "aiPlat-core/core/harness/execution/loop/compressor.py",
    "aiPlat-core/core/harness/execution/langgraph/compiled_graphs/react.py",
    "aiPlat-core/core/harness/integration/tool.py",
    "aiPlat-core/core/harness/integration/skill.py",
    "aiPlat-core/core/harness/infrastructure/gates/policy_gate.py",
]


def test_helper_stable():
    assert DomainRouter.default_session() == "default"


def test_targets_use_session_ssot():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert "DomainRouter.default_session()" in text, rel
        assert 'session_id or "default"' not in text, rel
        assert 'get("session_id", "default")' not in text, rel


def test_target_runtime_session_fallbacks_empty():
    """K60 targets: no remaining session \"default\" runtime fallbacks."""
    hits = []
    for rel in TARGETS:
        path = _repo_root() / rel
        for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "default_session" in ln or "PLATFORM_DEFAULT_SESSION" in ln:
                continue
            if "session" not in ln.lower():
                continue
            if 'or "default"' in ln or "or 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif re.search(r'get\(["\']session_id["\'],\s*["\']default["\']\)', ln):
                hits.append(f"{rel}:{i}:{ln.strip()}")
    assert hits == [], hits
