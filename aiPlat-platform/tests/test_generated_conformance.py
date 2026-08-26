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
triggers:
  - 查询
  - 检索
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


class TestTemplateContractAlignment:
    """B1 骨架化：agent_engineering 生成规范中的 SKILL.md 模板必须与 conformance 契约对齐。"""

    def test_skill_template_contains_contract_fields(self):
        """静态证据：生成规范模板含全部契约必填字段。"""
        spec = (ROOT / "aiPlat-core" / "core" / "engine" / "skills"
                / "agent_engineering" / "SKILL.md").read_text(encoding="utf-8")
        for field in ["execution_type: prompt", "input_schema:", "output_schema:",
                      "version: 1.0.0", "status: enabled", "description:"]:
            assert field in spec, f"生成规范模板缺契约字段 {field!r}"
        # 明确禁止 input/output 列表格式
        assert "禁止 input 列表" in spec

    def test_template_conformant_skill_passes(self):
        """端到端：按模板骨架填写的 SKILL.md（含 3 执步）通过 conformance 校验。"""
        template_filled = """---
name: video_analysis
description: 分析视频内容，生成场景/物体/字幕结果
execution_type: prompt
version: 1.0.0
status: enabled
triggers:
  - 分析视频
input_schema:
  video_id:
    type: string
    required: true
    description: 视频ID
output_schema:
  analysis_result:
    type: object
    required: true
    description: 分析结果（场景/物体/字幕）
---

# 视频分析

## 输入校验
- 格式校验: video_id 必须为非空字符串
- 校验失败 → 返回"video_id 不能为空"

## 核心处理
1. 加载视频元数据
2. 执行场景切分与物体识别

## 错误处理
- 输入无效 → 提示修正
- 超时 → 提示重试
"""
        assert validate_text(template_filled, "skill") == [], \
            validate_text(template_filled, "skill")


class TestB2RoutingContextBudget:
    """B2 路由-知识分离：trigger 声明 + 上下文预算。"""

    def test_missing_triggers_rejected(self):
        """缺 triggers 触发短语声明 → 拒绝（路由命中率无法保证）。"""
        no_triggers = GOOD_SKILL.replace("triggers:\n  - 查询\n  - 检索\n", "")
        violations = validate_text(no_triggers, "skill")
        assert any("triggers:" in v for v in violations), violations

    def test_body_over_budget_rejected(self):
        """正文超过 body_max_lines 预算（大而全）→ 拒绝（上下文预算）。"""
        long_body = GOOD_SKILL + "\n## 补充\n" + "\n".join(f"第{i}行冗余说明" for i in range(200))
        violations = validate_text(long_body, "skill")
        assert any("body_max_lines" in v for v in violations), violations

    def test_template_conformant_with_triggers_passes(self):
        """带 triggers + 预算内正文的 SKILL.md 通过校验。"""
        full = """---
name: video_analysis
description: 分析视频内容，生成场景/物体/字幕结果
execution_type: prompt
version: 1.0.0
status: enabled
triggers:
  - 分析视频
  - 解析视频
input_schema:
  video_id:
    type: string
    required: true
    description: 视频ID
output_schema:
  analysis_result:
    type: object
    required: true
    description: 分析结果
---

# 视频分析

## 输入校验
- 格式校验: video_id 非空

## 核心处理
1. 加载元数据

## 错误处理
- 输入无效 → 提示
"""
        assert validate_text(full, "skill") == [], validate_text(full, "skill")
