"""Phase 1: audit mapping classify + change_surface + runtime guard."""

from __future__ import annotations

import pytest

from core.harness.infrastructure.action_audit_validate import (
    ACTION_AUDIT_COLUMNS,
    build_add_column_sql,
    build_rollback_sql,
    check_change_surface,
    classify_audit_fields,
    load_change_surface_whitelist,
    render_mapping_report,
)
from core.harness.infrastructure.workbench_runtime_guard import WorkbenchRuntimeGuard
from core.harness.ontology_engine.action_registry import AsyncActionRegistry
from core.harness.ontology_engine.builtin_actions import register_all


def test_classify_present_embedded_no_missing_core():
    clf = classify_audit_fields(columns=set(ACTION_AUDIT_COLUMNS))
    statuses = {v["status"] for v in clf.values()}
    assert "present" in statuses
    assert "embedded" in statuses
    # Phase 1 strategy: core Landing fields should not be hard-missing
    missing = [k for k, v in clf.items() if v["status"] == "missing"]
    assert missing == [], missing


def test_add_and_rollback_sql_paired():
    adds = build_add_column_sql()
    rolls = build_rollback_sql(adds)
    assert len(adds) == len(rolls)
    assert all("ADD COLUMN" in s and "NULL" in s for s in adds)
    assert all("DROP COLUMN" in s for s in rolls)


def test_render_mapping_report_sections():
    md = render_mapping_report()
    assert "present" in md
    assert "embedded" in md
    assert "ADD COLUMN" in md or "无（Phase 1" in md


def test_change_surface_whitelist_loaded_from_schema():
    wl = load_change_surface_whitelist()
    assert "prompt_extra.*" in wl["allowed_keys"]
    assert "policy_gate.*" in wl["forbidden_keys"]


def test_change_surface_rejects_out_of_whitelist():
    ok = check_change_surface(["prompt_extra.foo"])
    assert ok["ok"] is True
    bad = check_change_surface(["auth.admin", "database.url"])
    assert bad["ok"] is False
    assert bad["require_hitl"] is True
    assert {v["key"] for v in bad["violations"]} >= {"auth.admin", "database.url"}


def test_runtime_guard_action_registered():
    reg = AsyncActionRegistry()
    miss = WorkbenchRuntimeGuard.check_action_registered(reg, "no_such_action")
    assert miss["ok"] is False
    from core.harness.infrastructure.action_contract import ActionContractModel, RiskLevel

    reg.register(
        ActionContractModel(
            action_id="customer_action:lock-service:accept_order",
            label="Accept",
            domain_id="lock-service",
            target_class="InstallOrder",
            action_namespace="customer_action",
            eval_gate="customer_action_safety",
            risk_level=RiskLevel.HIGH,
            require_approval=True,
        )
    )
    hit = WorkbenchRuntimeGuard.check_action_registered(
        reg, "customer_action:lock-service:accept_order"
    )
    assert hit["ok"] is True


def test_runtime_guard_kpi_stub():
    bad = WorkbenchRuntimeGuard.check_kpi_not_stub(
        {"pending_decisions": [], "signal_alerts": [{"x": 1}]}
    )
    assert bad["ok"] is False
    assert "pending_decisions" in bad["stub_keys"]
    good = WorkbenchRuntimeGuard.check_kpi_not_stub({"signal_alerts": [{"x": 1}]})
    assert good["ok"] is True


@pytest.mark.asyncio
async def test_namespaced_accept_order_seed_registers_and_audits():
    """Seed registers; namespaced _write_audit embeds audit.v1 (mock store)."""
    from unittest.mock import AsyncMock

    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="aud_mock")
    reg = AsyncActionRegistry(store=store)
    n = register_all(reg)
    assert n >= 5
    c = reg.get("customer_action:lock-service:accept_order")
    assert c is not None
    assert c.action_namespace == "customer_action"
    assert c.eval_gate == "customer_action_safety"

    await reg._write_audit(
        c,
        entity_id="IO-1",
        domain_id="lock-service",
        from_state="pending",
        to_state="accepted",
        result_status="executed",
        constraint={},
        params={"assigned_technician": "tech-1"},
        snapshot={"status": "pending"},
        actor="fda-1",
        role="agent",
    )
    store.insert_audit.assert_awaited_once()
    mapped = store.insert_audit.await_args.args[0]
    assert mapped["params"]["schema"] == "audit.v1"
    assert mapped["params"]["action_namespace"] == "customer_action"
    assert mapped["params"]["params_hash"].startswith("sha256:")
    assert mapped["entity_snapshot"]["before"]["status"] == "pending"
    assert mapped["entity_snapshot"]["after"]["status"] == "accepted"
