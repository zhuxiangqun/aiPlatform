import pytest


class _Resp:
    def __init__(self, status: int, text: str = "fail"):
        self.status = status
        self._text = text

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Sess:
    def __init__(self, status: int):
        self._status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json=None, headers=None):
        return _Resp(self._status, "nope")


@pytest.mark.asyncio
async def test_job_delivery_failed_goes_to_dlq(tmp_path, monkeypatch):
    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.management.job_scheduler import JobScheduler, SchedulerConfig

    db_path = tmp_path / "exec.sqlite3"
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()

    # Fail all webhook calls
    import aiohttp

    monkeypatch.setattr(aiohttp, "ClientSession", lambda *args, **kwargs: _Sess(500))

    scheduler = JobScheduler(execution_store=store, harness=None, config=SchedulerConfig(delivery_retries=1, delivery_backoff_seconds=0))
    res = await scheduler._deliver_webhook(
        {"type": "webhook", "url": "http://example.com/hook", "include": ["job", "run", "result"]},
        job={"id": "job-1"},
        run={"id": "run-1", "job_id": "job-1"},
        result={"ok": True},
    )
    assert res and res.get("ok") is False

    dlq = await store.list_job_delivery_dlq(status="pending", limit=10, offset=0)
    assert dlq["total"] == 1
    item = dlq["items"][0]
    assert item["job_id"] == "job-1"
    assert item["run_id"] == "run-1"
    assert item["attempts"] == 2  # retries + 1


@pytest.mark.asyncio
async def test_job_delivery_retry_resolves_dlq(tmp_path, monkeypatch):
    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.management.job_scheduler import JobScheduler, SchedulerConfig

    db_path = tmp_path / "exec.sqlite3"
    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    await store.init()

    # Create one DLQ item
    item = await store.enqueue_job_delivery_dlq(
        job_id="job-1",
        run_id="run-1",
        url="http://example.com/hook",
        delivery={"type": "webhook", "url": "http://example.com/hook"},
        payload={"type": "job_run", "job": {"id": "job-1"}},
        attempts=2,
        error="failed",
    )

    # Make retry succeed
    import aiohttp

    monkeypatch.setattr(aiohttp, "ClientSession", lambda *args, **kwargs: _Sess(200))

    scheduler = JobScheduler(execution_store=store, harness=None, config=SchedulerConfig(delivery_retries=0, delivery_backoff_seconds=0))
    out = await scheduler.retry_dlq_delivery(item["id"])
    assert out["ok"] is True

    got = await store.get_job_delivery_dlq_item(item["id"])
    assert got is not None
    assert got["status"] == "resolved"

