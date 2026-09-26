"""Unit tests for LLM execution-examples JSON extraction (no LLM)."""

from core.apps.skills.service.skill_execution_examples_llm import _extract_json_array


def test_extract_json_array_plain():
    raw = '[{"title": "长文摘要", "content": {"text": "段落一\\n段落二"}}]'
    out = _extract_json_array(raw)
    assert len(out) == 1
    assert out[0]["title"] == "长文摘要"
    assert "段落一" in out[0]["content"]


def test_extract_json_array_fenced_and_rejects_legacy():
    raw = """```json
[
  {"title": "坏", "content": "请按本能力说明完成一次冒烟测试"},
  {"title": "好", "content": "【周报】\\n一、进展\\n二、风险\\n请输出三点摘要"}
]
```"""
    out = _extract_json_array(raw)
    assert len(out) == 1
    assert out[0]["title"] == "好"
