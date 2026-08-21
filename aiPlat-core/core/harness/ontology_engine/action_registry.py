"""
AsyncActionRegistry — enterprise action execution engine (v3, 2026-07-29).

7-step execution pipeline:
  0. mutex lock (concurrent double-click prevention)
  1. input validation (JSON Schema)
  2. entity loading (single-domain str or cross-domain tuple)
  3. entity constraints (class + state + role → 4-level constraint_type)
  4. approval gate (stake lock + pending_approvals table)
  5. handler execution (async callable + retry strategy)
  6. audit write (action_audit table with entity snapshot)
  7. mutex release
"""
from __future__ import annotations

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
        self._contracts: Dict[str, ActionContractModel] = {}
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
        if contract.action_id in self._contracts:
            logger.warning("Action '%s' already registered, overwriting", contract.action_id)
        self._contracts[contract.action_id] = contract
        if contract.handler:
            self._resolve_handler(contract)
        logger.info("Registered: %s (%s)", contract.action_id, contract.label)

    def register_batch(self, contracts: List[ActionContractModel]) -> int:
        for c in contracts:
            self.register(c)
        return len(contracts)

    # ═══════════════════════════════════════════════════════
    # Query
    # ═══════════════════════════════════════════════════════

    def get(self, action_id: str) -> Optional[ActionContractModel]:
        return self._contracts.get(action_id)

    def list_for_class(
        self, domain_id: str, class_name: str, state: str = "", role: str = "",
        include_cross_domain: bool = False,
    ) -> List[ActionContractModel]:
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

        constraint_type mapping for frontend coloring:
          "permission" → red, "state" → orange, "class" → orange,
          "scope" → gray, "unknown" → gray
        """
        c = self._contracts.get(action_id)
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
        _bypass_approval: bool = False,
    ) -> Dict[str, Any]:
        c = self._contracts.get(action_id)
        if not c:
            return {"status": "invalid", "error": f"Unknown action: {action_id}"}

        # resolve entity
        if isinstance(entity_ref, tuple):
            entity_id = entity_ref[1]
            domain_id = entity_ref[0]
        else:
            entity_id = entity_ref
            domain_id = c.domain_id or "default"

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
                return {"status": "not_found", "error": f"Entity {entity_id} not found in {domain_id}"}

            class_name = entity.get("class") or c.target_class or "Unknown"
            current_state = entity.get("state") or ""
            entity_snapshot = {"id": entity_id, "class": class_name, "state": current_state, "domain": domain_id}

            # ── Step 3: entity constraints ──
            constraint = self.check_entity_constraints(action_id, domain_id, class_name, current_state, role)
            if not constraint["valid"]:
                await self._write_audit(c, entity_id, domain_id, current_state, current_state,
                                        "blocked", constraint, params, entity_snapshot, actor, role)
                return {"status": "blocked", "reason": constraint["reason"], "constraint_type": constraint["constraint_type"]}

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
            if not _bypass_approval and c.require_approval:
                if c.approval_threshold is not None:
                    amount = params.get("amount", 0)
                    if amount < c.approval_threshold:
                        logger.info("Amount %.2f < threshold %.2f, auto-approved", amount, c.approval_threshold)
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
                await self._write_audit(c, entity_id, domain_id, current_state, to_state,
                                        exec_status, constraint, params, entity_snapshot, actor, role)

            return {"status": exec_status, "effect": c.effect_semantics, "compensation": c.compensation, "result": result, "audited": c.audit}

        finally:
            # ── Step 7: release mutex ──
            await self._lock_provider.release(mutex_lock_id)

    # ═══════════════════════════════════════════════════════
    # Approval callbacks
    # ═══════════════════════════════════════════════════════

    async def approve(self, lock_id: str, resolver: str = "approver") -> Dict[str, Any]:
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
        )
        return {"status": "approved", "execution": result}

    async def reject(self, lock_id: str, resolver: str = "approver", reason: str = "") -> Dict[str, Any]:
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

        误报 = 历史审计中人工纠正过的执行（result_status 为
        rejected / corrected / rolled_back / overridden 等）。

        返回 {action_id, level, total, false_positives, fp_rate, allowed}
        Lv4 且 fp_rate < CLOSURE_FP_RATE_MAX(0.5%) → allowed=True；否则降级人工确认。
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
        fp_rate = (false_positives / total) if total else 0.0
        allowed = fp_rate < CLOSURE_FP_RATE_MAX
        return {
            "action_id": action_id,
            "level": str(level),
            "total": total,
            "false_positives": false_positives,
            "fp_rate": round(fp_rate, 4),
            "fp_rate_max": CLOSURE_FP_RATE_MAX,
            "allowed": allowed,
            "reason": (
                f"fp_rate={fp_rate:.4f} < {CLOSURE_FP_RATE_MAX} — auto-close allowed"
                if allowed
                else f"fp_rate={fp_rate:.4f} ≥ {CLOSURE_FP_RATE_MAX} — downgrade to human confirmation"
            ),
        }

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
            g = GraphIndex.load(domain_id)
            node = g.get_node(entity_id)
            if node is None:
                return None
            return {
                "id": node.entity_id,
                "name": node.entity_name,
                "class": node.class_name,
                "state": (node.metadata or {}).get("state", ""),
                "domain": domain_id,
                "metadata": node.metadata or {},
            }
        except Exception as e:
            logger.error("Failed to load entity %s/%s: %s", domain_id, entity_id, e, exc_info=True)
            return None

    def _get_handler(self, action_id: str) -> Optional[Callable]:
        if action_id in self._handlers:
            return self._handlers[action_id]
        c = self._contracts.get(action_id)
        if c and c.handler:
            return self._resolve_handler(c)
        return None

    def _resolve_handler(self, c: ActionContractModel) -> Optional[Callable]:
        if not c.handler:
            return None
        try:
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
                           actor: str, role: str) -> None:
        try:
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
        self._cache_timestamp = 0


# ═══════════════════════════════════════════════════════════
# Global singleton
# ═══════════════════════════════════════════════════════════

_registry: Optional[AsyncActionRegistry] = None


def get_action_registry() -> AsyncActionRegistry:
    global _registry
    if _registry is None:
        _registry = AsyncActionRegistry()
        try:
            from core.harness.ontology_engine.builtin_actions import register_all
            register_all(_registry)
        except ImportError:
            logger.info("builtin_actions not yet loaded")
    return _registry


async def init_action_registry() -> None:
    reg = get_action_registry()
    await reg._store.initialize()
    logger.info("ActionRegistry initialized")
