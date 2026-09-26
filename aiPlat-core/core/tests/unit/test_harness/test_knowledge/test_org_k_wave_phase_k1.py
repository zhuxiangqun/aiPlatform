"""Phase K1 — extraction confirm emits signal; live YAML and edges stay untouched."""

from __future__ import annotations

import json

import pytest

from core.apps.fde.service.k_wave_signal import confirm_extraction_k1, live_yaml_hash, signals_path


class _FakePendingStore:
    def __init__(self, rows):
        self._rows = {r["extraction_id"]: dict(r) for r in rows}
        self.confirm_calls = []

    async def get_row(self, extraction_id: str):
        return self._rows.get(extraction_id)

    async def confirm(self, extraction_id: str, *, enqueue_proposal: bool = True, write_graph: bool = True):
        self.confirm_calls.append(
            {
                "extraction_id": extraction_id,
                "enqueue_proposal": enqueue_proposal,
                "write_graph": write_graph,
            }
        )
        row = self._rows.get(extraction_id)
        if not row:
            return {"ok": False, "reason": "not_found", "extraction_id": extraction_id}
        row["status"] = "confirmed"
        return {
            "ok": True,
            "extraction_id": extraction_id,
            "domain_id": row.get("domain_id"),
            "proposal_id": None,
            "graph_write": None,
        }


@pytest.mark.asyncio
async def test_k1_confirm_emits_trace_without_yaml_or_edge(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    onto = tmp_path / "ontologies"
    onto.mkdir()
    yaml_body = (
        "name: it-ops\n"
        "namespace: http://aiplat.local/ontology/it-ops/\n"
        "classes:\n  Alert:\n    label: 告警\n"
    )
    (onto / "it-ops.yaml").write_text(yaml_body, encoding="utf-8")
    before = live_yaml_hash("it-ops")
    assert before

    store = _FakePendingStore(
        [
            {
                "extraction_id": "ext-k1-1",
                "domain_id": "it-ops",
                "status": "pending",
                "entities_json": json.dumps(
                    [{"name": "告警A", "class_type": "事件", "entity_id": "ent-a"}],
                    ensure_ascii=False,
                ),
            }
        ]
    )

    first = await confirm_extraction_k1("ext-k1-1", actor="analyst-a", store=store)
    assert first["ok"] is True
    assert first["idempotent"] is False
    assert first["trace_origin"] == "extraction_confirm"
    assert first["trace_id"]
    assert first["signal_id"].startswith("sig-")
    assert first["entity_ids"] == ["ent-a"]
    assert first["extract_actor"] == "analyst-a"
    assert first["yaml_unchanged"] is True
    assert first["wrote_live_yaml"] is False
    assert first["wrote_cross_domain_edge"] is False
    assert store.confirm_calls == [
        {"extraction_id": "ext-k1-1", "enqueue_proposal": False, "write_graph": False}
    ]
    assert live_yaml_hash("it-ops") == before
    assert (onto / "it-ops.yaml").read_text(encoding="utf-8") == yaml_body
    assert len(signals_path().read_text(encoding="utf-8").strip().splitlines()) == 1

    second = await confirm_extraction_k1("ext-k1-1", actor="analyst-b", store=store)
    assert second["ok"] is True
    assert second["idempotent"] is True
    assert second["trace_id"] == first["trace_id"]
    assert live_yaml_hash("it-ops") == before
    assert len(signals_path().read_text(encoding="utf-8").strip().splitlines()) == 1
    assert len(store.confirm_calls) == 1


@pytest.mark.asyncio
async def test_k1_missing_extraction(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    store = _FakePendingStore([])
    out = await confirm_extraction_k1("missing", actor="a", store=store)
    assert out["ok"] is False
    assert out["reason"] == "not_found"
    assert not signals_path().is_file()
