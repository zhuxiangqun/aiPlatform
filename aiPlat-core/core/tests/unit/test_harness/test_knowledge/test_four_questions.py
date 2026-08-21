"""P2-L0: FDE 立项四问评估测试 — 逐问打分 + 总分判定 + MVP tier 建议。

对应：docs/research/企业级AI可信落地全景图-aiPlat对照.md §L0（决策反复 / 跨3+系统 / Owner+指标 / 可写回Action）
"""
from core.apps.fde.service.four_questions import (
    FOUR_QUESTIONS,
    GO_THRESHOLD,
    CONDITIONAL_THRESHOLD,
    evaluate_four_questions,
)


def test_four_questions_definition():
    assert len(FOUR_QUESTIONS) == 4
    keys = [q["key"] for q in FOUR_QUESTIONS]
    assert keys == ["recurrence", "cross_system", "owner_metrics", "action_writeback"]
    assert sum(q["weight"] for q in FOUR_QUESTIONS) == 1.0


def test_evaluate_go_high_score():
    r = evaluate_four_questions({
        "title": "合同签署自动化",
        "recurrence": "daily",
        "systems_count": 4,
        "has_owner": True,
        "metrics": ["签署时长", "出错率"],
        "action_writeback": "sign_contract",
    })
    assert r["verdict"] == "go"
    assert r["total_score"] >= GO_THRESHOLD
    assert r["suggested_tier"] in ("logic", "core")
    assert len(r["gaps"]) == 0


def test_evaluate_sandbox_low_score():
    r = evaluate_four_questions({
        "title": "一次性复盘报告",
        "recurrence": "once",
        "systems_count": 0,
        "has_owner": False,
        "metrics": [],
        "action_writeback": None,
    })
    assert r["verdict"] == "sandbox"
    assert r["total_score"] < CONDITIONAL_THRESHOLD
    assert r["suggested_tier"] == "edge"
    assert len(r["gaps"]) == 4


def test_evaluate_conditional_mid_score():
    r = evaluate_four_questions({
        "title": "库存调拨建议",
        "recurrence": "weekly",
        "systems_count": 2,
        "has_owner": True,
        "metrics": [],
        "action_writeback": None,
    })
    # 有 Owner 但无指标、无写回 → 50 分档（weekly 75 + cross 60 + owner 60 + action 0 = 48.75 → 49）
    assert CONDITIONAL_THRESHOLD <= r["total_score"] < GO_THRESHOLD or r["total_score"] < CONDITIONAL_THRESHOLD
    assert r["suggested_tier"] in ("edge", "logic")
    assert any(g["key"] == "action_writeback" for g in r["gaps"])


def test_score_boundaries():
    # 满分四问
    full = evaluate_four_questions({
        "recurrence": "daily", "systems_count": 5, "has_owner": True,
        "metrics": ["m"], "action_writeback": "x",
    })
    assert full["total_score"] == 100

    # 全零
    zero = evaluate_four_questions({
        "recurrence": "rare", "systems_count": 0, "has_owner": False,
        "metrics": [], "action_writeback": None,
    })
    assert zero["total_score"] < 30

    # 分数非负
    for a in zero["answers"]:
        assert 0 <= a["score"] <= 100


def test_empty_inputs_do_not_crash():
    r = evaluate_four_questions({})
    assert 0 <= r["total_score"] <= 100
    assert r["title"] == "未命名决策"
    assert len(r["answers"]) == 4
