"""
Action Contract Registry — Pydantic v2 models with security sandbox, YAML I/O, and
entity constraint validators (v3, 2026-07-29).

Extends the original 4 built-in actions with enterprise-grade fields:
  - Entity constraints: scope, domain_id, target_class, required_state, forbidden_states
  - Semantics: effect_semantics, compensation, risk_level
  - Approval: require_approval, approval_threshold, lock_on_pending
  - Handler security: module whitelist + dangerous keyword rejection
  - YAML sandbox: path whitelist for from_yaml()
"""
from __future__ import annotations

import os
import yaml
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# ═══════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════

class ActionScope(str, Enum):
    DOMAIN = "domain"
    CROSS_DOMAIN = "cross_domain"
    GLOBAL = "global"


class ActionCategory(str, Enum):
    MUTATION = "mutation"
    NOTIFICATION = "notification"
    REVIEW = "review"
    CASE_STUDY = "case_study"
    BUSINESS = "business"


class FailureStrategy(str, Enum):
    LOG_ONLY = "log_only"
    RETRY = "retry"
    BLOCK = "block_state_transition"
    ESCALATE = "escalate"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ═══════════════════════════════════════════════════════════
# Core Model
# ═══════════════════════════════════════════════════════════

class ActionContractModel(BaseModel):
    """Enterprise action contract with entity constraints, semantics, and security."""

    model_config = {"extra": "forbid"}

    # ── Identity ──
    action_id: str = Field(..., min_length=1, max_length=128)
    label: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    category: ActionCategory = ActionCategory.MUTATION

    # ── Entity constraints ──
    scope: ActionScope = ActionScope.DOMAIN
    domain_id: str = ""
    target_class: str = ""
    required_state: str = ""  # empty = any state
    forbidden_states: List[str] = Field(default_factory=list)
    lock_on_pending: bool = True

    # ── Semantics (human-readable) ──
    effect_semantics: str = ""
    compensation: str = ""
    risk_level: RiskLevel = RiskLevel.LOW

    # ── Schema (machine-validated) ──
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)

    # ── Permissions & approval ──
    required_permissions: List[str] = Field(default_factory=list)
    allowed_roles: List[str] = Field(default_factory=list)
    require_approval: bool = False
    approval_threshold: Optional[float] = None

    # ── Execution control ──
    handler: str = ""  # "module.path:function_name"
    rollback_action_id: str = ""
    retry_policy: Dict[str, Any] = Field(
        default_factory=lambda: {"max_retries": 1, "backoff_seconds": 5}
    )
    failure_strategy: FailureStrategy = FailureStrategy.LOG_ONLY
    max_concurrent: int = 0
    audit: bool = True
    preconditions: List[Dict] = Field(default_factory=list)

    # ═══ 决策节流（v3.1 — MSS 启示二：防橡皮图章效应）═══
    throttle_limit: int = Field(100, ge=0, description="每小时最大执行次数，0=不限")
    throttle_window_seconds: int = Field(3600, ge=1, description="统计时间窗口（秒）")
    throttle_block_on_breach: bool = Field(True, description="超限时是否阻断执行")
    throttle_bypass_roles: List[str] = Field(default_factory=list, description="豁免角色列表（如 admin）")

    # ═══════════════════════════════════════════════════════
    # Pydantic v2 Validators
    # ═══════════════════════════════════════════════════════

    @field_validator("handler")
    @classmethod
    def _validate_handler_security(cls, v: str) -> str:
        """Module whitelist — prevent arbitrary code execution (RCE).

        Handler format: "module.path:function_name".
        The module prefix (before ':') must be in the whitelist.
        """
        if not v:
            return v

        ALLOWED_PREFIXES = (
            "core.harness.ontology_engine.builtin_handlers",
            "custom_handlers",
        )
        # Extract module path (before the colon)
        module_part = v.rsplit(":", 1)[0] if ":" in v else v
        if not any(module_part == p or module_part.startswith(p + ".") for p in ALLOWED_PREFIXES):
            raise ValueError(
                f"Handler '{v}' not in allowed modules. "
                f"Module prefix must match: {ALLOWED_PREFIXES}"
            )

        DANGEROUS = ("os.", "sys.", "subprocess.", "shutil.", "builtins.")
        if any(kw in v for kw in DANGEROUS):
            raise ValueError(
                f"Handler '{v}' contains dangerous module reference"
            )
        return v

    @field_validator("required_state")
    @classmethod
    def _validate_state_consistency(cls, v: str, info) -> str:
        """required_state must not appear in forbidden_states."""
        forbidden = info.data.get("forbidden_states") or []
        if v and v in forbidden:
            raise ValueError(f"'{v}' is both required and forbidden")
        return v

    @field_validator("domain_id")
    @classmethod
    def _validate_domain_id(cls, v: str, info) -> str:
        """domain_id is required when scope=domain."""
        if info.data.get("scope") == ActionScope.DOMAIN and not v:
            raise ValueError("domain_id is required when scope is 'domain'")
        return v

    @field_validator("target_class")
    @classmethod
    def _validate_target_class(cls, v: str, info) -> str:
        """target_class is required when scope is domain or cross_domain."""
        scope = info.data.get("scope")
        if scope in (ActionScope.DOMAIN, ActionScope.CROSS_DOMAIN) and not v:
            raise ValueError("target_class is required when scope is 'domain' or 'cross_domain'")
        return v

    # ═══════════════════════════════════════════════════════
    # YAML I/O (business-user entry point)
    # ═══════════════════════════════════════════════════════

    def to_yaml(self) -> str:
        """Serialize to YAML string for human review."""
        data = self.model_dump(exclude_none=True, mode="python")
        for key, val in data.items():
            if isinstance(val, Enum):
                data[key] = val.value
        return yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)

    @classmethod
    def from_yaml(cls, path: str) -> "ActionContractModel":
        """Load from YAML file (path-whitelist sandbox)."""
        real_path = os.path.realpath(os.path.expanduser(path))

        ALLOWED_DIRS = [
            os.path.realpath("./config/actions/"),
            os.path.realpath(os.path.expanduser("~/.aiplat/actions/")),
        ]
        if not any(real_path.startswith(d) for d in ALLOWED_DIRS):
            raise ValueError(
                f"YAML path '{path}' resolves outside allowed directories: {ALLOWED_DIRS}"
            )

        if not os.path.exists(real_path):
            raise FileNotFoundError(f"YAML file not found: {real_path}")

        with open(real_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if isinstance(raw, dict) and "actions" in raw:
            actions_list = raw["actions"]
            if not isinstance(actions_list, list):
                raise ValueError("'actions' key must contain a list")
            if len(actions_list) == 1:
                data = actions_list[0]
            else:
                raise ValueError(
                    f"YAML contains {len(actions_list)} actions. "
                    "Use register_from_yaml for batch loading."
                )
        else:
            data = raw

        return cls.model_validate(data)

    @classmethod
    def from_yaml_batch(cls, path: str) -> List["ActionContractModel"]:
        """Load multiple actions from a YAML file (batch mode)."""
        real_path = os.path.realpath(os.path.expanduser(path))

        ALLOWED_DIRS = [
            os.path.realpath("./config/actions/"),
            os.path.realpath(os.path.expanduser("~/.aiplat/actions/")),
        ]
        if not any(real_path.startswith(d) for d in ALLOWED_DIRS):
            raise ValueError(f"Path '{path}' outside allowed directories")

        if not os.path.exists(real_path):
            raise FileNotFoundError(f"YAML file not found: {real_path}")

        with open(real_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        actions = raw.get("actions", [raw])
        if not isinstance(actions, list):
            actions = [actions]

        return [cls.model_validate(a) for a in actions]
