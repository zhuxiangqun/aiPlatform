"""InterfaceContract — 附录 C.4 最小契约（多态接口）。

职责：定义 Interface 的机器可校验合同（properties/links/actions/implementers）。
非目标：不实现管理端 publish、字段级 ACL、SDK、父类继承替代。
"""
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator


class InterfaceContractModel(BaseModel):
    """附录 C.4 Interface 必填字段。"""

    model_config = {"extra": "forbid"}

    interface_id: str = Field(..., min_length=1, max_length=160)
    properties: List[Dict[str, Any]] = Field(default_factory=list)
    links: List[Dict[str, Any]] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    implementers: List[str] = Field(..., min_length=1)
    label: str = ""
    description: str = ""
    version: str = "1.0.0"
    required_permissions: List[str] = Field(default_factory=lambda: ["kb:read"])

    @field_validator("properties")
    @classmethod
    def _validate_properties(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """附录 C.4 properties 项必须含 id/type。

        Args:
            v: 属性规格列表。
        """
        out: List[Dict[str, Any]] = []
        for i, item in enumerate(v or []):
            if not isinstance(item, dict):
                raise ValueError(f"properties[{i}] must be object")
            pid = str(item.get("id") or "").strip()
            ptype = str(item.get("type") or "").strip()
            if not pid or not ptype:
                raise ValueError(f"properties[{i}] requires id and type")
            out.append({"id": pid, "type": ptype})
        return out

    @field_validator("links")
    @classmethod
    def _validate_links(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """附录 C.4 links 项必须含 link_type/target。

        Args:
            v: 链接规格列表。
        """
        out: List[Dict[str, Any]] = []
        for i, item in enumerate(v or []):
            if not isinstance(item, dict):
                raise ValueError(f"links[{i}] must be object")
            lt = str(item.get("link_type") or "").strip()
            tgt = str(item.get("target") or "").strip()
            if not lt or not tgt:
                raise ValueError(f"links[{i}] requires link_type and target")
            out.append({"link_type": lt, "target": tgt})
        return out
