"""Factory confirm: K1 signal + Path A proposal enqueue."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_confirm_route_enqueues_proposal_after_k1():
    """HTTP confirm keeps K1 (no live YAML) but also returns proposal_id for ③."""
    from apps.fde.api import extraction_routes as routes

    k1 = {
        "ok": True,
        "signal_id": "sig-x",
        "trace_id": "tr-x",
        "trace_origin": "extraction_confirm",
        "extract_actor": "t",
        "entity_ids": ["e1"],
        "yaml_unchanged": True,
        "domain_id": "lock-service",
        "idempotent": False,
    }
    row = {
        "extraction_id": "ext-1",
        "domain_id": "lock-service",
        "source_doc": "doc",
        "entities_json": '[{"name":"张三","class_type":"安装师傅"}]',
    }

    with patch(
        "core.api.core_facade.k1_confirm_extraction",
        new=AsyncMock(return_value=k1),
    ), patch.object(routes._store, "initialize", new=AsyncMock()), patch.object(
        routes._store, "get_row", new=AsyncMock(return_value=row)
    ), patch.object(
        routes._store,
        "_enqueue_ontology_proposal",
        new=AsyncMock(return_value="prop_lock-service_test"),
    ), patch(
        "core.harness.knowledge_pipeline.extractor.write_extraction_to_graph_index",
        return_value={"created_entities": ["e1"], "relations": []},
    ):
        out = await routes.confirm_extraction("ext-1", actor="factory")

    assert out["status"] == "confirmed"
    assert out["signal_id"] == "sig-x"
    assert out["proposal_id"] == "prop_lock-service_test"
    assert out["wrote_live_yaml"] is False
    assert out.get("graph_write", {}).get("created_entities") == ["e1"]


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
