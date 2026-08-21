"""P2-L1: tier 分层治变测试 — OntologyClass.tier / loader 解析 / 分级审批 / 审计分组。

对应设计：docs/research/plan-tier-ontology-layering.md §3/§4
  - tier 字段语义：core(承重墙, 全员审批) / logic(可变逻辑, 产品确认, 默认) / edge(实验边缘, 自服务)
  - apply_proposal 按 tier 分级审批 + edge 绝不自动升格（需复用证明）
"""
import asyncio
import json
import os
import tempfile

import pytest

from core.harness.knowledge.knowledge_ontology import (
    TIER_CORE,
    TIER_LOGIC,
    TIER_EDGE,
    normalize_tier,
)
from core.harness.knowledge.ontology_loader import (
    load_ontology_from_yaml,
    validate_ontology_yaml,
)
from core.harness.knowledge.versioned_ontology_store import (
    VersionedOntologyStore,
    PROMOTION_REUSE_THRESHOLD,
    TIER_APPROVAL_ROLES,
)


# ═══════════════════════════════════════════════════════════
# 1) tier 解析
# ═══════════════════════════════════════════════════════════

def test_normalize_tier_valid_and_default():
    assert normalize_tier("core") == TIER_CORE
    assert normalize_tier("  LOGIC ") == TIER_LOGIC
    assert normalize_tier("edge") == TIER_EDGE
    assert normalize_tier("wall") == TIER_LOGIC  # 未知 → 默认 logic
    assert normalize_tier(None) == TIER_LOGIC
    assert normalize_tier("") == TIER_LOGIC


def test_load_ontology_from_yaml_parses_tier(tmp_path):
    yaml_path = tmp_path / "tier_test.yaml"
    yaml_path.write_text(
        """
name: tier-test
namespace: http://aiplat.local/ontology/tier-test/
version: 1.0.0
classes:
  Customer:
    label: 客户
    tier: core
    required_fields: [id]
  RiskScore:
    label: 评分
    tier: logic
  TempHypothesis:
    label: 临时假设
    tier: edge
  Legacy:
    label: 存量无标注
""".strip(),
        encoding="utf-8",
    )
    domain = load_ontology_from_yaml(str(yaml_path))
    by_label = {c.label: c.tier for c in domain.classes}
    assert by_label["客户"] == TIER_CORE
    assert by_label["评分"] == TIER_LOGIC
    assert by_label["临时假设"] == TIER_EDGE
    assert by_label["存量无标注"] == TIER_LOGIC  # 默认 logic，存量零改动


def test_validate_ontology_yaml_rejects_invalid_tier():
    ok = validate_ontology_yaml(
        """
name: t
namespace: http://x/
version: 1.0.0
classes:
  A: {label: 甲, tier: core}
""".strip()
    )
    assert ok["valid"] is True
    bad = validate_ontology_yaml(
        """
name: t
namespace: http://x/
version: 1.0.0
classes:
  A: {label: 甲, tier: bearing_wall}
""".strip()
    )
    assert bad["valid"] is False
    assert any("invalid tier" in e for e in bad["errors"])


# ═══════════════════════════════════════════════════════════
# 2) impact 分析（tier 聚合 + 升格检测）
# ═══════════════════════════════════════════════════════════

def test_analyze_impact_tier_aggregation():
    store = VersionedOntologyStore("impact-test")
    current = {
        "classes": [
            {"name": "Customer", "tier": TIER_CORE},
            {"name": "RiskScore", "tier": TIER_LOGIC},
            {"name": "TempHypo", "tier": TIER_EDGE},
        ]
    }
    # 只动 edge 类 → max_tier = edge
    impact = store._analyze_impact(current, {"deprecate": ["TempHypo"]})
    assert impact["max_tier"] == TIER_EDGE
    assert impact["tiers"][TIER_EDGE] == ["TempHypo"]

    # 动 core 类 → max_tier = core
    impact = store._analyze_impact(current, {"deprecate": ["Customer"]})
    assert impact["max_tier"] == TIER_CORE

    # 新增类缺省 tier → logic
    impact = store._analyze_impact(current, {"add": {"class": {"name": "NewThing"}}})
    assert impact["max_tier"] == TIER_LOGIC


def test_analyze_impact_detects_promotion_edge_to_logic():
    store = VersionedOntologyStore("promo-test")
    current = {"classes": [{"name": "TempHypo", "tier": TIER_EDGE}]}
    impact = store._analyze_impact(
        current, {"merge": {"sources": ["TempHypo"], "into": {"name": "TempHypo", "tier": TIER_LOGIC}}}
    )
    assert impact["promotions"] == [
        {"class": "TempHypo", "from": TIER_EDGE, "to": TIER_LOGIC}
    ]
    assert impact["max_tier"] == TIER_LOGIC


# ═══════════════════════════════════════════════════════════
# 3) 分级审批 + tier gate（异步）
# ═══════════════════════════════════════════════════════════

def _run(coro):
    return asyncio.run(coro)


def test_approval_roles_matrix():
    assert "*" in TIER_APPROVAL_ROLES[TIER_EDGE]  # 自服务
    assert "product_manager" in TIER_APPROVAL_ROLES[TIER_LOGIC]
    assert "governance_admin" in TIER_APPROVAL_ROLES[TIER_CORE]
    assert "product_manager" not in TIER_APPROVAL_ROLES[TIER_CORE]


