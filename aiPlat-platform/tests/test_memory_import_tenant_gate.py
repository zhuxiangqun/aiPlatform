"""Sticky/archive tenant must come from _resolve_identity, not raw headers."""
from __future__ import annotations

from pathlib import Path

_SRC = (Path(__file__).resolve().parents[1] / "api/routers/memory_import.py").read_text(
    encoding="utf-8"
)


def test_memory_import_tenant_uses_resolve_identity():
    assert "_resolve_identity" in _SRC
    assert "service_to_core_identity_headers" not in _SRC  # inbound gate, not outbound
    # Ungated header read must be gone from tenant helper.
    assert 'headers.get("X-AIPLAT-TENANT-ID")' not in _SRC
    assert "_tenant_from_request" in _SRC
