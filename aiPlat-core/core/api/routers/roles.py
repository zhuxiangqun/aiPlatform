"""Role Management API — configure and monitor the four-agent role system.

Roles:
  员工 (Employee)  — ReActLoop + lightweight model + fast execution
  保安 (Guard)     — ImmuneMemory + CircuitBreaker + ApprovalGate
  顾问 (Advisor)   — SkillOpt dual-channel + DynamicRouter reflection
  协调员 (Orchestrator) — BusinessGoalTracker + GoalAwareRouter

Endpoints:
  GET  /roles/agents               — list all agents with role assignments
  PUT  /roles/agents/{agent_id}    — update agent role + config
  GET  /roles/metrics              — realtime role performance metrics
  POST /roles/strategy/override    — manual strategy override per agent
"""
from fastapi import APIRouter, HTTPException
from typing import Any, Dict, List, Optional

router = APIRouter(prefix="/roles", tags=["roles"])

# Default role configs (per-agent overrides stored in memory)
_role_configs: Dict[str, Dict[str, Any]] = {}


ROLE_DEFAULTS = {
    "employee": {
        "model": "qwen2.5-coder:7b",
        "max_steps": 15,
        "temperature": 0.2,
        "reflection_enabled": False,
        "approval_bypass_known": True,
    },
    "guard": {
        "immune_level1": 0.95,
        "immune_level2": 0.88,
        "circuit_cooldown_s": 60,
        "alert_cooldown_s": 300,
        "force_hitl_external": True,
    },
    "advisor": {
        "model": "gpt-4o",
        "reflection_enabled": True,
        "max_edits_per_draft": 4,
        "skill_simulation_enabled": True,
        "dual_channel_enabled": True,
    },
}


from core.schemas_common import ListResponse
from core.schemas_roles import RoleAgentItem, RoleAgentUpdateResponse, RoleMetricsResponse, RoleStrategyOverrideResponse, RoleAgentUpdateRequest, RoleStrategyOverrideRequest

@router.get("/agents", response_model=ListResponse[RoleAgentItem])
async def get_role_agents() -> List[Dict[str, Any]]:
    """List all agents with current role assignments and config."""
    import os
    agents = []

    # Each agent can be configured with a role
    for agent_id, config in _role_configs.items():
        agents.append({
            "agent_id": agent_id,
            "role": config.get("role", "employee"),
            "model": config.get("model", ""),
            "reflection_enabled": config.get("reflection_enabled", False),
            "last_updated": config.get("last_updated", ""),
        })

    # Scan workspace agents directory
    workspace_dir = os.path.expanduser("~/.aiplat/agents")
    if os.path.isdir(workspace_dir):
        for name in os.listdir(workspace_dir):
            if name not in _role_configs and os.path.isdir(os.path.join(workspace_dir, name)):
                agents.append({
                    "agent_id": name, "role": "employee", "model": "",
                    "reflection_enabled": name == "advisor_agent",
                    "last_updated": "",
                })

    # System services (not AGENT.md-driven, display-only — no role assignment)
    agents.append({"agent_id": "kpi_agent", "role": "system_service",
                    "model": "core.harness.agents.kpi_agent.KPIAgent",
                    "reflection_enabled": False, "last_updated": "",
                    "agent_type": "system_service", "description": "KPI监控：自动追踪目标、偏离预警"})
    agents.append({"agent_id": "strategy_agent", "role": "system_service",
                    "model": "core.harness.agents.strategy_agent.StrategyAgent",
                    "reflection_enabled": False, "last_updated": "",
                    "agent_type": "system_service", "description": "策略调优：日常参数微调、异常响应"})

    return {"items": agents}


@router.put("/agents/{agent_id}", response_model=RoleAgentUpdateResponse)
async def update_agent_role(agent_id: str, body: RoleAgentUpdateRequest) -> Dict[str, Any]:
    """Configure an agent's role and parameters."""
    role = body.role
    if role not in ("employee", "guard", "advisor"):
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}")

    import time
    config = dict(ROLE_DEFAULTS.get(role, {}))
    config.update(body.config)
    config["role"] = role
    config["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    _role_configs[agent_id] = config
    return {"agent_id": agent_id, **config}


@router.get("/metrics", response_model=RoleMetricsResponse)
async def get_role_metrics() -> Dict[str, Any]:
    """Realtime role-specific performance metrics."""
    from core.harness.finance.value_calculator import get_value_calculator
    calc = get_value_calculator()

    metrics = {
        "employee": _get_employee_metrics(),
        "guard": _get_guard_metrics(),
        "advisor": _get_advisor_metrics(),
        "orchestrator": _get_orchestrator_metrics(),
    }
    return metrics


@router.post("/strategy/override", response_model=RoleStrategyOverrideResponse)
async def override_strategy(body: RoleStrategyOverrideRequest) -> Dict[str, Any]:
    """Manually override routing strategy for specific agents."""
    agent_id = body.agent_id
    mode = body.mode  # normal / speed / quality / guard / pause

    if agent_id not in _role_configs:
        _role_configs[agent_id] = {}

    overrides = {
        "speed": {"role": "employee", "max_steps": 8, "reflection_enabled": False},
        "quality": {"role": "advisor", "reflection_enabled": True, "max_edits_per_draft": 4},
        "guard": {"role": "guard", "force_hitl_external": True},
        "pause": {"role": "paused"},
    }

    config = overrides.get(mode, overrides["speed"])
    _role_configs[agent_id].update(config)
    _role_configs[agent_id]["mode_override"] = mode
    import time
    _role_configs[agent_id]["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    return {"agent_id": agent_id, "mode": mode, "config": _role_configs[agent_id]}


# ── Metrics helpers ──

def _get_employee_metrics() -> Dict[str, Any]:
    """Fast executors: success rate, token cost, avg latency."""
    return {"status": "active"}


def _get_guard_metrics() -> Dict[str, Any]:
    """Defense layer: attacks blocked, circuits, alerts."""
    try:
        from core.harness.security.immune_memory import ImmuneMemory
        from core.harness.learning.tool_drift_detector import get_drift_detector
        im = ImmuneMemory.get_stats()
        dd = get_drift_detector()
        rt = dd.get_realtime_stats()
        return {
            "attacks_memorized": im["total_records"],
            "attack_types": im["total_types"],
            "circuit_breakers_open": len(rt.get("circuit_breakers_open", {})),
            "unstable_tools": len(rt.get("unstable_tools", [])),
            "tools_monitored": rt.get("tools_monitored", 0),
        }
    except Exception:
        return {"status": "unavailable"}


def _get_advisor_metrics() -> Dict[str, Any]:
    """Quality improvers: drafts generated, pass rates, skills."""
    try:
        from core.harness.learning import get_auto_learner
        learner = get_auto_learner()
        return {
            "drafts_in_storage": len(learner._storage),
            "rejected_buffer": len(learner._rejected_buffer),
            "max_edits": learner._max_edits,
        }
    except Exception:
        return {"status": "unavailable"}


def _get_orchestrator_metrics() -> Dict[str, Any]:
    """Strategy layer: goals, routing adjustments."""
    try:
        from core.harness.finance.value_calculator import get_value_calculator
        calc = get_value_calculator()
        goals = calc.goal_tracker.get_all()
        lagging = sum(1 for g in goals if g.progress_pct < 0.8)
        return {
            "total_goals": len(goals),
            "lagging_goals": lagging,
            "goal_ids": [g.goal_id for g in goals],
        }
    except Exception:
        return {"status": "unavailable"}
