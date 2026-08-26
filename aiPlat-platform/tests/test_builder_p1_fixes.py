"""
P1 回归测试（platform 侧）— 应用工厂审计 P1-1 / P1-3 / P1-4 修复验证（2026-08-25）。

覆盖:
- P1-1: v3.1 HITL gates 模板 dict 属性访问 → AttributeError 被吞 → 功能静默失效
  （builder_project_service.py:1234,1239-1240 对 TeamTemplate.stages 的 dict 用 .agent_id/.hitl 访问）
- P1-3: 授权不一致——create 需 admin（:105）但破坏性 delete/batch-delete 仅 builder（:114,119）
- P1-4: merge apply 部分失败误报 ok（merge_engine.py:339-351 failed 非空仍 status=ok）

运行方式（aiPlat-platform 目录）：
    AIPLAT_HOME=$(pwd)/../.tmp_pytest/home python3 -m pytest tests/test_builder_p1_fixes.py -v
"""
import asyncio
import os
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROJECT_SVC = ROOT / "aiPlat-platform" / "builder" / "builder_project_service.py"
BUILDER_ROUTER = ROOT / "aiPlat-platform" / "api" / "routers" / "builder.py"
MERGE_ENGINE = ROOT / "aiPlat-platform" / "builder" / "merge_engine.py"


# ---- P1-1: HITL gates 模板 dict 属性访问 ----

class TestP1_1HitlTemplateDictAccess:
    def test_hitl_map_uses_dict_access(self):
        """静态证据：_hitl_map 必须用 dict 访问（.get），禁止属性访问。"""
        src = PROJECT_SVC.read_text(encoding="utf-8")
        seg_start = src.index("_hitl_map =")
        seg = src[seg_start:seg_start + 700]
        assert 's.get("agent_id")' in seg, "P1-1 未修复：_hitl_map 未用 dict 访问"
        assert 's.get("hitl")' in seg, "P1-1 未修复：hitl 过滤未用 dict 访问"
        assert '.get("hitl_phase")' in seg, "P1-1 未修复：hitl_phase 未用 dict 访问"
        # 该段不得再出现对模板项（独立变量 s）的属性访问；ts 是 PipelineStageConfig 对象合法
        assert not re.search(r"(?<![A-Za-z0-9_])s\.(agent_id|hitl|hitl_phase)\b", seg), \
            "P1-1 未修复：仍对模板 dict 做属性访问"

    def test_dict_access_semantics(self):
        """语义证据：dict 访问在 YAML 模板上有效；属性访问抛 AttributeError（bug 类）。"""
        stages = [
            {"agent_id": "architect_agent", "hitl": True, "hitl_phase": "review"},
            {"agent_id": "programmer_agent", "hitl": False},
        ]
        # 修复后的 dict 访问
        hitl_map = {s.get("agent_id"): s for s in stages if s.get("hitl") and s.get("agent_id")}
        assert hitl_map == {"architect_agent": stages[0]}
        assert hitl_map["architect_agent"].get("hitl_phase") == "review"
        # 修复前的属性访问（bug 类）：dict 无 .agent_id 属性
        with pytest.raises(AttributeError):
            _ = {s.agent_id: s for s in stages if s.hitl}


# ---- P1-3: 授权不一致 ----

class TestP1_3AuthConsistency:
    def test_destructive_delete_requires_admin(self):
        """静态证据：delete / batch-delete 必须 require_admin_access（与 create 对齐）。"""
        src = BUILDER_ROUTER.read_text(encoding="utf-8")
        m = re.search(
            r'@router\.delete\("/projects/\{project_id\}".*?async def delete_project.*?Depends\((\w+)\)',
            src, re.DOTALL,
        )
        assert m, "找不到 delete_project 端点"
        assert m.group(1) == "require_admin_access", \
            f"P1-3 未修复：delete_project 仍用 {m.group(1)}"
        m2 = re.search(
            r'@router\.post\("/projects/batch-delete".*?async def batch_delete_projects.*?Depends\((\w+)\)',
            src, re.DOTALL,
        )
        assert m2 and m2.group(1) == "require_admin_access", \
            f"P1-3 未修复：batch_delete_projects 仍用 {m2.group(1) if m2 else '?'}"


