"""
Rapid Industry Insight API — 48h industry cognition endpoints.

POST /upload          — 投喂材料 → 实体提取 → 跨域对齐
POST /analyze         — 触发三问分析 → Q1+Q2+Q3
POST /answer          — 提交答案 → 评分 + 盲区定位
GET  /status/{id}     — 获取当前认知得分 + 盲区清单
POST /re-patch        — 回补修正后重新三问
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Body, UploadFile, File

logger = logging.getLogger(__name__)
router = APIRouter(tags=["fde-rapid-insight"])

# In-memory session store (stateless in production — use execution_store)
_sessions: Dict[str, Any] = {}


def _get_domain_id(industry_name: str) -> str:
    """Sanitize industry name to domain_id."""
    return f"rapid-{industry_name.replace(' ', '-').lower()[:40]}"


# ═══════════════════════════════════════════════════════════
# POST /upload
# ═══════════════════════════════════════════════════════════

@router.post("/rapid-insight/upload")
async def rapid_insight_upload(
    files: List[UploadFile] = File(...),
    industry_name: str = Query("新行业", description="行业名称"),
    tenant_id: str = Query("default", description="租户ID（多客户隔离）"),
):
    """Step 1: 上传行业材料 → 提取实体 → 跨域对齐."""
    from core.apps.fde.service.rapid_insight_service import RapidSession

    domain_id = _get_domain_id(industry_name)
    session_id = f"{domain_id}-{uuid.uuid4().hex[:8]}"

    # Parse documents
    all_chunks = []
    for f in files:
        try:
            content = await f.read()
            text = content.decode("utf-8", errors="replace")
            all_chunks.append({
                "id": f"chunk-{f.filename}-0",
                "text": text[:5000],
                "source": f.filename,
            })
        except Exception as e:
            logger.warning("Failed to read %s: %s", f.filename, e)

    if not all_chunks:
        raise HTTPException(status_code=400, detail="无法解析上传的文件")

    # Run ontology engine
    entities_extracted = 0
    relations_extracted = 0
    try:
        from core.harness.ontology_engine.engine import OntologyEngine
        from core.harness.knowledge.domain_router import DomainRouter

        # Register temporary domain
        DomainRouter().register_domain(domain_id, {
            "name": f"快速行业认知-{industry_name}",
            "description": f"临时域：{industry_name} 行业知识图谱",
            "collection_id": "default",
            "namespace": f"http://aiplat.local/ontology/{domain_id}/",
            "maturity": "seeding",
            "maturity_score": 0.0,
            "min_wiki_score": 0.25,
            "expand_subclasses": False,
            "min_cross_results": 3,
        }, auto_rebuild=False)

        engine = OntologyEngine(domain_id)
        result = await engine.process_chunks(all_chunks, doc_id=f"rapid:{session_id}")

        entities_extracted = result.stats.get("mapped_entities", 0)
        relations_extracted = result.stats.get("inferred_edges", 0)
    except Exception as e:
        logger.warning("Ontology engine failed: %s", e)
        # Continue with partial results

    # Cross-domain alignment
    aligned_domains = []
    try:
        from core.harness.knowledge_pipeline.resolver import CrossDomainResolver
        resolver = CrossDomainResolver()
        candidates = resolver.find_candidates("bell_unified_client")
        aligned_domains = list(set(
            c.get("left", {}).get("domain", "") for c in candidates
        ))[:5]
    except Exception:
        pass

    session = {
        "session_id": session_id,
        "industry_name": industry_name,
        "domain_id": domain_id,
        "tenant_id": tenant_id,
        "entities_extracted": entities_extracted,
        "relations_extracted": relations_extracted,
        "aligned_domains": aligned_domains,
        "status": "uploaded",
    }

    # P2: Auto domain suggestions
    auto_suggestions = []
    icebreaker_questions = []
    try:
        from core.apps.fde.service.rapid_insight_service import (
            auto_suggest_domains, generate_icebreaker_questions)
        # Build simple entity list from parsed chunks for suggestion
        entity_list = []
        for c in all_chunks[:3]:
            entity_list.append({"name": c.get("source", ""), "description": c.get("text", "")[:200]})
        auto_suggestions = auto_suggest_domains(entity_list)
        icebreaker_questions = generate_icebreaker_questions(aligned_domains)
    except Exception as e:
        logger.debug("auto_suggest failed: %s", e)

    session["auto_suggestions"] = auto_suggestions
    session["icebreaker_questions"] = icebreaker_questions
    _sessions[session_id] = session

    return {**session, "auto_suggestions": auto_suggestions, "icebreaker_questions": icebreaker_questions}


# ═══════════════════════════════════════════════════════════
# POST /analyze
# ═══════════════════════════════════════════════════════════

@router.post("/rapid-insight/analyze")
async def rapid_insight_analyze(body: Dict[str, Any]):
    """Step 2: 三问分析 — Q1行业共识 + Q2路线之争 + Q3穿透性试题."""
    session_id = body.get("session_id", "")
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    from core.apps.fde.service.rapid_insight_service import (
        extract_industry_consensus,
        detect_industry_controversies,
        generate_penetrating_questions,
    )

    domain_id = session["domain_id"]
    aligned = session.get("aligned_domains", [])

    q1 = extract_industry_consensus(domain_id, aligned)
    q2 = detect_industry_controversies(domain_id, aligned)
    q3 = generate_penetrating_questions(domain_id, aligned)

    session["q1_report"] = q1
    session["q2_report"] = q2
    session["q3_questions"] = q3.get("questions", [])
    session["score"] = 0.0
    session["blind_spots"] = []
    session["status"] = "analyzed"

    return {
        "session_id": session_id,
        "q1": q1,
        "q2": q2,
        "q3": q3,
    }


# ═══════════════════════════════════════════════════════════
# POST /answer
# ═══════════════════════════════════════════════════════════

@router.post("/rapid-insight/answer")
async def rapid_insight_answer(body: Dict[str, Any]):
    """Step 3: 提交单题答案 → 评分 + 盲区定位."""
    session_id = body.get("session_id", "")
    question_id = body.get("question_id", "")
    user_answer = body.get("answer", "")

    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    questions = session.get("q3_questions", [])
    question = next((q for q in questions if q["id"] == question_id), None)
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    # Simple keyword match scoring
    expected = set(question.get("expected_answer_entities", []))
    answer_lower = user_answer.lower()

    matched = [e for e in expected if e.lower() in answer_lower]
    correct = len(matched) >= max(1, len(expected) * 0.5)

    # Locate blind spots for wrong answers
    blind_spots = []
    if not correct:
        from core.harness.ontology_engine.graph_index import GraphIndex
        from core.apps.fde.service.rapid_insight_service import locate_blind_spot_source

        domain_id = session["domain_id"]
        aligned = session.get("aligned_domains", [])

        for d in [domain_id] + aligned:
            try:
                g = GraphIndex.load(d)
                if g._nodes:
                    for e in expected:
                        if e.lower() not in answer_lower:
                            spot = locate_blind_spot_source(e, g)
                            blind_spots.append(spot)
                    break
            except Exception:
                pass

    session["answers"] = session.get("answers", {})
    session["answers"][question_id] = {
        "correct": correct,
        "matched": matched,
        "blind_spots": blind_spots,
    }
    session["blind_spots"] = session.get("blind_spots", []) + blind_spots

    # Recalculate score
    total = len(session.get("answers", {}))
    passed = sum(1 for a in session["answers"].values() if a.get("correct"))
    session["score"] = round(passed / total, 2) if total else 0.0

    return {
        "correct": correct,
        "matched_entities": matched,
        "expected": list(expected),
        "blind_spots": blind_spots,
        "current_score": session["score"],
    }


# ═══════════════════════════════════════════════════════════
# GET /status/{session_id}
# ═══════════════════════════════════════════════════════════

@router.get("/rapid-insight/status/{session_id}")
async def rapid_insight_status(session_id: str):
    """获取当前认知得分 + 盲区清单."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {
        "session_id": session_id,
        "industry_name": session.get("industry_name"),
        "status": session.get("status"),
        "entities_extracted": session.get("entities_extracted", 0),
        "relations_extracted": session.get("relations_extracted", 0),
        "aligned_domains": session.get("aligned_domains", []),
        "score": session.get("score", 0.0),
        "answers": session.get("answers", {}),
        "blind_spots": session.get("blind_spots", []),
        "reuse_rate": _compute_reuse_rate(session),
        "auto_suggestions": session.get("auto_suggestions", []),
        "icebreaker_questions": session.get("icebreaker_questions", []),
    }


