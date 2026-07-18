u"""
Action Contract Registry — 动作契约形式化 (v2.7).

Defines formal I/O schemas for all side-effect actions:
  - add_tag, call_webhook, mark_related_for_review, inject_case_study

Each action has: input_schema (JSON Schema), output_schema, permissions, 
preconditions, retry policy, failure_strategy, and a handler reference.
"""
from __future__ import annotations

import importlib
import json as _json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("action_contract")


@dataclass
class ActionContract:
    u"""Formal contract for a side-effect action."""
    action_id: str
    label: str
    description: str = ""
    category: str = "mutation"              # mutation | notification | review | case_study
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    required_permissions: List[str] = field(default_factory=list)
    preconditions: List[Dict] = field(default_factory=list)
    retry_policy: Dict[str, Any] = field(default_factory=dict)
    failure_strategy: str = "log_only"      # log_only | retry | escalate | block_state_transition
    audit: bool = True
    handler: str = ""                       # "module.path:function_name"


class ActionRegistry:
    u"""Global registry of all side-effect action contracts."""

    def __init__(self):
        self._contracts: Dict[str, ActionContract] = {}
        self._handlers: Dict[str, callable] = {}

    def register(self, contract: ActionContract) -> None:
        u"""Register an action contract. Validates handler existence at registration time."""
        self._contracts[contract.action_id] = contract
        if contract.handler:
            self._resolve_handler(contract)
        logger.debug("Action registered: %s", contract.action_id)

    def get(self, action_id: str) -> Optional[ActionContract]:
        return self._contracts.get(action_id)

    def list_all(self) -> List[ActionContract]:
        return list(self._contracts.values())

    def validate_params(self, action_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        u"""Validate action params against the contract's input_schema.

        Returns: {"valid": bool, "errors": [...]}
        """
        contract = self._contracts.get(action_id)
        if not contract:
            return {"valid": False, "errors": [f"Unknown action: {action_id}"]}
        schema = contract.input_schema
        if not schema:
            return {"valid": True, "errors": []}
        try:
            import jsonschema
            jsonschema.validate(params, schema)
            return {"valid": True, "errors": []}
        except ImportError:
            # Basic validation: check required fields
            errors = []
            for req in schema.get("required", []):
                if req not in params:
                    errors.append(f"Missing required field: {req}")
            return {"valid": len(errors) == 0, "errors": errors}
        except Exception as e:
            return {"valid": False, "errors": [str(e)]}

    def get_handler(self, action_id: str):
        u"""Get the callable handler for an action."""
        if action_id in self._handlers:
            return self._handlers[action_id]
        contract = self._contracts.get(action_id)
        if contract and contract.handler:
            return self._resolve_handler(contract)
        return None

    def _resolve_handler(self, contract: ActionContract):
        u"""Import and cache the handler from its class-path string."""
        if not contract.handler:
            return None
        try:
            mod_path, func_name = contract.handler.rsplit(".", 1)
            module = importlib.import_module(mod_path)
            handler = getattr(module, func_name, None)
            if handler is None:
                raise ValueError(
                    f"Handler '{func_name}' not found in {mod_path} "
                    f"for action '{contract.action_id}'"
                )
            self._handlers[contract.action_id] = handler
            return handler
        except Exception as e:
            logger.error(
                "Failed to resolve handler for action '%s': %s",
                contract.action_id, e
            )
            return None


# ── Global singleton ──
_registry: Optional[ActionRegistry] = None


def get_action_registry() -> ActionRegistry:
    global _registry
    if _registry is None:
        _registry = ActionRegistry()
        _register_builtins(_registry)
    return _registry


def _register_builtins(registry: ActionRegistry) -> None:
    u"""Register the 4 built-in side-effect actions."""
    registry.register(ActionContract(
        action_id="add_tag",
        label="添加标签",
        description="向实例 frontmatter 追加标签",
        category="mutation",
        input_schema={
            "type": "object",
            "required": ["tag"],
            "properties": {"tag": {"type": "string", "description": "标签名称"}},
        },
        output_schema={"type": "object", "properties": {"success": {"type": "boolean"}}},
        required_permissions=["execute"],
        failure_strategy="log_only",
        handler="",
    ))

    registry.register(ActionContract(
        action_id="call_webhook",
        label="Webhook 回调",
        description="向外部业务系统发送 HTTP POST 通知",
        category="notification",
        input_schema={
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string", "format": "uri"},
                "payload": {"type": "object"},
            },
        },
        output_schema={"type": "object", "properties": {"status_code": {"type": "integer"}}},
        required_permissions=["execute"],
        retry_policy={"max_retries": 1, "backoff_seconds": 5},
        failure_strategy="log_only",
        handler="",
    ))

    registry.register(ActionContract(
        action_id="mark_related_for_review",
        label="标记关联实体复审",
        description="将关联实体加入审查队列",
        category="review",
        input_schema={
            "type": "object",
            "properties": {
                "relation": {"type": "string"},
                "message": {"type": "string"},
            },
        },
        output_schema={"type": "object", "properties": {"affected_count": {"type": "integer"}}},
        required_permissions=["execute", "approve"],
        failure_strategy="log_only",
        handler="",
    ))

    registry.register(ActionContract(
        action_id="inject_case_study",
        label="注入案例研究",
        description="基于模板创建案例研究实体",
        category="case_study",
        input_schema={
            "type": "object",
            "required": ["template"],
            "properties": {
                "template": {"type": "string"},
                "relation_name": {"type": "string"},
                "relation_label": {"type": "string"},
            },
        },
        output_schema={"type": "object", "properties": {"case_name": {"type": "string"}}},
        required_permissions=["execute", "write"],
        failure_strategy="log_only",
        handler="",
    ))

    logger.info("ActionRegistry: %d built-in actions registered", len(registry.list_all()))
