"""
Rule Designer — NL to inference rule translation, validation, and deployment.

Phase F: AI-assisted business rule design.
  - design_rule(domain_id, nl_text) → NL → structured rule YAML
  - validate_rule(domain_id, rule)   → schema validation + warnings
  - deploy_rule(domain_id, rule)      → append to domain YAML + GraphInference
  - list_rules(domain_id)             → list existing rules
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml as _yaml

from .rule_prompt import build_rule_design_prompt

logger = logging.getLogger(__name__)


def validate_rule(domain_id: str, rule: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a rule against the domain ontology schema.

    Checks: name uniqueness, premises count, relation validity, confidence range.

    Returns: {"valid": bool, "errors": [str], "warnings": [str]}
    """
    domain = _load_domain(domain_id)
    errors = []
    warnings = []

    if not domain:
        return {"valid": False, "errors": [f"Domain '{domain_id}' not found"], "warnings": []}

    # Check required fields
    for field in ("name", "premises", "conclusion"):
        if field not in rule:
            errors.append(f"Missing required field: {field}")

    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings}

    # Check name uniqueness
    existing = domain.get("inference_rules", [])
    if isinstance(existing, list):
        for r in existing:
            if isinstance(r, dict) and r.get("name") == rule["name"]:
                warnings.append(f"Rule name '{rule['name']}' already exists — will overwrite on deploy")
                break

    # Check premises count
    premises = rule.get("premises", [])
    if not isinstance(premises, list) or len(premises) < 2:
        errors.append(f"premises must have at least 2 items, got {len(premises)}")
    elif len(premises) > 4:
        warnings.append(f"premises has {len(premises)} items — recommended ≤ 4 to avoid over-inference")

    # Check relation validity
    obj_props = domain.get("object_properties", [])
    valid_relations = {op.get("name", "") for op in obj_props if isinstance(op, dict)}
    for p in premises:
        if isinstance(p, dict):
            rel = p.get("relation", "")
            if rel and rel not in valid_relations:
                warnings.append(f"relation '{rel}' is not in domain object_properties — inference may not produce edges")

    # Check conclusion
    conclusion = rule.get("conclusion", {})
    if isinstance(conclusion, dict):
        conf = conclusion.get("confidence", 1.0)
        if not isinstance(conf, (int, float)) or not 0 < conf <= 1.0:
            errors.append(f"conclusion.confidence must be 0-1, got {conf}")
        crel = conclusion.get("relation", "")
        if crel and crel not in valid_relations:
            warnings.append(f"conclusion relation '{crel}' is not in domain object_properties")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def design_rule(
    domain_id: str, nl_text: str, *, model: Any = None
) -> Dict[str, Any]:
    """Translate natural language business requirement into a structured rule.

    1. Builds domain-aware prompt
    2. Calls LLM to generate YAML rule
    3. Validates the generated rule
    4. Returns rule + validation + existing related rules

    Args:
        domain_id: Domain ID (e.g. "ai-knowledge")
        nl_text: Natural language business requirement
        model: Optional LLM adapter (uses best_model_for_purpose if None)

    Returns:
        {"rule": dict, "validation": {...}, "existing_related": [...], "domain": str}
    """
    # Build prompt
    prompt_info = build_rule_design_prompt(domain_id, user_input=nl_text)
    if prompt_info.get("error"):
        return {"error": prompt_info["error"], "domain": domain_id}

    # Try LLM generation
    rule_yaml_text = ""
    try:
        if model is None:
            from core.harness.utils.model_injection import best_model_for_purpose, create_selected_adapter
            model_name = best_model_for_purpose("doc_llm")
            if model_name:
                model = create_selected_adapter(model_name=model_name)

        if model:
            messages = [
                {"role": "system", "content": prompt_info["system_prompt"]},
                {"role": "user", "content": prompt_info["user_prompt"]},
            ]
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, model.generate(messages))
                    response = future.result(timeout=30)
            else:
                response = asyncio.run(model.generate(messages))
            rule_yaml_text = getattr(response, "content", "") or str(response)
        else:
            return {
                "error": "No LLM model available for rule generation. Set AIPLAT_LLM_MODEL.",
                "domain": domain_id,
            }
    except Exception as e:
        logger.warning("LLM rule generation failed: %s. Returning prompt-only response.", e)
        return {
            "rule": None,
            "validation": {"valid": False, "errors": [], "warnings": []},
            "existing_related": [],
            "domain": domain_id,
            "prompt": prompt_info,
            "error": f"LLM generation failed: {e}",
        }

    # Parse YAML from LLM response
    rule = _parse_rule_yaml(rule_yaml_text)

    # Validate
    validation = validate_rule(domain_id, rule) if rule else {"valid": False, "errors": ["Failed to parse rule from LLM response"], "warnings": []}

    # Find existing related rules
    existing = _get_existing_rules(domain_id)
    related = []
    if rule:
        rule_name = rule.get("name", "")
        rule_desc = rule.get("description", "")
        for er in existing:
            er_name = er.get("name", "")
            er_desc = er.get("description", "")
            # Simple overlap check
            if (rule_name and er_name and any(w in er_name for w in rule_name.split("_"))) or \
               (rule_desc and er_desc and len(set(rule_desc) & set(er_desc)) > 5):
                related.append({"name": er_name, "description": er_desc})

    return {
        "rule": rule,
        "validation": validation,
        "existing_related": related,
        "domain": domain_id,
        "prompt": prompt_info,
    }


