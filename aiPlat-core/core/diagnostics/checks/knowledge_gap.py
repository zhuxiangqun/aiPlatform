"""Knowledge Gap 检测 — V1 关键词方案。

V1: 解析最近 pipeline run 的 Agent 输出，检测"显式知识缺口"关键词。
     - 不依赖外部 Embedding API
     - 纯字符串匹配，诊断调度器安全

# TODO(v2): Embedding-based gap detection
#  引入 Embedding 余弦相似度检测 RAG 召回质量。
#  设计约束：必须异步 + 3s timeout + 不能拖垮 auto-diagnostic scheduler。
"""

from typing import Any, Dict, List

# 显式知识缺口关键词（支持中英文）
_GAP_KEYWORDS = [
    "I don't know",
    "I do not know",
    "not found in the documentation",
    "no relevant information",
    "cannot answer",
    "unable to determine",
    "无法找到相关信息",
    "找不到相关文档",
    "无法回答",
    "没有足够的信息",
    "资料中没有提到",
    "现在还不确定",
]


async def check_knowledge_gap() -> Dict[str, Any]:
    try:
        from core.harness.execution.pipeline_run_store import get_pipeline_run_store
        store = get_pipeline_run_store()
        recent_runs = store.list_recent(limit=10)
    except Exception:
        return {"status": "warn", "reason": "pipeline_run_store unavailable"}

    if not recent_runs:
        return {"status": "pass", "note": "no recent pipeline runs"}

    gap_occurrences: List[Dict[str, Any]] = []

    for run in recent_runs:
        state = run.get("state", {})
        stages = state.get("_stages", [])
        if not isinstance(stages, list):
            continue

        for stage in stages:
            if not isinstance(stage, dict):
                continue
            output_key = stage.get("output_artifact", "")
            artifact = state.get(output_key, {})
            if not isinstance(artifact, dict):
                continue

            raw = artifact.get("raw_output", "")
            if not raw:
                raw = str(artifact)

            for kw in _GAP_KEYWORDS:
                if kw.lower() in raw.lower():
                    gap_occurrences.append({
                        "stage": stage.get("agent_id", "unknown"),
                        "keyword": kw,
                        "run_id": run.get("run_id", "")[:12],
                    })
                    break

    if gap_occurrences:
        return {
            "status": "warn",
            "gap_count": len(gap_occurrences),
            "occurrences": gap_occurrences[:5],
            "note": "V1 — keyword-based detection. upgrade to V2 for embedding similarity.",
        }
    return {"status": "pass", "runs_checked": len(recent_runs), "gaps_found": 0}
