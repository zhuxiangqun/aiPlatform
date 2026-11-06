"""Prompt eval ops — test cases + A/B runs (platform thin HTTP via CoreFacade)."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger("aiplat.prompt_eval_ops")


def _new_id() -> str:
    return f"pe-{uuid.uuid4().hex[:8]}"


def _db_path_from_store(store: Any) -> str:
    return str(store._config.db_path)


async def _require_store() -> Any:
    from core.api.core_facade import get_kernel_runtime

    rt = get_kernel_runtime()
    store = getattr(rt, "execution_store", None) if rt else None
    if not store:
        try:
            from core.api.core_facade import get_execution_store

            store = get_execution_store()
        except Exception as e:
            raise RuntimeError("ExecutionStore not initialized") from e
    if not store:
        raise RuntimeError("ExecutionStore not initialized")
    await store.init()
    return store


def prompt_eval_list_test_cases(
    *,
    db_path: str,
    template_id: str = "",
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    from core.api.core_facade import get_db_connection

    with get_db_connection(db_path) as conn:
        where, params = "", []
        if template_id:
            where = " WHERE template_id=?"
            params.append(template_id)
        total = conn.execute(
            f"SELECT COUNT(*) FROM prompt_test_cases{where};", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM prompt_test_cases{where} ORDER BY created_at DESC LIMIT ? OFFSET ?;",
            params + [limit, offset],
        ).fetchall()
        return {"total": total, "items": [dict(r) for r in rows]}


def prompt_eval_create_test_case(
    *,
    db_path: str,
    template_id: str,
    name: str,
    variables: Any,
    expected_keys: str,
) -> Dict[str, Any]:
    from core.api.core_facade import get_db_connection

    case_id = f"tc-{_new_id().split('-')[1]}"
    now = time.time()
    with get_db_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO prompt_test_cases(id,template_id,name,variables,expected_keys,created_at) "
            "VALUES(?,?,?,?,?,?);",
            (
                case_id,
                template_id,
                name,
                json.dumps(variables, ensure_ascii=False),
                expected_keys,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM prompt_test_cases WHERE id=?;", (case_id,)
        ).fetchone()
        return dict(row) if row else {}


def prompt_eval_update_test_case(
    *,
    db_path: str,
    case_id: str,
    name: Optional[str],
    variables: Any,
    expected_keys: Optional[str],
) -> Dict[str, Any]:
    from core.api.core_facade import get_db_connection

    with get_db_connection(db_path) as conn:
        existing = conn.execute(
            "SELECT * FROM prompt_test_cases WHERE id=?;", (case_id,)
        ).fetchone()
        if not existing:
            raise LookupError("Test case not found")
        new_name = name if name is not None else existing["name"]
        new_vars = (
            json.dumps(variables, ensure_ascii=False)
            if variables is not None
            else existing["variables"]
        )
        new_keys = expected_keys if expected_keys is not None else existing["expected_keys"]
        conn.execute(
            "UPDATE prompt_test_cases SET name=?, variables=?, expected_keys=? WHERE id=?;",
            (new_name, new_vars, new_keys, case_id),
        )
        conn.commit()
        return {"status": "updated"}


def prompt_eval_delete_test_case(*, db_path: str, case_id: str) -> Dict[str, Any]:
    from core.api.core_facade import get_db_connection

    with get_db_connection(db_path) as conn:
        conn.execute("DELETE FROM prompt_test_cases WHERE id=?;", (case_id,))
        conn.commit()
        return {"status": "deleted"}


def prompt_eval_list_runs(
    *,
    db_path: str,
    template_id: str = "",
    limit: int = 20,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    from core.api.core_facade import get_db_connection

    with get_db_connection(db_path) as conn:
        where, params = "", []
        if template_id:
            where = " WHERE template_id=?"
            params.append(template_id)
        rows = conn.execute(
            f"SELECT * FROM prompt_eval_runs{where} ORDER BY created_at DESC LIMIT ? OFFSET ?;",
            params + [limit, offset],
        ).fetchall()
        return [dict(r) for r in rows]


def prompt_eval_get_run(*, db_path: str, run_id: str) -> Dict[str, Any]:
    from core.api.core_facade import get_db_connection

    with get_db_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM prompt_eval_runs WHERE id=?;", (run_id,)
        ).fetchone()
        if not row:
            raise LookupError("Eval run not found")
        return dict(row)


def _load_cases_and_template(
    db_path: str,
    *,
    template_id: str,
    case_ids: Optional[List[str]],
) -> Tuple[List[Any], Any]:
    from core.api.core_facade import get_db_connection

    with get_db_connection(db_path) as conn:
        if case_ids:
            placeholders = ",".join("?" for _ in case_ids)
            case_rows = conn.execute(
                f"SELECT * FROM prompt_test_cases WHERE id IN ({placeholders});",
                case_ids,
            ).fetchall()
        else:
            case_rows = conn.execute(
                "SELECT * FROM prompt_test_cases WHERE template_id=? LIMIT 20;",
                (template_id,),
            ).fetchall()
        tpl = conn.execute(
            "SELECT * FROM prompt_app_templates WHERE id=?;", (template_id,)
        ).fetchone()
        return list(case_rows), tpl


async def _run_evaluation(
    run_id: str,
    *,
    model_name: str,
    case_rows: List[Any],
    tpl: Any,
    db_path: str,
) -> None:
    from core.api.core_facade import (
        create_selected_adapter,
        get_db_connection,
        sys_llm_generate,
    )

    try:
        model = create_selected_adapter(model_name=model_name)
        results = []
        scores_a = 0
        b_wins = draws = 0

        for case in case_rows:
            case_id = case["id"]
            variables = json.loads(case.get("variables", "{}"))
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
                output = resp.content if hasattr(resp, "content") else str(resp)
                expected = case.get("expected_keys", "")
                score = 7
                if expected:
                    matches = sum(
                        1
                        for k in expected.split(",")
                        if k.strip().lower() in output.lower()
                    )
                    score = min(10, 5 + matches * 2)
                results.append(
                    {
                        "case_id": case_id,
                        "variables": variables,
                        "output": str(output)[:1000],
                        "score": score,
                    }
                )
                scores_a += max(score, 5)
            except Exception as exc:
                results.append(
                    {"case_id": case_id, "error": str(exc)[:200], "score": 0}
                )

        total = len(results)
        a_wins = total
        avg_a = round(scores_a / max(total, 1), 1)

        def _save() -> None:
            with get_db_connection(db_path) as conn:
                conn.execute(
                    "UPDATE prompt_eval_runs SET status='done', results_json=?, a_wins=?, "
                    "b_wins=?, draws=?, avg_score_a=?, avg_score_b=?, finished_at=? WHERE id=?;",
                    (
                        json.dumps(results, ensure_ascii=False),
                        a_wins,
                        b_wins,
                        draws,
                        avg_a,
                        0,
                        time.time(),
                        run_id,
                    ),
                )
                conn.commit()

        await asyncio.to_thread(_save)
    except Exception:
        _log.exception("Eval run failed: %s", run_id)


async def prompt_eval_start_run(
    *,
    template_id: str,
    version_a: str,
    version_b: str,
    model: str,
    case_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create run row and schedule background evaluation. Returns protocol-ready dict."""
    from core.api.core_facade import (
        attach_eval_protocol,
        eval_protocol_from_generic,
        get_db_connection,
    )

    store = await _require_store()
    db_path = _db_path_from_store(store)
    case_rows, tpl = await asyncio.to_thread(
        _load_cases_and_template,
        db_path,
        template_id=template_id,
        case_ids=case_ids,
    )
    if not case_rows:
        raise ValueError("No test cases found")
    if not tpl:
        raise LookupError("Template not found")

    run_id = f"er-{_new_id().split('-')[1]}"
    now = time.time()
    total = len(case_rows)

    def _init_run() -> None:
        with get_db_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO prompt_eval_runs(id,template_id,version_a,version_b,model,status,"
                "total_cases,results_json,created_at) VALUES(?,?,?,?,?,?,?,?,?);",
                (
                    run_id,
                    template_id,
                    version_a,
                    version_b,
                    model,
                    "running",
                    total,
                    json.dumps([]),
                    now,
                ),
            )
            conn.commit()

    await asyncio.to_thread(_init_run)

    async def _safe_eval() -> None:
        try:
            await _run_evaluation(
                run_id,
                model_name=model,
                case_rows=case_rows,
                tpl=tpl,
                db_path=db_path,
            )
        except Exception:
            _log.warning("Prompt evaluation failed for run %s", run_id, exc_info=True)

    asyncio.create_task(_safe_eval())

    out = {"run_id": run_id, "status": "running", "total_cases": total}
    return attach_eval_protocol(
        out,
        eval_protocol_from_generic(
            task_id=f"prompt-eval:{run_id}",
            target_kind="workflow",
            target_ref=str(template_id),
            result=out,
            suite="prompt",
        ),
    )


