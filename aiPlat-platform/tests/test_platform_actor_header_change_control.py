"""change_control / learning_autocapture must not undo actor_from_http with raw headers."""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_change_control_routes_identity_through_gated_helper():
    src = (_ROOT / "api/routers/change_control.py").read_text(encoding="utf-8")
    assert "def _gated_identity" in src
    assert "actor_from_http" in src
    assert 'headers.get("X-AIPLAT-ACTOR-ID"' not in src
    assert 'headers.get("X-AIPLAT-TENANT-ID"' not in src
    assert 'or "admin"' not in src


def test_learning_autocapture_feedback_uses_actor_from_http():
    src = (_ROOT / "apps/learning/api/learning_autocapture.py").read_text(encoding="utf-8")
    assert "actor_from_http" in src
    assert 'headers.get("X-AIPLAT-ACTOR-ID")' not in src
    assert 'headers.get("X-AIPLAT-ACTOR-ROLE")' not in src
    assert 'headers.get("X-AIPLAT-TENANT-ID")' not in src
