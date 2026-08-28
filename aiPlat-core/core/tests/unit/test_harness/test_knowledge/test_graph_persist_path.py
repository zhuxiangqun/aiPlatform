"""test_graph_persist_path.py — 图谱持久化路径解析测试（2026-08-28）。

覆盖：① AIPLAT_HOME 优先（code_graph.db / cap_graph.db 落在 $AIPLAT_HOME 下）
② capability_graph 工作区扫描用 AIPLAT_HOME。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def test_code_graph_db_uses_aiplat_home(tmp_path, monkeypatch):
    """code_graph_persist._db_path → $AIPLAT_HOME/code_graph.db。"""
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    import importlib
    mod = importlib.import_module("core.harness.knowledge.code_graph_persist")
    mod._DB_PATH = None
    p = mod._db_path()
    assert p == str(tmp_path / "home" / "code_graph.db")


def test_cap_graph_db_uses_aiplat_home(tmp_path, monkeypatch):
    """cap_graph_persist._db_path → $AIPLAT_HOME/cap_graph.db。"""
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    import importlib
    mod = importlib.import_module("core.harness.knowledge.cap_graph_persist")
    mod._DB_PATH = None
    p = mod._db_path()
    assert p == str(tmp_path / "home" / "cap_graph.db")


def test_capability_graph_workspace_scan_uses_aiplat_home(tmp_path, monkeypatch):
    """capability_graph 工作区扫描（agents/skills）用 AIPLAT_HOME（非硬编码 ~/.aiplat）。"""
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    # 造一个工作区 agent 验证扫描命中
    agent_dir = tmp_path / "home" / "agents" / "test_graph_ws"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text("---\nname: test-graph-ws\nstatus: enabled\n---\n", encoding="utf-8")
    import importlib
    mod = importlib.import_module("core.harness.knowledge.capability_graph")
    nodes, edges = {}, []
    # 直接调工作区扫描（不触发全量）
    from core.harness.knowledge.capability_graph import _scan_agents_dir
    _scan_agents_dir(agent_dir.parent, node_prefix="workspace_agent", nodes=nodes, edges=edges)
    ids = [k for k in nodes if "test_graph_ws" in k]
    assert ids, f"工作区 agent 未按 AIPLAT_HOME 扫描: {list(nodes)}"
