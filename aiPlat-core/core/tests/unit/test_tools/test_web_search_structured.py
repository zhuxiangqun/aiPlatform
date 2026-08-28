"""test_web_search_structured.py — WebSearchTool 结构化输出层测试（2026-08-28）。

覆盖：① structured=true → 信源标注事实条目（claim/source_title/source_url/evidence_snippet/confidence）
② url 去重 + 置信度排序 ③ 向后兼容（默认返回原 title/url/snippet）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import asyncio

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture()
def tool():
    from core.apps.tools.web.web_search import WebSearchTool
    t = WebSearchTool()
    # stub 网络方法：单元测试不访问 DuckDuckGo
    async def _no_json(q, limit):
        return {"success": True, "backend": "json", "results": []}
    t._search_json = _no_json
    return t


def _tool_with_json_cross(hit_url: str):
    """构造 JSON 交叉命中指定 url 的工具（验证置信度提升）。"""
    from core.apps.tools.web.web_search import WebSearchTool
    t = WebSearchTool()
    async def _json_hit(q, limit):
        return {"success": True, "backend": "json", "results": [
            {"title": "Cross", "url": hit_url, "snippet": "json abstract"},
        ]}
    t._search_json = _json_hit
    return t


def test_structured_output_shape(tool):
    """structured=true → 每条结果含 claim/source_title/source_url/evidence_snippet/confidence。"""
    raw = {"success": True, "backend": "html", "results": [
        {"title": "Python 官网", "url": "https://python.org", "snippet": "Python 编程语言官方网站"},
        {"title": "Python 文档", "url": "https://docs.python.org", "snippet": "Python 3 文档"},
    ]}
    out = asyncio.run(tool._to_structured("python", raw, "html", 10))
    assert out["structured"] is True
    assert out["total"] == 2
    for item in out["results"]:
        assert item["claim"]
        assert item["source_title"]
        assert item["source_url"]
        assert item["evidence_snippet"]
        assert 0 <= float(item["confidence"]) <= 1


def test_structured_deduplicates_by_url(tool):
    """同 url 多后端出现 → 去重且置信度提升（弱交叉验证）。"""
    raw = {"success": True, "backend": "html", "results": [
        {"title": "A", "url": "https://example.com/a", "snippet": "s1"},
        {"title": "A-dup", "url": "https://example.com/a", "snippet": "s2"},  # 同 url
    ]}
    out = asyncio.run(tool._to_structured("q", raw, "html", 10))
    assert out["total"] == 1  # url 去重


def test_structured_cross_fusion_boosts_confidence():
    """JSON 后端结果交叉命中 → 置信度提升（> 基线 0.5，弱交叉验证）。"""
    t = _tool_with_json_cross("https://python.org")
    raw = {"success": True, "backend": "html", "results": [
        {"title": "Python", "url": "https://python.org", "snippet": "官方"},
    ]}
    out = asyncio.run(t._to_structured("python", raw, "html", 10))
    top = out["results"][0]
    assert float(top["confidence"]) > 0.5  # 基线 0.5 + 交叉 0.2
    assert top["source_url"] == "https://python.org"
    assert top["source"] == "ddg_abstract+cross"


def test_legacy_mode_preserved(tool):
    """默认（structured 未传）→ 返回原结构（title/url/snippet），不破坏向后兼容。"""
    # execute 默认 structured=False → 直接返回 raw
    raw = {"success": True, "backend": "html", "total": 1,
           "results": [{"title": "T", "url": "https://t.com", "snippet": "S"}]}
    # 用桩替换内部搜索方法，验证 execute 透传
    async def fake_html(q, limit):
        return raw
    tool._search_html = fake_html
    import asyncio
    out = asyncio.run(tool.execute({"query": "x", "backend": "html"}))
    assert out.get("structured") is None
    assert out["results"][0]["title"] == "T"
    assert "source_url" not in out["results"][0]  # 原形态无信源字段


def test_structured_requires_url(tool):
    """无 url 的条目被过滤（无法溯源 → 不作为事实条目）。"""
    raw = {"success": True, "backend": "html", "results": [
        {"title": "无链接", "url": "", "snippet": "no source"},
        {"title": "正常", "url": "https://ok.com", "snippet": "ok"},
    ]}
    out = asyncio.run(tool._to_structured("q", raw, "html", 10))
    assert out["total"] == 1
    assert out["results"][0]["source_url"] == "https://ok.com"