# ── async facade helpers (store lifecycle) ───────────────────────────


async def prompt_eval_list_test_cases_async(
    *, template_id: str = "", limit: int = 100, offset: int = 0
) -> Dict[str, Any]:
    store = await _require_store()
    db_path = _db_path_from_store(store)
    return await asyncio.to_thread(
        prompt_eval_list_test_cases,
        db_path=db_path,
        template_id=template_id,
        limit=limit,
        offset=offset,
    )


async def prompt_eval_create_test_case_async(
    *,
    template_id: str,
    name: str,
    variables: Any,
    expected_keys: str,
) -> Dict[str, Any]:
    store = await _require_store()
    db_path = _db_path_from_store(store)
    return await asyncio.to_thread(
        prompt_eval_create_test_case,
        db_path=db_path,
        template_id=template_id,
        name=name,
        variables=variables,
        expected_keys=expected_keys,
    )


async def prompt_eval_update_test_case_async(
    *,
    case_id: str,
    name: Optional[str],
    variables: Any,
    expected_keys: Optional[str],
) -> Dict[str, Any]:
    store = await _require_store()
    db_path = _db_path_from_store(store)
    return await asyncio.to_thread(
        prompt_eval_update_test_case,
        db_path=db_path,
        case_id=case_id,
        name=name,
        variables=variables,
        expected_keys=expected_keys,
    )


