"""
Budget query — isolated business logic, separated from generic KB service.

All domain-specific text (keywords, units, error messages) is configuration-driven
via environment variables, per CLAUDE.md §5.29 kernel-agnostic principle.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .db import KBSqlite
from .storage import get_tenant_storage

_BUDGET_KEYWORDS = os.getenv("AIPLAT_BUDGET_KEYWORDS", "预算,投资").split(",")
_BUDGET_NOT_SUPPORTED_MSG = os.getenv(
    "AIPLAT_BUDGET_NOT_SUPPORTED_MSG",
    "Current MVP only supports budget/investment queries.",
)
_BUDGET_UNIT = os.getenv("AIPLAT_BUDGET_UNIT", "万元")
_BUDGET_DEFAULT_YEAR = int(os.getenv("AIPLAT_BUDGET_DEFAULT_YEAR", "2026"))


def _wants_budget(question: str) -> bool:
    q = question.strip()
    return any(kw.strip() and kw.strip() in q for kw in _BUDGET_KEYWORDS)


def _build_items(
    rows: list,
    year: int,
    limit: int,
) -> Dict[str, Any]:
    import json as _json

    items: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    ykey = f"y{year}"

    for r in rows:
        cells = r.get("cells") or {}
        cell = (cells.get(ykey) or cells.get("total") or {}) if isinstance(cells, dict) else {}
        raw = cell.get("text")
        bbox = cell.get("bbox")
        amount = r.get(ykey) if r.get(ykey) is not None else r.get("total")
        if raw is None:
            if amount is None:
                continue
            raw = str(amount)
        items.append({
            "item": r.get("item"),
            "year": year,
            "amount_raw": raw,
            "amount": amount,
            "unit": _BUDGET_UNIT,
            "doc_id": r.get("doc_id"),
            "page_idx": r.get("page_idx"),
        })
        if bbox and r.get("page_image_path"):
            citations.append({
                "doc_id": r.get("doc_id"),
                "page_idx": r.get("page_idx"),
                "asset_path": r.get("page_image_path"),
                "bbox": bbox,
                "extra": {"item": r.get("item"), "year": year, "raw": raw},
            })
        if len(items) >= int(limit):
            break

    return {"items": items, "citations": citations}


def query(
    *,
    tenant_id: str,
    collection_id: str,
    question: str,
    year: Optional[int] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    if not tenant_id:
        raise ValueError("tenant_id_required")
    if not collection_id:
        raise ValueError("collection_id_required")
    q = str(question or "").strip()
    if not q:
        raise ValueError("question_required")

    st = get_tenant_storage(tenant_id)
    db = KBSqlite(st.db_path)
    db.ensure_schema()

    if not _wants_budget(q):
        return {"answer": _BUDGET_NOT_SUPPORTED_MSG, "items": [], "citations": []}

    y = int(year or _BUDGET_DEFAULT_YEAR)
    rows = db.list_budget_rows(tenant_id=st.tenant_id, collection_id=collection_id, year=y)

    result = _build_items(rows, y, limit)
    answer = f"Found {len(result['items'])} budget items for year {y}."
    return {
        "answer": answer,
        "items": result["items"],
        "citations": result["citations"],
        "tenant_id": st.tenant_id,
        "collection_id": collection_id,
    }
