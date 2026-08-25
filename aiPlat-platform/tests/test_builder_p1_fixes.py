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
