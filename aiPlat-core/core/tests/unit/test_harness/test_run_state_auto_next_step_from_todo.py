def test_auto_next_step_from_todo_picks_highest_priority():
    from core.harness.restatement.run_state import auto_next_step_from_todo, normalize_run_state

    rs = normalize_run_state(
        {
            "run_id": "r1",
            "next_step": "",
            "todo": [
                {"id": "t1", "title": "low", "status": "pending", "priority": "P2"},
                {"id": "t2", "title": "high", "status": "pending", "priority": "P0"},
            ],
        },
        run_id="r1",
    )
    rs2 = auto_next_step_from_todo(rs)
    assert "high" in rs2.get("next_step", "")

