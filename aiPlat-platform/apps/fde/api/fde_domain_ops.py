"""FDE Domain Operations — expose domain ontology operations for Agent discovery (split from fde.py)."""
from __future__ import annotations

from typing import Any, Dict, List
from apps.fde.schemas import FdeStatusResponse, FdeListResponse, FdeItemResponse


from fastapi import APIRouter, HTTPException

import os

router = APIRouter(tags=["fde-domain-ops"])


@router.get("/domain/{domain}/operations", response_model=FdeItemResponse)
async def fde_domain_operations(domain: str):
    """Expose domain ontology operations for Agent discovery.

    Returns class properties, states, transitions, side effects,
    inference rules, and object properties.
    """
    import os as _os_do
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from .fde_governance import _list_available_domains

    path = _os_do.path.expanduser(f"~/.aiplat/ontologies/{domain}.yaml")
    if not _os_do.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail=f"Domain '{domain}' not found. Available: {_list_available_domains()}",
        )

    try:
        dom = load_ontology_from_yaml(path)
        classes = {}
        for cls in dom.classes:
            entry = {
                "label": cls.label,
                "uri": cls.uri,
                "required_fields": list(cls.required_fields or []),
                "optional_fields": list(cls.optional_fields or []),
                "categories": list(cls.allowed_categories or []),
            }

            states_cfg = getattr(cls, 'states', {}) or {}
            if states_cfg:
                entry["states"] = {
                    "default": states_cfg.get("default", ""),
                    "enum": [
                        {"name": s.get("name",""), "label": s.get("label",""), "description": s.get("description","")}
                        for s in states_cfg.get("enum", [])
                    ],
                    "transitions": [
                        {"from": t.get("from",""), "to": t.get("to",""),
                         "description": t.get("description",""), "trigger": t.get("trigger",{})}
                        for t in states_cfg.get("transitions", [])
                    ],
                }
                se_list = states_cfg.get("side_effects", [])
                if se_list:
                    entry["side_effects"] = se_list

            perms = getattr(cls, 'permissions', None)
            if perms:
                entry["permissions"] = perms

            classes[cls.label] = entry

        props = []
        for p in dom.object_properties:
            uri = getattr(p, 'uri', '')
            props.append({
                "name": uri.rsplit('/', 1)[-1] if '/' in uri else str(uri),
                "label": p.label,
                "domain": [d.rsplit('/', 1)[-1] for d in (p.domain or []) if '/' in d],
                "range": [r.rsplit('/', 1)[-1] for r in (p.range or []) if '/' in r],
            })

        rules = []
        for r in (dom.inference_rules or []):
            rules.append({
                "name": r.get("name",""), "description": r.get("description",""),
                "premises": r.get("premises",[]), "conclusion": r.get("conclusion",{}),
            })

        return {
            "domain": domain,
            "name": dom.name,
            "version": dom.version,
            "class_count": len(dom.classes),
            "property_count": len(props),
            "rule_count": len(rules),
            "classes": classes,
            "object_properties": props,
            "inference_rules": rules,
            "_usage": "Agent在执行前查询此端点，获取该域的业务对象、状态转换、推理规则和可用操作",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Domain operations failed: {str(e)[:300]}")
