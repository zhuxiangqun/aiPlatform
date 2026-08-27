"""test_agent_messages.py — agent 消息总线测试。

覆盖：注册/下线、点对点发送（含未注册收件人拒绝）、收件箱（未读/标记已读）、在线列表。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from governance.agent_messages import AgentMessageStore  # noqa: E402


@pytest.fixture()
def store(tmp_path):
    return AgentMessageStore(str(tmp_path / "messages.json"))


def test_register_and_agents(store):
    store.register("job-1", meta={"pid": None, "kind": "daemon"})
    store.register("job-2", meta={"pid": None, "kind": "daemon"})
    agents = store.list_agents()
    assert {a["agent_id"] for a in agents} == {"job-1", "job-2"}
    # 无 pid → online=False
    assert all(a["online"] is False for a in agents)


def test_unregister(store):
    store.register("job-1")
    assert "error" not in store.unregister("job-1")
    assert "error" in store.unregister("job-1")  # 二次下线报错


def test_send_and_inbox(store):
    store.register("job-1")
    store.register("job-2")
    r = store.send("job-1", "job-2", "上游产物已就绪")
    assert r["sent"] is True
    inbox = store.inbox("job-2")
    assert inbox["count"] == 1
    assert inbox["messages"][0]["message"] == "上游产物已就绪"
    assert inbox["messages"][0]["status"] == "pending"
    # 未读过滤
    assert store.inbox("job-2", unread_only=True)["count"] == 1
    # 标记已读
    assert store.inbox("job-2", mark_read=True)["count"] == 1
    assert store.inbox("job-2", unread_only=True)["count"] == 0


def test_send_to_unregistered_rejected(store):
    store.register("job-1")
    r = store.send("job-1", "ghost", "hi")
    assert "error" in r  # 收件人未注册 → 拒绝


def test_send_between_agents_no_user(store):
    """a→b→a 双向，不经用户。"""
    store.register("a")
    store.register("b")
    store.send("a", "b", "m1")
    store.send("b", "a", "m2")
    assert store.inbox("a")["count"] == 1
    assert store.inbox("b")["count"] == 1