def _compute_reuse_rate(session: dict) -> dict:
    """P1: compute reuse rate for a session's domain."""
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        from core.apps.fde.service.rapid_insight_service import calculate_reuse_rate
        domain_id = session.get("domain_id", "")
        tenant_id = session.get("tenant_id", "default")
        g = GraphIndex.load(domain_id, tenant_id)
        return calculate_reuse_rate(g)
    except Exception:
        return {"rate": 1.0, "shared": 0, "custom": 0, "total": 0, "warning": False}


# ═══════════════════════════════════════════════════════════
# POST /re-patch
# ═══════════════════════════════════════════════════════════

@router.post("/rapid-insight/re-patch")
async def rapid_insight_re_patch(body: Dict[str, Any]):
    """回补修正后重新触发三问分析."""
    session_id = body.get("session_id", "")
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    from core.apps.fde.service.rapid_insight_service import (
        extract_industry_consensus,
        detect_industry_controversies,
        generate_penetrating_questions,
    )

    domain_id = session["domain_id"]
    aligned = session.get("aligned_domains", [])

    q1 = extract_industry_consensus(domain_id, aligned)
    q2 = detect_industry_controversies(domain_id, aligned)
    q3 = generate_penetrating_questions(domain_id, aligned)

    session["q1_report"] = q1
    session["q2_report"] = q2
    session["q3_questions"] = q3.get("questions", [])
    session["round_count"] = session.get("round_count", 0) + 1
    session["status"] = "re-analyzed"

    return {
        "session_id": session_id,
        "round": session["round_count"],
        "q1": q1,
        "q2": q2,
        "q3": q3,
    }
