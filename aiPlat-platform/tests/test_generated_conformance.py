"""
生成物契约校验回归测试（Generated-Artifact Conformance, 2026-08-26）。

覆盖（借鉴 SBA conformance 模式，P1-17）:
- 合规生成物通过；缺治理字段/首行残留/input-output 列表格式 → 拒绝
- 契约文件可加载、断言类型齐全
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "aiPlat-platform"))

from builder.generated_conformance import load_contract, validate_text


GOOD_SKILL = """---
name: demo_skill
description: 演示技能：支持查询与检索操作
execution_type: prompt
version: 1.0.0
status: enabled
triggers:
  - 查询
  - 检索
completion_criterion: FR-1 AC-1 查询返回非空结果
effects:
  - type: read
    resources: [filesystem:~/.aiplat]
    idempotent: true
    rollback_available: false
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

    def test_missing_completion_criterion_rejected(self):
        """F4: completion_criterion 必填（与 agent_engineering SOP 对齐）。"""
        bad = GOOD_SKILL.replace("completion_criterion: FR-1 AC-1 查询返回非空结果\n", "")
        violations = validate_text(bad, "skill")
        assert any("completion_criterion" in v for v in violations), violations

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

    def test_template_contains_default_single_mode(self):
        """Phase A：生成规范默认 single，禁止仅凭 FR 数量拆 multi。"""
        spec = (ROOT / "aiPlat-core" / "core" / "engine" / "skills"
                / "agent_engineering" / "SKILL.md").read_text(encoding="utf-8")
        assert '"mode": "single"' in spec
        assert "五条判据全部 AND" in spec or "五条 AND" in spec
        assert "不做无门控互调" in spec
        assert "≤3 个功能需求" not in spec  # 旧 FR 数量启发式已移除

    def test_template_conformant_skill_passes(self):
        """端到端：按模板骨架填写的 SKILL.md（含 3 执步）通过 conformance 校验。"""
        template_filled = """---
name: video_analysis
description: 分析视频并解析视频内容，生成场景/物体/字幕结果
execution_type: prompt
version: 1.0.0
status: enabled
triggers:
  - 分析视频
completion_criterion: FR-1 AC-1 返回非空分析结果
effects:
  - type: read
    resources: [filesystem:~/.aiplat]
    idempotent: true
    rollback_available: false
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


class TestManifestConformance:
    """Phase A：agent_manifest mode / multi 五条 AND 机器门。"""

    def test_single_manifest_passes(self):
        from builder.generated_conformance import validate_manifest
        m = {
            "app_name": "demo",
            "mode": "single",
            "agents": [{
                "name": "app_agent",
                "display_name": "App",
                "agent_type": "react",
                "skills": ["s1", "report_json_export"],
            }],
            "skill_routing": {"s1": "app_agent", "report_json_export": "app_agent"},
            "ui_bindings": {"result_dashboard": "report_json_export"},
        }
        assert validate_manifest(m) == [], validate_manifest(m)

    def test_multi_without_rationale_rejected(self):
        from builder.generated_conformance import validate_manifest
        m = {
            "mode": "multi_agent",
            "agents": [
                {"name": "a1", "skills": ["s1"]},
                {"name": "a2", "skills": ["s2"]},
            ],
            "skill_routing": {"s1": "a1", "s2": "a2"},
            "ui_bindings": {"data_form": "s1"},
        }
        violations = validate_manifest(m)
        assert any("multi_agent_rationale" in v for v in violations), violations
        assert any("upgrade_criteria" in v or "success_metrics" in v for v in violations), violations

    def test_multi_with_full_criteria_passes(self):
        from builder.generated_conformance import validate_manifest
        m = {
            "mode": "multi_agent",
            "multi_agent_rationale": "五条 AND 均满足：正交子任务、单Agent缺口、路由收益、PolicyGate、契约交接。",
            "success_metrics": {"min_runs": 20, "target_success_rate": 0.80},
            "upgrade_criteria": {
                "orthogonal_subtasks": ["a", "b", "c"],
                "single_agent_gap": {
                    "n_runs": 20,
                    "success_rate": 0.5,
                    "failed_stages": ["planning"],
                },
                "routing_benefit": "不同 skill 集导致上下文溢出",
                "policy_gate_stable": True,
                "contracted_handoff": True,
            },
            "agents": [
                {"name": "a1", "skills": ["s1"]},
                {"name": "a2", "skills": ["s2"]},
            ],
            "skill_routing": {"s1": "a1", "s2": "a2"},
            "ui_bindings": {"data_form": "s1"},
        }
        assert validate_manifest(m) == [], validate_manifest(m)

    def test_ui_binding_must_be_routing_key(self):
        from builder.generated_conformance import validate_manifest
        m = {
            "mode": "single",
            "agents": [{"name": "app_agent", "skills": ["s1"]}],
            "skill_routing": {"s1": "app_agent"},
            "ui_bindings": {"result_dashboard": "app_agent"},  # wrongly agent name
        }
        violations = validate_manifest(m)
        assert any("ui_bindings" in v for v in violations), violations


class TestPromotionGate:
    def test_run_through_requires_n20(self):
        from builder.promotion_gate import evaluate_run_through
        r = evaluate_run_through(
            n_runs=5, success_rate=1.0,
            conformance_green=True, real_tests_green=True,
            physical_evidence=True, policy_gate_closed=True,
        )
        assert not r["ok"]
        assert any("e2e_success_rate" in b for b in r["blockers"])

    def test_run_through_green(self):
        from builder.promotion_gate import evaluate_run_through
        r = evaluate_run_through(
            n_runs=20, success_rate=0.85,
            conformance_green=True, real_tests_green=True,
            physical_evidence=True, policy_gate_closed=True,
        )
        assert r["ok"], r

    def test_multi_upgrade_and(self):
        from builder.promotion_gate import evaluate_multi_agent_upgrade
        bad = evaluate_multi_agent_upgrade({})
        assert not bad["ok"]
        good = evaluate_multi_agent_upgrade({
            "orthogonal_subtasks": ["a", "b", "c"],
            "single_agent_gap": {
                "n_runs": 20, "success_rate": 0.4,
                "failed_stages": ["tool_selection"],
            },
            "routing_benefit": "skill sets are mutually exclusive",
            "policy_gate_stable": True,
            "contracted_handoff": True,
        })
        assert good["ok"], good


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
description: 分析视频并解析视频内容，生成场景/物体/字幕结果
execution_type: prompt
version: 1.0.0
status: enabled
triggers:
  - 分析视频
  - 解析视频
completion_criterion: FR-1 AC-1 返回非空分析结果
effects:
  - type: read
    resources: [filesystem:~/.aiplat]
    idempotent: true
    rollback_available: false
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


class TestB2DescriptionTriggerConsistency:
    """B2 深化：触发短语必须出现在 description 中（路由命中一致）。"""

    def test_trigger_not_in_description_rejected(self):
        md = """---
