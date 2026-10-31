"""aiPlat control-plane v0 — host exchange envelope + healthz shape.

SSOT: reports/five-products/modules/aiplat/contracts/schemas/
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, MutableMapping, Optional

SCHEMA_VERSION = "aiplat.control.v0"
_KINDS = frozenset({"bundle", "identity", "tenant", "policy", "run", "status"})
PRODUCT_ID = "aiplat"
CAPABILITY_ID = "aiplat"
DEPLOY_UNIT = "central"
DEFAULT_HOSTED = ("ontology", "evaluation", "fde")


def to_control_plane_v0(
    *,
    kind: str,
    payload: Optional[Mapping[str, Any]] = None,
    tenant_id: str = "",
    refs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    k = str(kind or "status").strip().lower()
    if k not in _KINDS:
        k = "status"
    out: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": k,
        "payload": dict(payload) if isinstance(payload, Mapping) else {},
    }
    if tenant_id:
        out["tenant_id"] = str(tenant_id)
    if refs:
        out["refs"] = [str(x) for x in refs if x is not None]
    return out


def normalize_health_status(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in {"ok", "healthy", "up", "pass", "passed", "success"}:
        return "ok"
    if s in {"degraded", "warn", "warning"}:
        return "degraded"
    if s in {"fail", "failed", "error", "down"}:
        return "fail"
    return "degraded" if s else "fail"


def to_aiplat_healthz(
    *,
    status: Any = "ok",
    version: str = "0.0.0",
    hosted: Optional[List[str]] = None,
    checks: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Central host healthz shape (aiPlat A1)."""
    out: Dict[str, Any] = {
        "status": normalize_health_status(status),
        "version": str(version or "0.0.0"),
        "product_id": PRODUCT_ID,
        "capability_id": CAPABILITY_ID,
        "deploy_unit": DEPLOY_UNIT,
        "hosted": list(hosted) if hosted is not None else list(DEFAULT_HOSTED),
    }
    if checks is not None:
        out["checks"] = dict(checks)
    return out


def attach_control_plane(
    response: MutableMapping[str, Any],
    envelope: Mapping[str, Any],
) -> MutableMapping[str, Any]:
    response["control_plane"] = dict(envelope)
    return response
