from __future__ import annotations

from dataclasses import dataclass
import re
import statistics
from typing import Any, Dict, List, Optional, Tuple

from .types import BBox, OCRToken


def _center_x(b: BBox) -> float:
    return (b[0] + b[2]) / 2.0


def _center_y(b: BBox) -> float:
    return (b[1] + b[3]) / 2.0


def _merge_bbox(a: BBox, b: BBox) -> BBox:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _cluster_by_y(tokens: List[OCRToken], *, y_tol: int = 18) -> List[List[OCRToken]]:
    """
    将 OCR token 按行聚类（基于 y center）。
    这是 PoC：对扫描件表格通常够用。
    """
    ts = sorted(tokens, key=lambda t: (_center_y(t.bbox), _center_x(t.bbox)))
    rows: List[List[OCRToken]] = []
    for t in ts:
        if not rows:
            rows.append([t])
            continue
        last = rows[-1]
        if abs(_center_y(last[0].bbox) - _center_y(t.bbox)) <= y_tol:
            last.append(t)
        else:
            rows.append([t])
    # sort inside each row by x
    for r in rows:
        r.sort(key=lambda t: _center_x(t.bbox))
    return rows


def _guess_budget_header_row(rows: List[List[OCRToken]]) -> Optional[int]:
    """
    找到表头行（预算表）：
    允许一些变体，但必须同时满足：
    - 存在预算语义（预算/投资）
    - 存在第一列语义（科目/项目/内容）
    - 存在年度语义（2026/2027/年度）
    """
    best = None
    best_score = -1
    for i, r in enumerate(rows):
        line = "".join([t.text for t in r]).replace(" ", "")
        if not line:
            continue
        # soft scoring instead of hard boolean
        score = 0
        has_budget = ("预算" in line) or ("投资" in line)
        has_item = ("科目" in line) or ("项目" in line) or ("内容" in line)
        has_year = ("2026" in line) or ("2027" in line) or ("年度" in line)
        if not (has_budget and has_item and has_year):
            continue

        score += 3
        score += 3
        score += 3
        if ("合计" in line) or ("总计" in line):
            score += 2
        if ("金额" in line) or ("单位" in line):
            score += 1
        # Prefer richer header row (more tokens/columns)
        score = score * 10 + len(r)
        if score > best_score:
            best = i
            best_score = score
    if best is not None:
        return best
    return None


def _build_columns_from_header(header: List[OCRToken]) -> Optional[List[Dict[str, Any]]]:
    """
    根据表头 token 估计列中心与列名。
    返回 columns: [{key,name,cx,bbox}]
    """
    # Merge tokens that are close (header may be split)
    merged: List[Tuple[str, BBox]] = []
    for t in header:
        if not merged:
            merged.append((t.text, t.bbox))
            continue
        prev_text, prev_bbox = merged[-1]
        # if horizontally close, treat as same phrase
        if t.bbox[0] - prev_bbox[2] < 18 and abs(_center_y(prev_bbox) - _center_y(t.bbox)) < 12:
            merged[-1] = (prev_text + t.text, _merge_bbox(prev_bbox, t.bbox))
        else:
            merged.append((t.text, t.bbox))

    cols = []
    for text, bbox in merged:
        name = text.strip()
        if not name:
            continue
        key = None
        # item col: very common variants
        if ("科目" in name) or ("项目" in name) or ("内容" in name) or ("预算科目" in name):
            key = "item"
        elif "2026" in name:
            key = "y2026"
        elif "2027" in name:
            key = "y2027"
        elif "合计" in name or "总计" in name:
            key = "total"
        if key:
            cols.append({"key": key, "name": name, "cx": _center_x(bbox), "bbox": bbox})

    # Need at least item + y2026
    if not any(c["key"] == "item" for c in cols):
        return None
    if not any(c["key"] == "y2026" for c in cols):
        return None
    # Prefer to have at least 2 numeric columns so we don't match random "2026" lines.
    if not any(c["key"] in ("y2027", "total") for c in cols):
        return None
    # sort by x
    cols.sort(key=lambda c: c["cx"])
    return cols


