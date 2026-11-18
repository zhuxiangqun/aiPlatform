"""N09 K51 — tenant_id SQL/assignment literals via DomainRouter.default_tenant()."""
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
    "aiPlat-core/core/harness/knowledge/process_orchestrator.py",
    "aiPlat-core/core/harness/knowledge/wiki_engine.py",
    "aiPlat-core/core/harness/ontology_engine/state_history.py",
    "aiPlat-core/core/harness/knowledge/skill_marketplace.py",
    "aiPlat-core/core/harness/security/emotion_tracker.py",
]


def test_helper_stable():
    assert DomainRouter.default_tenant() == "default"


def test_targets_use_ssot_not_sql_literal():
    for rel in TARGETS:
        text = Path(rel).read_text(encoding="utf-8")
        assert "default_tenant()" in text, rel
        assert "tenant_id = 'default'" not in text, rel
        assert "tenant_id='default'" not in text, rel
        assert "DEFAULT 'default'" not in text or "profile_id" in text or "collection_id" in text


def test_production_tenant_sql_and_assign_literals_empty():
    """tenant_id SQL / assignment / kwarg literals cleared (collection/profile excluded)."""
    rx = re.compile(
        r"(tenant_id\s*=\s*['\"]default['\"]|tenant_id\s+TEXT[^\n]*DEFAULT\s+'default')"
    )
    hits = []
    for root in ((_repo_root() / "aiPlat-core/core"), (_repo_root() / "aiPlat-platform")):
        for p in root.rglob("*.py"):
            if "/tests/" in str(p).replace("\\", "/"):
                continue
            for i, ln in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if "collection_id" in ln or "profile_id" in ln:
                    continue
                if rx.search(ln):
                    hits.append(f"{p}:{i}:{ln.strip()}")
    assert hits == [], hits
