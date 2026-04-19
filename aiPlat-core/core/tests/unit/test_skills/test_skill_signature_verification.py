from __future__ import annotations

import base64


def test_skill_signature_verify_ed25519_ok():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    from core.harness.infrastructure.crypto.signature import canonical_skill_payload, verify_skill_signature, key_id_for_public_key

    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key()
    pk_pem = pk.public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo).decode("utf-8")
    kid = key_id_for_public_key(pk_pem)

    msg = canonical_skill_payload(skill_id="demo_skill", version="1.2.3", bundle_sha256="a" * 64)
    sig = sk.sign(msg)
    sig_b64 = base64.b64encode(sig).decode("utf-8")

    r = verify_skill_signature(
        skill_id="demo_skill",
        version="1.2.3",
        bundle_sha256="a" * 64,
        signature=sig_b64,
        trusted_keys={kid: pk_pem},
    )
    assert r["verified"] is True
    assert r["key_id"] == kid


def test_skill_signature_verify_ed25519_fail_wrong_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    from core.harness.infrastructure.crypto.signature import canonical_skill_payload, verify_skill_signature, key_id_for_public_key

    sk = Ed25519PrivateKey.generate()
    wrong = Ed25519PrivateKey.generate()

    wrong_pk = wrong.public_key()
    wrong_pem = wrong_pk.public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo).decode("utf-8")
    kid = key_id_for_public_key(wrong_pem)

    msg = canonical_skill_payload(skill_id="demo_skill", version="1.2.3", bundle_sha256="b" * 64)
    sig = sk.sign(msg)
    sig_b64 = base64.b64encode(sig).decode("utf-8")

    r = verify_skill_signature(
        skill_id="demo_skill",
        version="1.2.3",
        bundle_sha256="b" * 64,
        signature=sig_b64,
        trusted_keys={kid: wrong_pem},
    )
    assert r["verified"] is False

