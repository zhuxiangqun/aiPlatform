"""code_generation must read ReAct params.input and reject clarify prose as success."""

from __future__ import annotations

import pytest

from core.apps.skills.base import CodeGenerationSkill


def test_resolve_requirements_accepts_input_alias():
    assert "POST /api" in CodeGenerationSkill._resolve_requirements(
        {"input": "实现 POST /api/v1/inspection/reports 路由"}
    )
    assert CodeGenerationSkill._resolve_requirements({"requirements": "x"}) == "x"
    assert CodeGenerationSkill._resolve_requirements({}) == ""


def test_has_code_substance_rejects_english_clarify_mentioning_class():
    prose = (
        "I need more details on what specific Python code you want me to write. "
        "Could you please provide more context or specify the function or class "
        "you're looking for?"
    )
    assert CodeGenerationSkill._has_code_substance(prose) is False


def test_has_code_substance_accepts_real_def():
    code = (
        "## FILE: app/main.py\n"
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.post('/api/v1/inspection/reports')\n"
        "async def create_report(body: dict):\n"
        "    return {'ok': True}\n"
    )
    assert CodeGenerationSkill._has_code_substance(code) is True


@pytest.mark.asyncio
async def test_execute_fails_when_requirements_missing(monkeypatch):
    skill = CodeGenerationSkill()
    skill.set_model(object())  # bypass model resolve; missing reqs fails first
    from core.harness.interfaces import SkillContext

    res = await skill.execute(SkillContext(session_id="t", user_id="u"), {"language": "python"})
    assert res.success is False
    assert "missing requirements" in str(res.error or "")


@pytest.mark.asyncio
async def test_execute_maps_input_and_rejects_clarify(monkeypatch):
    skill = CodeGenerationSkill()

    class _Fake:
        content = (
            "I understand you want a complete Python code snippet, but you haven't "
            "specified what kind of code you need. Are you looking for a class?"
        )

    async def _fake_llm(*a, **k):
        return _Fake()

    monkeypatch.setattr(
        "core.harness.syscalls.llm.sys_llm_generate",
        _fake_llm,
    )
    skill.set_model(object())
    from core.harness.interfaces import SkillContext

    res = await skill.execute(
        SkillContext(session_id="t", user_id="u"),
        {
            "input": "实现 POST /api/v1/inspection/reports 的 FastAPI 路由 + Pydantic model",
            "language": "python",
        },
    )
    assert res.success is False
    assert "thin" in str(res.error or "").lower() or "clarif" in str(res.error or "").lower()


@pytest.mark.asyncio
async def test_execute_patches_missing_auth_todo_deterministically(monkeypatch):
    """run-91896f56: prose ### TODO: auth → skill must inject // TODO: auth and pass."""
    skill = CodeGenerationSkill()

    class _Fake:
        content = (
            "## FILE: frontend/src/types.ts\n"
            "```typescript\n"
            "export type InspectionReportRequest = { description: string; severity?: string };\n"
            "export type InspectionReportResponse = { id: string; status: string };\n"
            "```\n\n"
            "## FILE: frontend/src/api/apiClient.ts\n"
            "```typescript\n"
            "import axios from 'axios';\n"
            "import type { InspectionReportRequest, InspectionReportResponse } from '../types';\n"
            "export const apiClient = axios.create({ baseURL: '/api/v1/inspection' });\n"
            "export async function postReports(\n"
            "  data: InspectionReportRequest\n"
            "): Promise<InspectionReportResponse> {\n"
            "  const response = await apiClient.post('/reports', data);\n"
            "  return response.data;\n"
            "}\n"
            "```\n\n"
            "## FILE: frontend/src/pages/ReportFaultPage.tsx\n"
            "```tsx\n"
            "import React, { useState } from 'react';\n"
            "import { postReports } from '../api/apiClient';\n"
            "import type { InspectionReportRequest } from '../types';\n"
            "export const ReportFaultPage: React.FC = () => {\n"
            "  const [data, setData] = useState<InspectionReportRequest>({ description: '' });\n"
            "  return (\n"
            "    <button onClick={() => postReports(data)}>Submit</button>\n"
            "  );\n"
            "};\n"
            "```\n\n"
            "### TODO: auth/鉴权\n"
            "在实际应用中需要添加鉴权逻辑。\n"
        )

    async def _fake_llm(*a, **k):
        return _Fake()

    monkeypatch.setattr("core.harness.syscalls.llm.sys_llm_generate", _fake_llm)
    skill.set_model(object())
    from core.harness.interfaces import SkillContext

    res = await skill.execute(
        SkillContext(session_id="t", user_id="u"),
        {
            "input": (
                "生成可组装前端模块 TypeScript："
                "## FILE: frontend/src/types.ts + apiClient.ts + pages/ReportFaultPage.tsx；"
                "POST /api/v1/inspection/reports；鉴权标 TODO。禁止假实现钉钉。"
            ),
            "language": "typescript",
            "_language_locked": True,
        },
    )
    assert res.success is True, res.error
    code = str((res.output or {}).get("code") or "")
    assert "// TODO: auth" in code
    assert "missing_auth_todo" not in str(res.error or "")


