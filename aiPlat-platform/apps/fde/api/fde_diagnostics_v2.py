"""FDE — Trend Analysis, Search, Alerts, Capabilities."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Any, Dict, List
from apps.fde.schemas import FdeStatusResponse, FdeListResponse, FdeItemResponse


from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["fde-diagnostics-v2"])

_EVIDENCE_SOURCE_LLM = "LLM推测"
_EVIDENCE_SOURCE_INDUSTRY = "行业普遍痛点"


# ════════════════════════════════════════════════════════════
# T: FDE Trend Analysis — time-series growth and health metrics
# ════════════════════════════════════════════════════════════

@router.get("/trends", response_model=FdeItemResponse)
async def fde_trends(
    months: int = Query(6, ge=1, le=24, description="Months of history to analyze"),
    bucket: str = Query("month", description="Time bucket: week | month"),
):
    """Time-series trend analysis across all FDE diagnosis sessions.

    Returns per-bucket: session count, delivery rate, top actions,
    term dictionary growth, and readiness score distribution.
    """
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex

        fd = GraphIndex.load("fde-delivery")
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=months * 30)

        # ── Collect session data with timestamps ──
        sessions_by_bucket = defaultdict(lambda: {
            "sessions": 0, "actions": 0, "n_unique_actions": 0, "names": [],
            "readiness_scores": [],
        })
        all_sessions = []

        for nid, node in list(fd._nodes.items()):
            if getattr(node, "class_name", "") != "DiagnosisSession":
                continue

            # Extract timestamp from session_id
            ts_str = nid.rsplit("_", 1)[-1]
            try:
                ts = int(ts_str)
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            except (ValueError, OSError):
                continue

            if dt < cutoff:
                continue

            # Determine bucket key
            if bucket == "week":
                week_start = dt - timedelta(days=dt.weekday())
                bucket_key = week_start.strftime("%Y-W%W")
            else:
                bucket_key = dt.strftime("%Y-%m")

            neighbors = fd.get_neighbor_edges(nid, direction="outgoing")
            has_action = False
            action_count = 0
            for neighbor_id, edge in neighbors:
                if edge.relation_name == "has_action":
                    has_action = True
                    action_count += 1

            # Check SessionMeta for readiness
            readiness = 0
            for neighbor_id, edge in neighbors:
                if edge.relation_name == "has_meta":
                    meta_node = fd.get_node(neighbor_id)
                    if meta_node:
                        try:
                            md = json.loads(meta_node.entity_name)
                            readiness = md.get("readiness_score", 0)
                        except Exception:
                            pass

            sessions_by_bucket[bucket_key]["sessions"] += 1
            if has_action:
                sessions_by_bucket[bucket_key]["actions"] += action_count
            sessions_by_bucket[bucket_key]["names"].append(node.entity_name[:30])
            if readiness:
                sessions_by_bucket[bucket_key]["readiness_scores"].append(readiness)

        # ── Build time series ──
        trends = []
        for bk in sorted(sessions_by_bucket.keys()):
            d = sessions_by_bucket[bk]
            total = d["sessions"]
            with_actions = d["actions"]
            avg_readiness = (
                round(sum(d["readiness_scores"]) / len(d["readiness_scores"]))
                if d["readiness_scores"] else 0
            )
            trends.append({
                "bucket": bk,
                "sessions": total,
                "actions": with_actions,
                "delivery_rate": round(with_actions / max(total, 1) * 100),
                "avg_readiness": avg_readiness,
            })

        # ── Term dictionary growth trend ──
        term_trends = []
        try:
            tg = GraphIndex.load("enterprise-terms")
            term_buckets = defaultdict(int)
            for nid, node in list(tg._nodes.items()):
                if getattr(node, "class_name", "") != "Term":
                    continue
                ts_str = nid.rsplit("_", 1)[-1]
                try:
                    ts = int(ts_str)
                except ValueError:
                    continue
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                if dt < cutoff:
                    continue
                bk = dt.strftime("%Y-%m") if bucket == "month" else ""
                if bk:
                    term_buckets[bk] += 1

            cumulative = 0
            for bk in sorted(term_buckets.keys()):
                cumulative += term_buckets[bk]
                term_trends.append({"bucket": bk, "new_terms": term_buckets[bk], "cumulative": cumulative})
        except Exception:
            pass

        # ── District distribution ──
        industries = defaultdict(int)
        for nid, node in list(fd._nodes.items()):
            if getattr(node, "class_name", "") == "DiagnosisSession":
                parts = node.entity_name.split("_", 1)
                if parts:
                    industries[parts[0][:15]] += 1

        return {
            "period": f"Last {months} months",
            "bucket": bucket,
            "trends": trends,
            "term_growth": term_trends,
            "total_sessions_in_period": sum(d["sessions"] for d in sessions_by_bucket.values()),
            "industry_distribution": dict(
                sorted(industries.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trends failed: {str(e)[:300]}")


# ════════════════════════════════════════════════════════════
# U: FDE Unified Search — cross-entity text search
# ════════════════════════════════════════════════════════════

@router.get("/search", response_model=FdeItemResponse)
async def fde_search(
    q: str = Query("", description="Search query across sessions/actions/terms/evidence"),
    scope: str = Query("all", description="Search scope: all | sessions | actions | terms | evidence | industries"),
    limit: int = Query(20, ge=1, le=100),
):
    """Search across all FDE data entities with a single text query.

    Returns matches ranked by relevance (substring match weighted by entity type).
    Each result includes entity type, name, matched text excerpt, and context.
    """
    query = q.strip().lower()
    if not query:
        return {"query": "", "results": [], "total": 0}

    results = []
    seen = set()

    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        import time as _time_us

        # ── 1. Search fde-delivery sessions ──
        if scope in ("all", "sessions"):
            fd = GraphIndex.load("fde-delivery")
            for nid, node in list(fd._nodes.items()):
                cls = getattr(node, "class_name", "")
                name = node.entity_name.lower()
                if query in name and (nid, "session") not in seen:
                    seen.add((nid, "session"))
                    # Extract timestamp
                    ts_str = nid.rsplit("_", 1)[-1]
                    try:
                        ts = int(ts_str)
                    except ValueError:
                        ts = 0
                    results.append({
                        "type": cls if cls else "session",
                        "name": node.entity_name[:100],
                        "id": nid,
                        "score": _score_match(name, query, 10),
                        "ts": ts,
                    })

        # ── 2. Search actions ──
        if scope in ("all", "actions"):
            for nid, node in list(fd._nodes.items()):
                cls = getattr(node, "class_name", "")
                if cls != "DeliveryAction":
                    continue
                name = node.entity_name.lower()
                if query in name and (nid, "action") not in seen:
                    seen.add((nid, "action"))
                    results.append({
                        "type": "action",
                        "name": node.entity_name[:100],
                        "id": nid,
                        "score": _score_match(name, query, 8),
                        "ts": 0,
                    })

        # ── 3. Search enterprise-terms ──
        if scope in ("all", "terms"):
            try:
                tg = GraphIndex.load("enterprise-terms")
                for nid, node in list(tg._nodes.items()):
                    name = node.entity_name.lower()
                    if query in name and (nid, "term") not in seen:
                        seen.add((nid, "term"))
                        results.append({
                            "type": "term",
                            "name": node.entity_name[:100],
                            "id": nid,
                            "score": _score_match(name, query, 7),
                            "ts": 0,
                        })
            except Exception:
                pass

        # ── 4. Search evidence ──
        if scope in ("all", "evidence"):
            for nid, node in list(fd._nodes.items()):
                if getattr(node, "class_name", "") != "Evidence":
                    continue
                name = node.entity_name.lower()
                if query in name and (nid, "evidence") not in seen:
                    seen.add((nid, "evidence"))
                    results.append({
                        "type": "evidence",
                        "name": node.entity_name[:100],
                        "id": nid,
                        "score": _score_match(name, query, 5),
                        "ts": 0,
                    })

        # ── 5. Search industries ──
        if scope in ("all", "industries"):
            industries_found = set()
            for nid, node in list(fd._nodes.items()):
                if getattr(node, "class_name", "") != "DiagnosisSession":
                    continue
                parts = node.entity_name.split("_", 1)
                if parts and query in parts[0].lower() and parts[0] not in industries_found:
                    industries_found.add(parts[0])
                    results.append({
                        "type": "industry",
                        "name": parts[0][:100],
                        "id": parts[0],
                        "score": _score_match(parts[0].lower(), query, 6),
                        "ts": 0,
                    })

        # Sort by score descending, then by timestamp descending
        results.sort(key=lambda r: (r["score"], r.get("ts", 0)), reverse=True)
        results = results[:limit]

        return {
            "query": q.strip(),
            "results": results,
            "total": len(results),
            "scope": scope,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)[:300]}")


def _score_match(text: str, query: str, base: int) -> int:
    """Simple relevance scoring: exact match > word match > substring match."""
    if text == query:
        return base * 3
    if f" {query} " in f" {text} ":
        return base * 2
    return base


# ════════════════════════════════════════════════════════════
# W: FDE Alerts — proactive attention-needed detection
# ════════════════════════════════════════════════════════════

@router.get("/alerts", response_model=FdeItemResponse)
async def fde_alerts(
    min_severity: str = Query("warning", description="Minimum alert level: info | warning | error"),
):
    """Scan all sessions and return ones needing attention.

    Alert types:
      - blocked: actions in blocked status
      - stale: no transitions in 30+ days and not completed
      - low_quality: overall quality < 40
      - zero_evidence: no ontology-backed conclusions
      - high_gaps: > 3 unbacked concepts
    """
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex

        fd = GraphIndex.load("fde-delivery")
        now = datetime.now(timezone.utc)
        stale_cutoff = now - timedelta(days=30)

        alerts = []
        for nid, node in list(fd._nodes.items()):
            if getattr(node, "class_name", "") != "DiagnosisSession":
                continue

            session_alerts = []
            neighbors = list(fd.get_neighbor_edges(nid, direction="outgoing"))

            # Check for blocked actions
            for neighbor_id, edge in neighbors:
                if edge.relation_name == "has_action":
                    atrans = fd.get_neighbor_edges(neighbor_id, direction="outgoing")
                    for atid, ae in atrans:
                        if ae.relation_name == "has_transition":
                            atnode = fd.get_node(atid)
                            if atnode and "blocked" in atnode.entity_name.lower():
                                an = fd.get_node(neighbor_id)
                                session_alerts.append({
                                    "type": "blocked",
                                    "severity": "error",
                                    "detail": f"Action blocked: {(an.entity_name if an else neighbor_id)[:80]}",
                                })

            # Check for stale sessions
            ts_str = nid.rsplit("_", 1)[-1]
            try:
                ts = int(ts_str)
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                has_recent = any(
                    e.relation_name == "has_transition" for _, e in neighbors
                )
                if dt < stale_cutoff and not has_recent:
                    session_alerts.append({
                        "type": "stale",
                        "severity": "warning",
                        "detail": f"No activity since {dt.strftime('%Y-%m-%d')} ({(now - dt).days}d)",
                    })
            except (ValueError, OSError):
                pass

            # Check for low evidence
            for neighbor_id, edge in neighbors:
                if edge.relation_name == "has_meta":
                    mn = fd.get_node(neighbor_id)
                    if mn:
                        try:
                            md = json.loads(mn.entity_name)
                            em = md.get("evidence_map", [])
                            ev = sum(1 for x in em if x.get("source") and x["source"] not in ("", _EVIDENCE_SOURCE_LLM, _EVIDENCE_SOURCE_INDUSTRY))
                            kg = len(md.get("knowledge_gaps", []))
                            if em and ev == 0:
                                session_alerts.append({
                                    "type": "zero_evidence",
                                    "severity": "error",
                                    "detail": f"No ontology-backed conclusions ({len(em)} total)",
                                })
                            if kg > 3:
                                session_alerts.append({
                                    "type": "high_gaps",
                                    "severity": "warning",
                                    "detail": f"{kg} unbacked concepts",
                                })
                        except Exception:
                            pass

            if session_alerts:
                severity_order = {"error": 0, "warning": 1, "info": 2}
                min_sev = severity_order.get(min_severity, 1)
                session_alerts = [a for a in session_alerts if severity_order.get(a["severity"], 2) <= min_sev]
                if session_alerts:
                    alerts.append({
                        "session_id": nid,
                        "company": node.entity_name,
                        "alert_count": len(session_alerts),
                        "alerts": session_alerts,
                    })

        # Sort by severity (errors first, then warning, then info)
        alerts.sort(key=lambda a: (
            0 if any(x["severity"] == "error" for x in a["alerts"]) else
            1 if any(x["severity"] == "warning" for x in a["alerts"]) else 2,
            -a["alert_count"]
        ))

        error_count = sum(1 for a in alerts if any(x["severity"] == "error" for x in a["alerts"]))
        warning_count = sum(1 for a in alerts if not any(x["severity"] == "error" for x in a["alerts"]) and any(x["severity"] == "warning" for x in a["alerts"]))

        return {
            "total_alerts": len(alerts),
            "errors": error_count,
            "warnings": warning_count,
            "critical_sessions": len(alerts),
            "alerts": alerts[:30],
            "min_severity": min_severity,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Alerts failed: {str(e)[:300]}")


# ════════════════════════════════════════════════════════════
# Z: Self-describing capabilities — open platform manifesto
# ════════════════════════════════════════════════════════════

@router.get("/capabilities", response_model=FdeItemResponse)
async def fde_capabilities():
    """Return a structured catalog of all FDE system capabilities.

    Organized by layer: data, ontology, analysis, interaction, governance.
    This is the system's self-description — the "open platform" endpoint (Z).
    """
    return {
        "system": "FDE (Field Deployment Engineer) — AI-Powered Diagnosis Platform",
        "paradigm": "Enterprise Brain Prototype — ontology-driven, decision-capable, action-closed",
        "layers": {
            "data_ingestion": {
                "description": "Cross-system data bridging and knowledge ingestion",
                "capabilities": [
                    {"name": "ingest", "endpoint": "POST /fde/ingest", "label": "跨系统数据桥接", "maturity": "alpha"},
                    {"name": "kb_ingest", "skill": "knowledge_ingest", "label": "多模态文档入库", "maturity": "production"},
                    {"name": "datasource", "module": "data_source.py", "label": "SQL/API/File连接器", "maturity": "production"},
                ],
            },
            "ontology_engine": {
                "description": "Domain ontology modeling, graph construction, semantic reasoning",
                "capabilities": [
                    {"name": "domain_yaml", "endpoint": "~/.aiplat/ontologies/", "label": "7域YAML本体引擎", "maturity": "production"},
                    {"name": "domain_router", "module": "domain_router.py", "label": "3层域路由器", "maturity": "production"},
                    {"name": "graph_index", "module": "graph_index.py", "label": "实体+关系+超边图索引", "maturity": "production"},
                    {"name": "graph_inference", "module": "graph_inference.py", "label": "YAML推理规则引擎", "maturity": "production"},
                    {"name": "state_machine", "module": "state_machine.py", "label": "状态转换引擎", "maturity": "production"},
                    {"name": "entity_resolver", "module": "entity_resolver.py", "label": "实体消歧+归一化", "maturity": "production"},
                    {"name": "cross_domain", "module": "ontology_query_mapper.py", "label": "跨域语义类比", "maturity": "production"},
                    {"name": "relation_constraints", "module": "graph_index.py", "label": "关系domain/range校验", "maturity": "production"},
                    {"name": "term_dictionary", "module": "enterprise-terms.yaml", "label": "企业术语字典", "maturity": "beta"},
                ],
            },
            "diagnosis_engine": {
                "description": "AI diagnosis report generation with full ontology backing",
                "capabilities": [
                    {"name": "field_assessment", "skill": "field-assessment", "label": "8节结构诊断报告", "maturity": "production"},
                    {"name": "evidence_annotation", "module": "registry.py (P0)", "label": "三级证据等级标注", "maturity": "production"},
                    {"name": "consistency_gate", "module": "consistency_gate.py", "label": "跨阶段一致性门控", "maturity": "production"},
                    {"name": "self_optimization", "module": "registry.py (E)", "label": "历史驱动自优化", "maturity": "production"},
                    {"name": "multi_role_simulation", "module": "registry.py (F)", "label": "CIO/Dev/User三角色仿真", "maturity": "production"},
                    {"name": "digital_employee", "module": "registry.py (Y)", "label": "数字员工角色匹配", "maturity": "production"},
                    {"name": "knowledge_gaps", "module": "registry.py (G)", "label": "知识缺口检测", "maturity": "production"},
                    {"name": "term_seeding", "module": "registry.py (S)", "label": "术语自播种", "maturity": "production"},
                ],
            },
            "delivery_loop": {
                "description": "Diagnosis → Delivery → Feedback → Re-optimization closed loop",
                "capabilities": [
                    {"name": "delivery_tracking", "endpoint": "fde-delivery GraphIndex", "label": "交付跟踪本体", "maturity": "production"},
                    {"name": "timeline", "endpoint": "GET /fde/sessions/{id}/timeline", "label": "状态变迁时间线", "maturity": "production"},
                    {"name": "feedback", "endpoint": "POST /fde/delivery/feedback", "label": "交付反馈API", "maturity": "production"},
                    {"name": "evidence_entity", "endpoint": "Evidence节点", "label": "证据一等实体绑定", "maturity": "production"},
                    {"name": "quality_scoring", "endpoint": "GET /fde/sessions/{id}/quality", "label": "4维质量评分", "maturity": "production"},
                    {"name": "action_bridge", "endpoint": "StateTransition实体", "label": "动作闭环(状态变更记录)", "maturity": "production"},
                ],
            },
            "analytics": {
                "description": "Aggregation, trend analysis, benchmarking, proactive monitoring",
                "capabilities": [
                    {"name": "sessions", "endpoint": "GET /fde/sessions", "label": "历史诊断列表", "maturity": "production"},
                    {"name": "session_detail", "endpoint": "GET /fde/sessions/{id}", "label": "聚合详情视图", "maturity": "production"},
                    {"name": "benchmark", "endpoint": "GET /fde/benchmark", "label": "行业基准分析", "maturity": "production"},
                    {"name": "trends", "endpoint": "GET /fde/trends", "label": "时间序列趋势", "maturity": "production"},
                    {"name": "search", "endpoint": "GET /fde/search", "label": "统一全文检索", "maturity": "production"},
                    {"name": "alerts", "endpoint": "GET /fde/alerts", "label": "主动告警检测", "maturity": "production"},
                ],
            },
            "interaction": {
                "description": "User-facing interaction channels",
                "capabilities": [
                    {"name": "ask", "endpoint": "POST /fde/ask", "label": "追问端点", "maturity": "production"},
                    {"name": "health", "endpoint": "GET /fde/health", "label": "5维健康检查", "maturity": "production"},
                    {"name": "validate", "endpoint": "GET /fde/validate", "label": "8项E2E连通测试", "maturity": "production"},
                ],
            },
        },
        "totals": {
            "endpoints": 12,
            "domains": 7,
            "ontology_classes": 25,
            "maturity_summary": {"production": 28, "beta": 1, "alpha": 1},
            "philosophy": "从LLM记忆 → 本体驱动 → 交付闭环 → 自优化 → 数字员工 — 企业大脑原型",
        },
    }
