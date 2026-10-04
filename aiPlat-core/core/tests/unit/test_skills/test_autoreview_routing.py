"""Tests for autoreview auto panel/single routing."""
from core.engine.skills.autoreview.routing import (
    diff_security_score,
    resolve_review_routing,
)


def test_explicit_false_forces_single():
    r = resolve_review_routing(
        panel=False,
        focus="security",
        files=["auth/login.ts"],
        content="password = 'x'",
        total_lines=20,
    )
    assert r.use_panel is False
    assert r.reason == "panel=false"


def test_explicit_true_elevates_comprehensive_to_security_panel():
    r = resolve_review_routing(panel=True, focus="comprehensive", total_lines=10)
    assert r.use_panel is True
    assert r.focus == "security"
    assert "panel=true" in r.reason


def test_auto_focus_security_uses_panel():
    r = resolve_review_routing(panel="auto", focus="security", total_lines=10)
    assert r.use_panel is True
    assert r.preset_name == "security"
    assert r.mode == "quick"


def test_auto_large_security_uses_deep():
    r = resolve_review_routing(panel=None, focus="security", total_lines=600)
    assert r.use_panel is True
    assert r.mode == "deep"


def test_auto_comprehensive_clean_stays_single():
    r = resolve_review_routing(
        panel="auto",
        focus="comprehensive",
        files=["pages/ReportFaultPage.tsx"],
        content="+export function Page() { return null }\n",
        total_lines=40,
    )
    assert r.use_panel is False
    assert r.mode == "single"
    assert r.reason == "auto:single_default"


def test_auto_comprehensive_with_auth_path_uses_panel():
    r = resolve_review_routing(
        panel="auto",
        focus="comprehensive",
        files=["src/auth/login.ts"],
        content="+export function login() {}\n",
        total_lines=30,
    )
    assert r.use_panel is True
    assert r.focus == "security"
    assert "security_signals" in r.reason


def test_auto_content_secret_signal():
    score = diff_security_score(
        files=["a.ts"],
        content="+const api_key = 'sk-test'\n+el.innerHTML = user\n",
    )
    assert score >= 2
    r = resolve_review_routing(
        panel="auto",
        focus="comprehensive",
        files=["a.ts"],
        content="+const api_key = 'sk-test'\n+el.innerHTML = user\n",
        total_lines=5,
    )
    assert r.use_panel is True


def test_unset_panel_defaults_to_auto(monkeypatch):
    monkeypatch.delenv("AIPLAT_AUTOREVIEW_PANEL_DEFAULT", raising=False)
    r = resolve_review_routing(
        panel=None,
        focus="comprehensive",
        files=["x.ts"],
        content="+const x = 1\n",
        total_lines=3,
    )
    assert r.reason == "auto:single_default"
