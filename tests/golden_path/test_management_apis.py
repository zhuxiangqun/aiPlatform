"""
管理接口行为平面 — 诊断中心 / 系统概览。

验证这些管理端点是真执行（非空壳 stub）——能端到端跑通、不崩、
返回合法契约结构。复用 conftest 的 session http_client（1 reload）。

诚实排除：Agent 评估依赖 LLM（EvalRunner → agent.execute → sys_llm_generate），
无模型环境降级为 "No model available"，同 Agent 编排 D2 的困境，无法可靠验证。
"""


def test_diagnostics_run_all_quick(http_client):
    """诊断中心 run-all(quick=true) 能端到端跑通、不崩、返回合法结构。

    quick=true 跳过 LSP/e2e/security 等慢的外部检查，其余 15 个诊断类别
    （code_intel/capability/skill_lint/wiki_health 等）离线可跑。
    各子检查有 try/except 保护，一个失败不影响整体返回。
    """
    r = http_client.post("/api/core/diagnostics/run-all", params={"quick": "true"})
    assert r.status_code == 200, f"诊断端点返回非 200: {r.status_code} {r.text[:300]}"
    body = r.json()
    assert "categories" in body, f"缺 categories: {list(body.keys())[:8]}"
    assert "run_id" in body, f"缺 run_id: {list(body.keys())[:8]}"
    # 顶层有 overall_score/overall_grade + 统计字段，结构因 quick/full 模式不同
    assert (
        "overall_score" in body
        or "overall_grade" in body
        or "pass" in body
        or "warn" in body
    ), f"缺统计字段: {list(body.keys())[:8]}"


def test_overview_refresh(http_client):
    """系统概览(refresh=true) 能端到端跑通、不崩、返回四层结构。

    refresh=true 清除缓存，重新调用 InfraModelManager 等收集层状态。
    收集失败有 try/except 保护（不崩、但返回空数据或错误标记）。
    """
    r = http_client.get("/api/core/overview", params={"refresh": "true"})
    assert r.status_code == 200, f"概览端点返回非 200: {r.status_code} {r.text[:300]}"
    body = r.json()
    for layer in ("infra", "core", "platform", "app"):
        assert layer in body, f"缺 {layer} 层，keys: {list(body.keys())}"
        assert isinstance(body[layer], dict), f"{layer} 不是 dict: {type(body[layer])}"
    assert "status" in body["infra"], f"infra 层缺 status: {body['infra'].keys()}"
