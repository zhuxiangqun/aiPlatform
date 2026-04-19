"""
REST API Routes
"""

from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel
from typing import Optional, Any
from enum import Enum


app = FastAPI(title="aiPlat-platform API", version="0.1.0")


class RunStatus(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"
    TIMEOUT = "timeout"


class RunSummary(BaseModel):
    ok: bool
    run_id: str
    trace_id: Optional[str] = None
    status: RunStatus
    output: Optional[Any] = None
    error: Optional[dict] = None


@app.get("/health")
async def health_check(request: Request):
    """健康检查"""
    tenant_id = request.headers.get("X-AIPLAT-TENANT-ID", "default")
    return {"status": "healthy", "tenant_id": tenant_id}


@app.get("/healthz")
async def healthz():
    """完整健康检查"""
    return {
        "status": "healthy",
        "checks": {
            "database": "ok",
            "queue": "ok",
        },
    }


@app.post("/api/v1/runs")
async def create_run(
    request: Request,
    x_tenant_id: Optional[str] = Header(None, alias="X-AIPLAT-TENANT-ID"),
    x_actor_id: Optional[str] = Header(None, alias="X-AIPLAT-ACTOR-ID"),
):
    """创建运行"""
    tenant_id = x_tenant_id or request.headers.get("X-AIPLAT-TENANT-ID", "default")
    return RunSummary(
        ok=True,
        run_id="run_placeholder",
        trace_id="trace_placeholder",
        status=RunStatus.ACCEPTED,
    )


@app.get("/api/v1/runs/{run_id}")
async def get_run(run_id: str):
    """获取运行状态"""
    return RunSummary(
        ok=True,
        run_id=run_id,
        trace_id="trace_placeholder",
        status=RunStatus.RUNNING,
    )


@app.get("/api/v1/runs/{run_id}/events")
async def get_run_events(run_id: str, after_seq: int = 0):
    """获取运行事件"""
    return {"events": [], "next_seq": 0}


@app.post("/api/v1/runs/{run_id}/wait")
async def wait_for_run(run_id: str, timeout: int = 30):
    """等待运行完成"""
    return RunSummary(
        ok=True,
        run_id=run_id,
        status=RunStatus.COMPLETED,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)