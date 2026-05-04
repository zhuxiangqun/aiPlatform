from __future__ import annotations

import re

from .extract_numbers import pick_value_by_year, pick_values_by_keywords
from .types import Citation, IngestResult, QAResult


_YEAR_RE = re.compile(r"(19\d{2}|20\d{2})")


def answer_question(ingested: IngestResult, question: str) -> QAResult:
    """
    PoC 查询：
    - 从问题中抽取年份 year
    - 在每一页的 numbers_by_page 中寻找与 year 上下文相关的数字
    - 返回一个最可能的 value，并附带 bbox citation（页码 + page_image + bbox）

    注意：这是“先跑通链路”的 PoC，不代表最终精度。
    """
    q = str(question or "").strip()
    m = _YEAR_RE.search(q)
    year = m.group(1) if m else ""
    wants_budget = ("预算" in q) or ("投资" in q)
    keywords = []
    if "投资" in q:
        keywords.append("投资")
    if "预算" in q:
        keywords.append("预算")
    if "投资预算" in q:
        keywords.append("投资预算")

    # ---- Budget-like question: return a list of candidates ----
    if wants_budget and keywords:
        # Prefer structured budget table if extracted during ingest
        if ingested.tables_by_page:
            for page_idx, tables in enumerate(ingested.tables_by_page):
                if not tables:
                    continue
                # Take first table as budget table (PoC)
                table = tables
                lines = []
                cits = []
                for r in table:
                    item = str(r.get("item") or "").strip()
                    y2026 = r.get("y2026", None)
                    cells = r.get("cells") or {}
                    if year == "2026" and y2026 is None:
                        continue
                    if not item:
                        continue
                    if year == "2026":
                        # cite y2026 cell bbox if present
                        cell = cells.get("y2026") or {}
                        bbox = cell.get("bbox")
                        raw = cell.get("text")
                        lines.append(f"- {item}：{raw} 万元")
                        if bbox:
                            cits.append(Citation(page_idx=page_idx, asset_path=ingested.page_images[page_idx], bbox=tuple(bbox), extra={"item": item, "year": 2026, "raw": raw}))
                    else:
                        # list row summary
                        lines.append(f"- {item}：2026={r.get('y2026')}，2027={r.get('y2027')}，合计={r.get('total')}")

                if lines:
                    ans = "（PoC-结构化表格）识别到投资预算条目如下：\n" + "\n".join(lines)
                    return QAResult(answer=ans, citations=cits, debug={"year": year, "doc_id": ingested.doc_id, "table_page": page_idx, "rows": len(table)})

        # Fallback: keyword-based candidate numbers (older PoC)
        items = []
        for page_idx, nums in enumerate(ingested.numbers_by_page or []):
            for hit in pick_values_by_keywords(nums, keywords, limit=20):
                # Heuristics: prefer "money-like" numbers, exclude font sizes / pure page indices / pure years.
                ctx = str(hit.context or "")
                tok = str(hit.token.text or "")
                v = hit.value if hit.value is not None else None

                # drop obvious formatting hints
                if "pt" in ctx.lower() or "字号" in ctx or "行距" in ctx:
                    continue

                money_hint = any(x in tok for x in ("万", "元", "¥", "￥", "亿", "億元")) or any(
                    x in ctx for x in ("万", "万元", "元", "¥", "￥", "亿", "億元", "人民币", "日元", "JPY", "CNY")
                )
                if not money_hint:
                    continue

                # exclude pure years unless explicitly coupled with money words
                if v is not None and 1900 <= v <= 2099 and ("年" in ctx) and ("万元" not in ctx) and ("元" not in ctx):
                    continue

                # exclude small ordinal-like numbers
                if v is not None and abs(v) < 50 and ("万元" not in ctx) and ("元" not in ctx):
                    continue

                items.append((page_idx, hit))
        if not items:
            return QAResult(
                answer="未能在 OCR 文本中找到与“投资/预算”相关的数值上下文（PoC）。建议：提高 DPI、改用 PaddleOCR、或换更清晰扫描件。",
                citations=[],
                debug={"year": year, "keywords": keywords, "doc_id": ingested.doc_id},
            )
        # sort by page then value desc
        items.sort(key=lambda x: (x[0], -(x[1].value or -1.0)))
        top = items[:12]
        lines = []
        cits = []
        for page_idx, hit in top:
            page_img = ingested.page_images[page_idx]
            cits.append(Citation(page_idx=page_idx, asset_path=page_img, bbox=hit.token.bbox, extra={"value_raw": hit.value_raw, "context": hit.context}))
            ctx = (hit.context or "").strip()
            if len(ctx) > 120:
                ctx = ctx[:117] + "..."
            lines.append(f"- 第{page_idx+1}页：{hit.value_raw}（上下文：{ctx}）")
        ans = "（PoC）我在文档中识别到与“投资/预算”相关的候选条目如下：\n" + "\n".join(lines)
        return QAResult(answer=ans, citations=cits, debug={"year": year, "keywords": keywords, "doc_id": ingested.doc_id, "candidates": len(items)})

    # ---- Default: year-based single value ----
    best = None
    best_page = None
    for page_idx, nums in enumerate(ingested.numbers_by_page or []):
        hit = pick_value_by_year(nums, year) if year else None
        if not hit:
            continue
        # heuristic: prefer larger value
        v = hit.value if hit.value is not None else -1.0
        if best is None or (v > (best.value or -1.0)):
            best = hit
            best_page = page_idx

    if not best or best_page is None:
        return QAResult(
            answer="未能从该文档中可靠抽取到对应数值（PoC：建议换一个更清晰的扫描件，或提高 DPI / 改用 PaddleOCR）。",
            citations=[],
            debug={"year": year, "doc_id": ingested.doc_id},
        )

    page_img = ingested.page_images[best_page]
    cit = Citation(page_idx=best_page, asset_path=page_img, bbox=best.token.bbox, extra={"value_raw": best.value_raw, "context": best.context})

    ans = f"（PoC）我在第 {best_page + 1} 页附近识别到与 {year} 相关的数值：{best.value_raw}。"
    return QAResult(answer=ans, citations=[cit], debug={"year": year, "doc_id": ingested.doc_id})
