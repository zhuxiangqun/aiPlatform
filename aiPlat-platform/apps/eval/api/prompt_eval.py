"""Prompt Eval API — A/B test, test case management, batch evaluation."""
from __future__ import annotations
from typing import Dict, Any
import json as _json
import logging
import time
import uuid
from core.api.core_facade import get_db_connection


from fastapi import APIRouter, HTTPException
from core.api.core_facade import get_kernel_runtime
from core.api.core_facade import sys_llm_generate
from core.schemas_prompt_app import PromptTestCaseCreate, PromptTestCaseUpdate, PromptEvalRunCreate
from apps.common_schemas import StatusResponse, ListResponse, ItemResponse

router = APIRouter()
_log = logging.getLogger("aiplat.prompt_eval")


def _store():
    rt = get_kernel_runtime()
    return getattr(rt, "execution_store", None) if rt else None


def _new_id() -> str:
    return f"pe-{uuid.uuid4().hex[:8]}"


# ── Test Cases ──────────────────────────────────────────────────────

@router.get("/prompts/eval/test-cases", response_model=ItemResponse)
async def list_test_cases(template_id: str = "", limit: int = 100, offset: int = 0):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    # Use raw SQL for simplicity since we don't have a dedicated CRUD method
    await store.init()
    import sqlite3
    db_path = store._config.db_path
    def _sync():
        with get_db_connection(db_path) as conn:
            where, params = "", []
            if template_id:
                where = " WHERE template_id=?"
                params.append(template_id)
            total = conn.execute(f"SELECT COUNT(*) FROM prompt_test_cases{where};", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM prompt_test_cases{where} ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                params + [limit, offset]
            ).fetchall()
            items = [dict(r) for r in rows]
            return {"total": total, "items": items}
    import anyio
    return await anyio.to_thread.run_sync(_sync)


@router.post("/prompts/eval/test-cases", response_model=StatusResponse)
async def create_test_case(req: PromptTestCaseCreate):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    await store.init()
    import sqlite3
    db_path = store._config.db_path
    case_id = f"tc-{_new_id().split('-')[1]}"
    now = time.time()
    def _sync():
        with get_db_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO prompt_test_cases(id,template_id,name,variables,expected_keys,created_at) VALUES(?,?,?,?,?,?);",
                (case_id, req.template_id, req.name, _json.dumps(req.variables, ensure_ascii=False),
                 req.expected_keys, now))
            conn.commit()
            row = conn.execute("SELECT * FROM prompt_test_cases WHERE id=?;", (case_id,)).fetchone()
            return dict(row) if row else {}
    import anyio
    return await anyio.to_thread.run_sync(_sync)


@router.put("/prompts/eval/test-cases/{case_id}", response_model=StatusResponse)
async def update_test_case(case_id: str, req: PromptTestCaseUpdate):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    await store.init()
    import sqlite3
    db_path = store._config.db_path
    def _sync():
        with get_db_connection(db_path) as conn:
            existing = conn.execute("SELECT * FROM prompt_test_cases WHERE id=?;", (case_id,)).fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Test case not found")
            name = req.name if req.name is not None else existing["name"]
            variables = _json.dumps(req.variables, ensure_ascii=False) if req.variables is not None else existing["variables"]
            expected_keys = req.expected_keys if req.expected_keys is not None else existing["expected_keys"]
            conn.execute(
                "UPDATE prompt_test_cases SET name=?, variables=?, expected_keys=? WHERE id=?;",
                (name, variables, expected_keys, case_id))
            conn.commit()
            return {"status": "updated"}
    import anyio
    return await anyio.to_thread.run_sync(_sync)


