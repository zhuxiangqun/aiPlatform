"""N09 K46 — it-ops / data-gov signature defaults via DomainRouter PLATFORM_* constants."""
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
    "aiPlat-core/core/api/core_facade.py",
    "aiPlat-core/core/apps/fde/service/abox_connector.py",
    "aiPlat-core/core/apps/fde/service/governance_deepen.py",
    "aiPlat-core/core/apps/fde/service/k_wave_propose.py",
    "aiPlat-core/core/apps/org/service/org_approvals.py",
    "aiPlat-core/core/apps/org/service/org_auto_pass.py",
    "aiPlat-core/core/apps/org/service/org_evidence_pack.py",
    "aiPlat-core/core/apps/org/service/org_field_ops.py",
    "aiPlat-core/core/apps/org/service/org_fleet.py",
    "aiPlat-core/core/apps/org/service/org_ingress.py",
    "aiPlat-core/core/apps/org/service/org_interface.py",
    "aiPlat-core/core/apps/org/service/org_kpi.py",
    "aiPlat-core/core/apps/org/service/org_live_adapter.py",
    "aiPlat-core/core/apps/org/service/org_runtime.py",
    "aiPlat-core/core/apps/org/service/org_skill_draft.py",
    "aiPlat-core/core/apps/org/service/org_value_translation.py",
    "aiPlat-core/core/apps/org/service/v_wave_replay.py",
    "aiPlat-core/core/harness/knowledge/ontology_case_learning.py",
    "aiPlat-core/core/policy/graph_abox_acl.py",
]


def test_platform_constants_and_helpers():
    assert DomainRouter.PLATFORM_IT_OPS_DOMAIN == "it-ops"
    assert DomainRouter.PLATFORM_DATA_GOV_DOMAIN == "data-gov"
    r = DomainRouter()
    assert r.it_ops_domain() == "it-ops"
    assert r.data_gov_domain() == "data-gov"


def test_targets_use_platform_it_ops_or_data_gov():
    for rel in TARGETS:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert (
            "it_ops_domain()" in text or "data_gov_domain()" in text
        ), rel
        assert 'domain_id: str = "it-ops"' not in text, rel
        assert 'domain_id: str = "data-gov"' not in text, rel


def test_production_it_ops_data_gov_signature_defaults_empty():
    rx = re.compile(r'domain_id\s*:\s*str\s*=\s*["\'](it-ops|data-gov)["\']')
    hits = []
    for root in ((_repo_root() / "aiPlat-core/core"), (_repo_root() / "aiPlat-platform")):
        for p in root.rglob("*.py"):
            if "/tests/" in str(p).replace("\\", "/"):
                continue
            for i, ln in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if rx.search(ln):
                    hits.append(f"{p}:{i}")
    assert hits == [], hits
