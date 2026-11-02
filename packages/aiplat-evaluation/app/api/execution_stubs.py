"""B1-L — dynamic execution routes return 503 (not cohost-in-another-port).

Honesty:
- API hosts read/store; execute plane waits for B2-L Worker allowlist.
- Unified error body per B1_ROUTE_MATRIX.md.
- process_split_authorized remains false.
"""
from __future__ import annotations

from fastapi import FastAPI, Request

from app.auth import require_bearer
from app.errors import execution_not_migrated_response, sandbox_required_response


async def _stub_skill_run(request: Request, suite_id: str):
    require_bearer(request)
    return execution_not_migrated_response(runner_id="skill_suite")


async def _stub_prompt_eval_run(request: Request):
    require_bearer(request)
    return execution_not_migrated_response(runner_id="prompt_eval")


async def _stub_arena_run(request: Request):
    require_bearer(request)
    return execution_not_migrated_response(runner_id="arena")


async def _stub_kb_eval_run(request: Request):
    require_bearer(request)
    return execution_not_migrated_response(runner_id="kb_rag")


async def _stub_http_probe(request: Request):
    require_bearer(request)
    return sandbox_required_response(runner_id="http_probe")


async def _stub_cli_probe(request: Request):
    require_bearer(request)
    return sandbox_required_response(runner_id="cli_probe")


def register_execution_stubs(application: FastAPI) -> None:
    prefix = "/api/platform/apps/eval"
    application.add_api_route(
        f"{prefix}/skill-evals/suites/{{suite_id}}/run",
        _stub_skill_run,
        methods=["POST"],
    )
    application.add_api_route(
        f"{prefix}/prompts/eval/runs",
        _stub_prompt_eval_run,
        methods=["POST"],
    )
    application.add_api_route(
        f"{prefix}/arena/run",
        _stub_arena_run,
        methods=["POST"],
    )
    application.add_api_route(
        f"{prefix}/kb-eval/run",
        _stub_kb_eval_run,
        methods=["POST"],
    )
    application.add_api_route(
        f"{prefix}/probes/http",
        _stub_http_probe,
        methods=["POST"],
    )
    application.add_api_route(
        f"{prefix}/probes/cli",
        _stub_cli_probe,
        methods=["POST"],
    )


def _wire_execution_stubs(application: FastAPI) -> None:
    """Same-file caller for method_verify."""
    register_execution_stubs(application)
