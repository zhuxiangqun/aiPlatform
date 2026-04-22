"""
Signed plan token for Skills Installer.

Purpose:
- Prevent "plan vs install" parameter drift in production.
- Plan endpoint returns plan_id (token). Install must present the same plan_id.
- Token is stateless: contains canonicalized request fields + detected_subdir + exp, signed by HMAC.

Env:
- AIPLAT_SKILL_INSTALL_PLAN_SECRET: required for signing/verification.
- AIPLAT_SKILL_INSTALL_PLAN_TTL_SECONDS: default 900 (15 min)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional, Tuple, List


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * ((4 - (len(s) % 4)) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))


def _secret() -> bytes:
    sec = (os.getenv("AIPLAT_SKILL_INSTALL_PLAN_SECRET") or "").encode("utf-8")
    if not sec:
        raise RuntimeError("missing_AIPLAT_SKILL_INSTALL_PLAN_SECRET")
    return sec


def _metadata_hash(metadata: Optional[Dict[str, Any]]) -> str:
    if not metadata:
        return ""
    try:
        s = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        s = str(metadata)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def skills_digest(skills: Any) -> str:
    """
    Compute a stable digest for the planned skill set.

    Input: list[{"skill_id","name","version","kind",...}] (as produced by installer_plan)
    We intentionally hash only a stable subset to prevent accidental drift:
      skill_id, name, version, kind
    """
    if not isinstance(skills, list) or not skills:
        return ""
    rows: List[Tuple[str, str, str, str]] = []
    for it in skills:
        if not isinstance(it, dict):
            continue
        rows.append(
            (
                str(it.get("skill_id") or "").strip(),
                str(it.get("name") or "").strip(),
                str(it.get("version") or "").strip(),
                str(it.get("kind") or "").strip(),
            )
        )
    rows = sorted(rows)
    s = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def canonical_plan_data(
    *,
    scope: str,
    source_type: str,
    url: Optional[str],
    ref: Optional[str],
    path: Optional[str],
    skill_id: Optional[str],
    subdir: Optional[str],
    auto_detect_subdir: bool,
    allow_overwrite: bool,
    metadata: Optional[Dict[str, Any]],
    detected_subdir: Optional[str],
    planned_skills_digest: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Canonicalize parameters that MUST match between plan and install.
    """
    return {
        "scope": (scope or "workspace").strip().lower(),
        "source_type": (source_type or "").strip().lower(),
        "url": (url or "").strip(),
        "ref": (ref or "").strip(),
        "path": (path or "").strip(),
        "skill_id": (skill_id or "").strip(),
        "subdir": (subdir or "").strip(),
        "auto_detect_subdir": bool(auto_detect_subdir),
        "allow_overwrite": bool(allow_overwrite),
        "metadata_hash": _metadata_hash(metadata),
        "detected_subdir": (detected_subdir or "").strip(),
        # binds plan_id to the actual set of skills to be installed
        "planned_skills_digest": (planned_skills_digest or "").strip(),
    }


def build_plan_token(*, data: Dict[str, Any], ttl_seconds: Optional[int] = None) -> Tuple[str, float]:
    """
    Returns: (plan_id, expires_at_epoch_seconds)
    """
    ttl = ttl_seconds
    if ttl is None:
        ttl = int(os.getenv("AIPLAT_SKILL_INSTALL_PLAN_TTL_SECONDS", "900") or "900")
    ttl = max(30, min(int(ttl), 24 * 3600))
    exp = float(time.time() + ttl)
    payload = {"v": 1, "exp": exp, "data": data}
    msg = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(_secret(), msg, hashlib.sha256).digest()
    token = f"{_b64url_encode(msg)}.{_b64url_encode(sig)}"
    return token, exp


def verify_plan_token(*, token: str, expected_data: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
    """
    Verify token signature, expiry and data match.
    Returns decoded payload on success; raises ValueError/RuntimeError on failure.
    """
    if not token or "." not in token:
        raise ValueError("invalid_plan_id")
    a, b = token.split(".", 1)
    msg = _b64url_decode(a)
    sig = _b64url_decode(b)
    sig2 = hmac.new(_secret(), msg, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, sig2):
        raise ValueError("plan_id_signature_mismatch")
    try:
        payload = json.loads(msg.decode("utf-8"))
    except Exception:
        raise ValueError("invalid_plan_id_payload")
    exp = float(payload.get("exp") or 0)
    n = float(time.time() if now is None else now)
    if exp <= 0 or n > exp:
        raise ValueError("plan_id_expired")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if data != expected_data:
        raise ValueError("plan_id_payload_mismatch")
    return payload
