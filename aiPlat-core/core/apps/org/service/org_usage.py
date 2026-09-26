"""Phase C4 — usage ledger (W11).

Append-only, idempotent, replayable. Writes are best-effort and must not
block OrgRun. No prices, invoices, or SKUs.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def ledger_path() -> Path:
    return _home() / "org" / "usage.jsonl"


def _idem_key(trace_id: str, kind: str, ref: str) -> str:
    return f"{trace_id}:{kind}:{ref or '-'}"


def events_from_run(
    run: Dict[str, Any],
    *,
    channel: str = "",
    tenant_id: str = "",
    actor_id: str = "",
    tokens: int = 0,
) -> List[Dict[str, Any]]:
    run_id = str(run.get("run_id") or "")
    trace = str(run.get("trace_id") or run_id)
    base = {
        "ts": time.time(),
        "trace_id": trace,
        "run_id": run_id,
        "goal_id": str(run.get("goal_id") or ""),
        "domain_id": str(run.get("domain_id") or ""),
        "week_label": str(run.get("week_label") or ""),
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "channel": channel,
        "billing": None,
    }
    events = [
        {
            **base,
            "kind": "run",
            "ref": run_id,
            "tokens": 0,
            "idempotency_key": _idem_key(trace, "run", run_id),
        }
    ]
    for step in run.get("steps") or []:
        if not isinstance(step, dict):
            continue
        name = str(step.get("step") or "")
        if name not in ("triage_gate", "fetch"):
            continue
        events.append(
            {
                **base,
                "kind": "action",
                "ref": name,
                "action_id": name,
                "tokens": 0,
                "idempotency_key": _idem_key(trace, "action", name),
            }
        )
    tok = int(tokens or run.get("token_usage") or 0)
    events.append(
        {
            **base,
            "kind": "llm",
            "ref": "llm",
            "tokens": tok,
            "idempotency_key": _idem_key(trace, "llm", "llm"),
        }
    )
    for ev in events:
        ev.pop("price", None)
        ev["billing"] = None
    return events


def append_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                seen.add(json.loads(line).get("idempotency_key"))
            except Exception:
                continue
    written = 0
    with path.open("a", encoding="utf-8") as fh:
        for ev in events:
            key = ev.get("idempotency_key")
            if not key or key in seen:
                continue
            seen.add(key)
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
            written += 1
    return {"status": "ok", "written": written, "skipped": len(events) - written}


def schedule_run_usage(run: Dict[str, Any], **meta: Any) -> Dict[str, Any]:
    """Queue ledger write. Never raises to the OrgRun caller."""
    events = events_from_run(
        run,
        channel=str(meta.get("channel") or ""),
        tenant_id=str(meta.get("tenant_id") or ""),
        actor_id=str(meta.get("actor_id") or ""),
        tokens=int(meta.get("tokens") or 0),
    )

    def _write() -> None:
        try:
            append_events(events)
        except Exception:
            logger.warning("usage ledger write failed", exc_info=True)

    try:
        threading.Thread(target=_write, name="org-usage", daemon=True).start()
    except Exception:
        logger.warning("usage ledger thread failed", exc_info=True)
        return {"status": "skipped", "billing": None}
    return {"status": "queued", "billing": None, "events": len(events)}


def weekly_usage(domain_id: str = "", week: str = "") -> Dict[str, Any]:
    """Replay ledger into a weekly rollup. No prices."""
    path = ledger_path()
    rows: List[Dict[str, Any]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    did = (domain_id or "").strip()
    wk = (week or "").strip()
    picked = []
    for row in rows:
        if did and str(row.get("domain_id") or "") != did:
            continue
        if wk and str(row.get("week_label") or "") != wk:
            continue
        picked.append(row)
    runs = {r.get("run_id") for r in picked if r.get("kind") == "run" and r.get("run_id")}
    actions = [r for r in picked if r.get("kind") == "action"]
    tokens = sum(int(r.get("tokens") or 0) for r in picked if r.get("kind") == "llm")
    by_channel: Dict[str, int] = {}
    for r in picked:
        if r.get("kind") != "run":
            continue
        ch = str(r.get("channel") or "direct")
        by_channel[ch] = by_channel.get(ch, 0) + 1
    return {
        "status": "ok",
        "domain_id": did,
        "week": wk,
        "run_count": len(runs),
        "action_count": len(actions),
        "token_total": tokens,
        "by_channel": by_channel,
        "event_count": len(picked),
        "billing": None,
        "authority_note": "usage ledger only; no price list, invoice, or SKU",
    }
