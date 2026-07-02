"""
Rule Design Prompt — builds domain-aware LLM prompts for inference rule generation.

Reads a domain ontology YAML to inject classes, relations, and existing rules
as context for the LLM, ensuring generated rules are domain-valid and non-duplicate.

Usage:
    from core.harness.ontology_engine.rule_prompt import build_rule_design_prompt
    prompt = build_rule_design_prompt("ai-knowledge")
    # → multi-line system prompt with domain context
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml as _yaml


def _load_domain(domain_id: str) -> Optional[Dict[str, Any]]:
    """Load domain ontology YAML from ~/.aiplat/ontologies/{domain_id}.yaml."""
    path = Path(os.path.expanduser(f"~/.aiplat/ontologies/{domain_id}.yaml"))
    if not path.exists():
        return None
    try:
        return _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None


def build_rule_design_prompt(domain_id: str, *, user_input: str = "") -> Dict[str, Any]:
    """Build a domain-aware system prompt for rule generation.

    Returns:
        {
            "system_prompt": str,
            "user_prompt": str,
            "domain": domain_name,
            "context": {classes_count, relations_count, existing_rules_count}
        }
    """
    domain = _load_domain(domain_id)
    if not domain:
        return {
            "system_prompt": "",
            "user_prompt": user_input,
            "domain": domain_id,
            "error": f"Domain '{domain_id}' not found",
            "context": {},
        }

    name = domain.get("name", domain_id)
    desc = domain.get("description", "")

    # Collect classes
    classes = domain.get("classes", {})
    class_names = list(classes.keys()) if isinstance(classes, dict) else []

    # Collect object_properties (relations)
    obj_props = domain.get("object_properties", [])
    relation_names = []
    for op in obj_props:
        if isinstance(op, dict):
            rname = op.get("name", "")
            rlabel = op.get("label", "")
            if rname:
                relation_names.append(f"{rname} ({rlabel})" if rlabel else rname)

    # Collect existing inference rules
    existing_rules = domain.get("inference_rules", [])
    existing_names = []
    if isinstance(existing_rules, list):
        for r in existing_rules:
            if isinstance(r, dict):
                rn = r.get("name", "")
                rd = r.get("description", "")
                if rn:
                    existing_names.append(f"{rn} — {rd}" if rd else rn)

    # Build system prompt
    lines = [
        "你是企业业务规则设计助手。",
        f"当前域: {name} (ID: {domain_id})",
    ]
    if desc:
        lines.append(f"域描述: {desc}")

    lines.extend([
        "",
        f"已有类 ({len(class_names)}): {', '.join(class_names[:30])}",
        f"已有关系 ({len(relation_names)}): {', '.join(relation_names[:20])}",
    ])

    if existing_names:
        lines.extend([
            "",
            f"已有推理规则 ({len(existing_names)} 条，请避免重复):",
        ])
        for en in existing_names[:15]:
            lines.append(f"  - {en}")

    lines.extend([
        "",
        "请将以下业务需求转换为推理规则。规则格式（YAML）：",
        "  name: 英文snake_case唯一名",
        "  description: 中文描述",
        "  premises: [{relation: 关系名, direction: outgoing|incoming}, ...]",
        "  conclusion: {relation: 推断关系名, label: 中文标签, confidence: 0.7-1.0}",
        "",
        "约束:",
        "  - relation 必须是上面列出的已有关系名之一",
        "  - premises 数量: 2-4 个",
        "  - confidence: 0.7-1.0 之间",
        "  - name 不能与已有规则名重复",
        "  - 返回纯 YAML 格式，无需额外解释",
    ])

    system_prompt = "\n".join(lines)
    user_prompt = f"业务需求: {user_input}" if user_input else "请等待用户输入业务需求。"

    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "domain": name,
        "context": {
            "classes_count": len(class_names),
            "relations_count": len(relation_names),
            "existing_rules_count": len(existing_names),
        },
    }


__all__ = ["build_rule_design_prompt"]
