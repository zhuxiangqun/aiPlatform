"""
Knowledge extraction REST API — document upload → LLM extract → drafts → confirm.
Mounted at /api/platform/apps/fde/extract
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File, Form

from core.api.core_facade import ExtractionPipeline, PendingExtractionStore, ExtractionResult

router = APIRouter(tags=["fde-extraction"])

logger = logging.getLogger(__name__)
_store = PendingExtractionStore()


@router.post("/extract")
async def extract_document(
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    domain_id: str = Form("default"),
    doc_name: str = Form("uploaded_doc"),
):
    """Extract entities + relations from text or uploaded file.

    Accepts either raw text or a file upload (PDF/Word/PPTX/text).
    Binary office/PDF files are parsed via ConverterRegistry — never UTF-8-decoded as garbage.
    """
    from core.api.core_facade import file_bytes_to_text

    content = (text or "").strip()
    parse_meta: Dict[str, Any] = {}
    if file:
        try:
            raw = await file.read()
            doc_name = doc_name or file.filename or "uploaded_doc"
            parsed = file_bytes_to_text(raw, filename=file.filename or doc_name)
            parse_meta = {
                "parser": parsed.get("parser"),
                "char_count": parsed.get("char_count"),
                "truncated": parsed.get("truncated"),
                "kind": parsed.get("kind"),
                "file_bytes": len(raw),
            }
            file_text = (parsed.get("text") or "").strip()
            if file_text:
                # File first, then optional paste (matches UI copy)
                content = f"{file_text}\n\n{content}".strip() if content else file_text
            elif not content:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"未能从文件解析出可读文字（parser={parsed.get('parser')}）。"
                        "请确认 PPTX/PDF 含可选中文本，或改用粘贴纯文本。"
                    ),
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("File read/parse failed: %s", e, exc_info=True)
            raise HTTPException(status_code=400, detail=f"Unable to read file: {e}") from e

    if not content.strip():
        raise HTTPException(status_code=400, detail="No text content provided")

    pipeline = ExtractionPipeline()
    results = await pipeline.run(content, doc_name=doc_name, domain_id=domain_id)

    # Persist pending extractions (and rejected/auto for audit trail)
    await _store.initialize()
    for r in results:
        await _store.save(r)

    empty = all(len(r.entities) == 0 for r in results) if results else True
    warning = ""
    if empty:
        warning = (
            "抽取结果为空：LLM 未返回实体，或文档未能解析为可读文本。"
            "请确认模型可用，或改用「粘贴纯文本」重试；扫描版 PDF 需先能抽出文字。"
        )
        logger.warning("extract empty for doc=%s domain=%s meta=%s", doc_name, domain_id, parse_meta)
    elif parse_meta.get("truncated") or any(getattr(r, "_truncated_chunks", False) for r in results):
        warning = (
            f"文档较长，仅用前约 {parse_meta.get('char_count') or 'N'} 字 / "
            f"{getattr(results[0], '_chunk_count', '?') if results else '?'} 段做抽取（加速）。"
            "完整手册可拆成多份再抽，或提高 AIPLAT_EXTRACT_MAX_CHUNKS。"
        )

    # Return frontend-friendly summary
    return {
        "extractions": [
            {
                "extraction_id": r.extraction_id,
                "domain_id": r.domain_id,
                "source_doc": r.source_doc,
                "overall_confidence": r.overall_confidence,
                "entity_count": len(r.entities),
                "relation_count": len(r.relations),
                "status": r.status,
                "draft_yaml_path": r.draft_yaml_path,
                "chunk_count": getattr(r, "_chunk_count", None),
                "top_entities": [
                    {"name": e.name, "class_type": e.class_type, "confidence": e.confidence}
                    for e in r.entities[:10]
                ],
            }
            for r in results
        ],
        "count": len(results),
        "warning": warning,
        "ok": not empty,
        "parse": parse_meta or None,
    }


@router.get("/extractions/pending")
async def list_pending_extractions(
    domain_id: str = Query("", description="Filter by domain"),
):
    """List pending extractions awaiting review."""
    await _store.initialize()
    items = await _store.list_pending(domain_id=domain_id)
    return {"pending": items, "count": len(items)}


@router.post("/extractions/{extraction_id}/confirm")
async def confirm_extraction(
    extraction_id: str,
    actor: str = Query("", description="extract_actor; audited, not a new role"),
):
    """确认抽取：K1 信号 + 写入知识图实体/关系（不改活 YAML）。

    「写入说明书」仍在 ③ 提案同意/应用；本接口只补 ABox（GraphIndex）。
    """
    from core.api.core_facade import k1_confirm_extraction, write_extraction_to_graph_index
    import json as _json

    receipt = await k1_confirm_extraction(extraction_id, actor=actor)
    if not receipt.get("ok"):
        raise HTTPException(status_code=404, detail=receipt.get("reason") or "confirm failed")

    proposal_id = None
    graph_write = None
    # Path A: draft proposal for ③ — does not write live YAML
    try:
        await _store.initialize()
        row = await _store.get_row(extraction_id)
        if row:
            proposal_id = await _store._enqueue_ontology_proposal(row)
            # ABox: write entities + relations into GraphIndex (knowledge graph)
            def _parse_list(raw):
                if isinstance(raw, list):
                    return raw
                if isinstance(raw, str) and raw.strip():
                    try:
                        val = _json.loads(raw)
                        return val if isinstance(val, list) else []
                    except Exception:
                        return []
                return []

            ents = _parse_list(row.get("entities_json"))
            rels = _parse_list(row.get("relations_json"))
            domain_id = str(row.get("domain_id") or receipt.get("domain_id") or "default")
            if ents:
                try:
                    graph_write = write_extraction_to_graph_index(
                        domain_id,
                        ents,
                        rels,
                        source_doc_id=f"extract:{extraction_id}",
                    )
                except Exception:
                    logger.warning(
                        "factory confirm: GraphIndex write failed for %s",
                        extraction_id,
                        exc_info=True,
                    )
                    graph_write = {"error": "graph_write_failed"}
    except Exception:
        logger.warning("factory confirm: proposal/graph failed for %s", extraction_id, exc_info=True)

    return {
        "status": "confirmed",
        "path": "K1+graph",
        "extraction_id": extraction_id,
        "domain_id": receipt.get("domain_id"),
        "signal_id": receipt.get("signal_id"),
        "trace_id": receipt.get("trace_id"),
        "trace_origin": receipt.get("trace_origin"),
        "extract_actor": receipt.get("extract_actor"),
        "entity_ids": receipt.get("entity_ids") or (graph_write or {}).get("created_entities") or [],
        "yaml_unchanged": True,
        "wrote_live_yaml": False,
        "wrote_cross_domain_edge": False,
        "idempotent": bool(receipt.get("idempotent")),
        "proposal_id": proposal_id,
        "graph_write": graph_write,
    }


@router.post("/extractions/{extraction_id}/reject")
async def reject_extraction(extraction_id: str):
    """Reject an extraction → mark as discarded."""
    await _store.initialize()
    ok = await _store.reject(extraction_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Extraction not found or already resolved")
    return {"status": "rejected", "extraction_id": extraction_id}


# ═══════════════════════════════════════════════════════════
# Cross-domain resolution
# ═══════════════════════════════════════════════════════════

@router.get("/resolution/candidates")
async def list_resolution_candidates(
    view_name: str = Query("unified_customer", description="Cross-domain view name"),
):
    """List cross-domain merge candidates from registry.json views."""
    try:
        from core.api.core_facade import CrossDomainResolver, seed_cross_domain_config
        seed_cross_domain_config()
        resolver = CrossDomainResolver()
        candidates = resolver.find_candidates(view_name)
        return {
            "view": view_name,
            "candidates": [
                {
                    "left": c.left,
                    "right": c.right,
                    "score": c.score,
                    "strategy": c.strategy,
                    "evidence": c.evidence,
                }
                for c in candidates[:50]
            ],
            "count": len(candidates),
            "sources": [
                {
                    "domain": s.get("domain"),
                    "class": s.get("class") or "",
                    "entity_count": len(
                        CrossDomainResolver._load_entities(
                            str(s.get("domain") or ""),
                            str(s.get("class") or ""),
                        )
                    ),
                }
                for s in ((CrossDomainResolver()._load_views().get(view_name) or {}).get("sources") or [])
            ],
            "hint": (
                ""
                if candidates
                else "两侧图里几乎没有同名/同键实体。请先在 FDE⑦ 为两个域导入有相同 customer_name 的实例，或确认抽取确认后两边都有可比名称。"
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/resolution/resolve")
async def resolve_cross_domain(body: Dict[str, Any]):
    """K2: open an arbitration ticket. Does NOT write a cross-domain edge."""
    view_name = body.get("view_name", "unified_customer")
    left_id = str(body.get("left_id", ""))
    right_id = str(body.get("right_id", ""))
    left_domain = str(body.get("left_domain", ""))
    right_domain = str(body.get("right_domain", ""))
    confidence = float(body.get("confidence", 1.0))
    strategy = str(body.get("strategy", "") or "")
    trace_id = str(body.get("trace_id", "") or "")
    signal_id = str(body.get("signal_id", "") or "")
    left_tenant = str(body.get("left_tenant", "") or "")
    right_tenant = str(body.get("right_tenant", "") or "")

    if not all([left_id, right_id, left_domain, right_domain]):
        raise HTTPException(status_code=400, detail="left_id, right_id, left_domain, right_domain required")

    try:
        from core.api.core_facade import k2_propose_arbitration

        out = k2_propose_arbitration(
            view_name=view_name,
            left_id=left_id,
            right_id=right_id,
            left_domain=left_domain,
            right_domain=right_domain,
            left_tenant=left_tenant,
            right_tenant=right_tenant,
            confidence=confidence,
            strategy=strategy if strategy else ("exact" if confidence >= 1.0 else ""),
            suggested="merge",
            trace_id=trace_id,
            signal_id=signal_id,
        )
        if not out.get("ok"):
            raise HTTPException(status_code=400, detail=out)
        return {
            "status": out.get("status") or "pending",
            "path": "K2",
            "ticket_id": out.get("ticket_id"),
            "trace_id": out.get("trace_id"),
            "edge_written": False,
            "wrote_cross_domain_edge": False,
            "ticket": out,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/resolution/tickets")
async def list_arbitration_tickets(
    status: str = Query(""),
    domain_id: str = Query(""),
    tenant_id: str = Query(""),
):
    try:
        from core.api.core_facade import k2_list_arbitration

        return k2_list_arbitration(status=status, domain_id=domain_id, tenant_id=tenant_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/resolution/tickets/{ticket_id}/decide")
async def decide_arbitration_ticket(ticket_id: str, body: Dict[str, Any]):
    try:
        from core.api.core_facade import k2_decide_arbitration

        out = k2_decide_arbitration(
            ticket_id,
            decision=str(body.get("decision") or ""),
            actor=str(body.get("actor") or body.get("arbit_actor") or ""),
            note=str(body.get("note") or ""),
        )
        if not out.get("ok"):
            code = 404 if out.get("reason") == "not_found" else 400
            raise HTTPException(status_code=code, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/resolution/tickets/{ticket_id}/apply")
async def apply_arbitration_ticket(ticket_id: str, body: Optional[Dict[str, Any]] = None):
    """K2: write edge only for approved merge tickets."""
    body = body or {}
    try:
        from core.api.core_facade import k2_apply_arbitration

        out = k2_apply_arbitration(
            ticket_id,
            actor=str(body.get("actor") or body.get("arbit_actor") or ""),
        )
        if not out.get("ok") and not out.get("idempotent"):
            code = 404 if out.get("reason") == "not_found" else 400
            raise HTTPException(status_code=code, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/resolution/tickets/{ticket_id}/rollback-edge")
async def rollback_arbitration_edge(ticket_id: str, request: Request):
    """E2: undo one snapshotted merge edge. Role is the header, not the body."""
    role = request.headers.get("x-aiplat-role") or ""
    try:
        from core.api.core_facade import k2_rollback_arbitration_edge

        out = k2_rollback_arbitration_edge(ticket_id, role=role)
        if not out.get("ok") and not out.get("idempotent"):
            reason = str(out.get("reason") or "")
            if reason == "not_found":
                code = 404
            elif reason in ("identity_missing", "role_not_in_tier"):
                code = 403
            else:
                code = 400
            raise HTTPException(status_code=code, detail=out)
        return out
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/k5/scan")
async def k5_scan(domain_id: str = Query("it-ops")):
    """K5: aggregate repeat failures into edge drafts. Does not apply YAML."""
    try:
        from core.api.core_facade import k5_scan_repeat_failures

        out = await k5_scan_repeat_failures(domain_id or "it-ops")
        if out.get("reason") == "edge_auto_apply_forbidden":
            raise HTTPException(status_code=409, detail=out)
        return out
    except Exception as e:
        logger.error("k5_scan failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/rag/context")
async def get_entity_context(body: Dict[str, Any]):
    """Pre-load GraphRAG context for an entity (used by ActionRegistry)."""
    entity_id = str(body.get("entity_id", ""))
    domain_id = str(body.get("domain_id", "default"))
    action_context = str(body.get("context", ""))

    if not entity_id:
        raise HTTPException(status_code=400, detail="entity_id required")

    try:
        from core.api.core_facade import GraphRAGRetriever
        retriever = GraphRAGRetriever()
        context = await retriever.get_entity_context(entity_id, domain_id, action_context)
        return context
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


# ═══════════════════════════════════════════════════════════
# Decision throttle check (frontend pre-flight)
# ═══════════════════════════════════════════════════════════

@router.post("/throttle/check")
async def check_throttle_status(body: Dict[str, Any]):
    """Pre-flight throttle check before executing an action."""
    action_id = str(body.get("action_id", ""))
    actor = str(body.get("actor", "system"))
    domain_id = str(body.get("domain_id", "fde-delivery"))

    if not action_id:
        raise HTTPException(status_code=400, detail="action_id required")

    try:
        from core.api.core_facade import DecisionThrottle
        from core.api.core_facade import get_action_registry
        reg = get_action_registry()
        c = reg.get(action_id)
        if not c:
            raise HTTPException(status_code=404, detail="Action not found")

        throttle = DecisionThrottle()
        tl = getattr(c, 'throttle_limit', 0) or 0
        result = await throttle.check_rate_limit(
            actor=actor, action_id=action_id, domain_id=domain_id or c.domain_id,
            time_window_sec=getattr(c, 'throttle_window_seconds', 3600) or 3600,
            limit=tl, block_on_breach=False,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


# ═══════════════════════════════════════════════════════════
# Ontology evolution (Phase 3)
# ═══════════════════════════════════════════════════════════

@router.post("/ontology/proposals")
async def create_ontology_proposal(body: Dict[str, Any]):
    """Submit an ontology evolution proposal (add/split/merge/deprecate)."""
    domain_id = str(body.get("domain_id", "lock-service"))
    changes = body.get("changes", {})
    author = str(body.get("author", "system"))

    if not changes:
        raise HTTPException(status_code=400, detail="changes required")

    try:
        from core.api.core_facade import VersionedOntologyStore
        store = VersionedOntologyStore(domain_id)
        proposal_id = await store.create_proposal(changes, author)
        return {"status": "draft", "proposal_id": proposal_id, "domain_id": domain_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/ontology/proposals")
async def list_ontology_proposals(
    domain_id: str = Query("", description="Filter by domain"),
):
    """List ontology evolution proposals."""
    try:
        from core.api.core_facade import VersionedOntologyStore
        store = VersionedOntologyStore(domain_id or "lock-service")
        proposals = await store.list_proposals(domain_id=domain_id)
        return {"proposals": proposals, "count": len(proposals)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/ontology/proposals/{proposal_id}/approve")
async def approve_ontology_proposal(proposal_id: str, request: Request, body: Dict[str, Any] = None):
    """V4: identity from X-AIPLAT-ROLE. Body approver_role is not a grant."""
    try:
        from core.api.core_facade import approve_proposal_once

        result = await approve_proposal_once(
            proposal_id,
            role=request.headers.get("x-aiplat-role") or "",
        )
        if result.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=result.get("reason") or "not_found")
        if not result.get("success"):
            raise HTTPException(status_code=403, detail=result)
        return {"status": "approved", "proposal_id": proposal_id, **result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/ontology/proposals/{proposal_id}/apply")
async def apply_ontology_proposal(proposal_id: str):
    """Apply an approved ontology proposal → live YAML + receipt (path A)."""
    try:
        from core.api.core_facade import ActionStore, VersionedOntologyStore
        store = ActionStore()
        await store.initialize()
        proposal = await store.get_ontology_proposal(proposal_id)
        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        domain_id = proposal.get("domain_id", "lock-service")
        vstore = VersionedOntologyStore(domain_id)
        receipt = await vstore.apply_proposal(proposal_id)
        if not receipt.get("ok"):
            raise HTTPException(
                status_code=400,
                detail=receipt.get("reason") or "apply failed",
            )
        return {"status": "applied", **receipt}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])