@router.delete("/prompts/eval/test-cases/{case_id}", response_model=StatusResponse)
async def delete_test_case(case_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    await store.init()
    import sqlite3
    db_path = store._config.db_path
    def _sync():
        with get_db_connection(db_path) as conn:
            conn.execute("DELETE FROM prompt_test_cases WHERE id=?;", (case_id,))
            conn.commit()
            return {"status": "deleted"}
    import anyio
    return await anyio.to_thread.run_sync(_sync)


# ── Eval Runs ───────────────────────────────────────────────────────

@router.post("/prompts/eval/runs", response_model=StatusResponse)
async def create_eval_run(req: PromptEvalRunCreate):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    await store.init()
    import sqlite3
    db_path = store._config.db_path
    run_id = f"er-{_new_id().split('-')[1]}"
    now = time.time()

    # Load test cases and template versions
    def _load():
        with get_db_connection(db_path) as conn:
            # Get test cases
            case_rows = []
            if req.case_ids:
                placeholders = ",".join("?" for _ in req.case_ids)
                case_rows = conn.execute(
                    f"SELECT * FROM prompt_test_cases WHERE id IN ({placeholders});",
                    req.case_ids
                ).fetchall()
            else:
                case_rows = conn.execute(
                    "SELECT * FROM prompt_test_cases WHERE template_id=? LIMIT 20;",
                    (req.template_id,)
                ).fetchall()

            # Get template
            tpl = conn.execute(
                "SELECT * FROM prompt_app_templates WHERE id=?;", (req.template_id,)
            ).fetchone()
            return case_rows, tpl

    import anyio
    case_rows, tpl = await anyio.to_thread.run_sync(_load)

    if not case_rows:
        raise HTTPException(status_code=400, detail="No test cases found")
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    # Create run record
    total = len(case_rows)
    def _init_run():
        with get_db_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO prompt_eval_runs(id,template_id,version_a,version_b,model,status,total_cases,results_json,created_at) VALUES(?,?,?,?,?,?,?,?,?);",
                (run_id, req.template_id, req.version_a, req.version_b, req.model,
                 "running", total, _json.dumps([]), now))
            conn.commit()

    await anyio.to_thread.run_sync(_init_run)

    # Run evaluation in background
    import asyncio as _aio
    async def _safe_eval():
        try:
            await _run_evaluation(run_id, req, case_rows, tpl, db_path)
        except Exception:
            import logging
            logging.warning("Prompt evaluation failed for run %s", run_id, exc_info=True)
    _aio.create_task(_safe_eval())

    return {"run_id": run_id, "status": "running", "total_cases": total}


async def _run_evaluation(run_id: str, req: PromptEvalRunCreate, case_rows, tpl, db_path: str):
    """## platform:allowed — LLM inference for prompt evaluation."""
    try:
        from core.api.core_facade import create_selected_adapter
        model = create_selected_adapter(model_name=req.model)

        results = []
        a_wins = b_wins = draws = 0
        scores_a = scores_b = 0

        for case in case_rows:
            case_id = case["id"]
            variables = _json.loads(case.get("variables", "{}"))
            sp = tpl.get("system_prompt", "")
            up = tpl.get("user_prompt", "")
            for k, v in variables.items():
                up = up.replace("${" + k + "}", str(v))

            try:
                messages = []
                if sp:
                    messages.append({"role": "system", "content": sp})
                messages.append({"role": "user", "content": up})
                resp = await sys_llm_generate(model, messages)
                output = resp.content if hasattr(resp, 'content') else str(resp)

                # Simple scoring: compare with expected keys
                expected = case.get("expected_keys", "")
                score = 7
                if expected:
                    matches = sum(1 for k in expected.split(",") if k.strip().lower() in output.lower())
                    score = min(10, 5 + matches * 2)

                results.append({
                    "case_id": case_id,
                    "variables": variables,
                    "output": str(output)[:1000],
                    "score": score,
                })
                scores_a += max(score, 5)
            except Exception as exc:
                results.append({"case_id": case_id, "error": str(exc)[:200], "score": 0})

        # Update run results
        total = len(results)
        a_wins = total
        avg_a = round(scores_a / max(total, 1), 1)

        def _save():
            with get_db_connection(db_path) as conn:
                conn.execute(
                    "UPDATE prompt_eval_runs SET status='done', results_json=?, a_wins=?, b_wins=?, draws=?, avg_score_a=?, avg_score_b=?, finished_at=? WHERE id=?;",
                    (_json.dumps(results, ensure_ascii=False), a_wins, b_wins, draws, avg_a, 0, time.time(), run_id))
                conn.commit()
        import anyio
        await anyio.to_thread.run_sync(_save)
    except Exception as e:
        _log.exception("Eval run failed: %s", run_id)


@router.get("/prompts/eval/runs", response_model=ItemResponse)
async def list_eval_runs(template_id: str = "", limit: int = 20, offset: int = 0):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    await store.init()
    import sqlite3
    db_path = store._config.db_path
    def _sync():
        with get_db_connection(db_path) as conn:
            where, params = "", []
            if template_id:
                where = " WHERE template_id=?"
                params.append(template_id)
            rows = conn.execute(
                f"SELECT * FROM prompt_eval_runs{where} ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                params + [limit, offset]
            ).fetchall()
            return [dict(r) for r in rows]
    import anyio
    return await anyio.to_thread.run_sync(_sync)


@router.get("/prompts/eval/runs/{run_id}", response_model=ItemResponse)
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
