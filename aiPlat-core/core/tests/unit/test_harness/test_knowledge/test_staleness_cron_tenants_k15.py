"""N09 K15 — cron/health enumerate per-tenant KB paths."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")



def test_list_kb_tenant_ids_discovers_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    from core.harness.knowledge.staleness_monitor import list_kb_tenant_ids

    t_a = tmp_path / "kb" / "tenants" / "n09-t15a"
    t_b = tmp_path / "kb" / "tenants" / "n09-t15b"
    t_a.mkdir(parents=True)
    t_b.mkdir(parents=True)
    (t_a / "kb.sqlite3").write_bytes(b"")
    (t_b / "kb.sqlite3").write_bytes(b"")
    # empty dir without db must be ignored
    (tmp_path / "kb" / "tenants" / "empty").mkdir(parents=True)

    ids = list_kb_tenant_ids()
    assert "default" in ids
    assert "n09-t15a" in ids
    assert "n09-t15b" in ids
    assert "empty" not in ids


def test_aggregate_stale_summary_uses_per_tenant_monitors(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    from core.harness.knowledge import staleness_monitor as sm

    monkeypatch.setattr(sm, "list_kb_tenant_ids", lambda: ["a", "b"])

    class _FakeMon:
        def __init__(self, *, tenant_id="default"):
            self._tenant_id = tenant_id

        def get_stale_summary(self):
            if self._tenant_id == "a":
                return {
                    "total_scanned": 10,
                    "total_stale": 4,
                    "drift_ratio": 0.4,
                    "collections": {"c": 4},
                }
            return {
                "total_scanned": 5,
                "total_stale": 0,
                "drift_ratio": 0.0,
                "collections": {},
            }

    monkeypatch.setattr(sm, "StalenessMonitor", _FakeMon)
    out = sm.aggregate_stale_summary()
    assert out["total_scanned"] == 15
    assert out["total_stale"] == 4
    assert out["drift_ratio"] == round(4 / 15, 3)
    assert out["tenant_ids"] == ["a", "b"]
    assert out["tenants"]["a"]["total_stale"] == 4


def test_cron_and_health_source_wire_aggregate():
    server = (_repo_root() / "aiPlat-core/core/server.py").read_text(encoding="utf-8")
    assert "aggregate_stale_summary" in server
    assert "auto_rebuild_stale_tenants" in server
    # no bare StalenessMonitor() in the governance cron block
    cron = server[server.find("Knowledge drift monitoring") : server.find("ConfigDriftDetector")]
    assert "StalenessMonitor()" not in cron

    health = (_repo_root() / "aiPlat-core/core/harness/evaluation/system_health.py").read_text(
        encoding="utf-8"
    )
    assert "aggregate_stale_summary()" in health
    assert "StalenessMonitor().get_stale_summary()" not in health
