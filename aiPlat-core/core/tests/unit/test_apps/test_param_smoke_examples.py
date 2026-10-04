"""Tool/MCP/Workflow param smoke examples cover happy + boundary + complex."""

from __future__ import annotations

import json

from core.management.execution_examples import (
    build_agent_task_examples,
    build_boundary_payload,
    build_examples_from_input_schema,
    build_param_smoke_examples,
    build_sample_payload,
    build_workflow_start_examples,
    example_content_is_thin,
    examples_are_generic,
    flatten_json_schema,
    sample_value_for_field,
    workflow_example_to_start_inputs,
)


def test_param_smoke_has_happy_boundary_complex():
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索词"},
            "url": {"type": "string"},
            "limit": {"type": "integer"},
            "enable_cache": {"type": "boolean"},
        },
        "required": ["query", "url"],
    }
    ex = build_param_smoke_examples(schema, asset_id="web_search", asset_name="WebSearch", asset_kind="tool")
    titles = "\n".join(e["title"] for e in ex)
    assert "主路径" in titles
    assert "边界" in titles
    assert "复杂" in titles or "全量" in titles

    boundary = next(e for e in ex if "边界" in e["title"])
    payload = json.loads(boundary["content"])
    assert payload.get("url", "").startswith("http://127.0.0.1")
    assert payload.get("limit") in (0, None) or "limit" not in payload or payload["limit"] == 0


def test_build_examples_from_schema_uses_param_smoke_for_generic():
    schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "command": {"type": "string"}},
        "required": ["path"],
    }
    ex = build_examples_from_input_schema(schema, skill_id="shell", skill_name="Shell")
    assert any("边界" in e["title"] for e in ex)
    assert any("主路径" in e["title"] or "必填" in e["title"] for e in ex)


def test_workflow_start_examples_and_parse():
    ex = build_workflow_start_examples(
        [{"key": "message"}, {"key": "query"}],
        workflow_name="巡检流",
    )
    assert len(ex) >= 3
    assert any("边界" in e["title"] for e in ex)
    rows = workflow_example_to_start_inputs(ex[0]["content"])
    keys = {r["key"] for r in rows}
    assert "message" in keys and "query" in keys
    assert any(len(r["value"]) >= 40 for r in rows)


def test_file_and_byte_fields_are_not_description_placeholders():
    schema = {
        "file": {
            "type": "file",
            "required": True,
            "description": "本地视频文件，支持MP4/MOV/AVI/MKV",
        },
        "file_size": {
            "type": "integer",
            "required": True,
            "description": "文件大小（字节），不超过2GB",
        },
    }
    file_v = sample_value_for_field("file", schema["file"])
    size_v = sample_value_for_field("file_size", schema["file_size"])
    assert isinstance(file_v, str) and file_v.endswith(".mp4")
    assert "示例" not in file_v
    assert "本地视频" not in file_v
    assert isinstance(size_v, int)
    assert 1024 <= size_v <= 8 * 1024 * 1024
    assert size_v <= 2 * 1024 ** 3

    payload = build_sample_payload(schema, include_optional=False)
    assert payload["file"].endswith(".mp4")
    assert payload["file_size"] == size_v

    boundary = build_boundary_payload(flatten_json_schema(schema))
    assert "__aiplat_missing_path__" in str(boundary["file"])
    assert boundary["file_size"] == 2 * 1024 ** 3 + 1

    happy = json.loads(
        build_examples_from_input_schema(
            schema, skill_id="upload_video", skill_name="upload_video",
        )[0]["content"]
    )
    assert "示例" not in str(happy.get("file", ""))
    assert happy["file_size"] != 3
    assert example_content_is_thin(json.dumps(payload, ensure_ascii=False)) is False
    assert example_content_is_thin(
        json.dumps(
            {"file": "示例：本地视频文件，支持MP4/MOV/AVI/MKV", "file_size": 3},
            ensure_ascii=False,
        )
    ) is True
    assert examples_are_generic(
        [{"title": "upload_video（主路径·必填）", "content": json.dumps(
            {"file": "示例: 本地视频文件，支持MP4/MOV/AVI/MKV", "file_size": 3},
            ensure_ascii=False,
        )}],
        schema,
    )


