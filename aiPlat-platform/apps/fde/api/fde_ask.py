"""FDE — 追问端点：基于诊断上下文回答后续问题 (B0)."""
from __future__ import annotations

import re
from typing import Any, Dict, List
from apps.fde.api.schemas import FdeStatusResponse, FdeListResponse, FdeItemResponse


from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.api.core_facade import _sync_resolve
import logging

router = APIRouter(tags=["fde-ask"])

_EVIDENCE_SOURCE_LLM = "LLM推测"
_EVIDENCE_SOURCE_INDUSTRY = "行业普遍痛点"

# ════════════════════════════════════════════════════════════
# B0: FDE 追问端点 — 基于诊断上下文回答后续问题
# ════════════════════════════════════════════════════════════


class FdeAskRequest(BaseModel):
    question: str
    session_id: str = ""
    industry: str = ""
    company_name: str = ""
    pain_points: str = ""


@router.post("/ask", response_model=FdeStatusResponse)
async def fde_ask(req: FdeAskRequest):
    """## platform:allowed
    回答关于 FDE 诊断报告的追问（B0: 交互式追问）.

    基于 session_id 加载历史诊断上下文，或基于 industry/company/pain_points
    构建域上下文，然后回答用户的问题。

    Returns:
        {answer: str, sources: [{type, label, detail}]}
    """
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    industry = req.industry.strip()
    company = req.company_name.strip()
    domain_hint = industry or company

    try:
        # ── Build domain context ──
        from core.api.core_facade import DomainRouter
        from core.api.core_facade import GraphIndex

        did = DomainRouter().classify(domain_hint) if domain_hint else "ai-knowledge"

        context_blocks = [f"领域：{did}", f"行业：{industry}", f"公司：{company}"]

        # Load graph context
        try:
            g = GraphIndex.load(did)
            gstats = g.stats()
            context_blocks.append(f"知识图谱：{gstats['node_count']} 实体，{gstats['edge_count']} 关系")
        except Exception:
            context_blocks.append("知识图谱：不可用")

        # Load delivery tracking history
        try:
            fd = GraphIndex.load("fde-delivery")
            sessions = 0
            for nid, node in list(fd._nodes.items())[:50]:
                if getattr(node, "class_name", "") == "DiagnosisSession":
                    sessions += 1
            if sessions > 0:
                context_blocks.append(f"历史诊断：{sessions} 次")
        except Exception:
            logging.getLogger(__name__).debug('fde_ask failed', exc_info=True)

        # Load solution prototypes
        try:
            import os as _os_ask
            from core.api.core_facade import load_ontology_from_yaml
            sol_path = _os_ask.path.expanduser("~/.aiplat/ontologies/ai-solution.yaml")
            if _os_ask.path.exists(sol_path):
                sol = load_ontology_from_yaml(sol_path)
                arch_count = sum(1 for c in sol.classes if getattr(c, 'label', '') == '方案原型')
                context_blocks.append(f"AI方案原型：{arch_count} 类")
        except Exception:
            logging.getLogger(__name__).debug('fde_ask failed', exc_info=True)

        context = "\n".join(context_blocks)

        # ── Inject evidence_map from session for traceable answers ──
        evidence_context = ""
        if req.session_id:
            try:
                fd_session = GraphIndex.load("fde-delivery")
                sn = fd_session.get_node(req.session_id) or fd_session.find_by_name(req.session_id)
                if sn:
                    sid = getattr(sn, "entity_id", req.session_id)
                    for nid, e in fd_session.get_neighbor_edges(sid, direction="outgoing"):
                        if e.relation_name == "has_meta":
                            mn = fd_session.get_node(nid)
                            if mn:
                                import json as _json_ask
                                md = _json_ask.loads(mn.entity_name)
                                em = md.get("evidence_map", [])
                                if em:
                                    lines = ["该诊断报告的结论溯源："]
                                    for item in em[:5]:
                                        level = "本体实例支撑" if item.get("source") and item["source"] not in ("", _EVIDENCE_SOURCE_LLM, _EVIDENCE_SOURCE_INDUSTRY) else _EVIDENCE_SOURCE_LLM if not item.get("source") or item["source"] == _EVIDENCE_SOURCE_LLM else "历史案例参考"
                                        lines.append(f"  · {item.get('ai_opportunity','')} → {level} → 来源：{item.get('source','未标注')}")
                                    evidence_context = "\n".join(lines)
            except Exception:
                logging.getLogger(__name__).debug('code failed', exc_info=True)

        # ── Build prompt and call LLM ──
        from core.api.core_facade import sys_llm_generate
        from core.api.core_facade import best_model_for_purpose

        model = best_model_for_purpose("skill_execution")
        evidence_block = f"{evidence_context}\n\n" if evidence_context else ""
        system_content = _sync_resolve("fde-ask-system", context=context, evidence_block=evidence_block)
        messages = [
            {
                "role": "system",
                "content": system_content,
            },
            {
                "role": "user",
                "content": f"客户痛点：{req.pain_points}\n\n追问问题：{question}",
            },
        ]

        resp = await sys_llm_generate(model, messages, max_tokens=600, temperature=0.4)
        answer = str(getattr(resp, "content", "") or "")

        # ── Extract sources from answer for traceability ──
        sources = []
        # Match patterns like "在xxx域中" or "根据xxx类" or "参考xxx"
        for pattern, label in [
            (r'[^\s]*域', '域引用'),
            (r'[^\s]*类', '本体类'),
            (r'[^\s]*方案', '方案原型'),
        ]:
            matches = re.findall(pattern, answer)
            for m in matches[:3]:
                sources.append({"type": "domain", "label": label, "detail": m})

        return {
            "answer": answer,
            "sources": sources,
            "domain": did,
            "context_summary": context,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FDE ask failed: {str(e)[:300]}")
