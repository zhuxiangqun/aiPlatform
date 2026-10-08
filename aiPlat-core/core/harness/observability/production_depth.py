"""Production-depth readiness report for agent OS gaps.

Aggregates: stage reflection, exec/sandbox docker prefer, event ingress,
vector backend, observability contract.

callers: diagnostics GET /diagnostics/production-depth, CoreFacade.get_production_depth_report
"""

from __future__ import annotations

import inspect
import os
import shutil
from typing import Any, Dict, List


def _status(ok: bool, *, warn: bool = False) -> str:
    if ok:
        return "pass"
    return "warn" if warn else "fail"


def build_production_depth_report() -> Dict[str, Any]:
    """Synchronous readiness snapshot (safe for health checks / UI)."""
    checks: List[Dict[str, Any]] = []
    profile = (os.getenv("AIPLAT_PROFILE") or "").strip().lower()
    docker_bin = bool(shutil.which("docker"))

    # 1) Stage reflection closed
    reflection_ok = False
    reflection_detail = ""
    try:
        from core.harness.execution.pipeline_engine import PipelineEngine
        from core.harness.execution import stage_reflection as sr

        src = inspect.getsource(PipelineEngine._capture_stage_reflection)
        reflection_ok = "return None" not in src and "capture_stage_reflection" in src
        reflection_detail = f"module={sr.__name__} wired={reflection_ok}"
    except Exception as e:
        reflection_detail = f"{type(e).__name__}: {e}"
    checks.append({
        "id": "stage_reflection",
        "title": "Pipeline 阶段反思闭合",
        "status": _status(reflection_ok),
        "detail": reflection_detail,
        "hint": "pipeline_engine → stage_reflection.capture_stage_reflection",
    })

    # 2) Exec / sandbox docker preference
    prefer_exec = (
        profile == "production"
        or (os.getenv("AIPLAT_EXEC_PREFER_DOCKER") or "").lower() in ("1", "true", "yes", "y")
    )
    prefer_sandbox = (
        profile == "production"
        or (os.getenv("AIPLAT_SANDBOX_PREFER_DOCKER") or "").lower() in ("1", "true", "yes", "y")
    )
    explicit_backend = (os.getenv("AIPLAT_EXEC_BACKEND") or "").strip().lower()
    exec_ready = bool(explicit_backend == "docker" or (prefer_exec and docker_bin))
    checks.append({
        "id": "exec_docker",
        "title": "危险执行优先 Docker",
        "status": _status(exec_ready, warn=True),
        "detail": (
            f"profile={profile or '(unset)'} prefer_docker={prefer_exec} "
            f"AIPLAT_EXEC_BACKEND={explicit_backend or '(unset)'} docker_bin={docker_bin}"
        ),
        "hint": "export AIPLAT_PROFILE=production 或 AIPLAT_EXEC_PREFER_DOCKER=true，并安装 docker",
    })
    checks.append({
        "id": "sandbox_docker",
        "title": "Stage sandbox 优先 Docker",
        "status": _status(prefer_sandbox and docker_bin, warn=True),
        "detail": f"prefer_sandbox_docker={prefer_sandbox} docker_bin={docker_bin}",
        "hint": "export AIPLAT_SANDBOX_PREFER_DOCKER=true（或 AIPLAT_PROFILE=production）",
    })

    # 3) Agent event ingress
    ingress_enabled = (os.getenv("AIPLAT_AGENT_EVENT_INGRESS") or "").lower() in (
        "1", "true", "yes", "y",
    )
    ingress_stats: Dict[str, Any] = {}
    try:
        from core.harness.infrastructure.agent_event_ingress import get_agent_event_ingress
        ingress_stats = get_agent_event_ingress().stats
    except Exception as e:
        ingress_stats = {"error": f"{type(e).__name__}"}
    checks.append({
        "id": "agent_event_ingress",
        "title": "Agent 事件唤醒",
        "status": _status(ingress_enabled, warn=True),
        "detail": str(ingress_stats),
        "hint": "export AIPLAT_AGENT_EVENT_INGRESS=true；投递 ~/.aiplat/agent_events/inbox/*.json",
    })

    # 4) Vector backend
    vector_backend = "faiss"
    try:
        from core.harness.infrastructure.infra_bridge import resolve_vector_backend
        vector_backend = resolve_vector_backend(None)
    except Exception:
        vector_backend = (
            os.getenv("AIPLAT_VECTOR_BACKEND")
            or os.getenv("AIPLAT_VECTOR_DB")
            or "faiss"
        ).lower()
    vector_prod = vector_backend in ("milvus", "chroma", "pinecone") or profile != "production"
    checks.append({
        "id": "vector_backend",
        "title": "向量存储生产后端",
        "status": _status(vector_prod, warn=True),
        "detail": f"resolved={vector_backend} profile={profile or '(unset)'}",
        "hint": "生产建议 AIPLAT_VECTOR_BACKEND=milvus（或 chroma/pinecone）",
    })

    # 5) Observability contract
    contract: Dict[str, Any] = {}
    try:
        from core.harness.observability.contract import get_observability_contract
        contract = get_observability_contract()
    except Exception as e:
        contract = {"healthy": False, "error": f"{type(e).__name__}: {e}"}
    checks.append({
        "id": "observability_contract",
        "title": "可观测契约 (Prometheus+EventBus+run_graph)",
        "status": _status(bool(contract.get("healthy"))),
        "detail": contract.get("note") or str(contract.get("probes") or ""),
        "hint": (
            "契约内：Prometheus + EventBus + run_graph + syscall_events。"
            "ELK/OpenSearch 刻意标为 out_of_contract（可选外部接入，不算平台缺口）。"
        ),
        "contract": contract,
    })

    # 6) W6 — Agent architecture health (policy / bypass / plan_execute / router / CRAG / autonomy)
    arch_report: Dict[str, Any] = {}
    try:
        from core.harness.observability.architecture_health import build_architecture_health_report

        arch_report = build_architecture_health_report()
        for row in arch_report.get("checks") or []:
            if isinstance(row, dict) and row.get("id"):
                checks.append(row)
    except Exception as e:
        checks.append({
            "id": "architecture_health",
            "title": "架构健康 · 聚合失败",
            "status": "fail",
            "detail": f"{type(e).__name__}: {e}",
            "hint": "core.harness.observability.architecture_health",
        })

    passed = sum(1 for c in checks if c["status"] == "pass")
    warned = sum(1 for c in checks if c["status"] == "warn")
    failed = sum(1 for c in checks if c["status"] == "fail")
    overall = "pass" if failed == 0 and warned == 0 else ("warn" if failed == 0 else "fail")

    return {
        "status": overall,
        "score": int(round(100.0 * passed / max(len(checks), 1))),
        "profile": profile or "(unset)",
        "summary": {"pass": passed, "warn": warned, "fail": failed, "total": len(checks)},
        "checks": checks,
        "architecture_health": arch_report or None,
    }
