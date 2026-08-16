#!/usr/bin/env python3
"""verify_agent_conversation.py — 阶段2 Agent 真实对话测试端到端验证。

创建对话式应用 → confirm PRD(直接传,跳过 PM 多轮对话) → recommend-team → start
→ 轮询 → 检查 test_report.header.test_mode == "agent_conversation"。

用法: python3 scripts/verify_agent_conversation.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

PLATFORM = "http://localhost:8003"


def _http(method: str, url: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}", "_detail": e.read().decode()[:300]}
    except urllib.error.URLError as e:
        return {"_error": "URLError", "_detail": str(e.reason)}


# 对话式 PRD — 明确"自然语言/多轮对话"信号，引导 LLM 推荐 agent_engineer
PRD = {
    "title": "智能客服助手",
    "description": "对话式智能客服，用户用自然语言咨询订单状态、退换货政策、产品信息",
    "functional_requirements": [
        "FR-001: 用户用自然语言咨询订单状态，助手查询知识库并友好回复",
        "FR-002: 用户咨询退换货政策，助手解释规则",
        "FR-003: 支持多轮对话追问澄清模糊需求",
    ],
    "user_stories": ["作为用户，我想用自然语言咨询，得到友好准确的回复"],
}


def main() -> int:
    # 1. 创建项目
    r = _http("POST", f"{PLATFORM}/platform/builder/projects", {
        "name": "智能客服助手-验证",
        "description": PRD["description"],
        "app_name": "qa_customer_service",
    })
    if isinstance(r, dict) and r.get("_error"):
        print(f"❌ create 失败: {r}")
        return 1
    project_id = (r or {}).get("project_id") if isinstance(r, dict) else ""
    if not project_id:
        print(f"❌ create 未返回 project_id: {r}")
        return 1
    print(f"✅ 创建项目: {project_id}")

    # 2. confirm PRD（直接传，跳过 PM 多轮对话）
    r = _http("POST", f"{PLATFORM}/platform/builder/projects/{project_id}/confirm", {"prd": PRD})
    if isinstance(r, dict) and r.get("_error"):
        print(f"❌ confirm 失败: {r}")
        return 1
    print("✅ confirm PRD")

    # 3. recommend-team（LLM 推荐，应含 agent_engineer）
    r = _http("POST", f"{PLATFORM}/platform/builder/projects/{project_id}/recommend-team", {})
    if isinstance(r, dict) and r.get("_error"):
        print(f"❌ recommend-team 失败: {r}")
        return 1
    plan_stages = r.get("plan_stages", []) if isinstance(r, dict) else []
    agents = [s.get("agent_id", "") for s in plan_stages if isinstance(s, dict)]
    print(f"✅ 推荐团队: {agents}")
    if "agent_engineer" not in agents and "agent_engineer" not in str(plan_stages):
        print("⚠️ 警告: 推荐团队不含 agent_engineer，可能不会生成 agent_app（但仍继续尝试）")

    # 4. rebuild（confirm 后 confirmed_prd 存在，走 rebuild 启动 pipeline，与前端 handleStart 一致）
    r = _http("POST", f"{PLATFORM}/platform/builder/projects/{project_id}/rebuild", {})
    if isinstance(r, dict) and r.get("_error"):
        print(f"❌ rebuild 失败: {r}")
        return 1
    print("✅ 启动构建，轮询中（最多 15 分钟）...")

    # 5. 轮询
    t0 = time.time()
    while time.time() - t0 < 900:
        st = _http("GET", f"{PLATFORM}/platform/builder/projects/{project_id}/state")
        state = st.get("state", {}) if isinstance(st, dict) else {}
        phase = st.get("phase", "?") if isinstance(st, dict) else "?"
        tr = (state.get("test_report") or {}).get("raw_output", "") if isinstance(state.get("test_report"), dict) else ""
        if tr:
            try:
                tr_obj = json.loads(tr) if tr.strip().startswith("{") else {}
                mode = (tr_obj.get("header") or {}).get("test_mode")
                print(f"\n=== test_report (test_mode={mode}) ===")
                print(f"recommendation: {tr_obj.get('recommendation')}")
                print(f"meta: {tr_obj.get('meta')}")
                for res in (tr_obj.get("test_results") or [])[:5]:
                    print(f"  [{res.get('id')}] {res.get('result')} agent={res.get('agent')} "
                          f"evidence={str(res.get('evidence',''))[:80]}")
                if mode == "agent_conversation":
                    print("\n✅✅ 验证成功: agent_conversation 路径已触发")
                    return 0
                print(f"\n❌ 未命中 agent_conversation（当前 {mode}），需排查")
                return 1
            except Exception as e:
                print(f"test_report 解析失败: {e}")
        print(f"  [{int(time.time() - t0)}s] phase={phase}")
        if phase == "paused":
            r = _http("POST", f"{PLATFORM}/platform/builder/projects/{project_id}/approve", {"feedback": "自动审批"})
            print(f"  → approve: {(r or {}).get('status', r) if isinstance(r, dict) else r}")
        if phase in ("done", "failed"):
            print(f"流水线结束: phase={phase}")
            return 1
        time.sleep(15)
    print("❌ 轮询超时")
    return 1


if __name__ == "__main__":
    sys.exit(main())
