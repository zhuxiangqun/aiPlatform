"""Gateway must not setdefault tenant from ungated spoofable headers."""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = (_ROOT / "api/routers/gateway.py").read_text(encoding="utf-8")


def test_gateway_tenant_header_only_inside_identity_gate():
    # Ungated "else: h_tenant = headers.get(...)" path must be gone.
    assert "Allow tenant_id to come from header when client doesn't send it in body" not in _SRC
    assert "header_identity_allowed" in _SRC
    # Tenant header read must sit inside the trusted-header block (after the gate call).
    gate_idx = _SRC.find("if header_identity_allowed(")
    tenant_idx = _SRC.find('headers.get("X-AIPLAT-TENANT-ID")')
    assert gate_idx > 0
    assert tenant_idx > gate_idx
    # Actor headers remain gated the same way.
    assert 'headers.get("X-AIPLAT-ACTOR-ID")' in _SRC[gate_idx:]
