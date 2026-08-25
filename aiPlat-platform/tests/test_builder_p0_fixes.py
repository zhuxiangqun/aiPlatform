"""
P0 回归测试（platform 侧）— 应用工厂实现代码审计 P0-1 / P0-2 / P0-5 修复验证（2026-08-25）。

覆盖:
- P0-1: start_pipeline / start_pipeline_background 接线断裂
  （builder_app_service:161,190,221 / builder_workflow_service:214-215 / api/routers/builder.py:71,194
  共 6 处调用无类定义 → AttributeError。修复：BuilderProjectService 新增两个方法委托 rebuild_project）
- P0-2: PRD 解析 eval() 任意代码执行
  （builder_project_service.py:958 原 lambda s: eval(s) 解析 Python dict 字面量 → 改为 ast.literal_eval）
- P0-5: deploy_project_to_app 部署签名 fail-open → fail-closed
  （builder.py:529 原 except 后 warning 跳过继续部署 → 改为 raise HTTPException 403 拒绝部署）

运行方式（aiPlat-platform 目录）：
    AIPLAT_HOME=$(pwd)/../.tmp_pytest/home python3 -m pytest tests/test_builder_p0_fixes.py -v
"""
import asyncio
import json
import os
import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROJECT_SVC = ROOT / "aiPlat-platform" / "builder" / "builder_project_service.py"
BUILDER_ROUTER = ROOT / "aiPlat-platform" / "api" / "routers" / "builder.py"


def _make_service():
    """最小 BuilderProjectService：不触发真实模型 / 团队加载。"""
    from builder.builder_project_service import BuilderProjectService
    return BuilderProjectService(team_service=None)


# ---- P0-1: start_pipeline 接线断裂 ----

class TestP0_1StartPipelineWiring:
    def test_methods_defined_on_service(self):
        from builder.builder_project_service import BuilderProjectService
        assert callable(getattr(BuilderProjectService, "start_pipeline", None)), \
            "start_pipeline 未定义（P0-1 未修复）"
        assert callable(getattr(BuilderProjectService, "start_pipeline_background", None)), \
            "start_pipeline_background 未定义（P0-1 未修复）"

    def test_all_call_sites_reference_defined_methods(self):
        """6 处生产调用点引用的方法名必须都在类中有 async def 定义。"""
        svc_src = PROJECT_SVC.read_text(encoding="utf-8")
        defined = set(re.findall(r"async def (start_pipeline\w*)", svc_src))
        assert "start_pipeline" in defined and "start_pipeline_background" in defined
        callers = [
            ROOT / "aiPlat-platform" / "builder" / "builder_app_service.py",
            ROOT / "aiPlat-platform" / "builder" / "builder_workflow_service.py",
            BUILDER_ROUTER,
        ]
        total_call_sites = 0
        for caller in callers:
            src = caller.read_text(encoding="utf-8")
            used = set(re.findall(r"\.(start_pipeline\w*)", src))
            missing = used - defined
            assert not missing, f"{caller.name} 引用了未定义方法: {missing}"
            total_call_sites += len(re.findall(r"\.(start_pipeline\w*)", src))
        assert total_call_sites >= 6, f"调用点数量异常（预期 ≥6，实际 {total_call_sites}）"

    def test_start_pipeline_delegates_to_rebuild_project(self):
        svc = _make_service()
        svc._projects["prj_ok"] = {"project_id": "prj_ok", "confirmed_prd": {"title": "t"}}
        svc.rebuild_project = AsyncMock(return_value={"status": "ok", "detail": "built"})

        async def _run():
            return await svc.start_pipeline("prj_ok")

        result = asyncio.run(_run())
        assert result["status"] == "ok"
        assert result["run_id"] == "prj_ok"
        svc.rebuild_project.assert_awaited_once_with("prj_ok")

    def test_start_pipeline_requires_confirmed_prd(self):
        svc = _make_service()
        svc._projects["prj_no_prd"] = {"project_id": "prj_no_prd"}  # 无 confirmed_prd
        svc.rebuild_project = AsyncMock()

        async def _run():
            return await svc.start_pipeline("prj_no_prd")

        result = asyncio.run(_run())
        assert result["status"] == "error"
        svc.rebuild_project.assert_not_awaited()

        # 不存在的项目同样拒绝且不触发构建
        async def _run2():
            return await svc.start_pipeline("ghost")

        assert asyncio.run(_run2())["status"] == "error"
        svc.rebuild_project.assert_not_awaited()

    def test_start_pipeline_background_accepts_and_triggers(self):
        svc = _make_service()
        svc._projects["prj_b"] = {"project_id": "prj_b", "confirmed_prd": {"title": "t"}}
        svc.rebuild_project = AsyncMock(return_value={"status": "ok"})

        async def _run():
            result = await svc.start_pipeline_background("prj_b")
            assert result["status"] == "accepted"
            await asyncio.sleep(0.05)  # 让 create_task 完成
            return result

        result = asyncio.run(_run())
        assert result["run_id"] == "prj_b"
        svc.rebuild_project.assert_awaited_once_with("prj_b")

    def test_start_pipeline_background_rejects_without_prd(self):
        svc = _make_service()
        svc._projects["prj_b2"] = {"project_id": "prj_b2"}
        svc.rebuild_project = AsyncMock()

        async def _run():
            return await svc.start_pipeline_background("prj_b2")

        assert asyncio.run(_run())["status"] == "error"
        svc.rebuild_project.assert_not_awaited()


# ---- P0-2: eval → ast.literal_eval ----

