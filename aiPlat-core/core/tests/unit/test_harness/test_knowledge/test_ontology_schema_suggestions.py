"""Table/CSV header → Path A proposal draft (never apply, never GraphIndex)."""

from __future__ import annotations

import pytest

from core.apps.fde.service.ontology_code_suggestions import (
    suggest_classes_from_table_schema,
    suggest_classes_from_table_schema_async,
)


@pytest.fixture()
def aiplat_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    return home


def test_table_name_and_columns_to_edge_class():
    out = suggest_classes_from_table_schema(
        "it-ops",
        table_name="alert_events",
        columns=["id", "service_name", "severity", "state"],
        enqueue=False,
    )
    assert out["auto_apply"] is False
    assert out["writes_graph"] is False
    assert out["suggestions"]
    s = out["suggestions"][0]
    assert s["name"] == "AlertEvent"
    assert s["tier"] == "edge"
    assert "service_name" in s["required_fields"]
    assert "id" not in s["required_fields"]


def test_csv_text_infers_columns():
    csv = "id,host_name,cpu_pct\n1,web-1,90\n"
    out = suggest_classes_from_table_schema(
        "it-ops",
        table_name="host_metrics",
        csv_text=csv,
        enqueue=False,
    )
    s = out["suggestions"][0]
    assert s["name"] == "HostMetric"
    assert "host_name" in s["required_fields"]
    assert s["sample_row_count"] == 1


@pytest.mark.asyncio
async def test_enqueue_draft_no_auto_apply(aiplat_home):
    onto = aiplat_home / "ontologies"
    onto.mkdir(parents=True)
    (onto / "schema-d.yaml").write_text(
        "domain_id: schema-d\nclasses:\n  - name: Base\n    label: Base\n",
        encoding="utf-8",
    )
    out = await suggest_classes_from_table_schema_async(
        "schema-d",
        table_name="orders",
        columns=["order_id", "amount", "status"],
        enqueue=True,
        author="test",
    )
    assert out["auto_apply"] is False
    assert out["writes_graph"] is False
    assert out.get("proposal_id")
    assert out.get("enqueue_status") in ("draft", "local_draft")
    # live yaml unchanged (no apply)
    live = (onto / "schema-d.yaml").read_text(encoding="utf-8")
    assert "Order" not in live or "classes:\n  - name: Base" in live


def test_facade_symbol_present():
    text = (
        __import__("pathlib").Path(__file__).resolve().parents[4]
        / "api"
        / "core_facade.py"
    ).read_text(encoding="utf-8")
    assert "async def suggest_ontology_from_table_schema" in text
