"""Agent 产物质量校验 — 抽样 pipeline 产出物，运行已有校验器。

检查维度：
  - PRD: functional_requirements 至少 1 条 + acceptance_criteria 可验证
  - Architecture: components ≥ 3 + data_model ≥ 3
  - Code: 至少输出 1 个有效文件
  - Test Report: passed + failed + errors > 0

按 agent 维度汇总通过率，低于 70% 告警。
"""

from typing import Any, Dict, List, Optional


def _validate_prd_artifact(artifact: Dict) -> bool:
    """PRD 必须含至少 1 个功能需求且有验收标准。"""
    frs = artifact.get("functional_requirements", [])
    if not isinstance(frs, list) or len(frs) == 0:
        return False
    for fr in frs:
        if not isinstance(fr, dict):
            continue
        criteria = fr.get("acceptance_criteria", [])
        if isinstance(criteria, list) and len(criteria) > 0:
            return True
    return False


def _validate_architecture_artifact(artifact: Dict) -> bool:
    """架构必须含 ≥3 组件 + ≥3 数据实体。"""
    comps = artifact.get("components", [])
    models = artifact.get("data_model", [])
    return (isinstance(comps, (list, dict)) and len(comps) >= 3 and
            isinstance(models, list) and len(models) >= 3)


def _validate_code_artifact(artifact: Dict) -> bool:
    """代码产物必须至少包含 1 个文件。"""
    files_raw = artifact.get("raw_output", "")
    if not files_raw:
        files_raw = str(artifact)
    return "## FILE:" in str(files_raw) or "```" in str(files_raw)


def _validate_test_report(artifact: Dict) -> bool:
    """测试报告必须有 passed/failed/errors 非零统计。"""
    total = 0
    for key in ("passed", "failed", "errors"):
        val = artifact.get(key, 0)
        if isinstance(val, (int, float)):
            total += val
    return total > 0


_VALIDATORS = {
    "prd": _validate_prd_artifact,
    "architecture": _validate_architecture_artifact,
    "code": _validate_code_artifact,
    "code_generation": _validate_code_artifact,
    "test_report": _validate_test_report,
    "test_cases": _validate_test_report,
}


async def check_artifact_quality() -> Dict[str, Any]:
    """抽样最近 10 条 pipeline run，校验每个 agent 产出物质量。"""
    try:
        from core.harness.execution.pipeline_run_store import get_pipeline_run_store
    except ImportError:
        return {"status": "warn", "reason": "pipeline_run_store not available"}

    store = get_pipeline_run_store()
    try:
        recent_runs = store.list_recent(limit=10)
    except Exception:
        return {"status": "warn", "reason": "failed to list recent runs"}

    if not recent_runs:
        return {"status": "pass", "note": "no recent pipeline runs found"}

    agent_results: Dict[str, Dict[str, int]] = {}

    for run in recent_runs:
        state = run.get("state", {})
        stages = state.get("_stages", [])
        if not isinstance(stages, list):
            continue

        for stage in stages:
            if not isinstance(stage, dict):
                continue
            agent_id = stage.get("agent_id", "unknown")
            output_key = stage.get("output_artifact", "")
            artifact = state.get(output_key) if output_key else {}

            if not isinstance(artifact, dict) or not artifact:
                continue

            if agent_id not in agent_results:
                agent_results[agent_id] = {"total": 0, "passed": 0}

            agent_results[agent_id]["total"] += 1

            validator = _VALIDATORS.get(output_key)
            if validator and validator(artifact):
                agent_results[agent_id]["passed"] += 1

    failing_agents = []
    for agent, counts in agent_results.items():
        if counts["total"] == 0:
            continue
        rate = counts["passed"] / counts["total"]
        if rate < 0.7:
            failing_agents.append({
                "agent": agent,
                "pass_rate": round(rate, 2),
                "passed": counts["passed"],
                "total": counts["total"],
            })

    if failing_agents:
        return {"status": "warn", "failing_agents": failing_agents}
    return {"status": "pass", "agents_checked": len(agent_results)}
