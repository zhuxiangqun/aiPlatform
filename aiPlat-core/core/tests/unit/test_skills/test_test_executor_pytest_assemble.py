"""test_executor: pytest mode must assemble code from code_split input_artifacts."""
from __future__ import annotations

import asyncio

from core.engine.skills.test_executor.handler import (
    _assemble_code_from_params,
    _execute_body,
    _file_blocks_have_bodies,
    _hydrate_params,
)


def test_file_blocks_have_bodies_rejects_path_only_stub():
    stub = (
        "## FILE: backend/app/main.py\n"
        "## FILE: backend/app/routers/reports.py\n\n"
        "补充后我将按 Step B 执行\n"
    )
    assert _file_blocks_have_bodies(stub) is False


def test_file_blocks_have_bodies_accepts_real_test_file():
    body = (
        "## FILE: backend/tests/test_health.py\n"
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n\n"
        "def test_health():\n"
        "    c = TestClient(app)\n"
        "    assert c.get('/api/health').status_code == 200\n"
    )
    assert _file_blocks_have_bodies(body) is True


def test_assemble_merges_scaffold_fe_be_without_code_key():
    params = {
        "test_execution_mode": "pytest",
        "test_cases": "## FILE: backend/app/main.py\n\n拒绝编造\n",
        "project_scaffold": (
            "## FILE: backend/requirements.txt\nfastapi==0.115.6\npytest==8.3.4\n"
            "## FILE: backend/app/main.py\nfrom fastapi import FastAPI\napp = FastAPI()\n"
        ),
        "frontend_code": "## FILE: frontend/package.json\n{\"name\":\"fe\"}\n",
        "backend_code": (
            "## FILE: backend/app/main.py\n"
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n\n"
            "@app.get('/api/health')\n"
            "def health():\n"
            "    return {'status': 'ok'}\n"
        ),
    }
    blob = _assemble_code_from_params(params)
    assert "## FILE: backend/requirements.txt" in blob
    assert "## FILE: frontend/package.json" in blob
    assert "@app.get('/api/health')" in blob
    # path-only QA refusal must not be appended
    assert "拒绝编造" not in blob


def test_hydrate_sets_code_in_pytest_mode():
    params = {
        "test_execution_mode": "pytest",
        "project_scaffold": "## FILE: backend/app/main.py\nfrom fastapi import FastAPI\napp = FastAPI()\n",
    }
    out = _hydrate_params(params)
    assert "## FILE: backend/app/main.py" in str(out.get("code") or "")


def test_pytest_mode_missing_code_does_not_document_check_approve():
    result = asyncio.get_event_loop().run_until_complete(
        _execute_body({"test_execution_mode": "pytest", "project": "demo"})
    )
    assert result.get("error") == "pytest_mode_missing_code"
    assert result.get("recommendation") == "NEEDS_FIX"
    assert (result.get("header") or {}).get("test_mode") == "pytest"


def test_lang_tag_pattern_strips_bare_python_eof():
    from core.engine.skills.test_executor.handler import _lang_tag_pattern

    assert _lang_tag_pattern().sub("", "python", count=1) == ""
    assert _lang_tag_pattern().sub("", "python\nfrom x import y\n", count=1) == "from x import y\n"