# ---- P1-4: merge 部分失败误报 ok ----

class TestP1_4MergePartialFailure:
    def test_partial_failure_reports_partial(self, tmp_path):
        """行为证据：部分文件写入失败时 status=partial + failed 明细，不再误报 ok。"""
        from builder.merge_engine import apply_merge

        import_root = tmp_path / "imported"
        import_root.mkdir()
        (import_root / "keep.txt").write_text("keep")
        deploy_dir = tmp_path / "deploy"
        deploy_dir.mkdir()
        # 用目录占位 blocked.txt → open(..., "w") 抛 IsADirectoryError（OSError 子类）
        (deploy_dir / "blocked.txt").mkdir()

        previews = [
            {"path": "ok.txt", "new_content": "hello"},
            {"path": "blocked.txt", "new_content": "x"},
        ]
        decisions = {"ok.txt": "approved", "blocked.txt": "approved"}

        result = apply_merge("prj_p1", str(import_root), str(deploy_dir), previews, decisions)

        assert result["status"] == "partial", f"P1-4 未修复：status={result['status']}（应 partial）"
        assert result["applied"] == ["ok.txt"]
        assert len(result["failed"]) == 1
        assert result["failed"][0]["path"] == "blocked.txt"
        assert (deploy_dir / "ok.txt").read_text() == "hello"
        # baseline 拷贝不受影响
        assert (deploy_dir / "keep.txt").read_text() == "keep"
        # 前端可读的 detail 存在
        assert "写入失败" in result.get("detail", "")

    def test_all_success_reports_ok(self, tmp_path):
        """全部成功 → status=ok（不回归）。"""
        from builder.merge_engine import apply_merge

        deploy_dir = tmp_path / "deploy_ok"
        deploy_dir.mkdir()
        previews = [{"path": "a.txt", "new_content": "A"}]
        decisions = {"a.txt": "approved"}

        result = apply_merge("prj_p1", str(tmp_path / "no_import"), str(deploy_dir), previews, decisions)
        assert result["status"] == "ok"
        assert result["applied"] == ["a.txt"]
        assert result["failed"] == []
        assert (deploy_dir / "a.txt").read_text() == "A"


# ---- P1-8: 跨模块门禁误报（漏再生文件） ----

class TestP1_8CrossModuleGateFalsePositive:
    def test_unmodified_file_declarations_included(self, tmp_path):
        """行为证据：依赖方引用的 route 声明在未修改文件（再生文件）里 → 不得误判 broken。

        修复前 _new_version_text 只拼 previews（被修改文件）→ route 声明在未修改
        文件 → false positive 阻断合法合并；修复后 module_root 内未修改文件一并纳入。
        """
        from builder.cross_module import verify_changed_module_contracts

        module_root = tmp_path / "m2"
        module_root.mkdir()
        # 未修改文件：声明了依赖方引用的 route（本次 merge 未改它）
        (module_root / "router.py").write_text(
            'from fastapi import APIRouter\nrouter = APIRouter()\n'
            '@router.get("/api/items")\ndef list_items():\n    return []\n'
        )
        # 被修改文件（previews）：新版本不再包含该 route
        previews = [{"path": "changed.py", "new_content": "x = 1\n"}]

        graph = {
            "m2": {"depended_by": ["m1"], "depends_on": []},
            "m1": {"depended_by": [], "depends_on": ["m2"],
                   "evidence": {"m2": {"apis": [{"route": "/api/items"}], "entities": []}}},
        }

        # 修复前语义：不传 module_root → 只扫 previews → 误判 broken
        broken_without_root = verify_changed_module_contracts("m2", previews, graph)
        assert broken_without_root["ok"] is False, "前置条件：仅扫 previews 应误判 broken"

        # 修复后：传 module_root → 未修改文件声明被纳入 → ok
        result = verify_changed_module_contracts("m2", previews, graph, module_root=str(module_root))
        assert result["ok"] is True, f"P1-8 未修复：仍误判 broken: {result['broken']}"
        assert result["checked"] == ["m1→/api/items"]

    def test_preview_paths_not_double_counted(self, tmp_path):
        """previews 里的文件不重复纳入（其 new_content 已含新版本）。"""
        from builder.cross_module import _new_version_text

        module_root = tmp_path / "m2b"
        module_root.mkdir()
        (module_root / "changed.py").write_text("OLD_CONTENT\n")
        previews = [{"path": "changed.py", "new_content": "NEW_CONTENT\n"}]

        text = _new_version_text(previews, module_root=str(module_root))
        assert "NEW_CONTENT" in text
        assert "OLD_CONTENT" not in text, "preview 覆盖的文件不应再读旧内容"

    def test_verify_accepts_module_root(self):
        """静态证据：verify_changed_module_contracts 签名带 module_root 并透传。"""
        import inspect
        from builder.cross_module import verify_changed_module_contracts
        sig = inspect.signature(verify_changed_module_contracts)
        assert "module_root" in sig.parameters, "P1-8 未修复：verify 无 module_root 参数"
        from builder.cross_module import _new_version_text
        assert "module_root" in inspect.signature(_new_version_text).parameters


