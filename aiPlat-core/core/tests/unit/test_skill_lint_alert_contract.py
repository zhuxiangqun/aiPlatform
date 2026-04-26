from core.harness.maintenance.skill_lint_scan import _alert_event, _severity_for_scan


def test_severity_for_scan():
    assert _severity_for_scan({"blocked": 1, "errors": 0}) == "error"
    assert _severity_for_scan({"blocked": 0, "errors": 2}) == "warning"
    assert _severity_for_scan({"blocked": 0, "errors": 0}) is None


def test_alert_event_contract_minimal():
    ev = _alert_event(
        payload={"scopes": ["workspace"], "tenant_id": "ops", "actor_id": "system"},
        job_id="cron-skill-lint-scan",
        job_run_id="jobrun-1",
        trace_id="trace-1",
        cron="0 * * * *",
        finished_at=123.0,
        totals={"skills": 10, "blocked": 1, "errors": 2, "warnings": 3, "high_risk": 1},
        top={"errors": [{"code": "missing_markdown", "count": 2}], "warnings": []},
        blocked_skills=[{"scope": "workspace", "skill_id": "s1", "name": "s1", "risk_level": "high", "error_count": 1, "warning_count": 0}],
        severity="error",
    )
    assert ev["event_type"] == "skill_lint_alert"
    assert ev["severity"] == "error"
    assert "metrics" in ev and "top" in ev and "blocked_skills" in ev
    assert "markdown" in ev and "Skill Lint 告警" in ev["markdown"]

