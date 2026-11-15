"""FunctionRegistry — FunctionContract 注册与 invoke（W5 最小切片）。

硬规则：
  - ``side_effects`` 必须为 false，否则 ``side_effects_forbidden``
  - ``required_permissions`` 非空时失败关闭（对齐 Action L1）

非目标：不写 Fact/Wiki；不做审批队列；不生成 SDK。
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.harness.infrastructure.function_contract import FunctionContractModel
from core.utils.paths import get_aiplat_home

logger = logging.getLogger(__name__)


def _permissions_allow(need: List[str], have: Optional[List[str]]) -> Dict[str, Any]:
    """L1 权限评估（与 ActionRegistry._evaluate_l1_policy_gate 同语义）。"""
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


class FunctionRegistry:
    """内存 Function 合同注册表 + invoke。"""

    def __init__(self) -> None:
        """初始化空的内存合同表。"""
        self._contracts: Dict[str, FunctionContractModel] = {}

    def register(self, contract: FunctionContractModel) -> None:
        """注册或覆盖 Function 合同。

        Args:
            contract: 已校验的 FunctionContractModel。
        """
        self._contracts[contract.function_id] = contract

    def get(self, function_id: str) -> Optional[FunctionContractModel]:
        """按 id 取合同。

        Args:
            function_id: 函数标识。
        """
        return self._contracts.get(function_id)

    def list_ids(self) -> List[str]:
        """已注册 function_id 列表。"""
        return sorted(self._contracts.keys())

    async def invoke(
        self,
        function_id: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        permissions: Optional[List[str]] = None,
        actor: str = "",
    ) -> Dict[str, Any]:
        """执行无副作用函数。

        Args:
            function_id: 合同 id。
            params: 输入参数。
            permissions: 调用方权限/scopes。
            actor: 操作者（审计字段）。

        Returns:
            统一回执 dict（含 status / result 或 reason）。
        """
        contract = self._contracts.get(function_id)
        if contract is None:
            return {
                "status": "not_found",
                "function_id": function_id,
                "reason": "function_not_registered",
            }

        # 为什么：W5 验收「函数默认无副作用」——本切片一律拒绝 side_effects=true
        if contract.side_effects:
            return {
                "status": "side_effects_forbidden",
                "function_id": function_id,
                "reason": "side_effects_forbidden",
            }

        gate = _permissions_allow(list(contract.required_permissions or []), permissions)
        if gate["decision"] != "allow":
            return {
                "status": "policy_denied",
                "function_id": function_id,
                "reason": gate["reason"],
                "policy_gate": gate,
            }

        started = time.time()
        try:
            result = await asyncio.wait_for(
                self._call_handler(contract, params or {}, actor=actor),
                timeout=max(contract.timeout_ms, 1) / 1000.0,
            )
        except asyncio.TimeoutError:
            return {
                "status": "timeout",
                "function_id": function_id,
                "reason": f"timeout_ms:{contract.timeout_ms}",
            }
        except Exception as e:
            logger.warning("function invoke failed id=%s", function_id, exc_info=True)
            return {
                "status": "error",
                "function_id": function_id,
                "reason": str(e)[:500],
            }

        return {
            "status": "ok",
            "function_id": function_id,
            "version": contract.version,
            "actor": actor or "",
            "result": result if isinstance(result, dict) else {"value": result},
            "elapsed_ms": int((time.time() - started) * 1000),
            "policy_gate": gate,
        }

    async def _call_handler(
        self,
        contract: FunctionContractModel,
        params: Dict[str, Any],
        *,
        actor: str,
    ) -> Any:
        """动态加载 handler 并调用。

        Args:
            contract: 合同。
            params: 输入。
            actor: 操作者。
        """
        module_path, _, fn_name = contract.handler.partition(":")
        if not module_path or not fn_name:
            raise ValueError(f"invalid handler: {contract.handler}")
        mod = importlib.import_module(module_path)
        fn = getattr(mod, fn_name)
        if asyncio.iscoroutinefunction(fn):
            return await fn(params, actor=actor)
        return await asyncio.to_thread(fn, params, actor=actor)


_registry: Optional[FunctionRegistry] = None


def get_function_registry() -> FunctionRegistry:
    """进程内 FunctionRegistry 单例（首次装载 seed + AIPLAT_HOME/functions）。"""
    global _registry
    if _registry is None:
        _registry = FunctionRegistry()
        register_builtin_functions(_registry)
    return _registry


def _reset_function_registry_for_tests() -> None:
    """测试用：清空单例，下次 get 重新装载。"""
    global _registry
    _registry = None


def register_builtin_functions(reg: FunctionRegistry) -> int:
    """从 workspace_seeds/functions 与 ``AIPLAT_HOME/functions`` 装载 YAML。

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
            / "functions"
        )
        if seed.is_dir():
            roots.append(seed)
    except Exception:
        logger.debug("function seed path resolve failed", exc_info=True)

    try:
        home_fn = Path(get_aiplat_home()) / "functions"
        if home_fn.is_dir():
            roots.append(home_fn)
    except Exception:
        logger.debug("AIPLAT_HOME/functions resolve failed", exc_info=True)

    for root in roots:
        for path in sorted(root.glob("*.yaml")):
            try:
                count += _load_yaml_file(reg, path)
            except Exception:
                logger.warning("skip function yaml %s", path, exc_info=True)
    return count


def _load_yaml_file(reg: FunctionRegistry, path: Path) -> int:
    """解析单个 YAML（``functions: [...]`` 或单合同）。"""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items: List[Any]
    if isinstance(raw, dict) and isinstance(raw.get("functions"), list):
        items = raw["functions"]
    elif isinstance(raw, dict) and raw.get("function_id"):
        items = [raw]
    else:
        return 0
    n = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        contract = FunctionContractModel.model_validate(item)
        reg.register(contract)
        n += 1
    return n
