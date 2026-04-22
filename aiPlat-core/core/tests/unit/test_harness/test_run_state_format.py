def test_format_run_state_for_prompt_has_markers():
    from core.harness.restatement.run_state import format_run_state_for_prompt

    text = format_run_state_for_prompt(
        {
            "task": "build app",
            "next_step": "do X",
            "open_issues": [{"severity": "P0", "title": "bug"}],
            "todo": [{"id": "t2", "title": "fix", "status": "pending", "priority": "P0"}],
            "locked": False,
        }
    )
    assert "RUN STATE" in text
    assert "next_step" in text
    assert "bug" in text
    assert "current_todo_id" in text
    assert "TODO_DONE:" in text
