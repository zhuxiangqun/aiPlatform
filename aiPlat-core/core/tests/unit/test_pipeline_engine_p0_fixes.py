"""
P0 回归测试（core 侧）— 应用工厂实现代码审计 P0-3 / P0-4 修复验证（2026-08-25）。

覆盖:
- P0-3: _deploy_result_files 未做路径约束 → LLM 可控文件名可写任意路径
  （pipeline_engine.py:4685 原 _os2.path.join(_target, _fname) 直接拼接，../../ 逃逸。
  修复：模块级 _safe_join 约束，穿越尝试 ValueError → 跳过该文件 + warning）
- P0-4: _run_stage_skill 域注入段 _prd 未定义 → NameError 被吞 → 域注入 100% 失效
  （pipeline_engine.py:4224/4244 补 _prd 解析：state.prd_data 优先，否则 description
  尾部 JSON，异常回退 {}）

运行方式（仓库根）：
    TMPDIR=$(pwd)/../.tmp_pytest AIPLAT_HOME=$(pwd)/../.tmp_pytest/home \
        python3 -m pytest aiPlat-core/core/tests/unit/test_pipeline_engine_p0_fixes.py -v
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

CORE_ROOT = Path(__file__).resolve().parents[3]
ENGINE_PATH = CORE_ROOT / "core" / "harness" / "execution" / "pipeline_engine.py"

import sys
sys.path.insert(0, str(CORE_ROOT))

from core.harness.execution.pipeline_engine import PipelineEngine, _safe_join


# ---- P0-3: _deploy_result_files 路径穿越 ----

class TestP0_3DeployResultFilesTraversal:
    """LLM 可控文件名不得逃逸 _target 目录。"""

    def test_safe_join_rejects_traversal(self):
        base = tempfile.mkdtemp(prefix="p0_safe_join_")
        # 直接 ../ 逃逸
        with pytest.raises(ValueError):
            _safe_join(base, "../evil.py")
        # 深层穿越
        with pytest.raises(ValueError):
            _safe_join(base, "sub/../../evil.py")
        # 符号链接逃逸（经 realpath 解析后仍在 base 内才算安全）
        with pytest.raises(ValueError):
            _safe_join(base, "a/../../../../etc/passwd")
        # 绝对路径被 lstrip 约束为相对 → 不逃逸（不抛，但结果必须落在 base 内）
        joined = _safe_join(base, "/etc/passwd")
        assert os.path.realpath(joined).startswith(os.path.realpath(base) + os.sep)

    def test_safe_join_allows_normal_paths(self):
        base = tempfile.mkdtemp(prefix="p0_safe_join_ok_")
        joined = _safe_join(base, "src/utils/helper.py")
        assert os.path.realpath(joined).startswith(os.path.realpath(base) + os.sep)
        assert joined.endswith(os.path.join("src", "utils", "helper.py"))

    def test_deploy_result_files_uses_safe_join(self):
        """静态证据：_deploy_result_files 必须经 _safe_join 写文件。"""
        src = ENGINE_PATH.read_text(encoding="utf-8")
        m = re.search(
            r"def _deploy_result_files\(self.*?\)[^:]*:"
            r".*?(?=\n\s*(?:async )?def )",
            src, re.DOTALL,
        )
        assert m, "找不到 _deploy_result_files"
        body = m.group(0)
        assert "_safe_join(_target, _fname)" in body, \
            "P0-3 未修复：_deploy_result_files 未使用 _safe_join 约束文件名"

    def test_deploy_result_files_blocks_traversal_filename(self):
        """行为证据：## FILE: ../../evil.py 被跳过，不写出目录；正常文件仍落盘。"""
        engine = PipelineEngine.__new__(PipelineEngine)
        with tempfile.TemporaryDirectory(prefix="p0_deploy_") as tmp:
            target = os.path.join(tmp, "target")
            outside = os.path.join(tmp, "outside")
            state = {"project_id": "prj_p0", "_project_id": "prj_p0"}
            stage = SimpleNamespace(deploy_files_target_dir=target)
            result = (
                "## FILE: src/good.txt\nhello\n"
                "## FILE: ../../outside/evil.py\npwned\n"
            )
            import logging as _logging
            with patch("logging.getLogger") as mock_get_logger:
                mock_log = _logging.getLogger("test_p0_capture")
                mock_get_logger.return_value = mock_log
                engine._deploy_result_files(state, stage, result)
                blocked_msgs = [str(c.args[0]) for c in mock_log.warning.call_args_list]
            # 正常文件写入 target 内
            assert (Path(target) / "src" / "good.txt").read_text() == "hello"
            # 穿越文件不得出现在 target 外
            assert not (Path(outside) / "evil.py").exists()
            # 也不得出现在 target 内根级（../outside 被解析后逃逸）
            assert not (Path(target) / "outside" / "evil.py").exists()
            # 穿越尝试被告警
            assert any("blocked path traversal" in m for m in blocked_msgs), blocked_msgs