def deploy_rule(domain_id: str, rule: Dict[str, Any]) -> Dict[str, Any]:
    """Deploy a rule to the domain YAML file and GraphInference runtime.

    1. Validates rule
    2. Appends/overwrites in domain YAML
    3. Reloads GraphInference rules (next infer() call picks it up)

    Returns: {"deployed": bool, "domain": str, "rule_name": str, "validation": {...}}
    """
    validation = validate_rule(domain_id, rule)
    if not validation["valid"]:
        return {
            "deployed": False,
            "domain": domain_id,
            "rule_name": rule.get("name", ""),
            "validation": validation,
            "error": "Rule validation failed",
        }

    path = Path(os.path.expanduser(f"~/.aiplat/ontologies/{domain_id}.yaml"))
    if not path.exists():
        return {
            "deployed": False,
            "domain": domain_id,
            "rule_name": rule.get("name", ""),
            "error": f"Domain file not found: {path}",
        }

    domain = _load_domain(domain_id)
    if not domain:
        return {"deployed": False, "error": f"Domain '{domain_id}' not found"}

    # Append or update rule
    existing_rules = domain.get("inference_rules", [])
    if not isinstance(existing_rules, list):
        existing_rules = []

    # Overwrite or append
    updated = False
    rule_name = rule.get("name", "")
    for i, er in enumerate(existing_rules):
        if isinstance(er, dict) and er.get("name") == rule_name:
            existing_rules[i] = rule
            updated = True
            break
    if not updated:
        existing_rules.append(rule)

    domain["inference_rules"] = existing_rules

    # Write back to YAML
    path.write_text(_yaml.dump(domain, allow_unicode=True, default_flow_style=False, sort_keys=False), encoding="utf-8")

    logger.info("Rule '%s' deployed to domain '%s'", rule_name, domain_id)

    return {
        "deployed": True,
        "domain": domain_id,
        "rule_name": rule_name,
        "validation": validation,
        "total_rules": len(existing_rules),
    }


def list_rules(domain_id: str) -> Dict[str, Any]:
    """List all inference rules for a domain, with metadata."""
    domain = _load_domain(domain_id)
    if not domain:
        return {"error": f"Domain '{domain_id}' not found"}

    rules = domain.get("inference_rules", [])
    if not isinstance(rules, list):
        rules = []

    return {
        "domain": domain_id,
        "domain_name": domain.get("name", domain_id),
        "count": len(rules),
        "rules": [
            {
                "name": r.get("name", ""),
                "description": r.get("description", ""),
                "premises_count": len(r.get("premises", [])),
                "conclusion": r.get("conclusion", {}).get("relation", ""),
            }
            for r in rules if isinstance(r, dict)
        ],
    }


# ── Helpers ──

def _load_domain(domain_id: str) -> Optional[Dict[str, Any]]:
    path = Path(os.path.expanduser(f"~/.aiplat/ontologies/{domain_id}.yaml"))
    if not path.exists():
        return None
    try:
        return _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None


def _get_existing_rules(domain_id: str) -> List[Dict[str, Any]]:
    domain = _load_domain(domain_id)
    if not domain:
        return []
    rules = domain.get("inference_rules", [])
    return [r for r in rules if isinstance(r, dict)]


def _parse_rule_yaml(text: str) -> Dict[str, Any]:
    """Extract rule YAML from LLM response (may contain markdown wrapping)."""
    # Strip markdown code fences
    if "```" in text:
        parts = text.split("```")
        for i, part in enumerate(parts):
            if i % 2 == 1:
                part = part.strip()
                if part.startswith("yaml") or part.startswith("yml"):
                    part = part[4:].strip()
                try:
                    return _yaml.safe_load(part) or {}
                except Exception:
                    continue

    # Try plain YAML
    try:
        return _yaml.safe_load(text) or {}
    except Exception:
        # Try extracting YAML block between markers
        import re
        match = re.search(r"\{.*\"name\".*\}", text, re.DOTALL)
        if match:
            try:
                import json
                return json.loads(match.group())
            except Exception:
                logging.getLogger(__name__).debug('_parse_rule_yaml failed', exc_info=True)
    return {}


__all__ = ["design_rule", "validate_rule", "deploy_rule", "list_rules"]
