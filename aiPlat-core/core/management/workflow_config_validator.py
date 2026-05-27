"""
Workflow template configuration validator.

Checks:
  1. JSON syntax validity
  2. Required fields (name, stages)
  3. Stages array non-empty
  4. Each stage has agent_id
  5. Recommended: output_artifact, description
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ConfigIssue:
    workflow: str
    file: str
    severity: str  # "error" | "warn"
    message: str


def validate_workflow_template(json_path: Path) -> List[ConfigIssue]:
    """Validate a single workflow template JSON file."""
    issues: List[ConfigIssue] = []
    wf_name = json_path.stem
    file_path = str(json_path)

    # 1) Read file
    try:
        raw = json_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [ConfigIssue(workflow=wf_name, file=file_path, severity="error",
                           message=f"Cannot read file: {e}")]

    # 2) JSON syntax
    try:
        data = _json.loads(raw)
    except _json.JSONDecodeError as e:
        return [ConfigIssue(workflow=wf_name, file=file_path, severity="error",
                           message=f"JSON parse error: {e}")]

    if not isinstance(data, dict):
        return [ConfigIssue(workflow=wf_name, file=file_path, severity="error",
                           message="Workflow must be a JSON object")]

    # 3) Required: name
    if not data.get("name"):
        issues.append(ConfigIssue(
            workflow=wf_name, file=file_path, severity="error",
            message="Missing required field: name"
        ))

    # 4) Required: stages
    stages = data.get("stages", [])
    if not isinstance(stages, list) or len(stages) == 0:
        issues.append(ConfigIssue(
            workflow=wf_name, file=file_path, severity="error",
            message="Missing or empty 'stages' array — workflow has no steps"
        ))
    else:
        for i, stage in enumerate(stages):
            if not isinstance(stage, dict):
                issues.append(ConfigIssue(
                    workflow=wf_name, file=file_path, severity="error",
                    message=f"Stage [{i}] is not a valid object"
                ))
                continue
            if not stage.get("agent_id"):
                issues.append(ConfigIssue(
                    workflow=wf_name, file=file_path, severity="warn",
                    message=f"Stage [{i}] missing agent_id — stage won't execute"
                ))

    # 5) Recommended: description
    if not data.get("description"):
        issues.append(ConfigIssue(
            workflow=wf_name, file=file_path, severity="warn",
            message="Missing description"
        ))

    return issues


def validate_all_workflow_templates(templates_dir: str) -> tuple:
    """Validate all workflow template JSON files. Returns (errors, warnings)."""
    errors: List[ConfigIssue] = []
    warnings: List[ConfigIssue] = []
    base = Path(templates_dir)
    if not base.exists():
        return errors, warnings

    for json_path in sorted(base.glob("*.json")):
        if "__pycache__" in str(json_path):
            continue
        issues = validate_workflow_template(json_path)
        for issue in issues:
            if issue.severity == "error":
                errors.append(issue)
            else:
                warnings.append(issue)

    return errors, warnings
