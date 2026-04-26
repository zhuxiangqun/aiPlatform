def test_tag_assertions_text_and_limits():
    from core.harness.evaluation.tag_assertions import evaluate_tag_assertions, evaluate_tag_assertions_with_stats

    evidence = {
        "by_tag": {
            "login": {
                "snapshot": {"text": "欢迎 登录"},
                "console_messages": [{"type": "error", "text": "x"}],
                "network_requests": [{"status": 500, "url": "u"}],
                "duration_ms": 12000,
            }
        }
    }
    expectations = {"login": {"text_contains": ["登录"], "max_console_errors": 0, "max_network_5xx": 0, "max_duration_ms": 8000}}
    ok, failures = evaluate_tag_assertions(evidence, expectations)
    assert ok is False
    assert len(failures) >= 2

    ok2, failures2, stats = evaluate_tag_assertions_with_stats(evidence, expectations)
    assert ok2 is False
    assert isinstance(stats, dict)
    assert stats["login"]["console_errors"] == 1
    assert stats["login"]["network_5xx"] == 1
