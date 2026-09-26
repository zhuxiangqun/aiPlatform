"""Unit tests for FDE clarify_dialog (structured memory + extract)."""
from __future__ import annotations

import pytest

from core.apps.fde.service.clarify_dialog import (
    ClarifyTurnInput,
    _dialog_memory_key,
    _merge_dialog_memory,
    prioritize_gaps,
    run_clarify_turn,
    simple_extract_fields,
)


def test_simple_extract_fields_jiangsu_suoan():
    ans = (
        "客户是江苏锁安，做智能锁安装/替换/维保。"
        "行业：安装服务。域：lock-service。"
        "痛点：1）派单靠微信群；2）记录散落表格；3）催单人工追。"
        "希望先做派单到场POC。"
    )
    ctx = {k: "" for k in [
        "company_name", "industry", "pain_points", "team_size", "budget",
        "existing_tech_stack", "domain_id", "internal_data_sources",
        "external_data_sources", "compliance_requirements",
        "poc_timeline", "production_timeline",
    ]}
    ex = simple_extract_fields(ans, ctx)
    assert ex["company_name"] == "江苏锁安"
    assert "安装" in ex["industry"]
    assert "派单" in ex["pain_points"]
    assert ex["domain_id"] == "lock-service"


def test_prioritize_gaps_core_first():
    gaps = ["团队规模", "行业", "预算范围", "公司名称", "痛点"]
    assert prioritize_gaps(gaps)[:3] == ["公司名称", "行业", "痛点"]


def test_merge_dialog_memory_fills_empty():
    key = "unit-dlg-mem-1"
    ctx = {"company_name": "", "industry": "安装服务", "pain_points": ""}
    _merge_dialog_memory(key, {"company_name": "江苏锁安", "industry": "安装服务", "pain_points": "派单"})
    filled = _merge_dialog_memory(key, ctx)
    assert filled["company_name"] == "江苏锁安"
    assert filled["pain_points"] == "派单"
    assert filled["industry"] == "安装服务"


def test_dialog_memory_key_prefers_dialog_id():
    req = ClarifyTurnInput(dialog_id="dlg-abc", session_id="sess", company_name="X")
    assert _dialog_memory_key(req) == "dlg-abc"


@pytest.mark.asyncio
async def test_run_clarify_turn_structured_memory_across_turns(monkeypatch):
    """Empty company on turn 3 still recovers from dialog_id field cache."""
    # Force no LLM so path is deterministic
    monkeypatch.setattr(
        "core.harness.utils.model_injection.best_model_for_purpose",
        lambda *a, **k: None,
    )

    did = "unit-clarify-mem-2"
    r1 = await run_clarify_turn(ClarifyTurnInput(turn=1, answer="", dialog_id=did))
    assert r1.get("question")

    r2 = await run_clarify_turn(ClarifyTurnInput(
        turn=2,
        dialog_id=did,
        answer="客户是江苏锁安。行业：安装服务。痛点：派单靠微信。域：lock-service。",
        company_name="", industry="", pain_points="",
        history=[{"role": "user", "content": "客户是江苏锁安"}],
    ))
    assert r2["context"]["company_name"] == "江苏锁安"
    assert r2["core_ready"] is True

    r3 = await run_clarify_turn(ClarifyTurnInput(
        turn=3,
        dialog_id=did,
        answer="大概20人",
        company_name="", industry="", pain_points="",
        history=[{"role": "user", "content": "大概20人"}],
    ))
    assert r3["context"]["company_name"] == "江苏锁安"
    assert "20" in (r3["context"].get("team_size") or "")
