"""N09 K69 — misc label defaults via DomainRouter.default_label()."""
from __future__ import annotations

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
    "aiPlat-core/core/schemas_gateway.py",
    "aiPlat-core/core/services/execution_store/session_mixin.py",
    "aiPlat-core/core/learning/manager.py",
    "aiPlat-core/core/schemas_builder.py",
]


def test_helper_stable():
    assert DomainRouter.default_label() == "default"
    assert DomainRouter.PLATFORM_DEFAULT_LABEL == "default"


def test_targets_use_label_ssot():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert "default_label()" in text or "PLATFORM_DEFAULT_LABEL" in text, rel


def test_target_misc_label_defaults_empty():
    """K69 targets: no channel/agent_type/benchmark/output_style \"default\" literals."""
    hits = []
    needles = (
        'channel: str = "default"',
        'agent_type: str = "default"',
        'benchmark_name: str = "default"',
        'output_style: str = "default"',
    )
    for rel in TARGETS:
        path = _repo_root() / rel
        for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "default_label" in ln or "PLATFORM_DEFAULT_LABEL" in ln:
                continue
            for n in needles:
                if n in ln:
                    hits.append(f"{rel}:{i}:{ln.strip()}")
    assert hits == [], hits
