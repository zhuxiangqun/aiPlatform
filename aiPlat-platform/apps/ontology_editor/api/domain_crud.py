from api.schemas_response import StatusResponse
u"""
Ontology Editor — Domain CRUD endpoints.

Routes:
  GET    /domains                  — list all ontology domains
  GET    /domains/{id}/schema      — get domain schema as JSON
  POST   /domains                  — create empty domain
  PUT    /domains/{id}             — update domain metadata
  DELETE /domains/{id}             — delete domain
  POST   /domains/{id}/classes     — upsert a class definition
  DELETE /domains/{id}/classes/{name} — delete a class
  GET    /domains/{id}/rule-versions — list rule version snapshots
  POST   /domains/{id}/publish     — write YAML + invalidate caches
"""
from fastapi import APIRouter, HTTPException
from typing import Any, Dict, List

router = APIRouter(tags=["ontology-editor"])


@router.get("/domains", response_model=StatusResponse)
async def list_domains():
    u"""List all ontology domains with class/property/rule counts."""
    try:
        from core.api.core_facade import list_ontology_domains
        domains = list_ontology_domains()
        return {"domains": domains, "total": len(domains)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list domains: {e}")


@router.get("/domains/{domain_id}/schema", response_model=StatusResponse)
async def get_domain_schema(domain_id: str):
    u"""Get full domain schema as JSON (classes, properties, rules)."""
    try:
        from core.api.core_facade import get_ontology_domain_schema
        schema = get_ontology_domain_schema(domain_id)
        return {"domain_id": domain_id, "schema": schema}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load domain schema: {e}")


@router.post("/domains", response_model=StatusResponse)
async def create_domain(data: Dict[str, Any]):
    u"""Create a new empty ontology domain YAML."""
    try:
        from core.api.core_facade import create_ontology_domain
        domain_id = data.get("id") or data.get("domain_id", "")
        name = data.get("name", "")
        if not domain_id or not name:
            raise HTTPException(status_code=400, detail="id and name are required")
        result = create_ontology_domain(
            domain_id=domain_id,
            name=name,
            namespace=data.get("namespace", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
        )
        return result
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create domain: {e}")


@router.put("/domains/{domain_id}", response_model=StatusResponse)
async def update_domain_meta(domain_id: str, data: Dict[str, Any]):
    u"""Update domain metadata (name, description, version, namespace)."""
    try:
        from core.api.core_facade import update_ontology_domain_meta
        result = update_ontology_domain_meta(
            domain_id=domain_id,
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", ""),
            namespace=data.get("namespace", ""),
        )
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update domain: {e}")


@router.delete("/domains/{domain_id}", response_model=StatusResponse)
async def delete_domain(domain_id: str):
    u"""Delete an ontology domain YAML and remove from registry."""
    try:
        from core.api.core_facade import delete_ontology_domain
        result = delete_ontology_domain(domain_id)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete domain: {e}")


@router.post("/domains/{domain_id}/classes", response_model=StatusResponse)
async def upsert_class(domain_id: str, data: Dict[str, Any]):
    u"""Create or update a class definition within a domain."""
    try:
        from core.api.core_facade import upsert_ontology_class
        class_name = data.get("class_name") or data.get("name", "")
        class_data = data.get("class_data") or data.get("data", {})
        if not class_name:
            raise HTTPException(status_code=400, detail="class_name is required")
        if not class_data:
            class_data = {k: v for k, v in data.items()
                          if k not in ("class_name", "name")}
        result = upsert_ontology_class(domain_id, class_name, class_data)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upsert class: {e}")


@router.delete("/domains/{domain_id}/classes/{class_name}", response_model=StatusResponse)
async def delete_class(domain_id: str, class_name: str):
    u"""Remove a class from a domain YAML."""
    try:
        from core.api.core_facade import delete_ontology_class
        result = delete_ontology_class(domain_id, class_name)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete class: {e}")


@router.get("/domains/{domain_id}/rule-versions", response_model=StatusResponse)
async def list_rule_versions(domain_id: str):
    u"""List saved rule version snapshots for a domain."""
    try:
        from core.api.core_facade import list_rule_versions
        versions = list_rule_versions(domain_id)
        return {"domain_id": domain_id, "versions": versions, "total": len(versions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list rule versions: {e}")


@router.post("/domains/{domain_id}/rules/generate-from-description", response_model=StatusResponse)
async def generate_rule_from_description(domain_id: str, data: Dict[str, Any]):
    u"""NL→Rule: LLM generates inference rule draft from natural language description."""
    try:
        from core.api.core_facade import get_ontology_domain_schema, best_model_for_purpose, resolve_prompt
        import json as _json

        description = data.get("description", "")
        if not description:
            raise HTTPException(status_code=400, detail="description is required")

        schema = get_ontology_domain_schema(domain_id)
        domain_context = schema.get("name", domain_id)
        existing_relations = ", ".join(
            p.get("name", "") for p in schema.get("object_properties", [])[:10]
        )

        prompt = resolve_prompt(
            "nl-to-inference-rule",
            domain_context=domain_context,
            existing_relations=existing_relations,
            description=description,
        )

        model = best_model_for_purpose("code_gen")
        response = await model.agenerate(prompt)
        text = getattr(response, "content", str(response))
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if lines[0].startswith("```") else text
            if text.endswith("```"):
                text = text[:-3].strip()

        suggestion = _json.loads(text)
        # NL→Rule generates a candidate, NOT directly into YAML
        # User must review and approve before publish
        suggestion["_status"] = "candidate"
        suggestion["_requires_review"] = True

        return {"domain_id": domain_id, "suggestion": suggestion}
    except _json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="LLM returned invalid JSON")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")


@router.post("/domains/{domain_id}/rules/audit", response_model=StatusResponse)
async def audit_rules(domain_id: str):
    u"""Audit inference rules for conflicts, unreachable premises, missing transitions."""
    try:
        from core.api.core_facade import get_ontology_domain_schema
        from core.harness.knowledge.rule_auditor import audit_rules as _audit_rules

        schema = get_ontology_domain_schema(domain_id)
        result = _audit_rules(schema)
        return {"domain_id": domain_id, **result}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit failed: {e}")


@router.post("/domains/{domain_id}/publish", response_model=StatusResponse)
async def publish_domain(domain_id: str):
    u"""Validate and publish domain YAML — snapshot + cache invalidation."""
    try:
        from core.api.core_facade import publish_ontology_domain
        result = publish_ontology_domain(domain_id)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to publish domain: {e}")


@router.post("/domains/{domain_id}/generate-from-description", response_model=StatusResponse)
async def generate_from_description(domain_id: str, data: Dict[str, Any]):
    u"""NL→YAML: LLM generates ontology class draft from natural language description."""
    try:
        from core.api.core_facade import get_ontology_domain_schema, best_model_for_purpose, resolve_prompt

        description = data.get("description", "")
        target_class = data.get("target_class_name", "")
        if not description:
            raise HTTPException(status_code=400, detail="description is required")

        schema = get_ontology_domain_schema(domain_id)
        domain_context = schema.get("name", domain_id)
        existing_classes = ", ".join(list(schema.get("classes", {}).keys())[:10])

        prompt = resolve_prompt(
            "nl-to-ontology-class",
            domain_context=domain_context,
            existing_classes=existing_classes,
            description=description,
            target_class=target_class or "(auto)",
        )

        model = best_model_for_purpose("code_gen")
        response = await model.agenerate(prompt)
        text = getattr(response, "content", str(response))

        import json as _json
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if lines[0].startswith("```") else text
            if text.endswith("```"):
                text = text[:-3].strip()
        suggestion = _json.loads(text)

        return {"domain_id": domain_id, "suggestion": suggestion}
    except _json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="LLM returned invalid JSON")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")
