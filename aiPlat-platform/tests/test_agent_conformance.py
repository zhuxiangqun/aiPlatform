"""
workspace agent 符合度校验器测试（Agent Conformance, 2026-08-26）。

覆盖（ratchet 模式，同 ruff F821 先例）:
- 合规 AGENT.md 通过（行数≤100 / 无 model / 交接 5 字段 / 输出格式无模板）
- 四类违规各自被捕获
- ratchet_diff：存量违规容忍、新增违规阻断
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "aiPlat-platform"))

from builder.agent_conformance import (
    HANDOFF_FIELDS,
    ratchet_diff,
    validate_agent_md,
)

GOOD = """---
name: demo_agent
display_name: 演示Agent
agent_type: react
required_skills:
  - code_generation
---

# 演示Agent

## SOP
1. 步骤一

## 交接规范
1. **做了什么**：完成 X
2. **产出物在哪**：state["x"]
3. **如何验证**：命令 V
4. **已知问题**：边界 Y
5. **下一步**：下游读 state["x"]
"""


class TestAgentConformance:
    def test_good_passes(self):
        assert validate_agent_md("/dev/null")  # 不存在文件报错
        # 写临时文件验证
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "AGENT.md"
            p.write_text(GOOD, encoding="utf-8")
            assert validate_agent_md(str(p)) == []

    def test_model_hardcode_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "AGENT.md"
            bad = GOOD.replace("agent_type: react", "agent_type: react\nmodel: deepseek-chat")
            p.write_text(bad, encoding="utf-8")
            v = validate_agent_md(str(p))
            assert any("model:" in x and "§12" in x for x in v), v

    def test_missing_handoff_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "AGENT.md"
            bad = GOOD.replace("\n## 交接规范", "\n## 其他")
            p.write_text(bad, encoding="utf-8")
            v = validate_agent_md(str(p))
            assert any("handoff" in x for x in v), v

    def test_output_format_template_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "AGENT.md"
            bad = GOOD.replace("## SOP", "## 输出格式\n```json\n{\"a\": 1}\n```\n\n## SOP")
            p.write_text(bad, encoding="utf-8")
            v = validate_agent_md(str(p))
            assert any("output_format" in x for x in v), v

    def test_over_lines_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "AGENT.md"
            bad = GOOD + "\n".join(f"## 补充{i}" for i in range(120))
            p.write_text(bad, encoding="utf-8")
            v = validate_agent_md(str(p))
            assert any("max_lines" in x for x in v), v


class TestAgentRatchet:
    def test_baseline_tolerates_legacy(self):
        """存量违规在基线中 → 不判新增。"""
        base = {"legacy_agent": ["max_lines: 150 行超过预算 100", "handoff: 缺字段"]}
        cur = {"legacy_agent": ["max_lines: 150 行超过预算 100", "handoff: 缺字段"]}
        assert ratchet_diff(cur, base) == {}

    def test_new_violation_blocked(self):
        """新增违规（基线没有的）→ 判新增。"""
        base = {"legacy_agent": ["handoff: 缺字段"]}
        cur = {"legacy_agent": ["handoff: 缺字段", "model: 硬编码"]}
        diff = ratchet_diff(cur, base)
        assert diff["legacy_agent"] == ["model: 硬编码"], diff

    def test_new_agent_all_violations_blocked(self):
        """基线没有的新 agent → 全部违规判新增。"""
        diff = ratchet_diff({"new_agent": ["handoff: 缺字段"]}, {})
        assert diff["new_agent"] == ["handoff: 缺字段"]
