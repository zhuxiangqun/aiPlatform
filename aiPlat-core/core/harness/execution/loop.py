"""
Execution Loop - Base Implementation

Implements ILoop interface with ReAct (Reasoning + Acting) execution pattern.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
import asyncio
import os

from ..interfaces.loop import (
    ILoop,
    LoopState,
    LoopStateEnum,
    LoopConfig,
    LoopResult,
)
from ..infrastructure.hooks import HookManager, HookPhase, HookContext
from .tool_calling import parse_action_call, parse_tool_call
from ..syscalls import sys_llm_generate, sys_skill_call, sys_tool_call
from ..assembly import PromptAssembler


class BaseLoop(ILoop):
    """
    Base execution loop implementation
    
    Provides common functionality for execution loops.
    """

    def __init__(
        self,
        config: Optional[LoopConfig] = None,
        hook_manager: Optional[HookManager] = None
    ):
        self._config = config or LoopConfig()
        self._hook_manager = hook_manager or HookManager()
        self._current_state = LoopState()
        self._current_node = "init"
        self._step_handlers: Dict[LoopStateEnum, Callable] = {}

    async def run(self, state: LoopState, config: LoopConfig) -> LoopResult:
        """Run execution loop"""
        self._current_state = state
        self._config = config
        stop_reason = None

        # Session start + pre-loop hooks
        await self._trigger_hook(HookPhase.SESSION_START, {"state": state, "config": config})
        await self._trigger_hook(HookPhase.PRE_LOOP, {"state": state})
        
        try:
            while self.should_continue(self._current_state):
                # Contract check (optional hooks may block)
                contract_results = await self._trigger_hook(
                    HookPhase.PRE_CONTRACT_CHECK,
                    {"state": self._current_state, "config": config},
                )
                deny = _extract_deny(contract_results)
                if deny:
                    await self._trigger_hook(HookPhase.SCOPE_REVIEW, {"reason": deny.get("reason", "contract denied")})
                    raise RuntimeError(deny.get("reason", "contract denied"))

                # Execute step
                self._current_state = await self.step(self._current_state)

                await self._trigger_hook(
                    HookPhase.POST_CONTRACT_CHECK,
                    {"state": self._current_state, "config": config},
                )

                # Observability-driven control (minimal closed-loop)
                self._apply_observability_control(self._current_state, config)
                if self._current_state.current == LoopStateEnum.PAUSED:
                    stop_reason = "paused"
                    break
                
                # Check for errors
                if self._current_state.current == LoopStateEnum.ERROR:
                    if config.stop_on_error:
                        break
            
            # Determine stop reason
            if self._current_state.current == LoopStateEnum.FINISHED:
                stop_reason = "finished"
            elif self._current_state.current == LoopStateEnum.ERROR:
                stop_reason = "error"
            elif self._current_state.step_count >= self._config.max_steps:
                stop_reason = "max_steps"
            elif self._current_state.budget_remaining <= 0:
                stop_reason = "budget_exhausted"
            else:
                stop_reason = "stopped"

            # Post-loop hook
            await self._trigger_hook(HookPhase.POST_LOOP, {"state": self._current_state})
            await self._trigger_hook(HookPhase.STOP, {"state": self._current_state, "reason": stop_reason})
            await self._trigger_hook(HookPhase.SESSION_END, {"state": self._current_state, "reason": stop_reason})
            
            error = None
            if self._current_state.current == LoopStateEnum.PAUSED:
                error = self._current_state.context.get("error") or "paused"
            elif self._current_state.current == LoopStateEnum.ERROR:
                error = self._current_state.context.get("error") or "error"

            return LoopResult(
                success=self._current_state.current == LoopStateEnum.FINISHED,
                final_state=self._current_state,
                output=self._current_state.context.get("output"),
                error=error,
                metadata={"steps": self._current_state.step_count, "stop_reason": stop_reason}
            )
            
        except Exception as e:
            self._current_state.current = LoopStateEnum.ERROR
            stop_reason = stop_reason or "exception"
            try:
                await self._trigger_hook(HookPhase.STOP, {"state": self._current_state, "reason": stop_reason, "error": str(e)})
                await self._trigger_hook(HookPhase.SESSION_END, {"state": self._current_state, "reason": stop_reason, "error": str(e)})
            except Exception:
                pass
            return LoopResult(
                success=False,
                final_state=self._current_state,
                error=str(e),
                metadata={"exception": type(e).__name__}
            )

    def should_continue(self, state: LoopState) -> bool:
        """Determine if loop should continue"""
        # Check max steps
        if state.step_count >= self._config.max_steps:
            return False
        
        # Check token budget
        if state.budget_remaining <= 0:
            return False
        
        # Check state
        if state.current in [LoopStateEnum.FINISHED, LoopStateEnum.ERROR, LoopStateEnum.PAUSED]:
            return False
        
        return True

    def _apply_observability_control(self, state: LoopState, config: LoopConfig) -> None:
        """
        Minimal observability-driven control:
        - If tool_error_rate > 0.2 and tool_calls >= 10 -> pause + require manual
        - If token usage ratio > 0.8 -> compact messages (keep last 2)
        """
        # 1) tool error rate based pause
        tool_calls = int(state.metadata.get("tool_calls", 0) or 0)
        tool_failures = int(state.metadata.get("tool_failures", 0) or 0)
        if tool_calls >= 10:
            rate = tool_failures / max(1, tool_calls)
            if rate > 0.2:
                state.current = LoopStateEnum.PAUSED
                state.metadata["control_action"] = "require_manual"
                state.metadata["tool_error_rate"] = rate
                state.context["observation"] = f"Paused: tool_error_rate={rate:.2f} exceeds threshold"
                return

        # 2) token budget based compaction (best-effort)
        max_tokens = float(getattr(config, "max_tokens", state.max_tokens) or state.max_tokens)
        used_tokens = float(getattr(state, "used_tokens", 0) or 0)
        if max_tokens > 0 and (used_tokens / max_tokens) > 0.8:
            msgs = state.context.get("messages")
            if isinstance(msgs, list) and len(msgs) > 2:
                state.context["messages"] = msgs[-2:]
                state.metadata["control_action"] = "compact_context"
                state.metadata["compacted_messages"] = True

    async def step(self, state: LoopState) -> LoopState:
        """Execute single step - to be implemented by subclass"""
        state.step_count += 1
        state.history.append({
            "step": state.step_count,
            "node": self._current_node,
            "state": state.current.value
        })
        
        return state

    def get_current_node(self) -> str:
        """Get current execution node"""
        return self._current_node

    async def reset(self) -> None:
        """Reset loop to initial state"""
        self._current_state = LoopState()
        self._current_node = "init"

    async def _trigger_hook(self, phase: HookPhase, data: Dict[str, Any]) -> List[Any]:
        """Trigger hooks for a phase and return hook results."""
        context = HookContext(phase=phase, state=data)
        return await self._hook_manager.trigger(phase, context)


def _extract_deny(results: List[Any]) -> Optional[Dict[str, Any]]:
    """Extract first deny dict from hook results."""
    for r in results or []:
        if isinstance(r, dict) and r.get("allow") is False:
            return r
    return None


class ReActLoop(BaseLoop):
    """
    ReAct (Reasoning + Acting) Execution Loop
    
    Implements the ReAct pattern:
    - Reasoning: LLM decides what action to take
    - Acting: Execute the action (Skill or Tool)
    - Observing: Process the result
    
    Skill vs Tool distinction:
    - Skill: Internal capability, executed within Agent (e.g., text generation, code analysis)
    - Tool: External interface, called outside Agent (e.g., API, database, web search)
    """

    def __init__(
        self,
        config: Optional[LoopConfig] = None,
        hook_manager: Optional[HookManager] = None,
        model: Optional[Any] = None,
        skills: Optional[List[Any]] = None,
        tools: Optional[List[Any]] = None,
        approval_manager: Optional[Any] = None
    ):
        super().__init__(config, hook_manager)
        self._model = model
        self._skills = skills or []
        self._tools = tools or []
        self._approval_manager = approval_manager
        self._current_node = "reason"

    def set_model(self, model: Any) -> None:
        self._model = model

    def set_skills(self, skills: List[Any]) -> None:
        self._skills = skills

    def set_tools(self, tools: List[Any]) -> None:
        self._tools = tools
    
    def set_approval_manager(self, manager: Any) -> None:
        self._approval_manager = manager
    
    def _approval_check(self, tool_name: str, context: Dict[str, Any]) -> None:
        """Check tool approval via ApprovalManager. Raises if denied."""
        # Phase 3+: approval is migrating into sys_tool (PolicyGate). When enabled,
        # avoid double-approval here to keep behavior stable.
        if os.getenv("AIPLAT_SYSCALL_ENFORCE_APPROVAL", "false").lower() in ("1", "true", "yes", "y"):
            return
        if not self._approval_manager:
            return
        try:
            from ...infrastructure.approval import ApprovalContext, RequestStatus
            user_id = context.get("user_id", "system")
            session_id = context.get("session_id", "default")
            approval_ctx = ApprovalContext(
                session_id=session_id,
                user_id=user_id,
                operation=f"tool:{tool_name}",
                operation_context={"tool": tool_name, "context": context}
            )
            request = self._approval_manager.check_and_request(approval_ctx)
            if request.status in (RequestStatus.PENDING, RequestStatus.REJECTED):
                raise RuntimeError(f"Tool '{tool_name}' not approved: {request.result.comments if request.result else 'pending'}")
        except RuntimeError:
            raise
        except Exception:
            pass
    
    def _get_skill(self, name: str) -> Optional[Any]:
        """Get skill by name"""
        for skill in self._skills:
            if hasattr(skill, 'name') and skill.name == name:
                return skill
            if hasattr(skill, '_config') and skill._config.name == name:
                return skill
        return None
    
    def _get_tool(self, name: str) -> Optional[Any]:
        """Get tool by name"""
        for tool in self._tools:
            if hasattr(tool, 'name') and tool.name == name:
                return tool
        return None

    async def step(self, state: LoopState) -> LoopState:
        """Execute single ReAct step: reason -> act -> observe."""
        state.step_count += 1
        state.history.append({
            "step": state.step_count,
            "node": self._current_node,
            "state": state.current.value
        })

        # Resume semantics: if kernel is resuming from a paused state, we may skip reasoning
        # and re-run the previous action after approval is granted.
        if state.metadata.pop("resume_skip_reason", False):
            reasoning = state.context.get("reasoning", "")
        else:
            await self._trigger_hook(HookPhase.PRE_REASONING, state.context)
            state.current = LoopStateEnum.REASONING
            reasoning = await self._reason(state)
            state.context["reasoning"] = reasoning
            await self._trigger_hook(HookPhase.POST_REASONING, state.context)

        # 支持“直接结束”语义：当模型给出 DONE/FINAL 且没有动作调用时，直接结束。
        # 这使得在无工具调用场景也能完成一次 agent 执行（例如 mock LLM / 纯对话）。
        try:
            raw = str(reasoning or "")
            up = raw.strip().upper()
            # Only treat as terminal when DONE/FINAL appears at the beginning.
            # This avoids false positives when the prompt contains JSON examples.
            if up.startswith("DONE:") or up.startswith("FINAL:"):
                final_text = raw.strip()
                for tag in ("DONE:", "FINAL:"):
                    if final_text.upper().startswith(tag):
                        final_text = final_text[len(tag) :].strip()
                        break
                state.context["output"] = final_text
                state.current = LoopStateEnum.FINISHED
                return state
        except Exception:
            pass

        state.current = LoopStateEnum.ACTING
        await self._trigger_hook(HookPhase.PRE_ACT, state.context)
        action_result = await self._act(state)
        state.context["action_result"] = action_result
        await self._trigger_hook(HookPhase.POST_ACT, state.context)

        # If a syscall requested pause (approval_required / policy_denied), stop here.
        if state.metadata.get("pause_requested"):
            state.current = LoopStateEnum.PAUSED
            return state

        state.current = LoopStateEnum.OBSERVING
        await self._trigger_hook(HookPhase.PRE_OBSERVE, state.context)
        observation = await self._observe(state)
        state.context["observation"] = observation
        await self._trigger_hook(HookPhase.POST_OBSERVE, state.context)

        if "DONE" in observation.upper() or "FINISHED" in observation.upper():
            state.current = LoopStateEnum.FINISHED

        return state

    async def _reason(self, state: LoopState) -> str:
        """Reasoning phase"""
        if not self._model:
            return "No model available"

        task = state.context.get("task", "")
        history = "\n".join([
            f"{msg.get('role', 'user')}: {msg.get('content', '')}"
            for msg in state.context.get("messages", [])[-5:]
        ])
        tools_desc, tools_desc_stats = self._build_tools_desc()
        # Best-effort: attach to state for observability/debugging
        try:
            state.metadata["tools_desc_stats"] = tools_desc_stats
            state.context["tools_desc_stats"] = tools_desc_stats
        except Exception:
            pass

        if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y"):
            prompt = PromptAssembler().build_react_reasoning_messages(
                task=task,
                history=history,
                tools_desc=tools_desc,
                observation=state.context.get("observation", "None"),
            )
        else:
            prompt = f"""Task: {task}

