"""
SBA 原则 10+17 落地测试（2026-08-26）。

覆盖:
- 原则 10 证据门控：deploy_to_app 在 real_pytest pass_rate=0（全失败）时拒绝部署；
  无测试证据（estimated/skip_pytest_gate）放行但已标记风险
- 原则 17 需求派生验收：agent_engineering 生成规范要求 completion_criterion 引用
  PRD acceptance_criteria（验收是根，生成物不得偷换/缩窄验收）

运行方式（aiPlat-platform 目录）：
    AIPLAT_HOME=$(pwd)/../.tmp_pytest/home python3 -m pytest tests/test_builder_evidence_gate.py -v
"""
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _make_final_state(pass_rate=None, skip_gate=False, has_tests=True, arch_len=800, code_len=800):
    state = {
        "code": {"raw_output": "x" * code_len},
        "architecture": {"raw_output": "y" * arch_len},
        "_has_tests": has_tests,
    }
    if pass_rate is not None:
        state["_test_pass_rate"] = pass_rate
    if skip_gate:
        state["_skip_pytest_gate"] = True
    return state


class TestP1_18EvidenceGate:
    """原则 10：真实 pytest 全失败（pass_rate=0）→ 拒绝部署。"""

    @staticmethod
    def _make_svc_with_final(tmp_path, final_state):
        """构造 BuilderProjectService + final_state 文件（mock 部署执行）。"""
        from builder.builder_project_service import BuilderProjectService
        svc = BuilderProjectService(team_service=None)
        svc._projects["prj_g"] = {
            "project_id": "prj_g",
            "runs": [{"phase": "done", "pass_rate": 0}],
            "confirmed_prd": {"title": "t"},
        }
        out_dir = tmp_path / "output" / "prj_g"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "_final_state.json").write_text(json.dumps(final_state))
        return svc

    def test_real_pytest_zero_blocked(self, tmp_path, monkeypatch):
        """real_pytest pass_rate=0 → 拒绝部署（证据门控）。"""
        svc = self._make_svc_with_final(tmp_path, _make_final_state(pass_rate=0.0))
        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
        deployed = []
        with patch("builder.builder_project_service._deploy_to_app_for_project",
                   side_effect=lambda pid, dd, p: deployed.append(pid) or {"status": "ok"}):
            import asyncio
            result = asyncio.run(svc.deploy_to_app("prj_g"))
        assert result["status"] == "error", f"pass_rate=0 应被拒绝: {result}"
        assert "pass_rate=0" in result.get("detail", ""), result
        assert not deployed, "证据门控下不得调用部署"

    def test_real_pytest_pass_allowed(self, tmp_path, monkeypatch):
        """real_pytest pass_rate=0.8 → 放行部署。"""
        svc = self._make_svc_with_final(tmp_path, _make_final_state(pass_rate=0.8))
        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
        deployed = []
        with patch("builder.builder_project_service._deploy_to_app_for_project",
                   side_effect=lambda pid, dd, p: deployed.append(pid) or {"status": "ok"}):
            import asyncio
            result = asyncio.run(svc.deploy_to_app("prj_g"))
        assert result["status"] == "ok", result
        assert deployed == ["prj_g"]

    def test_estimated_no_evidence_allowed(self, tmp_path, monkeypatch):
        """无测试证据（estimated）→ 放行（不阻断，但 runs 标记 source=estimated）。"""
        svc = self._make_svc_with_final(tmp_path, _make_final_state(pass_rate=None))
        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
        deployed = []
        with patch("builder.builder_project_service._deploy_to_app_for_project",
                   side_effect=lambda pid, dd, p: deployed.append(pid) or {"status": "ok"}):
            import asyncio
            result = asyncio.run(svc.deploy_to_app("prj_g"))
        assert result["status"] == "ok", result
        assert deployed == ["prj_g"]
        assert svc._projects["prj_g"]["runs"][-1].get("pass_rate_source") == "estimated"

    def test_skip_pytest_gate_allowed(self, tmp_path, monkeypatch):
        """skip_pytest_gate（L2 合法逃生）→ 放行。"""
        svc = self._make_svc_with_final(tmp_path, _make_final_state(pass_rate=None, skip_gate=True))
        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
        deployed = []
        with patch("builder.builder_project_service._deploy_to_app_for_project",
                   side_effect=lambda pid, dd, p: deployed.append(pid) or {"status": "ok"}):
            import asyncio
            result = asyncio.run(svc.deploy_to_app("prj_g"))
        assert result["status"] == "ok", result
        assert "skipped pytest gate" in svc._projects["prj_g"]["runs"][-1].get(
            "pass_rate_estimate_reason", "")


class TestP1_18AcceptanceDerivation:
    """原则 17：生成规范必须要求 completion_criterion 引用 PRD 验收。"""

    def test_spec_has_acceptance_derivation_step(self):
        spec = (ROOT / "aiPlat-core" / "core" / "engine" / "skills"
                / "agent_engineering" / "SKILL.md").read_text(encoding="utf-8")
        assert "Step 1.5" in spec and "派生验收标准" in spec, "原则 17 未落地：缺验收派生步骤"
        assert "completion_criterion" in spec, "缺 completion_criterion 引用要求"
        assert "偷换/缩窄" in spec, "缺'禁止偷换验收'约束"

    def test_prd_acceptance_injected_to_pipeline(self):
        """_rebuild_via_core 必须把完整 PRD（含 acceptance_criteria）传给 Core。"""
        svc_src = (ROOT / "aiPlat-platform" / "builder" / "builder_project_service.py").read_text(
            encoding="utf-8")
        seg = svc_src[svc_src.index("async def _rebuild_via_core"):]
        seg = seg[:seg.index("\n    async def ") if "\n    async def " in seg else len(seg)]
        assert '"prd_data": prd_data' in seg, "PRD（含验收）未注入 pipeline"
        assert 'prd_data = proj.get("confirmed_prd")' in seg, "confirmed_prd 未作为 prd_data"
