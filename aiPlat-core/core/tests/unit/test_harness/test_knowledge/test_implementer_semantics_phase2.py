"""W10 N18：实现方语义测试最小套件 + 门槛门。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline import implementer_semantics as sem


@pytest.mark.asyncio
async def test_suite_passes_and_gate_never_certifies(tmp_path):
    suite = await sem.run_implementer_semantics_suite(work_dir=str(tmp_path / "n18"))
    assert suite["ok"] is True
    assert suite["passed"] is True
    assert suite["certified"] is False
    assert suite["n18_full_conformance"] is False
    assert {c["id"] for c in suite["cases"]} == set(sem.REQUIRED_CASES)
    assert all(c["ok"] for c in suite["cases"])

    gate = sem.evaluate_implementer_semantics_gate(suite)
    assert gate["pass"] is True, gate
    assert gate["certified"] is False
    assert gate["n18_full_conformance"] is False


def test_gate_fails_when_suite_not_run():
    gate = sem.evaluate_implementer_semantics_gate(None)
    assert gate["pass"] is False
    assert "suite_not_run" in gate["issues"]


def test_gate_fails_when_case_missing():
    thin = {
        "passed": True,
        "cases": [{"id": "raw_immutable", "ok": True}],
        "required": list(sem.REQUIRED_CASES),
        "missing_required": [],
        "failed": [],
        "certified": False,
        "n18_full_conformance": False,
    }
    gate = sem.evaluate_implementer_semantics_gate(thin)
    assert gate["pass"] is False
    assert any(x.startswith("missing_case:") for x in gate["issues"])


def test_gate_rejects_honesty_certified_flag():
    suite = {
        "passed": True,
        "cases": [{"id": cid, "ok": True} for cid in sem.REQUIRED_CASES],
        "required": list(sem.REQUIRED_CASES),
        "missing_required": [],
        "failed": [],
        "certified": True,
        "n18_full_conformance": False,
    }
    gate = sem.evaluate_implementer_semantics_gate(suite)
    assert gate["pass"] is False
    assert "honesty_certified_flag_forbidden" in gate["issues"]
    assert gate["certified"] is False


@pytest.mark.asyncio
async def test_gate_fails_when_case_fails(tmp_path, monkeypatch):
    async def _fail_raw(*_a, **_k):
        return {"id": "raw_immutable", "ok": False, "detail": "forced"}

    monkeypatch.setattr(sem, "_probe_raw_immutable", _fail_raw)
    suite = await sem.run_implementer_semantics_suite(work_dir=str(tmp_path / "n18-bad"))
    assert suite["ok"] is False
    assert "raw_immutable" in suite["failed"]
    gate = sem.evaluate_implementer_semantics_gate(suite)
    assert gate["pass"] is False
    assert "case_failed:raw_immutable" in gate["issues"]
