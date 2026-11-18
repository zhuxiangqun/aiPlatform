"""N09 K33 — custom_handlers / seed scripts GraphIndex tenant."""
from __future__ import annotations

from pathlib import Path
import sys

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")




def _assert_no_bare_loads(rel: str) -> None:
    text = (_repo_root() / rel).read_text(encoding="utf-8")
    bare = [
        ln
        for ln in text.splitlines()
        if "GraphIndex.load(" in ln and "tenant_id" not in ln
    ]
    assert bare == [], bare


def test_custom_handlers_source_wires_tenant():
    text = (_repo_root() / "custom_handlers/service_handlers.py").read_text(encoding="utf-8")
    assert "def _handler_graph_tenant(" in text
    assert (
        'GraphIndex.load("service-domain", tenant_id=_handler_graph_tenant(params))'
        in text
    )
    assert text.count("GraphIndex.load(") == 5
    _assert_no_bare_loads("custom_handlers/service_handlers.py")


def test_quick_seed_source_wires_tenant():
    text = (_repo_root() / "scripts/quick_seed.py").read_text(encoding="utf-8")
    assert "def _seed_tenant(" in text
    assert 'parser.add_argument("--tenant"' in text
    assert "GraphIndex.load(domain_id, tenant_id=_seed_tenant(tenant_id))" in text
    _assert_no_bare_loads("scripts/quick_seed.py")


def test_handler_graph_tenant_prefers_params(monkeypatch):
    sys.path.insert(0, str(_repo_root()))
    import custom_handlers.service_handlers as sh

    monkeypatch.setattr(
        "core.api.core_facade.resolve_graph_tenant",
        lambda params=None: "ctx-default",
    )
    assert sh._handler_graph_tenant({"tenant_id": "n09-t33"}) == "n09-t33"
    assert sh._handler_graph_tenant({}) == "ctx-default"


def test_seed_tenant_prefers_explicit(monkeypatch):
    import importlib.util

    path = (_repo_root() / "scripts/quick_seed.py")
    spec = importlib.util.spec_from_file_location("quick_seed_k33", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    monkeypatch.setattr(
        "core.api.core_facade.resolve_graph_tenant",
        lambda params=None: "ctx-default",
    )
    assert mod._seed_tenant("n09-t33") == "n09-t33"
    assert mod._seed_tenant("") == "ctx-default"
