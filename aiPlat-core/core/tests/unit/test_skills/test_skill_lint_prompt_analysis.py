"""Prompt/analysis skills must not get coding change_contract / noisy SOP-trigger warnings."""

from __future__ import annotations

from pathlib import Path

from core.management.skill_linter import lint_skill


def _codes(rep: dict) -> set:
    out = set()
    for bucket in ("errors", "warnings", "info"):
        for it in rep.get(bucket) or []:
            if isinstance(it, dict) and it.get("code"):
                out.add(it["code"])
    return out


def test_prompt_executable_skill_skips_change_contract(tmp_path: Path):
    """skill_kind=executable + execution_type=prompt must NOT require coding change_contract."""
    md = tmp_path / "SKILL.md"
    md.write_text(
        "---\nname: x\n---\n\n# X\n\n## 输出铁律（强制）\n\n1. 直接输出产物\n\n## SOP\n\n1. 做分析\n",
        encoding="utf-8",
    )
    rep = lint_skill(
        {
            "id": "requirement_analysis_like",
            "name": "requirement_analysis_like",
            "description": "分析用户需求并输出结构化PRD",
            "type": "analysis",
            "category": "analysis",
            "metadata": {
                "skill_kind": "executable",
                "execution_type": "prompt",
                "execution_mode": "prompt",
                "permissions": ["fs:read"],
                "triggers": ["需求分析", "PRD", "需求文档"],
                "trigger_conditions": [{"when": "pipeline需求阶段", "query": "生成PRD"}],
                "skip_when": "已有完整PRD文档",
                "keywords": {
                    "objects": ["PRD", "需求", "验收标准"],
                    "actions": ["分析", "生成", "输出"],
                },
                "completion_criterion": "functional_requirements至少3条",
                "filesystem": {"skill_md": str(md)},
            },
            "input_schema": {"user_requirement": {"type": "string", "required": True}},
            "output_schema": {
                "prd": {"type": "object", "required": True},
                "markdown": {"type": "string", "required": True},
            },
        }
    )
    codes = _codes(rep)
    assert "missing_change_contract" not in codes
    assert "sop_missing_goal" not in codes
    assert "sop_missing_checklist" not in codes
    assert "missing_negative_triggers" not in codes
    assert "triggers_too_few" not in codes


def test_coding_handler_still_needs_change_contract():
    rep = lint_skill(
        {
            "id": "code_fix",
            "name": "code_fix",
            "description": "修改代码并验收回滚",
            "category": "coding",
            "metadata": {
                "skill_kind": "executable",
                "execution_type": "handler",
                "permissions": ["tool:workspace_fs_write"],
                "trigger_conditions": ["修 bug", "改代码", "refactor", "补测试", "回滚", "验收"],
            },
            "input_schema": {"task": {"type": "string"}},
            "output_schema": {"markdown": {"type": "string", "required": True}},
        }
    )
    assert "missing_change_contract" in _codes(rep)


def test_prompt_write_effects_lint_unrealized_side_effect():
    rep = lint_skill(
        {
            "id": "upload_like",
            "name": "upload_like",
            "description": "上传文件到对象存储",
            "category": "execution",
            "execution_type": "prompt",
            "effects": [{"type": "write", "resources": ["filesystem:~"]}],
            "metadata": {"execution_type": "prompt", "permissions": ["fs:write"]},
            "input_schema": {"file": {"type": "file"}},
            "output_schema": {"markdown": {"type": "string", "required": True}},
        }
    )
    assert "unrealized_side_effect" in _codes(rep)


def test_generation_handler_skips_change_contract():
    """PPT 等 generation+handler 不应被要求 coding 输出契约。"""
    rep = lint_skill(
        {
            "id": "ppt_like",
            "name": "ppt_like",
            "description": "根据大纲生成演示文稿",
            "category": "generation",
            "type": "generation",
            "metadata": {
                "skill_kind": "executable",
                "execution_type": "handler",
                "permissions": ["tool:workspace_fs_write"],
                "trigger_conditions": ["生成PPT", "做演示", "大纲转幻灯片", "pptx", "模版填充", "演示文稿"],
                "skip_when": "已有成品 pptx",
                "keywords": {"objects": ["PPT", "大纲"], "actions": ["生成", "填充"]},
            },
            "input_schema": {"outline": {"type": "string"}},
            "output_schema": {"markdown": {"type": "string", "required": True}},
        }
    )
    assert "missing_change_contract" not in _codes(rep)