def _compute_col_ranges(cols: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Compute [x_min, x_max) ranges for each column based on midpoints between centers.
    This is more stable than nearest-center for noisy OCR.
    """
    cs = sorted(cols, key=lambda c: float(c["cx"]))
    xs = [float(c["cx"]) for c in cs]
    bounds = [-1e18]
    for i in range(len(xs) - 1):
        bounds.append((xs[i] + xs[i + 1]) / 2.0)
    bounds.append(1e18)
    out = []
    for i, c in enumerate(cs):
        cc = dict(c)
        cc["x_min"] = bounds[i]
        cc["x_max"] = bounds[i + 1]
        out.append(cc)
    return out


def _assign_to_col(cols_with_ranges: List[Dict[str, Any]], token: OCRToken) -> Optional[Dict[str, Any]]:
    cx = _center_x(token.bbox)
    for c in cols_with_ranges:
        if float(c["x_min"]) <= cx < float(c["x_max"]):
            return c
    return cols_with_ranges[-1] if cols_with_ranges else None


def _to_amount(s: str) -> Optional[float]:
    """
    Parse numeric amount from OCR text.
    Supports:
    - 1,000 / 1000 / 1000.5
    - with units like "万元"/"万" (we keep numeric part; unit normalization can be added later)
    """
    ss = (s or "").replace(",", "").strip()
    if not ss:
        return None
    # Extract first number-like token
    m = re.search(r"[-+]?\d+(?:\.\d+)?", ss)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def extract_budget_table(tokens: List[OCRToken]) -> List[Dict[str, Any]]:
    """
    从一页 OCR tokens 中抽取“投资预算”类表格（PoC）。
    输出 rows: [{item, y2026, y2027, total, cells:{...}}]
    cells: 每个字段带 bbox 与 raw text，便于引用/高亮。
    """
    # Adaptive y tolerance: fixed 20 often merges multiple table rows on high-DPI renders.
    try:
        hs = [max(1, int(t.bbox[3] - t.bbox[1])) for t in tokens]
        med_h = statistics.median(hs) if hs else 18
        y_tol = max(10, min(18, int(float(med_h) * 0.6)))
    except Exception:
        y_tol = 14
    rows = _cluster_by_y(tokens, y_tol=y_tol)
    header_idx = _guess_budget_header_row(rows)
    if header_idx is None:
        return []
    cols = _build_columns_from_header(rows[header_idx])
    if not cols:
        return []
    cols2 = _compute_col_ranges(cols)

    # Data rows below header
    data_rows = rows[header_idx + 1 :]

    out: List[Dict[str, Any]] = []
    for r in data_rows:
        # Stop if row looks like footer / not table
        line = "".join([t.text for t in r]).strip()
        if not line:
            continue
        # Heuristic: budget data rows must contain digits (amounts).
        has_digit = any(any(ch.isdigit() for ch in t.text) for t in r)
        if not has_digit:
            continue

        cells: Dict[str, Dict[str, Any]] = {}
        for t in r:
            c = _assign_to_col(cols2, t)
            if not c:
                continue
            k = str(c["key"])
            if k not in cells:
                cells[k] = {"text": t.text, "bbox": t.bbox}
            else:
                # merge text and bbox
                cells[k]["text"] = str(cells[k]["text"]) + t.text
                cells[k]["bbox"] = _merge_bbox(tuple(cells[k]["bbox"]), t.bbox)  # type: ignore

        # must have item and at least one amount cell
        if "item" not in cells:
            continue
        if not any(k in cells for k in ("y2026", "y2027", "total")):
            continue

        row = {
            "item": str(cells.get("item", {}).get("text", "")).strip(),
            "y2026": _to_amount(str(cells.get("y2026", {}).get("text", ""))),
            "y2027": _to_amount(str(cells.get("y2027", {}).get("text", ""))),
            "total": _to_amount(str(cells.get("total", {}).get("text", ""))),
            "cells": cells,
        }
        # Filter false positives: must parse at least one numeric amount.
        if row["y2026"] is None and row["y2027"] is None and row["total"] is None:
            continue

        # stop condition: if the "item" looks like next section header
        if len(row["item"]) > 30 and ("排版" in row["item"] or "建议" in row["item"]):
            continue

        out.append(row)

    # Dedup by item
    dedup = {}
    for r in out:
        key = r.get("item") or ""
        if not key:
            continue
        dedup[key] = r
    return list(dedup.values())
