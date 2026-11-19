"""Knowledge SDK 最小切片（附录 E.3）。

由 ObjectType 绑定生成类型化调用表面；运行时经 CoreFacade，不绕过权限/审批。
非目标：不实现多语言包发布、字段级 ACL、手写平行 API。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.harness.knowledge_pipeline.fact_ledger import load_object_type_bindings
from core.harness.knowledge_pipeline.object_set import (
    _default_bindings_path,
    _permissions_allow,
    _resolve_binding,
)

logger = logging.getLogger(__name__)

_REQUIRED_READ = ["kb:read"]
_FORBIDDEN_IN_SOURCE = ("sql", "write_fact", "raw_sql", "_bypass_approval")


def _client_name(object_type: str) -> str:
    """ObjectType id → Client 类名。

    Args:
        object_type: ObjectType id。
    """
    safe = re.sub(r"[^A-Za-z0-9_]", "_", str(object_type or "").strip()) or "Object"
    if safe[0].isdigit():
        safe = f"T_{safe}"
    return f"{safe}Client"


def build_sdk_surface(
    object_type: str,
    *,
    permissions: Optional[List[str]] = None,
    bindings_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """从 ObjectType 绑定构建附录 E.3 SDK 表面（只读元数据）。

    Args:
        object_type: ObjectType id。
        permissions: 调用方权限；须含 kb:read。
        bindings_path: 可选绑定 JSON。

    Returns:
        surface dict（status=ok|policy_denied|not_found）。
    """
    gate = _permissions_allow(_REQUIRED_READ, permissions)
    if gate.get("decision") != "allow":
        return {
            "status": "policy_denied",
            "reason": gate.get("reason") or "policy_denied",
            "policy_gate": gate,
            "object_type": object_type,
            "methods": [],
        }

    ot = str(object_type or "").strip()
    if not ot:
        return {
            "status": "error",
            "reason": "object_type_required",
            "methods": [],
        }

    binding = _resolve_binding(ot, bindings_path=bindings_path)
    if binding is None:
        return {
            "status": "not_found",
            "reason": f"object_type_not_found:{ot}",
            "object_type": ot,
            "methods": [],
            "policy_gate": gate,
        }

    methods = [
        {"name": "get", "kind": "object.get", "via": "query_object_set"},
        {"name": "query", "kind": "object.query", "via": "query_object_set"},
        {
            "name": "aggregate",
            "kind": "object_set.aggregate",
            "via": "query_object_set",
        },
        {"name": "link", "kind": "link.traverse", "via": "traverse_object_links"},
        {
            "name": "call_function",
            "kind": "function.call",
            "via": "invoke_function",
        },
        {
            "name": "execute_action",
            "kind": "action.execute",
            "via": "execute_action",
        },
    ]
    return {
        "status": "ok",
        "object_type": ot,
        "client_name": _client_name(ot),
        "primary_key": str(binding.get("primary_key") or "id"),
        "domain_id": str(binding.get("domain_id") or ""),
        "label": str(binding.get("label") or ot),
        "properties": list(binding.get("properties") or []),
        "links": list(binding.get("links") or []),
        "methods": methods,
        "required_permissions": list(_REQUIRED_READ),
        "policy_gate": gate,
        "note": "generated_surface; runtime must call CoreFacade only",
    }


def render_sdk_python(surface: Dict[str, Any]) -> Dict[str, Any]:
    """把 surface 渲染为仅依赖 CoreFacade 的 Python 源码。

    Args:
        surface: ``build_sdk_surface`` 回执。

    Returns:
        含 ``source`` 的回执；surface 非 ok 时透传。
    """
    if surface.get("status") != "ok":
        return {**surface, "source": ""}

    name = str(surface.get("client_name") or "ObjectClient")
    ot = str(surface.get("object_type") or "")
    pk = str(surface.get("primary_key") or "id")
    domain = str(surface.get("domain_id") or "")

    # 为什么：生成物禁止 SQL/直写/bypass，强制只 import CoreFacade
    source = f'''"""Auto-generated Knowledge SDK client for {ot} (appendix E.3).

DO NOT edit by hand as a parallel API — regenerate from ObjectType bindings.
All calls go through core.api.core_facade (L1 / approval preserved).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.api.core_facade import (
    execute_action,
    invoke_function,
    query_object_set,
    traverse_object_links,
)


