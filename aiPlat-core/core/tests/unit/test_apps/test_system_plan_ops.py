"""System combination Plan exam (§0.8 P3 / §10.1)."""
from __future__ import annotations

import pytest

from core.apps.eval.service.system_plan_ops import run_system_plan_exam


@pytest.mark.asyncio
async def test_run_system_plan_exam_default_parts_dry():
    out = await run_system_plan_exam(object_id="sys_demo", live=False)
    assert out.get("object_type") == "system"
    assert out.get("accuracy_claim") is False
    assert isinstance(out.get("runtime_parts"), list)
    assert len(out["runtime_parts"]) >= 4
    sub_ids = {p.get("sub_id") for p in out["runtime_parts"]}
    assert any(str(s).startswith("prompt:") for s in sub_ids)
    assert any(str(s).startswith("dataset:") for s in sub_ids)
    # Dry typed parts share actual fixture → homogeneous top-level tier
    assert out.get("runtime_tier") in ("fixture", "mixed")
    assert out.get("runtime_claim") is False
    assert out.get("counts", {}).get("parts", 0) >= 4
    assert out.get("counts", {}).get("tasks", 0) >= 1
    assert isinstance(out.get("evaluation_plan"), dict)
    assert out.get("ok") is True


@pytest.mark.asyncio
async def test_run_system_plan_exam_custom_two_parts():
    out = await run_system_plan_exam(
        object_id="sys_small",
        parts=[
            {"object_type": "prompt", "set_ids": ["prompt/basic"], "object_id": "p1"},
            {"object_type": "dataset", "set_ids": ["dataset/basic"], "object_id": "d1"},
        ],
        live=False,
    )
    assert len(out.get("parts") or []) == 2
    assert len(out.get("runtime_parts") or []) == 2
    assert out.get("counts", {}).get("parts") == 2
