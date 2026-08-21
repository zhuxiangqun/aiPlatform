"""P2-L5: Action 阶梯量化门测试 — Lv 标注 + 自动闭环误报率门（FP < 0.5%）。

对应：docs/research/企业级AI可信落地全景图-aiPlat对照.md §L5
（Action 阶梯 Lv1-4 + "误报率<0.5% 才自动闭环"的量化门）
"""
import asyncio

from core.harness.infrastructure.action_contract import (
    ActionContractModel,
    ActionLevel,
    CLOSURE_FP_RATE_MAX,
)
from core.harness.ontology_engine.action_registry import AsyncActionRegistry


def _run(coro):
    return asyncio.run(coro)


def _make_registry(tmp_path, level: ActionLevel) -> AsyncActionRegistry:
    db = str(tmp_path / "exec_store.db")
    reg = AsyncActionRegistry()
    reg._store.db_path = db
    handler_called = {"n": 0}

    async def handler(entity, params, actor="system"):
        handler_called["n"] += 1
        return {"ok": True, "count": handler_called["n"]}

    reg.register(ActionContractModel(
        action_id="test_auto",
        label="自动闭环动作",
        domain_id="default",
        action_level=level,
    ))
    reg._handlers["test_auto"] = handler
    return reg


def test_action_level_ladder():
    assert [v.value for v in ActionLevel] == [
        "lv1_readonly", "lv2_confirmed", "lv3_rule_bound", "lv4_auto_close",
    ]
    # 默认 Lv2 人工确认（保守）
    c = ActionContractModel(action_id="a", label="A")
    assert c.action_level == ActionLevel.LV2_CONFIRMED


def test_closure_gate_rejects_high_fp(tmp_path):
    reg = _make_registry(tmp_path, ActionLevel.LV4_AUTO_CLOSE)

    async def scenario():
        await reg._store.initialize()
        # 造 3 条历史：2 条误报 → fp_rate=0.667 ≥ 0.5%
        for i in range(3):
            await reg._store.insert_audit({
                "action_id": "test_auto",
                "entity_id": f"e{i}",
                "domain_id": "d",
                "result_status": "corrected" if i < 2 else "executed",
            })
        gate = await reg.compute_closure_gate("test_auto")
        assert gate["total"] == 3
        assert gate["false_positives"] == 2
        assert gate["fp_rate"] == 0.6667
        assert gate["allowed"] is False

    _run(scenario())


def test_closure_gate_allows_low_fp(tmp_path):
    reg = _make_registry(tmp_path, ActionLevel.LV4_AUTO_CLOSE)

    async def scenario():
        await reg._store.initialize()
        # 200 条执行，0 误报 → allowed
        for i in range(200):
            await reg._store.insert_audit({
                "action_id": "test_auto",
                "entity_id": f"e{i}",
                "domain_id": "d",
                "result_status": "executed",
            })
        gate = await reg.compute_closure_gate("test_auto")
        assert gate["total"] == 200
        assert gate["fp_rate"] == 0.0
        assert gate["allowed"] is True

    _run(scenario())


def test_non_lv4_never_auto_allowed(tmp_path):
    reg = _make_registry(tmp_path, ActionLevel.LV2_CONFIRMED)

    async def scenario():
        gate = await reg.compute_closure_gate("test_auto")
        assert gate["allowed"] is False
        assert "not lv4_auto_close" in gate["reason"]

    _run(scenario())


def test_execute_lv4_blocked_by_gate(tmp_path, monkeypatch):
    """Lv4 但误报率超标 → execute 返回 closure_gated，handler 不执行。"""
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    reg = _make_registry(tmp_path, ActionLevel.LV4_AUTO_CLOSE)
    # 造一个真实 GraphIndex 实体，让 execute 的实体加载通过
    from core.harness.ontology_engine.graph_index import GraphIndex
    g = GraphIndex.load("default")
    g.add_entity(entity_id="x1", entity_name="X1", class_name="C")
    g.add_entity_property("x1", "state", "s1")
    g.save()

    async def scenario():
        await reg._store.initialize()
        for i in range(2):
            await reg._store.insert_audit({
                "action_id": "test_auto",
                "entity_id": f"e{i}",
                "domain_id": "d",
                "result_status": "overridden",
            })
        result = await reg.execute(
            action_id="test_auto",
            entity_ref="x1",
            params={},
            actor="system",
        )
        assert result["status"] == "closure_gated"
        assert result["fp_rate"] == 1.0

    _run(scenario())


def test_execute_lv4_passes_gate(tmp_path, monkeypatch):
    """Lv4 且误报率 0 → 执行成功。"""
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    reg = _make_registry(tmp_path, ActionLevel.LV4_AUTO_CLOSE)
    from core.harness.ontology_engine.graph_index import GraphIndex
    g = GraphIndex.load("default")
    g.add_entity(entity_id="x1", entity_name="X1", class_name="C")
    g.add_entity_property("x1", "state", "s1")
    g.save()

    async def scenario():
        await reg._store.initialize()
        for i in range(50):
            await reg._store.insert_audit({
                "action_id": "test_auto",
                "entity_id": f"e{i}",
                "domain_id": "d",
                "result_status": "executed",
            })
        result = await reg.execute(
            action_id="test_auto",
            entity_ref="x1",
            params={},
            actor="system",
        )
        assert result["status"] in ("executed", "done", "completed", "success", "ok")

    _run(scenario())


def test_fp_rate_max_constant():
    assert CLOSURE_FP_RATE_MAX == 0.005  # 0.5%
