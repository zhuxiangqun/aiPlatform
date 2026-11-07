"""Builtin skill eval suite seed — fixture/claim honesty + idempotent ensure."""
from __future__ import annotations

import pytest


def test_builtin_spec_has_override_and_fixed_id():
    from core.apps.eval.service.skill_evals_ops import (
        BUILTIN_SKILL_EVAL_SUITE_ID,
        builtin_skill_eval_suite_spec,
    )

    spec = builtin_skill_eval_suite_spec(tenant_id="eval-v1")
    assert spec["suite_id"] == BUILTIN_SKILL_EVAL_SUITE_ID
    assert spec["target_skill_id"] == "pdf_table_extract"
    assert len(spec["positive_queries"]) >= 1
    assert len(spec["negative_queries"]) >= 1
    assert isinstance(spec["skills_override"], list) and len(spec["skills_override"]) >= 2


@pytest.mark.asyncio
async def test_ensure_builtin_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(tmp_path / "exec.sqlite3")))
    await store.init()

    monkeypatch.setattr(
        "core.apps.eval.service.skill_evals_ops._store",
        lambda: store,
    )

    from core.apps.eval.service.skill_evals_ops import (
        BUILTIN_SKILL_EVAL_SUITE_ID,
        ensure_builtin_skill_eval_suites,
        list_skill_eval_suites,
    )

    first = await ensure_builtin_skill_eval_suites(tenant_id="eval-v1")
    assert first["created"] is True
    assert first["suite_id"] == BUILTIN_SKILL_EVAL_SUITE_ID
    cfg = (first.get("suite") or {}).get("config") or {}
    assert isinstance(cfg.get("skills_override"), list)

    second = await ensure_builtin_skill_eval_suites(tenant_id="eval-v1")
    assert second["created"] is False

    listed = await list_skill_eval_suites(tenant_id="eval-v1", limit=20, offset=0)
    ids = [str(x.get("suite_id") or "") for x in (listed.get("items") or [])]
    assert BUILTIN_SKILL_EVAL_SUITE_ID in ids


@pytest.mark.asyncio
async def test_preflight_and_store_direct_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec2.sqlite3"))

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(tmp_path / "exec2.sqlite3")))
    await store.init()

    monkeypatch.setattr(
        "core.apps.eval.service.skill_evals_ops._store",
        lambda: store,
    )
    monkeypatch.setattr(
        "core.apps.eval.service.skill_evals_ops._rt",
        lambda: None,
    )
    monkeypatch.setattr(
        "core.api.core_facade.get_execution_store",
        lambda: store,
    )

    from core.apps.eval.service.skill_evals_ops import (
        BUILTIN_SKILL_EVAL_SUITE_ID,
        ensure_builtin_skill_eval_suites,
        run_skill_eval_suite,
        skill_eval_preflight,
    )

    await ensure_builtin_skill_eval_suites(tenant_id="eval-v1")
    pf = await skill_eval_preflight(
        tenant_id="eval-v1", eval_kind="trigger", mode="heuristic"
    )
    assert pf["ok"] is True
    assert pf["checks"]["path"] == "store_direct"
    assert pf["runtime_tier"] == "fixture"
    assert pf["runtime_claim"] is False

    out = await run_skill_eval_suite(
        suite_id=BUILTIN_SKILL_EVAL_SUITE_ID,
        body={"eval_kind": "trigger", "mode": "heuristic", "max_cases": 10},
        actor={"actor_id": "test", "tenant_id": "eval-v1"},
    )
    assert out.get("status") == "ok"
    assert out.get("exec_path") == "store_direct"
    assert out.get("run_id")
    assert out.get("runtime_tier") == "fixture"
    metrics = ((out.get("run") or {}).get("metrics")) or {}
    if isinstance(metrics, str):
        import json

        metrics = json.loads(metrics)
    counts = (metrics or {}).get("counts") or {}
    assert int(counts.get("total") or 0) == 2
    assert int(counts.get("tp") or 0) == 1
    assert int(counts.get("tn") or 0) == 1
