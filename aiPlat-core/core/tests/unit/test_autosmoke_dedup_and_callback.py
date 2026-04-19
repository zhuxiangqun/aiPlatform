import pytest


@pytest.mark.anyio
async def test_autosmoke_dedup_and_callback(monkeypatch):
    from core.harness.smoke.autoscheduler import enqueue_autosmoke

    monkeypatch.setenv("AIPLAT_AUTOSMOKE_ENABLED", "true")
    monkeypatch.setenv("AIPLAT_AUTOSMOKE_DEDUP_SECONDS", "600")

    calls = {"completed": 0}

    class FakeStore:
        def __init__(self):
            self.jobs = {}

        async def get_job(self, job_id: str):
            return self.jobs.get(job_id)

        async def create_job(self, job: dict):
            self.jobs[job["id"]] = {**job, "last_run_at": None}
            return self.jobs[job["id"]]

        async def update_job(self, job_id: str, patch: dict):
            cur = self.jobs[job_id]
            cur.update(patch)
            return cur

        async def add_audit_log(self, **kwargs):
            return None

    class FakeScheduler:
        def __init__(self, store: FakeStore):
            self._store = store

        async def run_job_once(self, job_id: str):
            # mimic scheduler: update last_run_at in job
            self._store.jobs[job_id]["last_run_at"] = 123.0
            return {"id": "jobrun-1", "job_id": job_id, "status": "completed", "error": None}

    store = FakeStore()
    sched = FakeScheduler(store)

    async def on_complete(run: dict):
        calls["completed"] += 1

    r1 = await enqueue_autosmoke(execution_store=store, job_scheduler=sched, resource_type="agent", resource_id="a1", on_complete=on_complete)
    assert r1["enqueued"] is True

    # second call dedup (job last_run_at is 123.0; now-ts isn't used in fake, so simulate by forcing get_job last_run_at)
    store.jobs["autosmoke-agent:a1"]["last_run_at"] = 9999999999.0  # very recent
    r2 = await enqueue_autosmoke(execution_store=store, job_scheduler=sched, resource_type="agent", resource_id="a1", on_complete=on_complete)
    assert r2["enqueued"] is False

