"""Prompt Eval API — A/B test, test case management, batch evaluation."""
from __future__ import annotations
from typing import Dict, Any
import json as _json
import logging
import time
import uuid
from core.harness.infrastructure.db_utils import get_db_connection


from fastapi import APIRouter, HTTPException
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.syscalls.llm import sys_llm_generate
from core.schemas_prompt_app import PromptTestCaseCreate, PromptTestCaseUpdate, PromptEvalRunCreate

router = APIRouter()
_log = logging.getLogger("aiplat.prompt_eval")


def _store():
    rt = get_kernel_runtime()
    return getattr(rt, "execution_store", None) if rt else None


def _new_id() -> str:
    return f"pe-{uuid.uuid4().hex[:8]}"


# ── Test Cases ──────────────────────────────────────────────────────

@router.get("/prompts/eval/runs/{run_id}", response_model=Dict[str, Any])
async def get_eval_run(run_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    await store.init()
    import sqlite3
    db_path = store._config.db_path
    def _sync():
        with get_db_connection(db_path) as conn:
            row = conn.execute("SELECT * FROM prompt_eval_runs WHERE id=?;", (run_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Eval run not found")
            return dict(row)
    import anyio
    return await anyio.to_thread.run_sync(_sync)
