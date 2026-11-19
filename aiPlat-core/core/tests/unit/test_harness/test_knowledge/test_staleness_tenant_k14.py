"""N09 K14 — StalenessMonitor / diagnostics use per-tenant KB paths."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")



def test_kb_sqlite_path_for_tenant(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    from core.harness.knowledge.staleness_monitor import (
        kb_sqlite_path_for_tenant,
        StalenessMonitor,
    )

    p = kb_sqlite_path_for_tenant("n09-t14")
    assert p == tmp_path / "kb" / "tenants" / "n09-t14" / "kb.sqlite3"

    m = StalenessMonitor(tenant_id="n09-t14")
    assert m._tenant_id == "n09-t14"
    assert m._kb_db_path == p


def test_diagnostics_source_wires_tenant():
    text = (_repo_root() / "aiPlat-core/core/api/routers/diagnostics.py").read_text(encoding="utf-8")
    assert "StalenessMonitor(tenant_id=tid)" in text
    assert "kb_sqlite_path_for_tenant(tid)" in text
    assert "auto_ontology_pipeline_for_doc(doc_id, row[0], cid, tenant_id=tid)" in text
    rebuild = text[text.find("async def trigger_drift_rebuild") : text.find("_drift_cache")]
    assert "tenants/default/" not in rebuild


def test_staleness_source_uses_self_tenant():
    text = (_repo_root() / "aiPlat-core/core/harness/knowledge/staleness_monitor.py").read_text(
        encoding="utf-8"
    )
    assert "def kb_sqlite_path_for_tenant" in text
    assert "tenant_id=self._tenant_id" in text
    assert 'Path(get_aiplat_home()) / "kb" / "tenants" / "default"' not in text
