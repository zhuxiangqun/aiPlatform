"""
Action execution REST API — list available actions and execute them.

Mounted at: /api/platform/apps/fde/actions
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request

router = APIRouter(tags=["fde-actions"])

logger = logging.getLogger(__name__)


def _parse_scopes(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [p.strip() for p in str(raw).replace(";", ",").split(",") if p.strip()]


def _resolve_role_from_request(
    request: Optional[Request],
    *,
    explicit_role: str = "",
    header_role: Optional[str] = None,
    scopes_header: Optional[str] = None,
) -> str:
    from core.api.core_facade import resolve_abox_actor_role

    hdr = header_role
    scopes = _parse_scopes(scopes_header)
    if request is not None:
        if not hdr:
            hdr = request.headers.get("X-AIPLAT-ACTOR-ROLE") or request.headers.get(
                "X-AIPLAT-ROLE"
            )
        if not scopes:
            scopes = _parse_scopes(request.headers.get("X-AIPLAT-SCOPES"))
    return resolve_abox_actor_role(
        explicit_role=explicit_role or "",
        header_role=hdr or "",
        scopes=scopes,
    )


def _safe_contract(contract) -> Dict[str, Any]:
    """Extract frontend-safe fields from ActionContractModel (no handler paths)."""
    ns = getattr(contract, "action_namespace", "") or ""
    return {
        "action_id": contract.action_id,
        "label": contract.label,
        "description": contract.description,
        "category": contract.category.value,
        "scope": contract.scope.value,
        "domain_id": contract.domain_id,
        "target_class": contract.target_class,
        "required_state": contract.required_state,
        "forbidden_states": contract.forbidden_states,
        "effect_semantics": contract.effect_semantics,
        "compensation": contract.compensation,
        "risk_level": contract.risk_level.value,
        "require_approval": contract.require_approval,
        "input_schema": contract.input_schema,
        "action_namespace": ns,
        "action_kind": (
            "customer" if ns == "customer_action"
            else "platform" if ns == "platform_action"
            else "legacy"
        ),
        "aliases": list(getattr(contract, "aliases", None) or []),
    }


@router.get("/actions")
async def list_actions(
    class_name: str = Query("", description="Entity class to filter actions for", alias="class"),
    state: str = Query("", description="Entity state to filter actions for"),
    domain: str = Query("", description="Domain ID"),
    role: str = Query("", description="Caller's role (optional)"),
    include_cross_domain: bool = Query(False, description="Include cross-domain actions"),
):
    """List actions available for a given entity class + state."""
    try:
        from core.api.core_facade import get_action_registry
        reg = get_action_registry()
        actions = reg.list_for_class(
            domain_id=domain or "fde-delivery",
            class_name=class_name,
            state=state,
            role=role,
            include_cross_domain=include_cross_domain,
        )
        return {"actions": [_safe_contract(a) for a in actions], "count": len(actions)}
    except Exception as e:
        logger.error("Failed to list actions: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/graph/entities")
async def list_graph_entities(
    request: Request,
    domain: str = Query(..., description="Domain ID"),
    class_name: str = Query("", alias="class", description="Entity class label"),
    limit: int = Query(50, ge=1, le=200),
    actor_role: str = Query("", description="Optional role for ABox ACL filter/redact"),
    x_aiplat_actor_role: Optional[str] = Header(None, alias="X-AIPLAT-ACTOR-ROLE"),
    x_aiplat_scopes: Optional[str] = Header(None, alias="X-AIPLAT-SCOPES"),
):
    """List GraphIndex entities (for AcceptTab picker / live state).

    When actor_role (or identity header) is set, applies graph_abox_acl filter/redact.
    """
    try:
        from core.api.core_facade import GraphIndex, check_graph_entity_acl, redact_graph_entity_fields

        role = _resolve_role_from_request(
            request,
            explicit_role=actor_role,
            header_role=x_aiplat_actor_role,
            scopes_header=x_aiplat_scopes,
        )
        g = GraphIndex.load(domain)
        nodes = g.get_entities_by_class(class_name) if class_name else list(g._nodes.values())
        out = []
        for n in nodes:
            if role and not check_graph_entity_acl(domain, n.entity_id, role, "read"):
                continue
            meta = dict(n.metadata or {})
            row = {
                "entity_id": n.entity_id,
                "name": n.entity_name,
                "class": n.class_name,
                "state": meta.get("state") or meta.get("status") or "",
                "metadata": meta,
            }
            if role:
                row = redact_graph_entity_fields(domain, n.entity_id, row, role)
                meta2 = row.get("metadata") if isinstance(row.get("metadata"), dict) else meta
                row["state"] = meta2.get("state") or meta2.get("status") or row.get("state") or ""
            out.append(row)
            if len(out) >= limit:
                break
        return {"domain": domain, "entities": out, "count": len(out), "actor_role": role or None}
    except Exception as e:
        logger.error("list_graph_entities failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/graph/entities")
async def create_graph_entity(body: Dict[str, Any]):
    """Create a demo ABox entity in GraphIndex.

    Body:
      scenario — optional:
        "it-ops-alert" — minimal call-path + Alert (path C minimal)
        "it-ops-alert-complex" — B3.2 teaching flood topology (path C complex)
        "data-gov-assets" — B4 teaching governance graph + ABox ACL seed
      profile — optional alias when scenario=it-ops-alert: "minimal"|"complex"
      domain_id — default lock-service (or it-ops when it-ops scenario)
      class_name — default 安装工单 / 告警
      entity_id — optional; auto IO-DEMO-xxx / ALT-DEMO-xxx
      name — display name
      state — default pending / open
      with_technician — bool, also seed TECH-DEMO-001 (lock-service only)
    """
    scenario = str(body.get("scenario") or "").strip()
    profile = str(body.get("profile") or "").strip().lower()
    if scenario in ("it-ops-alert", "it-ops-alert-complex") or (
        scenario == "" and profile in ("minimal", "complex") and body.get("domain_id") == "it-ops"
    ):
        domain_id = "it-ops"
        if scenario == "it-ops-alert-complex" or profile == "complex":
            seed_profile = "complex"
            scenario_out = "it-ops-alert-complex"
        else:
            seed_profile = "minimal"
            scenario_out = "it-ops-alert"
        state = str(body.get("state") or "open")
        name = str(body.get("name") or (
            "积分系统告警洪水（教学复杂）" if seed_profile == "complex" else "积分系统告警洪水（演示）"
        ))
        entity_id = str(body.get("entity_id") or "").strip()
        if not entity_id:
            import time
            entity_id = f"ALT-DEMO-{int(time.time()) % 100000:05d}"
        try:
            from core.api.core_facade import GraphIndex
            from core.apps.fde.service.it_ops_demo_seed import (
                ensure_it_ops_fault_ontology,
                seed_it_ops_demo_graph,
            )

            # Path C needs fault-diagnosis it-ops.yaml (not knowledge「基础设施」版)
            ensure_it_ops_fault_ontology()
            GraphIndex._loaded_instances.clear()
            g = GraphIndex.load(domain_id)
            meta = seed_it_ops_demo_graph(
                g,
                profile=seed_profile,
                primary_alert_id=entity_id,
                primary_alert_name=name,
                primary_state=state,
                source_doc_id="ui-demo",
                ensure_ontology=False,  # already ensured above
            )
            g.save()
            return {
                "status": "created",
                "domain_id": domain_id,
                "entity_id": entity_id,
                "class": "告警",
                "state": state,
                "scenario": scenario_out,
                "profile": meta["profile"],
                "topology": meta["topology"],
                "alerts": meta.get("alerts", [entity_id]),
                "default_root": meta["default_root"],
                "ontology_ensure": meta.get("ontology_ensure") or {"action": "pre_ensured"},
            }
        except Exception as e:
            logger.error("create_graph_entity it-ops demo failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)[:300])

    if scenario in ("data-gov-assets", "data-gov-b4"):
        domain_id = "data-gov"
        try:
            from core.api.core_facade import GraphIndex
            from core.apps.fde.service.data_gov_demo_seed import (
                ensure_data_gov_ontology,
                seed_data_gov_demo_graph,
            )

            ensure_data_gov_ontology()
            GraphIndex._loaded_instances.clear()
            g = GraphIndex.load(domain_id)
            meta = seed_data_gov_demo_graph(g, ensure_ontology=False, seed_acl=True)
            g.save()
            return {
                "status": "created",
                "domain_id": domain_id,
                "entity_id": meta.get("primary_asset_id"),
                "class": "数据资产",
                "state": "meta_ready",
                "scenario": "data-gov-assets",
                "profile": meta.get("profile"),
                "topology": meta.get("topology"),
                "ghost_id": meta.get("ghost_id"),
                "catalog_id": meta.get("catalog_id"),
                "acl_seeded": meta.get("acl_seeded"),
                "ontology_ensure": meta.get("ontology_ensure"),
            }
        except Exception as e:
            logger.error("create_graph_entity data-gov demo failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)[:300])

    domain_id = str(body.get("domain_id") or "lock-service")
    class_name = str(body.get("class_name") or "安装工单")
    state = str(body.get("state") or "pending")
    name = str(body.get("name") or "演示安装工单")
    with_tech = bool(body.get("with_technician", True))
    entity_id = str(body.get("entity_id") or "").strip()
    if not entity_id:
        import time
        entity_id = f"IO-DEMO-{int(time.time()) % 100000:05d}"

    try:
        from core.api.core_facade import GraphIndex
        GraphIndex._loaded_instances.clear()
        g = GraphIndex.load(domain_id)
        tech_id = str(body.get("technician_id") or "TECH-DEMO-001")
        if with_tech:
            g.add_entity(tech_id, "演示安装师傅", "安装师傅", source_doc_id="ui-demo")
        g.add_entity(entity_id, name, class_name, source_doc_id="ui-demo")
        g.add_entity_property(entity_id, "state", state)
        g.add_entity_property(entity_id, "status", state)
        g.save()
        return {
            "status": "created",
            "domain_id": domain_id,
            "entity_id": entity_id,
            "class": class_name,
            "state": state,
            "technician_id": tech_id if with_tech else None,
        }
    except Exception as e:
        logger.error("create_graph_entity failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/graph/import")
async def import_graph_payload(body: Dict[str, Any]):
    """Path B: import monitor/JSON/table ABox into GraphIndex (it-ops / connector domains).

    Body:
      domain_id — default it-ops
      source_type — omit|entities|table_map (table_map = CSV/rows via connector.table_map)
      use_sample — bool, load bundled fixture when payload omitted
      payload — {entities, relations, primary_alert_id?, default_root?}
      rows / csv_text / relation_rows — for source_type=table_map
    """
    domain_id = str(body.get("domain_id") or "it-ops").strip() or "it-ops"
    source_type = str(body.get("source_type") or "").strip().lower()
    try:
        from core.api.core_facade import GraphIndex
        from core.apps.fde.service.abox_connector import (
            ensure_connector_config,
            import_abox_payload,
            import_table_map_payload,
            load_connector_config,
        )

        # ── table / CSV Path B ──
        if source_type == "table_map":
            if domain_id == "it-ops":
                from core.apps.fde.service.it_ops_demo_seed import ensure_it_ops_fault_ontology

                ensure_it_ops_fault_ontology()
            else:
                ensure_connector_config(domain_id)
            GraphIndex._loaded_instances.clear()
            g = GraphIndex.load(domain_id)
            rows = body.get("rows") if isinstance(body.get("rows"), list) else None
            relation_rows = (
                body.get("relation_rows")
                if isinstance(body.get("relation_rows"), list)
                else None
            )
            meta = import_table_map_payload(
                g,
                domain_id=domain_id,
                rows=rows,
                csv_text=str(body.get("csv_text") or "") or None,
                relation_rows=relation_rows,
                use_sample=bool(body.get("use_sample")),
                source_doc_id=str(body.get("source") or "table-map"),
            )
            g.save()
            return {
                "status": "imported",
                "domain_id": domain_id,
                "path": "B",
                "source_type": "table_map",
                **meta,
            }

        payload = body.get("payload")
        if not isinstance(payload, dict) or not payload:
            if body.get("use_sample") and domain_id == "it-ops":
                from core.apps.fde.service.it_ops_demo_seed import load_it_ops_import_sample

                payload = load_it_ops_import_sample()
            else:
                raise HTTPException(
                    status_code=400,
                    detail="payload object required (or use_sample=true for it-ops)",
                )

        if domain_id == "it-ops":
            from core.apps.fde.service.it_ops_demo_seed import (
                ensure_it_ops_fault_ontology,
                import_it_ops_alert_payload,
            )

            ensure_it_ops_fault_ontology()
            GraphIndex._loaded_instances.clear()
            g = GraphIndex.load(domain_id)
            meta = import_it_ops_alert_payload(
                g,
                payload,
                source_doc_id=str(payload.get("source") or "monitor-import"),
                ensure_ontology=False,
            )
        else:
            ensure_connector_config(domain_id)
            cfg = load_connector_config(domain_id)
            allow_cls = set(cfg.get("allowed_classes") or [])
            if not allow_cls:
                raise HTTPException(
                    status_code=400,
                    detail=f"domain {domain_id} has empty allowed_classes in connector.json",
                )
            GraphIndex._loaded_instances.clear()
            g = GraphIndex.load(domain_id)
            meta = import_abox_payload(
                g,
                payload,
                allowed_classes=allow_cls,
                allowed_relations=set(cfg.get("allowed_relations") or []),
                source_doc_id=str(payload.get("source") or "monitor-import"),
                primary_class=str(cfg.get("primary_class") or ""),
            )
        g.save()
        return {
            "status": "imported",
            "domain_id": domain_id,
            "path": "B",
            **meta,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("import_graph_payload failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/ontology/pillars/{domain_id}")
async def ontology_pillars(domain_id: str):
    """Read-only data / logic / action three-pillar view for a domain."""
    try:
        from core.apps.fde.service.ontology_pillars import get_ontology_pillars

        return get_ontology_pillars(domain_id)
    except Exception as e:
        logger.error("ontology_pillars failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/ontology/code-suggestions")
async def ontology_code_suggestions(body: Dict[str, Any]):
    """Code/doc → proposal drafts only (never auto-apply)."""
    domain_id = str(body.get("domain_id") or "it-ops").strip() or "it-ops"
    try:
        from core.apps.fde.service.ontology_code_suggestions import (
            suggest_classes_from_snippets_async,
        )

        snippets = body.get("snippets") if isinstance(body.get("snippets"), list) else None
        file_paths = body.get("file_paths") if isinstance(body.get("file_paths"), list) else None
        enqueue = bool(body.get("enqueue", True))
        return await suggest_classes_from_snippets_async(
            domain_id,
            snippets=snippets,
            file_paths=file_paths,
            author=str(body.get("author") or "code-suggest"),
            enqueue=enqueue,
        )
    except Exception as e:
        logger.error("ontology_code_suggestions failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/ontology/owl-review/{domain_id}")
async def ontology_owl_review(domain_id: str):
    """Offline OWL consistency review — suggestion only; unchecked ≠ valid."""
    try:
        from core.apps.fde.service.offline_owl_review import review_domain_owl_offline

        result = review_domain_owl_offline(domain_id)
        if result.get("status") in ("unchecked", "error"):
            result["valid"] = False
        return result
    except Exception as e:
        logger.error("ontology_owl_review failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/graph/webhook/{source_id}")
async def graph_webhook_ingest(
    source_id: str,
    body: Dict[str, Any],
    x_aiplat_webhook_secret: Optional[str] = Header(None, alias="X-AIPLAT-WEBHOOK-SECRET"),
):
    """Production Path B: monitoring / external systems push ABox JSON.

    Resolves ``source_id`` via connector.json (no harness domain hardcoding).
    Receipt: created_entities / relations / skipped / primary_id.
    """
    try:
        from core.api.core_facade import ingest_abox_webhook

        payload = body.get("payload") if isinstance(body.get("payload"), dict) else body
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="JSON object payload required")
        result = ingest_abox_webhook(
            source_id,
            payload,
            secret=x_aiplat_webhook_secret or str(body.get("secret") or "") or None,
            domain_id=str(body.get("domain_id") or "").strip() or None,
        )
        if result.get("status") == "unauthorized":
            raise HTTPException(status_code=401, detail=result.get("reason") or "unauthorized")
        if result.get("status") == "rejected":
            raise HTTPException(status_code=404, detail=result.get("reason") or "unknown source")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("graph_webhook_ingest failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/actions/execute")
async def execute_action(
    body: Dict[str, Any],
    request: Request,
    x_aiplat_actor_role: Optional[str] = Header(None, alias="X-AIPLAT-ACTOR-ROLE"),
    x_aiplat_scopes: Optional[str] = Header(None, alias="X-AIPLAT-SCOPES"),
):
    """Execute a registered action.

    Body:
      action_id  — registered action identifier
      entity_id  — target entity ID (str) or [domain, entity_id] for cross-domain
      params     — input parameters matching action.input_schema
      actor      — who triggered the action (optional)
      role       — actor's role for constraint checking (optional; header preferred)
    """
    action_id = str(body.get("action_id", "")).strip()
    entity_ref = body.get("entity_id")
    params = body.get("params", {}) or {}
    actor = str(body.get("actor", "system"))
    role = _resolve_role_from_request(
        request,
        explicit_role=str(body.get("role", "")),
        header_role=x_aiplat_actor_role,
        scopes_header=x_aiplat_scopes,
    )

    if not action_id:
        raise HTTPException(status_code=400, detail="action_id is required")

    if not entity_ref:
        raise HTTPException(status_code=400, detail="entity_id is required")

    # Support cross-domain tuple: entity_ref = ["domain_id", "entity_id"]
    if isinstance(entity_ref, list):
        if len(entity_ref) >= 2:
            entity_ref = (str(entity_ref[0]), str(entity_ref[1]))
        else:
            entity_ref = str(entity_ref[0])

    try:
        from core.api.core_facade import get_action_registry, check_graph_entity_acl

        # Resolve domain + entity id for ABox ACL (T9)
        acl_domain = ""
        acl_eid = ""
        if isinstance(entity_ref, tuple) and len(entity_ref) >= 2:
            acl_domain, acl_eid = str(entity_ref[0]), str(entity_ref[1])
        else:
            acl_eid = str(entity_ref)
            # infer domain from action_id customer_action:{domain}:...
            parts = action_id.split(":")
            if len(parts) >= 3 and parts[0] == "customer_action":
                acl_domain = parts[1]
        if role and acl_domain and acl_eid:
            if not check_graph_entity_acl(acl_domain, acl_eid, role, "state_change"):
                return {
                    "status": "blocked",
                    "reason": f"ABox ACL denies state_change for role={role} on {acl_eid}",
                    "constraint_type": "abox_acl",
                }

        reg = get_action_registry()
        result = await reg.execute(
            action_id=action_id,
            entity_ref=entity_ref,
            params=params,
            actor=actor,
            role=role,
        )

        # Map constraint types to HTTP-friendly responses
        status = result.get("status", "unknown")
        if status == "blocked":
            return {
                "status": "blocked",
                "reason": result.get("reason", "Unknown constraint"),
                "constraint_type": result.get("constraint_type", "unknown"),
            }
        if status == "pending_approval":
            return {
                "status": "pending_approval",
                "action_id": result.get("action_id"),
                "entity_id": result.get("entity_id"),
                "lock_id": result.get("lock_id"),
                "locked_until": result.get("locked_until"),
                "message": result.get("message", "Approval required"),
            }
        if status == "invalid_params":
            raise HTTPException(status_code=400, detail=result.get("errors", ["Invalid params"]))

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Action execution failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/graph/acl/{domain_id}")
async def get_graph_acl(domain_id: str):
    """Load ABox ACL document + CRUD matrix (T9 / Phase 3 lite)."""
    try:
        from core.api.core_facade import get_abox_acl_doc, get_abox_crud_matrix

        return {
            "domain_id": domain_id,
            "acl": get_abox_acl_doc(domain_id),
            "crud_matrix": get_abox_crud_matrix(),
        }
    except Exception as e:
        logger.error("get_graph_acl failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.put("/graph/acl/{domain_id}/entities/{entity_id}")
async def put_graph_entity_acl(domain_id: str, entity_id: str, body: Dict[str, Any]):
    """Upsert instance ACL (deny_roles / allow_roles)."""
    try:
        from core.api.core_facade import set_graph_entity_acl

        entry = set_graph_entity_acl(
            domain_id,
            entity_id,
            deny_roles=body.get("deny_roles"),
            allow_roles=body.get("allow_roles"),
        )
        return {"domain_id": domain_id, "entity_id": entity_id, "entry": entry}
    except Exception as e:
        logger.error("put_graph_entity_acl failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.put("/graph/acl/{domain_id}/fields/{entity_id}/{field_name}")
async def put_graph_field_acl(
    domain_id: str, entity_id: str, field_name: str, body: Dict[str, Any]
):
    """Upsert field visibility / redaction rule."""
    try:
        from core.api.core_facade import set_graph_field_acl

        entry = set_graph_field_acl(
            domain_id,
            entity_id,
            field_name,
            visibility=str(body.get("visibility") or "all"),
            redaction=str(body.get("redaction") or "mask"),
            replace_with=str(body.get("replace_with") or "[REDACTED]"),
        )
        return {
            "domain_id": domain_id,
            "entity_id": entity_id,
            "field": field_name,
            "entry": entry,
        }
    except Exception as e:
        logger.error("put_graph_field_acl failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/actions/from-yaml")
async def register_from_yaml(body: Dict[str, Any]):
    """Register actions from a YAML file (business expert entry point).

    Body:
      yaml_path  — path to YAML file (must be within ~/.aiplat/actions/ or ./config/actions/)
    """
    yaml_path = str(body.get("yaml_path", "")).strip()
    if not yaml_path:
        raise HTTPException(status_code=400, detail="yaml_path is required")

    try:
        from core.api.core_facade import ActionContractModel
        from core.api.core_facade import get_action_registry

        contracts = ActionContractModel.from_yaml_batch(yaml_path)
        reg = get_action_registry()
        count = reg.register_batch(contracts)

        return {
            "status": "registered",
            "registered_count": count,
            "action_ids": [c.action_id for c in contracts],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("YAML registration failed: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)[:300])


# ═══════════════════════════════════════════════════════════
# Approval workflow
# ═══════════════════════════════════════════════════════════

@router.get("/actions/approvals/pending")
async def list_pending_approvals(
    entity_ref: str = Query("", description="Filter by entity (domain:entity_id)"),
):
    """List pending approval requests."""
    try:
        from core.api.core_facade import get_action_registry
        reg = get_action_registry()
        items = await reg._store.list_pending_by_entity(entity_ref) if entity_ref else []
        return {"pending": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/actions/approvals/{lock_id}/approve")
async def approve_action(lock_id: str, body: Dict[str, Any] = None):
    """Approve a pending action."""
    try:
        from core.api.core_facade import get_action_registry
        reg = get_action_registry()
        result = await reg.approve(lock_id, resolver=body.get("resolver", "approver") if body else "approver")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/actions/approvals/{lock_id}/reject")
async def reject_action(lock_id: str, body: Dict[str, Any] = None):
    """Reject a pending action."""
    try:
        from core.api.core_facade import get_action_registry
        reg = get_action_registry()
        result = await reg.reject(
            lock_id,
            resolver=body.get("resolver", "approver") if body else "approver",
            reason=body.get("reason", "") if body else "",
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])
