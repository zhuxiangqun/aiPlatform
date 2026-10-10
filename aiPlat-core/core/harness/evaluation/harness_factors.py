"""Harness experiment factors for gold regression (ReviewBench / LangChain lesson).

Record config knobs that change review quality *without* changing the model,
so same-profile gates can detect silent harness drift.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


def collect_harness_factors(*, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Snapshot of harness knobs relevant to code-review / agent quality."""
    factors = {
        "coding_policy_profile": (
            os.environ.get("AIPLAT_CODING_POLICY_PROFILE_WORKSPACE")
            or os.environ.get("AIPLAT_CODING_POLICY_PROFILE_ENGINE")
            or "karpathy_v1"
        ),
        "done_verify": (os.environ.get("AIPLAT_DONE_VERIFY") or "true").strip().lower(),
        "done_verify_min_len": (os.environ.get("AIPLAT_DONE_VERIFY_MIN_LEN") or "20").strip(),
        "meta_tool_code": (os.environ.get("AIPLAT_META_TOOL_CODE") or "true").strip().lower(),
        "meta_tool_auto_bind": (os.environ.get("AIPLAT_META_TOOL_AUTO_BIND") or "auto").strip().lower(),
        "subagent_force_isolate": (os.environ.get("AIPLAT_SUBAGENT_FORCE_ISOLATE") or "auto").strip().lower(),
        "os_sandbox": (os.environ.get("AIPLAT_SANDBOX") or "").strip().lower() or "(unset)",
        "profile_env": (os.environ.get("AIPLAT_PROFILE") or "").strip().lower() or "(unset)",
        "gold_profile_gate": (os.environ.get("AIPLAT_GOLD_PROFILE_GATE") or "auto").strip().lower(),
    }
    if isinstance(extra, dict):
        for k, v in extra.items():
            if v is not None:
                factors[str(k)] = v
    return factors


def harness_factors_delta(
    current: Optional[Dict[str, Any]],
    previous: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Keys that changed between two gold runs (excluding written_at noise)."""
    cur = current if isinstance(current, dict) else {}
    prev = previous if isinstance(previous, dict) else {}
    changed = {}
    keys = set(cur) | set(prev)
    for k in sorted(keys):
        if cur.get(k) != prev.get(k):
            changed[k] = {"from": prev.get(k), "to": cur.get(k)}
    return changed
