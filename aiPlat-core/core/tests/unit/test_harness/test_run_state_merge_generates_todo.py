def test_run_state_merge_generates_todo_and_keeps_completed():
    from core.harness.restatement.run_state import merge_from_evaluation, normalize_run_state, _stable_id

    current = normalize_run_state(
        {
            "run_id": "r1",
            "todo": [
                {"id": _stable_id("issue", "旧问题"), "title": "旧问题", "status": "completed", "priority": "P0"},
            ],
            "locked": False,
        },
        run_id="r1",
    )
    report = {
        "pass": False,
        "issues": [
            {"severity": "P0", "title": "旧问题", "suggested_fix": "x"},
            {"severity": "P1", "title": "新问题", "suggested_fix": "y"},
        ],
        "next_actions_for_generator": ["补齐 e2e 测试"],
    }
    merged = merge_from_evaluation(current, evaluation_report=report, source="evaluator")
    todo = merged.get("todo")
    assert isinstance(todo, list)
    # should keep completed item (same title -> stable id)
    titles = [t.get("title") for t in todo if isinstance(t, dict)]
    assert "旧问题" in titles
    assert "新问题" in titles
    assert "补齐 e2e 测试" in titles
