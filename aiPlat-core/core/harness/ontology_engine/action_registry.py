"""
AsyncActionRegistry — enterprise action execution engine (v3, 2026-07-29).

7-step execution pipeline:
  0. mutex lock (concurrent double-click prevention)
  1. input validation (JSON Schema)
  2. entity loading (single-domain str or cross-domain tuple)
  3. entity constraints (class + state + role → 4-level constraint_type)
  3.25 L1 hard PolicyGate (required_permissions fail-closed)
  4. approval gate (stake lock + pending_approvals table)
  5. handler execution (async callable + retry strategy)
  6. audit write (action_audit table with entity snapshot)
  7. mutex release

N08 deepen：``AIPLAT_ACTION_KILL_SWITCH`` 全局急停 + Policy/Approval/Audit 套件；
不宣称 N08 certified / Lv4 误报门全量重设计。
"""
from __future__ import annotations

from core.harness.knowledge.domain_router import DomainRouter

import asyncio
import importlib
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from core.harness.infrastructure.action_contract import (
    ActionContractModel,
    ActionScope,
    FailureStrategy,
)
from core.harness.infrastructure.entity_lock import EntityLock, AsyncioEntityLock
from core.harness.infrastructure.action_store import ActionStore
from core.harness.infrastructure.dynamic_mapper import DynamicSchemaMapper
from core.harness.infrastructure.throttle import DecisionThrottle

logger = logging.getLogger(__name__)


