"""评测 Extended E09 — Tool/MCP subject + 外援 verified_tier 绑定。

附录 B：``tool`` / ``mcp`` 为 v1 Extended subject；引用外援资产时 MUST
带 ``verified_tier``（互通附录 H）。未校准 accuracy / claim 仍关闭。
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from core.harness.maintenance.asset_compat import normalize_compat_level

_TOOL_MCP_KINDS = frozenset({"tool", "mcp"})
_VALID_TIERS = frozenset({"L0", "L1", "L2", "unknown"})


def normalize_tool_mcp_subject(
    raw: Optional[Mapping[str, Any]] = None,
    *,
    require_verified_tier: bool = False,
) -> Dict[str, Any]:
    """归一化 Tool/MCP 评测 subject（E09）。

    Args:
        raw: 原始 subject / contract 片段。
        require_verified_tier: 为 True 或 raw 含 ``interop_ref`` 时强制 verified_tier。

    Returns:
        含 ``subject_kind`` / ``verified_tier`` / ``claim_eligible=false``。

    Raises:
        ValueError: 未知 kind 或外援缺 verified_tier。
    """
    src = dict(raw or {})
    kind = str(src.get("subject_kind") or src.get("object_type") or "").strip().lower()
    if kind not in _TOOL_MCP_KINDS:
        raise ValueError(f"eval.subject_kind_not_tool_mcp:{kind or '(empty)'}")

    subject_id = str(src.get("subject_id") or src.get("object_id") or "").strip()
    if not subject_id:
        raise ValueError("eval.subject_id_required")

    interop_ref = str(src.get("interop_ref") or src.get("asset_ref") or "").strip()
    verified_raw = src.get("verified_tier") or src.get("compat_tier")
    verified = normalize_compat_level(verified_raw) if verified_raw else ""
    if verified and verified not in _VALID_TIERS:
        verified = "unknown"

    must_tier = bool(require_verified_tier) or bool(interop_ref) or bool(
        src.get("interop_asset")
    )
    if must_tier and not verified:
        raise ValueError("eval.verified_tier_required_for_interop_subject")

    claimed = normalize_compat_level(src.get("claimed_tier")) if src.get("claimed_tier") else verified
    _rank = {"unknown": 0, "L0": 1, "L1": 2, "L2": 3}
    illegal = bool(
        claimed
        and verified
        and _rank.get(claimed, 0) > _rank.get(verified, 0)
    )

    out = dict(src)
    out.update(
        {
            "schema": "aiplat.eval.tool_mcp_subject.v0",
            "subject_kind": kind,
            "subject_id": subject_id,
            "verified_tier": verified or None,
            "claimed_tier": claimed or None,
            "interop_ref": interop_ref or None,
            "tier_claim_illegal": illegal,
            "claim_eligible": False,
            "accuracy_claim": False,
            "honesty": (
                "E09 tool/mcp subject: fixture/adapter path ≠ live MCP accuracy; "
                "interop refs require verified_tier"
            ),
        }
    )
    return out


def list_e09_subject_kinds() -> Sequence[str]:
    """E09 支持的 subject_kind 列表。

    Returns:
        ``tool`` / ``mcp``。
    """
    return sorted(_TOOL_MCP_KINDS)
