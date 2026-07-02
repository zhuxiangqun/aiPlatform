"""
ExecutionStore — database persistence layer (Mixin-based SRP split).

Original 9683-line monolith split into focused mixins by entity type:
  - _base.py         — core: __init__, _connect, init, prune, get_schema_version
  - graph_mixin.py   — graph lifecycle: start/finish/checkpoint/list/resume
  - trace_mixin.py   — trace + execution links
  - gateway_mixin.py — enterprise gateway pairings/tokens
  - runs_mixin.py    — run events/cancel/locks
  - syscall_mixin.py — syscall events + change control
  - audit_mixin.py   — audit logs + tenant policies
  - quota_mixin.py   — tenant quotas/usage + connector DLQ
  - approval_mixin.py— approval requests
  - agent_mixin.py   — agent CRUD
  - skill_mixin.py   — skill CRUD
  - job_mixin.py     — job delivery attempts/DLQ
  - memory_mixin.py  — enterprise memory pins/blocks
  - deploy_mixin.py  — release rollouts/plugins/onboarding/prompts/evals

Public API (backward-compatible):
  from core.services import get_execution_store
"""
import os
from typing import Optional

from ._base import _ExecutionStoreBase, ExecutionStoreConfig
from .graph_mixin import GraphMixin
from .trace_mixin import TraceMixin
from .gateway_mixin import GatewayMixin
from .runs_mixin import RunsMixin
from .metrics_mixin import MetricsMixin
from .syscall_mixin import SyscallMixin
from .audit_mixin import AuditMixin
from .quota_mixin import QuotaMixin
from .approval_mixin import ApprovalMixin
from .agent_mixin import AgentMixin
from .skill_mixin import SkillMixin
from .job_ops_mixin import JobOpsMixin
from .job_mixin import JobMixin
from .memory_mixin import MemoryMixin
from .skill_pack_mixin import SkillPackMixin
from .package_mixin import PackageMixin
from .adapter_mixin import AdapterMixin
from .settings_mixin import SettingsMixin
from .tenant_mixin import TenantMixin
from .ltm_mixin import LongTermMemoryMixin
from .costs_mixin import CostsMixin
from .session_mixin import SessionMixin
from .release_mixin import ReleaseMixin
from .plugin_mixin import PluginMixin
from .onboard_mixin import OnboardMixin
from .prompt_mixin import PromptMixin
from .eval_mixin import EvalMixin


class ExecutionStore(
    _ExecutionStoreBase,
    GraphMixin, TraceMixin, GatewayMixin, RunsMixin,
    SyscallMixin, AuditMixin, QuotaMixin, ApprovalMixin, MetricsMixin, JobOpsMixin,
    AgentMixin, SkillMixin, JobMixin,
    MemoryMixin, ReleaseMixin, PluginMixin, OnboardMixin,
    PromptMixin, EvalMixin, SkillPackMixin, PackageMixin, AdapterMixin, SettingsMixin, TenantMixin, LongTermMemoryMixin, CostsMixin, SessionMixin,
):
    """Composed ExecutionStore — inherits from base + 19 mixins."""
    pass


# ── Process-wide singleton factory ──

_execution_store: Optional[ExecutionStore] = None


def get_execution_store(db_path: Optional[str] = None) -> ExecutionStore:
    """Process-wide singleton."""
    global _execution_store
    desired_path = db_path or os.environ.get(
        "AIPLAT_EXECUTION_DB_PATH",
        os.path.join(os.path.expanduser("~"), ".aiplat", "aiplat_executions.sqlite3")
    )
    if _execution_store is not None:
        try:
            if str(getattr(getattr(_execution_store, "_config", None), "db_path", "")) != str(desired_path):
                _execution_store = None
        except Exception:
            _execution_store = None

    if _execution_store is None:
        def _int_env(name: str) -> Optional[int]:
            v = os.environ.get(name)
            if v is None or str(v).strip() == "":
                return None
            try:
                return int(str(v).strip())
            except Exception:
                return None

        retention_days = _int_env("AIPLAT_EXECUTION_DB_RETENTION_DAYS")
        max_rows = _int_env("AIPLAT_EXECUTION_DB_MAX_ROWS_PER_ENTITY")
        prune_on_start = os.environ.get("AIPLAT_EXECUTION_DB_PRUNE_ON_START", "true").lower() not in ("0", "false", "no")
        vacuum_on_prune = os.environ.get("AIPLAT_EXECUTION_DB_VACUUM_ON_PRUNE", "false").lower() in ("1", "true", "yes")

        _execution_store = ExecutionStore(
            ExecutionStoreConfig(
                db_path=desired_path,
                retention_days=retention_days,
                max_rows_per_entity=max_rows,
                prune_on_start=prune_on_start,
                vacuum_on_prune=vacuum_on_prune,
            )
        )
    return _execution_store


__all__ = ["ExecutionStore", "ExecutionStoreConfig", "get_execution_store"]
