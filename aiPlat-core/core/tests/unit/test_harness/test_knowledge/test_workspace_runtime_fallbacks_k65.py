"""N09 K65 — workspace_id runtime via DomainRouter.default_workspace_id()."""
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
    "aiPlat-core/core/harness/knowledge/domain_router.py",
    "aiPlat-core/core/harness/named_workspace/registry.py",
    "aiPlat-core/core/harness/named_workspace/resolve.py",
    "aiPlat-core/core/apps/eval/service/external_exam_ops.py",
    "aiPlat-core/core/apps/eval/service/external_targets.py",
]


def test_helper_stable():
    assert DomainRouter.default_workspace_id() == "default"
    assert DomainRouter.PLATFORM_DEFAULT_WORKSPACE == "default"
    assert DomainRouter().default_workspace_id() == DomainRouter.default_workspace_id()


def test_targets_use_workspace_ssot():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert "default_workspace_id()" in text or "PLATFORM_DEFAULT_WORKSPACE" in text, rel


def test_target_runtime_workspace_fallbacks_empty():
    """K65 targets: no remaining workspace_id \"default\" runtime fallbacks."""
    hits = []
    for rel in TARGETS:
        path = _repo_root() / rel
        for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "default_workspace_id" in ln or "PLATFORM_DEFAULT_WORKSPACE" in ln:
                continue
            low = ln.lower()
            if "workspace" not in low and "wid" not in low:
                continue
            if '== "default"' in ln or "== 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif 'or "default"' in ln or "or 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif re.search(r'=\s*["\']default["\']', ln) and "workspace" in low:
                hits.append(f"{rel}:{i}:{ln.strip()}")
            elif 'raw = "default"' in ln or "raw = 'default'" in ln:
                hits.append(f"{rel}:{i}:{ln.strip()}")
    assert hits == [], hits
