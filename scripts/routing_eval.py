#!/usr/bin/env python3
"""
Routing evaluation — 路由分类准召率测试工具。

Usage:
  python3 scripts/routing_eval.py                 # 运行所有测试
  python3 scripts/routing_eval.py --verbose       # 显示每个测试详情
  python3 scripts/routing_eval.py --server        # 通过 API 测试（需要 core 运行）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Test cases: (user_message, expected_intent, expected_agent)
TEST_CASES = [
    # ── 客服类 ──
    ("我的订单 #12345 显示已发货但没收到，帮我查一下物流状态", "order_query", "智能客服"),
    ("我想退货，订单号 #67890 已经超过7天了还能退吗", "refund_request", "智能客服"),
    ("你们的产品质量太差了，我要投诉", "complaint", "智能客服"),
    ("这个产品怎么用？有哪些功能？", "product_info", "智能客服"),
    ("我是VIP会员，怎么查看我的积分？", "account_service", "智能客服"),
    # ── 开发类 ──
    ("审查下面代码的安全漏洞和SQL注入风险", "code_review", "代码审核"),
    ("帮我用Python写一个Flask API返回当前时间", "code_generation", "程序员"),
    ("这个函数有bug，一直返回null，帮我修一下", "bug_fix", "代码调试专家"),
    ("设计一个高并发的订单系统架构", "architecture_design", "系统架构师"),
    ("Python和Go做后端开发有什么区别？", "tech_consult", "产品经理"),
    # ── 测试类 ──
    ("生成用户登录模块的单元测试用例", "test_generation", "test-engineer"),
    ("打开 https://example.com，测试登录和下单流程", "e2e_test", "浏览器自动化"),
    # ── 文档/知识类 ──
    ("总结一下这份设计文档的核心要点", "summary", ""),
    ("对比一下React和Vue的优缺点", "compare", ""),
    # ── 安全类 ──
    ("对后端API做一次安全审查，检查XSS和CSRF漏洞", "security_audit", "安全审计专家"),
    # ── 通用类 ──
    ("调研一下2024年AI Agent的最新进展", "research", "自动调研助手"),
    ("你好", "chitchat", "智能客服"),
    ("asdfghjkl", "unknown", ""),
]

# Counter-examples (should NOT match these intents)
COUNTER_EXAMPLES = [
    ("设计一个高并发的订单系统架构", "order_query"),  # architecture, not order
    ("帮我写一个订单管理的API接口", "order_query"),      # code generation, not order
]


def run_standalone():
    """Run evaluation using local classifier (no server needed)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "aiPlat-core"))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "aiPlat-infra"))

    from core.harness.routing.classifier import classify
    from core.schemas_routing import RoutingContext

    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    total = passed = 0
    intent_ok = agent_ok = 0
    failures: list = []

    for msg, expected_intent, expected_agent in TEST_CASES:
        ctx = RoutingContext(user_message=msg)
        result = classify(ctx)
        total += 1
        intent_match = result.intent.value == expected_intent
        agent_match = (not expected_agent) or (result.primary_route.target == expected_agent)

        if intent_match:
            intent_ok += 1
        if agent_match:
            agent_ok += 1
        if intent_match and agent_match:
            passed += 1

        if verbose or not intent_match:
            status = "✅" if intent_match else f"❌ expected={expected_intent} got={result.intent.value}"
            print(f"{status:50s} | conf={result.confidence:.0%} | {msg[:50]}")

    # Counter examples
    counter_total = counter_passed = 0
    for msg, should_not_match in COUNTER_EXAMPLES:
        ctx = RoutingContext(user_message=msg)
        result = classify(ctx)
        counter_total += 1
        if result.intent.value != should_not_match:
            counter_passed += 1
        elif verbose:
            print(f"⚠️  Counter-miss: {msg[:50]} matched {should_not_match} (got {result.intent.value})")

    print(f"\n{'='*60}")
    print(f"意图分类准确率: {intent_ok}/{total} = {intent_ok/total*100:.1f}%")
    print(f"Agent 路由准确率: {agent_ok}/{total} = {agent_ok/total*100:.1f}%")
    print(f"综合准确率:       {passed}/{total} = {passed/total*100:.1f}%")
    print(f"反例过滤率:       {counter_passed}/{counter_total} = {counter_passed/counter_total*100:.1f}%")
    print(f"{'='*60}")

    if total == intent_ok == agent_ok:
        print("🎉 全部通过!")
    else:
        print("⚠️  存在未通过的用例，查看上方详情。")


def run_server(host="http://localhost:8002"):
    """Run evaluation via API (requires core running)."""
    import urllib.request

    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    total = passed = 0

    for msg, expected_intent, expected_agent in TEST_CASES:
        try:
            req = urllib.request.Request(
                f"{host}/api/core/workspace/routing/classify",
                data=json.dumps({"message": msg}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            intent = data.get("intent", "")
            agent = data.get("primary_route", {}).get("target", "")
            total += 1
            ok = intent == expected_intent and (not expected_agent or agent == expected_agent)
            if ok:
                passed += 1
            if verbose or not ok:
                print(f"{'✅' if ok else '❌'} {msg[:50]}")
                print(f"     expected={expected_intent}/{expected_agent} got={intent}/{agent}")
        except Exception as e:
            print(f"❌ Error: {e}")
            return

    print(f"\n准确率: {passed}/{total} = {passed/total*100:.1f}%" if total else "No results")


if __name__ == "__main__":
    if "--server" in sys.argv:
        run_server()
    else:
        run_standalone()
