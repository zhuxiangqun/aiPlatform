"""A0: output_style resolve / whitelist / inject. A3a: telemetry record/query."""
from __future__ import annotations

from core.harness.utils.output_style import (
    STYLE_ADHD,
    STYLE_DEFAULT,
    STYLE_VERSION,
    WHITELIST_OVERRIDE_KEYS,
    build_style_overlay,
    estimate_reply_tokens,
    infer_followups,
    inject_output_style,
    query_output_style_events,
    record_output_style_event,
    resolve_output_style,
    skill_body_hash,
    whitelist_overrides,
)


def test_resolve_output_style_default():
    assert resolve_output_style(None) == STYLE_DEFAULT
    assert resolve_output_style({"output_style": "adhd"}) == STYLE_ADHD
    assert resolve_output_style({"output_style": "off"}) == STYLE_DEFAULT
    assert resolve_output_style({"metadata": {"output_style": "adhd"}}) == STYLE_ADHD


def test_whitelist_overrides_filters():
    ov = whitelist_overrides(
        {"output_style_overrides": {"list_cap": 3, "evil": 1, "locale": "en"}}
    )
    assert ov == {"list_cap": 3, "locale": "en"}
    assert "evil" not in ov
    assert WHITELIST_OVERRIDE_KEYS >= set(ov)


def test_overlay_empty_for_default():
    assert build_style_overlay(STYLE_DEFAULT) == ""
    assert "list_cap=3" in build_style_overlay(STYLE_ADHD, {"list_cap": 3})


def test_overlay_includes_hard_constraints_v2():
    text = build_style_overlay(STYLE_ADHD)
    assert STYLE_VERSION == "adhd_v2"
    assert "version=adhd_v2" in text
    assert "no invented time estimates" in text
    assert "high-risk side issues" in text
    assert "presentation-only" in text
    # seed skill carries Hard Constraints chapter
    from core.harness.utils.output_style import load_adhd_skill_text

    body = load_adhd_skill_text()
    assert "## Hard Constraints" in body
    assert "No invented time estimates" in body
    assert "Debug spiral" in body


def test_inject_appends_system_tail_skips_tool():
    msgs = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "hi"},
        {"role": "tool", "content": '{"ok":true}'},
    ]
    out = inject_output_style(msgs, style=STYLE_ADHD)
    assert out[0]["role"] == "system"
    assert "[output_style=adhd" in out[0]["content"]
    assert out[2]["content"] == '{"ok":true}'
    assert skill_body_hash()  # seed skill present


def test_a3a_record_and_query_output_style_events(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    row = record_output_style_event(
        style=STYLE_ADHD,
        project_id="prj_a",
        session_id="prj_a",
        source="factory_chat",
        tokens=estimate_reply_tokens("下一步：确认需求\n1. 上传\n2. 查看"),
        followups=infer_followups(
            [
                {"role": "user", "content": "a"},
                {"role": "assistant", "content": "b"},
                {"role": "user", "content": "c"},
            ]
        ),
        first_pass_ok=True,
        experiment_id="output_style_v1",
        arm="treatment",
    )
    assert row["style"] == STYLE_ADHD
    assert row["style_version"] == STYLE_VERSION
    assert row["style_hash"]
    assert row["tokens"] and row["tokens"] > 0
    assert row["followups"] == 1
    assert row["first_pass_ok"] is True
    assert row["arm"] == "treatment"

    record_output_style_event(
        style=STYLE_DEFAULT,
        project_id="prj_b",
        source="factory_chat",
        tokens=10,
        followups=0,
        first_pass_ok=False,
        experiment_id="output_style_v1",
        arm="control",
    )
    all_rows = query_output_style_events(limit=10)
    assert len(all_rows) >= 2
    adhd_only = query_output_style_events(limit=10, style=STYLE_ADHD)
    assert all(r["style"] == STYLE_ADHD for r in adhd_only)
    prj = query_output_style_events(limit=10, project_id="prj_a")
    assert prj and prj[-1]["project_id"] == "prj_a"


def test_a3b_assign_sticky_and_compare(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_OUTPUT_STYLE_EXPERIMENT_PCT", "100")
    from core.harness.utils.output_style import (
        ARM_TREATMENT,
        assign_output_style_experiment,
        compare_output_style_arms,
        style_experiment_bucket,
    )

    assert style_experiment_bucket("same") == style_experiment_bucket("same")
    proj: dict = {"id": "prj_exp", "output_style": "default"}
    first = assign_output_style_experiment(proj, sticky_id="prj_exp", adhd_pct=100)
    assert first["assigned"] is True
    assert first["arm"] == ARM_TREATMENT
    assert proj["output_style"] == STYLE_ADHD
    second = assign_output_style_experiment(proj, sticky_id="prj_exp", adhd_pct=100)
    assert second["assigned"] is False and second["sticky"] is True
    assert second["arm"] == ARM_TREATMENT

    locked = {"output_style": "default", "output_style_user_set": True}
    skipped = assign_output_style_experiment(locked, sticky_id="x", adhd_pct=100)
    assert skipped["assigned"] is False
    assert locked["output_style"] == "default"

    off = {"output_style": "default"}
    none = assign_output_style_experiment(off, sticky_id="y", adhd_pct=0)
    assert none["arm"] == ""
    assert off.get("output_style_arm") in (None, "")

    record_output_style_event(
        style=STYLE_ADHD,
        project_id="p1",
        tokens=40,
        followups=0,
        first_pass_ok=True,
        experiment_id="output_style_v1",
        arm="treatment",
    )
    record_output_style_event(
        style=STYLE_DEFAULT,
        project_id="p2",
        tokens=80,
        followups=2,
        first_pass_ok=False,
        experiment_id="output_style_v1",
        arm="control",
    )
    table = compare_output_style_arms(experiment_id="output_style_v1", limit=50)
    assert table["total"] >= 2
    assert "treatment" in table["arms"] or "control" in table["arms"]
    assert table["arms"]["treatment"]["n"] >= 1
