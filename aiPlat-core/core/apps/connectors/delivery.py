from __future__ import annotations

from typing import Any, Dict, Optional


class ConnectorDelivery:
    """
    PR-12: 统一 connector delivery（含 DLQ）
    - 当前仅支持 webhook-like POST（Slack response_url / 通用 webhook）
    - 失败时写入 connector_delivery_dlq，供运维重试
    """

    def __init__(self, *, execution_store: Any):
        self._store = execution_store

    async def post_webhook(
        self,
        *,
        connector: str,
        url: str,
        payload: Dict[str, Any],
        tenant_id: Optional[str] = None,
        run_id: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        retries: int = 1,
        timeout_seconds: float = 8.0,
    ) -> Dict[str, Any]:
        import aiohttp

        if not url:
            return {"ok": False, "error": "missing_url"}
        attempts = 0
        last_err = None
        for i in range(int(retries) + 1):
            attempts = i + 1
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=float(timeout_seconds))) as sess:
                    async with sess.post(url, json=payload, headers=headers) as resp:
                        txt = await resp.text()
                        status = int(getattr(resp, "status", 0) or 0)
                        if self._store is not None:
                            try:
                                await self._store.add_connector_delivery_attempt(
                                    connector=str(connector),
                                    tenant_id=str(tenant_id) if tenant_id else None,
                                    run_id=str(run_id) if run_id else None,
                                    attempt=attempts,
                                    url=str(url),
                                    status="success" if 200 <= status < 300 else "failed",
                                    response_status=status,
                                    error=None if 200 <= status < 300 else (txt[:500] if isinstance(txt, str) else "failed"),
                                    payload=payload,
                                )
                            except Exception:
                                pass
                        if 200 <= status < 300:
                            return {"ok": True, "status": status}
                        last_err = f"http_{status}"
            except Exception as e:
                last_err = str(e)
                if self._store is not None:
                    try:
                        await self._store.add_connector_delivery_attempt(
                            connector=str(connector),
                            tenant_id=str(tenant_id) if tenant_id else None,
                            run_id=str(run_id) if run_id else None,
                            attempt=attempts,
                            url=str(url),
                            status="failed",
                            response_status=None,
                            error=str(e),
                            payload=payload,
                        )
                    except Exception:
                        pass

        # DLQ
        if self._store is not None:
            try:
                await self._store.enqueue_connector_delivery_dlq(
                    connector=str(connector),
                    tenant_id=str(tenant_id) if tenant_id else None,
                    run_id=str(run_id) if run_id else None,
                    url=str(url),
                    payload=payload,
                    attempts=int(attempts),
                    error=str(last_err or "delivery_failed"),
                )
            except Exception:
                pass
        return {"ok": False, "error": str(last_err or "delivery_failed"), "attempts": int(attempts)}

