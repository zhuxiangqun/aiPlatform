"""Factory confirm: ActionRegistry L1 + K1 signal + Path A proposal enqueue."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_confirm_route_enqueues_proposal_after_k1():
    """HTTP confirm keeps K1 (no live YAML) but also returns proposal_id for ③."""
    from apps.fde.api import extraction_routes as routes

    mock_reg = MagicMock()
    mock_reg.execute = AsyncMock(
        return_value={
            "status": "executed",
            "result": {
                "ok": True,
                "status": "confirmed",
                "signal_id": "sig-x",
                "trace_id": "tr-x",
                "trace_origin": "extraction_confirm",
                "extract_actor": "t",
                "entity_ids": ["e1"],
                "yaml_unchanged": True,
                "wrote_live_yaml": False,
                "domain_id": "lock-service",
                "idempotent": False,
                "proposal_id": "prop_lock-service_test",
                "graph_write": {"created_entities": ["张三"], "relations": []},
            },
        }
    )
    req = MagicMock()
    req.headers = {"X-AIPLAT-SCOPES": "kb:write"}

    with patch("core.api.core_facade.get_action_registry", return_value=mock_reg), patch(
        "apps.fde.api.extraction_routes.resolve_request_role", return_value="factory"
    ):
        out = await routes.confirm_extraction(req, "ext-1", actor="factory")

    assert out["status"] == "confirmed"
    assert out["signal_id"] == "sig-x"
    assert out["proposal_id"] == "prop_lock-service_test"
    assert out["wrote_live_yaml"] is False
    assert out.get("graph_write", {}).get("created_entities") == ["张三"]
    mock_reg.execute.assert_awaited_once()


def test_cross_domain_name_score_without_primary_keys():
    from core.harness.knowledge_pipeline.resolver import CrossDomainResolver

    r = CrossDomainResolver()
    score, strat, _ev = r._compute_match(
        {"name": "TECH-OCS-1", "id": "TECH-OCS-1"},
        {"name": "TECH-SD-1", "id": "TECH-SD-1"},
        {"primary": "customer_name||site_id", "secondary": "name", "min_confidence": 0.7},
        {"domain": "lock-service"},
        {"domain": "service-domain"},
    )
    assert strat == "name"
    assert score >= 0.7
