"""Batch B：Registry ``_bypass_approval`` 仅审批重入；裸 bypass 拒绝。"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.harness.infrastructure.action_contract import (
    ActionCategory,
    ActionContractModel,
    ActionScope,
    FailureStrategy,
    RiskLevel,
)
from core.harness.ontology_engine.action_registry import AsyncActionRegistry


ACTION_ID = "platform_action:test:bypass_gate"


async def _noop_handler(entity, params, actor="system"):
    return {"ok": True, "new_state": "ok"}


def _contract(*, require_approval: bool) -> ActionContractModel:
    return ActionContractModel(
        action_id=ACTION_ID,
        label="bypass gate probe",
        description="unit probe",
        category=ActionCategory.MUTATION,
        scope=ActionScope.GLOBAL,
        domain_id="platform",
        risk_level=RiskLevel.LOW,
        require_approval=require_approval,
        throttle_limit=0,
        failure_strategy=FailureStrategy.LOG_ONLY,
        action_namespace="platform_action",
        handler="core.harness.ontology_engine.builtin_handlers:confirm_extraction",
        input_schema={"type": "object", "properties": {}},
    )


@pytest.fixture()
def aiplat_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    return home


@pytest.mark.asyncio
async def test_naked_bypass_forbidden(aiplat_home):
    """裸 ``_bypass_approval=True`` → bypass_forbidden。"""
    store = AsyncMock()
    store.get_pending = AsyncMock(return_value=None)
    store.insert_audit = AsyncMock(return_value="a")
    reg = AsyncActionRegistry(store=store)
    c = _contract(require_approval=True)
    reg.register(c)
    reg._handlers[ACTION_ID] = _noop_handler

    out = await reg.execute(
        ACTION_ID,
        ("platform", "e1"),
        {},
        actor="u",
        _bypass_approval=True,
    )
    assert out.get("status") == "bypass_forbidden", out
    assert out.get("error") == "approval_reentry_required"


@pytest.mark.asyncio
async def test_bypass_with_unapproved_lock_forbidden(aiplat_home):
    store = AsyncMock()
    store.get_pending = AsyncMock(
        return_value={
            "lock_id": "L1",
            "action_id": ACTION_ID,
            "status": "pending",
        }
    )
    reg = AsyncActionRegistry(store=store)
    reg.register(_contract(require_approval=True))
    reg._handlers[ACTION_ID] = _noop_handler

    out = await reg.execute(
        ACTION_ID,
        ("platform", "e1"),
        {},
        actor="u",
        _bypass_approval=True,
        _approval_reentry_lock_id="L1",
    )
    assert out.get("status") == "bypass_forbidden", out
    assert out.get("error") == "approval_reentry_not_approved"


@pytest.mark.asyncio
async def test_approve_reentry_allows_bypass(aiplat_home):
    """approve() 写入 approved 后重入 execute 可 bypass。"""
    store = AsyncMock()
    store.get_pending = AsyncMock(
        return_value={
            "lock_id": "L-ok",
            "action_id": ACTION_ID,
            "status": "approved",
            "entity_ref": "platform:e1",
            "params": {},
            "actor": "requester",
        }
    )
    store.resolve_pending = AsyncMock(return_value=True)
    store.insert_audit = AsyncMock(return_value="a")
    lock = AsyncMock()
    lock.acquire = AsyncMock(return_value=True)
    lock.release = AsyncMock(return_value=True)

    reg = AsyncActionRegistry(store=store, lock_provider=lock)
    reg.register(_contract(require_approval=True))
    reg._handlers[ACTION_ID] = _noop_handler

    # 直接模拟 approve 重入路径
    out = await reg.execute(
        ACTION_ID,
        ("platform", "e1"),
        {},
        actor="requester",
        _bypass_approval=True,
        _approval_reentry_lock_id="L-ok",
    )
    assert out.get("status") == "executed", out


@pytest.mark.asyncio
async def test_require_approval_false_no_bypass_needed(aiplat_home):
    """合同 require_approval=false 时正常执行，无需 bypass。"""
    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="a")
    lock = AsyncMock()
    lock.acquire = AsyncMock(return_value=True)
    lock.release = AsyncMock(return_value=True)
    reg = AsyncActionRegistry(store=store, lock_provider=lock)
    reg.register(_contract(require_approval=False))
    reg._handlers[ACTION_ID] = _noop_handler

    out = await reg.execute(ACTION_ID, ("platform", "e1"), {}, actor="u")
    assert out.get("status") == "executed", out


def test_http_confirm_source_has_no_bypass():
    """生产 confirm / assert_inferred HTTP 源码不含裸 ``_bypass_approval=True``。"""
    from pathlib import Path

    # .../aiPlat-core/core/tests/unit/test_harness/test_knowledge/<file>
    aiplat_core = Path(__file__).resolve().parents[5]
    workspace = aiplat_core.parent
    confirm = workspace / "aiPlat-platform/apps/fde/api/extraction_routes.py"
    wiki = aiplat_core / "core/api/routers/wiki_ontology_engine.py"
    assert confirm.is_file(), confirm
    assert wiki.is_file(), wiki
    confirm_txt = confirm.read_text(encoding="utf-8")
    start = confirm_txt.find("async def confirm_extraction")
    assert start >= 0
    chunk = confirm_txt[start : start + 1800]
    assert "_bypass_approval=" not in chunk
    wiki_txt = wiki.read_text(encoding="utf-8")
    idx = wiki_txt.find("platform_action:graph:assert_inferred_edge")
    assert idx >= 0
    assert "_bypass_approval=" not in wiki_txt[idx : idx + 800]
