"""
售后服务域 Handler — 5 个动作实现 (service-domain reference)
"""
from datetime import datetime, timezone
from typing import Any, Dict


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def assign_technician(entity: Dict[str, Any], params: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    """指派技师 → 待指派→已指派"""
    from core.harness.ontology_engine.graph_index import GraphIndex

    entity_id = entity.get("id") or entity.get("entity_id")
    technician_id = params.get("technician_id")
    if not technician_id:
        raise ValueError("technician_id required")

    g = GraphIndex.load("service-domain")
    now = _iso_now()
    g.add_entity_property(entity_id, "status", "已指派")
    g.add_entity_property(entity_id, "technician_id", technician_id)
    g.add_entity_property(entity_id, "assigned_at", now)
    if params.get("notes"):
        g.add_entity_property(entity_id, "assign_notes", params["notes"])

    # Create assigned_to relation with temporal window
    g.add_relation(
        source_id=entity_id, target_id=technician_id,
        relation_name="assigned_to",
        valid_from=now, confidence=1.0,
    )
    return {"new_state": "已指派", "technician_id": technician_id, "assigned_at": now}


async def start_repair(entity: Dict[str, Any], params: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    """开始维修 → 已指派→维修中"""
    from core.harness.ontology_engine.graph_index import GraphIndex

    entity_id = entity.get("id") or entity.get("entity_id")
    g = GraphIndex.load("service-domain")
    now = _iso_now()
    g.add_entity_property(entity_id, "status", "维修中")
    g.add_entity_property(entity_id, "repair_started_at", now)
    return {"new_state": "维修中", "repair_started_at": now}


async def submit_report(entity: Dict[str, Any], params: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    """提交维修报告 → 维修中→待验收"""
    from core.harness.ontology_engine.graph_index import GraphIndex

    entity_id = entity.get("id") or entity.get("entity_id")
    resolution = params.get("resolution")
    duration = params.get("duration_minutes", 0)
    parts_used = params.get("parts_used") or []

    if not resolution:
        raise ValueError("resolution required")

    g = GraphIndex.load("service-domain")
    report_id = f"RPR-{entity_id}-{int(datetime.now().timestamp())}"

    g.add_entity(report_id, f"维修报告-{entity_id}", "RepairReport", source_doc_id="service-domain")
    g.add_entity_property(report_id, "report_id", report_id)
    g.add_entity_property(report_id, "resolution", resolution)
    g.add_entity_property(report_id, "duration_minutes", duration)
    g.add_entity_property(report_id, "submitted_at", _iso_now())

    g.add_relation(report_id, entity_id, "linked_to", confidence=1.0)

    for part_id in parts_used:
        g.add_relation(report_id, part_id, "consumes", confidence=1.0)

    g.add_entity_property(entity_id, "status", "待验收")
    g.add_entity_property(entity_id, "repair_report_uploaded", "true")
    g.add_entity_property(entity_id, "repair_report_id", report_id)
    g.add_entity_property(entity_id, "repair_duration_minutes", duration)

    return {"new_state": "待验收", "report_id": report_id, "parts_used": parts_used}


async def complete_work_order(entity: Dict[str, Any], params: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    """完成工单 → 待验收→已完成"""
    from core.harness.ontology_engine.graph_index import GraphIndex

    entity_id = entity.get("id") or entity.get("entity_id")
    confirmation = params.get("customer_confirmation")
    if not confirmation:
        raise ValueError("customer_confirmation required")

    g = GraphIndex.load("service-domain")
    now = _iso_now()
    g.add_entity_property(entity_id, "status", "已完成")
    g.add_entity_property(entity_id, "completed_at", now)
    g.add_entity_property(entity_id, "customer_confirmation", confirmation)
    if params.get("customer_name"):
        g.add_entity_property(entity_id, "confirmer_name", params["customer_name"])
    if params.get("rating"):
        g.add_entity_property(entity_id, "customer_rating", params["rating"])

    return {"new_state": "已完成", "completed_at": now, "customer_rating": params.get("rating")}


async def reopen_work_order(entity: Dict[str, Any], params: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    """重新打开工单 → 已完成→待指派"""
    from core.harness.ontology_engine.graph_index import GraphIndex

    entity_id = entity.get("id") or entity.get("entity_id")
    reason = params.get("reopen_reason")
    if not reason:
        raise ValueError("reopen_reason required")

    g = GraphIndex.load("service-domain")
    now = _iso_now()
    g.add_entity_property(entity_id, "status", "待指派")
    g.add_entity_property(entity_id, "technician_id", None)
    g.add_entity_property(entity_id, "assigned_at", None)
    g.add_entity_property(entity_id, "reopened_at", now)
    g.add_entity_property(entity_id, "reopen_reason", reason)

    return {"new_state": "待指派", "reopened": True, "reopen_reason": reason}
