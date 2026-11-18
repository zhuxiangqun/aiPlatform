"""v4.3.1 Phase 2 G2：Fact→Graph 可重建 + Action L1 required_permissions。"""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")

import pytest

from core.harness.infrastructure.action_contract import ActionContractModel
from core.harness.knowledge_pipeline.fact_ledger import FactLedger
from core.harness.knowledge_pipeline.fact_projector import project_facts_to_graph
from core.harness.ontology_engine.action_registry import AsyncActionRegistry
from core.harness.ontology_engine.graph_index import GraphIndex


@pytest.fixture
async def ledger(tmp_path):
    """临时 FactLedger。"""
    store = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await store.initialize()
    return store


@pytest.mark.asyncio
async def test_project_facts_rebuildable(ledger: FactLedger, tmp_path, monkeypatch):
    """G2：清投影后可从 Fact 精确重放。"""
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    src = await ledger.register_source(
        tenant_id="tenant-a",
        collection_id="lock-kb",
        kind="file",
        uri="file://orders/1.txt",
        content=b"status=pending",
        connector="g2",
        domain_id="lock-service",
    )
    evidence = [
        {
            "source_id": src["source_id"],
            "locator": "p.1",
            "quote": "status=pending",
            "fetched_at": src["fetched_at"],
        }
    ]
    await ledger.put_fact(
        tenant_id="tenant-a",
        collection_id="lock-kb",
        subject="InstallOrder:order-1",
        predicate="status",
        object="pending",
        evidence=evidence,
        source_policy="g2",
        extractor_version="test",
        review_status="published",
        confidence=0.9,
        allow_bootstrap_published=True,
        domain_id="lock-service",
    )
    seed = (
        tmp_path
        / "aiPlat-core"
        / "workspace_seeds"
        / "ontologies"
        / "lock-service-object-types.json"
    )
    # use repo seed if present
    from pathlib import Path

    repo_seed = (_repo_root() / "aiPlat-core/workspace_seeds/ontologies/lock-service-object-types.json")
    bindings = repo_seed if repo_seed.is_file() else None

    r1 = await project_facts_to_graph(
        tenant_id="tenant-a",
        domain_id="lock-service",
        ledger=ledger,
        bindings_path=bindings,
        clear_projected=True,
    )
    assert r1["rebuild_mode"] == "exact_replay_from_facts"
    assert "order-1" in (r1["created"] + r1["updated"])

    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load("lock-service", tenant_id="tenant-a")
    assert "order-1" in g._nodes
    assert g._nodes["order-1"].metadata.get("projection_source") == "fact_ledger"

    r2 = await project_facts_to_graph(
        tenant_id="tenant-a",
        domain_id="lock-service",
        ledger=ledger,
        bindings_path=bindings,
        clear_projected=True,
    )
    assert r2["removed_before"] >= 1
    assert "order-1" in (r2["created"] + r2["updated"])


@pytest.mark.asyncio
async def test_action_l1_policy_denied_without_permissions(tmp_path):
    """G2：required_permissions 缺失 → policy_denied。"""
    reg = AsyncActionRegistry()
    reg._store.db_path = str(tmp_path / "actions.db")
    await reg._store.initialize()

    async def handler(entity, params, actor="system"):
        return {"ok": True, "new_state": "accepted"}

    reg.register(
        ActionContractModel(
            action_id="customer_action:lock-service:accept_order",
            label="接受安装工单",
            domain_id="lock-service",
            target_class="安装工单",
            required_state="pending",
            require_approval=False,
            required_permissions=["action:lock-service:accept_order"],
            action_namespace="customer_action",
            eval_gate="customer_action_safety",
            audit=True,
        )
    )
    reg._handlers["customer_action:lock-service:accept_order"] = handler

    async def _get_entity(domain_id, entity_id):
        return {
            "id": entity_id,
            "class": "安装工单",
            "state": "pending",
            "domain": domain_id,
        }

    reg._get_entity = _get_entity  # type: ignore[method-assign]

    denied = await reg.execute(
        "customer_action:lock-service:accept_order",
        "order-1",
        {},
        actor="u1",
        role="operator",
        permissions=[],
    )
    assert denied["status"] == "policy_denied"

    allowed = await reg.execute(
        "customer_action:lock-service:accept_order",
        "order-1",
        {},
        actor="u1",
        role="operator",
        permissions=["action:lock-service:accept_order"],
    )
    assert allowed["status"] in {"executed", "done", "completed", "success", "ok"}