class {name}:
    """Typed ObjectClient for {ot}."""

    OBJECT_TYPE = {ot!r}
    PRIMARY_KEY = {pk!r}
    DOMAIN_ID = {domain!r}

    def __init__(
        self,
        *,
        tenant_id: str,
        permissions: Optional[List[str]] = None,
        domain_id: str = "",
    ) -> None:
        """绑定租户与权限。

        Args:
            tenant_id: 租户 ID。
            permissions: scopes（须含 kb:read 等合同要求）。
            domain_id: 可选域覆盖。
        """
        if not str(tenant_id or "").strip():
            raise ValueError("tenant_id_required")
        self.tenant_id = str(tenant_id).strip()
        self.permissions = permissions
        self.domain_id = str(domain_id or self.DOMAIN_ID or "").strip()

    async def get(self, object_id: str) -> Dict[str, Any]:
        """按主键取单对象。

        Args:
            object_id: 主键值。
        """
        return await query_object_set(
            {{
                "object_type": self.OBJECT_TYPE,
                "filter": {{self.PRIMARY_KEY: object_id}},
                "limit": 1,
                "domain_id": self.domain_id,
            }},
            tenant_id=self.tenant_id,
            permissions=self.permissions,
        )

    async def query(
        self,
        filter: Optional[Dict[str, Any]] = None,
        *,
        sort: Optional[List[Dict[str, str]]] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """ObjectSet 查询。

        Args:
            filter: 等值过滤。
            sort: 排序。
            limit: 上限。
        """
        return await query_object_set(
            {{
                "object_type": self.OBJECT_TYPE,
                "filter": filter or {{}},
                "sort": sort or [],
                "limit": limit,
                "domain_id": self.domain_id,
            }},
            tenant_id=self.tenant_id,
            permissions=self.permissions,
        )

    async def aggregate(
        self,
        aggregate: List[Dict[str, Any]],
        *,
        filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """只读聚合（count）。

        Args:
            aggregate: 聚合规格。
            filter: 等值过滤。
        """
        return await query_object_set(
            {{
                "object_type": self.OBJECT_TYPE,
                "filter": filter or {{}},
                "limit": 1,
                "domain_id": self.domain_id,
                "aggregate": aggregate,
            }},
            tenant_id=self.tenant_id,
            permissions=self.permissions,
        )

    async def link(
        self,
        start_id: str,
        *,
        link_types: Optional[List[str]] = None,
        max_hops: int = 2,
    ) -> Dict[str, Any]:
        """多跳链接遍历。

        Args:
            start_id: 起点 id。
            link_types: 链接类型。
            max_hops: 最大跳数。
        """
        return await traverse_object_links(
            {{
                "start_id": start_id,
                "object_type": self.OBJECT_TYPE,
                "link_types": link_types or [],
                "max_hops": max_hops,
                "domain_id": self.domain_id,
            }},
            tenant_id=self.tenant_id,
            permissions=self.permissions,
        )

    async def call_function(
        self,
        function_id: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        actor: str = "",
    ) -> Dict[str, Any]:
        """调用 FunctionContract。

        Args:
            function_id: Function id。
            params: 入参。
            actor: 操作者。
        """
        return await invoke_function(
            function_id,
            params or {{}},
            permissions=self.permissions,
            actor=actor,
        )

    async def execute_action(
        self,
        action_id: str,
        entity_ref: Any,
        params: Optional[Dict[str, Any]] = None,
        *,
        actor: str = "",
        role: str = "",
    ) -> Dict[str, Any]:
        """执行 ActionContract（禁止 bypass）。

        Args:
            action_id: Action id。
            entity_ref: 实体引用。
            params: 动作入参。
            actor: 操作者。
            role: 角色。
        """
        return await execute_action(
            action_id,
            entity_ref,
            params or {{}},
            permissions=self.permissions,
            actor=actor,
            role=role,
        )
'''
    lowered = source.lower()
    for bad in _FORBIDDEN_IN_SOURCE:
        if bad in lowered:
            return {
                "status": "error",
                "reason": f"generated_source_forbidden:{bad}",
                "source": "",
                "object_type": ot,
            }
    return {
        "status": "ok",
        "object_type": ot,
        "client_name": name,
        "source": source,
        "via": [m.get("via") for m in surface.get("methods") or []],
    }


async def _facade_query_object_set(
    request: Dict[str, Any],
    *,
    tenant_id: str,
    permissions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """经 CoreFacade 查询 ObjectSet（可被单测 monkeypatch）。

    Args:
        request: ObjectSet 请求。
        tenant_id: 租户。
        permissions: scopes。
    """
    from core.api.core_facade import query_object_set

    return await query_object_set(
        request, tenant_id=tenant_id, permissions=permissions
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
        action_id: Action id。
        entity_ref: 实体引用。
        params: 入参。
        permissions: scopes。
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


class ObjectClient:
    """运行时 ObjectClient（附录 E.3）；一律经 CoreFacade。"""

    def __init__(
        self,
        object_type: str,
        *,
        tenant_id: str,
        permissions: Optional[List[str]] = None,
        domain_id: str = "",
        primary_key: str = "id",
    ) -> None:
        """绑定租户与对象类型。

        Args:
            object_type: ObjectType id。
            tenant_id: 租户。
            permissions: scopes。
            domain_id: 域。
            primary_key: 主键字段。
        """
        if not str(tenant_id or "").strip():
            raise ValueError("tenant_id_required")
        if not str(object_type or "").strip():
            raise ValueError("object_type_required")
        self.object_type = str(object_type).strip()
        self.tenant_id = str(tenant_id).strip()
        self.permissions = permissions
        self.domain_id = str(domain_id or "").strip()
        self.primary_key = str(primary_key or "id")

    async def query(
        self,
        filter: Optional[Dict[str, Any]] = None,
        *,
        sort: Optional[List[Dict[str, str]]] = None,
        limit: int = 50,
        aggregate: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """经 Facade 查询 ObjectSet。

        Args:
            filter: 等值过滤。
            sort: 排序。
            limit: 上限。
            aggregate: 可选聚合。
        """
        req: Dict[str, Any] = {
            "object_type": self.object_type,
            "filter": filter or {},
            "sort": sort or [],
            "limit": limit,
            "domain_id": self.domain_id,
        }
        if aggregate:
            req["aggregate"] = aggregate
        return await _facade_query_object_set(
            req, tenant_id=self.tenant_id, permissions=self.permissions
        )

    async def get(self, object_id: str) -> Dict[str, Any]:
        """按主键取对象。

        Args:
            object_id: 主键值。
        """
        return await self.query(
            {self.primary_key: object_id},
            limit=1,
        )

    async def execute_action(
        self,
        action_id: str,
        entity_ref: Any,
        params: Optional[Dict[str, Any]] = None,
        *,
        actor: str = "",
        role: str = "",
    ) -> Dict[str, Any]:
        """经 Facade 执行动作（无 bypass）。

        Args:
            action_id: Action id。
            entity_ref: 实体引用。
            params: 入参。
            actor: 操作者。
            role: 角色。
        """
        return await _facade_execute_action(
            action_id,
            entity_ref,
            params or {},
            permissions=self.permissions,
            actor=actor,
            role=role,
        )


def create_object_client(
    object_type: str,
    *,
    tenant_id: str,
    permissions: Optional[List[str]] = None,
    bindings_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """构建 surface + 运行时 ObjectClient（或 policy_denied）。

    Args:
        object_type: ObjectType id。
        tenant_id: 租户。
        permissions: scopes。
        bindings_path: 可选绑定路径。

    Returns:
        ``{status, surface, client?}``。
    """
    surface = build_sdk_surface(
        object_type, permissions=permissions, bindings_path=bindings_path
    )
    if surface.get("status") != "ok":
        return {"status": surface.get("status"), "surface": surface, "client": None}
    client = ObjectClient(
        object_type,
        tenant_id=tenant_id,
        permissions=permissions,
        domain_id=str(surface.get("domain_id") or ""),
        primary_key=str(surface.get("primary_key") or "id"),
    )
    return {"status": "ok", "surface": surface, "client": client}


def list_sdk_object_types(
    *,
    permissions: Optional[List[str]] = None,
    bindings_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """列出可生成 SDK 的 ObjectType id。

    Args:
        permissions: 须含 kb:read。
        bindings_path: 可选绑定 JSON。
    """
    gate = _permissions_allow(_REQUIRED_READ, permissions)
    if gate.get("decision") != "allow":
        return {
            "status": "policy_denied",
            "reason": gate.get("reason") or "policy_denied",
            "object_types": [],
            "policy_gate": gate,
        }
    path = bindings_path or _default_bindings_path()
    if path is None or not Path(path).is_file():
        return {
            "status": "not_found",
            "reason": "bindings_missing",
            "object_types": [],
            "policy_gate": gate,
        }
    types = [
        str(b.get("object_type_id") or "")
        for b in load_object_type_bindings(Path(path))
        if b.get("object_type_id")
    ]
    return {
        "status": "ok",
        "object_types": types,
        "bindings_path": str(path),
        "policy_gate": gate,
    }
