"""Platform surfaces must not undo actor_from_http with raw header defaults."""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_gate_policies_routes_identity_through_actor_from_http():
    src = (_ROOT / "api/routers/gate_policies.py").read_text(encoding="utf-8")
    assert "actor_from_http" in src
    assert "def _identity_from_http" in src
    assert 'headers.get("X-AIPLAT-ACTOR-ID")' not in src
    assert 'headers.get("X-AIPLAT-ACTOR-ROLE")' not in src
    assert 'headers.get("X-AIPLAT-TENANT-ID")' not in src
    assert 'or "admin"' not in src


def test_prompt_templates_autosmoke_uses_gated_identity():
    src = (_ROOT / "apps/prompt/api/prompt_templates.py").read_text(encoding="utf-8")
    assert "def _autosmoke_identity" in src
    assert 'headers.get("X-AIPLAT-ACTOR-ID", "admin")' not in src
    assert 'headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")' not in src


def test_skill_evals_does_not_or_raw_headers_after_gate():
    src = (_ROOT / "apps/eval/api/skill_evals.py").read_text(encoding="utf-8")
    assert 'or http_request.headers.get("X-AIPLAT-ACTOR-ID"' not in src
    assert 'or http_request.headers.get("X-AIPLAT-TENANT-ID")' not in src
    assert 'or http_request.headers.get("X-AIPLAT-ACTOR-ROLE")' not in src
