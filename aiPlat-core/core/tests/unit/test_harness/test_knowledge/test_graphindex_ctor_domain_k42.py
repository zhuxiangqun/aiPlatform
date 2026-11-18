"""N09 K42 — GraphIndex ctor domain via DomainRouter (no bare domain literals)."""
from __future__ import annotations

import re
from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")


TARGETS = [
    "aiPlat-core/core/harness/evaluation/hallucination_tracker.py",
    "aiPlat-core/core/harness/knowledge/doc_quality_monitor.py",
    "aiPlat-core/core/harness/syscalls/retrieval.py",
]


def test_domain_router_default_graph_domain():
    from core.harness.knowledge.domain_router import DomainRouter

    r = DomainRouter()
    assert r.default_graph_domain() == DomainRouter.PLATFORM_DEFAULT_GRAPH_DOMAIN
    assert r.default_graph_domain() == "default"
    assert r.default_kb_domain() != r.default_graph_domain()


def test_targets_use_domain_router_helpers():
    ht = Path(TARGETS[0]).read_text(encoding="utf-8")
    assert "default_kb_domain()" in ht
    assert 'GraphIndex("ai-knowledge"' not in ht

    dq = Path(TARGETS[1]).read_text(encoding="utf-8")
    assert "default_graph_domain()" in dq
    assert 'GraphIndex("default"' not in dq

    ret = Path(TARGETS[2]).read_text(encoding="utf-8")
    assert "default_graph_domain()" in ret
    assert "domain_id or get_domain_router().default_graph_domain()" in ret
    # GraphIndex early-exit must not keep bare domain fallback (tenant "default" OK)
    assert not re.search(
        r'GraphIndex\([^)]*domain_id\s*=\s*domain_id\s+or\s+["\']default["\']',
        ret,
        re.DOTALL,
    )


def test_production_graphindex_ctor_domain_literals_empty():
    """No GraphIndex(<quoted-domain>) / domain_id=<quoted> in production."""
    rx_pos = re.compile(r'GraphIndex\(\s*["\']([a-z0-9_-]+)["\']')
    rx_kw = re.compile(r'GraphIndex\([^)]*domain_id\s*=\s*["\']([a-z0-9_-]+)["\']')
    hits = []
    for root in ((_repo_root() / "aiPlat-core/core"), (_repo_root() / "aiPlat-platform")):
        for p in root.rglob("*.py"):
            if "/tests/" in str(p).replace("\\", "/"):
                continue
            for i, ln in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if "GraphIndex.load" in ln:
                    continue
                for rx in (rx_pos, rx_kw):
                    m = rx.search(ln)
                    if m:
                        hits.append(f"{p}:{i}:{m.group(1)}")
    assert hits == [], hits
