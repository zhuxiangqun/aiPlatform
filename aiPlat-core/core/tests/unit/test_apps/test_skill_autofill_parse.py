"""Unit tests for skill autofill parse + enrich (no LLM)."""

from core.apps.skills.service.skill_autofill import (
    _completeness_gaps,
    _enrich_draft,
    _parse_skill_md,
)


def test_parse_skill_md_frontmatter_and_sop():
    text = """---
name: ppt_generation
display_name: PPT生成
description: >-
  根据大纲生成 pptx
category: generation
skill_kind: executable
permissions:
  - llm:generate
  - tool:workspace_fs_write
trigger_conditions:
  - 生成PPT
  - 做一份PPT
  - 根据大纲做PPT
input_schema:
  outline:
    type: object
    required: true
    description: 结构化大纲
output_schema:
  pptx_path:
    type: string
    required: true
    description: 输出路径
  markdown:
    type: string
    required: true
    description: 摘要
---

# 概述

## 工作流程（SOP）
1. 校验输入
2. 填充模版
3. 写出 pptx
"""
    fm, sop = _parse_skill_md(text)
    assert fm["name"] == "ppt_generation"
    assert fm["skill_kind"] == "executable"
    assert "workspace_fs_write" in str(fm.get("permissions"))
    assert "校验输入" in sop
    assert "待补充" not in sop


def test_parse_skill_md_inside_fence():
    text = """好的，这是草稿：

```yaml
---
name: report_writer
display_name: 报告撰写
description: 写报告
category: generation
skill_kind: rule
permissions:
  - llm:generate
trigger_conditions:
  - 写报告
  - 生成报告
  - 帮我写报告
input_schema:
  topic:
    type: string
    required: true
    description: 主题
output_schema:
  markdown:
    type: string
    required: true
    description: 正文
---

# SOP

1. 收集主题
2. 生成正文
```
"""
    fm, sop = _parse_skill_md(text)
    assert fm.get("name") == "report_writer"
    assert "收集主题" in sop


def test_enrich_file_write_forces_executable_and_perms():
    draft = {
        "name": "ppt_generator",
        "display_name": "PPT 生成器",
        "description": (
            "应具备：1) 输入：结构化大纲（标题/章节/每页要点）+ 可选模版路径(.pptx/.potx)或默认模版名；"
            "2) 按模版母版/占位符逐页填充，控制单页字数；"
            "3) 输出：生成的 .pptx 文件路径 + 页数/所用模版等元信息；"
            "4) 不联网找素材、不编造用户未提供的事实。"
        ),
        "category": "general",
        "skill_kind": "rule",
        "permissions": [],
        "trigger_conditions": [],
        "input_schema": {},
        "output_schema": {},
        "config": {},
        "sop": "",
    }
    out = _enrich_draft(
        draft,
        seed_name="ppt_generator",
        seed_desc=draft["description"],
    )
    assert out["skill_kind"] == "executable"
    assert "llm:generate" in out["permissions"]
    assert any("workspace_fs_write" in p for p in out["permissions"])
    assert not any("websearch" in p for p in out["permissions"])
    assert out["config"].get("require_confirmation") is True
    assert out["category"] == "generation"
    assert "outline" in out["input_schema"]
    assert "template_path" in out["input_schema"]
    assert "pptx_path" in out["output_schema"]
    assert "markdown" in out["output_schema"]
    assert "page_count" in out["output_schema"]
    assert len(out["trigger_conditions"]) >= 3
    assert "大纲" in out["sop"] or "pptx" in out["sop"].lower() or "落盘" in out["sop"] or "输入" in out["sop"]
    gaps = _completeness_gaps(out, out["description"])
    assert gaps == []


def test_synthesize_io_from_description_keywords():
    from core.apps.skills.service.skill_autofill import _synthesize_io_schemas, _synthesize_triggers

    inn, out = _synthesize_io_schemas(
        "输入结构化大纲与模版路径.pptx，输出 pptx 路径与页数，不联网",
        file_write=True,
    )
    assert "outline" in inn
    assert "pptx_path" in out
    triggers = _synthesize_triggers("PPT 生成器", "ppt_generator", "根据大纲生成PPT")
    assert len(triggers) >= 3
    assert any("PPT" in t for t in triggers)
