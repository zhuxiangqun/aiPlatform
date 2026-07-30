"""
WebCrawlTool + WebMapTool — 全站抓取 + URL 发现 (对齐 Firecrawl Crawl/Map)

复用 WebFetchTool 的单页抓取能力，构建 BFS 全站抓取和 URL 映射。
"""

from __future__ import annotations

import asyncio
import logging
import re as _re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

from core.apps.tools.base import BaseTool, ToolMetadata

logger = logging.getLogger(__name__)


class WebCrawlTool(BaseTool):
    def __init__(self):
        super().__init__(ToolMetadata(
            name="web_crawl",
            display_name="全站抓取",
            description="从起始 URL 开始 BFS 抓取全站页面，返回每个页面的 Markdown/HTML 内容。支持深度限制和同源过滤。",
            category="web",
            tags=["web", "crawl", "scrape", "firecrawl"],
            risk_level="normal",
        ))
        self.input_schema = {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "起始基 URL"},
                "max_pages": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                "max_depth": {"type": "integer", "default": 2, "minimum": 1, "maximum": 5},
                "same_domain": {"type": "boolean", "default": True, "description": "仅抓取同域名页面"},
            },
            "required": ["url"],
        }

    async def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        start_url = str(args.get("url", "")).strip()
        if not start_url:
            return {"success": False, "error": "url required"}

        max_pages = min(int(args.get("max_pages", 20)), 100)
        max_depth = min(int(args.get("max_depth", 2)), 5)
        same_domain = bool(args.get("same_domain", True))
        base_domain = urlparse(start_url).netloc

        visited: Set[str] = set()
        results: List[Dict] = []
        queue = [(start_url, 0)]

        while queue and len(visited) < max_pages:
            url, depth = queue.pop(0)
            if url in visited or depth > max_depth:
                continue
            visited.add(url)

            try:
                content, links = await self._fetch_page(url)
                results.append({"url": url, "content": content[:5000], "depth": depth})

                if depth < max_depth:
                    for link in links[:20]:
                        full = urljoin(url, link)
                        if full not in visited and (not same_domain or urlparse(full).netloc == base_domain):
                            queue.append((full, depth + 1))
            except Exception as e:
                results.append({"url": url, "error": str(e)[:200], "depth": depth})

        return {"success": True, "total_pages": len(results), "start_url": start_url, "max_depth": max_depth, "pages": results}

    async def _fetch_page(self, url: str) -> tuple:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "aiPlat/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        # Extract text
        from core.harness.document.parsers import extract_text_from_html
        text = extract_text_from_html(html)
        # Extract links
        links = list(set(_re.findall(r'href=["\']([^"\']+)["\']', html)))
        return text[:10000], [l for l in links if l.startswith("/") or l.startswith("http")]


class WebMapTool(BaseTool):
    def __init__(self):
        super().__init__(ToolMetadata(
            name="web_map",
            display_name="网站地图",
            description="发现网站所有 URL 及标题，返回结构化链接列表。对齐 Firecrawl Map 端点。",
            category="web",
            tags=["web", "map", "discover", "firecrawl"],
            risk_level="low",
        ))
        self.input_schema = {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标网站 URL"},
                "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
            },
            "required": ["url"],
        }

    async def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        start_url = str(args.get("url", "")).strip()
        if not start_url:
            return {"success": False, "error": "url required"}

        limit = min(int(args.get("limit", 50)), 200)
        base_domain = urlparse(start_url).netloc
        visited: Set[str] = set()
        links: List[Dict] = []
        queue = [start_url]

        while queue and len(visited) < limit:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            try:
                import urllib.request
                req = urllib.request.Request(url, headers={"User-Agent": "aiPlat/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                title = ""
                m = _re.search(r"<title>(.*?)</title>", html, _re.IGNORECASE)
                if m:
                    title = _re.sub(r"<[^>]+>", "", m.group(1)).strip()
                links.append({"url": url, "title": title or urlparse(url).path.split("/")[-1] or url})
                # Find more URLs
                for m in _re.finditer(r'href=["\']([^"\']+)["\']', html):
                    full = urljoin(url, m.group(1))
                    if full not in visited and urlparse(full).netloc == base_domain:
                        queue.append(full)
            except Exception:
                links.append({"url": url, "error": "fetch failed"})

        return {"success": True, "total": len(links), "links": links[:limit]}
