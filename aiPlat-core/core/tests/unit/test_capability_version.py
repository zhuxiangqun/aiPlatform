"""A2 capability version SSOT resolver."""
from __future__ import annotations

from core.harness.meta.capability_version import load_versions_ssot, resolve_capability_version


def test_ssot_has_five_capabilities():
    ssot = load_versions_ssot()
    for cid in ("aiplat", "pi", "ontology", "evaluation", "fde"):
        assert cid in ssot, cid
        assert ssot[cid] == "0.1.0"


def test_resolve_matches_ssot():
    assert resolve_capability_version("aiplat") == "0.1.0"
    assert resolve_capability_version("ontology") == "0.1.0"
    assert resolve_capability_version("evaluation") == "0.1.0"
    assert resolve_capability_version("fde") == "0.1.0"


def test_facade_healthz_versions():
    from core.api.core_facade import (
        evaluation_healthz_payload,
        fde_healthz_payload,
        ontology_healthz_payload,
    )

    assert ontology_healthz_payload()["version"] == "0.1.0"
    assert evaluation_healthz_payload()["version"] == "0.1.0"
    hz = fde_healthz_payload()
    assert hz["version"] == "0.1.0"
    assert hz["product_id"] == "fde"
    assert hz["production_field"] is True
    assert hz["field_d1_adr"] == "accepted"
