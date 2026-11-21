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


def _make_registry(
    tmp_path,
    level: ActionLevel,
    *,
    rollback_action_id: str = "test_auto_rollback",
) -> AsyncActionRegistry:
    """构造带可选 rollback 的测试注册表（对齐 N08 Lv4 门 v2）。

    Args:
        tmp_path: pytest 临时目录。
        level: Action 阶梯等级。
        rollback_action_id: Lv4 放行所需回滚动作；空串测缺失路径。
    """
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
        rollback_action_id=rollback_action_id,
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
    """≥min_samples 且高误报 → 拒绝（对齐 Lv4 门 v2）。"""
    reg = _make_registry(tmp_path, ActionLevel.LV4_AUTO_CLOSE)

    async def scenario():
        await reg._store.initialize()
        # 为什么：v2 要求 ≥10 样本才算 fp_rate；3 条会走 insufficient_history
        for i in range(12):
            await reg._store.insert_audit({
                "action_id": "test_auto",
                "entity_id": f"e{i}",
                "domain_id": "d",
                "result_status": "corrected" if i < 8 else "executed",
            })
        gate = await reg.compute_closure_gate("test_auto")
        assert gate["total"] == 12
        assert gate["false_positives"] == 8
        assert gate["fp_rate"] == round(8 / 12, 4)
        assert gate["allowed"] is False

    _run(scenario())


def test_closure_gate_allows_low_fp(tmp_path):
    """足样本 + rollback + 0 误报 → allowed。"""
    reg = _make_registry(tmp_path, ActionLevel.LV4_AUTO_CLOSE)

    async def scenario():
        await reg._store.initialize()
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
    from core.harness.ontology_engine.graph_index import GraphIndex
    g = GraphIndex.load("default")
    g.add_entity(entity_id="x1", entity_name="X1", class_name="C")
    g.add_entity_property("x1", "state", "s1")
    g.save()

    async def scenario():
        await reg._store.initialize()
        for i in range(10):
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
    """Lv4 + 足样本 + rollback + 0 误报 → 执行成功。"""
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
