"""Coding Agents must not auto_done on clarify-only / thin ## FILE stubs."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.harness.execution.loop._facade import ReActLoop
from core.harness.interfaces.loop import LoopConfig, LoopState, LoopStateEnum


CORE = Path(__file__).resolve().parents[3]


def test_coding_deliverable_veto_wired_into_acceptance_gate():
    src = (CORE / "harness/execution/loop/_facade.py").read_text(encoding="utf-8")
    assert "def _coding_deliverable_veto" in src
    assert "coding_veto = self._coding_deliverable_veto(state)" in src
    assert "is_non_deliverable_coding_output" in src
    assert "skill_delivery=once requires a successful primary skill call" in src


def test_pm_skill_once_does_not_apply_coding_product_veto():
    """requirement_analysis Agents use skill_delivery=once but not code_generation."""
    loop = ReActLoop(config=LoopConfig(max_steps=6), model=None, tools=[], skills=[])
    prd = (
        "# PRD 草稿\n工人拍照上报、班组长审批、派修。照片不能传到公网。"
        "钉钉 API 文档未开放。FR-001 上报 / FR-002 审批 / FR-003 派修。"
    )
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "_skill_delivery": "once",
            "_primary_skill_delivered": "requirement_analysis",
            "_bound_skill_ids": ["requirement_analysis"],
            "_user_task": (
                "请按产品经理职责完成一次可验收的需求分析草稿。"
                "现场巡检报障：上报、审批、派修。照片不能传到公网。"
            ),
            "output": prd,
        },
        step_count=2,
    )
    assert loop._coding_deliverable_veto(state) is None


def test_coding_veto_blocks_clarify_without_skill_when_once():
    loop = ReActLoop(config=LoopConfig(max_steps=6), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "_skill_delivery": "once",
            "_bound_skill_ids": ["code_generation"],
            "_user_task": "根据 api_contracts 生成前端列表页代码",
            "output": (
                "我理解你想做一个前端页面。请确认以下信息是否已经准备好："
                "api_contracts、组件清单。如果你已经准备好，请告诉我，我们可以开始下一步。"
            ),
        },
        step_count=1,
    )
    reason = loop._coding_deliverable_veto(state)
    assert reason
    assert "primary skill" in reason or "skill_delivery=once" in reason


def test_coding_veto_blocks_thin_file_stub_after_fake_delivery():
    loop = ReActLoop(config=LoopConfig(max_steps=6), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "_skill_delivery": "once",
            "_primary_skill_delivered": "code_generation",
            "_bound_skill_ids": ["code_generation"],
            "_user_task": "生成 FastAPI 路由与 Pydantic model",
            "output": "DONE\n## FILE: app/main.py\n",
        },
        step_count=2,
    )
    reason = loop._coding_deliverable_veto(state)
    assert reason
    assert "thin" in reason or "stub" in reason or "clarify" in reason


def test_pending_coding_followup_prefers_autoreview():
    loop = ReActLoop(config=LoopConfig(max_steps=6), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "_bound_skill_ids": ["code_generation", "code-hygiene", "autoreview"],
            "_followup_skills_done": [],
        },
        step_count=2,
    )
    assert loop._pending_coding_followup(state) == "autoreview"
    state.context["_followup_skills_done"] = ["autoreview"]
    assert loop._pending_coding_followup(state) == "code-hygiene"


def test_coding_agents_bind_autoreview_and_roomy_max_steps():
    """FE/BE must bind autoreview and leave steps for gen→review→DONE (+ thin retry)."""
    home = Path.home() / ".aiplat" / "agents"
    for aid in ("frontend_engineer", "backend_developer"):
        p = home / aid / "AGENT.md"
        if not p.is_file():
            pytest.skip(f"{aid} AGENT.md not installed under ~/.aiplat")
        text = p.read_text(encoding="utf-8")
        assert "- autoreview" in text, f"{aid} missing required_skills: autoreview"
        assert "autoreview" in text.split("system_prompt:", 1)[-1][:400]
        import re

        m = re.search(r"max_steps:\s*(\d+)", text)
        assert m and int(m.group(1)) >= 10, f"{aid} max_steps too low for followup"


def test_coding_veto_rejects_pending_skill_call_envelope():
    loop = ReActLoop(config=LoopConfig(max_steps=6), model=None, tools=[], skills=[])
    env = (
        '{"type":"skill_call","skill":"code_generation","input":{'
        '"code":"' + ("export function x(){return 1}\\n" * 10) + '"}}'
    )
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "_bound_skill_ids": ["code_generation", "autoreview"],
            "_skill_delivery": "once",
            "_user_task": "根据 api_contracts 生成 TypeScript 前端代码",
            "output": env,
        },
        step_count=1,
    )
    veto = loop._coding_deliverable_veto(state)
    assert veto and "skill_call" in veto


def test_coding_veto_requires_autoreview_followup():
    loop = ReActLoop(config=LoopConfig(max_steps=10), model=None, tools=[], skills=[])
    code = (
        "## FILE: src/api/tasks.ts\n"
        "export async function getTasks() {\n"
        "  return apiClient.get('/api/tasks');\n"
        "}\n" * 3
    )
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "_bound_skill_ids": ["code_generation", "autoreview"],
            "_skill_delivery": "once",
            "_primary_skill_delivered": "code_generation",
            "_user_task": "根据 api_contracts 生成 TypeScript 前端代码",
            "output": code,
            "_followup_skills_done": [],
        },
        step_count=3,
    )
    veto = loop._coding_deliverable_veto(state)
    assert veto and "autoreview" in veto


def test_coding_veto_fail_open_after_three_vetoes():
    """After 3 coding vetoes, allow DONE so finalize can seal (QR may still fail)."""
    loop = ReActLoop(config=LoopConfig(max_steps=10), model=None, tools=[], skills=[])
    code = (
        "## FILE: src/api/tasks.ts\n"
        "export async function getTasks() {\n"
        "  return apiClient.get('/api/tasks');\n"
        "}\n" * 3
    )
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "_bound_skill_ids": ["code_generation", "autoreview"],
            "_skill_delivery": "once",
            "_primary_skill_delivered": "code_generation",
            "_user_task": "根据 api_contracts 生成 TypeScript 前端代码",
            "output": code,
            "_followup_skills_done": [],
            "_acceptance_veto_count": 3,
        },
        step_count=5,
    )
    assert loop._coding_deliverable_veto(state) is None
    assert state.context.get("_coding_veto_exhausted") is True
    assert "autoreview" in str(state.context.get("_coding_veto_last_reason") or "")


def test_coding_veto_followup_fail_open_at_two():
    """Follow-up-only vetoes exhaust at 2 to avoid nested LLM hang (run-1d72)."""
    loop = ReActLoop(config=LoopConfig(max_steps=10), model=None, tools=[], skills=[])
    code = (
        "## FILE: src/api/tasks.ts\n"
        "export async function getTasks() {\n"
        "  return apiClient.get('/api/tasks');\n"
        "}\n" * 3
    )
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "_bound_skill_ids": ["code_generation", "autoreview"],
            "_skill_delivery": "once",
            "_primary_skill_delivered": "code_generation",
            "_user_task": "根据 api_contracts 生成 TypeScript 前端代码",
            "output": code,
            "_followup_skills_done": [],
            "_acceptance_veto_count": 2,
        },
        step_count=4,
    )
    assert loop._coding_deliverable_veto(state) is None
    assert state.context.get("_coding_veto_exhausted") is True


def test_skill_scope_ignores_off_spec_path_split():
    """code_generation scope=skill must accept baseURL+/reports apiClient (run-054f)."""
    from core.management.execution_quality_review import is_non_deliverable_coding_output

    # 「仅输出 ## FILE」skips frontend_module_incomplete so this isolates path-split.
    inp = (
        "前端编码冒烟 TypeScript：仅输出 ## FILE，生成 apiClient "
        "POST /api/v1/inspection/reports；调用 code_generation → DONE。"
    )
    code = (
        "## FILE: src/apiClient.ts\n```typescript\n"
        "import axios from 'axios';\n"
        "const API_BASE_URL = '/api/v1/inspection';\n"
        "export const apiClient = {\n"
        "  async createReport(reporter_id: string, equipment_id: string, "
        "description: string, photo_uris: string[]) {\n"
        "    await axios.post(`${API_BASE_URL}/reports`, "
        "{ reporter_id, equipment_id, description, photo_uris });\n"
        "  }\n"
        "};\n"
        "```\n"
    )
    assert not is_non_deliverable_coding_output(
        input_text=inp,
        output_text=code,
        raw_out={"code": code, "language": "typescript", "text": code},
        scope="skill",
    )


def test_auto_followup_dispatch_wired():
    """After primary delivery, observe auto-dispatches autoreview (no LLM nudge loop)."""
    src = (CORE / "harness/execution/loop/_facade.py").read_text(encoding="utf-8")
    assert "_auto_followup_dispatched" in src
    assert "observe_auto_followup_seal" in src
    assert "auto_followup_seal_close" in src
    assert "ParsedActionCall" in src
    assert "not blocking coding seal" in src
    assert "before_auto_followup" in src
    assert "AIPLAT_AUTO_FOLLOWUP_TIMEOUT" in src
    # Old nudge exhaustion path must stay gone (caused incomplete seals).
    assert "observe_followup_exhausted" not in src
    assert "nudges >= 2" not in src


def test_orphan_watchdog_skips_prep_stall_when_skill_progress():
    """Skill success must not be killed as pre_llm_prep_stalled (run-2ff29a641bf5)."""
    src = (CORE / "api/routers/executions_trace.py").read_text(encoding="utf-8")
    assert "has_exec_progress" in src
    assert 'kind_i == "skill"' in src
    assert "run-2ff29a641bf5" in src


def test_primary_skill_timeout_seals_in_observe():
    """code_generation timeout must FINISH the loop, not nest more reason LLMs."""
    src = (CORE / "harness/execution/loop/_facade.py").read_text(encoding="utf-8")
    assert "observe_primary_skill_timeout" in src
    assert "primary_skill_timeout_seal" in src
    assert "Skill execution timed out" in src or "llm_timeout" in src


def test_coding_veto_still_blocks_followup_before_exhaustion():
    loop = ReActLoop(config=LoopConfig(max_steps=10), model=None, tools=[], skills=[])
    code = (
        "## FILE: src/api/tasks.ts\n"
        "export async function getTasks() {\n"
        "  return apiClient.get('/api/tasks');\n"
        "}\n" * 3
    )
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "_bound_skill_ids": ["code_generation", "autoreview"],
            "_skill_delivery": "once",
            "_primary_skill_delivered": "code_generation",
            "_user_task": "根据 api_contracts 生成 TypeScript 前端代码",
            "output": code,
            "_followup_skills_done": [],
            "_acceptance_veto_count": 1,
        },
        step_count=3,
    )
    veto = loop._coding_deliverable_veto(state)
    assert veto and "autoreview" in veto
    assert not state.context.get("_coding_veto_exhausted")


def test_inference_steers_to_followup_not_blind_done():
    """skill_delivery=once must not force DONE while autoreview is still pending."""
    src = (CORE / "harness/execution/loop/inference.py").read_text(encoding="utf-8")
    assert "Delivery follow-up" in src
    assert "_pending_coding_followup" in src
    assert "or any skill" not in src


def test_act_rerun_primary_steers_to_autoreview():
    """Re-calling code_generation after delivery should point at autoreview, not DONE."""
    import asyncio

    loop = ReActLoop(config=LoopConfig(max_steps=10), model=None, tools=[], skills=[])
    state = LoopState(
        current=LoopStateEnum.ACTING,
        context={
            "_skill_delivery": "once",
            "_primary_skill_delivered": "code_generation",
            "_primary_skill_output": "## FILE: a.ts\nexport const x = 1\n",
            "_bound_skill_ids": ["code_generation", "autoreview"],
            "_followup_skills_done": [],
            "reasoning": (
                '{"type":"skill_call","skill":"code_generation",'
                '"input":{"code":"export const x=1"}}'
            ),
        },
        step_count=2,
    )

    out = asyncio.run(loop._act(state))
    assert "autoreview" in out
    assert "already delivered" in out
    assert "Next call skill" in out


def test_coding_veto_allows_real_code_body():
    loop = ReActLoop(config=LoopConfig(max_steps=6), model=None, tools=[], skills=[])
    code = (
        "## FILE: src/api/tasks.ts\n"
        "export async function getTasks(params: { page?: number }) {\n"
        "  return apiClient.get('/api/tasks', { params });\n"
        "}\n"
        "export async function createTask(body: { title: string }) {\n"
        "  return apiClient.post('/api/tasks', body);\n"
        "}\n"
    )
    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "_skill_delivery": "once",
            "_primary_skill_delivered": "code_generation",
            "_bound_skill_ids": ["code_generation"],
            "_user_task": "根据 api_contracts 生成前端 API 层",
            "output": code,
        },
        step_count=2,
    )
    assert loop._coding_deliverable_veto(state) is None


@pytest.mark.asyncio
async def test_auto_done_clarify_is_vetoed_for_skill_once():
    """Regression: frontend_engineer completed with 「请确认是否准备好」 — must not FINISH."""
    from unittest.mock import AsyncMock, MagicMock, patch

    loop = ReActLoop(config=LoopConfig(max_steps=6), model=None, tools=[], skills=[])
    loop._trigger_hook = AsyncMock()  # type: ignore[method-assign]
    loop._apply_todo_done_markers = AsyncMock()  # type: ignore[method-assign]
    loop._detect_quality_drift = lambda reasoning, state: (False, "")  # type: ignore[method-assign]
    loop._skill_delivery_body = lambda state: ""  # type: ignore[method-assign]

    clarify = (
        "我理解你的需求。请确认以下信息是否已经准备好：Architecture 中的 api_contracts。"
        "如果你已经准备好，请告诉我，我们就可以开始生成前端代码。"
    )

    async def _fake_reason(state: LoopState):
        return clarify

    loop._reason = _fake_reason  # type: ignore[method-assign]

    state = LoopState(
        current=LoopStateEnum.REASONING,
        context={
            "_run_id": "run-clarify-veto",
            "_agent_id": "frontend_engineer",
            "_skill_delivery": "once",
            "_bound_skill_ids": ["code_generation"],
            "_user_task": "根据 api_contracts 生成前端代码，使用 ## FILE: 格式",
            "messages": [{"role": "user", "content": "根据 api_contracts 生成前端代码"}],
        },
        step_count=1,
    )

    store = MagicMock()
    store.add_syscall_event = AsyncMock()
    fin = AsyncMock(return_value=True)

    with patch(
        "core.services.execution_store.get_execution_store", return_value=store
    ), patch(
        "core.harness.utils.execute_session.finalize_agent_after_skill_delivery", fin
    ):
        out = await loop.step(state)

    assert out.current != LoopStateEnum.FINISHED
    assert out.current == LoopStateEnum.REASONING
    assert int(out.context.get("_acceptance_veto_count") or 0) >= 1
    fin.assert_not_awaited()
