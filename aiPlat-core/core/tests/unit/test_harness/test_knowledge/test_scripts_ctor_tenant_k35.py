"""N09 K35 — scripts GraphIndex constructor tenant."""
from __future__ import annotations

import importlib.util
from pathlib import Path

TARGETS = [
    "scripts/benchmark_ontology.py",
    "scripts/benchmark_traversal.py",
    "scripts/seed_lock_service_orders.py",
    "scripts/new_domain_scaffold.py",
]


def _bare_ctors(rel: str) -> list[str]:
    out = []
    for ln in Path(rel).read_text(encoding="utf-8").splitlines():
        if "GraphIndex(" not in ln or "GraphIndex.load" in ln:
            continue
        if ln.strip().startswith("#"):
            continue
        if "tenant_id" in ln:
            continue
        if any(x in ln for x in ("def ", "class ", "Type[", "Optional[")):
            continue
        out.append(ln.strip())
    return out


def test_scripts_no_bare_graphindex_ctors():
    for rel in TARGETS:
        assert _bare_ctors(rel) == [], (rel, _bare_ctors(rel))


def test_scripts_cli_tenant_flags():
    for rel in (
        "scripts/benchmark_ontology.py",
        "scripts/benchmark_traversal.py",
        "scripts/seed_lock_service_orders.py",
    ):
        text = Path(rel).read_text(encoding="utf-8")
        assert 'add_argument("--tenant"' in text
        assert "def _script_graph_tenant(" in text


def test_script_graph_tenant_prefers_explicit(monkeypatch):
    path = Path("scripts/seed_lock_service_orders.py")
    spec = importlib.util.spec_from_file_location("seed_lock_k35", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    monkeypatch.setattr(
        "core.api.core_facade.resolve_graph_tenant",
        lambda params=None: "ctx-default",
    )
    assert mod._script_graph_tenant("n09-t35") == "n09-t35"
    assert mod._script_graph_tenant("") == "ctx-default"


def test_scaffold_template_wires_tenant():
    text = Path("scripts/new_domain_scaffold.py").read_text(encoding="utf-8")
    assert 'GraphIndex(DOMAIN, tenant_id="default")' in text
