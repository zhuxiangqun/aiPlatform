"""Agent 编排端到端行为平面 — 真实 Harness（非 DummyHarness）+ 审批边界。

补的空白：现有所有 execute 端点测试都用 DummyHarness 全量替换 Harness，从不验证
真实 Harness 的权限边界。本文件用共享的进程内 TestClient（conftest `http_client`，
全程只 reload 一次）验证 deny-by-default：无 EXECUTE 权限的 user → 403
PERMISSION_DENIED，编排在 LLM 调用前被权限层拦截（CLAUDE.md §11/§5.11 安全红线）。

未含 authorized happy-path 的原因：无模型测试环境下它只会降级返回 "No model
available"（验证价值有限），且 server lifespan 未取消其后台 task（详见 honest_status）。
"""


def test_agent_execute_denies_unauthorized(http_client):
    """deny-by-default：无 EXECUTE 权限的 user 调 execute → 403，真实 Harness 权限层拦截。"""
    r = http_client.post(
        "/api/core/agents/conversational_agent/execute",
        json={"input": {"message": "hi"}, "user_id": "unauthorized_user", "session_id": "s1"},
    )
    assert r.status_code == 403, r.text
    body = r.json()
    assert body.get("ok") is False, body
    assert (body.get("error") or {}).get("code") == "PERMISSION_DENIED", body
