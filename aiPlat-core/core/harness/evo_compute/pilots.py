"""Phase 0 首批三试点 genome 选型（实施计划 §9）。

低风险、可回放、可回滚：路由权重 / 检索参数 / 超时重试。
排除 Prompt 全文、PolicyGate、核心代码、客户合同参数。
"""
from __future__ import annotations

from typing import Any, Dict, List

from core.harness.evo_compute.genome_registry import register_genome

# 实施计划 §9 冻结的三个试点 id
PILOT_GENOME_IDS: tuple = (
    "routing.weights.v1",
    "retrieval.params.v1",
    "timeout.retry.v1",
)


def pilot_genome_specs() -> List[Dict[str, Any]]:
    """返回三试点 genome 契约（只读规格，不落盘）。

    Returns:
        三个 genome 字典列表。
    """
    return [
        {
            "genome_id": "routing.weights.v1",
            "target": "execution.routing",
            "representation": "continuous_vector",
            "fields": [
                {"name": "semantic_weight", "type": "float", "min": 0.0, "max": 1.0},
                {"name": "cost_weight", "type": "float", "min": 0.0, "max": 1.0},
                {"name": "latency_weight", "type": "float", "min": 0.0, "max": 1.0},
            ],
            "constraints": ["sum(weights) == 1.0"],
            "owner": "platform-oncall",
            "evaluation_profile": "routing_replay_v1",
            "rollback": "versioned_config",
            "risk_class": "low",
            "mutable": True,
            "pilot": True,
        },
        {
            "genome_id": "retrieval.params.v1",
            "target": "knowledge.retrieval",
            "representation": "continuous_vector",
            "fields": [
                {"name": "top_k", "type": "int", "min": 1, "max": 50},
                {"name": "score_threshold", "type": "float", "min": 0.0, "max": 1.0},
                {"name": "rrf_weight", "type": "float", "min": 0.0, "max": 1.0},
            ],
            "constraints": [],
            "owner": "platform-oncall",
            "evaluation_profile": "retrieval_replay_v1",
            "rollback": "versioned_config",
            "risk_class": "low",
            "mutable": True,
            "pilot": True,
        },
        {
            "genome_id": "timeout.retry.v1",
            "target": "execution.resilience",
            "representation": "continuous_vector",
            "fields": [
                {"name": "timeout_ms", "type": "int", "min": 100, "max": 120000},
                {"name": "max_retries", "type": "int", "min": 0, "max": 10},
                {"name": "backoff", "type": "float", "min": 1.0, "max": 8.0},
            ],
            "constraints": [],
            "owner": "platform-oncall",
            "evaluation_profile": "resilience_replay_v1",
            "rollback": "versioned_config",
            "risk_class": "low",
            "mutable": True,
            "pilot": True,
        },
    ]


def list_pilot_genome_ids() -> List[str]:
    """三试点 genome_id 列表。

    Returns:
        冻结的试点 id。
    """
    return list(PILOT_GENOME_IDS)


def register_pilot_genomes(*, persist: bool = True) -> Dict[str, Any]:
    """登记三试点 genome 到 Registry。

    Args:
        persist: 是否落盘到 AIPLAT_HOME。

    Returns:
        回执含 registered ids；certified/e2 恒 false。
    """
    registered: List[str] = []
    errors: List[Dict[str, str]] = []
    for spec in pilot_genome_specs():
        r = register_genome(spec, persist=persist)
        gid = str(spec.get("genome_id") or "")
        if r.get("ok"):
            registered.append(gid)
        else:
            errors.append({"genome_id": gid, "error": str(r.get("error") or "register_failed")})
    ok = len(registered) == len(PILOT_GENOME_IDS) and not errors
    return {
        "ok": ok,
        "registered": registered,
        "expected": list(PILOT_GENOME_IDS),
        "count": len(registered),
        "errors": errors,
        "pilots_determined": ok,
        "g0_foundation": True,
        "certified": False,
        "e2_claimed": False,
        "phase0_complete": False,
        "production_write": False,
    }
