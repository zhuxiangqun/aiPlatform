"""
Evaluation policy (weights + thresholds)

Used by evaluator workbench / auto-eval to keep scoring consistent and tunable.
Persisted as a LearningArtifact(kind=evaluation_policy, target_type=system).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


DEFAULT_POLICY = {
    "schema_version": "0.1",
    "thresholds": {"functionality_min": 7.0},
    "weights": {"functionality": 0.55, "product_depth": 0.2, "design_ux": 0.15, "code_architecture": 0.1},
    # evidence capture anti-flaky controls (best-effort)
    # max_retries=1 means: 1 initial attempt + 1 retry on non-HTTP failures
    "evidence_capture": {"max_retries": 1},
    # canary escalation (P1-1)
    # - enabled: whether canary failures should be recorded into Change Control
    # - p0_only: only escalate when there is at least one P0 issue (recommended)
    # - consecutive_failures: escalate only after N consecutive failures (recommended: 2)
    "canary": {"escalate": {"enabled": True, "p0_only": True, "consecutive_failures": 2}},
    # regression gate (based on evidence_diff)
    # default is strict: any new console error or new 5xx is a regression
    "regression_gate": {
        "max_new_console_errors": 0,
        "max_new_network_5xx": 0,
        "max_new_network_4xx": 5,
        # coverage: require these tags to be executed when doing browser evidence
        "required_tags": ["login", "create", "save"],
        # visual regression (screenshot hash changes); default off (set small number to enable)
        "max_changed_screenshot_tags": 999,
    },
    # reusable tag assertion templates (versionable in evaluation_policy)
    # each template can provide expected_tags + tag_expectations
    "default_tag_template": "webapp_basic",
    "tag_templates": {
        "webapp_basic": {
            "expected_tags": ["login", "create", "save"],
            "tag_expectations": {
                "login": {"text_contains": ["登录"], "max_console_errors": 0, "max_network_5xx": 0, "max_duration_ms": 8000},
                "create": {"max_console_errors": 0, "max_network_5xx": 0},
                "save": {"max_console_errors": 0, "max_network_5xx": 0},
            },
        }
    },
}


@dataclass
class EvaluationPolicy:
    schema_version: str = "0.1"
    thresholds: Dict[str, Any] = None  # type: ignore[assignment]
    weights: Dict[str, float] = None  # type: ignore[assignment]
    evidence_capture: Dict[str, Any] = None  # type: ignore[assignment]
    canary: Dict[str, Any] = None  # type: ignore[assignment]
    regression_gate: Dict[str, Any] = None  # type: ignore[assignment]
    default_tag_template: str = "webapp_basic"
    tag_templates: Dict[str, Any] = None  # type: ignore[assignment]

    @classmethod
    def from_dict(cls, obj: Optional[Dict[str, Any]]) -> "EvaluationPolicy":
        src = obj or {}
        out = DEFAULT_POLICY.copy()
        if isinstance(src.get("schema_version"), str):
            out["schema_version"] = src["schema_version"]
        if isinstance(src.get("thresholds"), dict):
            out["thresholds"] = src["thresholds"]
        if isinstance(src.get("weights"), dict):
            w = {}
            for k, v in src["weights"].items():
                try:
                    w[str(k)] = float(v)
                except Exception:
                    continue
            if w:
                out["weights"] = w
        if isinstance(src.get("evidence_capture"), dict):
            out["evidence_capture"] = src["evidence_capture"]
        if isinstance(src.get("canary"), dict):
            out["canary"] = src["canary"]
        if isinstance(src.get("regression_gate"), dict):
            out["regression_gate"] = src["regression_gate"]
        if isinstance(src.get("default_tag_template"), str):
            out["default_tag_template"] = src["default_tag_template"]
        if isinstance(src.get("tag_templates"), dict):
            out["tag_templates"] = src["tag_templates"]
        return cls(
            schema_version=str(out["schema_version"]),
            thresholds=dict(out["thresholds"]),
            weights=dict(out["weights"]),
            evidence_capture=dict(out.get("evidence_capture") or {}),
            canary=dict(out.get("canary") or {}),
            regression_gate=dict(out.get("regression_gate") or {}),
            default_tag_template=str(out.get("default_tag_template") or "webapp_basic"),
            tag_templates=dict(out.get("tag_templates") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "thresholds": self.thresholds or {},
            "weights": self.weights or {},
            "evidence_capture": self.evidence_capture or DEFAULT_POLICY.get("evidence_capture") or {},
            "canary": self.canary or DEFAULT_POLICY.get("canary") or {},
            "regression_gate": self.regression_gate or DEFAULT_POLICY.get("regression_gate") or {},
            "default_tag_template": str(self.default_tag_template or DEFAULT_POLICY.get("default_tag_template") or "webapp_basic"),
            "tag_templates": self.tag_templates or DEFAULT_POLICY.get("tag_templates") or {},
        }


def merge_policy(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge override onto base (dict-only). Lists are replaced.
    """
    if not isinstance(base, dict):
        base = {}
    if not isinstance(override, dict):
        override = {}

    def _merge(a: Any, b: Any) -> Any:
        if isinstance(a, dict) and isinstance(b, dict):
            out = dict(a)
            for k, v in b.items():
                if k in out:
                    out[k] = _merge(out[k], v)
                else:
                    out[k] = v
            return out
        # replace
        return b

    return _merge(dict(base), dict(override))
