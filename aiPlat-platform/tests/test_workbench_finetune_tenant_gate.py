"""Workbench/finetune must not trust raw tenant headers outside identity gate."""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_WB = (_ROOT / "apps/workbench/api/workbench.py").read_text(encoding="utf-8")
_FT = (_ROOT / "apps/misc/api/finetune.py").read_text(encoding="utf-8")
_CORE_FT = (
    Path(__file__).resolve().parents[2]
    / "aiPlat-core/core/api/routers/finetune.py"
).read_text(encoding="utf-8")


def test_workbench_tenant_via_resolve_identity():
    assert "_resolve_identity" in _WB
    assert "platform_dev_mode" in _WB
    assert 'headers.get("X-AIPLAT-TENANT-ID", "")' not in _WB
    assert 'headers.get("x-aiplat-tenant-id", "")' not in _WB


def test_platform_finetune_tenant_via_resolve_identity():
    assert "_resolve_identity" in _FT
    assert "platform_dev_mode" in _FT
    assert 'headers.get("X-AIPLAT-TENANT-ID", "dev-default")' not in _FT


def test_core_finetune_tenant_via_header_identity_allowed():
    assert "header_identity_allowed" in _CORE_FT
    # Ungated default tenant assignment removed.
    assert 'tenant = request.headers.get("X-AIPLAT-TENANT-ID", "dev-default")' not in _CORE_FT
