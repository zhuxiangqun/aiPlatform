import pytest


@pytest.mark.anyio
async def test_job_scheduler_delivery_started_and_completed(monkeypatch):
    from core.management.job_scheduler import JobScheduler

    calls = []

    class FakeStore:
        def __init__(self):
            self.jobs = {
                "j1": {
                    "id": "j1",
                    "kind": "smoke_e2e",
                    "target_id": "smoke_e2e",
                    "user_id": "u1",
                    "session_id": "s1",
                    "payload": {},
                    "delivery": {"type": "webhook", "url": "http://example.invalid", "on": ["started", "completed"]},
                }
            }
            self.runs = {}

        async def get_job(self, job_id: str):
            return self.jobs.get(job_id)

        async def acquire_job_lock(self, job_id: str, owner: str, ttl_seconds: float):
            return True

        async def release_job_lock(self, job_id: str, owner: str):
            return True

        async def update_job(self, job_id: str, patch: dict):
            self.jobs[job_id].update(patch)
            return self.jobs[job_id]

        async def create_job_run(self, run: dict):
            self.runs[run["id"]] = dict(run)
            return self.runs[run["id"]]

        async def finish_job_run(self, run_id: str, patch: dict):
            cur = self.runs.get(run_id) or {"id": run_id}
            cur.update(patch)
            self.runs[run_id] = cur
            return cur

        async def get_job_run(self, run_id: str):
            return self.runs.get(run_id)

        # delivery attempt hooks not needed for this unit test
        async def add_job_delivery_attempt(self, **kwargs):
            return None

        async def enqueue_job_delivery_dlq(self, **kwargs):
            return None

    class FakeResult:
        ok = True
        error = None
        trace_id = "t1"
        payload = {"status": "completed"}

    class FakeHarness:
        async def execute(self, req):
            return FakeResult()

    store = FakeStore()
    sched = JobScheduler(execution_store=store, harness=FakeHarness())

    async def fake_deliver(self, delivery, *, job, run, result, phase="completed"):
        calls.append(str(phase))
        return {"ok": True}

    monkeypatch.setattr(JobScheduler, "_deliver_webhook", fake_deliver, raising=True)

    r = await sched.run_job_once("j1")
    assert r.get("status") in ("completed", "success")
    assert calls[0] in ("started", "running")
    assert "completed" in calls

