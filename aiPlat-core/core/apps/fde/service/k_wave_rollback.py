"""V5 — state the rollback boundary. Does not roll anything back."""

from __future__ import annotations

from typing import Any, Dict


def rollback_scope() -> Dict[str, Any]:
    """Two columns. Not a rollback, and not a promise that every change undoes."""
    return {
        "can_rollback": [
            "已挂上且已 apply 的 VersionedOntologyStore 提案",
            "带 edge_before 的 merge 仲裁边",
        ],
        "cannot_rollback": [
            "本地草稿 draft_local_*",
            "本地草稿 k5_local_*",
            "没有 edge_before 的仲裁边",
            "没有提案 id 的案例",
        ],
        "covers_edges": False,
        "covers_local_drafts": False,
        "one_click_any_change": False,
        "change_trace": "人批 apply 时另写 JSON diff。回滚仍用 YAML 快照。没有提案的旧边仍不能撤。",
        "authority_note": "可回滚已挂上的本体提案，以及带写入前快照的 merge 边。没有快照的边不能撤。不是一键撤回任意变更。",
    }
