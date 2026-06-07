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


def parse_ed25519_private_key(private_key: str):
    """
    Accept formats:
    - PEM (-----BEGIN PRIVATE KEY----- ...)
    - "ed25519:base64-raw-32-bytes"
    - raw base64 (32 bytes)
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    pk = (private_key or "").strip()
    if not pk:
        raise ValueError("empty_private_key")
    if pk.startswith("-----BEGIN"):
        return serialization.load_pem_private_key(pk.encode("utf-8"), password=None)
    if pk.lower().startswith("ed25519:"):
        raw = _b64decode_maybe(pk.split(":", 1)[1])
        return Ed25519PrivateKey.from_private_bytes(raw)
    raw = _b64decode_maybe(pk)
    return Ed25519PrivateKey.from_private_bytes(raw)


def generate_ed25519_key_pair():
    """
    Returns (private_key_pem: str, public_key_pem: str)
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key()
    sk_pem = sk.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pk_pem = pk.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return sk_pem, pk_pem


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


def sign_skill(
    *,
    private_key: str,
    skill_id: str,
    version: str,
    bundle_sha256: str,
) -> str:
    """
    Sign a skill's canonical payload with an Ed25519 private key.

    Returns base64-encoded signature string (without "base64:" prefix).
    Raises ValueError on key parse or sign failure.
    """
    sk = parse_ed25519_private_key(private_key)
    msg = canonical_skill_payload(skill_id=skill_id, version=version, bundle_sha256=bundle_sha256)
    sig = sk.sign(msg)
    return base64.b64encode(sig).decode("utf-8")

