"""W6 — Agent architecture health checks (config + static evidence).

Surfaced via production_depth report / diagnostics UI.
Metrics: policy fail_mode, LLM bypass allowlist, architecture_profile pilot,
DynamicRouter opt-in, CRAG entrypoints, autonomous GoalExecutor default-off.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_WORKSPACE = Path(__file__).resolve().parents[4]  # aiPlat-core/core/harness/observability → repo? 
# __file__ = .../aiPlat-core/core/harness/observability/architecture_health.py
# parents[0]=observability [1]=harness [2]=core [3]=aiPlat-core [4]=workspace
if not (_WORKSPACE / "scripts").is_dir():
    _WORKSPACE = Path(__file__).resolve().parents[3]  # fallback if layout differs


def _status(ok: bool, *, warn: bool = False) -> str:
    if ok:
        return "pass"
    return "warn" if warn else "fail"


def _run_script(rel: str, *args: str, timeout: float = 15.0) -> Dict[str, Any]:
    script = _WORKSPACE / rel
    if not script.is_file():
        return {"ok": False, "detail": f"missing {rel}", "code": -1}
    try:
        proc = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=str(_WORKSPACE),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        summary = ""
        for line in out.strip().splitlines()[::-1]:
            if line.startswith("summary:"):
                summary = line
                break
        return {
            "ok": proc.returncode == 0,
            "code": proc.returncode,
            "detail": summary or out.strip()[-400:],
        }
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__}: {e}", "code": -1}


def _count_security_degraded(limit: int = 50) -> Dict[str, Any]:
    try:
        from core.services.execution_store import get_execution_store

        store = get_execution_store()
        if store is None:
            return {"available": False, "count": 0, "blocked": 0}
        # Best-effort: stores vary; prefer dedicated API if present
        if hasattr(store, "count_audit_by_action"):
            n = int(store.count_audit_by_action("security_degraded") or 0)
            return {"available": True, "count": n, "blocked": 0}
        if hasattr(store, "list_audit_log"):
            rows = store.list_audit_log(action="security_degraded", limit=limit) or []
            blocked = sum(
                1
                for r in rows
                if (r.get("status") == "blocked")
                or (isinstance(r.get("detail"), dict) and r["detail"].get("blocked"))
            )
            return {"available": True, "count": len(rows), "blocked": blocked}
    except Exception as e:
        return {"available": False, "count": 0, "blocked": 0, "error": f"{type(e).__name__}"}
    return {"available": False, "count": 0, "blocked": 0}


def _seed_plan_execute_pilot() -> Dict[str, Any]:
    path = _WORKSPACE / "aiPlat-core/core/workspace_seeds/teams/code_split.yaml"
    if not path.is_file():
        return {"ok": False, "detail": "code_split.yaml missing"}
    text = path.read_text(encoding="utf-8")
    ok = "architecture_profile: plan_execute" in text
    return {
        "ok": ok,
        "detail": "code_split backend_developer → plan_execute" if ok else "pilot profile not found",
    }


def build_architecture_health_checks() -> List[Dict[str, Any]]:
    """Return check rows compatible with production_depth UI."""
    checks: List[Dict[str, Any]] = []
    profile = (os.getenv("AIPLAT_PROFILE") or "").strip().lower()
    fail_mode = (os.getenv("AIPLAT_POLICY_FAIL_MODE") or "open").strip().lower()
    crit_mode = (os.getenv("AIPLAT_POLICY_FAIL_CRITICAL_MODE") or "").strip().lower()
    prodish = profile == "production"

    # 1) Policy fail_mode
    if prodish:
        mode_ok = fail_mode in ("ask", "closed") or crit_mode in ("ask", "closed")
        checks.append({
            "id": "policy_fail_mode",
            "title": "架构健康 · PolicyGate 降级策略",
            "status": _status(mode_ok, warn=True),
            "detail": f"FAIL_MODE={fail_mode} CRITICAL_MODE={crit_mode or '(unset)'} profile=production",
            "hint": "生产建议 AIPLAT_POLICY_FAIL_MODE=ask，关键路径 AIPLAT_POLICY_FAIL_CRITICAL_MODE=closed",
        })
    else:
        checks.append({
            "id": "policy_fail_mode",
            "title": "架构健康 · PolicyGate 降级策略",
            "status": "pass",
            "detail": f"FAIL_MODE={fail_mode} (non-production default open OK)",
            "hint": "生产切换 profile=production 后改 ask/closed",
        })

    # 2) security_degraded volume (observability)
    deg = _count_security_degraded()
    if deg.get("available"):
        # warn if many degraded opens
        ok = int(deg.get("count") or 0) < 20
        checks.append({
            "id": "policy_degraded_count",
            "title": "架构健康 · security_degraded 审计量",
            "status": _status(ok, warn=True),
            "detail": f"recent≈{deg.get('count')} blocked≈{deg.get('blocked')}",
            "hint": "降级飙升时检查权限 DB；回滚: AIPLAT_POLICY_FAIL_MODE=open",
        })
    else:
        # Store API optional — do not fail non-prod dashboards; warn only in production.
        checks.append({
            "id": "policy_degraded_count",
            "title": "架构健康 · security_degraded 审计量",
            "status": "warn" if prodish else "pass",
            "detail": deg.get("error") or "execution_store 无审计查询接口（可选）",
            "hint": "生产建议接线 count_audit_by_action / list_audit_log(action=security_degraded)",
        })

    # 3) LLM bypass allowlist
    bypass = _run_script("scripts/check_pipeline_llm_bypass.py", "--ci")
    checks.append({
        "id": "llm_bypass_allowlist",
        "title": "架构健康 · pipeline LLM 旁路台账",
        "status": _status(bool(bypass.get("ok"))),
        "detail": str(bypass.get("detail") or ""),
        "hint": "新增 sys_llm_generate 须 # bypass-ok + allowlist（A2）",
    })

    # 4) architecture_profile pilot
    pilot = _seed_plan_execute_pilot()
    checks.append({
        "id": "architecture_profile_pilot",
        "title": "架构健康 · plan_execute 试点",
        "status": _status(bool(pilot.get("ok")), warn=True),
        "detail": str(pilot.get("detail") or ""),
        "hint": "code_split.yaml backend_developer.architecture_profile=plan_execute（B1）",
    })

    # 5) DynamicRouter opt-in
    enabled = (os.getenv("AIPLAT_DYNAMIC_ROUTER_ENABLED") or "0").lower() in ("1", "true", "yes", "y")
    pct = (os.getenv("AIPLAT_DYNAMIC_ROUTER_PERCENTAGE") or "0").strip()
    try:
        pct_i = int(pct)
    except ValueError:
        pct_i = 0
    router_scan = _run_script("scripts/check_team_routing_mode.py", "--ci")
    # Production: must not have ENABLED without intentional grayscale
    if prodish and enabled and pct_i >= 100:
        router_ok = False
        router_detail = "production + ENABLED + 100% — 过宽，建议灰度 PERCENTAGE<100"
    else:
        router_ok = bool(router_scan.get("ok")) and (not enabled or pct_i > 0)
        # default-off is pass
        if not enabled:
            router_ok = bool(router_scan.get("ok"))
        router_detail = (
            f"ENABLED={enabled} PERCENTAGE={pct_i} seeds={router_scan.get('detail')}"
        )
    checks.append({
        "id": "dynamic_router_opt_in",
        "title": "架构健康 · DynamicRouter 默认关",
        "status": _status(router_ok, warn=True),
        "detail": router_detail,
        "hint": "开启须 ENABLED=1 + PERCENTAGE>0 + MIN_STAGES；种子须 static 或 # routing-ok",
    })

    # 6) CRAG entrypoints
    crag = _run_script("scripts/check_retrieval_entrypoints.py", "--ci")
    checks.append({
        "id": "retrieval_crag_entry",
        "title": "架构健康 · 问答检索走 CRAG",
        "status": _status(bool(crag.get("ok"))),
        "detail": str(crag.get("detail") or ""),
        "hint": "用户侧用 kb_qa_retrieve；GraphRAG 仅 CRAG L0（W4）",
    })

    # 7) Autonomous GoalExecutor default off
    try:
        import inspect

        from core.harness.optimization.goal_executor import GoalExecutor

        gsrc = inspect.getsource(GoalExecutor.__init__)
        default_off = "enabled: bool = False" in gsrc or "enabled=False" in gsrc
        env_auto = (os.getenv("AIPLAT_GOAL_AUTO_EXECUTE") or "0").lower() in (
            "1", "true", "yes", "y",
        )
        auto_ok = default_off and not env_auto
        auto_detail = f"default_off={default_off} AIPLAT_GOAL_AUTO_EXECUTE={env_auto}"
    except Exception as e:
        auto_ok = False
        auto_detail = f"{type(e).__name__}: {e}"
    checks.append({
        "id": "autonomous_default_off",
        "title": "架构健康 · Autonomous 默认关闭",
        "status": _status(auto_ok, warn=True),
        "detail": auto_detail,
        "hint": "GoalExecutor 默认 enabled=False；开启需人工确认 + MFA（admin）",
    })

    # 8) Factory / builder default mode=single (anti Multi-Agent sprawl)
    try:
        conf = (
            _WORKSPACE
            / "aiPlat-platform/builder/generated_conformance.py"
        )
        conf_ok = False
        detail = "generated_conformance.py missing"
        if conf.is_file():
            src = conf.read_text(encoding="utf-8")
            conf_ok = 'mode = data.get("mode") or "single"' in src
            detail = (
                "builder default manifest.mode=single (+ multi_agent 五条件 AND)"
                if conf_ok
                else "default mode=single 字面量未找到"
            )
        checks.append({
            "id": "multi_agent_default_single",
            "title": "架构健康 · Multi-Agent 默认 single",
            "status": _status(conf_ok, warn=True),
            "detail": detail,
            "hint": "能单不双；升 multi_agent 须 rationale + upgrade_criteria 五条件",
        })
    except Exception as e:
        checks.append({
            "id": "multi_agent_default_single",
            "title": "架构健康 · Multi-Agent 默认 single",
            "status": "warn",
            "detail": f"{type(e).__name__}: {e}",
            "hint": "aiPlat-platform/builder/generated_conformance.py",
        })

    return checks


def build_architecture_health_report() -> Dict[str, Any]:
    checks = build_architecture_health_checks()
    passed = sum(1 for c in checks if c["status"] == "pass")
    warned = sum(1 for c in checks if c["status"] == "warn")
    failed = sum(1 for c in checks if c["status"] == "fail")
    overall = "pass" if failed == 0 and warned == 0 else ("warn" if failed == 0 else "fail")
    return {
        "status": overall,
        "score": int(round(100.0 * passed / max(len(checks), 1))),
        "summary": {"pass": passed, "warn": warned, "fail": failed, "total": len(checks)},
        "checks": checks,
    }
