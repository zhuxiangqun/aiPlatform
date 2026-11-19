"""N09 K37 — ontology branch YAML path tenant prefix."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")



def test_branch_yaml_path_tenant_prefix(tmp_path, monkeypatch):
    import core.harness.ontology_engine.ontology_branch as ob

    monkeypatch.setattr(ob, "HOME", tmp_path)
    (tmp_path / "ontologies").mkdir()
    main_default = ob._branch_yaml_path("demo", "main", "default")
    br_default = ob._branch_yaml_path("demo", "experiment", "default")
    main_t = ob._branch_yaml_path("demo", "main", "n09-t37")
    br_t = ob._branch_yaml_path("demo", "experiment", "n09-t37")
    assert main_default.name == "demo.yaml"
    assert br_default.name == "demo__experiment.yaml"
    assert main_t.name == "n09-t37:demo.yaml"
    assert br_t.name == "n09-t37:demo__experiment.yaml"


def test_resolve_yaml_source_falls_back_to_shared(tmp_path, monkeypatch):
    import core.harness.ontology_engine.ontology_branch as ob

    monkeypatch.setattr(ob, "HOME", tmp_path)
    ont = tmp_path / "ontologies"
    ont.mkdir()
    shared = ont / "demo.yaml"
    shared.write_text("domain_id: demo\n", encoding="utf-8")
    resolved = ob._resolve_branch_yaml_source("demo", "main", "n09-t37")
    assert resolved == shared
    # once tenant copy exists, prefer it
    tenant_main = ont / "n09-t37:demo.yaml"
    tenant_main.write_text("domain_id: demo\ntenant: n09-t37\n", encoding="utf-8")
    resolved2 = ob._resolve_branch_yaml_source("demo", "main", "n09-t37")
    assert resolved2 == tenant_main


def test_fork_copies_yaml_to_tenant_path(tmp_path, monkeypatch):
    import core.harness.ontology_engine.ontology_branch as ob

    monkeypatch.setattr(ob, "HOME", tmp_path)
    monkeypatch.setattr(ob, "GRAPH_DIR", tmp_path / "graph")
    monkeypatch.setattr(ob, "BRANCH_REGISTRY_PATH", tmp_path / "branches.json")
    monkeypatch.setattr(ob, "_resolve_branch_tenant", lambda tenant_id="": tenant_id or "default")
    (tmp_path / "graph").mkdir()
    (tmp_path / "ontologies").mkdir()
    # main graph db required by fork
    (tmp_path / "graph" / "n09-t37:demo.db").write_bytes(b"")
    (tmp_path / "ontologies" / "demo.yaml").write_text("name: demo\n", encoding="utf-8")

    # skip snapshot GraphIndex noise
    class _FakeGI:
        def __init__(self, *a, **k):
            pass

        def snapshot(self, label=""):
            return {"id": 1, "label": label}

        def close(self):
            return None

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex",
        _FakeGI,
    )

    bm = ob.OntologyBranchManager()
    info = bm.fork("demo", "exp", description="k37", from_snapshot=False, tenant_id="n09-t37")
    assert info.branch_name == "exp"
    out = tmp_path / "ontologies" / "n09-t37:demo__exp.yaml"
    assert out.exists()
    assert "demo" in out.read_text(encoding="utf-8")


def test_source_wires_branch_yaml_helpers():
    text = (_repo_root() / "aiPlat-core/core/harness/ontology_engine/ontology_branch.py").read_text(
        encoding="utf-8"
    )
    assert "def _branch_yaml_path(" in text
    assert "def _resolve_branch_yaml_source(" in text
    assert "_branch_yaml_path(domain_id, branch_name, tid)" in text