# ---- P0-4: _run_stage_skill 域注入 _prd 未定义 ----

class TestP0_4PrdParsingInDomainInjection:
    """域注入段 _prd 必须在 use-before 赋值（NameError 被吞 → 注入失效）。"""

    def test_prd_assigned_before_use(self):
        """静态证据：_run_stage_skill 内所有 _prd.get 前必须已有 _prd 赋值。"""
        src = ENGINE_PATH.read_text(encoding="utf-8")
        m = re.search(
            r"def _run_stage_skill\(.*?(?=\n    async def |\n    def )",
            src, re.DOTALL,
        )
        assert m, "找不到 _run_stage_skill"
        body = m.group(0)
        # 定位域注入段（P0-4 修复注释所在块）
        fix_marker = "P0-4 修复（2026-08-25）"
        assert fix_marker in body, "P0-4 修复块缺失"
        seg = body[body.index(fix_marker):]
        seg = seg[:seg.index("_domain_id = ")]
        assert "_prd = {}" in seg
        # 段内任何 _prd.get 出现前必须已赋值
        uses = [mo.start() for mo in re.finditer(r"_prd\.get\(", seg)]
        assign_pos = seg.index("_prd = {}")
        for pos in uses:
            assert pos > assign_pos, f"_prd.get 在赋值前被使用 (offset {pos})"

    def test_prd_parsing_semantics(self):
        """行为证据：复刻修复块的解析语义 —— prd_data 优先，否则 description 尾部 JSON，否则 {}。"""

        def resolve_prd(state: dict, desc: str):
            _prd = {}
            try:
                _pd = state.get("prd_data")
                if isinstance(_pd, dict):
                    _prd = _pd
                else:
                    import json as _prd_json
                    _desc_str = str(desc or "")
                    if _desc_str:
                        _tail = _desc_str[-4000:]
                        _start = _tail.find("{")
                        _end = _tail.rfind("}")
                        if 0 <= _start < _end:
                            _cand = _tail[_start:_end + 1]
                            _parsed = _prd_json.loads(_cand)
                            if isinstance(_parsed, dict):
                                _prd = _parsed
            except Exception:
                _prd = {}
            return _prd

        # 1) state.prd_data 优先
        assert resolve_prd({"prd_data": {"title": "T1"}}, "desc...") == {"title": "T1"}
        # 2) 无 prd_data → description 尾部 JSON 兜底
        assert resolve_prd({}, "背景说明 {\"title\": \"T2\"}") == {"title": "T2"}
        # 3) 都没有 → {}
        assert resolve_prd({}, "没有 JSON 的纯文本描述") == {}
        # 4) prd_data 存在但非 dict → 走 description 解析
        assert resolve_prd({"prd_data": "not-a-dict"}, "{\"title\": \"T3\"}") == {"title": "T3"}
        # 5) 解析异常（截断 JSON）→ 回退 {}，不抛
        assert resolve_prd({}, "尾部 {" ) == {}