@pytest.mark.asyncio
async def test_execute_injects_run_id_from_params_into_llm_trace(monkeypatch):
    """Orphan watchdog needs llm:generate rows under the agent run_id."""
    skill = CodeGenerationSkill()
    seen = {}

    class _Fake:
        content = (
            "## FILE: api/reports.py\n"
            "from fastapi import APIRouter\n"
            "from pydantic import BaseModel\n"
            "router = APIRouter()\n"
            "class ReportIn(BaseModel):\n"
            "    reporter_id: str\n"
            "@router.post('/reports')\n"
            "async def create(body: ReportIn):\n"
            "    return body\n"
        )

    async def _fake_llm(*a, **k):
        seen["trace_context"] = k.get("trace_context") or {}
        return _Fake()

    monkeypatch.setattr("core.harness.syscalls.llm.sys_llm_generate", _fake_llm)
    skill.set_model(object())
    from core.harness.interfaces import SkillContext

    # _run_id only on params (as sys_skill_call prepares) — not on context.variables
    res = await skill.execute(
        SkillContext(session_id="skill-sess", user_id="u", variables={}),
        {
            "_run_id": "run-deadbeef001",
            "input": "实现 POST /api/v1/inspection/reports 的 FastAPI 路由",
            "language": "python",
        },
    )
    assert res.success is True
    tc = seen.get("trace_context") or {}
    assert tc.get("run_id") == "run-deadbeef001"
    assert "code_generation" in str(tc.get("parent_span_id") or "")


@pytest.mark.asyncio
async def test_execute_fails_locked_typescript_when_body_is_python(monkeypatch):
    """preferred_language lock + text+code envelope must still reject Python body."""
    skill = CodeGenerationSkill()

    class _Fake:
        content = (
            "## FILE: app/main.py\n```python\n"
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "@app.post('/api/v1/inspection/reports')\n"
            "async def create(body: dict):\n"
            "    return {'ok': True}\n"
            "```\n"
        )

    async def _fake_llm(*a, **k):
        return _Fake()

    monkeypatch.setattr("core.harness.syscalls.llm.sys_llm_generate", _fake_llm)
    skill.set_model(object())
    from core.harness.interfaces import SkillContext

    res = await skill.execute(
        SkillContext(session_id="t", user_id="u"),
        {
            # No 'TypeScript' word — mirrors FE preferred_language inject
            "input": (
                "根据 Architecture 中的 api_contracts 生成前端代码；"
                "实现报障列表页与创建报障表单的可运行切片。"
            ),
            "language": "typescript",
            "_language_locked": True,
        },
    )
    assert res.success is False
    codes = set((res.metadata or {}).get("contract_fail_codes") or [])
    assert "language_mismatch" in codes or "language_mismatch" in str(res.error or "")


@pytest.mark.asyncio
async def test_locked_language_not_overridden_by_python_word_in_task(monkeypatch):
    """When loop locks typescript, skill must not flip to python from stray words."""
    skill = CodeGenerationSkill()
    seen = {}

    class _Fake:
        content = (
            "## FILE: src/apiClient.ts\n```typescript\n"
            "export async function createReport(body: {\n"
            "  reporter_id: string; equipment_id: string;\n"
            "  description: string; photo_uris: string[];\n"
            "}) {\n"
            "  // TODO: auth/鉴权\n"
            "  return fetch('/api/v1/inspection/reports', {\n"
            "    method: 'POST', body: JSON.stringify(body),\n"
            "  });\n"
            "}\n```\n"
        )

    async def _fake_llm(model, msgs, **k):
        seen["user"] = (msgs or [{}])[-1].get("content", "")
        return _Fake()

    monkeypatch.setattr("core.harness.syscalls.llm.sys_llm_generate", _fake_llm)
    skill.set_model(object())
    from core.harness.interfaces import SkillContext

    res = await skill.execute(
        SkillContext(session_id="t", user_id="u"),
        {
            # Mentions Python only as a forbidden alternative — must stay locked TS
            "input": (
                "生成前端 apiClient（禁止 Python/FastAPI）；"
                "POST /api/v1/inspection/reports；鉴权未给出标 TODO。"
            ),
            "language": "typescript",
            "_language_locked": True,
        },
    )
    assert res.success is True
    assert "generate typescript code" in str(seen.get("user") or "").lower()
    assert (res.output or {}).get("language") == "typescript"
    assert (res.output or {}).get("_language_locked") is True
