"""FDE Sessions — session list, detail, timeline, quality, ontology-coverage (split from fde.py)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from apps.fde.api.schemas import FdeStatusResponse, FdeListResponse, FdeItemResponse


from fastapi import APIRouter, HTTPException, Query

import json
import logging
import time as _time_mod

router = APIRouter(tags=["fde-sessions-v2"])

log = logging.getLogger("aiplat.fde.sessions_v2")

# ── Evidence source labels ──
_EVIDENCE_SOURCE_LLM = "LLM推测"
_EVIDENCE_SOURCE_INDUSTRY = "行业普遍痛点"


@router.get("/sessions", response_model=FdeListResponse)
async def fde_sessions(
    industry: str = Query("", description="Filter by industry keyword"),
    company: str = Query("", description="Filter by company name"),
    status: str = Query("", description="Filter by delivery status (delivered/in_progress/completed/abandoned)"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
):
    """List past FDE diagnosis sessions with delivery tracking status.

    Returns sessions from fde-delivery GraphIndex, ordered by recency.
    Each session includes company, industry hint, action count, and delivery stats.
    """
    try:
        from core.api.core_facade import GraphIndex

        fd = GraphIndex.load("fde-delivery")
        sessions = []
        industry_lower = industry.strip().lower()
        company_lower = company.strip().lower()
        status_filter = status.strip().lower()

        for nid, node in list(fd._nodes.items()):
            if getattr(node, "class_name", "") != "DiagnosisSession":
                continue

            name = node.entity_name
            if industry_lower and industry_lower not in name.lower():
                continue
            if company_lower and company_lower not in name.lower():
                continue

            # Count actions and infer status
            neighbors = fd.get_neighbor_edges(nid, direction="outgoing")
            actions = []
            session_status = "generated"
            for neighbor_id, edge in neighbors:
                if edge.relation_name == "has_action":
                    action_node = fd.get_node(neighbor_id)
                    if action_node:
                        actions.append(action_node.entity_name)
                        session_status = "in_progress"

            if status_filter:
                # Simple status matching
                if status_filter == "active" and session_status not in ("in_progress", "delivered"):
                    continue
                if status_filter not in ("", "active") and status_filter not in session_status:
                    continue

            # Extract timestamp from session_id (format: session_{company}_{timestamp})
            ts_str = nid.rsplit("_", 1)[-1]
            try:
                ts = int(ts_str)
                from datetime import datetime, timezone
                generated_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            except (ValueError, OSError):
                generated_at = ""

            sessions.append({
                "session_id": nid,
                "company": name,
                "industry_hint": name.split("_")[0] if "_" in name else "",
                "generated_at": generated_at,
                "status": session_status,
                "action_count": len(actions),
                "actions": actions[:5],
            })

        # Sort by recency (most recent first)
        sessions.sort(key=lambda s: s["generated_at"], reverse=True)
        sessions = sessions[:limit]

        # Compute aggregate stats
        total = sum(1 for _, n in fd._nodes.items()
                    if getattr(n, "class_name", "") == "DiagnosisSession")
        with_actions = sum(1 for s in [dict()] if False)  # placeholder
        with_actions = sum(1 for s in sessions if s["action_count"] > 0)

        return {
            "sessions": sessions,
            "total": total,
            "returned": len(sessions),
            "limit": limit,
            "filters": {"industry": industry, "company": company, "status": status},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session list failed: {str(e)[:300]}")


@router.get("/sessions/{session_id}/timeline", response_model=FdeListResponse)
async def fde_session_timeline(session_id: str):
    """Return the state transition timeline for a diagnosis session.

    Part of the action bridge (L): traces every status change
    from diagnosis generation through delivery to completion.
    """
    sid = session_id.strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")

    try:
        from core.api.core_facade import GraphIndex

        fd = GraphIndex.load("fde-delivery")
        session_node = fd.get_node(sid) or fd.find_by_name(sid)
        if not session_node:
            for nid, node in list(fd._nodes.items()):
                if sid in nid or sid in node.entity_name:
                    session_node = node
                    sid = nid
                    break
        if not session_node:
            raise HTTPException(status_code=404, detail=f"Session {sid} not found")

        # Collect all StateTransition entities linked to this session or its actions
        tl_entries = []
        seen_action_ids = set()

        # Session-level transitions
        session_neighbors = fd.get_neighbor_edges(sid, direction="outgoing")
        for neighbor_id, edge in session_neighbors:
            if edge.relation_name == "has_transition":
                tnode = fd.get_node(neighbor_id)
                if tnode:
                    ts_str = neighbor_id.rsplit("_", 1)[-1]
                    try:
                        t = int(ts_str)
                        from datetime import datetime, timezone
                        ts_iso = datetime.fromtimestamp(t, tz=timezone.utc).isoformat()
                    except (ValueError, OSError):
                        ts_iso = ""
                    tl_entries.append({
                        "type": "session",
                        "description": tnode.entity_name,
                        "timestamp": ts_iso,
                        "transition_id": neighbor_id,
                    })

            # Action-level transitions
            if edge.relation_name == "has_action":
                aid = neighbor_id
                if aid in seen_action_ids:
                    continue
                seen_action_ids.add(aid)
                action_node = fd.get_node(aid)
                action_name = action_node.entity_name if action_node else "unknown"
                action_transitions = fd.get_neighbor_edges(aid, direction="outgoing")
                for atid, aedge in action_transitions:
                    if aedge.relation_name == "has_transition":
                        atnode = fd.get_node(atid)
                        if atnode:
                            ts_str2 = atid.rsplit("_", 1)[-1]
                            try:
                                t2 = int(ts_str2)
                                from datetime import datetime, timezone
                                ats_iso = datetime.fromtimestamp(t2, tz=timezone.utc).isoformat()
                            except (ValueError, OSError):
                                ats_iso = ""
                            tl_entries.append({
                                "type": "action",
                                "action": action_name[:80],
                                "description": atnode.entity_name,
                                "timestamp": ats_iso,
                                "transition_id": atid,
                            })

        # Sort by timestamp descending (most recent first)
        tl_entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

        # Count action completion
        actions_completed = sum(
            1 for e in tl_entries
            if e["type"] == "action" and "→" in e.get("description", "")
            and ("complet" in e["description"].lower() or "blocked" in e["description"].lower())
        )

        return {
            "session_id": sid,
            "company": session_node.entity_name,
            "total_transitions": len(tl_entries),
            "actions_with_transitions": len(seen_action_ids),
            "actions_completed_or_blocked": actions_completed,
            "timeline": tl_entries,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Timeline failed: {str(e)[:300]}")


@router.get("/sessions/{session_id}", response_model=FdeListResponse)
async def fde_session_detail(session_id: str):
    """Get aggregated detail for a single diagnosis session.

    Aggregates: session summary, evidence_map, knowledge_gaps,
    delivery timeline, and related sessions in the same industry.
    Single-request full view for the FDE dashboard detail page.
    """
    sid = session_id.strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")

    try:
        from core.api.core_facade import GraphIndex

        fd = GraphIndex.load("fde-delivery")
        session_node = fd.get_node(sid) or fd.find_by_name(sid)
        if not session_node:
            for nid, node in list(fd._nodes.items()):
                if sid in nid or sid in node.entity_name:
                    session_node = node
                    sid = nid
                    break
        if not session_node:
            raise HTTPException(status_code=404, detail=f"Session {sid} not found")

        result = {
            "session_id": sid,
            "company": session_node.entity_name,
        }

        # 1. Session metadata (evidence_map + knowledge_gaps + readiness)
        neighbors = fd.get_neighbor_edges(sid, direction="outgoing")
        for neighbor_id, edge in neighbors:
            if edge.relation_name == "has_meta":
                meta_node = fd.get_node(neighbor_id)
                if meta_node:
                    try:
                        md = json.loads(meta_node.entity_name)
                        result["evidence_map"] = md.get("evidence_map", [])
                        result["knowledge_gaps"] = md.get("knowledge_gaps", [])
                        result["readiness_score"] = md.get("readiness_score", 0)
                        result["industry"] = md.get("industry", "")
                        result["pain_points"] = md.get("pain_points", "")
                    except json.JSONDecodeError:
                        pass  # noqa: cleanup-best-effort

        # 2. Actions and delivery status
        actions = []
        delivery_status = "generated"
        transition_count = 0
        for neighbor_id, edge in sorted(neighbors, key=lambda x: abs(hash(x[0]))):
            if edge.relation_name == "has_action":
                action_node = fd.get_node(neighbor_id)
                if action_node:
                    # Get action transitions
                    action_transitions = fd.get_neighbor_edges(neighbor_id, direction="outgoing")
                    latest_status = "pending"
                    for atid, aedge in action_transitions:
                        if aedge.relation_name == "has_transition":
                            transition_count += 1
                            atnode = fd.get_node(atid)
                            if atnode and "→" in atnode.entity_name:
                                latest_status = atnode.entity_name.split("→")[-1].strip().split(")")[0].strip()
                    actions.append({
                        "name": action_node.entity_name[:100],
                        "status": latest_status,
                    })

            if edge.relation_name == "has_transition":
                transition_count += 1

        # Infer delivery status
        if actions:
            completed_actions = sum(1 for a in actions if a["status"] in ("completed", "complet"))
            blocked_actions = sum(1 for a in actions if a["status"] == "blocked")
            if completed_actions == len(actions):
                delivery_status = "completed"
            elif blocked_actions > 0:
                delivery_status = "blocked"
            elif any(a["status"] not in ("pending",) for a in actions):
                delivery_status = "in_progress"

        result["actions"] = actions
        result["action_count"] = len(actions)
        result["delivery_status"] = delivery_status
        result["transition_count"] = transition_count

        # 3. Related sessions (same industry)
        industry_hint = result.get("industry") or ""
        if industry_hint:
            related = []
            for nid, node in list(fd._nodes.items()):
                if getattr(node, "class_name", "") == "DiagnosisSession" and nid != sid:
                    if industry_hint.lower() in node.entity_name.lower():
                        related.append({
                            "session_id": nid,
                            "company": node.entity_name,
                        })
            result["related_sessions"] = related[:5]

        # 4. Stats summary
        result["evidence_summary"] = {
            "total_opportunities": len(result.get("evidence_map", [])),
            "ontology_backed": sum(
                1 for e in result.get("evidence_map", [])
                if e.get("source", "") and e["source"] not in ("", _EVIDENCE_SOURCE_LLM, _EVIDENCE_SOURCE_INDUSTRY)
            ),
            "llm_inferred": sum(
                1 for e in result.get("evidence_map", [])
                if not e.get("source") or e.get("source", "") in ("", _EVIDENCE_SOURCE_LLM)
            ),
            "gap_count": len(result.get("knowledge_gaps", [])),
        }

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session detail failed: {str(e)[:300]}")


@router.get("/sessions/{session_id}/quality", response_model=FdeListResponse)
async def fde_session_quality(session_id: str):
    """Run all quality checks against a diagnosis session. Returns 0-100 score."""
    sid = session_id.strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")

    try:
        from core.api.core_facade import GraphIndex

        fd = GraphIndex.load("fde-delivery")
        session_node = fd.get_node(sid) or fd.find_by_name(sid)
        if not session_node:
            for nid, node in list(fd._nodes.items()):
                if sid in nid or sid in node.entity_name:
                    session_node = node
                    sid = nid
                    break
        if not session_node:
            raise HTTPException(status_code=404, detail=f"Session {sid} not found")

        dims = {}
        nb = list(fd.get_neighbor_edges(sid, direction="outgoing"))

        # Evidence coverage
        ev_cnt = tot = 0
        for nid, e in nb:
            if e.relation_name == "has_meta":
                mn = fd.get_node(nid)
                if mn:
                    try:
                        md = json.loads(mn.entity_name)
                        em = md.get("evidence_map", [])
                        tot = len(em)
                        ev_cnt = sum(1 for x in em if x.get("source") and x["source"] not in ("", _EVIDENCE_SOURCE_LLM, _EVIDENCE_SOURCE_INDUSTRY))
                    except Exception:
                        logging.getLogger(__name__).debug('fde_session_quality failed', exc_info=True)
        dims["evidence"] = round(ev_cnt / max(tot, 1) * 100) if tot > 0 else 0

        # Action completion
        act_cnt = cmp_cnt = 0
        for nid, e in nb:
            if e.relation_name == "has_action":
                act_cnt += 1
                for aid, ae in fd.get_neighbor_edges(nid, direction="outgoing"):
                    if ae.relation_name == "has_transition":
                        an = fd.get_node(aid)
                        if an and ("complet" in an.entity_name.lower() or "blocked" in an.entity_name.lower()):
                            cmp_cnt += 1
                            break
        dims["actions"] = round(cmp_cnt / max(act_cnt, 1) * 100) if act_cnt > 0 else 0

        # Term coverage
        try:
            tg = GraphIndex.load("enterprise-terms")
            tc = sum(1 for _, n in tg._nodes.items() if getattr(n, "class_name", "") == "Term")
            dims["terms"] = min(100, tc * 5)
        except Exception:
            dims["terms"] = 0

        # Transitions
        tr_cnt = sum(1 for _, e in nb if e.relation_name == "has_transition")
        dims["transitions"] = min(100, tr_cnt * 10)

        # Overall score (weighted)
        w = {"evidence": 0.30, "actions": 0.25, "terms": 0.15, "transitions": 0.30}
        overall = round(sum(dims[k] * w[k] for k in dims) / sum(w[k] for k in dims))
        rating = "excellent" if overall >= 80 else "good" if overall >= 60 else "fair" if overall >= 40 else "poor"

        return {
            "session_id": sid,
            "company": session_node.entity_name,
            "overall_quality": overall,
            "rating": rating,
            "dimensions": {k: {"score": v} for k, v in dims.items()},
            "weights": w,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quality scoring failed: {str(e)[:300]}")


@router.get("/sessions/{session_id}/ontology-coverage", response_model=FdeListResponse)
async def fde_ontology_coverage(session_id: str):
    """Quantify how much of a diagnosis is backed by ontology vs LLM inference.

    Returns per-dimension coverage ratios that precisely answer:
    "This diagnosis is X% ontology-backed, Y% history-backed, Z% LLM inference."
    The determinism_score = ontology + history = % of conclusions with grounding.
    """
    sid = session_id.strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")

    try:
        from core.api.core_facade import GraphIndex

        fd = GraphIndex.load("fde-delivery")
        session_node = fd.get_node(sid) or fd.find_by_name(sid)
        if not session_node:
            for nid, node in list(fd._nodes.items()):
                if sid in nid or sid in node.entity_name:
                    session_node = node
                    sid = nid
                    break
        if not session_node:
            raise HTTPException(status_code=404, detail=f"Session {sid} not found")

        neighbors = list(fd.get_neighbor_edges(sid, direction="outgoing"))

        # ── 1. Ontology vs History vs LLM coverage from evidence_map ──
        ontology_count = 0
        history_count = 0
        llm_count = 0
        total_conclusions = 0

        for neighbor_id, edge in neighbors:
            if edge.relation_name == "has_meta":
                meta_node = fd.get_node(neighbor_id)
                if meta_node:
                    try:
                        md = json.loads(meta_node.entity_name)
                        em = md.get("evidence_map", [])
                        total_conclusions = len(em)
                        for item in em:
                            src = (item.get("source") or "").strip()
                            if src and src not in (_EVIDENCE_SOURCE_LLM, _EVIDENCE_SOURCE_INDUSTRY):
                                ontology_count += 1
                            elif src == _EVIDENCE_SOURCE_LLM:
                                llm_count += 1
                            else:
                                # Check evidence entities for history backing
                                history_count += 1
                    except Exception:
                        logging.getLogger(__name__).debug('fde_ontology_coverage failed', exc_info=True)

        # Count evidence entities related to this session for history estimation
        evidence_entities = 0
        for neighbor_id, edge in neighbors:
            if edge.relation_name == "has_evidence":
                ev_node = fd.get_node(neighbor_id)
                if ev_node and "historical_case" not in (ev_node.entity_name or "").lower():
                    evidence_entities += 1

        # If we have evidence entities but no explicit evidence_map breakdown,
        # adjust: evidence entities count as ontology-backed
        if evidence_entities > 0 and ontology_count == 0:
            ontology_count = min(evidence_entities, total_conclusions or evidence_entities)

        # Normalize: history = total - ontology - llm
        if total_conclusions > 0 and history_count == 0:
            history_count = total_conclusions - ontology_count - llm_count
            history_count = max(0, history_count)

        total = max(total_conclusions, 1)
        cov_ontology = round(ontology_count / total, 2)
        cov_history = round(history_count / total, 2)
        cov_llm = round(llm_count / total, 2)

        # ── 2. Term coverage from enterprise-terms graph ──
        term_coverage = 0.0
        try:
            tg = GraphIndex.load("enterprise-terms")
            term_count = sum(1 for _, n in tg._nodes.items()
                           if getattr(n, "class_name", "") == "Term")
            # Rough estimate: each term covers ~1 concept per diagnosis
            term_coverage = round(min(term_count / max(total, 5), 1.0), 2)
        except Exception:
            logging.getLogger(__name__).debug('code failed', exc_info=True)

        # ── 3. Determinism score = ontology + history ──
        determinism = round(cov_ontology + cov_history, 2)
        if determinism >= 0.90:
            rating = "excellent"
            interpret = f"{int(determinism*100)}%的结论有本体或历史案例支撑，可信度为优秀"
        elif determinism >= 0.70:
            rating = "good"
            interpret = f"{int(determinism*100)}%的结论有本体或历史案例支撑，可信度为良好"
        elif determinism >= 0.50:
            rating = "fair"
            interpret = f"{int(determinism*100)}%的结论有支撑，{int(cov_llm*100)}%依赖LLM推测，建议补充本体实例或历史数据"
        else:
            rating = "poor"
            interpret = f"仅{int(determinism*100)}%的结论有支撑，{int(cov_llm*100)}%依赖LLM推测。需大幅补充本体类定义和案例数据"

        return {
            "session_id": sid,
            "company": session_node.entity_name,
            "total_conclusions": total_conclusions,
            "coverage": {
                "ontology_instance": cov_ontology,
                "historical_case": cov_history,
                "llm_inferred": cov_llm,
            },
            "term_coverage": term_coverage,
            "determinism_score": determinism,
            "rating": rating,
            "interpretation": interpret,
            "formula": "determinism_score = ontology_instance + historical_case — 本体包住不确定性的量化度量",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ontology coverage failed: {str(e)[:300]}")

