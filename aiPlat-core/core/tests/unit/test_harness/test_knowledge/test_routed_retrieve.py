"""test_routed_retrieve.py — 意图路由统一检索测试（AnySearch 借鉴 P0-2，2026-08-28）。

覆盖：① 意图判定（code/knowledge/web）② 通道分发（stub 各通道）③ web 通道结构化输出
（信源标注）④ 通道降级（code 不可用 → knowledge → web）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core.harness.syscalls.retrieval import _route_intent  # noqa: E402


def test_route_intent_code():
    assert _route_intent("python 报错 如何修复") == "code"
    assert _route_intent("实现一个快速排序算法") == "code"


def test_route_intent_knowledge():
    assert _route_intent("操作手册 配置流程 说明") == "knowledge"
    assert _route_intent("规范 标准 术语") == "knowledge"


def test_route_intent_web():
    assert _route_intent("今天天气怎么样") == "web"
    assert _route_intent("最新的新闻") == "web"


def test_sys_routed_retrieve_code_channel(monkeypatch):
    """代码意图 → 路由 code 通道，返回代码事实条目。"""
    from core.harness.syscalls import retrieval as mod

    async def fake_code_search(pattern, **kwargs):
        return {"results": [{"content": "def add(a, b): return a + b", "path": "app.py", "score": 0.9}]}
    monkeypatch.setattr("core.harness.syscalls.code.sys_code_search", fake_code_search)

    import asyncio
    r = asyncio.run(mod.sys_routed_retrieve("python 报错", top_k=5))
    assert r["route"] == "code"
    assert r["results"][0]["source"] == "code"
    assert r["sources"][0]["url"] == "app.py"


def test_sys_routed_retrieve_web_channel(monkeypatch):
    """通用意图 → 路由 web 通道，结构化信源标注。"""
    from core.harness.syscalls import retrieval as mod

    class _FakeTool:
        async def execute(self, args):
            return {"success": True, "results": [
                {"claim": "C", "source_title": "T", "source_url": "https://x.com",
                 "evidence_snippet": "evidence", "source": "web", "confidence": 0.6},
            ]}
    monkeypatch.setattr("core.apps.tools.web.web_search.WebSearchTool", _FakeTool)

    import asyncio
    r = asyncio.run(mod.sys_routed_retrieve("今天新闻", top_k=5))
    assert r["route"] == "web"
    assert r["sources"][0]["url"] == "https://x.com"
    assert r["sources"][0]["source"] == "web"


def test_sys_routed_retrieve_code_fallback(monkeypatch):
    """code 通道异常 → 降级 knowledge（不伪装命中）。"""
    from core.harness.syscalls import retrieval as mod

    def boom(*a, **k):
        raise RuntimeError("code unavailable")
    monkeypatch.setattr("core.harness.syscalls.code.sys_code_search", boom)

    # knowledge 也 stub 为空（同步函数，与 sys_knowledge_retrieve 签名一致）
    def fake_kb(*a, **k):
        return []
    monkeypatch.setattr("core.harness.syscalls.retrieval.sys_knowledge_retrieve", fake_kb)
    # 禁用 web 避免真实网络
    import asyncio
    r = asyncio.run(mod.sys_routed_retrieve("python 报错", top_k=5, include_web=False))
    # code 抛异常 → 降级 knowledge（空）→ 不再降级 web（include_web=False）
    assert r["route"] == "knowledge"
