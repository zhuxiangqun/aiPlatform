import os

import pytest


@pytest.mark.asyncio
async def test_phase65_evolution_engine_records_learning_artifacts(tmp_path, monkeypatch):
    """
    Phase 6.5 acceptance:
    - When AIPLAT_RECORD_LEARNING_ARTIFACTS is enabled, EvolutionEngine records:
      * skill_evolution artifact on successful trigger_evolution
      * skill_rollback artifact on auto_rollback trigger
    - This is best-effort and should not change success behavior.
    """
    monkeypatch.setenv("AIPLAT_RECORD_LEARNING_ARTIFACTS", "true")

    db_path = tmp_path / "executions.sqlite3"

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.services.trace_service import TraceService
    from core.harness.integration import KernelRuntime
    from core.harness.kernel.runtime import set_kernel_runtime
    from core.harness.infrastructure.approval.manager import ApprovalManager
    from core.apps.skills.evolution.engine import EvolutionEngine
    from core.apps.skills.evolution.types import EvolutionConfig, TriggerType

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()
    trace_service = TraceService(execution_store=store)
    runtime = KernelRuntime(execution_store=store, trace_service=trace_service, approval_manager=ApprovalManager(execution_store=store))
    set_kernel_runtime(runtime)

    engine = EvolutionEngine(EvolutionConfig())
    skill_id = "skill-1"

    r = await engine.trigger_evolution(
        skill_id=skill_id,
        trigger_type=TriggerType.POST_EXEC,
        context={"reason": "ok", "content": "x", "trace_id": "t1", "run_id": "r1", "success": True},
    )
    assert r.success is True
    assert r.new_version is not None

    # Force rollback via metrics degradation
    did_rb = await engine.auto_rollback(
        skill_id=skill_id,
        current_metrics={"m": 0.0},
        baseline_metrics={"m": 1.0},
    )
    assert did_rb is True

    items = await store.list_learning_artifacts(target_type="skill", target_id=skill_id, limit=50, offset=0)
    kinds = [i.get("kind") for i in (items.get("items") or [])]
    assert "skill_evolution" in kinds
    assert "skill_rollback" in kinds

