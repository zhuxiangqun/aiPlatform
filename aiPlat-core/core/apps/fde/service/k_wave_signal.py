"""Phase K1 — extraction confirm emits a change signal. It does not write live YAML.

GraphIndex and proposal enqueue stay on PendingExtractionStore.confirm for
callers that pass those flags. This path always turns them off.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def signals_path() -> Path:
    return _home() / "k_wave" / "signals.jsonl"


def live_yaml_path(domain_id: str) -> Path:
    did = (domain_id or "").strip() or "default"
    return _home() / "ontologies" / f"{did}.yaml"


def live_yaml_hash(domain_id: str) -> str:
    path = live_yaml_path(domain_id)
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_signals() -> List[Dict[str, Any]]:
    path = signals_path()
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _entity_ids(entities: Any) -> List[str]:
    if isinstance(entities, str):
        try:
            entities = json.loads(entities)
        except Exception:
            return []
    if not isinstance(entities, list):
        return []
    out: List[str] = []
    for ent in entities:
        if isinstance(ent, dict):
            ref = str(ent.get("entity_id") or ent.get("name") or "").strip()
        else:
            ref = str(ent or "").strip()
        if ref:
            out.append(ref)
    return out


def _append_signal(event: Dict[str, Any]) -> None:
    path = signals_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


async def _load_row(store: Any, extraction_id: str) -> Optional[Dict[str, Any]]:
    getter = getattr(store, "get_row", None)
    if callable(getter):
        row = await getter(extraction_id)
        return dict(row) if isinstance(row, dict) else None
    import aiosqlite

    async with aiosqlite.connect(store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pending_extractions WHERE extraction_id=?",
            (extraction_id,),
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def confirm_extraction_k1(
    extraction_id: str,
    *,
    actor: str = "",
    store: Optional[Any] = None,
) -> Dict[str, Any]:
    """Confirm one pending extraction into a K1 signal. No live YAML write, no edge write."""
    eid = (extraction_id or "").strip()
    if not eid:
        return {"ok": False, "reason": "need_extraction_id"}

    for row in _read_signals():
        if row.get("extraction_id") == eid and row.get("status") == "confirmed":
            return {**row, "ok": True, "idempotent": True}

    if store is None:
        from core.harness.knowledge_pipeline.extractor import PendingExtractionStore

        store = PendingExtractionStore()
        await store.initialize()

    pending = await _load_row(store, eid)
    if not pending:
        return {"ok": False, "extraction_id": eid, "reason": "not_found"}
    domain_id = str(pending.get("domain_id") or "default")
    before = live_yaml_hash(domain_id)

    receipt = await store.confirm(eid, enqueue_proposal=False, write_graph=False)
    if not receipt.get("ok"):
        return receipt

    after = live_yaml_hash(domain_id)
    if before != after:
        logger.error("K1 confirm changed live yaml for %s", domain_id)
        return {
            "ok": False,
            "extraction_id": eid,
            "domain_id": domain_id,
            "reason": "live_yaml_changed",
            "yaml_unchanged": False,
        }

    signal = {
        "signal_id": f"sig-{uuid.uuid4().hex[:12]}",
        "trace_id": uuid.uuid4().hex,
        "trace_origin": "extraction_confirm",
        "extraction_id": eid,
        "domain_id": domain_id,
        "source": "extraction",
        "entity_ids": _entity_ids(pending.get("entities_json")),
        "status": "confirmed",
        "extract_actor": (actor or "").strip(),
        "yaml_hash": after,
        "yaml_unchanged": True,
        "wrote_live_yaml": False,
        "wrote_cross_domain_edge": False,
        "authority_note": "K1 signal only; not TBox; not a cross-domain edge",
    }
    _append_signal(signal)
    return {"ok": True, "idempotent": False, **signal}
