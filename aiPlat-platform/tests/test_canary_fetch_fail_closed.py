"""Canary live fetch must not claim healthy on errors (fail closed)."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.fde.api.fde_phase4 import resolve_live_canary_ok


def test_canary_fetch_exception_is_not_ok(monkeypatch):
    def _boom():
        raise RuntimeError("router down")

    monkeypatch.setattr(
        "core.api.core_facade.get_skill_router",
        _boom,
        raising=False,
    )
    # Import path used inside resolve_live_canary_ok
    import core.api.core_facade as facade

    monkeypatch.setattr(facade, "get_skill_router", _boom)
    ok, sources = resolve_live_canary_ok()
    assert ok is False
    assert "canary_error" in sources


def test_missing_skill_router_is_not_ok(monkeypatch):
    import core.api.core_facade as facade

    monkeypatch.setattr(facade, "get_skill_router", lambda: None)
    ok, sources = resolve_live_canary_ok()
    assert ok is False
    assert sources.get("canary_error") == "skill_router_unavailable"


def test_healthy_rollout_is_ok(monkeypatch):
    import core.api.core_facade as facade

    router = SimpleNamespace(get_rollout_status=lambda: [{"status": "ok"}])
    monkeypatch.setattr(facade, "get_skill_router", lambda: router)
    ok, sources = resolve_live_canary_ok()
    assert ok is True
    assert sources["canary"]["ok"] is True


def test_rollback_flagged_rollout_is_not_ok(monkeypatch):
    import core.api.core_facade as facade

    router = SimpleNamespace(
        get_rollout_status=lambda: [{"status": "ok"}, {"needs_rollback": True}]
    )
    monkeypatch.setattr(facade, "get_skill_router", lambda: router)
    ok, sources = resolve_live_canary_ok()
    assert ok is False
    assert sources["canary"]["ok"] is False
