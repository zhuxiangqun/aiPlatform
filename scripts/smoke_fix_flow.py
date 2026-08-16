#!/usr/bin/env python3
"""smoke_fix_flow.py — 一键修复流程冒烟验证。

验证「重启 core → 触发重建 → 检查决策溯源 → 调用一键修复」全链路，
用于确认决策溯源 agent_id/run_id 一致性与混合修复计划（build_fix_plan）已生效。

用法:
    python3 scripts/smoke_fix_flow.py --check-services
    python3 scripts/smoke_fix_flow.py --restart-core
    python3 scripts/smoke_fix_flow.py --rebuild <project_id>
    python3 scripts/smoke_fix_flow.py --poll <project_id> [timeout_sec]
    python3 scripts/smoke_fix_flow.py --check-trace <project_id>
    python3 scripts/smoke_fix_flow.py --fix-direct <project_id>
    python3 scripts/smoke_fix_flow.py --fix-agent <project_id>
    python3 scripts/smoke_fix_flow.py --all <project_id>     # 全流程
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

CORE = "http://localhost:8002"
PLATFORM = "http://localhost:8003"
TRACE_DIR = os.path.expanduser("~/.aiplat/decision_traces")


def _http(method: str, url: str, body: dict | None = None, timeout: int = 30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}", "_detail": e.read().decode()[:300]}
    except urllib.error.URLError as e:
        return {"_error": "URLError", "_detail": str(e.reason)}


def check_services():
    print("=== 服务健康检查 ===")
    for name, base in (("core", CORE), ("platform", PLATFORM)):
        try:
            urllib.request.urlopen(base + "/docs", timeout=5)
            print(f"  ✅ {name}: {base}")
        except Exception as e:
            print(f"  ❌ {name}: {base} — {type(e).__name__}: {e}")
    return 0


def restart_core():
    print("=== 重启 core 服务（SIGHUP 优雅重载）===")
    out = subprocess.run(["pgrep", "-f", "gunicorn.*server:app"],
                         capture_output=True, text=True).stdout.split()
    if not out:
        print("  ❌ 未找到 core gunicorn 进程（gunicorn.*server:app）")
        return 1
    master = None
    for pid in out:
        for other in out:
            if other == pid:
                continue
            ppid = subprocess.run(["ps", "-o", "ppid=", "-p", other],
                                  capture_output=True, text=True).stdout.strip()
            if ppid == pid:
                master = pid
                break
        if master:
            break
    master = master or out[0]
    try:
        os.kill(int(master), signal.SIGHUP)
        print(f"  ✅ 已向 master (PID {master}) 发送 SIGHUP，等待 3s 重载")
        time.sleep(3)
    except Exception as e:
        print(f"  ❌ SIGHUP 失败: {e}")
        return 1
    return 0


def rebuild(project_id: str):
    print(f"=== 触发重建 {project_id} ===")
    r = _http("POST", f"{PLATFORM}/platform/builder/projects/{project_id}/rebuild", {})
    print(f"  响应: {json.dumps(r, ensure_ascii=False)[:200]}")
    return 0 if "_error" not in r else 1


def poll(project_id: str, timeout: int = 600):
    print(f"=== 轮询流水线状态 {project_id} (超时 {timeout}s) ===")
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = _http("GET", f"{PLATFORM}/platform/builder/projects/{project_id}/state")
        phase = r.get("phase", "?") if isinstance(r, dict) else "?"
        prog = ""
        if isinstance(r.get("state"), dict):
            p = r["state"].get("_progress") or {}
            prog = f" stage={p.get('stage','?')} status={p.get('status','?')}"
        print(f"  [{int(time.time()-t0)}s] phase={phase}{prog}")
        if phase in ("done", "failed"):
            print(f"  ✅ 流水线结束: phase={phase}")
            return 0 if phase == "done" else 1
        time.sleep(5)
    print(f"  ❌ 轮询超时")
    return 1


def check_trace(project_id: str):
    print(f"=== 检查决策溯源 {project_id} ===")
    fp = os.path.join(TRACE_DIR, f"{project_id}.json")
    if not os.path.isfile(fp):
        print(f"  ❌ 未找到 trace 文件: {fp}")
        print(f"     提示: 需重启 core 后重新构建一次流水线，让 record_decision 生效")
        return 1
    with open(fp) as f:
        d = json.load(f)
    decisions = d.get("decisions", {})
    failed = d.get("failed", [])
    print(f"  决策数: {len(decisions)}  |  失败标记: {len(failed)}")
    for did, rec in sorted(decisions.items()):
        print(f"    - stage={rec.get('stage_id'):<15} agent={rec.get('agent_id',''):<20} conf={rec.get('confidence')}")
    if not decisions:
        print("  ⚠️  decisions 为空 —— 决策溯源未记录，locate_max_error_node 将返回 None")
    return 0


def _derive_failed_stages(project_id: str, test_report_raw: str):
    """确定性 bug→stage 映射：按当前项目团队动态定位代码/前端阶段（不硬编码 agent 名）。"""
    stages = set()
    try:
        d = json.loads(test_report_raw) if test_report_raw.strip().startswith("{") else {}
    except Exception:
        d = {}
    bugs = d.get("bug_summary", {}).get("bugs", []) if isinstance(d, dict) else []
    if not bugs and isinstance(d, dict):
        # 兜底：全文搜索 FR
        import re
        bugs = [{"suggested_fix": m.group(0)} for m in re.finditer(r'suggested_fix[^,}]+', test_report_raw)]

    # 动态获取当前项目团队阶段（而非硬编码 agent 名）
    team_stages = []
    try:
        proj = _http("GET", f"{PLATFORM}/platform/builder/projects/{project_id}")
        if isinstance(proj, dict):
            team_stages = proj.get("team_stages") or []
    except Exception:
        team_stages = []
    code_agent = next((s.get("agent_id") for s in team_stages
                       if s.get("output_artifact") == "code" or s.get("uses_file_output")), "programmer_agent")
    frontend_agent = next((s.get("agent_id") for s in team_stages
                           if s.get("output_artifact") in ("frontend_pages", "app_page")), "frontend_developer")

    for b in bugs:
        fix = str(b.get("suggested_fix", "") or "") if isinstance(b, dict) else str(b)
        if any(k in fix for k in ("接口", "后端", "失败原因", "校验逻辑", "pytest", "ImportError", "AssertionError")):
            stages.add(code_agent)
        if any(k in fix for k in ("组件", "表单", "上传", "页面", "按钮", "会话")):
            stages.add(frontend_agent)
    return sorted(stages)


def fix_direct(project_id: str):
    print(f"=== 确定性修复（generate-hypotheses → regenerate）{project_id} ===")
    st = _http("GET", f"{PLATFORM}/platform/builder/projects/{project_id}/state")
    state = st.get("state", {}) if isinstance(st, dict) else {}
    test_report_raw = (state.get("test_report") or {}).get("raw_output", "") if isinstance(state.get("test_report"), dict) else ""
    if not test_report_raw:
        # 兜底：直接从 output 目录读
        out_fp = os.path.expanduser(f"~/.aiplat/output/{project_id}/test_report.json")
        if os.path.isfile(out_fp):
            test_report_raw = open(out_fp).read()
    if not test_report_raw:
        print("  ❌ 未取到 test_report")
        return 1

    failed = _derive_failed_stages(project_id, test_report_raw)
    print(f"  失败阶段（确定性映射）: {failed}")
    if not failed:
        print("  ⚠️ 未映射到失败阶段，跳过（可先跑 --poll 确认流水线完成）")
        return 1

    r = _http("POST", f"{PLATFORM}/platform/builder/projects/{project_id}/generate-hypotheses",
              {"failed_stage_ids": failed, "test_report": test_report_raw[:8000]})
    if "_error" in r:
        print(f"  ❌ generate-hypotheses 失败: {r}")
        return 1
    fix_plan = r.get("fix_plan", [])
    print(f"  fix_plan: {fix_plan}")
    print(f"  max_error_stage: {r.get('max_error_stage')}")
    print(f"  hypotheses: {len(r.get('hypotheses', []))} 条")

    for stage in fix_plan:
        rr = _http("POST", f"{PLATFORM}/platform/builder/projects/{project_id}/regenerate",
                   {"stage_id": stage, "feedback": test_report_raw[:8000]})
        status = rr.get("status") if isinstance(rr, dict) else str(rr)
        print(f"  regenerate {stage}: {status}")
    print("  ✅ 修复已触发，等待流水线后台重跑，用 --poll 观察结果")
    return 0


def fix_agent(project_id: str):
    print(f"=== 调用一键修复 agent（test_report_orchestrator）{project_id} ===")
    st = _http("GET", f"{PLATFORM}/platform/builder/projects/{project_id}/state")
    state = st.get("state", {}) if isinstance(st, dict) else {}
    test_report_raw = (state.get("test_report") or {}).get("raw_output", "") if isinstance(state.get("test_report"), dict) else ""
    r = _http("POST", f"{CORE}/core/workspace/agents/test_report_orchestrator/execute",
              {"input": {"project_id": project_id, "test_report": test_report_raw}})
    print(f"  响应: {json.dumps(r, ensure_ascii=False)[:400]}")
    return 0 if "_error" not in r else 1


def all_flow(project_id: str):
    steps = [
        ("restart-core", lambda: restart_core()),
        ("rebuild", lambda: rebuild(project_id)),
        ("poll", lambda: poll(project_id)),
        ("check-trace", lambda: check_trace(project_id)),
        ("fix-direct", lambda: fix_direct(project_id)),
    ]
    for name, fn in steps:
        print()
        rc = fn()
        if rc != 0 and name in ("rebuild", "poll"):
            print(f"❌ 步骤 {name} 失败，中止")
            return rc
    return 0


def main():
    ap = argparse.ArgumentParser(description="一键修复流程冒烟验证")
    ap.add_argument("--check-services", action="store_true")
    ap.add_argument("--restart-core", action="store_true")
    ap.add_argument("--rebuild", metavar="PROJECT_ID")
    ap.add_argument("--poll", metavar="PROJECT_ID")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--check-trace", metavar="PROJECT_ID")
    ap.add_argument("--fix-direct", metavar="PROJECT_ID")
    ap.add_argument("--fix-agent", metavar="PROJECT_ID")
    ap.add_argument("--all", metavar="PROJECT_ID")
    args = ap.parse_args()

    if args.check_services:
        sys.exit(check_services())
    if args.restart_core:
        sys.exit(restart_core())
    if args.rebuild:
        sys.exit(rebuild(args.rebuild))
    if args.poll:
        sys.exit(poll(args.poll, args.timeout))
    if args.check_trace:
        sys.exit(check_trace(args.check_trace))
    if args.fix_direct:
        sys.exit(fix_direct(args.fix_direct))
    if args.fix_agent:
        sys.exit(fix_agent(args.fix_agent))
    if args.all:
        sys.exit(all_flow(args.all))
    ap.print_help()


if __name__ == "__main__":
    main()
