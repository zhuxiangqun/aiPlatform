"""N09 K34 — GraphIndex constructor / branch DB path tenant."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")



TARGETS = [
    "aiPlat-core/core/harness/ontology_engine/ontology_branch.py",
    "aiPlat-core/core/harness/knowledge/okf_exporter.py",
    "aiPlat-core/core/harness/ontology_engine/graph_importer.py",
    "aiPlat-core/core/harness/knowledge/recon_subgraph.py",
    "aiPlat-core/core/harness/syscalls/retrieval.py",
    "aiPlat-core/core/harness/infrastructure/gates/ontology_validator.py",
    "aiPlat-core/core/harness/knowledge/wiki_indexer.py",
    "aiPlat-core/core/harness/evaluation/hallucination_tracker.py",
    "aiPlat-core/core/harness/knowledge/doc_quality_monitor.py",
]


def _bare_ctors(rel: str) -> list[str]:
    """找出未带 tenant_id 的 GraphIndex(...) 构造（支持跨行参数）。"""
    text = (_repo_root() / rel).read_text(encoding="utf-8")
    out = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if "GraphIndex(" not in ln or "GraphIndex.load" in ln:
            i += 1
            continue
        if ln.strip().startswith("#"):
            i += 1
            continue
        if any(x in ln for x in ("def ", "class ", "Type[", "Optional[", "ShardedGraphIndex")):
            i += 1
            continue
        # 合并到匹配右括号（多行 ctor），再判断是否含 tenant_id
        block = ln
        j = i
        while block.count("(") > block.count(")") and j + 1 < len(lines):
            j += 1
            block += "\n" + lines[j]
        if "tenant_id" not in block:
            out.append(ln.strip())
        i = j + 1
    return out


def test_k34_targets_no_bare_graphindex_ctors():
    for rel in TARGETS:
        assert _bare_ctors(rel) == [], (rel, _bare_ctors(rel))


def test_branch_db_path_tenant_prefix():
    from core.harness.ontology_engine.ontology_branch import _branch_db_path

    main_default = _branch_db_path("demo-domain", "main", "default")
    main_t = _branch_db_path("demo-domain", "main", "n09-t34")
    br_t = _branch_db_path("demo-domain", "experiment", "n09-t34")
    assert main_default.name == "demo-domain.db"
    assert main_t.name == "n09-t34:demo-domain.db"
    assert br_t.name == "n09-t34:demo-domain__experiment.db"


def test_branch_resolve_prefers_explicit(monkeypatch):
    from core.harness.ontology_engine import ontology_branch as ob

    monkeypatch.setattr(
        "core.harness.knowledge.context_bus._resolve_graph_tenant",
        lambda params=None: "ctx-default",
    )
    assert ob._resolve_branch_tenant("n09-t34") == "n09-t34"
    assert ob._resolve_branch_tenant("") == "ctx-default"


def test_fde_api_branch_okf_pass_tenant():
    text = (_repo_root() / "aiPlat-platform/apps/fde/api/fde.py").read_text(encoding="utf-8")
    assert "tenant_id=fde_graph_tenant()" in text
    assert "exporter.export(" in text
    # fork / diff / merge / delete / export all pass tenant
    assert text.count("tenant_id=fde_graph_tenant()") >= 5
