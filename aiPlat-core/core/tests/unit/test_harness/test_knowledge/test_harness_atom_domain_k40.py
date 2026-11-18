"""N09 K40 — harness GraphIndex atom/kb/terms via DomainRouter."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")


TARGETS = [
    "aiPlat-core/core/harness/knowledge/seci_engine.py",
    "aiPlat-core/core/harness/knowledge/context_bus.py",
    "aiPlat-core/core/harness/knowledge/convergence_engine.py",
    "aiPlat-core/core/harness/knowledge/system_diagnostician.py",
    "aiPlat-core/core/harness/knowledge/system_evolver.py",
    "aiPlat-core/core/harness/knowledge/orchestrated_retrieval.py",
    "aiPlat-core/core/harness/execution/pipeline_engine.py",
    "aiPlat-core/core/apps/skills/registry.py",
    "aiPlat-core/core/api/routers/wiki.py",
]

HARD = ("knowledge-atom", "ai-knowledge", "enterprise-terms")


def test_harness_targets_no_hardcoded_graphindex_domain_loads():
    bare = []
    for rel in TARGETS:
        for i, ln in enumerate(Path(rel).read_text(encoding="utf-8").splitlines(), 1):
            if "GraphIndex.load(" not in ln:
                continue
            if any(f'GraphIndex.load("{d}"' in ln for d in HARD):
                bare.append(f"{rel}:{i}")
    assert bare == [], bare


def test_harness_loads_use_domain_router_helpers():
    text = (_repo_root() / "aiPlat-core/core/harness/knowledge/seci_engine.py").read_text(
        encoding="utf-8"
    )
    assert "knowledge_atom_domain()" in text
    text2 = (_repo_root() / "aiPlat-core/core/api/routers/wiki.py").read_text(encoding="utf-8")
    assert "default_kb_domain()" in text2
    text3 = (_repo_root() / "aiPlat-core/core/apps/skills/registry.py").read_text(encoding="utf-8")
    assert "terms_domain()" in text3


def test_seci_metadata_domain_not_literal():
    text = (_repo_root() / "aiPlat-core/core/harness/knowledge/seci_engine.py").read_text(
        encoding="utf-8"
    )
    assert '"domain": "knowledge-atom"' not in text


def test_production_graphindex_literal_inventory_nearly_clear():
    """K40 baseline; K41 clears bell-competition — inventory must stay empty."""
    from pathlib import Path
    import re

    rx = re.compile(r'GraphIndex\.load\(\s*["\']([a-z0-9_-]+)["\']')
    hits = []
    for root in ((_repo_root() / "aiPlat-core/core"), (_repo_root() / "aiPlat-platform")):
        for p in root.rglob("*.py"):
            if "/tests/" in str(p):
                continue
            for i, ln in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                m = rx.search(ln)
                if m:
                    hits.append((m.group(1), f"{p}:{i}"))
    domains = sorted({d for d, _ in hits})
    assert domains == [], domains
