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
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.apps.tools.base import BaseTool, ToolMetadata

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    def __init__(self):
        super().__init__(ToolMetadata(
            name="web_search",
            display_name="Web 搜索",
            description="统一 Web 搜索引擎: 支持 DuckDuckGo HTML/JSON/浏览器三种后端。返回结构化搜索结果 (title, url, snippet)。默认使用 HTML 后端 (零外部依赖)。",
            category="web",
            tags=["web", "search", "duckduckgo", "firecrawl"],
            risk_level="normal",
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
            },
            "required": ["query"],
        }

    async def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        query = str(args.get("query", "")).strip()
        if not query:
            return {"success": False, "error": "query 不能为空", "results": []}

        limit = min(int(args.get("limit", 10)), 30)
        backend = str(args.get("backend", "html"))

        if backend == "json":
            return await self._search_json(query, limit)
        elif backend == "browser":
            return await self._search_browser(query, limit)
        else:
            return await self._search_html(query, limit)

    async def _search_html(self, query: str, limit: int) -> Dict[str, Any]:
        """DuckDuckGo Lite HTML 搜索 (零外部依赖)."""
        try:
            import urllib.parse
            import urllib.request
            from html.parser import HTMLParser

            url = f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            results = _parse_html_results(html)
            return {"success": True, "backend": "html", "total": len(results), "results": results[:limit]}

        except Exception as e:
            logger.warning("HTML search failed: %s", e)
            return {"success": False, "backend": "html", "error": str(e)[:200], "results": []}

    async def _search_json(self, query: str, limit: int) -> Dict[str, Any]:
        """DuckDuckGo Instant Answer API."""
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
