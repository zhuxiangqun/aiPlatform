"""Eval HTTP response_model must not strip eval_protocol / list payloads."""
from __future__ import annotations

from apps.common_schemas import ItemResponse, ListResponse, StatusResponse


def test_status_response_keeps_eval_protocol_and_report():
    """StatusResponse 须保留 artifact_id / report / eval_protocol（extra=allow）。"""
    raw = {
        "status": "ok",
        "artifact_id": "a1",
        "report": {"pass": True, "score": 0.9},
        "eval_protocol": {"schema_version": "eval.protocol.v0"},
    }
    out = StatusResponse.model_validate(raw).model_dump()
    assert out["status"] == "ok"
    assert out["artifact_id"] == "a1"
    assert out["report"]["pass"] is True
    assert out["eval_protocol"]["schema_version"] == "eval.protocol.v0"


def test_item_response_keeps_nested_eval_protocol():
    """ItemResponse 载荷在 data 内时须完整保留协议字段。"""
    raw = {
        "data": {
            "status": "ok",
            "item": {"id": "ev1"},
            "eval_protocol": {"schema_version": "eval.protocol.v0"},
        }
    }
    out = ItemResponse.model_validate(raw).model_dump()
    assert out["data"]["item"]["id"] == "ev1"
    assert out["data"]["eval_protocol"]["schema_version"] == "eval.protocol.v0"


def test_store_list_shape_via_item_response():
    """store 列表端点改用 ItemResponse 后，data.items 不得被剥空。"""
    raw = {"data": {"items": [{"id": "set-1", "name": "demo"}], "total": 1}}
    out = ItemResponse.model_validate(raw).model_dump()
    assert out["data"]["total"] == 1
    assert out["data"]["items"][0]["id"] == "set-1"


def test_list_response_still_accepts_top_level_items():
    """ListResponse 顶层 items/total 仍可用（其它模块）。"""
    raw = {"items": [{"id": "x"}], "total": 1, "cursor": "n"}
    out = ListResponse.model_validate(raw).model_dump()
    assert out["items"][0]["id"] == "x"
    assert out["total"] == 1
    assert out.get("cursor") == "n"
