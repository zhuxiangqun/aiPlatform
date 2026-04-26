from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException


async def get_trusted_skill_pubkeys_map(execution_store: Any) -> Dict[str, str]:
    """
    Global trusted public keys for skill signature verification.
    Stored in global_setting: trusted_skill_pubkeys = {"keys":[{"key_id","public_key"}]}
    """
    out: Dict[str, str] = {}
    try:
        if execution_store is None:
            return out
        gs = await execution_store.get_global_setting(key="trusted_skill_pubkeys")
        v = gs.get("value") if isinstance(gs, dict) else None
        keys = (v or {}).get("keys") if isinstance(v, dict) else None
        if isinstance(keys, list):
            for it in keys:
                if not isinstance(it, dict):
                    continue
                kid = str(it.get("key_id") or "").strip()
                pk = str(it.get("public_key") or "").strip()
                if kid and pk:
                    out[kid] = pk
    except Exception:
        return {}
    return out


async def require_skill_signature_gate_approval(
    *,
    approval_manager: Any,
    user_id: str,
    skill_id: str,
    action: str,
    details: str,
    metadata: Dict[str, Any],
) -> str:
    """Create approval request for unverified skill signature actions."""
    from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RuleType

    if not approval_manager:
        raise HTTPException(status_code=503, detail="Approval manager not available")
    op = f"skills:signature_gate:{action}"
    rule = ApprovalRule(
        rule_id=f"skills_signature_gate_{action}",
        rule_type=RuleType.SENSITIVE_OPERATION,
        name=f"Skills signature gate（{action}）审批",
        description=f"workspace skill 签名未验证，{action} 需要审批",
        priority=1,
        metadata={"sensitive_operations": ["skills:signature_gate"]},
    )
    approval_manager.register_rule(rule)
    ctx = ApprovalContext(
        user_id=user_id or "admin",
        operation=op,
        operation_context={"details": details},
        metadata=metadata or {},
    )
    req = approval_manager.create_request(ctx, rule=rule)
    try:
        await approval_manager._persist(req)  # type: ignore[attr-defined]
    except Exception:
        pass
    return req.request_id


def signature_gate_eval(*, metadata: Optional[Dict[str, Any]], trusted_keys_count: int) -> Dict[str, Any]:
    """
    Determine whether signature gate should trigger.
    Rule: require approval unless signature_verified == True.
    """
    prov = (metadata or {}).get("provenance") if isinstance((metadata or {}).get("provenance"), dict) else {}
    integ = (metadata or {}).get("integrity") if isinstance((metadata or {}).get("integrity"), dict) else {}
    sig = prov.get("signature")
    bundle = integ.get("bundle_sha256")
    verified = prov.get("signature_verified") is True
    reason = prov.get("signature_verified_reason")
    if verified:
        return {"required": False, "verified": True, "reason": None}
    if not bundle:
        return {"required": True, "verified": False, "reason": "missing_bundle_sha256"}
    if not sig:
        return {"required": True, "verified": False, "reason": "missing_signature"}
    if trusted_keys_count <= 0:
        return {"required": True, "verified": False, "reason": "no_trusted_keys"}
    return {"required": True, "verified": False, "reason": str(reason or "not_verified")}


def is_approval_resolved_approved(approval_manager: Any, approval_request_id: str) -> bool:
    if not approval_request_id or not approval_manager:
        return False
    from core.harness.infrastructure.approval.types import RequestStatus

    r = approval_manager.get_request(str(approval_request_id))
    if not r:
        return False
    return r.status in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED)

