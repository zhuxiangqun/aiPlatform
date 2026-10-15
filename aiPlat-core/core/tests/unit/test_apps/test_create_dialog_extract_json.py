"""create_dialog extract_json_object → canonical parse_json / extract_json_safe."""

from __future__ import annotations

from core.apps.common.create_dialog_utils import extract_json_object


def test_plain_object():
    assert extract_json_object('{"next":"draft","reply":"ok"}')["next"] == "draft"


def test_fenced_and_trailing_commentary():
    raw = """这里是说明：
```json
{"next": "clarify", "questions": ["名称是什么？"]}
```
以上为 JSON。"""
    out = extract_json_object(raw)
    assert out["next"] == "clarify"
    assert out["questions"] == ["名称是什么？"]


def test_array_or_empty_returns_empty_dict():
    assert extract_json_object("[1,2]") == {}
    assert extract_json_object("") == {}
    assert extract_json_object("not json") == {}
