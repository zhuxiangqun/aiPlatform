"""
Hooks System Module
"""

import os
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

    # Pre-reasoning repo inference: try to pick correct CLAUDE.md BEFORE LLM reasoning.
    # This helps the model plan/think under the right project guidelines, not only at tool time.
    async def repo_root_from_messages_hook(context: HookContext):
        import os
        from pathlib import Path

        meta = context.state or {}
        # Only do best-effort inference; never hard-fail here.
        try:
            from core.harness.context.claude_md import infer_claude_md_files_from_text
            from core.harness.kernel.execution_context import get_active_workspace_context, set_active_workspace_context, ActiveWorkspaceContext
        except Exception:
            return {"allow": True}

        # Already has multi files -> nothing to do
        wctx0 = get_active_workspace_context()
        if wctx0 and getattr(wctx0, "claude_md_files", None):
            return {"allow": True}

        task = str(meta.get("task") or "")
        msgs = meta.get("messages") if isinstance(meta.get("messages"), list) else []
        tail = []
        for m in msgs[-8:]:
            if isinstance(m, dict):
                tail.append(str(m.get("content") or ""))
        text = "\n".join([task] + tail).strip()
        if not text:
            return {"allow": True}

        files = infer_claude_md_files_from_text(text)
        if not files:
            return {"allow": True}

        # Choose a base repo_root for context engine; keep existing repo_root if set.
        repo_root = getattr(wctx0, "repo_root", None) if wctx0 else None
        if not (isinstance(repo_root, str) and repo_root.strip()):
            # best-effort: common parent of all CLAUDE.md files if it has CLAUDE.md, else use first file parent
            try:
                parents = [Path(f).resolve().parent for f in files]
                common = parents[0]
                for p in parents[1:]:
                    while common not in p.parents and common != p:
                        common = common.parent
                repo_root = str(common)
            except Exception:
                repo_root = str(Path(files[0]).resolve().parent)

        set_active_workspace_context(
            ActiveWorkspaceContext(
                repo_root=str(repo_root) if repo_root else None,
                toolset=getattr(wctx0, "toolset", None) if wctx0 else None,
                claude_md_files=list(files),
            )
        )
        return {"allow": True, "claude_md_files": list(files), "repo_root_selected": repo_root}

    hooks["pre_reasoning_repo_root_from_messages"] = create_hook(
        name="pre_reasoning_repo_root_from_messages",
        callback=repo_root_from_messages_hook,
        phase=HookPhase.PRE_REASONING,
        priority=90,
    )

    # Repo-aware CLAUDE.md selection (per-file nearest ancestor)
    # - Updates active workspace context repo_root (and optional claude_md_files)
    # - Optionally enforces presence of CLAUDE.md for write/edit operations
    async def repo_root_from_tool_args_hook(context: HookContext):
        import os
        from pathlib import Path

        meta = context.state or {}
        tool_name = meta.get("tool_name") or meta.get("tool")
        tool_args = meta.get("tool_args") or {}

        # Only try when args looks like a dict
        if not isinstance(tool_args, dict):
            return {"allow": True}

        try:
            from core.harness.context.claude_md import find_nearest_claude_md_root, load_claude_md
            from core.harness.kernel.execution_context import get_active_workspace_context, set_active_workspace_context, ActiveWorkspaceContext
        except Exception:
            return {"allow": True}

        # Extract likely file paths from tool args
        PATH_KEYS = {"path", "file", "file_path", "filepath", "filename", "target_path", "dest_path", "src_path"}
        LIST_KEYS = {"paths", "file_paths", "files"}

        candidates = []
        for k, v in list(tool_args.items()):
            kk = str(k or "").strip().lower()
            if kk in PATH_KEYS and isinstance(v, str):
                candidates.append(v)
            elif kk in LIST_KEYS and isinstance(v, list):
                for x in v:
                    if isinstance(x, str):
                        candidates.append(x)

        # If repo_root is already explicitly provided, prefer it.
        explicit_repo_root = None
        for k in ("repo_root", "directory", "workspace_root"):
            if isinstance(tool_args.get(k), str) and str(tool_args.get(k)).strip():
                explicit_repo_root = str(tool_args.get(k)).strip()
                break

        roots = []
        for p in candidates:
            p0 = str(p or "").strip()
            if not p0.startswith("/"):
                continue
            r = find_nearest_claude_md_root(p0)
            if r:
                roots.append(r)

        roots = list(dict.fromkeys([r for r in roots if r]))  # dedup preserve order

        # Nothing to do
        if explicit_repo_root or not roots:
            return {"allow": True, "repo_root_selected": explicit_repo_root or None}

        # Choose: single root => use it; multiple => use workspace root if present, and pass all CLAUDE.md files
        selected_root = roots[0] if len(roots) == 1 else None
        claude_files = []
        for r in roots:
            try:
                p = str(Path(r) / "CLAUDE.md")
                if Path(p).is_file():
                    claude_files.append(p)
            except Exception:
                continue

        if not selected_root:
            # best-effort workspace fallback: first common parent that has CLAUDE.md, else keep current repo_root
            try:
                # simplest: use common parent of all roots
                parents = [Path(r).resolve() for r in roots]
                common = parents[0]
                for p in parents[1:]:
                    while common not in p.parents and common != p:
                        common = common.parent
                if (common / "CLAUDE.md").is_file():
                    selected_root = str(common)
            except Exception:
                selected_root = None

        wctx = get_active_workspace_context()
        # If we have CLAUDE.md files, persist them for downstream prompt assembly even if selected_root is None.
        if claude_files:
            selected_root = selected_root or (getattr(wctx, "repo_root", None) if wctx else None) or roots[0]
            set_active_workspace_context(
                ActiveWorkspaceContext(
                    repo_root=str(selected_root) if selected_root else None,
                    toolset=getattr(wctx, "toolset", None) if wctx else None,
                    claude_md_files=claude_files or None,
                )
            )

        # Optional enforcement: require all touched paths to have a nearest CLAUDE.md root
        enforce = os.getenv("AIPLAT_ENFORCE_CLAUDE_MD", "false").strip().lower() in ("1", "true", "yes", "y", "on")
        if enforce:
            # If multiple roots and no CLAUDE.md found for some path, deny.
            missing = []
            for p in candidates:
                p0 = str(p or "").strip()
                if not p0.startswith("/"):
                    continue
                if not find_nearest_claude_md_root(p0):
                    missing.append(p0)
            if missing:
                return {"allow": False, "reason": f"CLAUDE.md is required for touched paths but not found: {missing[:3]}"}

            # Also block if selected repo_root's CLAUDE.md is blocked by policy
            try:
                if selected_root:
                    _c, _p, d = load_claude_md(str(selected_root))
                    if getattr(d, "action", "none") in {"block", "approval_required"}:
                        return {"allow": False, "reason": f"CLAUDE.md blocked by policy under {selected_root}"}
            except Exception:
                return {"allow": False, "reason": "CLAUDE.md enforcement failed during tool selection"}

        return {"allow": True, "repo_root_selected": selected_root, "claude_md_files": claude_files}

    hooks["pre_approval_check_repo_root_from_tool_args"] = create_hook(
        name="pre_approval_check_repo_root_from_tool_args",
        callback=repo_root_from_tool_args_hook,
        phase=HookPhase.PRE_APPROVAL_CHECK,
        priority=90,
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

    # Contract enforcement: require project-level CLAUDE.md (server-side).
    # This makes project guidelines effective in the execution chain, not just in IDEs.
    async def enforce_claude_md_hook(context: HookContext):
        import os
        from pathlib import Path

        enforce = os.getenv("AIPLAT_ENFORCE_CLAUDE_MD", "false").strip().lower() in ("1", "true", "yes", "y", "on")
        if not enforce:
            return {"allow": True}

        try:
            from core.harness.kernel.execution_context import get_active_workspace_context
            from core.harness.kernel.execution_context import set_active_workspace_context, ActiveWorkspaceContext
            from core.harness.context.claude_md import load_claude_md, infer_claude_md_files_from_text

            wctx = get_active_workspace_context()
            repo_root = getattr(wctx, "repo_root", None) if wctx else None
            # If no repo_root is provided, try infer from loop state/task/messages (best-effort).
            if not (isinstance(repo_root, str) and repo_root.strip()):
                try:
                    st = (context.state or {}).get("state")  # LoopState (best-effort)
                    ctx = getattr(st, "context", None) if st is not None else None
                    task = str((ctx or {}).get("task") or "") if isinstance(ctx, dict) else ""
                    msgs = (ctx or {}).get("messages") if isinstance(ctx, dict) else []
                    tail = []
                    if isinstance(msgs, list):
                        for m in msgs[-8:]:
                            if isinstance(m, dict):
                                tail.append(str(m.get("content") or ""))
                    text = "\n".join([task] + tail).strip()
                    files = infer_claude_md_files_from_text(text) if text else []
                    if files:
                        # use common parent as repo_root
                        try:
                            import pathlib

                            parents = [pathlib.Path(f).resolve().parent for f in files]
                            common = parents[0]
                            for p in parents[1:]:
                                while common not in p.parents and common != p:
                                    common = common.parent
                            repo_root = str(common)
                        except Exception:
                            repo_root = str(Path(files[0]).resolve().parent)
                        set_active_workspace_context(
                            ActiveWorkspaceContext(
                                repo_root=str(repo_root),
                                toolset=getattr(wctx, "toolset", None) if wctx else None,
                                claude_md_files=list(files),
                            )
                        )
                except Exception:
                    pass
            # Still no repo_root -> allow (backward compatible) but record
            if not (isinstance(repo_root, str) and repo_root.strip()):
                return {"allow": True, "claude_md": {"enforced": True, "skipped": "no_repo_root"}}

            content, used_path, decision = load_claude_md(str(repo_root))
            if not used_path or not Path(used_path).is_file():
                return {"allow": False, "reason": f"CLAUDE.md is required but not found under repo_root={repo_root}"}
            if not (content or "").strip():
                return {"allow": False, "reason": f"CLAUDE.md is required but empty: {used_path}"}
            action = getattr(decision, "action", "none")
            if action in {"block", "approval_required"}:
                pol = getattr(decision, "policy", None)
                findings = getattr(decision, "findings", None) or []
                return {"allow": False, "reason": f"CLAUDE.md blocked by policy={pol}, findings={findings}", "metadata": {"file": used_path}}
            return {"allow": True, "claude_md": {"enforced": True, "file": used_path, "sha256": getattr(decision, 'sha256', None)}}
        except Exception as e:
            # Fail closed when enforcement is enabled (safer default).
            return {"allow": False, "reason": f"CLAUDE.md enforcement failed: {e}"}


    # ── Auto-evaluation hook ──────────────────────────────────────────
    async def auto_eval_session_end_hook(context: HookContext):
        u"""Automatically evaluate agent execution quality at session end.
        
        Opt-in via AIPLAT_ENABLE_AUTO_EVAL=true.
        Captures basic task completion, step count, error count, and tool call stats.
        Saves to ~/.aiplat/eval_results/ for the evaluation dashboard.
        """
        import os as _os, json as _json, time as _time
        if _os.getenv("AIPLAT_ENABLE_AUTO_EVAL", "").lower() not in ("1", "true", "yes"):
            return {"continue": True}
        
        try:
            loop_state = context.state.get("state") if isinstance(context.state, dict) else None
            if not loop_state:
                return {"continue": True}
            
            ctx = getattr(loop_state, "context", {}) or {}
            run_id = ctx.get("_run_id", "") or ""
            agent_id = ctx.get("_agent_id", "") or "unknown"
            output = ctx.get("output", "") or ""
            stop_reason = ctx.get("_stop_reason", "unknown")
            error = ctx.get("error", None) or ctx.get("_error", None)
            
            messages = getattr(loop_state, "messages", None) or []
            steps = len(messages) if messages else 0
            
            from core.harness.evaluation.eval_types import TaskResultLevel
            if error:
                level = TaskResultLevel.ERROR_FAILURE
            elif str(stop_reason).lower() in ("finished", "max_steps", "stop", "done") and output:
                level = TaskResultLevel.COMPLETE
            elif stop_reason == "PAUSED":
                level = TaskResultLevel.PARTIAL
            else:
                level = TaskResultLevel.CORRECT_FAILURE if output else TaskResultLevel.ERROR_FAILURE
            
            tool_calls, tool_errors, tokens_est = 0, 0, 0
            try:
                history = getattr(loop_state, "history", None) or []
                for entry in history:
                    if isinstance(entry, dict):
                        kind = entry.get("kind", "")
                        if kind in ("tool_call", "tool"):
                            tool_calls += 1
                            if entry.get("error") or entry.get("status") == "error":
                                tool_errors += 1
                msg_text = ""
                for m in messages:
                    msg_text += str(getattr(m, "content", m)) if not isinstance(m, str) else m
                tokens_est = len(msg_text) // 4 if msg_text else 0
            except Exception:
                pass
            
            result = {
                "agent_id": agent_id, "eval_set_id": "auto_session", "eval_time": _time.time(),
                "total_tasks": 1,
                "composite_score": {"complete": 100, "partial": 70, "correct_failure": 40, "error_failure": 0}[level.value],
                "grade": {"complete": "A", "partial": "B", "correct_failure": "C", "error_failure": "F"}[level.value],
                "task_completion": {"level": level.value,
                    "complete": 1 if level == TaskResultLevel.COMPLETE else 0,
                    "partial": 1 if level == TaskResultLevel.PARTIAL else 0,
                    "error_failure": 1 if level == TaskResultLevel.ERROR_FAILURE else 0,
                    "reliability": 100.0 if level != TaskResultLevel.ERROR_FAILURE else 0.0},
                "tool_quality": {"overall": 100.0 if tool_calls == 0 else round((1 - tool_errors/max(tool_calls,1))*100,1)},
                "step_efficiency": {"avg_steps": steps},
                "safety": {"violations": 0}, "cost": {"tokens_per_task": tokens_est, "calls_per_task": tool_calls},
                "run_id": run_id, "stop_reason": stop_reason,
            }
            
            from pathlib import Path as _Path
            results_dir = _Path(_os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))) / "eval_results"
            results_dir.mkdir(parents=True, exist_ok=True)
            out_path = results_dir / f"{agent_id}_{int(_time.time())}_auto.json"
            out_path.write_text(_json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            
        except Exception:
            import logging as _logging
            _logging.getLogger("auto_eval").warning("auto_eval_session_end failed", exc_info=True)
        
        return {"continue": True}
    
    hooks["auto_eval_session_end"] = create_hook(
        name="auto_eval_session_end",
        callback=auto_eval_session_end_hook,
        phase=HookPhase.SESSION_END,
        priority=50,
    )

    hooks["pre_contract_check_claude_md"] = create_hook(
        name="pre_contract_check_claude_md",
        callback=enforce_claude_md_hook,
        phase=HookPhase.PRE_CONTRACT_CHECK,
        priority=95,
    )
    
    return hooks
