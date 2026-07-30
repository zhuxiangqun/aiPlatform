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
    """Approve a diagnosis session: transition from delivered → in_progress."""
    from core.harness.ontology_engine.graph_index import GraphIndex

    entity_id = entity.get("id") or entity.get("entity_id", "")
    g = GraphIndex.load("fde-delivery")

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
    """Accept an installation order: transition from pending → accepted."""
    from core.harness.ontology_engine.graph_index import GraphIndex

    entity_id = entity.get("id") or entity.get("entity_id", "")
    g = GraphIndex.load("lock-service")

    g.update_entity_property(entity_id, "state", "accepted")
    g.update_entity_property(entity_id, "technician_id", params.get("technician_id", ""))
    g.update_entity_property(entity_id, "appointment_slot", params.get("appointment_slot", ""))

    return {
        "new_state": "accepted",
        "technician_id": params.get("technician_id"),
        "appointment_slot": params.get("appointment_slot"),
        "accepted_by": actor,
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
    """Bell24: GenAI共创完成 → 创建 AI_Agent 实体并建立开发关系."""
    from core.harness.ontology_engine.graph_index import GraphIndex

    entity_id = entity.get("id") or entity.get("entity_id", "")
    agent_name = params.get("agent_name", f"{entity.get('name', 'Lab')}-AI-Agent")
    partner = params.get("development_partner", "AVILEN")

    # Update GenAI lab status
    g_consulting = GraphIndex.load("bell-consulting")
    g_consulting.update_entity_property(entity_id, "state", "deployed")
    g_consulting.update_entity_property(entity_id, "last_agent_deployed", agent_name)

    # Create AI_Agent entity in bell-data-cloud
    g_cloud = GraphIndex.load("bell-data-cloud")
    agent_entity_id = f"AIAG-{entity_id.replace('GENAI-', '').replace('-', '')}"
    node = g_cloud.add_entity(agent_entity_id, agent_name, "AI_Agent")
    g_cloud.update_entity_property(agent_entity_id, "development_partner", partner)
    g_cloud.update_entity_property(agent_entity_id, "deployment_status", "deploying")
    g_cloud.update_entity_property(agent_entity_id, "launch_date", params.get("launch_date", ""))
    g_cloud.update_entity_property(agent_entity_id, "target_clients", params.get("target_clients", 0))
    g_cloud.update_entity_property(agent_entity_id, "created_by", actor)

    # Cross-domain edge: GenAI Lab → develops → AI_Agent
    g_consulting.add_relation(entity_id, agent_entity_id, "develops",
                              relation_label="开发AI Agent", confidence=0.95)

    return {
        "new_state": "deployed",
        "agent_name": agent_name,
        "development_partner": partner,
        "agent_entity_id": agent_entity_id,
        "deployed_by": actor,
    }


async def trigger_emergency_response(entity: Dict[str, Any], params: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    """Bell24 CRO: 临床试验严重事件 → 创建紧急应对记录."""
    from core.harness.ontology_engine.graph_index import GraphIndex
    import datetime as _dt

    entity_id = entity.get("id") or entity.get("entity_id", "")
    incident_type = params.get("incident_type", "adverse_event")
    severity = params.get("severity", "serious")
    description = params.get("description", "")

    g = GraphIndex.load("bell-healthcare")
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

    g = GraphIndex.load("bell-consulting")
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

    g = GraphIndex.load("bell-global")
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
