"""知识系统 Agent 工具面（附录 F.2 最小切片）。

提供 ``object.query`` / ``function.call`` / ``link.traverse`` /
``object_set.aggregate`` / ``action.execute``，一律经 CoreFacade；
禁止通用 SQL / 直写 Fact。
非目标：SDK 生成见 ``sdk_generator``（不在本工具面实现）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.apps.tools.base import BaseTool, ToolResult
from core.harness.interfaces import ToolConfig

logger = logging.getLogger(__name__)

_FORBIDDEN_KEYS = frozenset(
    {
        "sql",
        "raw_sql",
        "query_sql",
        "write_fact",
        "mutate",
        "insert",
        "update",
        "delete",
    }
)


def _reject_sql_or_write(params: Dict[str, Any]) -> Optional[str]:
    """若入参含 SQL/写路径键则返回拒绝原因。

    Args:
        params: 工具入参。
    """
    for k in params or {}:
        if str(k).lower() in _FORBIDDEN_KEYS:
            return f"sql_or_write_forbidden:{k}"
    return None


def _parse_permissions(params: Dict[str, Any]) -> Optional[List[str]]:
    """从 params 提取 permissions/scopes 列表。

    Args:
        params: 工具入参。
    """
    raw = params.get("permissions")
    if raw is None:
        raw = params.get("scopes")
    if raw is None:
        return None
    if isinstance(raw, str):
        return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    if isinstance(raw, list):
        return [str(p).strip() for p in raw if str(p).strip()]
    return None


async def _facade_query_object_set(
    request: Dict[str, Any],
    *,
    tenant_id: str,
    permissions: Optional[List[str]] = None,
    role: str = "",
) -> Dict[str, Any]:
    """经 CoreFacade 查询 ObjectSet（可被单测 monkeypatch）。

    Args:
        request: E.1 请求 dict。
        tenant_id: 租户。
        permissions: 权限/scopes。
        role: 角色（ABox ACL）。
    """
    from core.api.core_facade import query_object_set

    return await query_object_set(
        request, tenant_id=tenant_id, permissions=permissions, role=role or ""
    )


async def _facade_invoke_function(
    function_id: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    permissions: Optional[List[str]] = None,
    actor: str = "",
) -> Dict[str, Any]:
    """经 CoreFacade 调用 Function（可被单测 monkeypatch）。

    Args:
        function_id: Function id。
        params: 入参。
        permissions: 权限/scopes。
        actor: 操作者。
    """
    from core.api.core_facade import invoke_function

    return await invoke_function(
        function_id, params or {}, permissions=permissions, actor=actor
    )


async def _facade_execute_action(
    action_id: str,
    entity_ref: Any,
    params: Optional[Dict[str, Any]] = None,
    *,
    permissions: Optional[List[str]] = None,
    actor: str = "",
    role: str = "",
) -> Dict[str, Any]:
    """经 CoreFacade 执行 Action（可被单测 monkeypatch）。

    Args:
        action_id: ActionContract id。
        entity_ref: 实体引用。
        params: 动作入参。
        permissions: 权限/scopes。
        actor: 操作者。
        role: 角色。
    """
    from core.api.core_facade import execute_action

    return await execute_action(
        action_id,
        entity_ref,
        params or {},
        permissions=permissions,
        actor=actor,
        role=role,
    )


def _resolve_entity_ref(params: Dict[str, Any]) -> Any:
    """从工具入参解析 entity_ref。

    Args:
        params: 工具入参（entity_ref / entity_id / domain_id）。
    """
    if "entity_ref" in params and params.get("entity_ref") not in (None, ""):
        return params.get("entity_ref")
    entity_id = str(params.get("entity_id") or "").strip()
    domain_id = str(params.get("domain_id") or "").strip()
    if entity_id and domain_id:
        return (domain_id, entity_id)
    return entity_id


async def _facade_traverse_links(
    request: Dict[str, Any],
    *,
    tenant_id: str,
    permissions: Optional[List[str]] = None,
    role: str = "",
) -> Dict[str, Any]:
    """经 CoreFacade 多跳链接遍历（可被单测 monkeypatch）。

    Args:
        request: link.traverse 请求 dict。
        tenant_id: 租户。
        permissions: 权限/scopes。
        role: ABox ACL 角色。
    """
    from core.api.core_facade import traverse_object_links

    return await traverse_object_links(
        request, tenant_id=tenant_id, permissions=permissions, role=role or ""
    )


class ObjectQueryTool(BaseTool):
    """附录 F.2 ``object.query`` — 经 ObjectSet 只读查询。"""

    def __init__(self) -> None:
        """注册 object.query 工具合同。"""
        super().__init__(
            ToolConfig(
                name="object.query",
                description=(
                    "按 object_type + filter 查询对象集合（只读；须 tenant_id；经 CoreFacade）。"
                    "role 透传 ABox 实例/字段 ACL。禁止 sql/直写 Fact。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "tenant_id": {
                            "type": "string",
                            "description": "租户 ID（必填）",
                        },
                        "object_type": {
                            "type": "string",
                            "description": "ObjectType id，如 InstallOrder",
                        },
                        "filter": {
                            "type": "object",
                            "description": "等值过滤",
                        },
                        "sort": {
                            "type": "array",
                            "description": "排序规格",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "上限，默认 50",
                        },
                        "domain_id": {
                            "type": "string",
                            "description": "可选域 id",
                        },
                        "role": {
                            "type": "string",
                            "description": "调用方角色（ABox 字段/实例 ACL）",
                        },
                        "permissions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "调用方权限/scopes（须含 kb:read）",
                        },
                    },
                    "required": ["tenant_id", "object_type"],
                },
                metadata={"category": "knowledge", "appendix": "F.2"},
            )
        )

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """执行 object.query。

        Args:
            params: 含 tenant_id / object_type / filter 等。
        """
        bad = _reject_sql_or_write(params or {})
        if bad:
            return ToolResult(success=False, error=bad)

        tenant_id = str((params or {}).get("tenant_id") or "").strip()
        object_type = str((params or {}).get("object_type") or "").strip()
        if not tenant_id:
            return ToolResult(success=False, error="tenant_id_required")
        if not object_type:
            return ToolResult(success=False, error="object_type_required")

        request = {
            "object_type": object_type,
            "filter": (params or {}).get("filter") or {},
            "sort": (params or {}).get("sort") or [],
            "limit": int((params or {}).get("limit") or 50),
            "domain_id": str((params or {}).get("domain_id") or ""),
        }
        permissions = _parse_permissions(params or {})
        role = str((params or {}).get("role") or "")

        try:
            out = await _facade_query_object_set(
                request,
                tenant_id=tenant_id,
                permissions=permissions,
                role=role,
            )
        except Exception as e:
            logger.warning("object.query failed", exc_info=True)
            return ToolResult(success=False, error=str(e)[:500])

        status = out.get("status")
        if status == "ok":
            return ToolResult(success=True, output=out)
        return ToolResult(
            success=False,
            error=out.get("reason") or status or "query_failed",
            output=out,
        )


class FunctionCallTool(BaseTool):
    """附录 F.2 ``function.call`` — 经 FunctionRegistry 无副作用调用。"""

    def __init__(self) -> None:
        """注册 function.call 工具合同。"""
        super().__init__(
            ToolConfig(
                name="function.call",
                description=(
                    "调用 FunctionContract（默认无副作用；经 CoreFacade）。"
                    "禁止 sql/直写 Fact。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "function_id": {
                            "type": "string",
                            "description": "FunctionContract id",
                        },
                        "params": {
                            "type": "object",
                            "description": "函数入参",
                        },
                        "permissions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "调用方权限/scopes",
                        },
                        "actor": {
                            "type": "string",
                            "description": "操作者",
                        },
                    },
                    "required": ["function_id"],
                },
                metadata={"category": "knowledge", "appendix": "F.2"},
            )
        )

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """执行 function.call。

        Args:
            params: 含 function_id / params / permissions。
        """
        bad = _reject_sql_or_write(params or {})
        if bad:
            return ToolResult(success=False, error=bad)

        function_id = str((params or {}).get("function_id") or "").strip()
        if not function_id:
            return ToolResult(success=False, error="function_id_required")

        fn_params = (params or {}).get("params")
        if not isinstance(fn_params, dict):
            fn_params = {}
        # 为什么：函数入参也不得夹带 SQL/写键
        bad2 = _reject_sql_or_write(fn_params)
        if bad2:
            return ToolResult(success=False, error=bad2)

        permissions = _parse_permissions(params or {})
        actor = str((params or {}).get("actor") or "")

        try:
            out = await _facade_invoke_function(
                function_id,
                fn_params,
                permissions=permissions,
                actor=actor,
            )
        except Exception as e:
            logger.warning("function.call failed", exc_info=True)
            return ToolResult(success=False, error=str(e)[:500])

        status = out.get("status")
        if status == "ok":
            return ToolResult(success=True, output=out)
        return ToolResult(
            success=False,
            error=out.get("reason") or status or "invoke_failed",
            output=out,
        )


class LinkTraverseTool(BaseTool):
    """附录 F.2 ``link.traverse`` — 经 FactLedger 多跳只读遍历。"""

    def __init__(self) -> None:
        """注册 link.traverse 工具合同。"""
        super().__init__(
            ToolConfig(
                name="link.traverse",
                description=(
                    "从 start_id 多跳遍历对象链接（只读；须 tenant_id；经 CoreFacade）。"
                    "禁止 sql/直写 Fact。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "tenant_id": {
                            "type": "string",
                            "description": "租户 ID（必填）",
                        },
                        "start_id": {
                            "type": "string",
                            "description": "起点，建议 Type:id",
                        },
                        "object_type": {
                            "type": "string",
                            "description": "当 start_id 无冒号时补全类型",
                        },
                        "link_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "允许的谓词/链接类型；空=全部链接",
                        },
                        "max_hops": {
                            "type": "integer",
                            "description": "最大跳数 1–5，默认 2",
                        },
                        "domain_id": {
                            "type": "string",
                            "description": "可选域 id",
                        },
                        "direction": {
                            "type": "string",
                            "description": "outgoing|incoming|both",
                        },
                        "permissions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "调用方权限/scopes（须含 kb:read）",
                        },
                        "role": {
                            "type": "string",
                            "description": "ABox ACL 角色（实例拒绝/字段脱敏）",
                        },
                    },
                    "required": ["tenant_id", "start_id"],
                },
                metadata={"category": "knowledge", "appendix": "F.2"},
            )
        )

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """执行 link.traverse。

        Args:
            params: 含 tenant_id / start_id 等。
        """
        bad = _reject_sql_or_write(params or {})
        if bad:
            return ToolResult(success=False, error=bad)

        tenant_id = str((params or {}).get("tenant_id") or "").strip()
        start_id = str((params or {}).get("start_id") or "").strip()
        if not tenant_id:
            return ToolResult(success=False, error="tenant_id_required")
        if not start_id:
            return ToolResult(success=False, error="start_id_required")

        request = {
            "start_id": start_id,
            "object_type": str((params or {}).get("object_type") or ""),
            "link_types": list((params or {}).get("link_types") or []),
            "max_hops": int((params or {}).get("max_hops") or 2),
            "domain_id": str((params or {}).get("domain_id") or ""),
            "direction": str((params or {}).get("direction") or "both"),
        }
        permissions = _parse_permissions(params or {})
        role = str((params or {}).get("role") or "").strip()

        try:
            out = await _facade_traverse_links(
                request,
                tenant_id=tenant_id,
                permissions=permissions,
                role=role,
            )
        except Exception as e:
            logger.warning("link.traverse failed", exc_info=True)
            return ToolResult(success=False, error=str(e)[:500])

        status = out.get("status")
        if status == "ok":
            return ToolResult(success=True, output=out)
        return ToolResult(
            success=False,
            error=out.get("reason") or status or "traverse_failed",
            output=out,
        )


class ObjectSetAggregateTool(BaseTool):
    """附录 F.2 ``object_set.aggregate`` — 经 ObjectSet 只读聚合。"""

    def __init__(self) -> None:
        """注册 object_set.aggregate 工具合同。"""
        super().__init__(
            ToolConfig(
                name="object_set.aggregate",
                description=(
                    "对 ObjectSet 做只读聚合（须 tenant_id + aggregate；经 CoreFacade）。"
                    "当前支持 count[+group_by]；禁止 sql/直写 Fact。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "tenant_id": {
                            "type": "string",
                            "description": "租户 ID（必填）",
                        },
                        "object_type": {
                            "type": "string",
                            "description": "ObjectType id",
                        },
                        "aggregate": {
                            "type": "array",
                            "description": "聚合规格，如 [{type:count, group_by:[status]}]",
                        },
                        "filter": {
                            "type": "object",
                            "description": "等值过滤",
                        },
                        "domain_id": {
                            "type": "string",
                            "description": "可选域 id",
                        },
                        "permissions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "调用方权限/scopes（须含 kb:read）",
                        },
                    },
                    "required": ["tenant_id", "object_type", "aggregate"],
                },
                metadata={"category": "knowledge", "appendix": "F.2"},
            )
        )

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """执行 object_set.aggregate。

        Args:
            params: 含 tenant_id / object_type / aggregate。
        """
        bad = _reject_sql_or_write(params or {})
        if bad:
            return ToolResult(success=False, error=bad)

        tenant_id = str((params or {}).get("tenant_id") or "").strip()
        object_type = str((params or {}).get("object_type") or "").strip()
        aggregate = (params or {}).get("aggregate")
        if not tenant_id:
            return ToolResult(success=False, error="tenant_id_required")
        if not object_type:
            return ToolResult(success=False, error="object_type_required")
        if not isinstance(aggregate, list) or not aggregate:
            return ToolResult(success=False, error="aggregate_required")
        # 为什么：最小切片仅允许 count，避免冒充任意 SQL 聚合
        for spec in aggregate:
            if not isinstance(spec, dict):
                return ToolResult(success=False, error="aggregate_spec_invalid")
            if str(spec.get("type") or "") != "count":
                return ToolResult(success=False, error="aggregate_type_unsupported")

        request = {
            "object_type": object_type,
            "filter": (params or {}).get("filter") or {},
            "sort": [],
            "limit": 1,
            "domain_id": str((params or {}).get("domain_id") or ""),
            "aggregate": aggregate,
        }
        permissions = _parse_permissions(params or {})
        role = str((params or {}).get("role") or "")

        try:
            out = await _facade_query_object_set(
                request,
                tenant_id=tenant_id,
                permissions=permissions,
                role=role,
            )
        except Exception as e:
            logger.warning("object_set.aggregate failed", exc_info=True)
            return ToolResult(success=False, error=str(e)[:500])

        status = out.get("status")
        if status == "ok":
            return ToolResult(success=True, output=out)
        return ToolResult(
            success=False,
            error=out.get("reason") or status or "aggregate_failed",
            output=out,
        )


class ActionExecuteTool(BaseTool):
    """附录 F.2 ``action.execute`` — 经 ActionRegistry L1 执行动作。"""

    def __init__(self) -> None:
        """注册 action.execute 工具合同。"""
        super().__init__(
            ToolConfig(
                name="action.execute",
                description=(
                    "执行 ActionContract（经 CoreFacade → ActionRegistry；L1+审批）。"
                    "customer_action 须 tenant_id+idempotency_key。"
                    "禁止 sql/直写 Fact；禁止 bypass_approval。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "action_id": {
                            "type": "string",
                            "description": "ActionContract id",
                        },
                        "entity_id": {
                            "type": "string",
                            "description": "实体 id（可与 domain_id 组合）",
                        },
                        "domain_id": {
                            "type": "string",
                            "description": "可选域 id",
                        },
                        "entity_ref": {
                            "description": "实体引用（优先于 entity_id）",
                        },
                        "params": {
                            "type": "object",
                            "description": "动作入参（customer_action 含 tenant_id/idempotency_key）",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "租户（customer_action 可顶层或 params 内）",
                        },
                        "idempotency_key": {
                            "type": "string",
                            "description": "幂等键（customer_action 可顶层或 params 内）",
                        },
                        "permissions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "调用方权限/scopes",
                        },
                        "actor": {
                            "type": "string",
                            "description": "操作者",
                        },
                        "role": {
                            "type": "string",
                            "description": "角色（可选）",
                        },
                    },
                    "required": ["action_id"],
                },
                metadata={"category": "knowledge", "appendix": "F.2"},
            )
        )

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """执行 action.execute。

        Args:
            params: 含 action_id / entity_id|entity_ref / params。
        """
        bad = _reject_sql_or_write(params or {})
        if bad:
            return ToolResult(success=False, error=bad)

        # 为什么：工具面永不允许绕过审批门
        if (params or {}).get("bypass_approval") or (params or {}).get(
            "_bypass_approval"
        ):
            return ToolResult(success=False, error="bypass_approval_forbidden")

        action_id = str((params or {}).get("action_id") or "").strip()
        if not action_id:
            return ToolResult(success=False, error="action_id_required")

        entity_ref = _resolve_entity_ref(params or {})
        if entity_ref in (None, ""):
            return ToolResult(success=False, error="entity_ref_required")

        action_params = (params or {}).get("params")
        if not isinstance(action_params, dict):
            action_params = {}
        else:
            action_params = dict(action_params)
        bad2 = _reject_sql_or_write(action_params)
        if bad2:
            return ToolResult(success=False, error=bad2)

        # 为什么：customer_action 顶层键并入 params，供 Facade W7 幂等门读取
        if action_id.startswith("customer_action:"):
            for k in ("tenant_id", "idempotency_key"):
                if (params or {}).get(k) and not action_params.get(k):
                    action_params[k] = (params or {}).get(k)

        permissions = _parse_permissions(params or {})
        actor = str((params or {}).get("actor") or "")
        role = str((params or {}).get("role") or "")

        try:
            out = await _facade_execute_action(
                action_id,
                entity_ref,
                action_params,
                permissions=permissions,
                actor=actor,
                role=role,
            )
        except Exception as e:
            logger.warning("action.execute failed", exc_info=True)
            return ToolResult(success=False, error=str(e)[:500])

        status = out.get("status")
        # executed / pending_approval / idempotent_replay 为合法终态
        if status in ("executed", "pending_approval", "idempotent_replay"):
            return ToolResult(success=True, output=out)
        return ToolResult(
            success=False,
            error=out.get("reason") or out.get("error") or status or "execute_failed",
            output=out,
        )
