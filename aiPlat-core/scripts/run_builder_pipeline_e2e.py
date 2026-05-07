"""
端到端流水线测试：使用 Project Workbench + PipelineEngine。
验证：团队组建 → 创建项目 → PM对话 → PRD确认 → HITL → 循环修复。
使用真实 DeepSeek LLM。
"""

from __future__ import annotations

import asyncio, json, os, sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_env_local = os.path.join(os.path.dirname(__file__), "..", "..", ".env.local")
if os.path.exists(_env_local):
    with open(_env_local) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                if _k and _v and _k not in os.environ:
                    os.environ[_k] = _v
    print(f"Loaded env from {_env_local}")

os.environ.setdefault("AIPLAT_LLM_PROVIDER", "deepseek")


def _print_reply(label: str, reply: str, max_chars: int = 600):
    print(f"\n--- {label} ---")
    print(reply[:max_chars])
    if len(reply) > max_chars:
        print(f"... (共 {len(reply)} 字符)")


async def main():
    from core.harness.utils.model_injection import create_selected_adapter

    print("=" * 60)
    print("  Project Workbench 端到端测试 (DeepSeek)")
    print("=" * 60)

    # ── Step 1: 创建 LLM adapter ──
    print("\n[1] 创建 DeepSeek LLM adapter...")
    model = create_selected_adapter(model_name="deepseek-chat")

    # ── Step 2: 组装团队（直接创建 team stages） ──
    from core.services.builder_team_service import BuilderTeamService
    from core.schemas_builder import TeamAssembleRequest, PipelineStageConfig

    team_svc = BuilderTeamService(model=model)

    stages = [
        PipelineStageConfig(id="architect", agent_id="architect_agent", agent_name="系统架构师",
                             category="engineering", phase="design", order=0, hitl=True,
                             hitl_phase="awaiting_architecture_approval",
                             input_artifacts=["prd"], output_artifact="architecture"),
        PipelineStageConfig(id="programmer", agent_id="programmer_agent", agent_name="程序员",
                             category="engineering", phase="development", order=1,
                             input_artifacts=["prd", "architecture"], output_artifact="code"),
        PipelineStageConfig(id="qa_gen", agent_id="qa_agent", agent_name="测试经理",
                             category="quality", phase="testing", order=2, hitl=True,
                             hitl_phase="awaiting_test_plan_approval",
                             input_artifacts=["prd"], output_artifact="test_plan"),
        PipelineStageConfig(id="qa_exec", agent_id="qa_agent", agent_name="测试经理",
                             category="quality", phase="testing", order=3,
                             retry_target_id="programmer",
                             input_artifacts=["prd", "code", "test_plan"],
                             output_artifact="test_report"),
    ]
    team = await team_svc.create_team(TeamAssembleRequest(
        name="标准研发团队", description="PM + Architect + Programmer + QA", stages=stages,
    ))
    print(f"    team_id: {team.team_id} ({team.name}, {len(team.stages)} stages)")

    # ── Step 3: 创建项目 ──
    from core.services.builder_project_service import BuilderProjectService
    from core.schemas_builder import ProjectCreateRequest

    proj_svc = BuilderProjectService(model=model, team_service=team_svc)
    project = await proj_svc.create_project(ProjectCreateRequest(
        name="需求驱动开发助手",
        description="构建一个需求驱动开发助手：用户通过自然语言描述需求→PM Agent多轮对话生成PRD→用户确认后自动启动Architect→Programmer→QA流水线→QA自动根因分析并回退修复",
        team_id=team.team_id,
    ))
    print(f"    project_id: {project.project_id} ({project.name})")

    project_id = project.project_id

    # ── Step 4: PM 多轮对话 ──
    print("\n[4.1] PM 对话第 1 轮...")
    resp = await proj_svc.chat(project_id,
        "我需要构建一个需求驱动开发助手。请先分析信息缺口："
        "scope（新增Skill还是Agent还是组合）、界面形式、代码输出格式。"
    )
    _print_reply(f"PM reply (prd_ready={resp.get('prd_ready')})", resp.get("reply", ""))
    prd_ready = resp.get("prd_ready")

    if not prd_ready:
        print("\n[4.2] PM 对话第 2 轮...")
        resp = await proj_svc.chat(project_id,
            "Scope 是组合型：4个Agent + 8个Skill + LangGraph流水线 + REST API + 前端页面。"
            "界面是 Web 页面（React + TypeScript + Tailwind）。"
            "代码输出格式同时涉及 SKILL.md v2 和 AGENT.md。信息已充分，请直接生成 PRD JSON。"
        )
        _print_reply(f"PM reply (prd_ready={resp.get('prd_ready')})", resp.get("reply", ""))
        prd_ready = resp.get("prd_ready")

    if not prd_ready:
        print("\n[4.3] 追加...")
        resp = await proj_svc.chat(project_id, "直接输出 PRD JSON，附带 <!-- PRD_READY -->")
        _print_reply("PM final", resp.get("reply", ""))

    # ── Step 5: 确认 PRD ──
    print("\n[5] 确认 PRD...")
    confirm = await proj_svc.confirm_prd(project_id)
    print(f"    phase: {confirm.get('phase')}")

    # ── Step 6: 启动流水线 ──
    print("\n[6] 启动流水线 (使用团队 stages)...")
    result = await proj_svc.start_pipeline(project_id)
    phase = result.get("phase", "")
    run_id = result.get("run_id", "")
    print(f"    phase: {phase}  run_id: {run_id}")

    # ── Step 7: HITL approvals ──
    if "awaiting_architecture_approval" in phase:
        print("\n[7] HITL: 确认架构设计...")
        result = await proj_svc.approve_stage(project_id)
        phase = result.get("phase", "")
        print(f"    phase: {phase}")

    if "awaiting_test_plan_approval" in phase:
        print("\n[8] HITL: 确认测试用例...")
        result = await proj_svc.approve_stage(project_id)
        phase = result.get("phase", "")
        print(f"    phase: {phase}")

    # ── Step 9: 结果 ──
    full_state = await proj_svc.get_project_state(project_id)
    state = full_state.get("state", {})
    runs = full_state.get("runs", [])

    print(f"\n{'='*60}")
    print("  Pipeline 执行结果")
    print(f"{'='*60}")
    print(f"  Phase: {phase}")
    print(f"  Tokens: {state.get('tokens_used', 0)}/{state.get('tokens_budget', 0)}")
    print(f"  Iterations: {state.get('iteration', 0)}")
    print(f"  Runs: {len(runs)}")

    arch = state.get("architecture") or {}
    if arch.get("components"):
        print(f"\n  ══ 架构师 ══  组件: {len(arch['components'])}")

    code = state.get("code") or {}
    files = code.get("files", [])
    if files:
        print(f"\n  ══ 程序员 ══  文件: {len(files)}  Skills: {code.get('skills_created', [])}")

    report = state.get("test_report") or {}
    if report:
        print(f"\n  ══ QA ══  pass_rate: {(report.get('pass_rate', 0)*100):.0f}%  "
              f"rec: {report.get('recommendation')}")

    err = state.get("error", "")
    if err:
        print(f"\n  ⚠️  {err}")

    output_dir = state.get("output_dir", "")
    if output_dir:
        print(f"\n  输出目录: {output_dir}")

    print(f"\n{'='*60}")
    print("  测试完成")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
