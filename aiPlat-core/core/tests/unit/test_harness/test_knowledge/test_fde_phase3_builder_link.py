"""Phase 3: delivery session ↔ Builder link + eval gate (no parallel build)."""

from __future__ import annotations

from core.apps.fde.service.delivery_pipeline_session import (
    approve_delivery_session,
    attach_builder_observation,
    evaluate_delivery_session,
    get_delivery_session,
    link_builder_project,
    start_delivery_session,
)


def test_link_builder_updates_honesty(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))

    s = start_delivery_session(customer_name="p3", builder_project_id="")
    assert s["honesty"]["mode"] == "template_session"
    assert not s.get("builder_project_id")

    linked = link_builder_project(s["session_id"], "prj_demo_1")
    assert linked["builder_project_id"] == "prj_demo_1"
    assert linked["honesty"]["mode"] == "builder_linked"


def test_builder_eval_blocks_then_passes(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))

    s = start_delivery_session(
        customer_name="p3-eval",
        builder_project_id="prj_eval",
    )
    assert s["honesty"]["mode"] == "builder_linked"
    sid = s["session_id"]

    # Drive HITL to final without observation → eval_blocked
    cur = s
    guard = 0
    while cur.get("phase") == "paused" and guard < 10:
        cur = approve_delivery_session(sid, feedback=f"ok-{guard}")
        guard += 1
    assert cur["phase"] == "eval_blocked"
    assert cur["eval_gate"]["passed"] is False
    assert "builder_linked_but_not_observed" in cur["eval_gate"]["reasons"]

    # Observe factory product, then retry
    attach_builder_observation(
        sid,
        {
            "project_id": "prj_eval",
            "phase": "done",
            "artifacts": [{"id": "app", "url": "/apps/prj_eval", "kind": "deploy"}],
        },
    )
    gate = evaluate_delivery_session(sid)
    assert gate["passed"] is True
    done = approve_delivery_session(sid, feedback="retry-eval")
    assert done["phase"] == "done"
    assert done["progress_pct"] == 100
    links = get_delivery_session(sid)["artifact_links"]
    assert any(x.get("url") == "/apps/prj_eval" for x in links)


def test_template_only_still_completes_without_builder(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    s = start_delivery_session(customer_name="p3-tpl")
    sid = s["session_id"]
    cur = s
    for i in range(8):
        if cur.get("phase") != "paused":
            break
        cur = approve_delivery_session(sid, feedback=f"a{i}")
    assert cur["phase"] == "done"
