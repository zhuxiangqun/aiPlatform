"""InterfaceRegistry — InterfaceContract 注册与兼容性校验（W5 最小切片）。

硬规则：
  - 兼容性：implementer 声明 + properties/links/actions 全集覆盖
  - ``required_permissions`` 非空时失败关闭（对齐 Action/Function L1）

非目标：不写 Fact/Wiki；不做 publish 流水线；不生成 SDK。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.harness.infrastructure.interface_contract import InterfaceContractModel
from core.harness.knowledge_pipeline.fact_ledger import load_object_type_bindings
from core.utils.paths import get_aiplat_home

logger = logging.getLogger(__name__)


def _permissions_allow(need: List[str], have: Optional[List[str]]) -> Dict[str, Any]:
    """L1 权限评估（与 Action/Function 同语义）。"""
    if not need:
        return {"decision": "allow", "reason": "no_required_permissions"}
    held = set(have or [])
    if "*" in held or "admin" in held:
        return {"decision": "allow", "reason": "admin_or_wildcard_scope"}
    missing = [p for p in need if p not in held]
    if missing:
        return {
            "decision": "deny",
            "reason": f"missing_permissions:{sorted(missing)}",
        }
    return {"decision": "allow", "reason": "permissions_satisfied"}


def _default_bindings_path() -> Optional[Path]:
    """workspace_seeds 下 ObjectType 绑定（配置驱动）。"""
    roots = (
        Path(__file__).resolve().parents[3] / "workspace_seeds" / "ontologies",
        Path(__file__).resolve().parents[2] / "workspace_seeds" / "ontologies",
    )
    for seed_dir in roots:
        if not seed_dir.is_dir():
            continue
        matches = sorted(seed_dir.glob("*-object-types.json"))
        if matches:
            return matches[0]
    return None


def _resolve_object_type(
    object_type_id: str,
    *,
    bindings_path: Optional[Path] = None,
    object_type_override: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """解析 ObjectType 定义。

    Args:
        object_type_id: 对象类型 id。
        bindings_path: 可选种子路径。
        object_type_override: 测试/调用方直接传入的 ObjectType dict。
    """
    if object_type_override is not None:
        return object_type_override
    path = bindings_path or _default_bindings_path()
    if path is None or not Path(path).is_file():
        return None
    for b in load_object_type_bindings(Path(path)):
        if str(b.get("object_type_id") or "") == object_type_id:
            return b
    return None


def _check_shape(
    contract: InterfaceContractModel,
    object_type: Dict[str, Any],
) -> Dict[str, Any]:
    """对照 ObjectType 做 properties/links/actions 覆盖检查。

    Args:
        contract: Interface 合同。
        object_type: ObjectType 绑定 dict。
    """
    ot_props = {
        str(p.get("id") or ""): p
        for p in (object_type.get("properties") or [])
        if isinstance(p, dict)
    }
    ot_links = {
        str(lk.get("link_type") or ""): lk
        for lk in (object_type.get("links") or [])
        if isinstance(lk, dict)
    }
    ot_actions = {
        str(a) for a in (object_type.get("actions") or []) if str(a).strip()
    }

    missing_props: List[str] = []
    type_mismatches: List[str] = []
    for prop in contract.properties:
        pid = str(prop.get("id") or "")
        want_type = str(prop.get("type") or "")
        got = ot_props.get(pid)
        if got is None:
            missing_props.append(pid)
            continue
        got_type = str(got.get("type") or "")
        if got_type and want_type and got_type != want_type:
            type_mismatches.append(f"{pid}:{got_type}!={want_type}")

    missing_links = [
        str(lk.get("link_type") or "")
        for lk in contract.links
        if str(lk.get("link_type") or "") not in ot_links
    ]
    missing_actions = [a for a in contract.actions if a not in ot_actions]

    if missing_props or missing_links or missing_actions or type_mismatches:
        return {
            "compatible": False,
            "missing_properties": missing_props,
            "missing_links": missing_links,
            "missing_actions": missing_actions,
            "type_mismatches": type_mismatches,
        }
    return {
        "compatible": True,
        "missing_properties": [],
        "missing_links": [],
        "missing_actions": [],
        "type_mismatches": [],
    }


class InterfaceRegistry:
    """内存 Interface 合同注册表 + 兼容性校验。"""

    def __init__(self) -> None:
        """初始化空的内存合同表。"""
        self._contracts: Dict[str, InterfaceContractModel] = {}

    def register(self, contract: InterfaceContractModel) -> None:
        """注册或覆盖 Interface 合同。

        Args:
            contract: 已校验的 InterfaceContractModel。
        """
        self._contracts[contract.interface_id] = contract

    def get(self, interface_id: str) -> Optional[InterfaceContractModel]:
        """按 id 取合同。

        Args:
            interface_id: 接口标识。
        """
        return self._contracts.get(interface_id)

    def list_ids(self) -> List[str]:
        """已注册 interface_id 列表。"""
        return sorted(self._contracts.keys())

    def check_compatibility(
        self,
        interface_id: str,
        object_type_id: str,
        *,
        permissions: Optional[List[str]] = None,
        bindings_path: Optional[Path] = None,
        object_type_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """校验 ObjectType 是否兼容 Interface（W5 验收：接口兼容性校验）。

        Args:
            interface_id: Interface 合同 id。
            object_type_id: 候选 ObjectType id。
            permissions: 调用方权限/scopes。
            bindings_path: 可选 ObjectType 种子路径。
            object_type_override: 可选直接传入的 ObjectType dict（测试用）。

        Returns:
            统一回执（status + compatible / reason）。
        """
        contract = self._contracts.get(interface_id)
        if contract is None:
            return {
                "status": "not_found",
                "interface_id": interface_id,
                "object_type_id": object_type_id,
                "reason": "interface_not_registered",
            }

        gate = _permissions_allow(
            list(contract.required_permissions or []), permissions
        )
        if gate["decision"] != "allow":
            return {
                "status": "policy_denied",
                "interface_id": interface_id,
                "object_type_id": object_type_id,
                "reason": gate["reason"],
                "policy_gate": gate,
            }

        # 为什么：附录 C.4 implementers 是声明面；未声明不得冒充兼容
        if object_type_id not in contract.implementers:
            return {
                "status": "not_an_implementer",
                "interface_id": interface_id,
                "object_type_id": object_type_id,
                "compatible": False,
                "reason": "object_type_not_in_implementers",
                "implementers": list(contract.implementers),
                "policy_gate": gate,
            }

        ot = _resolve_object_type(
            object_type_id,
            bindings_path=bindings_path,
            object_type_override=object_type_override,
        )
        if ot is None:
            return {
                "status": "object_type_not_found",
                "interface_id": interface_id,
                "object_type_id": object_type_id,
                "compatible": False,
                "reason": "object_type_binding_missing",
                "policy_gate": gate,
            }

        shape = _check_shape(contract, ot)
        if not shape["compatible"]:
            return {
                "status": "incompatible",
                "interface_id": interface_id,
                "object_type_id": object_type_id,
                "compatible": False,
                "reason": "shape_mismatch",
                "details": shape,
                "policy_gate": gate,
            }

        return {
            "status": "ok",
            "interface_id": interface_id,
            "object_type_id": object_type_id,
            "compatible": True,
            "version": contract.version,
            "policy_gate": gate,
        }


_registry: Optional[InterfaceRegistry] = None


def get_interface_registry() -> InterfaceRegistry:
    """进程内 InterfaceRegistry 单例（首次装载 seed + AIPLAT_HOME/interfaces）。"""
    global _registry
    if _registry is None:
        _registry = InterfaceRegistry()
        register_builtin_interfaces(_registry)
    return _registry


def _reset_interface_registry_for_tests() -> None:
    """测试用：清空单例，下次 get 重新装载。"""
    global _registry
    _registry = None


def register_builtin_interfaces(reg: InterfaceRegistry) -> int:
    """从 workspace_seeds/interfaces 与 ``AIPLAT_HOME/interfaces`` 装载 YAML。

    Args:
        reg: 目标注册表。

    Returns:
        成功注册的合同数。
    """
    count = 0
    roots: List[Path] = []
    try:
        seed = (
            Path(__file__).resolve().parents[2]
            / "workspace_seeds"
            / "interfaces"
        )
        if seed.is_dir():
            roots.append(seed)
    except Exception:
        logger.debug("interface seed path resolve failed", exc_info=True)

    try:
        home_if = Path(get_aiplat_home()) / "interfaces"
        if home_if.is_dir():
            roots.append(home_if)
    except Exception:
        logger.debug("AIPLAT_HOME/interfaces resolve failed", exc_info=True)

    for root in roots:
        for path in sorted(root.glob("*.yaml")):
            try:
                count += _load_yaml_file(reg, path)
            except Exception:
                logger.warning("skip interface yaml %s", path, exc_info=True)
    return count


def _load_yaml_file(reg: InterfaceRegistry, path: Path) -> int:
    """解析单个 YAML（``interfaces: [...]`` 或单合同）。"""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items: List[Any]
    if isinstance(raw, dict) and isinstance(raw.get("interfaces"), list):
        items = raw["interfaces"]
    elif isinstance(raw, dict) and raw.get("interface_id"):
        items = [raw]
    else:
        return 0
    n = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        contract = InterfaceContractModel.model_validate(item)
        reg.register(contract)
        n += 1
    return n