# ---- P1-9: 并行实现收敛（节点→stage 转换 / PRD 解析） ----

class TestP1_9ParallelImplementationsConverged:
    """§10 API 唯一性：同一能力收敛到唯一实现。"""

    def test_nodes_to_stages_single_impl(self):
        """行为证据：app_service._build_stages_from_nodes 委托 workflow_service 唯一实现，
        且产出含全量字段（修复前精简版缺 output_artifact/hitl 等）。"""
        from builder.builder_workflow_service import WorkflowService
        from builder.builder_app_service import AppService

        nodes = [
            {"id": "n1", "data": {"label": "PM", "type": "agent",
             "config": {"agentId": "pm_agent", "outputArtifact": "prd", "hitl": True}}},
            {"id": "n2", "data": {"label": "Arch", "type": "llm",
             "config": {"agentId": "architect_agent"}}},
        ]
        edges = [{"source": "n1", "target": "n2"}]

        app_stages = AppService()._build_stages_from_nodes(nodes, edges)
        wf_stages = WorkflowService()._nodes_to_stages(nodes, edges)

        # 两处产出一致（收敛到同一实现）
        assert app_stages == wf_stages, "P1-9 未收敛：两处转换产出不一致"
        # 全量字段存在（精简版缺失 → 委托后补齐）
        assert app_stages[0]["output_artifact"] == "prd"
        assert app_stages[0]["hitl"] is True
        assert app_stages[1]["output_artifact"] in ("llm_output", "stage_output")
        assert app_stages[1]["agent_type"] in ("react", "conversational")
        # 拓扑排序生效：n1 在 n2 前
        assert [s["id"] for s in app_stages] == ["n1", "n2"]

    def test_app_service_delegates_not_duplicates(self):
        """静态证据：app_service._build_stages_from_nodes 体内无重复转换（委托调用）。"""
        from pathlib import Path
        import inspect
        from builder.builder_app_service import AppService
        body = inspect.getsource(AppService._build_stages_from_nodes)
        assert "WorkflowService()._nodes_to_stages" in body, \
            "P1-9 未修复：app_service 未委托唯一实现"
        assert "out_map" not in body, "P1-9 未修复：app_service 仍内联重复转换"

    def test_session_prd_parsing_delegates(self):
        """行为证据：session 版 _parse_markdown_prd 与 service 版结果一致（含 PRD_READY）。"""
        from builder.builder_session import BuilderSessionService
        from builder.builder_project_service import BuilderProjectService

        md = ("<!-- PRD_READY -->\n# 项目名称：测试项目\n\n## 项目背景\n背景\n"
              "## 功能需求\n### FR-01: 功能一\n- **用户故事**：作为用户，我想测试\n"
              "- **优先级**：P0\n- **验收标准**：\n  - AC1: 正向\n## 范围\n新增Agent")

        session_result = BuilderSessionService()._parse_markdown_prd(md)
        service_result = BuilderProjectService._parse_markdown_prd(md)

        assert session_result == service_result, "P1-9 未收敛：PRD 解析两处结果不一致"
        assert session_result.get("title") == "测试项目"
        assert session_result.get("functional_requirements"), "应解析出功能需求"

    def test_session_prd_delegation_static(self):
        """静态证据：session 版方法体是委托调用，无重复解析逻辑。"""
        from pathlib import Path
        import inspect
        from builder.builder_session import BuilderSessionService
        body = inspect.getsource(BuilderSessionService._parse_markdown_prd)
        assert "BuilderProjectService._parse_markdown_prd" in body, \
            "P1-9 未修复：session 版未委托 service 版"
        assert "re.match(r\"^## \"" not in body, "P1-9 未修复：session 版仍内联解析"


