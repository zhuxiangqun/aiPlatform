"""
WebSearchTool — 统一 Web 搜索入口 (对齐 Firecrawl Search)

合并原有 3 个搜索实现:
  SearchTool._search_duckduckgo (base.py:445) — DuckDuckGo Lite HTML
  _ddg_search (retrieval_crag.py:464) — DuckDuckGo JSON API
  BrowserTool.search (browser.py:202) — 浏览器搜索 UI

后端选择:
  backend="html" → DuckDuckGo Lite HTML (轻量, 零JS依赖)
  backend="json" → DuckDuckGo Instant Answer API (结构化)
  backend="browser" → 浏览器打开搜索引擎 (需要 Playwright)

结构化模式 (structured=true, 2026-08-28):
  面向 Agent 机器推理的交付形态——把"链接候选列表"归一化为"带信源标注的事实条目"
  (claim/source_title/source_url/evidence_snippet/confidence)，并融合多后端去重重排。
  借鉴 AnySearch 结构化输出理念：剔除广告/HTML 噪声，机器可直接消费，每条附权威信源。
  默认保持向后兼容（structured=false 返回原 title/url/snippet 列表）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.apps.tools.base import BaseTool, ToolMetadata

logger = logging.getLogger(__name__)


def infer_recency_days(query: str) -> Optional[int]:
    """Parse 「最近 N 天 / 过去一周 / last 30 days」 when the caller omitted recency_days."""
    import re

    text = str(query or "")
    if not text.strip():
        return None
    m = re.search(
        r"(?:最近|过去|近|last|past)\s*(\d{1,3})\s*(?:天|日|days?)",
        text,
        re.I,
    )
    if m:
        days = int(m.group(1))
        return max(1, min(365, days))
    if re.search(r"(?:最近|过去|近|last|past)\s*(?:一|1)?\s*周|last\s*week", text, re.I):
        return 7
    if re.search(r"(?:最近|过去|近|last|past)\s*(?:一|1)?\s*(?:个)?月|last\s*month", text, re.I):
        return 30
    if re.search(r"最近\s*30\s*天|过去\s*30\s*天", text):
        return 30
    return None


def apply_recency(query: str, recency_days: Any) -> tuple:
    """Return (query, df). df is DuckDuckGo's week/month/year filter, or ''."""
    text = str(query or "").strip()
    days_arg = recency_days
    if days_arg is None or days_arg == "":
        days_arg = infer_recency_days(text)
    if days_arg is None or days_arg == "":
        return text, ""
    try:
        days = int(days_arg)
    except (TypeError, ValueError):
        return text, ""
    if days <= 0:
        return text, ""
    if days <= 7:
        df = "w"
    elif days <= 31:
        df = "m"
    else:
        df = "y"
    return text, df


