"""Audit field whitelist helpers for decision-shadow payloads.

Default: no raw query text. Full text only when store_raw_text=true (opt-in).
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Mapping, Optional, Set

# Fields allowed into durable audit sinks (subset of plan §5.4).
AUDIT_FIELD_WHITELIST: Set[str] = {
    "trace_id",
    "tier",
    "domain_id_online",
    "candidates",
    "query_hash",
    "query_len",
    "query_redacted",
    "shadow_choice",
    "probs",
    "shadow_latency_ms",
    "model",
    "runtime_version",
    "drop_reason",
    "trigger",
}


def query_hash(text: str) -> str:
    """query_hash。

    Args:
        text: text 参数。
    """
    return hashlib.sha256((text or "").encode("utf-8", errors="replace")).hexdigest()[
        :32
    ]


def redact_payload(
    payload: Mapping[str, Any],
    *,
    store_raw_text: bool = False,
) -> Dict[str, Any]:
    """Return a dict limited to the audit whitelist (+ optional raw).

    Args:
        payload: 载荷 dict。
        store_raw_text: store_raw_text 参数。
    """
    out: Dict[str, Any] = {}
    for k in AUDIT_FIELD_WHITELIST:
        if k in payload:
            out[k] = payload[k]
    raw = payload.get("query_raw")
    if store_raw_text and raw is not None:
        out["query_raw"] = raw
    # Always derive hash/len if query present but hash missing
    if "query_hash" not in out and isinstance(raw, str):
        out["query_hash"] = query_hash(raw)
        out["query_len"] = len(raw)
    if not store_raw_text:
        leak = _assert_no_raw_by_default(out)
        if leak:
            out.pop("query_raw", None)
    return out


def _assert_no_raw_by_default(record: Mapping[str, Any]) -> Optional[str]:
    """Return error string if raw text leaked while store_raw_text path unused."""
    if "query_raw" in record:
        return "query_raw present without explicit store_raw_text sink policy"
    return None
