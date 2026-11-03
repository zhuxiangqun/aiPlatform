"""COMPLIANCE_PII_V0 — heuristic leak detection (≠ privacy certification)."""
from __future__ import annotations

import json
from pathlib import Path

from app.scoring.compliance_pii import evaluate_compliance_cases, scan_pii, score_pii_clean
from app.scoring.composite import metric_role

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "docs/a3/compliance_pii_tasks.v0.json"
SCHEMA = ROOT / "contracts/schemas/eval_compliance_pii.schema.json"


def test_scan_email_and_clean():
    assert scan_pii("hello world")["leak"] is False
    assert score_pii_clean(text="hello") == 1.0
    hit = scan_pii("mail me at bob@example.org please")
    assert hit["leak"] is True
    assert "email" in hit["kinds"]
    assert score_pii_clean(text="bob@example.org") == 0.0


def test_scan_ssn_and_cn_id():
    assert "us_ssn" in scan_pii("ssn 123-45-6789")["kinds"]
    assert "cn_id" in scan_pii("id 110101199001011234")["kinds"]


def test_fixture_tasks_pass_rate():
    payload = json.loads(TASKS.read_text(encoding="utf-8"))
    report = evaluate_compliance_cases(payload["cases"])
    assert report["accuracy_claim"] is False
    assert report["certified"] is False
    assert report["pass_rate"] >= 0.95


def test_schema_required_keys_present():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["properties"]["accuracy_claim"]["const"] is False
    assert "pass_rate" in (schema.get("required") or [])


def test_pii_metrics_report_only_in_composite():
    assert metric_role("pii_clean") == "report_only"
    assert metric_role("pii_leak") == "report_only"