# ---- P1-11: localhost:8004 硬编码收敛 ----

class TestP1_11AppBaseUrlConfigurable:
    """跨进程/前端硬编码 http://localhost:8004 收敛（环境变量 + vite proxy）。"""

    def test_backend_uses_configurable_base_url(self):
        """后端返回的 app URL 必须用 _APP_BASE_URL（环境变量可覆盖），无硬编码。"""
        from pathlib import Path
        router_src = (Path(__file__).resolve().parents[2]
                      / "aiPlat-platform" / "api" / "routers" / "builder.py").read_text(encoding="utf-8")
        assert '_APP_BASE_URL = os.getenv("AIPLAT_APP_BASE_URL"' in router_src, \
            "P1-11 未修复：后端缺 _APP_BASE_URL 配置常量"
        assert 'http://localhost:8004/app/sessions/' not in router_src, \
            "P1-11 未修复：后端仍硬编码 localhost:8004"
        assert "{_APP_BASE_URL}/app/sessions/" in router_src, \
            "P1-11 未修复：文件 URL 未用 _APP_BASE_URL"

    def test_frontend_no_hardcoded_8004(self):
        """前端不得再出现 http://localhost:8004（走 vite proxy 相对路径）。"""
        from pathlib import Path
        mgmt = Path(__file__).resolve().parents[2] / "aiPlat-management" / "frontend" / "src"
        hits = []
        for p in [mgmt / "pages/App/AppPage.tsx", mgmt / "pages/App/Factory/index.tsx"]:
            src = p.read_text(encoding="utf-8")
            if "http://localhost:8004" in src:
                hits.append(str(p))
        assert not hits, f"P1-11 未修复：前端仍硬编码 8004: {hits}"
        # vite proxy 已配置 /app → 8004
        vite_cfg = (mgmt.parent / "vite.config.ts").read_text(encoding="utf-8")
        assert "'/app': {" in vite_cfg and "http://localhost:8004" in vite_cfg, \
            "P1-11 未修复：vite proxy 未配置 /app → 8004"


# ---- P1-12: 状态读取三路径收敛（HTTP → SQLite 唯一实现） ----

class TestP1_12StateReadConverged:
    """§10 API 唯一性：_get_state_via_core 与 get_project_state 收敛到 SQLite 直读。"""

    def test_get_state_via_core_reads_sqlite(self):
        """行为证据：_get_state_via_core 经 SQLite run store 读取（不再走 Core HTTP）。"""
        from unittest.mock import patch, MagicMock
        from builder.builder_project_service import BuilderProjectService

        svc = BuilderProjectService(team_service=None)

        fake_store = MagicMock()
        fake_store.get_full_state.return_value = {
            "phase": "done", "project_id": "prj_x", "some": "data",
        }

        async def _run():
            with patch("core.api.core_facade.get_pipeline_run_store", return_value=fake_store):
                return await svc._get_state_via_core("prj_x")

        import asyncio
        result = asyncio.run(_run())
        assert result["project_id"] == "prj_x"
        assert result["phase"] == "done"
        assert result["state"]["some"] == "data"
        fake_store.get_full_state.assert_called_once_with("prj_x")

    def test_no_http_client_in_state_read(self):
        """静态证据：_get_state_via_core 不再 import PipelineOrchestratorClient（HTTP 路径已收敛）。"""
        from pathlib import Path
        src = (Path(__file__).resolve().parents[2]
               / "aiPlat-platform" / "builder" / "builder_project_service.py").read_text(encoding="utf-8")
        m = src[src.index("async def _get_state_via_core"):]
        m = m[:m.index("\n    async def ")] if "\n    async def " in m else m
        assert "PipelineOrchestratorClient" not in m, \
            "P1-12 未修复：_get_state_via_core 仍走 HTTP 客户端"
        assert "get_pipeline_run_store" in m, "P1-12 未修复：未收敛到 SQLite 直读"

    def test_get_project_state_reuses_converged_reader(self):
        """get_project_state 委托 _get_state_via_core（唯一实现）。"""
        from pathlib import Path
        src = (Path(__file__).resolve().parents[2]
               / "aiPlat-platform" / "builder" / "builder_project_service.py").read_text(encoding="utf-8")
        m = src[src.index("async def get_project_state"):]
        m = m[:m.index("\n    async def ")] if "\n    async def " in m else m
        assert "await self._get_state_via_core(project_id)" in m, \
            "P1-12 未修复：get_project_state 未复用唯一实现"