History:
{history}

Available tools:
{tools_desc}

Observation: {state.context.get('observation', 'None')}

Think about what to do next. If using a tool/skill, respond with:
1) 优先（结构化）：
```json
{{"tool":"tool_name","args":{{...}}}}
```

Skill（必须显式标注，避免误触发）：
```json
{{"skill":"skill_name","args":{{...}}}}
```

2) 兼容旧格式（tool）：
ACTION: tool_name: argument

兼容旧格式（skill）：
SKILL: skill_name: argument

If finished, respond with:
DONE: final_answer
"""
        try:
            trace_ctx = {
                "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
                "run_id": state.context.get("_run_id") or state.context.get("run_id"),
            }
            response = await sys_llm_generate(self._model, prompt, trace_context=trace_ctx)
            return response.content
        except Exception as e:
            return f"Model error: {e}"

    def _build_tools_desc(self) -> tuple[str, Dict[str, Any]]:
        """
        Build a compact tools description string with budgets.

        Why:
        - MCP / tool ecosystems can grow large; dumping full descriptions every turn is expensive.
        - Claude Code uses dynamic MCP discovery; as a first step we apply budgets + observability.
        """
        import os

        per_tool_max = int(os.getenv("AIPLAT_TOOL_DESC_PER_TOOL_MAX_CHARS", "400") or "400")
        total_max = int(os.getenv("AIPLAT_TOOLS_DESC_MAX_CHARS", "4000") or "4000")

        stats: Dict[str, Any] = {
            "per_tool_max_chars": per_tool_max,
            "total_max_chars": total_max,
            "tools_total": len(self._tools or []),
            "tools_included": 0,
            "tools_hidden": 0,
            "tools_truncated": 0,
            "chars_total": 0,
        }

        if not self._tools:
            return "No tools available", stats

        # Ensure tool_search is always visible to the model when tools are truncated.
        always_include = {"tool_search"}
        ordered = list(self._tools)
        try:
            ordered.sort(key=lambda x: (0 if getattr(x, "name", "") in always_include else 1, str(getattr(x, "name", ""))))
        except Exception:
            ordered = list(self._tools)

        lines: List[str] = []
        for t in ordered:
            try:
                name = getattr(t, "name", None) or (t.get_name() if hasattr(t, "get_name") else str(t))
            except Exception:
                name = str(t)
            try:
                desc = getattr(t, "description", None) or (t.get_description() if hasattr(t, "get_description") else "")
            except Exception:
                desc = ""

            desc = str(desc or "")
            if per_tool_max > 0 and len(desc) > per_tool_max:
                desc = desc[: max(0, per_tool_max - 16)] + " …(truncated)"
                stats["tools_truncated"] += 1

            line = f"- {name}: {desc}".strip()
            projected = stats["chars_total"] + len(line) + (1 if lines else 0)
            if total_max > 0 and projected > total_max:
                stats["tools_hidden"] = stats["tools_total"] - stats["tools_included"]
                break

            lines.append(line)
            stats["tools_included"] += 1
            stats["chars_total"] = projected

        if stats["tools_hidden"]:
            lines.append(f"... ({stats['tools_hidden']} tools hidden; use tool search/narrow toolset)")

        return "\n".join(lines), stats

    async def _act(self, state: LoopState) -> str:
        """Acting phase - execute tool or skill."""
        reasoning = state.context.get("reasoning", "")
        parsed = parse_action_call(reasoning)
        if not parsed:
            return "No action to execute"

        if parsed.kind == "skill":
            skill_name = parsed.name
            skill_args = parsed.args
            state.context["skill_call"] = {"skill": skill_name, "args": skill_args, "format": parsed.format}
            for skill in self._skills:
                name = ""
                if hasattr(skill, "name"):
                    name = str(getattr(skill, "name", "") or "")
                elif hasattr(skill, "_config") and getattr(skill, "_config", None) is not None:
                    name = str(getattr(skill._config, "name", "") or "")
                if name.strip().lower() == skill_name.strip().lower():
                    from ..interfaces import SkillContext
                    await self._trigger_hook(HookPhase.PRE_SKILL_USE, {"skill": skill_name, "skill_args": skill_args, "format": parsed.format})
                    try:
                        skill_context = SkillContext(
                            session_id=state.context.get("session_id", "default"),
                            user_id=state.context.get("user_id", "system"),
                            variables=skill_args,
                        )
                        result = await sys_skill_call(
                            skill,
                            skill_args,
                            context=skill_context,
                            user_id=skill_context.user_id,
                            session_id=skill_context.session_id,
                            trace_context={
                                "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
                                "run_id": state.context.get("_run_id") or state.context.get("run_id"),
                            },
                        )
                        result_output = result.output if hasattr(result, 'output') else str(result)
                    except Exception as e:
                        result_output = f"Skill error: {e}"
                    await self._trigger_hook(HookPhase.POST_SKILL_USE, {"skill": skill_name, "result": result_output, "format": parsed.format})
                    return str(result_output)
            return f"Skill not found: {skill_name}"

        tool_name = parsed.name
        tool_args = parsed.args
        state.context["tool_call"] = {"tool": tool_name, "args": tool_args, "format": parsed.format}

        for tool in self._tools:
            if str(getattr(tool, 'name', '')).strip().lower() == str(tool_name).strip().lower():
                # Approval hooks (may block)
                approval_results = await self._trigger_hook(
                    HookPhase.PRE_APPROVAL_CHECK,
                    {"tool_name": tool_name, "tool_args": tool_args, "context": state.context},
                )
                deny = _extract_deny(approval_results)
                if deny:
                    await self._trigger_hook(HookPhase.POST_APPROVAL_CHECK, {"tool_name": tool_name, "allowed": False, "reason": deny.get("reason")})
                    return f"Denied: {deny.get('reason', 'approval denied')}"

                self._approval_check(tool_name, state.context)
                await self._trigger_hook(HookPhase.PRE_TOOL_USE, {"tool_name": tool_name, "tool_args": tool_args, "format": parsed.format})
                try:
                    # If we are resuming an approval-required tool call, attach the approval_request_id
                    # so PolicyGate can validate and allow execution.
                    approval_meta = state.context.get("approval") if isinstance(state.context.get("approval"), dict) else {}
                    approval_req_id = approval_meta.get("approval_request_id")
                    if approval_req_id:
                        try:
                            tool_args = dict(tool_args or {})
                            tool_args["_approval_request_id"] = approval_req_id
                        except Exception:
                            pass
                    result = await sys_tool_call(
                        tool,
                        tool_args,
                        user_id=state.context.get("user_id", "system"),
                        session_id=state.context.get("session_id", "default"),
                        trace_context={
                            "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
                            "run_id": state.context.get("_run_id") or state.context.get("run_id"),
                            "tenant_id": state.context.get("tenant_id"),
                        },
                    )
                    # Standardized syscall result handling
                    if getattr(result, "error", None) == "approval_required":
                        state.context["error"] = "approval_required"
                        state.context["approval"] = getattr(result, "metadata", {}) or {}
                        state.metadata["pause_requested"] = True
                        result_output = "Approval required"
                        ok = False
                    elif getattr(result, "error", None) == "policy_denied":
                        state.context["error"] = "policy_denied"
                        state.context["policy"] = getattr(result, "metadata", {}) or {}
                        state.metadata["pause_requested"] = True
                        result_output = "Policy denied"
                        ok = False
                    else:
                        result_output = result.output if hasattr(result, 'output') else str(result)
                        ok = bool(getattr(result, "success", True))
                except Exception as e:
                    result_output = f"Tool error: {e}"
                    ok = False
                # Record tool stats for observability-driven control
                state.metadata["tool_calls"] = int(state.metadata.get("tool_calls", 0) or 0) + 1
                if not ok:
                    state.metadata["tool_failures"] = int(state.metadata.get("tool_failures", 0) or 0) + 1
                await self._trigger_hook(HookPhase.POST_TOOL_USE, {"tool_name": tool_name, "result": result_output, "format": parsed.format})
                await self._trigger_hook(HookPhase.POST_APPROVAL_CHECK, {"tool_name": tool_name, "allowed": True})
                return str(result_output)

        return f"Tool not found: {tool_name}"

    async def _observe(self, state: LoopState) -> str:
        """Observing phase"""
        return state.context.get("action_result", "")


class PlanExecuteLoop(BaseLoop):
    """
    Plan-Execute Loop
    
    Implements two-phase execution:
    - Plan: Analyze task and create execution plan
    - Execute: Execute plan steps using available tools/skills
    """

    def __init__(
        self,
        config: Optional[LoopConfig] = None,
        hook_manager: Optional[HookManager] = None,
        model: Optional[Any] = None,
        skills: Optional[List[Any]] = None,
        tools: Optional[List[Any]] = None
    ):
        super().__init__(config, hook_manager)
        self._model = model
        self._skills = skills or []
        self._tools = tools or []
        self._plan: List[Dict[str, Any]] = []
        self._current_node = "plan"

    def set_model(self, model: Any) -> None:
        self._model = model

    def set_skills(self, skills: List[Any]) -> None:
        self._skills = skills

    def set_tools(self, tools: List[Any]) -> None:
        self._tools = tools

    async def step(self, state: LoopState) -> LoopState:
        """Execute Plan-Execute step"""
        state.step_count += 1
        
        if self._current_node == "plan":
            state = await self._plan(state)
        elif self._current_node == "execute":
            state = await self._execute(state)
        
        state.history.append({
            "step": state.step_count,
            "node": self._current_node,
            "state": state.current.value
        })
        
        return state

    async def _plan(self, state: LoopState) -> LoopState:
        """Planning phase - create execution plan"""
        state.current = LoopStateEnum.REASONING
        
        if self._model:
            if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y"):
                prompt = PromptAssembler().build_plan_execute_plan_messages(task=state.context.get("task", ""))
            else:
                prompt = (
                    "请为任务生成可执行的步骤计划。\n"
                    "要求：\n"
                    "1) 普通步骤用自然语言描述即可。\n"
                    "2) 若某一步需要调用工具，请用结构化 JSON 表达（单行）：\n"
                    "   {\"tool\":\"tool_name\",\"args\":{...}}\n"
                    "3) 若某一步需要调用 skill，也必须显式标注（单行）：\n"
                    "   {\"skill\":\"skill_name\",\"args\":{...}}\n"
                    f"\nTask: {state.context.get('task', '')}\n"
                )
            response = await sys_llm_generate(
                self._model,
                prompt,
                trace_context={
                    "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
                    "run_id": state.context.get("_run_id") or state.context.get("run_id"),
                },
            )
            
            # Parse plan (simplified)
            self._plan = [
                {"step": i + 1, "action": line.strip().lstrip("0123456789. ").strip()}
                for i, line in enumerate(response.content.split("\n"))
                if line.strip() and not line.strip().startswith("#")
            ]
        
        state.context["plan"] = self._plan
        self._current_node = "execute"
        state.current = LoopStateEnum.ACTING
        
        return state

    async def _execute(self, state: LoopState) -> LoopState:
        """Execution phase - execute plan steps with tool/skill support"""
        state.current = LoopStateEnum.ACTING
        
        current_step = state.context.get("current_step", 0)
        
        if current_step < len(self._plan):
            step = self._plan[current_step]
            action = step.get("action", "")
            state.context["current_step"] = current_step + 1
            
            # Pre-acting hook
            await self._trigger_hook(HookPhase.PRE_ACT, {"state": state, "step": step})
            
            step_result = None
            
            # Execute only when explicitly routed (avoid substring accidental dispatch)
            parsed_action = parse_action_call(action)
            if parsed_action and parsed_action.kind == "tool" and self._tools:
                for tool in self._tools:
                    tool_name = getattr(tool, "name", "")
                    if str(tool_name).strip().lower() == str(parsed_action.name).strip().lower():
                        try:
                            await self._trigger_hook(HookPhase.PRE_TOOL_USE, {"tool": tool_name, "tool_args": parsed_action.args, "format": parsed_action.format})
                            result = await sys_tool_call(
                                tool,
                                parsed_action.args,
                                user_id=state.context.get("user_id", "system"),
                                session_id=state.context.get("session_id", "default"),
                                trace_context={
                                    "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
                                    "run_id": state.context.get("_run_id") or state.context.get("run_id"),
                                },
                            )
                            step_result = result.output if hasattr(result, "output") else str(result)
                            await self._trigger_hook(HookPhase.POST_TOOL_USE, {"tool": tool_name, "result": step_result, "format": parsed_action.format})
                            break
                        except Exception as e:
                            step_result = f"Tool error ({tool_name}): {e}"

            if step_result is None and parsed_action and parsed_action.kind == "skill" and self._skills:
                for skill in self._skills:
                    skill_name = getattr(skill, "_config", None)
                    skill_name = skill_name.name if skill_name else getattr(skill, "name", "")
                    if str(skill_name).strip().lower() == str(parsed_action.name).strip().lower():
                        try:
                            from ...harness.interfaces import SkillContext
                            skill_context = SkillContext(
                                session_id=state.context.get("session_id", "loop"),
                                user_id=state.context.get("user_id", "system"),
                                variables=parsed_action.args,
                                tools=[t.name for t in self._tools if hasattr(t, "name")],
                            )
                            await self._trigger_hook(HookPhase.PRE_SKILL_USE, {"skill": skill_name, "skill_args": parsed_action.args, "format": parsed_action.format})
                            result = await sys_skill_call(
                                skill,
                                parsed_action.args,
                                context=skill_context,
                                user_id=skill_context.user_id,
                                session_id=skill_context.session_id,
                                trace_context={
                                    "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
                                    "run_id": state.context.get("_run_id") or state.context.get("run_id"),
                                },
                            )
                            step_result = result.output if hasattr(result, "output") else str(result)
                            await self._trigger_hook(HookPhase.POST_SKILL_USE, {"skill": skill_name, "result": step_result, "format": parsed_action.format})
                            break
                        except Exception as e:
                            step_result = f"Skill error ({skill_name}): {e}"
            
            # Fall back to model for this step
            if step_result is None and self._model:
                try:
                    if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y"):
                        prompt = PromptAssembler().build_plan_execute_step_messages(
                            action=action,
                            task=state.context.get("task", ""),
                        )
                    else:
                        prompt = f"Execute this step: {action}\nContext: {state.context.get('task', '')}"
                    response = await sys_llm_generate(
                        self._model,
                        prompt,
                        trace_context={
                            "trace_id": state.context.get("_trace_id") or state.context.get("trace_id"),
                            "run_id": state.context.get("_run_id") or state.context.get("run_id"),
                        },
                    )
                    step_result = response.content
                except Exception as e:
                    step_result = f"Model error: {e}"
            
            if step_result is None:
                step_result = f"No handler for step: {action}"
            
            state.context[f"step_{current_step}_result"] = step_result
            state.context["action_result"] = step_result
            
            # Post-acting hook
            await self._trigger_hook(HookPhase.POST_ACT, {"state": state, "result": step_result})
            
            if current_step + 1 >= len(self._plan):
                state.context["output"] = state.context.get("step_0_result", step_result)
                state.current = LoopStateEnum.FINISHED
                self._current_node = "finish"
        else:
            state.current = LoopStateEnum.FINISHED
            self._current_node = "finish"
        
        return state


def create_loop(
    loop_type: str = "react",
    config: Optional[LoopConfig] = None,
    **kwargs
) -> ILoop:
    """
    Factory function to create execution loop
    
    Args:
        loop_type: Type of loop ("react", "plan_execute")
        config: Loop configuration
        **kwargs: Additional arguments
        
    Returns:
        ILoop: Execution loop instance
    """
    if loop_type == "react":
        return ReActLoop(config=config, **kwargs)
    elif loop_type == "plan_execute":
        return PlanExecuteLoop(config=config, **kwargs)
    else:
        return BaseLoop(config=config)
