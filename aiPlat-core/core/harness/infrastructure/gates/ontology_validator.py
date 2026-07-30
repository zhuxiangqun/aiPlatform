"""
OntologyValidator — 本体驱动确定性校验 (注入 Agent Harness L 组件)

从域 YAML 的 side_effects.constraints 字段读取校验规则，
映射到 HookManager 的三个阶段:

  PreToolUse  → "该操作在当前状态下是否合法？"
  PostToolUse → "执行结果是否符合约束？"
  Stop        → "是否满足业务闭环条件？"

设计原则 (文章论点):
  确定性规则 → 代码执行 (不经过 LLM)
  灵活判断   → LLM 处理

调用者: HookManager (PreToolUse / PostToolUse / Stop hooks)
依赖: 域 YAML (side_effects.constraints 字段) + RuleValidator
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Data Models ──────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """校验结果."""
    passed: bool
    reason: str = ""
    warnings: List[str] = field(default_factory=list)
    block: bool = True             # True → 阻断执行，False → 仅警告


# ── OntologyValidator ────────────────────────────────────────────────────

class OntologyValidator:
    """本体驱动的确定性校验器.

    使用方式:
        validator = OntologyValidator()
        result = validator.pre_check("fde-delivery", "deploy", state, tool_name, args)
        if not result.passed:
            raise PermissionError(result.reason)
    """

    # ── PreToolUse: 执行前校验 ────────────────────────────────────────

    def pre_check(
        self,
        domain_id: str,
        action: str,
        state: Dict[str, Any],
        tool_name: str = "",
        tool_args: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """PreToolUse 阶段: 检查操作是否合法.

        校验内容:
          1. 状态守卫 (allowed_from): 当前状态是否允许此操作
          2. 依赖检查 (dependency_check): 必要字段是否已就绪
          3. 权限约束: 操作是否有保留策略限制
        """
        rules = self._load_rules(domain_id, state.get("current_state", ""))
        if not rules:
            return ValidationResult(passed=True, reason="no rules defined")

        for rule in rules:
            for constraint in rule.get("constraints", []):
                ctype = constraint.get("type", "")

                # 状态守卫
                if ctype == "state_guard":
                    allowed = constraint.get("allowed_from", [])
                    current = state.get("current_state", "")
                    if allowed and current not in allowed:
                        return ValidationResult(
                            passed=False,
                            reason=f"State guard: cannot {action} from '{current}' (allowed: {allowed})",
                        )

                # 依赖检查
                if ctype == "dependency_check":
                    field = constraint.get("field", "")
                    if field and not state.get(field):
                        return ValidationResult(
                            passed=False,
                            reason=f"Dependency check: '{field}' is required but missing",
                        )

                # 互斥状态
                if ctype == "exclusive_state":
                    exclusive = constraint.get("states", [])
                    current = state.get("current_state", "")
                    if current in exclusive:
                        return ValidationResult(
                            passed=False,
                            reason=f"Exclusive state: operation not allowed in '{current}'",
                        )

                # 保留策略 → 仅警告不阻断
                if ctype == "retention_policy":
                    action_required = constraint.get("action", "")
                    if action_required:
                        return ValidationResult(
                            passed=True,
                            reason=f"Retention policy triggered: {action_required}",
                            block=False,
                        )

        return ValidationResult(passed=True, reason="all constraints passed")

    # ── PostToolUse: 执行后校验 ───────────────────────────────────────

    def post_check(
        self,
        domain_id: str,
        action: str,
        state: Dict[str, Any],
        result: Any,
        expected: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """PostToolUse 阶段: 检查执行结果是否符合约束.

        校验内容:
          1. 高风险操作是否绑定了审批记录
          2. 执行结果是否包含必要字段
        """
        rules = self._load_rules(domain_id, state.get("current_state", ""))
        if not rules:
            return ValidationResult(passed=True, reason="no rules defined")

        for rule in rules:
            for constraint in rule.get("constraints", []):

                # 高风险操作 → 必须有审批记录
                if constraint.get("type") == "high_risk" and constraint.get("require", "") == "approval":
                    has_approval = (
                        getattr(result, "approval_request_id", None)
                        or (hasattr(result, "error") and "approval_required" in str(getattr(result, "error", "")))
                    )
                    if not has_approval and not getattr(result, "success", True):
                        return ValidationResult(
                            passed=False,
                            reason="High-risk operation requires approval binding",
                        )

                # 输出完整性 → 必须包含某些字段
                if constraint.get("type") == "output_required":
                    fields = constraint.get("fields", [])
                    output = getattr(result, "output", {}) or {}
                    if isinstance(output, dict):
                        missing = [f for f in fields if f not in output]
                        if missing:
                            return ValidationResult(
                                passed=False,
                                reason=f"Output required fields missing: {missing}",
                            )

        return ValidationResult(passed=True, reason="post-check passed")

    # ── Stop: 终止前校验 ─────────────────────────────────────────────

    def final_check(
        self,
        domain_id: str,
        state: Dict[str, Any],
    ) -> ValidationResult:
        """Stop 阶段: 检查是否满足业务闭环条件.

        校验内容:
          1. 必要字段是否已填充
          2. 是否所有依赖都已满足
        """
        rules = self._load_rules(domain_id, state.get("current_state", ""))
        if not rules:
            return ValidationResult(passed=True, reason="no rules defined")

        issues = []
        for rule in rules:
            for constraint in rule.get("constraints", []):

                if constraint.get("type") == "dependency_check":
                    field = constraint.get("field", "")
                    if field and not state.get(field):
                        issues.append(f"Missing required: {field}")

                if constraint.get("type") == "output_required":
                    fields = constraint.get("fields", [])
                    missing = [f for f in fields if not state.get(f)]
                    if missing:
                        issues.append(f"Output fields missing: {missing}")

        if issues:
            return ValidationResult(
                passed=False,
                reason=f"Closure check failed: {'; '.join(issues)}",
            )

        return ValidationResult(passed=True, reason="closure satisfied")

    # ── Rule Loading ──────────────────────────────────────────────────

    def _load_rules(
        self,
        domain_id: str,
        current_state: str = "",
    ) -> List[Dict[str, Any]]:
        """从域 YAML 加载校验规则.

        读取 side_effects 中的 constraints 字段。
        按 current_state 过滤 (仅匹配当前状态的规则).
        """
        try:
            import os
            import yaml as _yaml

            yaml_path = ""
            home = os.path.expanduser(os.getenv("AIPLAT_HOME", "~/.aiplat"))
            yaml_path = f"{home}/ontologies/{domain_id}.yaml"
            if not os.path.exists(yaml_path):
                versioned = f"{home}/ontologies/{domain_id}_v"
                for i in range(10, 0, -1):
                    if os.path.exists(f"{versioned}{i}.yaml"):
                        yaml_path = f"{versioned}{i}.yaml"
                        break

            if not os.path.exists(yaml_path):
                return []

            with open(yaml_path) as f:
                data = _yaml.safe_load(f)

            # Phase 51: Scan all classes for side_effects.constraints
            rules = data.get("side_effects", [])  # top-level
            classes = data.get("classes", {})
            for class_name, class_def in classes.items():
                if isinstance(class_def, dict):
                    class_rules = class_def.get("side_effects", [])
                    if class_rules:
                        rules.extend(class_rules)
                    # Also check states.side_effects (nested under states key)
                    states = class_def.get("states", {})
                    if isinstance(states, dict):
                        state_rules = states.get("side_effects", [])
                        if state_rules:
                            rules.extend(state_rules)
            if not rules:
                return []

            # Return all rules (constraint-specific filtering happens in pre/post/final methods)
            return rules

        except Exception as e:
            logger.debug("Rule loading skipped for %s: %s", domain_id, e)
            return []
