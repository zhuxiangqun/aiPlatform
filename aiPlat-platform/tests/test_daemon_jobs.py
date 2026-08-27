"""test_daemon_jobs.py — 后台任务托管（断线续跑）测试。

覆盖：start → status 全生命周期、输出 attach、退出码解析（成功/失败）、kill。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from governance.daemon_jobs import DaemonJobStore  # noqa: E402


@pytest.fixture()
def store(tmp_path):
    return DaemonJobStore(str(tmp_path / "jobs.json"))


def test_start_and_finish_success(store):
    r = store.start("echo-job", "echo hello-world")
    assert "id" in r and r["status"] == "running"
    time.sleep(1.0)
    st = store.status(r["id"])
    assert st["status"] in ("finished", "failed")
    assert st["exit_code"] == "0"
    # attach 能读到输出
    a = store.attach(r["id"])
    assert "hello-world" in a["output"]


def test_start_and_fail_exit_code(store):
    r = store.start("fail-job", "sh -c 'exit 3'")
    time.sleep(1.0)
    st = store.status(r["id"])
    assert st["status"] == "failed"
    assert st["exit_code"] == "3"


def test_list_sorted(store):
    store.start("a", "sleep 0.1")
    time.sleep(0.05)
    store.start("b", "sleep 0.1")
    jobs = store.list()
    assert len(jobs) == 2
    # 最新在前
    assert jobs[0]["name"] == "b"


def test_kill_running_job(store):
    r = store.start("sleep-job", "sleep 30")
    time.sleep(0.3)
    k = store.kill(r["id"])
    assert k["status"] == "killed"
    time.sleep(0.2)
    st = store.status(r["id"])
    assert st["status"] == "killed"


def test_unknown_job(store):
    assert "error" in store.status("job-does-not-exist")
    assert "error" in store.attach("job-does-not-exist")
