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

    async def export_approvals_csv(
        self,
        *,
        tenant_id: Optional[str],
        status: Optional[str] = None,
        limit: int = 1000,
    ) -> Tuple[bytes, str]:
        res = await self._store.list_approval_requests(tenant_id=tenant_id, status=status, limit=int(limit), offset=0)
        items = res.get("items") or []
        fieldnames = [
            "request_id",
            "tenant_id",
            "user_id",
            "actor_id",
            "actor_role",
            "session_id",
            "run_id",
            "operation",
            "status",
            "details",
            "created_at",
            "updated_at",
            "expires_at",
        ]
        return _csv_bytes(items, fieldnames=fieldnames), "approvals.csv"

    async def export_tenant_usage_csv(
        self,
        *,
        tenant_id: str,
        day_start: Optional[str] = None,
        day_end: Optional[str] = None,
        metric_key: Optional[str] = None,
        limit: int = 2000,
    ) -> Tuple[bytes, str]:
        res = await self._store.list_tenant_usage(
            tenant_id=str(tenant_id),
            day_start=day_start,
            day_end=day_end,
            metric_key=metric_key,
            limit=int(limit),
            offset=0,
        )
        items = res.get("items") or []
        fieldnames = ["tenant_id", "day", "metric_key", "value", "updated_at"]
        return _csv_bytes(items, fieldnames=fieldnames), "tenant_usage.csv"

    async def export_gateway_dlq_csv(
        self,
        *,
        status: Optional[str] = None,
        tenant_id: Optional[str] = None,
        connector: Optional[str] = None,
        limit: int = 2000,
    ) -> Tuple[bytes, str]:
        res = await self._store.list_connector_delivery_dlq(status=status, tenant_id=tenant_id, connector=connector, limit=int(limit), offset=0)
        items = res.get("items") or []
        fieldnames = ["id", "connector", "tenant_id", "run_id", "url", "attempts", "error", "status", "created_at", "resolved_at"]
        return _csv_bytes(items, fieldnames=fieldnames), "gateway_dlq.csv"

    async def export_connector_attempts_csv(
        self,
        *,
        connector: Optional[str] = None,
        tenant_id: Optional[str] = None,
        run_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 2000,
    ) -> Tuple[bytes, str]:
        res = await self._store.list_connector_delivery_attempts(
            connector=connector,
            tenant_id=tenant_id,
            run_id=run_id,
            status=status,
            limit=int(limit),
            offset=0,
        )
        items = res.get("items") or []
        fieldnames = ["id", "connector", "tenant_id", "run_id", "attempt", "url", "status", "response_status", "error", "created_at"]
        return _csv_bytes(items, fieldnames=fieldnames), "connector_attempts.csv"

    async def export_jobs_dlq_csv(
        self,
        *,
        status: Optional[str] = None,
        job_id: Optional[str] = None,
        limit: int = 2000,
    ) -> Tuple[bytes, str]:
        res = await self._store.list_job_delivery_dlq(status=status, job_id=job_id, limit=int(limit), offset=0)
        items = res.get("items") or []
        fieldnames = ["id", "job_id", "run_id", "url", "attempts", "error", "status", "created_at", "resolved_at"]
        return _csv_bytes(items, fieldnames=fieldnames), "jobs_dlq.csv"

    async def export_job_delivery_attempts_csv(
        self,
        *,
        job_id: Optional[str] = None,
        run_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 2000,
    ) -> Tuple[bytes, str]:
        res = await self._store.list_job_delivery_attempts(job_id=job_id, run_id=run_id, status=status, limit=int(limit), offset=0)
        items = res.get("items") or []
        fieldnames = ["id", "job_id", "run_id", "attempt", "url", "status", "response_status", "error", "created_at"]
        return _csv_bytes(items, fieldnames=fieldnames), "job_delivery_attempts.csv"

    async def export_gateway_pairings_csv(
        self,
        *,
        channel: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 5000,
    ) -> Tuple[bytes, str]:
        res = await self._store.list_gateway_pairings(channel=channel, user_id=user_id, limit=int(limit), offset=0)
        items = res.get("items") or []
        fieldnames = ["id", "channel", "channel_user_id", "user_id", "session_id", "tenant_id", "created_at", "updated_at"]
        return _csv_bytes(items, fieldnames=fieldnames), "gateway_pairings.csv"

    async def export_gateway_tokens_csv(
        self,
        *,
        enabled: Optional[bool] = None,
        limit: int = 5000,
    ) -> Tuple[bytes, str]:
        res = await self._store.list_gateway_tokens(limit=int(limit), offset=0, enabled=enabled)
        items = res.get("items") or []
        # Note: token_sha256 intentionally not present in list_gateway_tokens result.
        fieldnames = ["id", "name", "tenant_id", "enabled", "created_at"]
        return _csv_bytes(items, fieldnames=fieldnames), "gateway_tokens.csv"

    async def export_release_rollouts_csv(
        self,
        *,
        tenant_id: str,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        limit: int = 5000,
    ) -> Tuple[bytes, str]:
        res = await self._store.list_release_rollouts(
            tenant_id=str(tenant_id),
            target_type=target_type,
            target_id=target_id,
            limit=int(limit),
            offset=0,
        )
        items = res.get("items") or []
        fieldnames = [
            "tenant_id",
            "target_type",
            "target_id",
            "candidate_id",
            "status",
            "rollout_percent",
            "include_actor_ids",
            "exclude_actor_ids",
            "metadata",
            "created_at",
            "updated_at",
        ]
        # stringify lists/dicts
        norm = []
        for it in items:
            if isinstance(it, dict):
                d = dict(it)
                import json

                if isinstance(d.get("include_actor_ids"), (list, dict)):
                    d["include_actor_ids"] = json.dumps(d.get("include_actor_ids"), ensure_ascii=False)
                if isinstance(d.get("exclude_actor_ids"), (list, dict)):
                    d["exclude_actor_ids"] = json.dumps(d.get("exclude_actor_ids"), ensure_ascii=False)
                if isinstance(d.get("metadata"), (list, dict)):
                    d["metadata"] = json.dumps(d.get("metadata"), ensure_ascii=False)
                norm.append(d)
        return _csv_bytes(norm, fieldnames=fieldnames), "release_rollouts.csv"

    async def export_release_metrics_csv(
        self,
        *,
        tenant_id: str,
        candidate_id: str,
        metric_key: Optional[str] = None,
        limit: int = 5000,
    ) -> Tuple[bytes, str]:
        res = await self._store.list_release_metric_snapshots(
            tenant_id=str(tenant_id),
            candidate_id=str(candidate_id),
            metric_key=metric_key,
            limit=int(limit),
            offset=0,
        )
        items = res.get("items") or []
        fieldnames = ["id", "tenant_id", "candidate_id", "metric_key", "value", "window_start", "window_end", "metadata", "created_at"]
        norm = []
        for it in items:
            if isinstance(it, dict):
                d = dict(it)
                import json

                if isinstance(d.get("metadata"), (list, dict)):
                    d["metadata"] = json.dumps(d.get("metadata"), ensure_ascii=False)
                norm.append(d)
        return _csv_bytes(norm, fieldnames=fieldnames), f"release_metrics_{candidate_id}.csv"

    async def export_learning_artifacts_csv(
        self,
        *,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        kind: Optional[str] = None,
        status: Optional[str] = None,
        trace_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 5000,
    ) -> Tuple[bytes, str]:
        res = await self._store.list_learning_artifacts(
            target_type=target_type,
            target_id=target_id,
            kind=kind,
            status=status,
            trace_id=trace_id,
            run_id=run_id,
            limit=int(limit),
            offset=0,
        )
        items = res.get("items") or []
        fieldnames = ["artifact_id", "kind", "target_type", "target_id", "version", "status", "trace_id", "run_id", "created_at", "payload", "metadata"]
        norm = []
        for it in items:
            if isinstance(it, dict):
                d = dict(it)
                import json

                if isinstance(d.get("payload"), (list, dict)):
                    d["payload"] = json.dumps(d.get("payload"), ensure_ascii=False)
                if isinstance(d.get("metadata"), (list, dict)):
                    d["metadata"] = json.dumps(d.get("metadata"), ensure_ascii=False)
                norm.append(d)
        return _csv_bytes(norm, fieldnames=fieldnames), "learning_artifacts.csv"
