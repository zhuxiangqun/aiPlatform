"""
Skill Lint Scan (scheduled / ops).

Used by:
- Jobs/Cron scheduler (kind = "skill_lint_scan")
- API endpoint /core/workspace/skills/lint-scan (ad-hoc scan)

This module keeps side-effects minimal:
- It reads skills via SkillManager (filesystem)
- It writes *optional* audit logs (best-effort) for blocked/high-risk findings
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.management.skill_linter import lint_skill, lint_summary
from core.management.skill_manager import SkillManager


def _as_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    if isinstance(v, list):
        out: List[str] = []
        for it in v:
            s = str(it).strip()
            if s:
                out.append(s)
        return out
    return []


def _severity_for_scan(totals: Dict[str, Any]) -> Optional[str]:
    try:
        blocked = int(totals.get("blocked") or 0)
        errors = int(totals.get("errors") or 0)
        if blocked > 0:
            return "error"
        if errors > 0:
            return "warning"
        return None
    except Exception:
        return None


def _alert_event(
    *,
    payload: Dict[str, Any],
    job_id: str,
    job_run_id: Optional[str],
    trace_id: Optional[str],
    cron: str,
    finished_at: float,
    totals: Dict[str, Any],
    top: Dict[str, Any],
    blocked_skills: List[Dict[str, Any]],
    severity: str,
) -> Dict[str, Any]:
    scopes = _as_list(payload.get("scopes") or payload.get("scope")) or ["workspace"]
    ev = {
        "event_type": "skill_lint_alert",
        "severity": severity,
        "source": {
            "job_id": job_id,
            "job_run_id": job_run_id,
            "trace_id": trace_id,
            "scopes": scopes,
        },
        "window": {"finished_at": finished_at, "cron": cron},
        "metrics": totals,
        "top": top,
        "blocked_skills": blocked_skills[:50],
        "links": {
            "dashboard": "/workspace/skills-lint",
            "jobs": "/core/jobs",
            "skills": "/workspace/skills",
        },
    }
    # Human-readable markdown (keep short)
    top_e = None
    try:
        arr = top.get("errors") if isinstance(top.get("errors"), list) else []
        if arr:
            top_e = arr[0]
    except Exception:
        top_e = None
    md = [
        f"## Skill Lint 告警（{severity}）",
        f"- blocked={int(totals.get('blocked') or 0)}，errors={int(totals.get('errors') or 0)}，warnings={int(totals.get('warnings') or 0)}",
    ]
    if top_e:
        md.append(f"- Top error: {top_e.get('code')} ×{top_e.get('count')}")
    md.append(f"- 处理入口：{ev['links']['dashboard']}")
    ev["markdown"] = "\n".join(md) + "\n"
    return ev


async def _deliver_webhook_if_configured(*, url: str, event: Dict[str, Any]) -> None:
    url = (url or "").strip()
    if not url:
        return
    # Minimal delivery: best-effort, 2 retries
    import aiohttp

    body = event
    for _ in range(2):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(url, json=body) as resp:
                    if 200 <= int(resp.status) < 300:
                        return
        except Exception:
            continue


async def run_skill_lint_scan(
    *,
    payload: Optional[Dict[str, Any]],
    execution_store: Any,
) -> Dict[str, Any]:
    """
    Execute a lint scan.

    payload:
      - scopes: ["workspace","engine"]  (default ["workspace"])
      - category: optional
      - status: optional
      - include_full: bool (default False)
      - max_items: int (default 500)
    """
    p = payload if isinstance(payload, dict) else {}
    scopes = _as_list(p.get("scopes") or p.get("scope")) or ["workspace"]
    category = str(p.get("category") or "").strip() or None
    status = str(p.get("status") or "").strip() or None
    include_full = bool(p.get("include_full", False))
    max_items = int(p.get("max_items") or 500)

    started_at = time.time()
    findings: List[Dict[str, Any]] = []

    totals = {
        "skills": 0,
        "errors": 0,
        "warnings": 0,
        "blocked": 0,
        "high_risk": 0,
    }
    code_stats = {
        "errors": {},  # code -> count
        "warnings": {},  # code -> count
        "error_examples": {},  # code -> message
        "warning_examples": {},  # code -> message
    }

    for scope in scopes:
        sc = (scope or "").strip().lower()
        if sc not in {"workspace", "engine"}:
            continue
        mgr = SkillManager(seed=False, scope=sc)
        skills = await mgr.list_skills(skill_type=category, status=status, limit=max_items, offset=0)
        for s in skills:
            rep = lint_skill(s)
            summ = lint_summary(rep)
            # Aggregate code-level stats (for productized dashboard / trend view)
            try:
                for it in (rep.get("errors") if isinstance(rep, dict) else []) or []:
                    if not isinstance(it, dict):
                        continue
                    c = str(it.get("code") or "").strip() or "unknown"
                    code_stats["errors"][c] = int(code_stats["errors"].get(c) or 0) + 1
                    if c not in code_stats["error_examples"] and it.get("message"):
                        code_stats["error_examples"][c] = str(it.get("message"))
                for it in (rep.get("warnings") if isinstance(rep, dict) else []) or []:
                    if not isinstance(it, dict):
                        continue
                    c = str(it.get("code") or "").strip() or "unknown"
                    code_stats["warnings"][c] = int(code_stats["warnings"].get(c) or 0) + 1
                    if c not in code_stats["warning_examples"] and it.get("message"):
                        code_stats["warning_examples"][c] = str(it.get("message"))
            except Exception:
                pass
            totals["skills"] += 1
            totals["errors"] += int(summ.get("error_count") or 0)
            totals["warnings"] += int(summ.get("warning_count") or 0)
            if str(summ.get("risk_level") or "") == "high":
                totals["high_risk"] += 1
            if bool(summ.get("blocked")):
                totals["blocked"] += 1

            findings.append(
                {
                    "scope": sc,
                    "skill_id": getattr(s, "id", None),
                    "name": getattr(s, "name", None),
                    "summary": summ,
                    "lint": rep if include_full else None,
                }
            )

            # Audit only blocked/high-risk findings to reduce noise.
            if execution_store is not None and bool(summ.get("blocked")):
                try:
                    await execution_store.add_audit_log(
                        action="skill_lint_blocked",
                        status="failed",
                        tenant_id=str(p.get("tenant_id") or "") or None,
                        actor_id=str(p.get("actor_id") or "system"),
                        resource_type="skill",
                        resource_id=str(getattr(s, "id", "") or ""),
                        change_id=None,
                        detail={"scope": sc, "summary": summ},
                    )
                except Exception:
                    pass

    finished_at = time.time()
    # Top issue codes for UI (keep payload compact, do not include full per-skill lint by default)
    def _top(d: Dict[str, int], ex: Dict[str, str], n: int = 10) -> List[Dict[str, Any]]:
        try:
            items = [{"code": k, "count": int(v), "example": ex.get(k)} for k, v in (d or {}).items()]
            items.sort(key=lambda x: int(x.get("count") or 0), reverse=True)
            return items[:n]
        except Exception:
            return []

    top_obj = {
        "errors": _top(code_stats["errors"], code_stats["error_examples"]),
        "warnings": _top(code_stats["warnings"], code_stats["warning_examples"]),
    }

    out = {
        "ok": True,
        "status": "completed",
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": (finished_at - started_at) * 1000.0,
        "request": {"scopes": scopes, "category": category, "status": status, "include_full": include_full, "max_items": max_items},
        "totals": totals,
        "top": top_obj,
        "items": findings,
    }

    # Alert (productized): based on totals, emit audit log + optional webhook.
    severity = _severity_for_scan(totals)
    if severity and execution_store is not None:
        try:
            # blocked skills summary (compact)
            blocked_skills = [
                {
                    "scope": it.get("scope"),
                    "skill_id": it.get("skill_id"),
                    "name": it.get("name"),
                    "risk_level": (it.get("summary") or {}).get("risk_level"),
                    "error_count": (it.get("summary") or {}).get("error_count"),
                    "warning_count": (it.get("summary") or {}).get("warning_count"),
                }
                for it in findings
                if isinstance(it, dict) and isinstance(it.get("summary"), dict) and bool(it["summary"].get("blocked"))
            ]

            job_id = str(p.get("job_id") or "cron-skill-lint-scan")
            job_run_id = str(p.get("job_run_id") or "") or None
            trace_id = str(p.get("trace_id") or "") or None
            cron = str(p.get("cron") or "0 * * * *")
            ev = _alert_event(
                payload=p,
                job_id=job_id,
                job_run_id=job_run_id,
                trace_id=trace_id,
                cron=cron,
                finished_at=finished_at,
                totals=totals,
                top=top_obj,
                blocked_skills=blocked_skills,
                severity=severity,
            )
            await execution_store.add_audit_log(
                action="skill_lint_alert",
                status="failed" if severity == "error" else "ok",
                tenant_id=str(p.get("tenant_id") or "") or None,
                actor_id=str(p.get("actor_id") or "system"),
                resource_type="job",
                resource_id=job_id,
                change_id=None,
                detail=ev,
            )
            # Optional webhook
            hook = (p.get("webhook_url") or "") if isinstance(p, dict) else ""
            if not hook:
                import os

                hook = (os.getenv("AIPLAT_SKILL_LINT_WEBHOOK_URL") or "").strip()
            if hook:
                await _deliver_webhook_if_configured(url=str(hook), event=ev)
            out["alert"] = {"severity": severity, "event": ev}
        except Exception:
            pass

    return out
