def test_auto_eval_prompt_includes_browser_evidence():
    from core.harness.evaluation.auto import build_auto_eval_prompt

    msgs = build_auto_eval_prompt(
        run={"run_id": "r1", "status": "completed", "trace_id": "t1"},
        events=[{"seq": 1, "type": "tool_start", "payload": {"tool": "x"}}],
        extra={"k": "v"},
        browser_evidence={"url": "http://example.com", "snapshot": {"title": "x"}},
    )
    assert isinstance(msgs, list)
    text = msgs[-1]["content"]
    assert "Browser evidence" in text
    assert "example.com" in text

