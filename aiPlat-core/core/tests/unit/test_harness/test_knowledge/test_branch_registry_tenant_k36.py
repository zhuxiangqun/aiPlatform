"""N09 K36 — ontology branch registry key tenant isolation."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")



def test_branch_key_tenant_formats():
    from core.harness.ontology_engine.ontology_branch import _branch_key, _legacy_branch_key

    assert _branch_key("demo", "main", "default") == "demo::main"
    assert _legacy_branch_key("demo", "main") == "demo::main"
    assert _branch_key("demo", "experiment", "n09-t36") == "n09-t36::demo::experiment"


def test_find_branch_entry_legacy_default():
    from core.harness.ontology_engine.ontology_branch import _find_branch_entry

    branches = {"demo::exp": {"domain_id": "demo", "branch_name": "exp", "created_at": 1.0}}
    key, data = _find_branch_entry(branches, "demo", "exp", "default")
    assert key == "demo::exp"
    assert data is not None
    key2, data2 = _find_branch_entry(branches, "demo", "exp", "n09-t36")
    assert data2 is None
    assert key2 == "n09-t36::demo::exp"


def test_list_branches_isolates_tenants(tmp_path, monkeypatch):
    import core.harness.ontology_engine.ontology_branch as ob

    registry_path = tmp_path / "branches.json"
    monkeypatch.setattr(ob, "BRANCH_REGISTRY_PATH", registry_path)
    monkeypatch.setattr(ob, "_resolve_branch_tenant", lambda tenant_id="": (tenant_id or "default"))

    bm = ob.OntologyBranchManager()
    # write via registry directly to avoid needing graph DB for fork
    ob._save_registry(
        {
            "branches": {
                "demo::a": {
                    "domain_id": "demo",
                    "branch_name": "a",
                    "created_at": 1.0,
                    "description": "legacy-default",
                },
                "n09-t36::demo::b": {
                    "domain_id": "demo",
                    "branch_name": "b",
                    "created_at": 2.0,
                    "description": "tenant-b",
                },
            }
        }
    )
    default_names = {x.branch_name for x in bm.list_branches("demo", tenant_id="default")}
    t36_names = {x.branch_name for x in bm.list_branches("demo", tenant_id="n09-t36")}
    assert "a" in default_names
    assert "b" not in default_names
    assert "b" in t36_names
    assert "a" not in t36_names
    assert "main" in default_names and "main" in t36_names


def test_fde_list_branches_passes_tenant():
    text = (_repo_root() / "aiPlat-platform/apps/fde/api/fde.py").read_text(encoding="utf-8")
    assert "list_branches(domain_id, tenant_id=fde_graph_tenant())" in text
