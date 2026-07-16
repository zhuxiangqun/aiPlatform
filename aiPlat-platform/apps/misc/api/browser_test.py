"""
Browser Test API — 全功能浏览器自动化测试端点

POST   /browser/test/start          — 启动测试
GET    /browser/test/status         — 查询进度
GET    /browser/test/report         — 获取报告
POST   /browser/test/stop           — 停止测试
POST   /browser/test/generate-cases — 生成用例 Excel
POST   /browser/test/execute-cases  — 执行用例 Excel
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from core.harness.kernel.runtime import get_kernel_runtime
from core.apps.tools.browser_test_engine import register_engine, unregister_engine, get_active_engine

router = APIRouter()

_active_task: Optional[asyncio.Task] = None
_lock = threading.Lock()

# Tests count is included in the models module — we just need the class reference
_case_executor_ref: Optional[Any] = None
_case_task: Optional[asyncio.Task] = None


@router.post("/browser/test/start", response_model=Dict[str, Any])
async def start_test(request: dict):
    global _active_task
    with _lock:
        if _active_task and not _active_task.done():
            raise HTTPException(status_code=409, detail="A test is already running. Stop it first.")

    from core.apps.tools.browser_test_engine import (
        Account,
        BrowserTestEngine,
        TestConfig,
    )

    base_url = str(request.get("base_url", "https://8.216.36.35"))
    login_url = str(request.get("login_url", ""))
    accounts_raw = request.get("accounts", [{"username": "admin", "password": "admin"}])
    if isinstance(accounts_raw, list):
        accounts = [Account(
            username=str(a.get("username", "admin")),
            password=str(a.get("password", "admin")),
            label=str(a.get("label", "")),
        ) for a in accounts_raw]
    else:
        accounts = [Account(username="admin", password="admin")]

    routes = request.get("routes", [])
    if isinstance(routes, list):
        routes = [str(r) for r in routes]

    config = TestConfig(
        base_url=base_url,
        login_url=login_url,
        accounts=accounts,
        routes=routes if routes else [],
        exclude_patterns=request.get("exclude_patterns", []),
        include_patterns=request.get("include_patterns", []),
        max_recursion_depth=int(request.get("max_recursion_depth", 3)),
        allow_writes=bool(request.get("allow_writes", False)),
        allow_delete=bool(request.get("allow_delete", False)),
        action_timeout_ms=int(request.get("action_timeout_ms", 15000)),
        page_load_timeout_ms=int(request.get("page_load_timeout_ms", 30000)),
        screenshot_dir=str(request.get("screenshot_dir", "")),
        video_enabled=bool(request.get("video_enabled", True)),
        headless=bool(request.get("headless", False)),
    )

    engine = BrowserTestEngine(config)
    register_engine(engine)
    _active_task = asyncio.create_task(engine.run())

    return {
        "ok": True,
        "message": "Browser test started",
        "config": {
            "base_url": base_url,
            "accounts": len(accounts),
            "routes": len(config.routes) if config.routes else "all_default",
        },
    }


@router.get("/browser/test/status", response_model=Dict[str, Any])
async def test_status():
    global _active_task
    if _active_task is None:
        return {"running": False, "status": "not_started"}

    done = _active_task.done()
    summary: Dict[str, Any] = {}
    engine = get_active_engine()
    if engine and hasattr(engine, "_report"):
        report = engine._report
        summary = {
            "total_pages": report.total_pages,
            "total_actions": report.total_actions,
            "passed": report.passed,
            "failed": report.failed,
            "skipped": report.skipped,
            "duration_ms": report.total_duration_ms,
            "errors": len(report.errors),
        }

    return {
        "running": not done,
        "status": "running" if not done else "finished",
        "summary": summary,
    }


@router.get("/browser/test/report", response_model=Dict[str, Any])
async def test_report(detail: bool = False):
    engine = get_active_engine()
    if engine is None:
        raise HTTPException(status_code=404, detail="No test has been run")

    report = engine._report

    if not detail:
        return {
            "started_at": report.started_at,
            "finished_at": report.finished_at,
            "total_pages": report.total_pages,
            "total_actions": report.total_actions,
            "passed": report.passed,
            "failed": report.failed,
            "skipped": report.skipped,
            "total_duration_ms": report.total_duration_ms,
            "errors": report.errors[-10:],
        }

    return {
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "total_pages": report.total_pages,
        "total_actions": report.total_actions,
        "passed": report.passed,
        "failed": report.failed,
        "skipped": report.skipped,
        "total_duration_ms": report.total_duration_ms,
        "errors": report.errors,
        "pages": [
            {
                "url": p.url,
                "depth": p.depth,
                "loaded": p.loaded,
                "elements_found": p.elements_found,
                "screenshot": p.screenshot,
                "modals_detected": p.modals_detected,
                "actions": [
                    {
                        "step_id": a.step_id,
                        "action": a.action,
                        "element_role": a.element_role,
                        "element_text": a.element_text,
                        "result": a.result,
                        "error": a.error,
                        "duration_ms": a.duration_ms,
                        "screenshot_before": a.screenshot_before,
                        "screenshot_after": a.screenshot_after,
                    }
                    for a in p.actions
                ],
            }
            for p in report.pages
        ],
    }


@router.post("/browser/test/stop", response_model=Dict[str, Any])
async def stop_test():
    global _active_task
    engine = get_active_engine()
    if engine is None:
        return {"ok": False, "message": "No test running"}

    engine.stop()
    if _active_task and not _active_task.done():
        _active_task.cancel()

    summary = {}
    if hasattr(engine, "_report"):
        report = engine._report
        summary = {
            "total_pages": report.total_pages,
            "total_actions": report.total_actions,
            "passed": report.passed,
            "failed": report.failed,
            "skipped": report.skipped,
        }

    unregister_engine()
    _active_task = None
    return {"ok": True, "message": "Test stopped", "summary": summary}


@router.post("/browser/test/generate-cases", response_model=Dict[str, Any])
async def generate_cases(request: dict):
    """页面分析 → 生成测试用例 Excel。"""
    global _case_executor_ref

    from core.apps.tools.browser_test_engine import (
        Account, TestConfig,
    )
    from core.apps.tools.test_case_generator import TestCaseGenerator

    base_url = str(request.get("base_url", "https://8.216.36.35"))
    routes = request.get("routes", [])
    if isinstance(routes, list):
        routes = [str(r) for r in routes]
    include_patterns = request.get("include_patterns", [])
    max_depth = int(request.get("max_recursion_depth", 2))

    config = TestConfig(
        base_url=base_url,
        routes=routes if routes else [],
        include_patterns=include_patterns,
        max_recursion_depth=max_depth,
        login_url=str(request.get("login_url", "")),
        accounts=[
            Account(username=str(a.get("username", "admin")), password=str(a.get("password", "admin")))
            for a in request.get("accounts", [])
        ] if isinstance(request.get("accounts"), list) else [],
    )

    generator = TestCaseGenerator(config)
    _case_executor_ref = generator  # register for stop support
    try:
        xlsx_path = await generator.generate()
    finally:
        _case_executor_ref = None

    return {
        "ok": True,
        "message": "Test cases generated",
        "xlsx_path": xlsx_path,
        "total_cases": len(generator._rows),
    }


@router.post("/browser/test/upload-cases", response_model=Dict[str, Any])
async def upload_cases(file: UploadFile = File(...)):
    """上传编辑后的 xlsx 文件，保存到临时目录并返回路径。"""
    if not file.filename or not file.filename.endswith('.xlsx'):
        raise HTTPException(status_code=400, detail="Only .xlsx files are accepted")
    content = await file.read()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(tempfile.gettempdir(), f"uploaded_cases_{ts}.xlsx")
    with open(dest, "wb") as f:
        f.write(content)
    return {"ok": True, "path": dest, "filename": file.filename}


@router.get("/browser/test/download", response_model=Dict[str, Any])
async def download_file(path: str = ""):
    """下载生成的 xlsx 文件。"""
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    filename = os.path.basename(path)
    return FileResponse(path, filename=filename, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/browser/test/execute-cases", response_model=Dict[str, Any])
async def execute_cases(request: dict):
    """从 Excel 读取 approved 用例 → 执行。"""
    global _case_executor_ref, _case_task

    xlsx_path = str(request.get("xlsx_path", ""))
    if not xlsx_path or not os.path.exists(xlsx_path):
        raise HTTPException(status_code=400, detail="xlsx_path is required and must exist")

    from core.apps.tools.browser_test_engine import TestConfig, Account
    from core.apps.tools.test_case_executor import TestCaseExecutor

    config = TestConfig(
        base_url=str(request.get("base_url", "")),
        headless=bool(request.get("headless", False)),
        login_url=str(request.get("login_url", "")),
        accounts=[
            Account(username=str(a.get("username", "admin")), password=str(a.get("password", "admin")))
            for a in (request.get("accounts", []) if isinstance(request.get("accounts"), list) else [])
        ],
    )
    executor = TestCaseExecutor(xlsx_path, config)
    _case_executor_ref = executor
    _case_task = asyncio.create_task(executor.execute(
        auto_approve=bool(request.get("auto_approve", False))
    ))

    return {"ok": True, "message": "Case execution started"}


@router.post("/browser/test/execute-cases/stop", response_model=Dict[str, Any])
async def stop_case_execution():
    global _case_executor_ref, _case_task
    if _case_executor_ref:
        _case_executor_ref.stop()
    if _case_task and not _case_task.done():
        _case_task.cancel()
        _case_task = None
    return {"ok": True, "message": "Case execution stopped"}


@router.get("/browser/test/execute-cases/status", response_model=Dict[str, Any])
async def case_execution_status():
    global _case_task, _case_executor_ref
    if not _case_task:
        return {"running": False, "status": "not_started", "error": ""}
    progress = getattr(_case_executor_ref, "_last_progress", None) if _case_executor_ref else None
    if progress:
        return dict(progress)
    # Fallback: check if task raised an exception
    if _case_task.done():
        exc = _case_task.exception()
        err = str(exc) if exc else ""
        return {"running": False, "status": "finished", "error": err, "done": 0, "total": 0, "passed": 0, "failed": 0, "result_path": "", "video_path": ""}
    return {"running": True, "status": "running", "error": ""}
