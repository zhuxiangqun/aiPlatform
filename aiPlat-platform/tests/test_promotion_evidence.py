"""Promotion gate evidence wiring: last_test_report → get_promotion_status."""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "aiPlat-platform"))


def _load_hop_metrics():
    path = ROOT / "aiPlat-platform" / "builder" / "hop_metrics.py"
    spec = importlib.util.spec_from_file_location("hop_metrics_promo_ev", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_get_promotion_status_uses_last_test_report(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    hm = _load_hop_metrics()
    pid = "prj_promo_ev"
    for _ in range(20):
        hm.record_hop(pid, skill="s1", agent="a1", ok=True)

    projects_file = tmp_path / "projects.json"
    projects_file.write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "project_id": pid,
                        "name": "promo-ev",
                        "last_test_report": {
                            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "test_passed": True,
                            "test_report": {
                                "meta": {"pass_rate": 1.0},
                                "cases": [{"name": "t1"}],
                            },
                            "e2e_smoke": {"passed": True},
                        },
                    }
                ],
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    from builder.builder_project_service import BuilderProjectService

    svc = BuilderProjectService(team_service=None)
    blocked = svc.get_promotion_status("missing_project_no_hops")
    assert blocked.get("ok") is False

    out = svc.get_promotion_status(pid)
    assert out.get("ok") is True, out
    assert out.get("evidence", {}).get("real_tests_green") is True
    assert out.get("evidence", {}).get("physical_evidence") is True
    assert int(out.get("hops_raw_n") or 0) >= 20
