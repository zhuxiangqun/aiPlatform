"""Prompt Eval API — thin HTTP over CoreFacade prompt_eval_* (ARCH v1.1b)."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from core.schemas_prompt_app import PromptTestCaseCreate, PromptTestCaseUpdate, PromptEvalRunCreate
from apps.common_schemas import StatusResponse, ItemResponse

router = APIRouter()


def _as_item(out: Any) -> Dict[str, Any]:
    """Wrap facade payloads for ItemResponse ({data: dict}).

    list_runs returns a bare list; list_test_cases returns {items,total}.
    FE unwrap uses res.data ?? res and reads items/total.
    """
    if isinstance(out, list):
        return {"data": {"items": out, "total": len(out)}}
    if isinstance(out, dict):
        if "items" in out or "total" in out or "data" in out:
            return {"data": out}
        return {"data": out}
    return {"data": {"value": out}}


@router.get("/prompts/eval/test-cases", response_model=ItemResponse)
async def list_test_cases(template_id: str = "", limit: int = 100, offset: int = 0):
    """列出 test_cases。

    Args:
        template_id: template 标识。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    from core.api.core_facade import prompt_eval_list_test_cases

    try:
        return _as_item(
            await prompt_eval_list_test_cases(
                template_id=template_id, limit=limit, offset=offset
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/prompts/eval/test-cases", response_model=StatusResponse)
async def create_test_case(req: PromptTestCaseCreate):
    """创建 test_case。

    Args:
        req: req 参数。
    """
    from core.api.core_facade import prompt_eval_create_test_case

    try:
        return await prompt_eval_create_test_case(
            template_id=req.template_id,
            name=req.name,
            variables=req.variables,
            expected_keys=req.expected_keys,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put("/prompts/eval/test-cases/{case_id}", response_model=StatusResponse)
async def update_test_case(case_id: str, req: PromptTestCaseUpdate):
    """update_test_case。

    Args:
        case_id: 用例 ID。
        req: req 参数。
    """
    from core.api.core_facade import prompt_eval_update_test_case

    try:
        return await prompt_eval_update_test_case(
            case_id=case_id,
            name=req.name,
            variables=req.variables,
            expected_keys=req.expected_keys,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/prompts/eval/test-cases/{case_id}", response_model=StatusResponse)
async def delete_test_case(case_id: str):
    """删除 test_case。

    Args:
        case_id: 用例 ID。
    """
    from core.api.core_facade import prompt_eval_delete_test_case

    try:
        return await prompt_eval_delete_test_case(case_id=case_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/prompts/eval/runs", response_model=StatusResponse)
async def create_eval_run(req: PromptEvalRunCreate):
    """创建 eval_run。

    Args:
        req: req 参数。
    """
    from core.api.core_facade import prompt_eval_start_run

    try:
        return await prompt_eval_start_run(
            template_id=req.template_id,
            version_a=req.version_a,
            version_b=req.version_b,
            model=req.model,
            case_ids=list(req.case_ids) if req.case_ids else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/prompts/eval/runs", response_model=ItemResponse)
async def list_eval_runs(template_id: str = "", limit: int = 20, offset: int = 0):
    """列出 eval_runs。

    Args:
        template_id: template 标识。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    from core.api.core_facade import prompt_eval_list_runs

    try:
        return _as_item(
            await prompt_eval_list_runs(
                template_id=template_id, limit=limit, offset=offset
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/prompts/eval/runs/{run_id}", response_model=ItemResponse)
async def get_eval_run(run_id: str):
    """获取 eval_run。

    Args:
        run_id: 运行 ID。
    """
    from core.api.core_facade import prompt_eval_get_run

    try:
        return _as_item(await prompt_eval_get_run(run_id=run_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
