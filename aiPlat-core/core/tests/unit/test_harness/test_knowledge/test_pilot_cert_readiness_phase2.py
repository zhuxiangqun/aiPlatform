"""E4：试点域认证就绪包（N01/N06/N09；certified 恒 false）。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline.conformance_pack import (
    build_pilot_cert_readiness_pack,
    evaluate_pilot_cert_readiness_gate,
)


@pytest.mark.asyncio
async def test_pilot_readiness_pack_and_honesty():
    pack = await build_pilot_cert_readiness_pack(pilot_domain="lock-service")
    assert pack["ok"] is True
    assert pack["focus_gates_ok"] is True
    assert pack["focus_evidence_ok"] is True
    assert pack["certified"] is False
    assert pack["pilot_certified"] is False
    assert pack["n24_full_conformance"] is False
    assert set(pack["item_gates"]) == {"N01", "N06", "N09"}
    assert all(g["ok"] is True for g in pack["item_gates"].values())
    assert all(g.get("certified") is False for g in pack["item_gates"].values())

    gate = evaluate_pilot_cert_readiness_gate(pack)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["pilot_certified"] is False

    forged = dict(pack)
    forged["pilot_certified"] = True
    bad = evaluate_pilot_cert_readiness_gate(forged)
    assert bad["ok"] is False
    assert "honesty_certified_flag_forbidden" in bad["issues"]
    assert bad["certified"] is False


def test_empty_readiness_gate_fails():
    gate = evaluate_pilot_cert_readiness_gate({})
    assert gate["ok"] is False
    assert gate["certified"] is False
