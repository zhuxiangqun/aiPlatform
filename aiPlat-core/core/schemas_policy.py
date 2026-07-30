"""
Permission & evaluation policy schemas (2026-07-29 — wired).

Permission config migrated to: auth.schemas_policy (platform layer).
Evaluation policy types defined in: core.schemas_eval_policy.

This module re-exports both for backward compatibility.
"""
from core.schemas_eval_policy import EvalPolicy, EvalTrigger, EvalMetric

# Backward-compat re-export of auth permissions
try:
    from auth.schemas_policy import *  # noqa: F403
except ImportError:
    pass  # noqa: optional-dependency — auth module may not be installed
