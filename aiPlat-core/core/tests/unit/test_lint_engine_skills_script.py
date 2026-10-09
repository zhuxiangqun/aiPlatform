"""scripts/lint_engine_skills.py — engine corpus clean + injected debt fails."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SCRIPT = REPO / "scripts" / "lint_engine_skills.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("lint_engine_skills", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_engine_corpus_currently_clean():
    mod = _load_mod()
    findings = mod.scan(REPO / "aiPlat-core" / "core" / "engine" / "skills")
    assert findings == [], findings[:5]


def test_injected_misplaced_file_completion_fails():
    mod = _load_mod()
    with tempfile.TemporaryDirectory(prefix="eng_skill_lint_") as tmp:
        d = Path(tmp) / "fake_summary"
        d.mkdir()
        (d / "SKILL.md").write_text(
            """---
name: fake_summary
description: 摘要技能
execution_type: prompt
completion_criterion: |
  1. 输出符合 ## FILE: 格式规范
  2. 每个文件包含完整可运行代码
---

# SOP
1. 总结文本
""",
            encoding="utf-8",
        )
        findings = mod.scan(Path(tmp))
        codes = {f.get("code") for f in findings}
        assert "misplaced_file_completion" in codes, findings


def test_injected_handler_pairing_fails():
    mod = _load_mod()
    with tempfile.TemporaryDirectory(prefix="eng_skill_pair_") as tmp:
        d = Path(tmp) / "has_handler"
        d.mkdir()
        (d / "handler.py").write_text("async def execute(p): return p\n", encoding="utf-8")
        (d / "SKILL.md").write_text(
            """---
name: has_handler
description: 有 handler 却声明 prompt
execution_type: prompt
---

# SOP
1. 做事
""",
            encoding="utf-8",
        )
        findings = mod.scan(Path(tmp))
        codes = {f.get("code") for f in findings}
        assert "handler_pairing" in codes, findings
