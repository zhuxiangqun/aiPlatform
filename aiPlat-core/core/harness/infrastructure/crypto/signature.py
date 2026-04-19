"""
Signature helpers (P1-3): skill provenance verification.

Current scope:
- Ed25519 signatures over a canonical payload derived from:
  (skill_id, version, bundle_sha256)
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Dict, Optional, Tuple


def canonical_skill_payload(*, skill_id: str, version: str, bundle_sha256: str) -> bytes:
    payload = {
        "skill_id": str(skill_id),
        "version": str(version),
        "bundle_sha256": str(bundle_sha256),
    }
    # Stable encoding for signing/verifying
    s = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return s.encode("utf-8")


def _b64decode_maybe(s: str) -> bytes:
    v = (s or "").strip()
    if v.startswith("base64:"):
        v = v[len("base64:") :].strip()
    return base64.b64decode(v.encode("utf-8"))


def parse_ed25519_public_key(public_key: str):
    """
    Accept formats:
    - PEM (-----BEGIN PUBLIC KEY----- ...)
    - "ed25519:<base64-raw-32-bytes>"
    - raw base64 (32 bytes)
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives import serialization

    pk = (public_key or "").strip()
    if not pk:
        raise ValueError("empty_public_key")
    if pk.startswith("-----BEGIN"):
        return serialization.load_pem_public_key(pk.encode("utf-8"))
    if pk.lower().startswith("ed25519:"):
        raw = _b64decode_maybe(pk.split(":", 1)[1])
        return Ed25519PublicKey.from_public_bytes(raw)
    raw = _b64decode_maybe(pk)
    return Ed25519PublicKey.from_public_bytes(raw)


def parse_ed25519_signature(signature: str) -> bytes:
    """
    Accept formats:
    - "base64:...."
    - raw base64
    """
    sig = (signature or "").strip()
    if not sig:
        raise ValueError("empty_signature")
    return _b64decode_maybe(sig)


def verify_ed25519(*, public_key: str, message: bytes, signature: str) -> Tuple[bool, Optional[str]]:
    """
    Returns: (ok, error_reason)
    """
    try:
        pk = parse_ed25519_public_key(public_key)
        sig = parse_ed25519_signature(signature)
        pk.verify(sig, message)
        return True, None
    except Exception as e:
        return False, type(e).__name__


def key_id_for_public_key(public_key: str) -> str:
    """
    Deterministic key id for display/audit.
    """
    h = hashlib.sha256((public_key or "").strip().encode("utf-8")).hexdigest()
    return h[:12]


def verify_skill_signature(
    *,
    skill_id: str,
    version: str,
    bundle_sha256: str,
    signature: str,
    trusted_keys: Dict[str, str],
) -> Dict[str, Any]:
    """
    trusted_keys: {key_id: public_key_str}
    """
    msg = canonical_skill_payload(skill_id=skill_id, version=version, bundle_sha256=bundle_sha256)
    for kid, pk in (trusted_keys or {}).items():
        ok, err = verify_ed25519(public_key=pk, message=msg, signature=signature)
        if ok:
            return {"verified": True, "key_id": kid, "error": None}
    return {"verified": False, "key_id": None, "error": "no_trusted_key_matched"}

