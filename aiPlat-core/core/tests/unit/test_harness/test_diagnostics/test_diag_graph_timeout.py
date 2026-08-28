"""test_diag_graph_timeout.py — 诊断图谱构建超时保护测试（2026-08-28）。

覆盖：① 缓存命中毫秒返回 ② 构建超时（monkeypatch 慢 build）→ 返回空图不阻塞。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def test_cached_graph_returns_fast(monkeypatch):
    """_SHARED_GRAPH 有缓存 → 直接返回（不触发构建）。"""
    import core.api.routers.diagnostics as diag
    diag._SHARED_GRAPH = ({"a.py": {"id": "a.py"}}, [{"from": "a", "to": "b"}], [])
    built = []
    monkeypatch.setattr("core.api.core_facade.build_graph",
                        lambda *a, **k: built.append(1) or ({}, [], []))
    nodes, edges, issues = diag._get_or_build_graph()
    assert nodes == {"a.py": {"id": "a.py"}}
    assert built == []  # 未触发构建
    diag._SHARED_GRAPH = (None, None, None)


def test_graph_build_timeout_returns_empty(monkeypatch):
    """构建超时 → 返回空图（诊断降级，不阻塞端点）。"""
    import time
    import core.api.routers.diagnostics as diag
    diag._SHARED_GRAPH = (None, None, None)
    monkeypatch.setenv("AIPLAT_DIAG_GRAPH_BUILD_TIMEOUT", "0.2")

    def slow_build(*a, **k):
        time.sleep(5)  # 远超 0.2s 超时
        return {"slow.py": {}}, [], []
    # 同时 patch 两处引用（core_facade 的 build_graph 与本地 import）
    monkeypatch.setattr("core.api.core_facade.build_graph", slow_build)

    t0 = time.time()
    nodes, edges, issues = diag._get_or_build_graph()
    elapsed = time.time() - t0
    assert elapsed < 3, f"超时保护未生效，耗时 {elapsed:.1f}s"
    assert nodes == {} and edges == []  # 降级空图
