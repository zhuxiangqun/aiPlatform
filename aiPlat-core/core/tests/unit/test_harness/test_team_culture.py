"""T2: team Culture overlay tests."""
from __future__ import annotations

from core.harness.utils.output_style import STYLE_ADHD, build_style_overlay
from core.harness.utils.team_culture import (
    CULTURE_MAX_TOKENS,
    CULTURE_VERSION,
    build_culture_overlay,
    compose_prose_overlays,
    culture_body_hash,
    inject_team_culture,
    load_culture_text,
    resolve_culture_enabled,
    truncate_culture_body,
)


def test_load_seed_culture():
    text = load_culture_text()
    assert text
    assert culture_body_hash()


def test_truncate_culture_max_tokens():
    huge = "principle " * 500
    info = truncate_culture_body(huge, max_tokens=CULTURE_MAX_TOKENS)
    assert info["truncated"] is True
    assert info["tokens"] <= CULTURE_MAX_TOKENS + 5  # rough bound
    assert len(info["body"]) <= CULTURE_MAX_TOKENS * 4 + 8


def test_resolve_culture_enabled_env_and_project(monkeypatch):
    monkeypatch.delenv("AIPLAT_TEAM_CULTURE", raising=False)
    assert resolve_culture_enabled(None) is True
    assert resolve_culture_enabled({"culture_enabled": False}) is False
    monkeypatch.setenv("AIPLAT_TEAM_CULTURE", "0")
    assert resolve_culture_enabled({"culture_enabled": True}) is False


def test_build_culture_overlay_and_inject_skips_tool():
    overlay = build_culture_overlay(enabled=True)
    assert f"[team_culture={CULTURE_VERSION}" in overlay
    assert "outrank output_style" in overlay
    assert build_culture_overlay(enabled=False) == ""

    msgs = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "hi"},
        {"role": "tool", "content": '{"ok":true}'},
    ]
    out = inject_team_culture(msgs, enabled=True)
    assert "[team_culture=" in out[0]["content"]
    assert out[2]["content"] == '{"ok":true}'


def test_compose_order_hard_culture_style():
    culture = build_culture_overlay(enabled=True, text="Be careful.\n")
    style = build_style_overlay(STYLE_ADHD, {"list_cap": 3})
    hard = "[hard] never hide errors"
    combined = compose_prose_overlays(
        hard_overlay=hard,
        culture_overlay=culture,
        style_overlay=style,
    )
    assert combined.index("[hard]") < combined.index("[team_culture=")
    assert combined.index("[team_culture=") < combined.index("[output_style=")
