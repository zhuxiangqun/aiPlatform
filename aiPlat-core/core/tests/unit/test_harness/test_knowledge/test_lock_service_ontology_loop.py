"""P2 mid/deep: lock-service 抽取确认 → 本体提案 → apply；例外改模式后 compiler 变化."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml

from core.harness.knowledge.ontology_constraint_compiler import compile_axiom_rules
from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore
from core.harness.knowledge_pipeline.extractor import (
    ExtractionResult,
    PendingExtractionStore,
)
from core.harness.ontology_engine.action_registry import AsyncActionRegistry
from core.harness.ontology_engine.builtin_actions import register_all
from core.harness.ontology_engine.graph_index import GraphIndex

CANONICAL = "customer_action:lock-service:accept_order"
DOMAIN = "lock-service"


@pytest.fixture()
def aiplat_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    onto = home / "ontologies"
    onto.mkdir(parents=True)
    # Minimal lock-service YAML (dict classes layout matches production)
    (onto / f"{DOMAIN}.yaml").write_text(
        yaml.dump(
            {
                "name": "智能锁安装维保",
                "namespace": "http://aiplat.local/ontology/lock-service/",
                "version": "1.0.0",
                "classes": {
                    "InstallOrder": {
                        "label": "安装工单",
                        "required_fields": ["order_id", "status"],
                        "tier": "logic",
                        "states": {"default": "pending"},
                    }
                },
                "axioms": [
                    {
                        "id": "LS-A1",
                        "severity": "error",
                        "description": "安装工单仅允许从 pending 状态接单",
                    }
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    GraphIndex._loaded_instances.clear()
    return home


@pytest.mark.asyncio
async def test_mid_tier_extract_confirm_proposal_apply(aiplat_home, tmp_path):
    """中档：pending 抽取确认 → 提案(edge 类) → 审批 → apply → 运行时 YAML 可读."""
    db = tmp_path / "exec.db"
    pending = PendingExtractionStore(db_path=str(db))
    await pending.initialize()

    result = ExtractionResult(
        extraction_id="ext_lock_mid_1",
        domain_id=DOMAIN,
        source_doc="现场纪要.md",
        overall_confidence=0.72,
        entities=[{"name": "配件清单", "type": "SparePartKit"}],
        relations=[],
        status="pending",
        draft_yaml_path="",
    )
    await pending.save(result)
    assert len(await pending.list_pending(DOMAIN)) == 1
    assert await pending.confirm("ext_lock_mid_1") is True
    assert await pending.list_pending(DOMAIN) == []

    store = VersionedOntologyStore(DOMAIN)
    prop_id = await store.create_proposal(
        {
            "add": {
                "class": {
                    "name": "SparePartKit",
                    "label": "配件包",
                    "tier": "edge",
                    "required_fields": ["kit_id"],
                }
            }
        },
        author="knowledge_factory",
    )
    approved = await store.approve_proposal(prop_id, approver_role="analyst")
    assert approved.get("success") is True, approved
    assert await store.apply_proposal(prop_id) is True

    # Live pointer must remain for DomainRouter / compiler
    live = aiplat_home / "ontologies" / f"{DOMAIN}.yaml"
    assert live.is_file()
    dom = load_ontology_from_yaml(str(live))
    labels = {c.label for c in dom.classes}
    assert "配件包" in labels
    assert store.get_current_version() >= 1

    proposals = await store.list_proposals(DOMAIN)
    applied = [p for p in proposals if p.get("proposal_id") == prop_id]
    assert applied and applied[0].get("status") == "applied"


@pytest.mark.asyncio
async def test_deep_tier_exception_then_mode_change(aiplat_home):
    """深档：L1 否决例外 → 提案写入新公理 → apply 后 compiler 规则变化."""
    # ── Exception: wrong-state accept blocked + audited ──
    g = GraphIndex(DOMAIN)
    eid = "IO-DEEP-0001"
    g.add_entity(eid, "Deep order", "安装工单", source_doc_id="t")
    g.add_entity_property(eid, "state", "completed")
    g.save()
    GraphIndex._loaded_instances.clear()

    audit_store = AsyncMock()
    audit_store.insert_audit = AsyncMock(return_value="aud_deep")
    reg = AsyncActionRegistry(store=audit_store)
    register_all(reg)
    blocked = await reg.execute(
        CANONICAL,
        (DOMAIN, eid),
        {"assigned_technician": "t1"},
        actor="fde",
        role="agent",
        _bypass_approval=True,
    )
    assert blocked.get("status") == "blocked"
    assert blocked.get("constraint_type") == "state"
    audit_store.insert_audit.assert_awaited()

    before = compile_axiom_rules(DOMAIN)
    assert any("pending" in r for r in before)
    assert not any("LS-DEEP-EXC" in r or "例外回写" in r for r in before)

    # ── Mode change: ontology proposal adds axiom from the exception ──
    vstore = VersionedOntologyStore(DOMAIN)
    prop_id = await vstore.create_proposal(
        {
            "add": {
                "axiom": {
                    "id": "LS-DEEP-EXC",
                    "severity": "error",
                    "description": "例外回写：completed 工单禁止再次接单；须先补偿回 pending",
                }
            }
        },
        author="exception_loop",
    )
    ok = await vstore.approve_proposal(prop_id, approver_role="anyone")  # edge → *
    assert ok.get("success") is True, ok
    assert await vstore.apply_proposal(prop_id) is True

    after = compile_axiom_rules(DOMAIN)
    assert any("例外回写" in r for r in after)
    # Soft constraint grew; L1 hard gate still blocks completed
    again = reg.check_entity_constraints(
        CANONICAL, DOMAIN, "安装工单", "completed", role="agent"
    )
    assert again.get("valid") is False
