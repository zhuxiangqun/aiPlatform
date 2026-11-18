"""N09 K35 — scripts GraphIndex constructor tenant."""
from __future__ import annotations

import importlib.util
from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")


TARGETS = [
    "scripts/benchmark_ontology.py",
    "scripts/benchmark_traversal.py",
    "scripts/seed_lock_service_orders.py",
    "scripts/new_domain_scaffold.py",
]


def _bare_ctors(rel: str) -> list[str]:
    out = []
    for ln in (_repo_root() / rel).read_text(encoding="utf-8").splitlines():
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
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert 'add_argument("--tenant"' in text
        assert "def _script_graph_tenant(" in text


def test_script_graph_tenant_prefers_explicit(monkeypatch):
    path = (_repo_root() / "scripts/seed_lock_service_orders.py")
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
    text = (_repo_root() / "scripts/new_domain_scaffold.py").read_text(encoding="utf-8")
    assert 'GraphIndex(DOMAIN, tenant_id="default")' in text
