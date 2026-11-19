"""FDE conformance-pack Core HTTP 薄路由接线。"""
from __future__ import annotations

import asyncio

import core.api.core_facade as facade

from apps.fde.api import conformance_pack_routes as routes


def test_core_ready_route_delegates_to_facade(monkeypatch):
    called = {}

    def _fake(**kwargs):
        called.update(kwargs)
        return {"core_ready": True, "certified": False, "pilot_certified": False}

    monkeypatch.setattr(facade, "evaluate_core_ready_gate", _fake)
    out = asyncio.run(
        routes.evaluate_core_ready_gate_route(pilot_domain="x", catalog_path=None)
    )
    assert out["core_ready"] is True
    assert out["certified"] is False
    assert called.get("pilot_domain") == "x"


def test_pilot_core_cert_route_omits_badge_without_path(monkeypatch):
    def _fake(**kwargs):
        return {
            "pilot_certified": False,
            "certified": False,
            "issues": ["approval_record_path_required"],
            "approval_record_path": kwargs.get("approval_record_path"),
        }

    monkeypatch.setattr(facade, "evaluate_pilot_core_certification", _fake)
    out = asyncio.run(routes.evaluate_pilot_core_certification_route())
    assert out["pilot_certified"] is False
    assert out["certified"] is False
