"""P0-3b: authz/IDOR/SSRF smoke + pilot exit criteria."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "builder" / "artifact_authz_smoke.py"


def _load():
    name = "artifact_authz_smoke_under_test"
    spec = importlib.util.spec_from_file_location(name, MOD)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def authz():
    return _load()


class ScriptedTransport:
    def __init__(self, mapping: Dict[str, int]):
        # key: "METHOD path" → status
        self.mapping = mapping

    def __call__(
        self,
        method: str,
        url: str,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, str]:
        from urllib.parse import urlparse

        path = urlparse(url).path
        key = f"{method.upper()} {path}"
        if key not in self.mapping:
            return 500, f"unexpected {key}"
        return self.mapping[key], "ok"


def _passing_map_crud():
    return {
        "GET /api/items": 401,
        "GET /api/items/1": 403,
        "POST /api/fetch": 422,
        "GET /health": 200,
    }


def test_run_authz_smoke_pass(authz):
    r = authz.run_authz_smoke(
        base_url="http://example",
        app_type="crud",
        sample_id="s1",
        transport=ScriptedTransport(_passing_map_crud()),
    )
    assert r["status"] == "pass"
    assert r["negatives_blocked"] is True
    assert r["app_type"] == "crud"


def test_run_authz_smoke_fail_when_negative_allowed(authz):
    m = _passing_map_crud()
    m["GET /api/items"] = 200  # authz bypass
    r = authz.run_authz_smoke(
        base_url="http://example",
        app_type="crud",
        sample_id="s-bad",
        transport=ScriptedTransport(m),
    )
    assert r["status"] == "fail"


def test_classify_crud(authz, tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "def create(): pass\ndef update(): pass\ndef delete(): pass\n# CRUD repository\n",
        encoding="utf-8",
    )
    assert authz.classify_app_type(tmp_path) == "crud"


def test_pilot_exit_requires_two_types_and_owner(authz, tmp_path: Path, monkeypatch):
    path = tmp_path / "pilot.json"
    monkeypatch.setenv("AIPLAT_AUTHZ_PILOT_PATH", str(path))

    state = authz.PilotState(started_at=date.today().isoformat())
    # 3 crud pass
    for i in range(3):
        state.samples.append(
            authz.PilotSample(
                sample_id=f"c{i}",
                app_type="crud",
                authz_status="pass",
                negatives_blocked=True,
            )
        )
    # only 2 report → not ready
    for i in range(2):
        state.samples.append(
            authz.PilotSample(
                sample_id=f"r{i}",
                app_type="report",
                authz_status="pass",
                negatives_blocked=True,
            )
        )
    ev = authz.evaluate_pilot_exit(state)
    assert ev["status"] == "in_progress"
    assert ev["types_ready"] is False

    state.samples.append(
        authz.PilotSample(
            sample_id="r2",
            app_type="report",
            authz_status="pass",
            negatives_blocked=True,
        )
    )
    ev2 = authz.evaluate_pilot_exit(state)
    assert ev2["types_ready"] is True
    assert ev2["status"] == "in_progress"  # no owner yet

    state.owner_approval = "2026-11-09 Security Owner: exit pilot"
    ev3 = authz.evaluate_pilot_exit(state)
    assert ev3["status"] == "passed"
    assert ev3["require_authz_on_publish"] is True


def test_pilot_timeout_blocked(authz):
    started = (date.today() - timedelta(days=61)).isoformat()
    state = authz.PilotState(started_at=started, samples=[])
    ev = authz.evaluate_pilot_exit(state)
    assert ev["status"] == "blocked"
    assert ev["timed_out"] is True


def test_record_and_approve(authz, tmp_path: Path, monkeypatch):
    path = tmp_path / "pilot.json"
    monkeypatch.setenv("AIPLAT_AUTHZ_PILOT_PATH", str(path))
    smoke = authz.run_authz_smoke(
        base_url="http://example",
        app_type="report",
        sample_id="rep-1",
        transport=ScriptedTransport(
            {
                "GET /api/reports": 401,
                "GET /api/reports/org-secret": 404,
                "POST /api/reports/import": 400,
                "GET /health": 200,
            }
        ),
    )
    st = authz.record_pilot_sample(smoke, path=path)
    assert any(s.sample_id == "rep-1" for s in st.samples)
    assert path.is_file()