name: demo_skill
description: 演示技能（不含触发短语）
execution_type: prompt
version: 1.0.0
status: enabled
triggers:
  - 上传视频
effects:
  - type: read
    resources: [filesystem:~/.aiplat]
    idempotent: true
    rollback_available: false
input_schema:
  q:
    type: string
    required: true
    description: 查询
output_schema:
  r:
    type: string
    required: true
    description: 结果
---

# 演示
"""
        violations = validate_text(md, "skill")
        assert any("triggers_in_description" in v and "上传视频" in v for v in violations), violations

    def test_all_triggers_in_description_passes(self):
        md = """---
name: demo_skill
description: 上传视频并解析视频内容，生成分析结果
execution_type: prompt
version: 1.0.0
status: enabled
triggers:
  - 上传视频
  - 解析视频
completion_criterion: FR-1 AC-1 返回分析结果
effects:
  - type: read
    resources: [filesystem:~/.aiplat]
    idempotent: true
    rollback_available: false
input_schema:
  q:
    type: string
    required: true
    description: 查询
output_schema:
  r:
    type: string
    required: true
    description: 结果
---

# 演示
"""
        assert validate_text(md, "skill") == [], validate_text(md, "skill")


class TestC3RealArtifactBaseline:
    """C3 生成物验收基线：真实生成产物（frozen fixture）作为 conformance 回归基线。"""

    FIXTURES = ROOT / "aiPlat-platform" / "tests" / "fixtures" / "generated"

    def test_legacy_skill_rejected(self):
        """真实旧产物（video_sense，5 字段 + 首行残留）必须被拒——证明 conformance 有效。"""
        from builder.generated_conformance import validate_file
        violations = validate_file(str(self.FIXTURES / "video_sense_legacy_skill.md"), "skill")
        assert len(violations) >= 3, violations
        assert any("first_line_must_be" in v for v in violations), "应捕获首行残留"
        assert any("input_schema:" in v for v in violations), "应捕获缺 input_schema"

    def test_legacy_agent_rejected(self):
        """真实旧 AGENT.md（首行 markdown 残留）必须被拒。"""
        from builder.generated_conformance import validate_file
        violations = validate_file(str(self.FIXTURES / "video_sense_legacy_agent.md"), "agent")
        assert any("first_line_must_be" in v for v in violations), violations

    def test_new_template_artifact_passes(self):
        """新模板规范产物（含 triggers + description 一致 + 三执步 + 预算内）通过——验收基线的"应然"侧。"""
        new_skill = """---
