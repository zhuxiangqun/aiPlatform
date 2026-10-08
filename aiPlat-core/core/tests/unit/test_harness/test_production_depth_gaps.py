"""Production-depth gap wiring: vector backend, sandbox prefer docker, observability contract."""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import pytest


def test_resolve_vector_backend_env(monkeypatch):
    from core.harness.infrastructure.infra_bridge import resolve_vector_backend

    monkeypatch.setenv("AIPLAT_VECTOR_BACKEND", "chroma")
    monkeypatch.delenv("AIPLAT_PROFILE", raising=False)
    assert resolve_vector_backend(None) == "chroma"
    assert resolve_vector_backend("milvus") == "milvus"


def test_resolve_vector_backend_production_default(monkeypatch):
    from core.harness.infrastructure.infra_bridge import resolve_vector_backend

    monkeypatch.delenv("AIPLAT_VECTOR_BACKEND", raising=False)
    monkeypatch.delenv("AIPLAT_VECTOR_DB", raising=False)
    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    assert resolve_vector_backend(None) == "milvus"


def test_create_sandbox_prefers_docker_in_production(monkeypatch):
    from core.harness.execution.sandbox import DockerSandbox, StageSandbox, create_sandbox

    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    stage = SimpleNamespace(sandbox_mode="subprocess")
    sb = create_sandbox(stage)
    assert isinstance(sb, DockerSandbox)

    monkeypatch.delenv("AIPLAT_PROFILE", raising=False)
    monkeypatch.setenv("AIPLAT_SANDBOX_PREFER_DOCKER", "false")
    stage2 = SimpleNamespace(sandbox_mode="subprocess")
    sb2 = create_sandbox(stage2)
    assert isinstance(sb2, StageSandbox)


def test_observability_contract_shape():
    from core.harness.observability.contract import get_observability_contract

    c = get_observability_contract()
    assert c["version"]
    assert c["healthy"] is True
    names = {x["component"] for x in c["stack"]}
    assert "prometheus" in names
    assert "elk_opensearch" in names
    elk = next(x for x in c["stack"] if x["component"] == "elk_opensearch")
    assert elk["status"] == "out_of_contract"


def test_get_exec_backend_prefer_docker(monkeypatch):
    from core.apps.exec_drivers import registry as reg

    monkeypatch.delenv("AIPLAT_EXEC_BACKEND", raising=False)
    monkeypatch.setenv("AIPLAT_EXEC_PREFER_DOCKER", "true")

    async def _yes():
        return True

    monkeypatch.setattr(reg.DockerExecDriver, "_docker_available", lambda self: _yes())

    async def _none_setting(*_a, **_k):
        return None

    class _RT:
        execution_store = None

    monkeypatch.setattr(reg, "get_kernel_runtime", lambda: _RT())
    backend = asyncio.get_event_loop().run_until_complete(reg.get_exec_backend())
    assert backend == "docker"


def test_build_production_depth_report_shape():
    from core.harness.observability.production_depth import build_production_depth_report

    report = build_production_depth_report()
    assert report["status"] in ("pass", "warn", "fail")
    assert "score" in report
    ids = {c["id"] for c in report["checks"]}
    assert {
        "stage_reflection",
        "exec_docker",
        "sandbox_docker",
        "agent_event_ingress",
        "vector_backend",
        "observability_contract",
    } <= ids
    # W6 architecture health folded into the same report
    assert {
        "policy_fail_mode",
        "llm_bypass_allowlist",
        "architecture_profile_pilot",
        "dynamic_router_opt_in",
        "retrieval_crag_entry",
        "autonomous_default_off",
    } <= ids
    assert report.get("architecture_health") is not None
    # reflection wiring must be closed
    ref = next(c for c in report["checks"] if c["id"] == "stage_reflection")
    assert ref["status"] == "pass"


def test_diag_check_production_depth():
    from core.diagnostics.checks.production_depth import check_production_depth

    out = asyncio.get_event_loop().run_until_complete(check_production_depth())
    assert out["status"] in ("pass", "warn", "fail")
    assert out.get("href") == "/diagnostics/production-depth"


def test_agent_event_ingress_dispatch():
    from core.harness.infrastructure.agent_event_ingress import AgentEventIngress

    called = {}

    async def _fake_run(agent_info, message, **kwargs):
        called["agent_id"] = getattr(agent_info, "id", None)
        called["message"] = message
        return {"run_id": "run-test", "status": "running"}

    ingress = AgentEventIngress(enabled=True, run_agent=_fake_run)
    asyncio.get_event_loop().run_until_complete(
        ingress._dispatch({"agent_id": "demo", "message": "hello"}, source="test")
    )
    assert called["agent_id"] == "demo"
    assert called["message"] == "hello"
    assert ingress._dispatched == 1