def test_sanitize_rewrites_description_copied_values():
    from core.management.execution_examples import sanitize_execution_examples

    schema = {
        "file": {
            "type": "file",
            "required": True,
            "description": "本地视频文件，支持MP4/MOV/AVI/MKV",
        },
        "file_size": {
            "type": "integer",
            "required": True,
            "description": "文件大小（字节），不超过2GB",
        },
    }
    out = sanitize_execution_examples(
        [{
            "title": "upload_video（主路径·必填）",
            "content": json.dumps(
                {"file": "示例: 本地视频文件，支持MP4/MOV/AVI/MKV", "file_size": 3},
                ensure_ascii=False,
            ),
        }],
        schema,
        skill_hint="upload_video",
    )
    obj = json.loads(out[0]["content"])
    assert obj["file"].endswith(".mp4")
    assert "示例" not in obj["file"]
    assert int(obj["file_size"]) >= 1024


def test_accept_llm_does_not_launder_copied_descriptions():
    from core.management.execution_examples import accept_llm_execution_examples

    schema = {
        "file": {"type": "file", "required": True, "description": "本地视频文件，支持MP4"},
        "file_size": {"type": "integer", "required": True, "description": "字节不超过2GB"},
    }
    poisoned = [
        {
            "title": "主路径",
            "content": json.dumps(
                {"file": "示例: 本地视频文件，支持MP4", "file_size": 3},
                ensure_ascii=False,
            ),
        },
        {
            "title": "边界",
            "content": json.dumps({"file": "本地视频文件，支持MP4", "file_size": 8}, ensure_ascii=False),
        },
    ]
    assert accept_llm_execution_examples(poisoned, schema, skill_hint="upload_video") == []
    good = [
        {"title": "主", "content": json.dumps({"file": "/tmp/sample.mp4", "file_size": 1048576})},
        {"title": "边", "content": json.dumps({"file": "/tmp/bad.txt", "file_size": 0})},
    ]
    kept = accept_llm_execution_examples(good, schema, skill_hint="upload_video")
    assert len(kept) >= 2
    assert "/tmp/" in kept[0]["content"]


def test_resolve_schema_from_yaml_input_list():
    from core.management.execution_examples import resolve_skill_example_schema

    fm = {
        "input": [
            {"name": "file", "type": "file", "required": True, "description": "视频"},
            {"name": "file_size", "type": "integer", "required": True},
        ]
    }
    got = resolve_skill_example_schema(live={}, frontmatter=fm)
    assert "file" in got and got["file"]["type"] == "file"
    exec_first = resolve_skill_example_schema(
        live={"x": {"type": "string"}},
        frontmatter={"execution_input_schema": {"q": {"type": "string"}}, "input_schema": {"a": {}}},
    )
    assert "q" in exec_first and "x" not in exec_first


def test_llm_schema_gate_requires_typed_required_fields():
    from core.management.execution_examples import (
        llm_examples_pass_schema_gate,
        sop_excerpt_from_markdown,
    )

    schema = {
        "file": {"type": "file", "required": True, "description": "本地视频"},
        "file_size": {"type": "integer", "required": True, "description": "字节不超过2GB"},
    }
    bad = [
        {"title": "a", "content": json.dumps({"file": "本地视频", "file_size": 3})},
        {"title": "b", "content": "请测试一下上传"},
    ]
    assert llm_examples_pass_schema_gate(bad, schema) is False
    good = [
        {"title": "主", "content": json.dumps({"file": "/tmp/sample.mp4", "file_size": 1048576})},
        {"title": "边", "content": json.dumps({"file": "/tmp/__aiplat_missing_path__.txt", "file_size": 0})},
    ]
    assert llm_examples_pass_schema_gate(good, schema) is True
    md = "---\nname: x\n---\n# 流程\n1. 验证格式\n"
    assert "验证格式" in sop_excerpt_from_markdown(md)


def test_generic_agent_fallback_is_rich():
    ex = build_agent_task_examples(
        display_name="通用助手",
        description="协助日常任务",
        skill_ids=[],
        tool_ids=[],
    )
    blob = "\n".join(e["content"] for e in ex)
    assert "按本 Agent 的职责做一次冒烟验证" not in blob
    assert "简单冒烟" in blob or "可验收" in blob
    assert "复杂冒烟" in blob or "多约束" in blob
    assert not examples_are_generic(ex)
