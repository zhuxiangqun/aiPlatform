#!/usr/bin/env python3
"""Phase 4 — write disposition ledger tickets from failure taxonomy.

Maps taxonomy categories via phase4_routing.v0.json, appends open tickets,
and records a reeval pack fingerprint stub. Does NOT claim closed loop,
does NOT dispatch to infra, does NOT flip Chart.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "docs/a3/evidence/meta_eval"
ROUTING = ROOT / "docs/a3/config/phase4_routing.v0.json"
LEDGER = META / "phase4_disposition_ledger.v0.json"


def _now() -> str:
    """返回 +08:00 时间戳。

    Returns:
        ISO 本地时区字符串。
    """
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _load_routing() -> Dict[str, Any]:
    """加载路由配置。

    Returns:
        路由 JSON。
    """
    return json.loads(ROUTING.read_text(encoding="utf-8"))


def _route_map(routing: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """category → route row。

    Args:
        routing: 路由配置。

    Returns:
        映射表。
    """
    out: Dict[str, Dict[str, Any]] = {}
    for row in routing.get("routes") or []:
        if isinstance(row, dict) and row.get("category"):
            out[str(row["category"])] = row
    return out


def pack_fingerprint(payload: Dict[str, Any]) -> str:
    """稳定指纹：同一 pack 复评用。

    Args:
        payload: 可序列化对象。

    Returns:
        sha256 hex。
    """
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def taxonomy_to_tickets(
    taxonomy: Dict[str, Any],
    *,
    routing: Dict[str, Any],
    source: str,
    pack_id: str,
) -> List[Dict[str, Any]]:
    """把 taxonomy.counts 转成 open 处置单。

    Args:
        taxonomy: ``build_failure_taxonomy`` 风格对象。
        routing: 路由配置。
        source: 来源说明。
        pack_id: 复评包 id。

    Returns:
        处置单列表。
    """
    routes = _route_map(routing)
    counts = taxonomy.get("counts") if isinstance(taxonomy.get("counts"), dict) else {}
    samples = taxonomy.get("samples") if isinstance(taxonomy.get("samples"), dict) else {}
    tickets: List[Dict[str, Any]] = []
    for cat, n in sorted(counts.items(), key=lambda x: str(x[0])):
        if int(n or 0) <= 0:
            continue
        route = routes.get(str(cat)) or routes.get("unknown") or {
            "category": "unknown",
            "route_to": "eval_owner",
            "sla_owner_h": 24,
            "sla_disposition_h": 72,
        }
        tickets.append(
            {
                "ticket_id": f"disp-{uuid.uuid4().hex[:12]}",
                "status": "open",
                "failure_category": str(cat),
                "failure_n": int(n),
                "sample_task_ids": list(samples.get(str(cat)) or [])[:5],
                "route_to": route.get("route_to"),
                "sla_owner_h": route.get("sla_owner_h", 24),
                "sla_disposition_h": route.get("sla_disposition_h", 72),
                "opened_at": _now(),
                "closed_at": None,
                "disposition": None,
                "reeval_pack_id": pack_id,
                "source": source,
            }
        )
    return tickets


def write_ledger(
    *,
    taxonomy: Dict[str, Any],
    source: str,
    pack_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """写入/合并 disposition 账本。

    Args:
        taxonomy: 失败 taxonomy。
        source: 来源标签。
        pack_meta: 可选 pack 元数据（进指纹）。

    Returns:
        账本摘要。
    """
    routing = _load_routing()
    pack_meta = dict(pack_meta or {})
    pack_meta.setdefault("schema", "eval.phase4.reeval_pack.v0")
    pack_meta["taxonomy"] = {
        "counts": taxonomy.get("counts") or {},
        "total_failures": taxonomy.get("total_failures"),
    }
    fp = pack_fingerprint(pack_meta)
    pack_id = f"pack-{fp[:16]}"
    tickets = taxonomy_to_tickets(taxonomy, routing=routing, source=source, pack_id=pack_id)

    META.mkdir(parents=True, exist_ok=True)
    if LEDGER.is_file():
        ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    else:
        ledger = {
            "schema": "eval.phase4.disposition_ledger.v0",
            "tickets": [],
            "packs": [],
        }
    existing = list(ledger.get("tickets") or [])
    # Dedup: same pack_id + category open ticket → skip
    existing_keys = {
        (t.get("reeval_pack_id"), t.get("failure_category"))
        for t in existing
        if isinstance(t, dict) and t.get("status") == "open"
    }
    added = 0
    for t in tickets:
        key = (t["reeval_pack_id"], t["failure_category"])
        if key in existing_keys:
            continue
        existing.append(t)
        existing_keys.add(key)
        added += 1
    packs = list(ledger.get("packs") or [])
    if not any(p.get("pack_id") == pack_id for p in packs if isinstance(p, dict)):
        packs.append(
            {
                "pack_id": pack_id,
                "fingerprint_sha256": fp,
                "recorded_at": _now(),
                "source": source,
                "meta": {k: pack_meta[k] for k in pack_meta if k != "taxonomy"},
                "taxonomy_total_failures": taxonomy.get("total_failures"),
            }
        )
    ledger.update(
        {
            "schema": "eval.phase4.disposition_ledger.v0",
            "recorded_at": _now(),
            "routing_ref": "docs/a3/config/phase4_routing.v0.json",
            "tickets": existing,
            "packs": packs,
            "open_n": sum(1 for t in existing if isinstance(t, dict) and t.get("status") == "open"),
            "closed_n": sum(
                1 for t in existing if isinstance(t, dict) and t.get("status") == "closed"
            ),
            "closed_loop_claim": False,
            "chart_a3_process_split_authorized": False,
            "honesty": (
                "Disposition ledger write path only. Tickets stay open until human "
                "disposition + reeval. ≠ closed-loop automation ≠ Chart flip."
            ),
        }
    )
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "pack_id": pack_id,
        "fingerprint_sha256": fp,
        "tickets_added": added,
        "open_n": ledger["open_n"],
        "ledger": str(LEDGER.relative_to(ROOT)),
    }


def _demo_taxonomy() -> Dict[str, Any]:
    """本地演示 taxonomy（非生产失败）。

    Returns:
        taxonomy 对象。
    """
    return {
        "schema_version": "eval.failure_taxonomy.v0",
        "counts": {"implementation": 2, "data": 1, "unknown": 1},
        "samples": {
            "implementation": ["demo-impl-1", "demo-impl-2"],
            "data": ["demo-data-1"],
            "unknown": ["demo-unk-1"],
        },
        "total_failures": 4,
    }


def close_ticket(
    ticket_id: str,
    *,
    disposition: str,
    closed_by: str,
) -> Dict[str, Any]:
    """人工关单（写 disposition；不宣称闭环）。

    Args:
        ticket_id: 处置单 id。
        disposition: 处置说明。
        closed_by: 关单人。

    Returns:
        关单摘要。

    Raises:
        FileNotFoundError: 账本不存在。
        KeyError: ticket 不存在或已关闭。
    """
    if not LEDGER.is_file():
        raise FileNotFoundError(str(LEDGER))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    tickets = list(ledger.get("tickets") or [])
    found = None
    for t in tickets:
        if isinstance(t, dict) and t.get("ticket_id") == ticket_id:
            found = t
            break
    if found is None:
        raise KeyError(f"ticket not found: {ticket_id}")
    if found.get("status") == "closed":
        raise KeyError(f"ticket already closed: {ticket_id}")
    found["status"] = "closed"
    found["closed_at"] = _now()
    found["disposition"] = disposition
    found["closed_by"] = closed_by
    ledger["tickets"] = tickets
    ledger["open_n"] = sum(1 for t in tickets if isinstance(t, dict) and t.get("status") == "open")
    ledger["closed_n"] = sum(
        1 for t in tickets if isinstance(t, dict) and t.get("status") == "closed"
    )
    ledger["recorded_at"] = _now()
    ledger["closed_loop_claim"] = False
    ledger["chart_a3_process_split_authorized"] = False
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ticket_id": ticket_id,
        "status": "closed",
        "open_n": ledger["open_n"],
        "closed_n": ledger["closed_n"],
        "reeval_pack_id": found.get("reeval_pack_id"),
    }


def _refresh_prep_board() -> None:
    """委托 phase4_repair_loop_prep.py 刷新闸门板。

    Returns:
        None。
    """
    prep_py = ROOT / "scripts" / "phase4_repair_loop_prep.py"
    if not prep_py.is_file():
        return
    venv = ROOT.parents[1] / ".venv" / "bin" / "python"
    exe = str(venv) if venv.is_file() else sys.executable
    import subprocess

    subprocess.run([exe, str(prep_py)], check=False)  # noqa: S603 — local prep refresh


def main(argv: Optional[List[str]] = None) -> int:
    """CLI：写 disposition 账本或关单。

    Args:
        argv: 参数列表。

    Returns:
        退出码。
    """
    argv = list(argv if argv is not None else sys.argv[1:])
    taxonomy_path = None
    demo = False
    close_id = None
    disposition = None
    i = 0
    while i < len(argv):
        if argv[i] == "--demo":
            demo = True
            i += 1
        elif argv[i] == "--taxonomy" and i + 1 < len(argv):
            taxonomy_path = argv[i + 1]
            i += 2
        elif argv[i] == "--close" and i + 1 < len(argv):
            close_id = argv[i + 1]
            i += 2
        elif argv[i] == "--disposition" and i + 1 < len(argv):
            disposition = argv[i + 1]
            i += 2
        else:
            print(f"unknown arg: {argv[i]}", file=sys.stderr)
            return 2

    if close_id:
        if not disposition:
            print("--close requires --disposition TEXT", file=sys.stderr)
            return 2
        try:
            summary = close_ticket(
                close_id,
                disposition=disposition,
                closed_by=os.environ.get("USER", "owner"),
            )
        except (FileNotFoundError, KeyError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        _refresh_prep_board()
        print(
            json.dumps(
                {
                    "ok": True,
                    **summary,
                    "closed_loop_claim": False,
                    "note": "Ticket closed ≠ same-pack reeval done ≠ closed_loop",
                },
                ensure_ascii=False,
            )
        )
        return 0

    if taxonomy_path:
        taxonomy = json.loads(Path(taxonomy_path).read_text(encoding="utf-8"))
        source = f"file:{taxonomy_path}"
    elif demo or not argv:
        demo = True
        taxonomy = _demo_taxonomy()
        source = "demo_synthetic"
    else:
        print("use --demo, --taxonomy PATH, or --close ID --disposition TEXT", file=sys.stderr)
        return 2

    if not ROUTING.is_file():
        print("missing routing config", file=sys.stderr)
        return 1

    summary = write_ledger(
        taxonomy=taxonomy,
        source=source,
        pack_meta={"demo": demo, "operator": os.environ.get("USER", "ops")},
    )
    _refresh_prep_board()
    print(json.dumps({"ok": True, **summary, "closed_loop_claim": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
