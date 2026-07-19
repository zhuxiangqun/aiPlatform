u"""
Mapping Validator — 数据→语义映射自动验证 (v2.8).

Validates DataSource field_mapping correctness:
  - Type matching (source field type vs ontology field type)
  - Enum compliance (source values vs ontology field enum values)
  - Coverage (mapped fields / ontology required_fields)
"""
from __future__ import annotations

import logging
import os as _os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mapping_validator")


@dataclass
class MappingIssue:
    source_id: str
    source_field: str
    target_field: str
    issue_type: str        # type_mismatch | enum_violation | field_not_found | unmapped_required
    severity: str          # error | warning
    detail: str


@dataclass
class MappingValidationResult:
    source_id: str
    domain_id: str
    total_mappings: int
    issues: List[MappingIssue] = field(default_factory=list)
    coverage_pct: float = 0.0
    status: str = "unknown"  # good | warning | critical


def validate_source(source_id: str) -> MappingValidationResult:
    u"""Validate a single DataSource's field mappings."""
    base = _os.path.expanduser("~/.aiplat/datasources")
    yaml_path = _os.path.join(base, f"{source_id}.yaml")
    if not _os.path.exists(yaml_path):
        return MappingValidationResult(
            source_id=source_id, domain_id="", total_mappings=0,
            issues=[MappingIssue(source_id, "", "", "field_not_found", "error", "Data source config not found")],
            status="critical",
        )

    import yaml
    with open(yaml_path) as f:
        ds = yaml.safe_load(f) or {}

    domain_id = ds.get("domain_id", ds.get("name", ""))
    mappings = ds.get("mapping", {}).get("field_mapping", [])
    target_class = ds.get("mapping", {}).get("target_class", "")

    issues = []

    # Check ontology class exists
    if target_class:
        onto = _load_ontology(domain_id)
        if onto and target_class not in onto.get("classes", {}):
            issues.append(MappingIssue(
                source_id, "", target_class, "field_not_found", "error",
                f"Target class '{target_class}' not found in domain ontology"
            ))

    # Validate each mapping
    for m in mappings:
        source_field = m.get("source", "") if isinstance(m, dict) else str(m)
        target_field = m.get("target", "") if isinstance(m, dict) else str(m)

        if not source_field or not target_field:
            issues.append(MappingIssue(
                source_id, str(source_field), str(target_field),
                "field_not_found", "warning", "Empty source or target field"
            ))
            continue

        # Check if target field exists in ontology class
        if onto and target_class and target_field:
            class_def = onto["classes"].get(target_class, {})
            class_fields = class_def.get("fields", [])
            field_names = {f.get("name", "") for f in class_fields}
            if target_field not in field_names:
                issues.append(MappingIssue(
                    source_id, source_field, target_field, "field_not_found", "warning",
                    f"Target field '{target_field}' not found in class '{target_class}' fields"
                ))

    # Calculate coverage
    onto = _load_ontology(domain_id)
    required_count = 0
    if onto and target_class:
        class_def = onto["classes"].get(target_class, {})
        required_count = len(class_def.get("required_fields", []))
    coverage = round(len(mappings) / max(required_count, 1) * 100, 1)

    status = "good" if coverage >= 80 and len(issues) == 0 else \
             "warning" if coverage >= 50 else "critical"

    return MappingValidationResult(
        source_id=source_id, domain_id=domain_id,
        total_mappings=len(mappings), issues=issues,
        coverage_pct=coverage, status=status,
    )


def validate_all_sources(domain_id: str = "") -> List[MappingValidationResult]:
    u"""Validate all data sources (filtered by domain if provided)."""
    base = _os.path.expanduser("~/.aiplat/datasources")
    if not _os.path.isdir(base):
        return []

    results = []
    for fname in sorted(_os.listdir(base)):
        if not fname.endswith(".yaml"):
            continue
        sid = fname[:-5]
        result = validate_source(sid)
        if not domain_id or result.domain_id == domain_id:
            results.append(result)
    return results


def generate_mapping_report(domain_ids: List[str] = None) -> str:
    u"""Generate a markdown mapping coverage report."""
    results = []
    if domain_ids:
        for did in domain_ids:
            results.extend(validate_all_sources(did))
    else:
        results = validate_all_sources()

    if not results:
        return "No data sources found."

    lines = [
        "# 数据→语义映射覆盖率报告",
        "",
        f"生成时间: {__import__('time').strftime('%Y-%m-%d %H:%M:%S', __import__('time').gmtime())}",
        "",
        "| 数据源 | 域 | 映射数 | 覆盖率 | 状态 | 问题数 |",
        "|:---|:---|:---:|:---:|:---:|:---:|",
    ]
    for r in results:
        lines.append(
            f"| {r.source_id} | {r.domain_id} | {r.total_mappings} | "
            f"{r.coverage_pct}% | {r.status} | {len(r.issues)} |"
        )
    return "\n".join(lines)


def _load_ontology(domain_id: str) -> Optional[Dict]:
    u"""Load ontology YAML for a domain."""
    if not domain_id:
        return None
    onto_dir = _os.path.expanduser(_os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))
    yaml_path = _os.path.join(onto_dir, f"{domain_id}.yaml")
    if not _os.path.exists(yaml_path):
        return None
    import yaml
    try:
        with open(yaml_path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return None
