"""P0: concise writing profile (STE-inspired, not full ASD-STE100)."""
from __future__ import annotations

from core.harness.utils.writing_profile import (
    PROFILE_CONCISE,
    PROFILE_OFF,
    apply_concise_prose,
    apply_error_message,
    apply_handoff_fields,
    build_writing_overlay,
    resolve_writing_profile,
)


def test_resolve_aliases_and_off(monkeypatch):
    monkeypatch.delenv("AIPLAT_WRITING_PROFILE", raising=False)
    assert resolve_writing_profile(None, default=PROFILE_OFF) == PROFILE_OFF
    assert resolve_writing_profile({"writing_profile": "concise_v1"}) == PROFILE_CONCISE
    assert resolve_writing_profile({"writing_profile": "ste80"}) == PROFILE_CONCISE
    assert resolve_writing_profile({"writing_profile": "off"}) == PROFILE_OFF
    assert resolve_writing_profile(
        {"metadata": {"writing_profile": "concise"}}
    ) == PROFILE_CONCISE


def test_protect_backticks_and_error_codes():
    raw = (
        "Please utilize the API prior to commencing; "
        "call `ensure_done` then check ERR_TIMEOUT=1."
    )
    out = apply_concise_prose(raw, profile=PROFILE_CONCISE)
    assert "`ensure_done`" in out
    assert "ERR_TIMEOUT" in out
    assert "prior to" not in out.lower()
    assert "utilize" not in out.lower()
    assert "use" in out.lower()


def test_protect_extra_terms_verbatim():
    err = "FileNotFoundError: missing /tmp/foo.json"
    out = apply_error_message(
        f"Please ensure you resolve {err} prior to commencing",
        profile=PROFILE_CONCISE,
        protect=[err],
    )
    assert err in out
    assert "prior to" not in out.lower()


def test_apply_handoff_fields_skips_artifact_ref():
    fields = {
        "summary": "Please utilize stage prior to commencing",
        "artifact_ref": "state:prd",
        "verify": "Make sure gate passes",
        "known_issues": ["ERR_TIMEOUT raw"],
        "next": "Proceed to code",
    }
    out = apply_handoff_fields(fields, profile=PROFILE_CONCISE)
    assert out["artifact_ref"] == "state:prd"
    assert out["known_issues"] == ["ERR_TIMEOUT raw"]
    assert "utilize" not in out["summary"].lower()


def test_overlay_empty_when_off():
    assert build_writing_overlay(PROFILE_OFF) == ""
    ov = build_writing_overlay(PROFILE_CONCISE, term_whitelist=["done_verify"])
    assert "writing_profile=concise_v1" in ov
    assert "done_verify" in ov