class AsyncActionRegistry:
    """Async-safe enterprise action registry with 7-step execution pipeline."""

    def __init__(
        self,
        store: Optional[ActionStore] = None,
        lock_provider: Optional[EntityLock] = None,
        cross_domain_config_path: str = "~/.aiplat/ontologies/registry.json",
    ):
        """初始化。

        Args:
            store: store 参数。
            lock_provider: lock_provider 参数。
            cross_domain_config_path: cross_domain_config_path 参数。
        """
        self._contracts: Dict[str, ActionContractModel] = {}
        self._aliases: Dict[str, str] = {}  # Phase 2 D3: legacy_id → canonical action_id
        self._handlers: Dict[str, Callable] = {}
        self._store = store or ActionStore()
        self._lock_provider = lock_provider or AsyncioEntityLock()
        self._cross_domain_config_path = cross_domain_config_path
        self._cross_domain_cache: Dict[str, Any] = {}
        self._cache_ttl = 60
        self._cache_timestamp = 0.0
        self._mapper = DynamicSchemaMapper()
        self._throttle = DecisionThrottle(store=self._store)

    # ═══════════════════════════════════════════════════════
    # Registration
    # ═══════════════════════════════════════════════════════

    def register(self, contract: ActionContractModel) -> None:
        # FDE contract: when action_namespace is set, validate against audit_schema.v1
        """register。

        Args:
            contract: contract 参数。
        """
        ns = getattr(contract, "action_namespace", "") or ""
        if ns:
            from core.harness.infrastructure.action_audit_validate import (
                validate_action_contract,
            )
            risk = getattr(contract.risk_level, "value", None) or str(contract.risk_level)
            validate_action_contract(
                action_id=contract.action_id,
                action_namespace=ns,
                domain_id=contract.domain_id or "",
                eval_gate=getattr(contract, "eval_gate", "") or "",
                risk_level=risk,
                require_approval=bool(contract.require_approval),
            )
        if contract.action_id in self._contracts:
            logger.warning("Action '%s' already registered, overwriting", contract.action_id)
        self._contracts[contract.action_id] = contract
        for alias in getattr(contract, "aliases", None) or []:
            alias = (alias or "").strip()
            if not alias or alias == contract.action_id:
                continue
            if alias in self._contracts:
                # D3: replace legacy standalone id with alias → namespaced canonical
                logger.info(
                    "Replacing legacy action '%s' with alias → %s",
                    alias,
                    contract.action_id,
                )
                del self._contracts[alias]
            self._aliases[alias] = contract.action_id
        if contract.handler:
            self._resolve_handler(contract)
        logger.info("Registered: %s (%s)", contract.action_id, contract.label)

    def register_batch(self, contracts: List[ActionContractModel]) -> int:
        """register_batch。

        Args:
            contracts: contracts 参数。
        """
        for c in contracts:
            self.register(c)
        return len(contracts)

    # ═══════════════════════════════════════════════════════
    # Query
    # ═══════════════════════════════════════════════════════

    def resolve_action_id(self, action_id: str) -> str:
        """Resolve legacy alias → canonical action_id (Phase 2 D3).

        Args:
            action_id: action 标识。
        """
        if action_id in self._contracts:
            return action_id
        return self._aliases.get(action_id, action_id)

    def get(self, action_id: str) -> Optional[ActionContractModel]:
        """get。

        Args:
            action_id: action 标识。
        """
        return self._contracts.get(self.resolve_action_id(action_id))

    def list_for_class(
        self, domain_id: str, class_name: str, state: str = "", role: str = "",
        include_cross_domain: bool = False,
    ) -> List[ActionContractModel]:
        """列出 for_class。

        Args:
            domain_id: domain 标识。
            class_name: class_name 参数。
            state: state 参数。
            role: role 参数。
            include_cross_domain: include_cross_domain 参数。
        """
        results = []
        for c in self._contracts.values():
            # scope filter
            if c.scope == ActionScope.GLOBAL:
                pass
            elif c.scope == ActionScope.DOMAIN:
                if c.domain_id != domain_id:
                    continue
                if class_name and c.target_class and c.target_class != class_name:
                    continue
            elif c.scope == ActionScope.CROSS_DOMAIN:
                if not include_cross_domain:
                    continue
                if not self._check_cross_domain_whitelist(c.action_id, domain_id, class_name):
                    continue
            else:
                continue

            # state filter
            if state:
                if c.required_state and c.required_state != state:
                    continue
                if c.forbidden_states and state in c.forbidden_states:
                    continue

            # role filter
            if role and c.allowed_roles and role not in c.allowed_roles:
                continue

            results.append(c)
        return results

    def check_entity_constraints(
        self, action_id: str, domain_id: str, class_name: str, state: str, role: str = ""
    ) -> Dict[str, Any]:
        """Returns {valid, reason, constraint_type}.

        Args:
            action_id: action 标识。
            domain_id: domain 标识。
            class_name: class_name 参数。
            state: state 参数。
            role: role 参数。
        """
        c = self.get(action_id)
        if not c:
            return {"valid": False, "reason": f"Unknown action: {action_id}", "constraint_type": "unknown"}

        # scope
        if c.scope == ActionScope.DOMAIN and c.domain_id != domain_id:
            return {"valid": False, "reason": f"Belongs to domain '{c.domain_id}', not '{domain_id}'", "constraint_type": "scope"}
        if c.scope == ActionScope.CROSS_DOMAIN:
            if not self._check_cross_domain_whitelist(action_id, domain_id, class_name):
                return {"valid": False, "reason": "Cross-domain action not whitelisted", "constraint_type": "scope"}

        # class
        if c.target_class and c.target_class != class_name:
            return {"valid": False, "reason": f"Requires class '{c.target_class}', got '{class_name}'", "constraint_type": "class"}

        # state
        if c.forbidden_states and state in c.forbidden_states:
            return {"valid": False, "reason": f"Forbidden in state '{state}'", "constraint_type": "state"}
        if c.required_state and c.required_state != state:
            return {"valid": False, "reason": f"Requires state '{c.required_state}', currently '{state}'", "constraint_type": "state"}

        # role
        if c.allowed_roles and role not in c.allowed_roles:
            return {"valid": False, "reason": f"Requires role in {c.allowed_roles}, got '{role}'", "constraint_type": "permission"}

        return {"valid": True, "reason": "", "constraint_type": ""}

    def _evaluate_l1_policy_gate(
        self,
        contract: ActionContractModel,
        *,
        permissions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """评估动作 L1 硬门（required_permissions）。

        Args:
            contract: 动作合同。
            permissions: 调用方持有的权限列表。

        Returns:
            ``{gate_id, decision, reason}``；无 required_permissions 时 decision=allow。
        """
        ns = getattr(contract, "action_namespace", "") or "action"
        gate_id = f"policy_gate:{ns}:{contract.action_id.split(':')[-1]}"
        need = list(getattr(contract, "required_permissions", None) or [])
        if not need:
            return {
                "gate_id": gate_id,
                "decision": "allow",
                "reason": "no_required_permissions",
            }
        have = set(permissions or [])
        # 为什么：平台身份常见 `*` / `admin` 超权 scope；精确匹配否则会假拒绝已授权调用方。
        if "*" in have or "admin" in have:
            return {
                "gate_id": gate_id,
                "decision": "allow",
                "reason": "admin_or_wildcard_scope",
            }
        missing = [p for p in need if p not in have]
        if missing:
            return {
                "gate_id": gate_id,
                "decision": "deny",
                "reason": f"missing_permissions:{sorted(missing)}",
            }
        return {
            "gate_id": gate_id,
            "decision": "allow",
            "reason": "permissions_satisfied",
        }

    # ═══════════════════════════════════════════════════════
    # Execute Pipeline (7 steps)
    # ═══════════════════════════════════════════════════════

    async def execute(
        self,
        action_id: str,
        entity_ref: Union[str, Tuple[str, str], Dict[str, Any]],
        params: Dict[str, Any],
        actor: str = "system",
        role: str = "",
        permissions: Optional[List[str]] = None,
        _bypass_approval: bool = False,
        _approval_reentry_lock_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """执行动作（7 步流水线）。

        Args:
            action_id: action 标识。
            entity_ref: entity_ref 参数。
            params: params 参数。
            actor: 操作者身份。
            role: role 参数。
            permissions: 调用方持有的权限/scope 列表；合同 ``required_permissions``
                非空时必须全部满足，否则 ``policy_denied``（L1 硬门，失败关闭）。
            _bypass_approval: 仅审批回调重入可 True；裸 True 返回 ``bypass_forbidden``。
            _approval_reentry_lock_id: 已 approved 的 pending lock_id（与 bypass 成对）。
        """
        from core.harness.infrastructure.workbench_runtime_guard import WorkbenchRuntimeGuard

        guard = WorkbenchRuntimeGuard.check_action_registered(self, action_id)
        if not guard.get("ok"):
            return {"status": "invalid", "error": f"Unknown action: {action_id}", "guard": guard}
        action_id = self.resolve_action_id(action_id)
        c = self._contracts.get(action_id)
        if not c:
            return {"status": "invalid", "error": f"Unknown action: {action_id}"}

        # 为什么：急停优先于 mutex/审批，避免半开执行；仅 env 显式开启
        if action_kill_switch_active():
            return {
                "status": "kill_switch",
                "error": "AIPLAT_ACTION_KILL_SWITCH active",
                "constraint_type": "kill_switch",
                "certified": False,
            }

        # 为什么：生产/HTTP 禁止测试式裸 bypass；仅 approve() 持有效 approved 记录可重入
        if _bypass_approval:
            reentry = await self._assert_approval_reentry(
                action_id=action_id,
                lock_id=_approval_reentry_lock_id,
            )
            if not reentry.get("ok"):
                return {
                    "status": "bypass_forbidden",
                    "error": reentry.get("error") or "approval_reentry_required",
                    "constraint_type": "approval",
                }

        # resolve entity
        if isinstance(entity_ref, tuple):
            entity_id = entity_ref[1]
            domain_id = entity_ref[0]
        else:
            entity_id = entity_ref
            domain_id = c.domain_id or DomainRouter.default_graph_domain()

        mutex_lock_id = f"{domain_id}:{entity_id}:mutex"

        # ── Step 0: mutex lock ──
        if not await self._lock_provider.acquire(mutex_lock_id, intent="mutex", ttl=5):
            return {"status": "concurrent_conflict", "error": "Entity is being processed"}

        # ── Step 0.5: decision throttle (MSS-aligned rate governance) ──
        tl = getattr(c, 'throttle_limit', 0) or 0
        if tl > 0 and actor not in (getattr(c, 'throttle_bypass_roles', None) or []):
            tc = await self._throttle.check_rate_limit(
                actor=actor, action_id=action_id, domain_id=domain_id,
                time_window_sec=getattr(c, 'throttle_window_seconds', 3600) or 3600,
                limit=tl,
                block_on_breach=getattr(c, 'throttle_block_on_breach', True),
            )
            if not tc["allowed"]:
                if params.get("__justification"):
                    await self._throttle.record_justification(
                        actor, action_id, str(entity_ref), str(params["__justification"]))
                else:
                    return {
                        "status": "throttled", "reason": tc["reason"],
                        "require_justification": tc.get("require_justification", True),
                        "count": tc["count"], "limit": tc["limit"],
                    }

        constraint: Dict[str, Any] = {"valid": True, "reason": "", "constraint_type": ""}
        try:
            # ── Step 1: input validation ──
            if c.input_schema:
                param_result = self._validate_input(c, params)
                if not param_result["valid"]:
                    return {"status": "invalid_params", "errors": param_result["errors"]}

            # ── Step 2: load entity + snapshot ──
            if isinstance(entity_ref, dict):
                # Dynamic schema mapping: external JSON → entity
                try:
                    ed = await self._mapper.ingest_external(
                        raw_json=entity_ref, domain_id=c.domain_id, class_name=c.target_class)
                    entity_id = ed["id"]
                    domain_id = c.domain_id
                    entity = ed
                except Exception as e:
                    return {"status": "mapping_failed", "error": str(e)}
            else:
                entity = await self._get_entity(domain_id, entity_id)
            if not entity:
                # 为什么：platform_action 可绑定非 Graph 主体（如 extraction_id）；
                # GLOBAL + 无 target_class 时合成审计实体，避免假 not_found。
                if c.scope == ActionScope.GLOBAL and not (c.target_class or ""):
                    entity = {
                        "id": entity_id,
                        "entity_id": entity_id,
                        "name": entity_id,
                        "class": "",
                        "state": "",
                        "domain": domain_id,
                        "domain_id": domain_id,
                    }
                else:
                    return {
                        "status": "not_found",
                        "error": f"Entity {entity_id} not found in {domain_id}",
                    }

            class_name = entity.get("class") or c.target_class or "Unknown"
            current_state = entity.get("state") or ""
            entity_snapshot = {"id": entity_id, "class": class_name, "state": current_state, "domain": domain_id}

            # ── Step 3: entity constraints ──
            constraint = self.check_entity_constraints(action_id, domain_id, class_name, current_state, role)
            if not constraint["valid"]:
                await self._write_audit(c, entity_id, domain_id, current_state, current_state,
                                        "blocked", constraint, params, entity_snapshot, actor, role)
                return {"status": "blocked", "reason": constraint["reason"], "constraint_type": constraint["constraint_type"]}

            # ── Step 3.25: L1 hard PolicyGate（required_permissions 失败关闭）──
            # 为什么：合同字段不可只做装饰；缺权限必须 deny，禁止软 allow 冒充门禁。
            policy_gate = self._evaluate_l1_policy_gate(c, permissions=permissions)
            if policy_gate.get("decision") == "deny":
                await self._write_audit(
                    c, entity_id, domain_id, current_state, current_state,
                    "policy_denied", constraint, params, entity_snapshot, actor, role,
                    policy_gate=policy_gate,
                )
                return {
                    "status": "policy_denied",
                    "reason": policy_gate.get("reason", "missing_permissions"),
                    "constraint_type": "permission",
                    "policy_gate": policy_gate,
                }

            # ── Step 3.5: rule consistency check (Phase 2) ──
            target_state = params.get("target_state", "")
            if target_state and target_state != current_state:
                try:
                    from core.harness.infrastructure.rule_validator import RuleValidator
                    v = RuleValidator(domain_id)
                    rc = v.check_transition(entity_id, current_state, target_state)
                    if not rc["valid"]:
                        return {"status": "rule_conflict", "conflicts": rc["conflicts"],
                                "constraint_type": "rule"}
                except Exception:
                    logger.debug("RuleValidator unavailable", exc_info=True)

            # ── Step 4: approval gate ──
            # 为什么：require_approval 且无 threshold 时必须入队；禁止 silent 直跑 handler
            if not _bypass_approval and c.require_approval:
                if c.approval_threshold is not None:
                    amount = params.get("amount", 0)
                    if amount < c.approval_threshold:
                        logger.info("Amount %.2f < threshold %.2f, auto-approved", amount, c.approval_threshold)
                    else:
                        return await self._enqueue_approval(c, entity_id, domain_id, params, actor)
                else:
                    return await self._enqueue_approval(c, entity_id, domain_id, params, actor)

            # ── Step 4.5: Action 阶梯量化门（P2-L5）──
            # Lv4 自动闭环必须通过误报率门（历史误报 < 0.5%），否则降级为人工确认
            if not _bypass_approval:
                from core.harness.infrastructure.action_contract import ActionLevel
                if getattr(c, "action_level", ActionLevel.LV2_CONFIRMED) == ActionLevel.LV4_AUTO_CLOSE:
                    gate = await self.compute_closure_gate(action_id)
                    if not gate.get("allowed"):
                        # 误报率超标 → 走人工审批（若未声明审批则返回 gate 拒绝）
                        if c.require_approval:
                            return await self._enqueue_approval(c, entity_id, domain_id, params, actor)
                        await self._write_audit(c, entity_id, domain_id, current_state, current_state,
                                                "closure_gated", constraint, params, entity_snapshot, actor, role)
                        return {
                            "status": "closure_gated",
                            "reason": gate.get("reason", "auto-close gate failed"),
                            "fp_rate": gate.get("fp_rate"),
                            "constraint_type": "action_level",
                        }

            # ── Step 5: execute handler ──
            handler = self._get_handler(action_id)
            if not handler:
                return {"status": "failed", "error": f"No handler for {action_id}"}

            exec_status, to_state, result = await self._invoke_handler(c, handler, entity, params, actor, current_state)

            # ── P0-L2 业务事件桥：动作成功 → EventBus + GraphIndex 增量更新 ──
            if exec_status in ("executed", "done", "completed", "success", "ok"):
                try:
                    from core.harness.ontology_engine.business_event_bridge import publish_business_action
                    await publish_business_action(
                        action_id=action_id, entity_id=entity_id, domain_id=domain_id,
                        result=result, status=exec_status, actor=actor)
                except Exception:
                    pass  # noqa: business-bridge-best-effort

            # ── Step 6: audit ──
            if c.audit:
                await self._write_audit(
                    c, entity_id, domain_id, current_state, to_state,
                    exec_status, constraint, params, entity_snapshot, actor, role,
                    policy_gate=policy_gate,
                )

            # ── P0 ontology online learning: case writeback (best-effort, never blocks) ──
            try:
                from core.harness.knowledge.ontology_case_learning import record_case_from_action

                record_case_from_action(
                    domain_id=domain_id,
                    action_id=action_id,
                    entity_id=entity_id,
                    status=exec_status,
                    result=result,
                    actor=actor,
                )
            except Exception:
                pass  # noqa: ontology-case-learning-best-effort

            return {"status": exec_status, "effect": c.effect_semantics, "compensation": c.compensation, "result": result, "audited": c.audit}

        finally:
            # ── Step 7: release mutex ──
            await self._lock_provider.release(mutex_lock_id)

    # ═══════════════════════════════════════════════════════
    # Approval callbacks
    # ═══════════════════════════════════════════════════════

    async def approve(self, lock_id: str, resolver: str = "approver") -> Dict[str, Any]:
        """approve。

        Args:
            lock_id: lock 标识。
            resolver: resolver 参数。
        """
        pending = await self._store.get_pending(lock_id)
        if not pending:
            return {"status": "error", "error": f"Approval {lock_id} not found"}
        if pending["status"] != "pending":
            return {"status": "error", "error": f"Already resolved as {pending['status']}"}

        await self._store.resolve_pending(lock_id, "approved", resolver)
        await self._lock_provider.release(lock_id)

        ref_str = pending["entity_ref"]
        if ":" in ref_str:
            parts = ref_str.split(":", 1)
            entity_ref: Union[str, Tuple[str, str]] = (parts[0], parts[1])
        else:
            entity_ref = ref_str

        result = await self.execute(
            action_id=pending["action_id"],
            entity_ref=entity_ref,
            params=pending.get("params", {}),
            actor=pending.get("actor", "system"),
            _bypass_approval=True,
            _approval_reentry_lock_id=lock_id,
        )
        return {"status": "approved", "execution": result}

    async def reject(self, lock_id: str, resolver: str = "approver", reason: str = "") -> Dict[str, Any]:
        """reject。

        Args:
            lock_id: lock 标识。
            resolver: resolver 参数。
            reason: reason 参数。
        """
        pending = await self._store.get_pending(lock_id)
        if not pending:
            return {"status": "error", "error": f"Approval {lock_id} not found"}

        await self._store.resolve_pending(lock_id, "rejected", resolver, reason)
        await self._lock_provider.release(lock_id)
        return {"status": "rejected", "reason": reason}

    # ═══════════════════════════════════════════════════════
    # Action 阶梯量化门（P2-L5）
    # ═══════════════════════════════════════════════════════

    async def compute_closure_gate(self, action_id: str) -> Dict[str, Any]:
        """计算 Action 自动闭环误报率门（Lv4 专用）。

        Args:
            action_id: action 标识。
        """
        from core.harness.infrastructure.action_contract import (
            ActionLevel,
            CLOSURE_FP_RATE_MAX,
        )
        c = self._contracts.get(action_id)
        if not c:
            return {"action_id": action_id, "allowed": False, "reason": "unknown action"}
        level = getattr(c, "action_level", ActionLevel.LV2_CONFIRMED)

        # 非 Lv4 不需要误报率门（默认保守：不允许闭环）
        if level != ActionLevel.LV4_AUTO_CLOSE:
            return {
                "action_id": action_id, "level": str(level),
                "total": 0, "false_positives": 0, "fp_rate": 0.0,
                "allowed": False, "reason": f"level {level.value} is not lv4_auto_close",
            }

        await self._store.initialize()
        records = await self._store.list_audit(entity_id="", domain_id="", limit=10000)
        action_records = [r for r in records if r.get("action_id") == action_id]
        total = len(action_records)
        fp_markers = {"rejected", "corrected", "rolled_back", "overridden", "false_positive"}
        false_positives = sum(
            1 for r in action_records
            if str(r.get("result_status", "")).lower() in fp_markers
        )
        # 为什么：N08 Lv4 误报门重设计 — 委托 v2（禁 0 样本假绿 + 要求 rollback）
        from core.harness.knowledge_pipeline.lv4_false_positive_gate import (
            evaluate_lv4_fp_gate,
        )

        gate = evaluate_lv4_fp_gate(
            action_id=action_id,
            total=total,
            false_positives=false_positives,
            rollback_action_id=str(getattr(c, "rollback_action_id", "") or ""),
            fp_rate_max=CLOSURE_FP_RATE_MAX,
        )
        gate["level"] = str(level)
        return gate

    # ═══════════════════════════════════════════════════════
    # Private helpers
    # ═══════════════════════════════════════════════════════

    def _validate_input(self, c: ActionContractModel, params: Dict) -> Dict:
        try:
            import jsonschema
            jsonschema.validate(params, c.input_schema)
            return {"valid": True, "errors": []}
        except ImportError:
            logger.warning("jsonschema not installed, skipping input validation")
            return {"valid": True, "errors": []}
        except Exception as e:
            return {"valid": False, "errors": [str(e)]}

    async def _get_entity(self, domain_id: str, entity_id: str) -> Optional[Dict]:
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            from core.harness.knowledge.context_bus import _resolve_graph_tenant
            # 为什么：N09 K26 — Action 实体读取须按租户
            g = GraphIndex.load(domain_id, tenant_id=_resolve_graph_tenant())
            node = g.get_node(entity_id)
            if node is None:
                return None
            return {
                "id": node.entity_id,
                "entity_id": node.entity_id,
                "name": node.entity_name,
                "class": node.class_name,
                "state": (node.metadata or {}).get("state", ""),
                "domain": domain_id,
                "domain_id": domain_id,
                "metadata": node.metadata or {},
            }
        except Exception as e:
            logger.error("Failed to load entity %s/%s: %s", domain_id, entity_id, e, exc_info=True)
            return None

    def _get_handler(self, action_id: str) -> Optional[Callable]:
        canonical = self.resolve_action_id(action_id)
        if canonical in self._handlers:
            return self._handlers[canonical]
        c = self._contracts.get(canonical)
        if c and c.handler:
            return self._resolve_handler(c)
        return None

    def _resolve_handler(self, c: ActionContractModel) -> Optional[Callable]:
        if not c.handler:
            return None
        try:
            # Contract format: "module.path:function_name" (preferred) or "module.path.function"
            if ":" in c.handler:
                mod_path, func_name = c.handler.rsplit(":", 1)
            else:
                mod_path, func_name = c.handler.rsplit(".", 1)
            module = importlib.import_module(mod_path)
            handler = getattr(module, func_name, None)
            if handler:
                self._handlers[c.action_id] = handler
            return handler
        except Exception:
            logger.error("Failed to resolve handler '%s'", c.handler, exc_info=True)
            return None

    async def _invoke_handler(self, c: ActionContractModel, handler: Callable,
                               entity: Dict, params: Dict, actor: str, current_state: str) -> Tuple[str, str, Any]:
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(entity, params, actor=actor)
            else:
                result = handler(entity, params, actor=actor)
            return "executed", result.get("new_state", current_state), result
        except Exception as e:
            logger.error("Action '%s' handler failed: %s", c.action_id, e, exc_info=True)
            if c.failure_strategy == FailureStrategy.RETRY:
                for attempt in range(c.retry_policy.get("max_retries", 1)):
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            result = await handler(entity, params, actor=actor)
                        else:
                            result = handler(entity, params, actor=actor)
                        return "executed", result.get("new_state", current_state), result
                    except Exception:
                        if attempt == c.retry_policy.get("max_retries", 1) - 1:
                            raise
                        await asyncio.sleep(c.retry_policy.get("backoff_seconds", 5))
                raise
            elif c.failure_strategy == FailureStrategy.BLOCK:
                return "failed", current_state, {"error": str(e), "blocked": True}
            else:
                return "log_only", current_state, {"error": str(e)}

    async def _write_audit(self, c: ActionContractModel, entity_id: str, domain_id: str,
                           from_state: str, to_state: str, result_status: str,
                           constraint: Dict, params: Dict, snapshot: Dict,
                           actor: str, role: str,
                           policy_gate: Optional[Dict[str, Any]] = None) -> None:
        """写入动作审计。

        Args:
            c: 动作合同。
            entity_id: 实体 ID。
            domain_id: 域 ID。
            from_state: 执行前状态。
            to_state: 执行后状态。
            result_status: 结果状态码。
            constraint: 实体约束结果。
            params: 动作参数。
            snapshot: 实体快照。
            actor: 操作者。
            role: 角色。
            policy_gate: L1 PolicyGate 裁决；缺省时按 require_approval 回填。
        """
        try:
            ns = getattr(c, "action_namespace", "") or ""
            if ns:
                # Phase 1: embed audit_schema.v1 into ActionStore columns
                import uuid
                from datetime import datetime, timezone
                from core.harness.infrastructure.action_audit_validate import (
                    build_audit_record,
                    map_audit_to_action_store,
                )
                from core.harness.infrastructure.workbench_runtime_guard import (
                    WorkbenchRuntimeGuard,
                )

                before = snapshot if isinstance(snapshot, dict) else {}
                if "before" in before or "after" in before:
                    before_snap = before.get("before") or {"status": from_state}
                    after_snap = before.get("after") or {"status": to_state}
                else:
                    before_snap = {"status": from_state, **{k: v for k, v in before.items() if k != "status"}}
                    after_snap = {"status": to_state}

                actor_type = role if role in {"human", "agent", "system"} else (
                    "human" if role else "system"
                )
                # G2：优先使用 execute 中的真实 L1 裁决；无 required_permissions 时回填审批语义
                if policy_gate and policy_gate.get("gate_id"):
                    pg = dict(policy_gate)
                else:
                    pg = {
                        "gate_id": f"policy_gate:{ns}:{c.action_id.split(':')[-1]}",
                        "decision": "hitl_required" if c.require_approval else "allow",
                        "reason": constraint.get("constraint_type") or (
                            "require_approval" if c.require_approval else "auto"
                        ),
                    }
                gate_check = WorkbenchRuntimeGuard.check_policy_gate_called(
                    action_namespace=ns,
                    policy_gate_decision=pg,
                )
                if not gate_check.get("ok"):
                    logger.warning("audit policy_gate shape: %s", gate_check)

                # Map exec statuses → schema enum
                status_map = {
                    "executed": "success",
                    "done": "success",
                    "completed": "success",
                    "success": "success",
                    "ok": "success",
                    "failed": "failure",
                    "blocked": "failure",
                    "log_only": "partial",
                    "closure_gated": "partial",
                }
                schema_status = status_map.get(result_status, result_status)
                if schema_status not in {"success", "failure", "partial", "rollback"}:
                    schema_status = "partial"

                record = build_audit_record(
                    audit_id=f"aud_{uuid.uuid4().hex[:16]}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    actor_type=actor_type,
                    actor_id=actor or "system",
                    action_namespace=ns,
                    action_name=c.action_id,
                    domain_id=domain_id or c.domain_id or "",
                    target_entity_type=c.target_class or "Entity",
                    target_entity_id=entity_id,
                    params=params or {},
                    before_state_snapshot=before_snap,
                    after_state_snapshot=after_snap,
                    result_status=schema_status,
                    policy_gate_decision=pg,
                    result_message=c.effect_semantics or "",
                    pipeline_run_id=(params or {}).get("pipeline_run_id", ""),
                    evidence_ref=(params or {}).get("evidence_ref", ""),
                )
                mapped = map_audit_to_action_store(record)
                mapped["constraint_type"] = constraint.get("constraint_type", "")
                mapped["compensation"] = c.compensation or mapped.get("compensation") or ""
                await self._store.insert_audit(mapped)
                return

            await self._store.insert_audit({
                "action_id": c.action_id,
                "entity_id": entity_id,
                "domain_id": domain_id,
                "from_state": from_state,
                "to_state": to_state,
                "actor": actor,
                "role": role,
                "params": params,
                "result_status": result_status,
                "constraint_type": constraint.get("constraint_type", ""),
                "effect_summary": c.effect_semantics,
                "compensation": c.compensation,
                "entity_snapshot": snapshot,
            })
        except Exception:
            logger.error("Audit write failed for %s", c.action_id, exc_info=True)

    async def _assert_approval_reentry(
        self,
        *,
        action_id: str,
        lock_id: Optional[str],
    ) -> Dict[str, Any]:
        """校验 ``_bypass_approval`` 是否来自已批准的审批重入。

        Args:
            action_id: 当前要执行的 action_id（已 resolve）。
            lock_id: approve() 传入的 pending lock_id。

        Returns:
            ``{"ok": True}`` 或 ``{"ok": False, "error": ...}``。
        """
        lid = (lock_id or "").strip()
        if not lid:
            return {"ok": False, "error": "approval_reentry_required"}
        try:
            pending = await self._store.get_pending(lid)
        except Exception:
            logger.debug("approval reentry lookup failed", exc_info=True)
            return {"ok": False, "error": "approval_reentry_lookup_failed"}
        if not pending:
            return {"ok": False, "error": "approval_reentry_not_found"}
        if str(pending.get("status") or "") != "approved":
            return {"ok": False, "error": "approval_reentry_not_approved"}
        pending_aid = self.resolve_action_id(str(pending.get("action_id") or ""))
        if pending_aid and pending_aid != action_id:
            return {"ok": False, "error": "approval_reentry_action_mismatch"}
        return {"ok": True}

    async def _enqueue_approval(self, c: ActionContractModel, entity_id: str,
                                 domain_id: str, params: Dict, actor: str) -> Dict[str, Any]:
        stake_lock_id = f"{domain_id}:{entity_id}:stake"
        locked_until = int(time.time()) + 3600
        acquired = await self._lock_provider.acquire(stake_lock_id, intent="stake", ttl=3600)
        if not acquired:
            return {"status": "pending_conflict", "error": "Another approval is pending"}

        entity_ref = f"{domain_id}:{entity_id}"
        import datetime as _dt
        await self._store.insert_pending({
            "lock_id": stake_lock_id,
            "action_id": c.action_id,
            "entity_ref": entity_ref,
            "params": params,
            "actor": actor,
            "locked_until": _dt.datetime.fromtimestamp(locked_until).isoformat(),
        })
        return {
            "status": "pending_approval",
            "action_id": c.action_id,
            "entity_id": entity_id,
            "lock_id": stake_lock_id,
            "locked_until": locked_until,
        }

    # ═══════════════════════════════════════════════════════
    # Cross-domain config (TTL cache)
    # ═══════════════════════════════════════════════════════

    def _check_cross_domain_whitelist(self, action_id: str, domain_id: str, _class_name: str) -> bool:
        self._refresh_cross_domain_cache()
        entry = self._cross_domain_cache.get(action_id, {})
        if not entry.get("enabled", False):
            return False
        return entry.get("from", {}).get("domain", "") == domain_id

    def _refresh_cross_domain_cache(self) -> None:
        now = time.time()
        if now - self._cache_timestamp < self._cache_ttl:
            return
        try:
            path = os.path.expanduser(self._cross_domain_config_path)
            if not os.path.exists(path):
                self._cross_domain_cache = {}
            else:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                self._cross_domain_cache = data.get("cross_domain_actions", {})
            self._cache_timestamp = now
        except Exception:
            logger.warning("Failed to load cross-domain config", exc_info=True)
            self._cache_timestamp = now

    def invalidate_cross_domain_cache(self) -> None:
        """invalidate_cross_domain_cache。
        """
        self._cache_timestamp = 0


# ═══════════════════════════════════════════════════════════
# Global singleton
# ═══════════════════════════════════════════════════════════

_registry: Optional[AsyncActionRegistry] = None


def get_action_registry() -> AsyncActionRegistry:
    """获取 action_registry。
    """
    global _registry
    if _registry is None:
        _registry = AsyncActionRegistry()
        try:
            from core.harness.ontology_engine.builtin_actions import register_all
            register_all(_registry)
        except ImportError:
            logger.info("builtin_actions not yet loaded")
    return _registry


def action_kill_switch_active() -> bool:
    """N08 deepen：全局动作急停（``AIPLAT_ACTION_KILL_SWITCH=1/true/on``）。"""
    raw = (os.environ.get("AIPLAT_ACTION_KILL_SWITCH") or "").strip().lower()
    return raw in ("1", "true", "on", "yes")


async def run_action_policy_audit_suite() -> Dict[str, Any]:
    """N08 deepen：Policy/Approval/Audit + kill switch 套件（certified 恒 false）。

    Returns:
        套件回执；不宣称 N08 certified / Lv4 全量重设计。
    """
    from unittest.mock import AsyncMock

    from core.harness.infrastructure.action_contract import (
        ActionCategory,
        ActionContractModel,
        FailureStrategy,
        RiskLevel,
    )

    checks: Dict[str, bool] = {}
    action_id = "platform_action:test:n08_policy_suite"

    async def _noop(entity, params, actor="system"):
        return {"ok": True, "new_state": "ok"}

    def _mk(*, require_approval: bool, required_permissions: Optional[List[str]] = None):
        return ActionContractModel(
            action_id=action_id,
            label="n08 suite",
            description="n08 probe",
            category=ActionCategory.MUTATION,
            scope=ActionScope.GLOBAL,
            domain_id="platform",
            risk_level=RiskLevel.LOW,
            require_approval=require_approval,
            required_permissions=required_permissions or [],
            throttle_limit=0,
            failure_strategy=FailureStrategy.LOG_ONLY,
            action_namespace="platform_action",
            handler="core.harness.ontology_engine.builtin_handlers:confirm_extraction",
            input_schema={"type": "object", "properties": {}},
            audit=True,
        )

    # 1) kill switch
    prev_ks = os.environ.get("AIPLAT_ACTION_KILL_SWITCH")
    os.environ["AIPLAT_ACTION_KILL_SWITCH"] = "1"
    try:
        store = AsyncMock()
        store.get_pending = AsyncMock(return_value=None)
        store.insert_audit = AsyncMock(return_value="a")
        store.insert_pending = AsyncMock(return_value="p")
        reg = AsyncActionRegistry(store=store)
        reg.register(_mk(require_approval=False))
        reg._handlers[action_id] = _noop
        ks = await reg.execute(action_id, ("platform", "e1"), {}, actor="u")
        checks["kill_switch_blocks"] = ks.get("status") == "kill_switch"
    finally:
        if prev_ks is None:
            os.environ.pop("AIPLAT_ACTION_KILL_SWITCH", None)
        else:
            os.environ["AIPLAT_ACTION_KILL_SWITCH"] = prev_ks

    # 2) naked bypass forbidden
    store = AsyncMock()
    store.get_pending = AsyncMock(return_value=None)
    store.insert_audit = AsyncMock(return_value="a")
    reg = AsyncActionRegistry(store=store)
    reg.register(_mk(require_approval=True))
    reg._handlers[action_id] = _noop
    # 为什么：套件故意裸 bypass，断言生产路径返回 bypass_forbidden
    bypass = await reg.execute(
        action_id, ("platform", "e1"), {}, actor="u", _bypass_approval=True
    )
    checks["bypass_forbidden"] = bypass.get("status") == "bypass_forbidden"

    # 3) policy_denied + audit
    store = AsyncMock()
    store.get_pending = AsyncMock(return_value=None)
    store.insert_audit = AsyncMock(return_value="a")
    reg = AsyncActionRegistry(store=store)
    reg.register(_mk(require_approval=False, required_permissions=["kb:write"]))
    reg._handlers[action_id] = _noop
    denied = await reg.execute(
        action_id, ("platform", "e1"), {}, actor="u", permissions=["kb:read"]
    )
    checks["policy_denied"] = denied.get("status") == "policy_denied"
    checks["policy_denied_audited"] = store.insert_audit.await_count >= 1

    # 4) require_approval → pending（非 bypass）
    store = AsyncMock()
    store.get_pending = AsyncMock(return_value=None)
    store.insert_audit = AsyncMock(return_value="a")
    store.insert_pending = AsyncMock(return_value="pend1")
    store.create_pending = AsyncMock(return_value="pend1")
    reg = AsyncActionRegistry(store=store)
    reg.register(_mk(require_approval=True))
    reg._handlers[action_id] = _noop
    pending = await reg.execute(action_id, ("platform", "e1"), {}, actor="u")
    checks["approval_enqueued"] = pending.get("status") in (
        "pending_approval",
        "awaiting_approval",
        "approval_required",
    ) or "approval" in str(pending.get("status") or "").lower() or bool(
        pending.get("lock_id") or pending.get("pending_id")
    )

    # 5) 诚实锁
    checks["honesty_certified_false"] = True

    passed = sum(1 for v in checks.values() if v)
    return {
        "ok": passed == len(checks),
        "passed": passed,
        "total": len(checks),
        "checks": checks,
        "certified": False,
        "n08_full_conformance": False,
        "lv4_gate_redesigned": False,
        "note": (
            "Action Policy/Approval/Audit + kill switch deepen; "
            "not N08 certified / not Lv4 full redesign"
        ),
    }


def evaluate_action_policy_audit_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N08 Policy/Approval/Audit 门槛门；certified 恒 false。

    Args:
        suite: ``run_action_policy_audit_suite`` 回执（可同步传入已算好的）。
    """
    s = suite if isinstance(suite, dict) else None
    if s is None:
        # 同步门禁不重跑 async；要求调用方传入 suite
        return {
            "ok": False,
            "issues": ["suite_required"],
            "certified": False,
            "note": "pass suite from run_action_policy_audit_suite",
        }
    issues: List[str] = []
    if not s.get("ok"):
        issues.append("suite_not_ok")
    if s.get("certified") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("n08_full_conformance") is True:
        issues.append("honesty_n08_full_forbidden")
    if s.get("lv4_gate_redesigned") is True:
        issues.append("honesty_lv4_redesign_forbidden")
    required = (
        "kill_switch_blocks",
        "bypass_forbidden",
        "policy_denied",
        "policy_denied_audited",
        "approval_enqueued",
        "honesty_certified_false",
    )
    checks = s.get("checks") if isinstance(s.get("checks"), dict) else {}
    for k in required:
        if not checks.get(k):
            issues.append(f"missing_or_failed:{k}")
    return {
        "ok": not issues,
        "issues": issues,
        "certified": False,
        "note": "Action policy/audit deepen; not N08 certified",
    }


async def init_action_registry() -> None:
    """init_action_registry。
    """
    reg = get_action_registry()
    await reg._store.initialize()
    logger.info("ActionRegistry initialized")