def _attach_citations(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Every row with a url also carries citation for agent grounding."""
    rows = payload.get("results")
    if not isinstance(rows, list):
        return payload
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("source_url") or row.get("url") or "").strip()
        if url and not row.get("citation"):
            row["citation"] = url
    return payload


class WebSearchTool(BaseTool):
    def __init__(self):
        super().__init__(ToolMetadata(
            name="web_search",
            description="统一 Web 搜索引擎: 支持 DuckDuckGo HTML/JSON/浏览器三种后端。"
                        "structured=true 时返回面向 Agent 的结构化事实条目（信源标注 + 融合去重）。"
                        "默认使用 HTML 后端 (零外部依赖)。",
            category="web",
            tags=["web", "search", "duckduckgo", "firecrawl"],
        ))
        self.input_schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询词",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 30,
                    "description": "返回结果数量",
                },
                "backend": {
                    "type": "string",
                    "enum": ["html", "json", "browser"],
                    "default": "html",
                    "description": "搜索后端: html(DuckDuckGo Lite)/json(DuckDuckGo API)/browser(Playwright)",
                },
                "structured": {
                    "type": "boolean",
                    "default": False,
                    "description": "结构化模式: 返回信源标注的事实条目（claim/source_title/source_url/evidence_snippet/confidence），并融合多后端去重",
                },
                "recency_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 365,
                    "description": "只搜最近 N 天。≤7 用周、≤31 用月、否则用年（DuckDuckGo df）。查询含「最近30天」等时可省略，会自动推断",
                },
            },
            "required": ["query"],
        }

    async def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        query = str(args.get("query", "")).strip()
        if not query:
            return {"success": False, "error": "query 不能为空", "results": []}

        limit = min(int(args.get("limit", 10)), 30)
        backend = str(args.get("backend", "html"))
        structured = bool(args.get("structured", False))
        recency_days = args.get("recency_days")
        if recency_days is None or recency_days == "":
            recency_days = infer_recency_days(query)
        query, df = apply_recency(query, recency_days)

        if backend == "json":
            raw = await self._search_json(query, limit, df=df)
        elif backend == "browser":
            # Browser backend has no time filter; honor df via HTML like JSON does.
            if df:
                raw = await self._search_html(query, limit, df=df)
                raw["backend"] = "browser"
            else:
                raw = await self._search_browser(query, limit)
        else:
            raw = await self._search_html(query, limit, df=df)

        raw["recency_days"] = int(recency_days) if df and recency_days not in (None, "") else None
        raw["time_window"] = df or ""
        if not structured:
            return _attach_citations(raw)
        out = await self._to_structured(query, raw, backend, limit)
        out["recency_days"] = raw.get("recency_days")
        out["time_window"] = raw.get("time_window")
        return _attach_citations(out)

    # ── 结构化输出层（AnySearch 借鉴：信源标注 + 多后端融合，2026-08-28）──
    async def _to_structured(self, query: str, raw: Dict[str, Any],
                             backend: str, limit: int) -> Dict[str, Any]:
        """把原始候选列表归一化为事实条目，并融合其他后端去重。

        条目字段: {claim, source_title, source_url, evidence_snippet, source, confidence}
        confidence 启发式: json/abstract 信源较高，html 普通条目 0.5 基线；
        多后端同 url 出现 → 提升置信度（弱交叉验证）。
        """
        items: Dict[str, Dict[str, Any]] = {}  # url → item（url 去重）
        raw_results = raw.get("results") or []
        for r in raw_results:
            if not isinstance(r, dict):
                continue
            url = str(r.get("url") or "").strip()
            if not url:
                continue
            title = str(r.get("title") or "").strip()
            snippet = str(r.get("snippet") or "").strip()
            source = str(r.get("source") or backend)
            # 结构化条目：snippet 即证据片段，附信源标注
            items[url] = {
                "claim": title or snippet[:80],
                "source_title": title,
                "source_url": url,
                "evidence_snippet": snippet[:500],
                "source": source,
                "confidence": 0.5,  # 基线；多源交叉后提升
            }

        # 多后端融合：JSON Instant Answer 的摘要信源提升置信度（结构化信源）
        if backend != "json":
            try:
                json_raw = await self._search_json(query, 5, df=str(raw.get("time_window") or ""))
                for r in (json_raw.get("results") or []):
                    if not isinstance(r, dict):
                        continue
                    url = str(r.get("url") or "").strip()
                    if not url:
                        continue
                    if url in items:
                        items[url]["confidence"] = min(0.85, items[url]["confidence"] + 0.2)
                        items[url]["source"] = "ddg_abstract+cross"
                    else:
                        items[url] = {
                            "claim": str(r.get("title") or r.get("snippet") or "")[:80],
                            "source_title": str(r.get("title") or ""),
                            "source_url": url,
                            "evidence_snippet": str(r.get("snippet") or "")[:500],
                            "source": "ddg_abstract",
                            "confidence": 0.7,  # Instant Answer 结构化信源
                        }
            except Exception:
                logger.debug("structured fusion: json 后端不可用，跳过交叉验证", exc_info=True)

        ordered = sorted(items.values(), key=lambda x: float(x.get("confidence") or 0), reverse=True)
        return {"success": raw.get("success", True), "backend": backend,
                "structured": True, "query": query,
                "total": len(ordered), "results": ordered[:limit]}

    async def _search_html(self, query: str, limit: int, df: str = "") -> Dict[str, Any]:
        """DuckDuckGo Lite HTML 搜索 (零外部依赖)."""
        try:
            import urllib.parse
            import urllib.request
            from html.parser import HTMLParser

            url = f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}"
            if df:
                url += f"&df={urllib.parse.quote(df)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            results = _parse_html_results(html)
            return {"success": True, "backend": "html", "total": len(results), "results": results[:limit]}

        except Exception as e:
            logger.warning("HTML search failed: %s", e)
            return {"success": False, "backend": "html", "error": str(e)[:200], "results": []}

    async def _search_json(self, query: str, limit: int, df: str = "") -> Dict[str, Any]:
        """DuckDuckGo Instant Answer API.

        The instant-answer API ignores time filters. A requested window uses
        the HTML index, which honors ``df``.
        """
        if df:
            filtered = await self._search_html(query, limit, df=df)
            filtered["backend"] = "json"
            filtered["time_window"] = df
            return filtered
        try:
            import urllib.parse
            import urllib.request
            import json as _json

            url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = _json.loads(resp.read().decode("utf-8", errors="ignore"))

            results = []
            if data.get("Abstract"):
                results.append({"title": data.get("Heading", ""), "url": data.get("AbstractURL", ""), "snippet": data["Abstract"], "source": "ddg_abstract"})
            for topic in data.get("RelatedTopics", [])[:limit]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({"title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "), "url": topic.get("FirstURL", ""), "snippet": topic.get("Text", ""), "source": "ddg_related"})
            return {"success": True, "backend": "json", "total": len(results), "results": results[:limit]}

        except Exception as e:
            logger.warning("JSON search failed: %s", e)
            return await self._search_html(query, limit)

    async def _search_browser(self, query: str, limit: int) -> Dict[str, Any]:
        """浏览器搜索 (需要 Playwright 环境)."""
        try:
            from core.apps.tools.browser import BrowserTool
            bt = BrowserTool()
            result = await bt.execute({"action": "search", "query": query, "engine": "google"})
            return {"success": True, "backend": "browser", "total": 1, "results": [result.get("output", {})] if result.get("success") else []}
        except Exception as e:
            logger.warning("Browser search unavailable, falling back to HTML: %s", e)
            return await self._search_html(query, limit)


def _parse_html_results(html: str) -> List[Dict[str, str]]:
    results = []
    try:
        from html.parser import HTMLParser
        class LiteParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results = []
                self.current = {}
                self.in_link = False
                self.in_snippet = False
                self.last_href = ""
            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                if tag == "a" and "href" in attrs_dict:
                    url = attrs_dict["href"]
                    if url.startswith("http"):
                        self.last_href = url
                        self.current = {"url": url}
                        self.in_link = True
                elif tag == "td" and "result-snippet" in (attrs_dict.get("class", "")):
                    self.in_snippet = True
            def handle_data(self, data):
                if self.in_link and self.current:
                    self.current["title"] = data.strip()
                    self.in_link = False
                elif self.in_snippet and self.current:
                    self.current["snippet"] = data.strip()
                    self.results.append(self.current)
                    self.current = {}
                    self.in_snippet = False
            def handle_endtag(self, tag):
                pass
        parser = LiteParser()
        parser.feed(html)
        results = parser.results
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
    return results[:20]
