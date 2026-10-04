"""Generic (not skill-id-specific) rich execution examples."""

from __future__ import annotations

import json

from core.management.execution_examples import (
    build_examples_from_input_schema,
    example_content_is_thin,
    examples_are_generic,
    sample_value_for_field,
)


def test_any_skill_with_narrative_field_gets_simple_complex_pair():
    ex = build_examples_from_input_schema(
        {"user_requirement": {"type": "string", "required": True, "description": "用户的原始需求描述"}},
        skill_id="some_custom_analyzer",
        skill_name="自定义分析",
    )
    assert len(ex) == 2
    assert "简单" in ex[0]["title"]
    assert "复杂" in ex[1]["title"]
    assert not examples_are_generic(ex)
    for e in ex:
        obj = json.loads(e["content"])
        assert not example_content_is_thin(obj["user_requirement"])


def test_requirement_analysis_uses_prd_domain_scenarios():
    ex = build_examples_from_input_schema(
        {"user_requirement": {"type": "string", "required": True}},
        skill_id="requirement_analysis",
        skill_name="需求分析",
    )
    assert len(ex) == 2
    blob = "\n".join(e["content"] for e in ex)
    assert "不上公网" in blob or "不能传到公网" in blob
    assert "FR" in blob or "可验证" in blob
    assert "搜索" in blob or "关键词" in blob
    assert not examples_are_generic(ex)


def test_summarize_like_message_field_stays_rich():
    ex = build_examples_from_input_schema(
        {"text": {"type": "string", "required": True}},
        skill_id="summarize",
        skill_name="摘要",
    )
    assert len(ex) >= 2
    blob = "\n".join(e["content"] for e in ex)
    assert "周报" in blob or "进展" in blob or "加严验收" in blob


def test_thin_llm_one_liner_is_generic():
    thin = [
        {
            "title": "简单示例",
            "content": json.dumps({"user_requirement": "用户希望实现搜索功能。"}, ensure_ascii=False),
        },
        {
            "title": "复杂示例",
            "content": json.dumps({"user_requirement": "再加一个智能客服。"}, ensure_ascii=False),
        },
    ]
    assert examples_are_generic(thin) is True


def test_sample_narrative_field_not_desc_prefix():
    v = sample_value_for_field(
        "user_requirement",
        {"type": "string", "description": "用户的原始需求描述"},
        skill_hint="any_skill",
    )
    assert isinstance(v, str) and len(v) > 80
    assert not str(v).startswith("示例：")
