"""test_generated_governance_wiring.py — 生成物侧治理接线测试（CLAUDE.md §23）。

覆盖：① conformance 拒绝 → experience_feedback 登记（生成物失败经验回写）；
② 注册成功 → runtime_governance.md sidecar 预置；③ 注册成功 → 生成 agent 上线
消息总线（agent_messages 生成物侧接线）；④ sidecar daemon CLI 入口可执行（冒烟）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def env(tmp_path):
    os.environ["AIPLAT_HOME"] = str(tmp_path / "home")
    os.environ["AIPLAT_EXPERIENCE_FILE"] = str(tmp_path / "exp.json")
    yield tmp_path
    os.environ.pop("AIPLAT_HOME", None)
    os.environ.pop("AIPLAT_EXPERIENCE_FILE", None)


def test_conformance_rejection_registers_experience(env):
    """生成物 conformance 拒绝 → experience_feedback 登记（生成失败经验回写接线）。"""
    from builder.generated_conformance import record_rejection
    record_rejection("proj-x", "skill", "/tmp/demo/SKILL.md",
                     ["must_contain: 缺 effects 字段", "首行残留"])
    exp = json.load(open(env / "exp.json"))
    recs = list(exp.values())[0].values() if isinstance(exp, dict) and "jobs" in exp else (
        exp if isinstance(exp, list) else [])
    if not recs and isinstance(exp, dict):
        recs = [r for j in exp.get("jobs", {}).values() for r in [j]]
    assert len(recs) >= 1
    r = recs[0]
    assert r["rule_id"].startswith("generated-conformance-reject-skill")
    assert r["status"] == "pending"
    assert r["source"] == "generated_conformance"
    assert r["confidence"] == 1.0


def test_sidecar_generated_on_registration(env):
    """注册成功 → runtime_governance.md sidecar 预置（不侵入 AGENT.md）。"""
    from builder.builder_project_service import _write_runtime_governance_sidecar
    agent_dir = env / "agents" / "demo-agent"
    agent_dir.mkdir(parents=True)
    agent_md = agent_dir / "AGENT.md"
    agent_md.write_text("---\nname: demo\n---\n", encoding="utf-8")
    _write_runtime_governance_sidecar(str(agent_md))
    sc = agent_dir / "runtime_governance.md"
    assert sc.exists()
    content = sc.read_text(encoding="utf-8")
    assert "experience_feedback" in content
    assert "daemon_jobs" in content
    assert "运行时治理入口" in content
    # AGENT.md 本体不被侵入
    assert "runtime_governance" not in agent_md.read_text(encoding="utf-8")


def test_generated_agent_registered_to_bus(env):
    """注册成功 → 生成 agent 上线消息总线（agent_messages 生成物侧接线）。"""
    from builder.builder_project_service import _register_generated_agent_to_bus
    _register_generated_agent_to_bus("demo-agent")
    # 默认存储路径 = $AIPLAT_HOME/agent_messages.json（fixture 已指向 tmp）
    from governance.agent_messages import AgentMessageStore
    store = AgentMessageStore()
    agents = {a["agent_id"]: a for a in store.list_agents()}
    assert "demo-agent" in agents
    assert agents["demo-agent"]["kind"] == "generated-agent"


def test_sidecar_daemon_cli_entry_executable(env):
    """sidecar 中 daemon 断线续跑 CLI 入口真实可执行（冒烟，生成物侧待接线入口验证）。"""
    _djs = Path(__file__).resolve().parents[1] / "governance/daemon_jobs.py"
    assert _djs.exists()
    r = subprocess.run(
        [sys.executable, str(_djs), "--status"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "AIPLAT_DAEMON_JOBS_FILE": str(env / "daemon_jobs.json")})
    assert r.returncode == 0
    out = r.stdout.strip()
    assert '"jobs"' in out  # --status 无 id 时返回 {"jobs": [...]}
