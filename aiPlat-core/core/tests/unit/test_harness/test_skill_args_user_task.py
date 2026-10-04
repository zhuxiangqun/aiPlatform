"""skill_call must forward the user PRD, not the skill description blurb."""

from __future__ import annotations

from core.harness.execution.loop._facade import ReActLoop
from core.harness.interfaces.loop import LoopState, LoopStateEnum


def _state(user_task: str, **extra) -> LoopState:
    ctx = {"_user_task": user_task, "task": user_task}
    ctx.update(extra)
    return LoopState(
        current=LoopStateEnum.INIT,
        context=ctx,
    )


def test_replaces_skill_description_boilerplate():
    user = (
        "现场巡检报障小应用；照片不可上公网；钉钉 API 未开放；"
        "6 周试点一个车间；需要分期切片与风险。"
    )
    args = {"input": "根据PRD需求设计完整、详细、可落地的系统架构，输出结构化JSON。"}
    out = ReActLoop._inject_user_task_into_skill_args(_state(user), args)
    assert "巡检" in str(out.get("input"))
    assert "6 周" in str(out.get("input")) or "分期" in str(out.get("input"))
    assert "根据PRD需求设计" not in str(out.get("input"))


def test_keeps_rich_user_payload():
    user = "现场巡检报障；不上公网；6 周试点"
    rich = user + "；额外补充：班组长审批后派修，要看板。"
    out = ReActLoop._inject_user_task_into_skill_args(
        _state(user), {"input": rich}
    )
    assert out["input"] == rich


def test_fills_missing_input_key():
    user = (
        "现场巡检报障小应用；照片不可上公网；钉钉 API 未开放；"
        "需要数据流与安全合规章节，以及 6 周分期切片与风险。"
    )
    out = ReActLoop._inject_user_task_into_skill_args(_state(user), {})
    assert out.get("input") == user


def test_preferred_language_fills_when_model_omits_language():
    """FE agent preferred_language=typescript when task does not name a language."""
    user = (
        "根据 Architecture 中的 api_contracts 生成前端代码；"
        "实现报障列表页与创建报障表单的可运行切片。"
    )
    out = ReActLoop._inject_preferred_language_into_skill_args(
        _state(user, _preferred_language="typescript"),
        "code_generation",
        {"input": user},
    )
    assert out.get("language") == "typescript"
    assert out.get("_language_locked") is True


def test_envelope_locked_language_mismatch_without_task_lang():
    """preferred typescript + Python body fails even when task omits 'TypeScript'."""
    from core.management.execution_quality_review import _coding_contract_fail_codes

    inp = (
        "根据 Architecture 中的 api_contracts 生成前端代码；"
        "实现报障列表页与创建报障表单的可运行切片。"
    )
    bad = (
        "## FILE: app/main.py\n```python\n"
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.post('/api/v1/inspection/reports')\n"
        "async def create(body: dict):\n"
        "    return body\n"
        "```\n"
    )
    codes = _coding_contract_fail_codes(
        inp,
        bad,
        {"code": bad, "language": "typescript", "_language_locked": True},
    )
    assert "language_mismatch" in codes
    # Skill gate also passes text=code — unwrap must not drop the lock.
    codes2 = _coding_contract_fail_codes(
        inp,
        bad,
        {
            "code": bad,
            "text": bad,
            "language": "typescript",
            "_language_locked": True,
        },
    )
    assert "language_mismatch" in codes2


def test_envelope_unlocked_python_default_with_ts_body_ok():
    from core.management.execution_quality_review import _coding_contract_fail_codes

    inp = "生成一段可运行的 API 客户端切片（路径 /api/tasks）。"
    good = (
        "## FILE: src/apiClient.ts\n```typescript\n"
        "export async function listTasks() {\n"
        "  return fetch('/api/tasks');\n"
        "}\n```\n"
    )
    codes = _coding_contract_fail_codes(
        inp,
        good,
        {"code": good, "language": "python"},  # unlocked stale default
    )
    assert "language_mismatch" not in codes


def test_preferred_language_task_typescript_wins_over_agent_default():
    user = (
        "请用 TypeScript 写 apiClient：POST /api/v1/inspection/reports；"
        "字段 reporter_id, equipment_id, description, photo_uris[]。"
    )
    out = ReActLoop._inject_preferred_language_into_skill_args(
        _state(user, _preferred_language="python"),
        "code_generation",
        {"input": user},
    )
    assert out.get("language") == "typescript"


def test_preferred_language_wins_over_model_python_arg():
    """Model echoing schema default python must not override FE preferred_language."""
    user = "写一段巡检报障前端代码切片，可运行。"
    out = ReActLoop._inject_preferred_language_into_skill_args(
        _state(user, _preferred_language="typescript"),
        "code_generation",
        {"input": user, "language": "python"},
    )
    assert out.get("language") == "typescript"
    assert out.get("_language_locked") is True


def test_preferred_language_task_python_wins_over_agent_typescript():
    user = (
        "请用 Python FastAPI 实现 POST /api/v1/inspection/reports 路由 + Pydantic model；"
        "字段 reporter_id, equipment_id, description, photo_uris[]。"
    )
    out = ReActLoop._inject_preferred_language_into_skill_args(
        _state(user, _preferred_language="typescript"),
        "code_generation",
        {"input": user, "language": "typescript"},
    )
    assert out.get("language") == "python"
    assert out.get("_language_locked") is True


def test_preferred_language_ignores_non_codegen_skills():
    out = ReActLoop._inject_preferred_language_into_skill_args(
        _state("x" * 50, _preferred_language="typescript"),
        "autoreview",
        {},
    )
    assert "language" not in out


def test_injects_test_cases_from_execute_payload():
    cases = [{"id": "SMK-001", "title": "上报", "steps": ["提交"], "expected": "工单号"}]
    st = _state("请执行下列 test_cases " + ("x" * 40), _execute_input={"message": "run", "test_cases": cases})
    out = ReActLoop._inject_execute_payload_into_skill_args(st, {"input": "请执行测试"})
    assert out["test_cases"] == cases


def test_does_not_overwrite_skill_provided_test_cases():
    cases = [{"id": "A"}]
    other = [{"id": "B"}]
    st = _state("请执行 " + ("x" * 40), _execute_input={"test_cases": cases})
    out = ReActLoop._inject_execute_payload_into_skill_args(st, {"test_cases": other})
    assert out["test_cases"] == other


def test_overwrites_empty_test_cases_list_from_model():
    cases = [{"id": "SMK-001", "title": "上报"}]
    st = _state("请执行下列 test_cases " + ("x" * 40), _execute_input={"test_cases": cases})
    out = ReActLoop._inject_execute_payload_into_skill_args(st, {"test_cases": []})
    assert out["test_cases"] == cases