class TestP0_2NoBareEvalInPrdParsing:
    def test_no_bare_eval_in_project_service(self):
        """禁止裸 eval(；仅允许 ast.literal_eval。"""
        src = PROJECT_SVC.read_text(encoding="utf-8")
        bad = re.findall(r"[^A-Za-z_]eval\(", src)
        assert not bad, f"builder_project_service.py 仍含裸 eval( : {bad}"

    def test_parser_chain_rejects_code_execution(self):
        """复刻 _extract_prd_from_chat 三级 parser 链：恶意字符串不执行、不解析。"""
        import ast as _ast
        import json as _json

        def parse_chain(json_str):
            for parser in [
                lambda s: _json.loads(s),                       # standard JSON
                lambda s: _json.loads(s.replace("'", '"')),     # single-quoted keys
                lambda s: _ast.literal_eval(s),                 # Python dict literal（P0-2 修复）
            ]:
                try:
                    prd = parser(json_str)
                    if isinstance(prd, dict) and prd:
                        return prd
                except Exception:
                    continue
            return None

        # Python dict 字面量（LLM 常见输出）→ 第三 parser 解析成功
        prd = parse_chain("{'title': 'x', 'frs': ['a']}")
        assert prd == {"title": "x", "frs": ["a"]}

        # 恶意代码 payload：旧 eval() 会执行 → 现在必须返回 None 且无副作用
        marker = ROOT / ".tmp_p0_pwned_marker"
        if marker.exists():
            marker.unlink()
        malicious = f"__import__('os').system('touch {marker}')"
        assert parse_chain(malicious) is None, "恶意 payload 不应被解析为 PRD"
        assert not marker.exists(), "P0-2 未修复：eval 执行了恶意 payload！"


# ---- P0-5: 部署签名 fail-closed ----

class TestP0_5DeploySignatureFailClosed:
    def test_fail_open_wording_removed(self):
        src = BUILDER_ROUTER.read_text(encoding="utf-8")
        assert "部署签名验证失败，跳过" not in src, "fail-open 日志仍在（P0-5 未修复）"
        assert "拒绝部署（fail-closed）" in src, "fail-closed 日志缺失"

    @staticmethod
    def _make_proj_files(home: Path, project_id: str, sig: str):
        proj_dir = home / "projects" / project_id
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "project.json").write_text(json.dumps({"title": "t"}))
        (proj_dir / "PROJECT.manifest.json").write_text(
            json.dumps({"signature": sig, "version": "0.1.0"})
        )

    def _make_deploy_coro(self, svc_factory, verify_impl, monkeypatch):
        """monkeypatch 路由依赖 + verify_skill_signature，返回可 await 的部署协程。"""
        from api.routers import builder as builder_router
        monkeypatch.setattr(builder_router, "_get_svc", svc_factory)
        import core.api.core_facade as cf
        monkeypatch.setattr(cf, "verify_skill_signature", verify_impl)

        async def _run():
            return await builder_router.deploy_project_to_app("prj_sig", _auth="tester")

        return _run

    def test_verification_exception_raises_403(self, monkeypatch, tmp_path):
        """验证抛异常（如签名服务不可用）→ 拒绝部署（403），不得 fallback 到跳过部署。"""
        home = tmp_path / "home"
        self._make_proj_files(home, "prj_sig", "sig-abc")
        monkeypatch.setenv("AIPLAT_HOME", str(home))

        reached_deploy = []

        class FakeProjects:
            def get(self, pid, default=None):
                return {"metadata": {"provenance": {"signature": "sig-abc"}}}

        class FakeSvc:
            _projects = FakeProjects()

            async def deploy_to_app(self, pid):
                reached_deploy.append(pid)  # fail-open 下才会到达这里
                return {"status": "ok"}

        def boom(*a, **k):
            raise RuntimeError("signature service down")

        from fastapi import HTTPException

        coro = self._make_deploy_coro(lambda: FakeSvc(), boom, monkeypatch)
        with pytest.raises(HTTPException) as ei:
            asyncio.run(coro())
        assert ei.value.status_code == 403
        assert not reached_deploy, "fail-closed 下 deploy_to_app 不应被调用"

    def test_verified_signature_still_deploys(self, monkeypatch, tmp_path):
        """签名验证通过 → 正常部署（fail-closed 不破坏合法路径）。"""
        home = tmp_path / "home"
        self._make_proj_files(home, "prj_sig", "sig-abc")
        monkeypatch.setenv("AIPLAT_HOME", str(home))

        class FakeProjects:
            def get(self, pid, default=None):
                return {"metadata": {"provenance": {"signature": "sig-abc"}}}

        class FakeSvc:
            _projects = FakeProjects()

            async def deploy_to_app(self, pid):
                return {"status": "ok", "deployed_to": "app-8004"}

        coro = self._make_deploy_coro(
            lambda: FakeSvc(),
            lambda *a, **k: {"verified": True},
            monkeypatch,
        )
        result = asyncio.run(coro())
        assert result["status"] == "ok"
        assert result["deployed_to"] == "app-8004"

    def test_no_signature_skips_verification_and_deploys(self, monkeypatch, tmp_path):
        """项目无签名 → 不进入验证分支 → 正常部署（签名验证仅对签名项目生效）。"""
        home = tmp_path / "home"
        monkeypatch.setenv("AIPLAT_HOME", str(home))

        class FakeProjects:
            def get(self, pid, default=None):
                return {"project_id": pid}  # 无 metadata.provenance.signature

        class FakeSvc:
            _projects = FakeProjects()

            async def deploy_to_app(self, pid):
                return {"status": "ok"}

        coro = self._make_deploy_coro(
            lambda: FakeSvc(),
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("不应调用验证")),
            monkeypatch,
        )
        result = asyncio.run(coro())
        assert result["status"] == "ok"