def test_approve_proposal_tier_gate(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    store = VersionedOntologyStore("gate-test")

    async def scenario():
        await store.store.initialize()
        # core 提案：非架构角色被拒
        core_prop = await store.create_proposal(
            {"deprecate": ["Customer"]}, author="tester"
        )
        # 手工把当前域里 Customer 标为 core，便于 impact 计算
        await store.store.update_ontology_proposal_impact(
            core_prop,
            json.dumps({"max_tier": TIER_CORE, "promotions": []}, ensure_ascii=False),
        )
        denied = await store.approve_proposal(core_prop, approver_role="operator")
        assert denied["success"] is False
        assert "tier=core" in denied["reason"]

        # 架构角色通过
        allowed = await store.approve_proposal(core_prop, approver_role="governance_admin")
        assert allowed["success"] is True
        assert allowed["status"] == "approved"

        # edge 提案：自服务（任意角色可批）
        edge_prop = await store.create_proposal(
            {"add": {"class": {"name": "TempHypo", "tier": TIER_EDGE}}}, author="tester"
        )
        edge_ok = await store.approve_proposal(edge_prop, approver_role="analyst")
        assert edge_ok["success"] is True

        # 已批准提案不能重复批准
        again = await store.approve_proposal(edge_prop, approver_role="admin")
        assert again["success"] is False

    _run(scenario())


def test_apply_proposal_tier_gate_blocks_core_without_arch_review(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    store = VersionedOntologyStore("apply-gate")

    async def scenario():
        await store.store.initialize()
        # 写一个 core 变更提案，approved 但无架构评审记录
        prop = await store.create_proposal({"deprecate": ["Customer"]}, author="tester")
        await store.store.update_ontology_proposal_impact(
            prop, json.dumps({"max_tier": TIER_CORE, "promotions": [], "approval_level": ""}, ensure_ascii=False)
        )
        await store.store.update_ontology_proposal_status(prop, "approved")
        assert await store.apply_proposal(prop) is False  # 阻断

        # 带架构评审证据 → 放行（无实体文件场景下返回 False 但原因不同；此处验证 gate 通过后走到 apply）
        await store.store.update_ontology_proposal_impact(
            prop, json.dumps({"max_tier": TIER_CORE, "promotions": [], "approval_level": TIER_CORE}, ensure_ascii=False)
        )
        await store.store.update_ontology_proposal_status(prop, "approved")
        # apply 应不再被 tier gate 阻断（后续可能因无 YAML 而正常 apply 或报文件不存在，两者都不是 gate 拒绝）
        ok = await store.apply_proposal(prop)
        assert ok is not False  # 未被 gate 拒绝

    _run(scenario())


def test_apply_proposal_blocks_edge_promotion_without_reuse_proof(monkeypatch, tmp_path):
    home = tmp_path / "home"
    onto_dir = home / "ontologies"
    onto_dir.mkdir(parents=True)
    (onto_dir / "promo-gate.yaml").write_text(
        """
name: promo-gate
namespace: http://aiplat.local/ontology/promo-gate/
version: 1.0.0
classes:
  TempHypo:
    label: 临时假设
    tier: edge
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    store = VersionedOntologyStore("promo-gate")

    async def scenario():
        await store.store.initialize()
        changes = {
            "merge": {
                "sources": ["TempHypo"],
                "into": {"name": "TempHypo", "tier": TIER_LOGIC},
            }
        }
        prop = await store.create_proposal(changes, author="tester")
        impact = json.loads((await store.store.get_ontology_proposal(prop)).get("impact_analysis", "{}"))
        assert impact["max_tier"] == TIER_LOGIC
        assert impact["promotions"], "应检测到 edge→logic 升格"
        await store.store.update_ontology_proposal_status(prop, "approved")

        # 无复用证明 → 阻断
        assert await store.apply_proposal(prop) is False

        # 复用证明 ≥ 阈值 → gate 放行
        changes["promotion_proof"] = {"reuse_count": PROMOTION_REUSE_THRESHOLD}
        prop2 = await store.create_proposal(changes, author="tester")
        await store.store.update_ontology_proposal_impact(
            prop2, json.dumps(impact, ensure_ascii=False)
        )
        await store.store.update_ontology_proposal_status(prop2, "approved")
        ok = await store.apply_proposal(prop2)
        assert ok is not False

    _run(scenario())


# ═══════════════════════════════════════════════════════════
# 4) 审计分组
# ═══════════════════════════════════════════════════════════

def test_ontology_audit_tier_distribution(monkeypatch, tmp_path):
    from core.harness.knowledge.ontology_audit import OntologyAuditor

    home = tmp_path / "home"
    onto_dir = home / "ontologies"
    onto_dir.mkdir(parents=True)
    (onto_dir / "audit-tier.yaml").write_text(
        """
name: audit-tier
namespace: http://aiplat.local/ontology/audit-tier/
version: 1.0.0
classes:
  Customer: {label: 客户, tier: core}
  Contract: {label: 合同, tier: core}
  RiskScore: {label: 评分, tier: logic}
  TempHypo: {label: 假设, tier: edge}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    report = OntologyAuditor().audit_domain("audit-tier")
    assert report.tier_distribution == {TIER_CORE: 2, TIER_LOGIC: 1, TIER_EDGE: 1}
    d = report.to_dict()
    assert d["tier_distribution"][TIER_CORE] == 2
    assert any("core-tier" in r for r in report.recommendations)
    assert any("edge-tier" in r for r in report.recommendations)
