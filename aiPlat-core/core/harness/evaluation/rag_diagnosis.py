"""
diagnose_rag_quality() — lightweight post-generation diagnostic logic.

Uses faithfulness + hallucination_risk + quality flag to infer the root cause
of RAG quality issues and suggests corrective actions.

Integration point: materials_chat.py after _check_hallucination(), before AgentResult.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("aiplat.rag_diagnosis")


def diagnose_rag_quality(
    faithfulness: float,
    hallucination_risk: float,
    quality: str,
    retrieved_count: int,
) -> Dict[str, Any]:
    """Analyze RAG generation output and suggest root cause.

    Args:
        faithfulness: HallucinationTracker faith score (0-1)
        hallucination_risk: HallucinationTracker risk score (0-1)
        quality: quality flag from self_review ("ok" | "needs_review" | "low_evidence")
        retrieved_count: number of documents retrieved for this query

    Returns:
        {"diagnosis": str | None, "suggested_action": str, "confidence": float, "evidence": {...}}
    """
    
    # ── Case 1: Good faith but low evidence → retrieval scope issue ──
    if faithfulness > 0.8 and quality == "low_evidence":
        diagnose = "检索召回范围不对——模型没有编内容但获取的信息不足以回答问题"
        suggest = "检查检索召回范围。HyDE 已触发重试。考虑扩大检索范围或调整 Chunk 大小。"
        confidence = 0.85 if hallucination_risk < 0.3 else 0.6
        logger.info("RAG diagnosis: retrieval_scope — faith=%.2f risk=%.2f quality=%s",
                    faithfulness, hallucination_risk, quality)
        return _result(diagnose, suggest, confidence, faithfulness, hallucination_risk, quality, retrieved_count)

    # ── Case 2: Enough docs but low faith → Prompt/model issue ──
    if retrieved_count >= 5 and faithfulness < 0.5:
        diagnose = "Prompt约束不足或模型未严格基于检索资料生成"
        suggest = "检查 system prompt 是否明确要求基于检索内容生成。考虑加强 Prompt 约束或降低 temperature。"
        confidence = 0.75 if hallucination_risk > 0.4 else 0.5
        logger.info("RAG diagnosis: prompt_constraint — faith=%.2f risk=%.2f chunks=%d",
                    faithfulness, hallucination_risk, retrieved_count)
        return _result(diagnose, suggest, confidence, faithfulness, hallucination_risk, quality, retrieved_count)

    # ── Case 3: Few docs + low faith → Chunk/Embedding issue ──
    if retrieved_count < 3 and faithfulness < 0.5:
        diagnose = "Chunk切分或Embedding模型可能有问题——检索结果太少且模型编造内容"
        suggest = "检查 Chunk 大小、切分策略、Embedding 模型版本。考虑增加 Chunk overlap。"
        confidence = 0.7
        logger.info("RAG diagnosis: chunk_embedding — faith=%.2f risk=%.2f chunks=%d",
                    faithfulness, hallucination_risk, retrieved_count)
        return _result(diagnose, suggest, confidence, faithfulness, hallucination_risk, quality, retrieved_count)

    # ── Case 4: needs_review — partial info, model stayed faithful ──
    if faithfulness > 0.6 and quality == "needs_review":
        diagnose = "部分信息缺失，但模型保持了忠实——缺少关键内容"
        suggest = "检查是否有遗漏的关键内容未被召回。考虑调整检索策略或增加知识库覆盖。"
        confidence = 0.6
        logger.info("RAG diagnosis: partial_info — faith=%.2f quality=%s chunks=%d",
                    faithfulness, quality, retrieved_count)
        return _result(diagnose, suggest, confidence, faithfulness, hallucination_risk, quality, retrieved_count)

    # ── No diagnosis needed ──
    return {"diagnosis": None}


def _result(
    diagnosis: str, suggestion: str, confidence: float,
    faith: float, risk: float, quality: str, count: int,
) -> Dict[str, Any]:
    return {
        "diagnosis": diagnosis,
        "suggested_action": suggestion,
        "confidence": round(confidence, 2),
        "evidence": {
            "faithfulness": round(faith, 3),
            "hallucination_risk": round(risk, 3),
            "quality_flag": quality,
            "retrieved_chunks": count,
        },
    }


def log_rag_diagnosis(
    run_id: str,
    diagnosis: Dict[str, Any],
    trace_service: Any = None,
) -> None:
    """Write RAG diagnosis to both AgentResult metadata and execution_store audit_log.

    Call this from integration/agent.py after agent execution completes.

    Args:
        run_id: unique run identifier
        diagnosis: return value of diagnose_rag_quality()
        trace_service: optional TraceService for audit_log persistence
    """
    if not diagnosis or not diagnosis.get("diagnosis"):
        return

    try:
        # Write to execution_store audit_log for historical trend queries
        from core.services.execution_store import get_execution_store
        store = get_execution_store()
        if hasattr(store, "query_meta") or hasattr(store, "record_event"):
            event = {
                "event_type": "rag_diagnosis",
                "run_id": run_id,
                "payload": diagnosis,
                "timestamp": __import__("time").time(),
            }
            # Try record_event first, fallback to generic method
            if hasattr(store, "record_event"):
                store.record_event(**event)
            elif hasattr(store, "query_meta"):
                store.query_meta(key=f"rag_diag:{run_id}", value=diagnosis)
    except Exception:
        logger.debug("Failed to persist RAG diagnosis for run %s", run_id, exc_info=True)