name: video_analysis
description: 上传视频并解析视频内容，生成场景、物体、字幕分析结果
execution_type: prompt
version: 1.0.0
status: enabled
triggers:
  - 上传视频
  - 解析视频
completion_criterion: FR-1 AC-1 返回场景物体字幕分析结果
effects:
  - type: read
    resources: [filesystem:~/.aiplat]
    idempotent: true
    rollback_available: false
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
- 格式校验: video_id 必须非空
- 校验失败 → 返回"video_id 不能为空"

## 核心处理
1. 加载视频元数据
2. 执行场景切分与物体识别

## 错误处理
- 输入无效 → 提示修正
- 处理超时 → 提示重试
"""
        assert validate_text(new_skill, "skill") == [], validate_text(new_skill, "skill")


class TestPrinciple13FailureWriteback:
    """原则 13：conformance 拒绝（失败）→ 审计写回 → 聚合出规范改进建议。"""

    def test_record_and_aggregate(self, tmp_path, monkeypatch):
        """记录拒绝 → 聚合统计 top 缺失字段 + 生成建议。"""
        from builder.generated_conformance import (
            aggregate_rejections, record_rejection,
            _rejections_path,
        )
        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
        # 清空审计
        _p = _rejections_path()
        if os.path.exists(_p):
            os.remove(_p)

        record_rejection("prj_a", "skill", "/x/a/SKILL.md",
                         ["must_contain: 缺少 'input_schema:'",
                          "must_contain: 缺少 'version:'"])
        record_rejection("prj_a", "skill", "/x/b/SKILL.md",
                         ["must_contain: 缺少 'input_schema:'",
                          "per_field_must_contain[output_schema]: 值缺少 'type'"])
        record_rejection("prj_b", "agent", "/x/c/AGENT.md",
                         ["first_line_must_be: 期望首行为 '---'"])

        agg = aggregate_rejections()
        assert agg["total"] == 3
        assert agg["by_kind"] == {"skill": 2, "agent": 1}
        top_fields = {f for f, _ in agg["top_fields"]}
        assert "input_schema" in top_fields, f"input_schema 应高频缺失: {agg['top_fields']}"
        assert agg["suggestion"], "应有生成规范改进建议"
        assert "agent_engineering" in agg["suggestion"], agg["suggestion"]

    def test_empty_aggregate(self, tmp_path, monkeypatch):
        from builder.generated_conformance import aggregate_rejections
        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "empty_home"))
        agg = aggregate_rejections()
        assert agg["total"] == 0
        assert "暂无" in agg["suggestion"]
