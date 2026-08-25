"""
P1 回归测试（core 侧）— 应用工厂审计 P1-2 修复验证（2026-08-25）。

覆盖:
- P1-2: _exec_test_runner 上游代码落盘块不可达
  （pipeline_eval.py:260-266 写文件语句误放 except ValueError 内 continue 之后 → 永不执行
  → 被测代码从不落盘，测试永远在空目录跑）

运行方式（仓库根）：
    TMPDIR=$(pwd)/../.tmp_pytest AIPLAT_HOME=$(pwd)/../.tmp_pytest/home \
        python3 -m pytest aiPlat-core/core/tests/unit/test_pipeline_eval_p1_fixes.py -v
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[3]
EVAL_PATH = CORE_ROOT / "core" / "harness" / "execution" / "pipeline_eval.py"


class TestP1_2TestRunnerWriteBlockReachable:
    """上游代码落盘块必须在 continue 之前（可执行）。"""

    def test_write_block_precedes_continue(self):
        """静态证据：open(full,...) 写文件出现在 except 的 continue 之前。"""
        src = EVAL_PATH.read_text(encoding="utf-8")
        # 先切出 _exec_test_runner 函数体，避免命中其他循环
        fn = re.search(
            r"async def _exec_test_runner\(.*?(?=\n    async def |\n    def )",
            src, re.DOTALL,
        )
        assert fn, "找不到 _exec_test_runner"
        fn_body = fn.group(0)
        m = re.search(
            r"for f in all_files:.*?(?=\n        try:\n)",
            fn_body, re.DOTALL,
        )
        assert m, "找不到 all_files 写盘循环"
        seg = m.group(0)
        open_pos = seg.find("open(full")
        # continue 语句（缩进 + 换行），排除注释里的 "continue" 字样
        cont_m = re.search(r"\n\s+continue\s*\n", seg)
        assert open_pos != -1, "写文件块缺失（open(full）"
        assert cont_m, "continue 语句缺失"
        continue_pos = cont_m.start()
        assert open_pos < continue_pos, \
            f"P1-2 未修复：写文件块在 continue 之后不可达（open@{open_pos} > continue@{continue_pos}）"

    def test_write_semantics(self):
        """语义证据：复刻修复后的循环 —— 正常文件落盘、穿越文件跳过且不写出。"""
        import logging as _logging
        from unittest.mock import patch

        def safe_join(base_dir: str, file_path: str) -> str:
            base = os.path.realpath(base_dir)
            normalized = os.path.normpath(file_path.lstrip("/"))
            full = os.path.realpath(os.path.join(base, normalized))
            if not full.startswith(base + os.sep) and full != base:
                raise ValueError(f"path_traversal_blocked: {file_path}")
            return full

        with tempfile.TemporaryDirectory(prefix="p1_test_runner_") as tmp:
            output_dir = os.path.join(tmp, "out")
            os.makedirs(output_dir, exist_ok=True)
            all_files = [
                {"path": "app/main.py", "content": "x = 1"},
                {"path": "../../escape.py", "content": "pwned"},
            ]
            warnings_seen = []
            with patch("logging.getLogger") as mock_get:
                logger = _logging.getLogger("test_p1_capture")
                mock_get.return_value = logger
                for f in all_files:
                    path = f.get("path", "") or f.get("file", "")
                    content = f.get("content", "") or f.get("code", "")
                    if path and content:
                        try:
                            full = safe_join(output_dir, path)
                            os.makedirs(os.path.dirname(full), exist_ok=True)
                            with open(full, "w", encoding="utf-8") as fh:
                                fh.write(content)
                        except ValueError:
                            logger.warning("test_runner path traversal blocked: %s", path)
                            continue
                        except OSError:
                            pass
                warnings_seen = [str(c.args[0]) for c in logger.warning.call_args_list]
            # 正常文件落盘（修复前不会落盘）
            assert (Path(output_dir) / "app" / "main.py").read_text() == "x = 1"
            # 穿越文件被跳过且告警
            assert not (Path(tmp) / "escape.py").exists()
            assert any("path traversal blocked" in w for w in warnings_seen)