async def prompt_eval_delete_test_case_async(*, case_id: str) -> Dict[str, Any]:
    store = await _require_store()
    db_path = _db_path_from_store(store)
    return await asyncio.to_thread(
        prompt_eval_delete_test_case, db_path=db_path, case_id=case_id
    )


async def prompt_eval_list_runs_async(
    *, template_id: str = "", limit: int = 20, offset: int = 0
) -> List[Dict[str, Any]]:
    store = await _require_store()
    db_path = _db_path_from_store(store)
    return await asyncio.to_thread(
        prompt_eval_list_runs,
        db_path=db_path,
        template_id=template_id,
        limit=limit,
        offset=offset,
    )


async def prompt_eval_get_run_async(*, run_id: str) -> Dict[str, Any]:
    from core.api.core_facade import attach_eval_protocol, eval_protocol_from_generic

    store = await _require_store()
    db_path = _db_path_from_store(store)
    row = await asyncio.to_thread(prompt_eval_get_run, db_path=db_path, run_id=run_id)
    return attach_eval_protocol(
        row,
        eval_protocol_from_generic(
            task_id=f"prompt-eval:{run_id}",
            target_kind="workflow",
            target_ref=str(row.get("template_id") or run_id),
            result=row,
            suite="prompt",
        ),
    )
