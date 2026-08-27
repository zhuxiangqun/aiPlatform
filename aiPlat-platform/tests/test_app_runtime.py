"""test_app_runtime.py — 生成 app 运行时测试（CLAUDE.md §23 生成物侧接线，2026-08-27）。

覆盖：① 入口检测（FastAPI/Flask/Node/静态页/none）；② 静态页 app 端到端
冒烟（detect → daemon_jobs 启动 → HTTP 健康探测 → stop）；③ 记录清理。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def env(tmp_path):
    os.environ["AIPLAT_HOME"] = str(tmp_path / "home")
    os.environ["AIPLAT_DAEMON_JOBS_FILE"] = str(tmp_path / "daemon_jobs.json")
    yield tmp_path
    os.environ.pop("AIPLAT_HOME", None)
    os.environ.pop("AIPLAT_DAEMON_JOBS_FILE", None)


def _write_app(env, project_id: str, files: dict):
    app_home = env / "home" / "apps" / project_id / "current"
    for rel, content in files.items():
        p = app_home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return app_home


# ── 入口检测 ──
def test_detect_fastapi(env):
    from builder.app_runtime import detect_runtime
    _write_app(env, "p1", {
        "backend/app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
    })
    r = detect_runtime("p1")
    assert r["found"] and r["kind"] == "fastapi"
    assert "uvicorn" in r["command"] and "app.main:app" in r["command"]
    assert 18000 <= r["port"] < 19000


def test_detect_flask(env):
    from builder.app_runtime import detect_runtime
    _write_app(env, "p2", {
        "backend/app.py": "from flask import Flask\napp = Flask(__name__)\napp.run(port=5050)\n",
    })
    r = detect_runtime("p2")
    assert r["found"] and r["kind"] == "flask"
    assert r["port"] == 5050  # 从源码探测


def test_detect_static(env):
    from builder.app_runtime import detect_runtime
    _write_app(env, "p3", {"index.html": "<html>hi</html>"})
    r = detect_runtime("p3")
    assert r["found"] and r["kind"] == "static"
    assert "http.server" in r["command"]


def test_detect_none(env):
    from builder.app_runtime import detect_runtime
    _write_app(env, "p4", {"AGENT.md": "---\nname: x\n---\n"})
    r = detect_runtime("p4")
    assert not r["found"] and r["kind"] == "none"


# ── 端到端冒烟（静态页）──
def test_smoke_test_static_app(env):
    from builder.app_runtime import smoke_test
    _write_app(env, "smoke1", {"index.html": "<html><body>hello</body></html>"})
    r = smoke_test("smoke1", keep_alive=False, timeout_sec=20)
    assert r["detected"] is True
    assert r["kind"] == "static"
    assert r["e2e_smoke"]["passed"] is True
    assert r["e2e_smoke"]["status_code"] == 200
    # 测试后应已停止（keep_alive=False）→ 无运行记录
    from builder.app_runtime import _load_runtime_records
    recs = _load_runtime_records()
    assert "smoke1" not in recs


def test_smoke_test_keep_alive_then_stop(env):
    from builder.app_runtime import smoke_test, health_check, stop
    _write_app(env, "smoke2", {"index.html": "<html>hi</html>"})
    r = smoke_test("smoke2", keep_alive=True, timeout_sec=20)
    assert r["e2e_smoke"]["passed"] is True
    # keep_alive=True → 进程仍在服务（HTTP 探测，不依赖 ps；沙箱拒绝 ps 命令）
    h1 = health_check("smoke2", timeout_sec=5)
    assert h1["healthy"] is True
    stop("smoke2")
    time.sleep(1.0)
    # 停止后不再服务（端口关闭）
    h2 = health_check("smoke2", timeout_sec=5, interval_sec=0.3)
    assert h2["healthy"] is False


def test_smoke_failure_registers_experience(env):
    """冒烟失败 → experience_feedback 登记（生成物失败经验回写，与 conformance 拒绝同源）。"""
    from builder.app_runtime import smoke_test
    # Flask 入口但启动即崩溃 → detect 成功、launch 后健康探测失败 → 经验登记
    _write_app(env, "smokefail", {
        "app.py": "from flask import Flask\napp = Flask(__name__)\nraise SystemExit(1)\n",
    })
    r = smoke_test("smokefail", keep_alive=False, timeout_sec=8)
    assert r["smoke_passed"] is False
    # 经验登记到 ExperienceStore（default 存储在 AIPLAT_HOME 下）
    from governance.experience_feedback.experience_feedback import ExperienceStore
    st = ExperienceStore()
    status = st.status()
    rules = [j.get("rule_id", "") for j in status if isinstance(j, dict)]
    assert any("generated-smoke-" in rl for rl in rules), f"未登记冒烟失败经验: {rules}"


# ── 真实测试（测试经理模式：递归发现 → pytest 执行 → test_report）──
def test_real_tests_pass(env):
    """生成物自带测试用例（backend/tests/）→ 递归发现 + pytest 执行通过。"""
    from builder.app_runtime import real_tests
    _write_app(env, "rt1", {
        "backend/app.py": "from flask import Flask\napp = Flask(__name__)\n"
                          "@app.route('/ping')\ndef ping():\n    return 'pong'\n",
        "backend/requirements.txt": "flask\npytest\n",
        "backend/tests/test_api.py":
            "import sys, os\nsys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
            "from app import app\n\ndef test_ping():\n"
            "    c = app.test_client()\n"
            "    r = c.get('/ping')\n"
            "    assert r.status_code == 200\n"
            "    assert b'pong' in r.data\n",
    })
    r = real_tests("rt1", deploy_dir=str(env / "home" / "apps" / "rt1" / "current"),
                   install_deps=False, timeout_sec=30)
    assert r["detected"] is True
    assert r["test_passed"] is True
    report = r["test_report"]
    assert report["test_results"]["passed"] >= 1
    assert report["test_results"]["failed"] == 0
    assert report["bug_summary"]["total_bugs"] == 0


def test_real_tests_failure_bug_summary(env):
    """测试用例断言失败 → test_report 含 bug_summary（failed_tests + suggested_fix）。"""
    from builder.app_runtime import real_tests
    _write_app(env, "rt2", {
        "backend/app.py": "from flask import Flask\napp = Flask(__name__)\n"
                          "@app.route('/ping')\ndef ping():\n    return 'pong'\n",
        "backend/tests/test_api.py":
            "import sys, os\nsys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
            "from app import app\n\ndef test_ping():\n"
            "    c = app.test_client()\n"
            "    r = c.get('/ping')\n"
            "    assert r.status_code == 500  # 期望失败：真实业务断言\n"
            "    assert b'pong' in r.data\n",
    })
    r = real_tests("rt2", deploy_dir=str(env / "home" / "apps" / "rt2" / "current"),
                   install_deps=False, timeout_sec=30)
    assert r["detected"] is True
    assert r["test_passed"] is False
    assert r["test_report"]["test_results"]["failed"] >= 1
    assert r["test_report"]["bug_summary"]["total_bugs"] >= 1
    assert r["test_report"]["bug_summary"]["failed_tests"]


def test_real_tests_no_cases(env):
    """无测试用例 → detected=False。"""
    from builder.app_runtime import real_tests
    _write_app(env, "rt3", {"index.html": "<html>hi</html>"})
    r = real_tests("rt3", deploy_dir=str(env / "home" / "apps" / "rt3" / "current"))
    assert r["detected"] is False
