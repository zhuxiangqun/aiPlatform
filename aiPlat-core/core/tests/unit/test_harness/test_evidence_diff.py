def test_compute_evidence_diff_basic():
    from core.harness.evaluation.evidence_diff import compute_evidence_diff, evaluate_regression

    base = {
        "evidence_pack_id": "e1",
        "snapshot": {"title": "A"},
        "console_messages": [{"type": "error", "text": "x"}],
        "network_requests": [{"method": "GET", "status": 200, "url": "http://a"}],
        "by_tag": {"login": {"screenshot": {"data": "a"}}},
    }
    cur = {
        "evidence_pack_id": "e2",
        "snapshot": {"title": "B"},
        "console_messages": [{"type": "error", "text": "x"}, {"type": "error", "text": "y"}],
        "network_requests": [{"method": "GET", "status": 200, "url": "http://a"}, {"method": "POST", "status": 500, "url": "http://b"}],
        "by_tag": {"login": {"screenshot": {"data": "b"}}},
    }
    diff = compute_evidence_diff(base, cur)
    assert diff["base_evidence_pack_id"] == "e1"
    assert diff["new_evidence_pack_id"] == "e2"
    assert diff["diff"]["title"]["base"] == "A"
    assert diff["diff"]["title"]["new"] == "B"
    assert any("y" in x for x in diff["diff"]["console_new"])
    assert any("http://b" in x for x in diff["diff"]["network_new"])
    assert diff["metrics"]["new_console_errors"] >= 1
    assert diff["metrics"]["new_network_5xx"] >= 1
    assert diff["metrics"]["changed_screenshot_tags"] >= 1
    is_reg, reasons = evaluate_regression(diff, {"max_new_console_errors": 0, "max_new_network_5xx": 0, "max_new_network_4xx": 99}, executed_tags=["login"])
    assert is_reg is True
    assert any("console error" in r or "5xx" in r for r in reasons)