# ---- P1-13: HITL 审批三套收敛（委托 Core HTTP 唯一实现） ----

class TestP1_13HitlApprovalConverged:
    """§10 API 唯一性：team_service / builder_session 的 HITL 审批委托 project_service（Core HTTP）。"""

    def test_team_service_delegates_to_project_service(self):
        """行为证据：BuilderTeamService.approve_stage 委托 project_service（mock），
        不再走本地 session.approve 旧语义。"""
        from unittest.mock import AsyncMock, patch
        from builder.builder_team_service import BuilderTeamService

        svc = BuilderTeamService()
        fake = AsyncMock(return_value={"project_id": "t1", "phase": "executing",
                                       "status": "ok", "state": {"phase": "executing"}})

        async def _run():
            with patch("builder.builder_project_service._get_project_service", return_value=type("S", (), {"approve_stage": fake})()):
                return await svc.approve_stage("t1")

        import asyncio
        result = asyncio.run(_run())
        assert result["team_id"] == "t1"
        assert result["phase"] == "executing"
        fake.assert_awaited_once_with("t1")

    def test_team_service_no_local_approve(self):
        """静态证据：team_service 不再用 session.approve 本地语义。"""
        from pathlib import Path
        src = (Path(__file__).resolve().parents[2]
               / "aiPlat-platform" / "builder" / "builder_team_service.py").read_text(encoding="utf-8")
        m = src[src.index("async def approve_stage"):]
        m = m[:m.index("\n    async def ") if "\n    async def " in m else len(m)]
        assert "await session.approve(dict(state))" not in m, \
            "P1-13 未修复：team_service 仍走本地 session.approve"
        assert "_get_project_service().approve_stage" in m, "P1-13 未修复：未委托 project_service"

    def test_session_service_delegates_to_project_service(self):
        """行为证据：BuilderSessionService.approve_architecture 委托 project_service。"""
        from unittest.mock import AsyncMock, patch
        from builder.builder_session import BuilderSessionService

        svc = BuilderSessionService()
        fake = AsyncMock(return_value={"project_id": "s1", "phase": "executing", "status": "ok"})

        async def _run():
            with patch("builder.builder_project_service._get_project_service", return_value=type("S", (), {"approve_stage": fake})()):
                return await svc.approve_architecture("s1")

        import asyncio
        result = asyncio.run(_run())
        assert result.phase in ("executing", "failed", "dialogue"), f"unexpected phase: {result.phase}"
        fake.assert_awaited_once_with("s1")

    def test_session_no_local_pipeline_approve(self):
        """静态证据：builder_session 不再用 pipeline.approve 本地语义。"""
        from pathlib import Path
        src = (Path(__file__).resolve().parents[2]
               / "aiPlat-platform" / "builder" / "builder_session.py").read_text(encoding="utf-8")
        assert "pipeline.approve(dict(state))" not in src, \
            "P1-13 未修复：builder_session 仍走本地 pipeline.approve"
        assert "pipeline.reject(dict(state)" not in src, \
            "P1-13 未修复：builder_session 仍走本地 pipeline.reject"
