"""
sys_agent_call — Core syscall for dynamic sub-agent delegation.

Allows an agent in the ReAct loop to spawn a sub-agent (from its bound
agent_ids list), delegate a task, and receive a summarized result.

This is the syscall-level entry point for Agent→Agent orchestration.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional


async def sys_agent_call(
    subagent_name: str,
    task: str,
    *,
    context: Optional[List[Dict[str, str]]] = None,
    trace_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Spawn a sub-agent to execute a delegated task.

    Returns:
        {
            "success": bool,
            "output": str,          # summarized result (max 800 chars per §5.26)
            "error": str | None,
            "duration_ms": int,
            "subagent_name": str,
        }
    """
    try:
        from core.harness.integration import get_subagent_coordinator

        # ── Validate subagent against workspace gate (④ unified gate) ──
        try:
            from core.harness.tools.toolsets import check_workspace_gate
            allowed, reason, _ = check_workspace_gate("agent", str(subagent_name).strip())
            if not allowed:
                return {
                    "success": False,
                    "output": "",
                    "error": f"subagent_denied: {reason}",
                    "duration_ms": 0,
                    "subagent_name": subagent_name,
                }
        except Exception:
            import logging as _logging
            _logging.getLogger("aiplat.syscall.agent").debug("Workspace gate check skipped", exc_info=True)

        # ── PolicyGate enforcement (single entry point, §3.2) ──
        try:
            from core.harness.infrastructure.gates.policy_gate import PolicyGate, PolicyDecision
            pg = PolicyGate()
            pr = await pg.check_agent(
                user_id="",
                agent_id=str(subagent_name).strip(),
                agent_args={"task": task},
            )
            if pr.decision == PolicyDecision.DENY:
                from core.harness.infrastructure.feedback_translator import translate_denial, format_for_agent
                fb = translate_denial(pr.reason or "", str(subagent_name).strip())
                return {
                    "success": False, "output": format_for_agent(fb),
                    "error": f"policy_gate:deny — {pr.reason}",
                    "duration_ms": 0, "subagent_name": subagent_name,
                }
            if pr.decision == PolicyDecision.APPROVAL_REQUIRED:
                from core.harness.infrastructure.feedback_translator import translate_approval_required, format_for_agent
                fb = translate_approval_required(pr.reason or "", str(subagent_name).strip())
                return {
                    "success": False, "output": format_for_agent(fb),
                    "error": f"policy_gate:approval_required — {pr.reason}",
                    "duration_ms": 0, "subagent_name": subagent_name,
                }
        except Exception:
            pass

        # P2-24: DelegateManager — resource-budgeted delegation with retries
        try:
            from core.harness.infrastructure.delegate_tool import get_delegate_manager, DelegateConfig
            mgr = get_delegate_manager()
            config = DelegateConfig(
                subagent_name=subagent_name,
                task=task,
            )
            result = await mgr.delegate(config)
            return {
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "duration_ms": result.duration_ms,
                "subagent_name": result.subagent_name,
                "token_used": result.token_used,
            }
        except Exception:
            pass

        coordinator = get_subagent_coordinator()
        # Parallel dispatch: comma-separated subagent names
        if "," in str(subagent_name):
            names = [n.strip() for n in str(subagent_name).split(",") if n.strip()]
            if len(names) >= 2:
                result = await coordinator.execute_parallel(
                    subagent_names=names,
                    task=task,
                    context=context or [],
                )
                return {
                    "success": result.success,
                    "output": result.output or "",
                    "error": result.error,
                    "duration_ms": result.duration_ms,
                    "subagent_name": ", ".join(result.subagent_names or names),
                }
        result = await coordinator.execute_single(
            subagent_name=subagent_name,
            task=task,
            context=context or [],
        )
        return {
            "success": result.success,
            "output": result.output or "",
            "error": result.error,
            "duration_ms": result.duration_ms,
            "subagent_name": result.subagent_name,
        }
    except ImportError:
        return {
            "success": False,
            "output": "",
            "error": "SubagentCoordinator not available",
            "duration_ms": 0,
            "subagent_name": subagent_name,
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "duration_ms": 0,
            "subagent_name": subagent_name,
        }
