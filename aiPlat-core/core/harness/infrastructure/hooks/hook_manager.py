"""
Hooks System Module
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Callable, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class HookPhase(Enum):
    """Hook execution phases"""
    # Execution hooks
    PRE_LOOP = "pre_loop"
    POST_LOOP = "post_loop"
    PRE_REASONING = "pre_reasoning"
    POST_REASONING = "post_reasoning"
    PRE_ACT = "pre_act"
    POST_ACT = "post_act"
    PRE_OBSERVE = "pre_observe"
    POST_OBSERVE = "post_observe"
    
    # Session hooks
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    
    # Tool hooks
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    
    # Skill hooks
    PRE_SKILL_USE = "pre_skill_use"
    POST_SKILL_USE = "post_skill_use"
    
    # Control hooks
    STOP = "stop"
    
    # Contract hooks (Sprint Contract)
    PRE_CONTRACT_CHECK = "pre_contract_check"
    POST_CONTRACT_CHECK = "post_contract_check"
    SCOPE_REVIEW = "scope_review"
    
    # Approval hooks (Human-in-the-Loop)
    PRE_APPROVAL_CHECK = "pre_approval_check"
    POST_APPROVAL_CHECK = "post_approval_check"


@dataclass
class HookContext:
    """Hook execution context"""
    phase: HookPhase
    state: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Hook(Callable):
    """Hook definition"""
    
    def __init__(
        self,
        name: str,
        callback: Callable,
        phase: HookPhase,
        priority: int = 0
    ):
        self.name = name
        self.callback = callback
        self.phase = phase
        self.priority = priority
    
    async def __call__(self, context: HookContext) -> Any:
        import asyncio
        if asyncio.iscoroutinefunction(self.callback):
            return await self.callback(context)
        return self.callback(context)


class IHookManager(ABC):
    """
    Hook manager interface
    """
    
    @abstractmethod
    def register(self, hook: Hook) -> None:
        """Register a hook"""
        pass
    
    @abstractmethod
    def unregister(self, name: str) -> None:
        """Unregister a hook"""
        pass
    
    @abstractmethod
    async def trigger(self, phase: HookPhase, context: HookContext) -> List[Any]:
        """Trigger hooks for a phase"""
        pass
    
    @abstractmethod
    def get_hooks(self, phase: HookPhase) -> List[Hook]:
        """Get hooks for a phase"""
        pass


class HookManager(IHookManager):
    """
    Default hook manager implementation
    """
    
    def __init__(self):
        self._hooks: Dict[HookPhase, List[Hook]] = {phase: [] for phase in HookPhase}
        # Register default hooks
        try:
            for hook in get_default_hooks().values():
                self.register(hook)
        except Exception:
            pass
        # Optional: load workspace hooks (Claude Code-style extension point)
        try:
            from .workspace_loader import load_workspace_hooks

            load_workspace_hooks(hook_manager=self)
        except Exception:
            pass
    
    def register(self, hook: Hook) -> None:
        """Register a hook"""
        self._hooks[hook.phase].append(hook)
        self._hooks[hook.phase].sort(key=lambda h: h.priority, reverse=True)
    
    def unregister(self, name: str) -> None:
        """Unregister a hook by name"""
        for hooks in self._hooks.values():
            for i, hook in enumerate(hooks):
                if hook.name == name:
                    hooks.pop(i)
                    return
    
    async def trigger(self, phase: HookPhase, context: HookContext) -> List[Any]:
        """Trigger hooks for a phase"""
        results = []
        
        for hook in self._hooks[phase]:
            try:
                result = await hook(context)
                results.append(result)
            except Exception as e:
                # 生产环境可观测：保留堆栈信息
                logger.exception("Hook %s failed (phase=%s)", hook.name, phase.value)
        
        return results
    
    def get_hooks(self, phase: HookPhase) -> List[Hook]:
        """Get hooks for a phase"""
        return self._hooks[phase].copy()


def create_hook(
    name: str,
    callback: Callable,
    phase: HookPhase,
    priority: int = 0
) -> Hook:
    """Create a hook"""
    return Hook(name=name, callback=callback, phase=phase, priority=priority)


def get_default_hooks() -> Dict[str, Hook]:
    """Get default system hooks"""
    hooks = {}
    
    # Pre-loop hook
    async def pre_loop_hook(context: HookContext):
        context.state = context.state or {}
        context.state["step_count"] = 0
    
    hooks["pre_loop"] = create_hook(
        name="pre_loop",
        callback=pre_loop_hook,
        phase=HookPhase.PRE_LOOP,
        priority=100
    )
    
    # Post-loop hook
    async def post_loop_hook(context: HookContext):
        logger.info("Loop completed: %s", context.state)
    
    hooks["post_loop"] = create_hook(
        name="post_loop",
        callback=post_loop_hook,
        phase=HookPhase.POST_LOOP,
        priority=100
    )
    
    # Pre-tool-use hook
    async def pre_tool_use_hook(context: HookContext):
        logger.info("Tool call: %s", context.metadata.get("tool_name"))
    
    hooks["pre_tool_use"] = create_hook(
        name="pre_tool_use",
        callback=pre_tool_use_hook,
        phase=HookPhase.PRE_TOOL_USE,
        priority=50
    )

    # Session hooks (lightweight defaults)
    async def session_start_hook(context: HookContext):
        context.state = context.state or {}
        context.state.setdefault("session_started", True)

    hooks["session_start"] = create_hook(
        name="session_start",
        callback=session_start_hook,
        phase=HookPhase.SESSION_START,
        priority=100,
    )

    async def session_end_hook(context: HookContext):
        return {"ended": True, "reason": context.state.get("reason")}

    hooks["session_end"] = create_hook(
        name="session_end",
        callback=session_end_hook,
        phase=HookPhase.SESSION_END,
        priority=100,
    )

    # Approval check hook (baseline secret scan on write/edit tools).
    try:
        from .builtin import SecurityScanHook

        scanner = SecurityScanHook(scan_on_write=True)

        async def approval_scan_hook(context: HookContext):
            meta = context.state or {}
            tool_name = meta.get("tool_name") or meta.get("tool")
            tool_args = meta.get("tool_args") or {}
            # Tool scan allow/deny list (comma-separated, case-insensitive)
            # - If allowlist is set: only scan tools in allowlist
            # - Otherwise: scan default set (write, edit)
            # - If denylist is set: exclude tools in denylist
            import os

            def _parse_list(v: str) -> List[str]:
                return [x.strip().lower() for x in (v or "").split(",") if x.strip()]

            allowlist = _parse_list(os.getenv("AIPLAT_SECURITY_SCAN_TOOL_ALLOWLIST", ""))
            denylist = set(_parse_list(os.getenv("AIPLAT_SECURITY_SCAN_TOOL_DENYLIST", "")))
            default_scan = set(_parse_list(os.getenv("AIPLAT_SECURITY_SCAN_TOOLS", "write,edit")))

            name_norm = str(tool_name or "").strip().lower()
            should_scan = (name_norm in allowlist) if allowlist else (name_norm in default_scan)
            if name_norm in denylist:
                should_scan = False

            findings: List[Dict[str, Any]] = []
            if should_scan:
                findings = scanner.scan_tool_input(
                    "Write" if name_norm == "write" else ("Edit" if name_norm == "edit" else str(tool_name)),
                    tool_args if isinstance(tool_args, dict) else {},
                )

            # Write audit event into the execution context when provided
            exec_ctx = meta.get("context")
            if isinstance(exec_ctx, dict):
                events = exec_ctx.setdefault("audit_events", [])
                if isinstance(events, list):
                    events.append(
                        {
                            "event": "security_scan",
                            "tool_name": str(tool_name),
                            "scanned": should_scan,
                            "blocked": bool(findings),
                            "findings": findings,
                        }
                    )
            if findings:
                return {
                    "allow": False,
                    "action": "deny",
                    "reason": f"Security scan blocked potential secrets: {findings[0].get('type')}",
                    "metadata": {"findings": findings},
                }
            return {"allow": True}

        hooks["pre_approval_check"] = create_hook(
            name="pre_approval_check",
            callback=approval_scan_hook,
            phase=HookPhase.PRE_APPROVAL_CHECK,
            priority=80,
        )
    except Exception:
        pass
    
    return hooks
