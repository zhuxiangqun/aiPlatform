"""
生成物契约校验回归测试（Generated-Artifact Conformance, 2026-08-26）。

覆盖（借鉴 SBA conformance 模式，P1-17）:
- 合规生成物通过；缺治理字段/首行残留/input-output 列表格式 → 拒绝
- 契约文件可加载、断言类型齐全
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "aiPlat-platform"))

from builder.generated_conformance import load_contract, validate_text


GOOD_SKILL = """---
name: demo_skill
description: 演示技能
execution_type: prompt
version: 1.0.0
status: enabled
input_schema:
  query:
    type: string
    required: true
    description: 查询
output_schema:
  result:
    type: string
    required: true
    description: 结果
---

# 演示

SOP 正文
"""


GOOD_AGENT = """---
name: demo_agent
display_name: 演示Agent
agent_type: react
---

# 演示Agent

## SOP

1. 步骤一

## 反模式

- ❌ 不要做 X
"""


class TestGeneratedConformance:
    def test_contract_loads(self):
        c = load_contract()
        assert "skill" in c and "agent" in c
        assert c["skill"]["first_line_must_be"] == "---"
        assert "input_schema:" in c["skill"]["must_contain"]
        assert "must_contain_in_order" in c["skill"]

    def test_good_skill_passes(self):
        assert validate_text(GOOD_SKILL, "skill") == []

    def test_good_agent_passes(self):
        assert validate_text(GOOD_AGENT, "agent") == []

    def test_missing_governance_fields_rejected(self):
        """缺 input_schema/version/effects 等治理字段 → 拒绝（对应审计"生成物仅 5-6 字段"）。"""
        bad = GOOD_SKILL.replace("input_schema:", "# input_schema:")
        bad = bad.replace("version: 1.0.0", "version: 1.0.0")
        violations = validate_text(bad, "skill")
        assert any("input_schema" in v for v in violations), violations

    def test_input_output_list_format_rejected(self):
        """input/output 列表格式（registry 读 input_schema/output_schema）→ 拒绝。"""
        legacy = """---
name: legacy_skill
description: 旧格式
execution_type: prompt
version: 1.0.0
status: enabled
input:
  - name: q
    type: string
    required: true
output:
  - name: r
    type: string
---

SOP
"""
        violations = validate_text(legacy, "skill")
        assert any("input_schema" in v for v in violations), violations

    def test_first_line_residue_rejected(self):
        """首行 ```markdown 残留（frontmatter 解析失败 → 0 fields）→ 拒绝。"""
        bad = "```markdown\n" + GOOD_SKILL
        violations = validate_text(bad, "skill")
        assert any("first_line_must_be" in v for v in violations), violations

    def test_empty_first_line_rejected(self):
        """首行空行（auth_agent 0-fields 案例）→ 拒绝。"""
        bad = "\n" + GOOD_SKILL
        violations = validate_text(bad, "skill")
        assert any("first_line_must_be" in v for v in violations), violations

    def test_agent_missing_sop_rejected(self):
        bad = GOOD_AGENT.replace("## SOP", "## 说明")
        violations = validate_text(bad, "agent")
        assert any("## SOP" in v for v in violations), violations

    def test_unknown_kind_rejected(self):
        with pytest.raises(ValueError):
            validate_text(GOOD_SKILL, "unknown")
