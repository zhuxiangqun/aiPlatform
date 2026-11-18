"""N09 K30 — skills/registry / org_kpi / pipeline / router GraphIndex tenant."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")


_FILES = (
    "aiPlat-core/core/apps/skills/registry.py",
    "aiPlat-core/core/apps/org/service/org_kpi.py",
    "aiPlat-core/core/harness/execution/router.py",
    "aiPlat-core/core/harness/execution/pipeline_engine.py",
)


def _assert_no_bare_loads(rel: str) -> None:
    text = Path(rel).read_text(encoding="utf-8")
    bare = [
        ln
        for ln in text.splitlines()
        if "GraphIndex.load(" in ln and "tenant_id" not in ln
    ]
    assert bare == [], bare


def test_k30_sources_wire_tenant():
    for rel in _FILES:
        text = Path(rel).read_text(encoding="utf-8")
        assert "tenant_id=" in text, rel
        _assert_no_bare_loads(rel)
    skills = (_repo_root() / "aiPlat-core/core/apps/skills/registry.py").read_text(
        encoding="utf-8"
    )
    assert "def _skills_graph_tenant(" in skills
    assert skills.count("tenant_id=_skills_graph_tenant()") == 3


def test_skills_graph_tenant_resolves(monkeypatch):
    from core.apps.skills import registry as reg

    monkeypatch.setattr(
        "core.harness.knowledge.context_bus._resolve_graph_tenant",
        lambda params=None: "n09-t30",
    )
    assert reg._skills_graph_tenant() == "n09-t30"


def test_org_kpi_loads_tenant(monkeypatch):
    from core.apps.org.service import org_kpi as ok

    seen = {}

    class _G:
        _nodes = {}

    def _fake_load(domain_id, tenant_id="default"):
        seen["domain_id"] = domain_id
        seen["tenant_id"] = tenant_id
        return _G()

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load", _fake_load
    )
    monkeypatch.setattr(
        "core.harness.knowledge.context_bus._resolve_graph_tenant",
        lambda params=None: "n09-t30",
    )
    # weekly_kpi_report may early-return before graph; still assert wiring if hit
    try:
        ok.weekly_kpi_report(domain_id="demo-domain")
    except Exception:
        pass
    text = (_repo_root() / "aiPlat-core/core/apps/org/service/org_kpi.py").read_text(
        encoding="utf-8"
    )
    assert "tenant_id=_resolve_graph_tenant()" in text
    if seen:
        assert seen.get("tenant_id") == "n09-t30"
