"""
Built-in action handlers — callable functions for registered actions.

Signature convention: async def handler(entity: dict, params: dict, actor: str = "") -> dict
Return: {"new_state": str, ...additional fields}
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Business-domain handlers
# ═══════════════════════════════════════════════════════════

async def approve_diagnosis(entity: Dict[str, Any], params: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    """Approve a diagnosis session: transition from delivered → in_progress.

    Domain is read from entity (via action executor) or params. No hardcoded domain ID.
    """
    from core.harness.ontology_engine.graph_index import GraphIndex

    entity_id = entity.get("id") or entity.get("entity_id", "")
    domain_id = entity.get("domain_id") or params.get("domain_id", "")
    if not domain_id:
        raise ValueError("domain_id is required — pass via entity['domain_id'] or params['domain_id']")
    g = GraphIndex.load(domain_id)

    # Update entity state
    g.update_entity_property(entity_id, "state", "in_progress")
    g.update_entity_property(entity_id, "assigned_engineer", params.get("assigned_engineer", ""))
    if params.get("priority"):
        g.update_entity_property(entity_id, "priority", params["priority"])

    return {
        "new_state": "in_progress",
        "assigned_engineer": params.get("assigned_engineer"),
        "priority": params.get("priority", "medium"),
        "approved_by": actor,
    }


async def accept_order(entity: Dict[str, Any], params: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    """Accept an installation order: transition from pending → accepted.

    Domain is read from entity (via action executor) or params. No hardcoded domain ID.
    Accepts both seed schema (assigned_technician/scheduled_at) and legacy
    (technician_id/appointment_slot) param names.
    """
    from core.harness.ontology_engine.graph_index import GraphIndex

    entity_id = entity.get("id") or entity.get("entity_id", "")
    domain_id = entity.get("domain_id") or entity.get("domain") or params.get("domain_id", "")
    if not domain_id:
        raise ValueError("domain_id is required — pass via entity['domain_id'] or params['domain_id']")
    g = GraphIndex.load(domain_id)

    technician = (
        params.get("assigned_technician")
        or params.get("technician_id")
        or ""
    )
    scheduled = (
        params.get("scheduled_at")
        or params.get("appointment_slot")
        or ""
    )

    g.update_entity_property(entity_id, "state", "accepted")
    g.update_entity_property(entity_id, "technician_id", technician)
    g.update_entity_property(entity_id, "assigned_technician", technician)
    g.update_entity_property(entity_id, "appointment_slot", scheduled)
    g.update_entity_property(entity_id, "scheduled_at", scheduled)

    return {
        "new_state": "accepted",
        "technician_id": technician,
        "assigned_technician": technician,
        "appointment_slot": scheduled,
        "scheduled_at": scheduled,
        "accepted_by": actor,
    }


async def assign_work_order(entity: Dict[str, Any], params: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    """Generic work-order assign: required_state → target_state (default 已指派).

    Domain-agnostic; used by service-domain vertical (Phase 5+ copyability).
    """
    from core.harness.ontology_engine.graph_index import GraphIndex

    entity_id = entity.get("id") or entity.get("entity_id", "")
    domain_id = entity.get("domain_id") or entity.get("domain") or params.get("domain_id", "")
    if not domain_id:
        raise ValueError("domain_id is required")
    g = GraphIndex.load(domain_id)
    technician = params.get("assigned_technician") or params.get("technician_id") or ""
    new_state = params.get("target_state") or "已指派"
    g.update_entity_property(entity_id, "state", new_state)
    g.update_entity_property(entity_id, "assigned_technician", technician)
    g.update_entity_property(entity_id, "technician_id", technician)
    return {
        "new_state": new_state,
        "assigned_technician": technician,
        "assigned_by": actor,
    }


async def set_entity_state(entity: Dict[str, Any], params: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    """Domain-agnostic state transition. Caller/contract supplies target via new_state/target_state.

    Used by customer_action lifecycle seeds (assign / start / complete / triage).
    Writes evidence relations:
      assigned → assigned_to; in_progress → visited_at; completed → installed_by;
      triaging/rooted → suspects / rooted_at (it-ops alert path).
    """
    from core.harness.ontology_engine.graph_index import GraphIndex
    from datetime import datetime, timezone

    entity_id = entity.get("id") or entity.get("entity_id", "")
    domain_id = entity.get("domain_id") or entity.get("domain") or params.get("domain_id", "")
    if not domain_id:
        raise ValueError("domain_id is required")
    new_state = params.get("new_state") or params.get("target_state") or ""
    if not new_state:
        raise ValueError("new_state or target_state is required")
    g = GraphIndex.load(domain_id)
    g.update_entity_property(entity_id, "state", new_state)
    # Dual-write status for TBox required_fields that still say "status"
    g.update_entity_property(entity_id, "status", new_state)
    for key in (
        "assigned_technician",
        "technician_id",
        "completion_notes",
        "evidence_ref",
        "suspected_root",
        "root_entity_id",
        "path_note",
        "catalog_id",
    ):
        if params.get(key) is not None:
            g.update_entity_property(entity_id, key, params[key])

    tech = (
        params.get("assigned_technician")
        or params.get("technician_id")
        or params.get("installed_by")
        or ""
    )
    if tech and tech not in g._nodes:
        g.add_entity(str(tech), f"Technician {tech}", "安装师傅", source_doc_id="action-auto")

    def _rel(name: str, target: str, label: str) -> None:
        if not target:
            return
        try:
            g.add_relation(entity_id, str(target), name, relation_label=label, confidence=0.95)
        except Exception as e:
            logger.warning("%s relation failed %s→%s: %s", name, entity_id, target, e, exc_info=True)

    def _ensure_ref(nid: str, display: str, class_name: str) -> None:
        if nid and nid not in g._nodes:
            g.add_entity(str(nid), display, class_name, source_doc_id="action-auto")

    if new_state == "assigned" and tech:
        _rel("assigned_to", tech, "派单给")
    if new_state == "in_progress":
        visit_target = tech or entity_id
        if visit_target not in g._nodes and visit_target == entity_id:
            pass  # self-edge allowed if node exists
        elif visit_target not in g._nodes:
            g.add_entity(str(visit_target), f"Visit {visit_target}", "安装师傅", source_doc_id="action-auto")
        _rel("visited_at", visit_target if visit_target in g._nodes else entity_id, "到场")
        g.update_entity_property(
            entity_id, "visited_at", datetime.now(timezone.utc).isoformat()
        )
    if params.get("installed_by") or (new_state == "completed" and tech):
        _rel("installed_by", params.get("installed_by") or tech, "安装完成")

    # it-ops alert triage: suspects / rooted_at (prefer pre-seeded topology nodes)
    suspect = str(params.get("suspected_root") or "").strip()
    root_id = str(params.get("root_entity_id") or "").strip()
    if suspect:
        _ensure_ref(suspect, f"Suspect {suspect}", str(params.get("suspect_class") or "中间件"))
        _rel("suspects", suspect, "疑似根因指向")
    if root_id and new_state == "rooted":
        _ensure_ref(root_id, f"Root {root_id}", str(params.get("root_class") or "中间件"))
        _rel("rooted_at", root_id, "根因落点")

    # data-gov / catalog mount: mounts edge when cataloging
    catalog_id = str(params.get("catalog_id") or "").strip()
    if catalog_id and new_state == "cataloged":
        _ensure_ref(
            catalog_id,
            f"Catalog {catalog_id}",
            str(params.get("catalog_class") or "目录条目"),
        )
        _rel("mounts", catalog_id, "挂载目录")

    try:
        g.save()
    except Exception as e:
        logger.debug("GraphIndex.save after set_entity_state: %s", e)

    return {
        "new_state": new_state,
        "updated_by": actor,
        "suspected_root": suspect or None,
        "root_entity_id": root_id or None,
        "catalog_id": catalog_id or None,
    }


async def assert_inferred_edge(
    entity: Dict[str, Any], params: Dict[str, Any], actor: str = ""
) -> Dict[str, Any]:
    """Commit one inference suggestion into GraphIndex (authority path).

    Must be invoked via ActionRegistry — marks edge inferred=true for audit/query split.
    """
    from core.harness.ontology_engine.graph_index import GraphIndex

    domain_id = entity.get("domain_id") or entity.get("domain") or params.get("domain_id") or ""
    if not domain_id:
        raise ValueError("domain_id is required")
    source_id = str(params.get("source_id") or entity.get("id") or entity.get("entity_id") or "").strip()
    target_id = str(params.get("target_id") or "").strip()
    relation_name = str(params.get("relation_name") or params.get("rel") or "").strip()
    if not source_id or not target_id or not relation_name:
        raise ValueError("source_id, target_id, relation_name are required")

    g = GraphIndex.load(domain_id)
    if source_id not in g._nodes or target_id not in g._nodes:
        raise ValueError(f"endpoints missing: {source_id}→{target_id}")

    conf = float(params.get("confidence") or 0.7)
    rule_name = str(params.get("rule_name") or "manual_assert")
    label = str(params.get("relation_label") or relation_name)
    added = g.add_inferred_edge(
        source_id,
        target_id,
        relation_name,
        relation_label=label,
        confidence=conf,
        rule_name=rule_name,
    )
    try:
        g.save()
    except Exception as e:
        logger.debug("GraphIndex.save after assert_inferred_edge: %s", e)

    return {
        "inferred": True,
        "added": bool(added),
        "source_id": source_id,
        "target_id": target_id,
        "relation_name": relation_name,
        "rule_name": rule_name,
        "confidence": conf,
        "asserted_by": actor,
        "authority": "action_asserted",
    }


async def assert_inferred_edges(
    entity: Dict[str, Any], params: Dict[str, Any], actor: str = ""
) -> Dict[str, Any]:
    """Batch-commit inference suggestions (still one Action audit record)."""
    from core.harness.ontology_engine.graph_index import GraphIndex, GraphEdge
    from core.harness.ontology_engine.graph_inference import InferenceResult, GraphInference

    domain_id = entity.get("domain_id") or entity.get("domain") or params.get("domain_id") or ""
    if not domain_id:
        raise ValueError("domain_id is required")
    raw_edges = params.get("edges") or []
    if not isinstance(raw_edges, list) or not raw_edges:
        raise ValueError("edges list required")

    g = GraphIndex.load(domain_id)
    inf = InferenceResult()
    for raw in raw_edges:
        if not isinstance(raw, dict):
            continue
        e = GraphEdge(
            source_id=str(raw.get("source") or raw.get("source_id") or ""),
            target_id=str(raw.get("target") or raw.get("target_id") or ""),
            relation_name=str(raw.get("relation_name") or raw.get("rel") or ""),
            relation_label=str(raw.get("relation_label") or raw.get("label") or ""),
            confidence=float(raw.get("confidence") or 0.7),
        )
        e.inferred = True
        e.rule_name = str(raw.get("rule_name") or "batch_assert")
        if e.source_id and e.target_id and e.relation_name:
            inf.inferred_edges.append(e)

    class _Dom:
        inference_rules = []

    added = GraphInference(_Dom(), g).apply_to_graph(inf, via_action=True)
    try:
        g.save()
    except Exception as e:
        logger.debug("GraphIndex.save after assert_inferred_edges: %s", e)

    return {
        "inferred": True,
        "added": added,
        "requested": len(inf.inferred_edges),
        "asserted_by": actor,
        "authority": "action_asserted",
    }


# ═══════════════════════════════════════════════════════════
# Legacy bridge handlers
# ═══════════════════════════════════════════════════════════

async def webhook_forward(entity: Dict[str, Any], params: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    """Fire-and-forget HTTP POST to external system (legacy call_webhook)."""
    import aiohttp

    url = params.get("url", "")
    payload = params.get("payload", {})
    if not url:
        return {"new_state": entity.get("state", ""), "status_code": 0, "error": "No URL provided"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                logger.info("Webhook %s → %d", url, resp.status)
                return {"new_state": entity.get("state", ""), "status_code": resp.status}
    except Exception as e:
        logger.warning("Webhook %s failed: %s", url, e)
        return {"new_state": entity.get("state", ""), "status_code": 0, "error": str(e)}


# ═══════════════════════════════════════════════════════════
# BellSystem24 business handlers
# ═══════════════════════════════════════════════════════════

async def deploy_ai_agent(entity: Dict[str, Any], params: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    """Cross-domain: source entity → create target entity in another domain."""
    from core.harness.ontology_engine.graph_index import GraphIndex

    entity_id = entity.get("id") or entity.get("entity_id", "")
    agent_name = params.get("agent_name", f"{entity.get('name', 'Lab')}-AI-Agent")
    partner = params.get("development_partner", "AVILEN")

    source_domain = entity.get("domain_id") or params.get("source_domain_id", "")
    target_domain = params.get("cross_domain_id") or params.get("target_domain_id", "")

    # Update source entity status
    g_consulting = GraphIndex.load(source_domain) if source_domain else None
    if g_consulting:
        g_consulting.update_entity_property(entity_id, "state", "deployed")
        g_consulting.update_entity_property(entity_id, "last_agent_deployed", agent_name)

    # Create AI_Agent entity in target domain
    g_cloud = GraphIndex.load(target_domain) if target_domain else None
    if g_cloud:
        agent_entity_id = f"AIAG-{entity_id.replace('GENAI-', '').replace('-', '')}"
        node = g_cloud.add_entity(agent_entity_id, agent_name, "AI_Agent")
        g_cloud.update_entity_property(agent_entity_id, "development_partner", partner)
        g_cloud.update_entity_property(agent_entity_id, "deployment_status", "deploying")
        g_cloud.update_entity_property(agent_entity_id, "launch_date", params.get("launch_date", ""))
        g_cloud.update_entity_property(agent_entity_id, "target_clients", params.get("target_clients", 0))
        g_cloud.update_entity_property(agent_entity_id, "created_by", actor)

    # Cross-domain edge: source → develops → target
    if g_consulting and g_cloud:
        g_consulting.add_relation(
            entity_id, agent_entity_id, "develops",
            relation_label="AI agent deployment", confidence=0.95
        )

    return {
        "new_state": "deployed",
        "agent_name": agent_name,
        "development_partner": partner,
        "agent_entity_id": agent_entity_id,
        "deployed_by": actor,
    }


async def trigger_emergency_response(entity: Dict[str, Any], params: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    """Emergency response: create emergency record from clinical trial."""
    from core.harness.ontology_engine.graph_index import GraphIndex
    import datetime as _dt

    entity_id = entity.get("id") or entity.get("entity_id", "")
    incident_type = params.get("incident_type", "adverse_event")
    severity = params.get("severity", "serious")
    description = params.get("description", "")

    domain_id = entity.get("domain_id") or params.get("domain_id", "")
    if not domain_id:
        raise ValueError("domain_id is required")
    g = GraphIndex.load(domain_id)
    em_id = f"EM-{entity_id.replace('TRIAL-','')}-{_dt.datetime.now().strftime('%H%M%S')}"

    # Create EmergencyReception entity
    node = g.add_entity(em_id, f"{entity.get('name', 'Trial')}紧急事件",
                        "EmergencyReception")
    g.update_entity_property(em_id, "incident_type", incident_type)
    g.update_entity_property(em_id, "severity", severity)
    g.update_entity_property(em_id, "reported_at", _dt.datetime.now().isoformat() + "Z")
    g.update_entity_property(em_id, "response_action", params.get("response_action", "pending_investigation"))
    g.update_entity_property(em_id, "reported_by", actor)

    # Relation: ClinicalTrial → supports → EmergencyReception
    g.add_relation(entity_id, em_id, "supports",
                   relation_label="紧急事件响应", confidence=0.95)

    # Update trial status
    g.update_entity_property(entity_id, "status", "active")
    g.update_entity_property(entity_id, "last_incident_at", _dt.datetime.now().isoformat() + "Z")

    return {
        "new_state": "reported",
        "incident_id": em_id,
        "incident_type": incident_type,
        "severity": severity,
        "response_action": params.get("response_action", "pending_investigation"),
        "triggered_by": actor,
    }


async def complete_bpr_delivery(entity: Dict[str, Any], params: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    """Bell24: BPR咨询交付完成 → 更新状态并记录效率数据."""
    from core.harness.ontology_engine.graph_index import GraphIndex

    entity_id = entity.get("id") or entity.get("entity_id", "")
    efficiency_rate = params.get("efficiency_improvement_rate", 0)
    man_hours_saved = params.get("man_hours_saved", 0)

    domain_id = entity.get("domain_id") or params.get("domain_id", "")
    if not domain_id:
        raise ValueError("domain_id is required")
    g = GraphIndex.load(domain_id)
    g.update_entity_property(entity_id, "state", "completed")
    g.update_entity_property(entity_id, "efficiency_improvement_rate", efficiency_rate)
    g.update_entity_property(entity_id, "man_hours_saved", man_hours_saved)
    g.update_entity_property(entity_id, "completed_by", actor)

    result = {
        "new_state": "completed",
        "efficiency_improvement_rate": efficiency_rate,
        "man_hours_saved": man_hours_saved,
        "completed_by": actor,
    }

    # If high efficiency, suggest AI Agent follow-up
    if int(efficiency_rate) >= 20:
        result["suggested_next"] = "AI Agent导入推荐"
        result["suggests_ai_agent"] = True

    return result


async def sync_overseas_status(entity: Dict[str, Any], params: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    """Bell24: 海外子公司状态同步 → 更新集团视图."""
    from core.harness.ontology_engine.graph_index import GraphIndex

    entity_id = entity.get("id") or entity.get("entity_id", "")
    new_status = params.get("consolidation_status", "consolidated")
    employee_update = params.get("employees", 0)
    locations_update = params.get("locations_count", 0)

    domain_id = entity.get("domain_id") or params.get("domain_id", "")
    if not domain_id:
        raise ValueError("domain_id is required")
    g = GraphIndex.load(domain_id)
    g.update_entity_property(entity_id, "consolidation_status", new_status)
    if employee_update:
        g.update_entity_property(entity_id, "employees", employee_update)
    if locations_update:
        g.update_entity_property(entity_id, "locations_count", locations_update)
    g.update_entity_property(entity_id, "last_synced_by", actor)

    return {
        "new_state": entity.get("state", "active"),
        "consolidation_status": new_status,
        "employees": employee_update,
        "locations_count": locations_update,
        "synced_by": actor,
    }
