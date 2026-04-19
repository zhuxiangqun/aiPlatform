from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional, Tuple


def _csv_bytes(rows: List[Dict[str, Any]], *, fieldnames: List[str]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k) for k in fieldnames})
    return buf.getvalue().encode("utf-8")


class OpsExporter:
    """
    PR-14: export endpoints (MVP)
    - audit_logs
    - run_events
    - approvals (approval_requests)

    为了简单：直接查询 ExecutionStore 对应 list API，输出 CSV bytes。
    """

    def __init__(self, *, execution_store: Any):
        self._store = execution_store

    async def export_audit_logs_csv(
        self,
        *,
        tenant_id: Optional[str],
        limit: int = 1000,
    ) -> Tuple[bytes, str]:
        res = await self._store.list_audit_logs(tenant_id=tenant_id, limit=int(limit), offset=0)
        items = res.get("items") or []
        fieldnames = [
            "id",
            "tenant_id",
            "actor_id",
            "actor_role",
            "action",
            "resource_type",
            "resource_id",
            "request_id",
            "run_id",
            "trace_id",
            "status",
            "created_at",
        ]
        return _csv_bytes(items, fieldnames=fieldnames), "audit_logs.csv"

    async def export_run_events_csv(self, *, run_id: str, limit: int = 5000) -> Tuple[bytes, str]:
        res = await self._store.list_run_events(run_id=str(run_id), after_seq=0, limit=int(limit))
        items = res.get("items") or []
        fieldnames = ["seq", "event_type", "trace_id", "tenant_id", "payload", "created_at"]
        # Normalize for CSV
        norm = []
        for it in items:
            if isinstance(it, dict):
                d = dict(it)
                # store uses key 'type'
                if "event_type" not in d and "type" in d:
                    d["event_type"] = d.get("type")
                # payload may be dict -> str
                if isinstance(d.get("payload"), (dict, list)):
                    import json

                    d["payload"] = json.dumps(d.get("payload"), ensure_ascii=False)
                norm.append(d)
        return _csv_bytes(norm, fieldnames=fieldnames), f"run_events_{run_id}.csv"

    async def export_syscall_events_csv(
        self,
        *,
        tenant_id: Optional[str],
        run_id: Optional[str] = None,
        kind: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 2000,
    ) -> Tuple[bytes, str]:
        res = await self._store.list_syscall_events(
            tenant_id=tenant_id,
            run_id=run_id,
            kind=kind,
            status=status,
            limit=int(limit),
            offset=0,
        )
        items = res.get("items") or []
        fieldnames = [
            "id",
            "tenant_id",
            "run_id",
            "trace_id",
            "span_id",
            "kind",
            "name",
            "status",
            "duration_ms",
            "error_code",
            "error",
            "target_type",
            "target_id",
            "user_id",
            "session_id",
            "created_at",
        ]
        # Flatten args/result to keep export small; can be extended later.
        return _csv_bytes(items, fieldnames=fieldnames), "syscall_events.csv"
