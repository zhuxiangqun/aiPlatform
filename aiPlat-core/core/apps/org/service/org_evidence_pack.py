"""H2 — signoff evidence pack. Read-only. Not a signature."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_MAX_TRACES = 5
_COVER = (
    "本包不是签字。m4_claim_allowed=false。客户尚未签收。"
)


def _role_ok(role: str) -> bool:
    return bool((role or "").strip())


def _pick_trace_ids(domain_id: str, goal_id: str, week: str, limit: int) -> List[str]:
    from core.apps.org.service.org_runtime import list_runs

    runs = list_runs(goal_id or "", limit=50).get("runs") or []
    did = (domain_id or "").strip() or "it-ops"
    week_f = (week or "").strip()
    ids: List[str] = []
    seen = set()
    for r in runs:
        if did and str(r.get("domain_id") or did) not in (did, ""):
            if str(r.get("domain_id") or "") != did:
                continue
        if week_f and str(r.get("week_label") or "") != week_f:
            continue
        tid = str(r.get("trace_id") or r.get("run_id") or "").strip()
        if not tid or tid in seen:
            continue
        seen.add(tid)
        ids.append(tid)
        if len(ids) >= limit:
            break
    return ids


def _replay_summary(trace_id: str, domain_id: str) -> Dict[str, Any]:
    from core.apps.org.service.v_wave_replay import replay_org_trace

    raw = replay_org_trace(trace_id, domain_id=domain_id)
    steps = []
    for step in raw.get("steps") or []:
        if not isinstance(step, dict):
            continue
        steps.append(
            {
                "step": step.get("step"),
                "status": step.get("status"),
                "note": step.get("note") or "",
            }
        )
    return {
        "trace_id": trace_id,
        "chain_status": raw.get("status"),
        "steps": steps,
    }


def _approval_counts(domain_id: str, goal_id: str) -> Dict[str, Any]:
    from core.apps.fde.service.k_wave_arbit import list_tickets
    from core.apps.org.service.org_kpi import weekly_kpi_report

    pending_arb = list_tickets(status="pending", domain_id=domain_id).get("count") or 0
    approved_arb = list_tickets(status="approved", domain_id=domain_id).get("count") or 0
    rejected_arb = list_tickets(status="rejected", domain_id=domain_id).get("count") or 0
    weekly = weekly_kpi_report(domain_id, goal_id or "goal-it-ops-alert-sla", week="")
    return {
        "arbitration_pending": pending_arb,
        "arbitration_approved": approved_arb,
        "arbitration_rejected": rejected_arb,
        "hitl_pending": len(weekly.get("pending_hitl") or []),
        "ids_only": True,
        "note": "只计数量与类别，不含内部草稿正文。",
    }


def _blank_sign_table() -> List[Dict[str, str]]:
    rows = [
        "沙箱 OrgRun + HITL 走过一轮",
        "飞书入站签名与身份映射已配",
        "Interface 白名单主机与基址已核",
        "周报三 KPI 看过",
        "回滚（暂停 Goal + IO_MODE=deny）演练",
        "同意对外只称单线、不称全域",
    ]
    return [{"item": r, "customer": "", "platform": "", "date": ""} for r in rows]


def _to_markdown(pack: Dict[str, Any]) -> str:
    lines = [
        "# it-ops 签收证据包",
        "",
        pack.get("cover_statement") or _COVER,
        "",
        f"- domain: {pack.get('domain_id')}",
        f"- week: {pack.get('week') or '全部可见周'}",
        f"- sandbox_mode: {pack.get('sandbox_mode')}",
        f"- m4_claim_allowed: {pack.get('m4_claim_allowed')}",
        "",
        "## 岗位与渠道",
        "```json",
        json.dumps(pack.get("channels") or {}, ensure_ascii=False, indent=2)[:2000],
        "```",
        "",
        "## 本周 KPI 与用量",
        "```json",
        json.dumps(
            {"kpis": pack.get("kpis"), "usage": pack.get("usage")},
            ensure_ascii=False,
            indent=2,
        )[:3000],
        "```",
        "",
        "## 可审计收益（不是签收）",
        "```json",
        json.dumps(pack.get("value_translation") or {}, ensure_ascii=False, indent=2)[:2000],
        "```",
        "",
        "## 代表性回放（至多 5 条）",
    ]
    for tr in pack.get("trace_summaries") or []:
        lines.append(f"### {tr.get('trace_id')}")
        for s in tr.get("steps") or []:
            lines.append(f"- {s.get('step')}: {s.get('status')} {s.get('note') or ''}")
    if pack.get("truncated"):
        lines.append("")
        lines.append("> 已截断。")
    lines.extend(
        [
            "",
            "## 审批计数",
            "```json",
            json.dumps(pack.get("approval_counts") or {}, ensure_ascii=False, indent=2),
            "```",
            "",
            "## 回滚范围",
            "可回滚：",
        ]
    )
    for x in (pack.get("rollback_scope") or {}).get("can_rollback") or []:
        lines.append(f"- {x}")
    lines.append("不可回滚：")
    for x in (pack.get("rollback_scope") or {}).get("cannot_rollback") or []:
        lines.append(f"- {x}")
    lines.extend(["", "## C5 清单", "自动项："])
    for it in pack.get("c5_auto") or []:
        lines.append(f"- [{'x' if it.get('ok') else ' '}] {it.get('label')}")
    lines.append("人工项（本包不勾选）：")
    for it in pack.get("c5_manual") or []:
        lines.append(f"- [ ] {it.get('label')}")
    lines.extend(["", "## 空白双签表"])
    for row in pack.get("blank_sign_table") or []:
        lines.append(f"- {row.get('item')} | 客户:____ | 平台:____ | 日期:____")
    text = "\n".join(lines)
    if len(text) > 40000:
        return text[:40000] + "\n\n> 已截断。\n"
    return text


def build_evidence_pack(
    *,
    role: str,
    domain_id: str = "it-ops",
    goal_id: str = "goal-it-ops-alert-sla",
    week: str = "",
    max_traces: int = _MAX_TRACES,
    sandbox_mode: bool = False,
    as_markdown: bool = False,
) -> Dict[str, Any]:
    """Assemble a customer-safe evidence pack. Never writes business state."""
    if not _role_ok(role):
        return {"ok": False, "reason": "identity_missing", "writable": False}

    did = (domain_id or "").strip() or "it-ops"
    gid = (goal_id or "").strip() or "goal-it-ops-alert-sla"
    n = min(_MAX_TRACES, max(1, int(max_traces or _MAX_TRACES)))

    from core.apps.fde.service.k_wave_rollback import rollback_scope
    from core.apps.org.service.org_field_ops import field_ops_checklist
    from core.apps.org.service.org_ingress import ingress_status
    from core.apps.org.service.org_kpi import weekly_kpi_report
    from core.apps.org.service.org_post import list_posts
    from core.apps.org.service.org_usage import weekly_usage
    from core.apps.org.service.org_value_translation import translate_org_value
    from core.apps.org.service.org_signoff_progress import load_signoff_progress

    checklist = field_ops_checklist(did)
    items = checklist.get("items") or []
    c5_auto = []
    c5_manual = []
    for it in items:
        if not isinstance(it, dict):
            continue
        label = str(it.get("label") or "")
        entry = {"id": it.get("id"), "label": label, "ok": bool(it.get("ok"))}
        if it.get("id") in ("oncall", "live_unlock") or "人工" in label:
            c5_manual.append(entry)
        else:
            c5_auto.append(entry)

    weekly = weekly_kpi_report(did, gid, week=week or "")
    usage = weekly_usage(domain_id=did, week=week or "")
    value = translate_org_value(
        domain_id=did, goal_id=gid, week=week or "", tenant_id=""
    )
    usage_safe = {
        "run_count": usage.get("run_count"),
        "token_total": usage.get("token_total") or usage.get("tokens"),
        "billing": None,
        "status": usage.get("status"),
    }
    kpis = weekly.get("kpis") or {}
    kpis_safe = {
        "mtta_seconds": kpis.get("mtta_seconds"),
        "root_cause_rate": kpis.get("root_cause_rate"),
        "exception_ratio": kpis.get("exception_ratio"),
        "run_count": weekly.get("run_count"),
    }

    posts = list_posts()
    post_safe = []
    for row in posts.get("items") or []:
        p = row.get("post") if isinstance(row, dict) else None
        if not isinstance(p, dict):
            continue
        post_safe.append(
            {
                "post_id": p.get("post_id"),
                "title": p.get("title"),
                "org_goal_id": p.get("org_goal_id"),
                "enabled": p.get("enabled"),
                "channel_allowlist": p.get("channel_allowlist"),
            }
        )

    ingress = ingress_status()
    channels = {
        "inbound": ingress.get("inbound"),
        "outbound_only": [
            {"id": x.get("id"), "configured": bool(x.get("configured"))}
            for x in (ingress.get("outbound_only") or [])
            if isinstance(x, dict)
        ],
        "second_channel": ingress.get("second_channel"),
    }

    trace_ids = _pick_trace_ids(did, gid, week, n)
    summaries = [_replay_summary(tid, did) for tid in trace_ids]
    truncated = False  # length guard in markdown

    prog = load_signoff_progress()
    sign_table = _blank_sign_table()
    filled = prog.get("dual_sign") or []
    if filled:
        by_item = {str(r.get("item") or ""): r for r in filled if isinstance(r, dict)}
        for row in sign_table:
            hit = by_item.get(str(row.get("item") or ""))
            if hit:
                row["customer"] = hit.get("customer") or ""
                row["platform"] = hit.get("platform") or ""
                row["date"] = hit.get("date") or ""
                row["notes"] = hit.get("notes") or ""

    pack = {
        "ok": True,
        "writable": False,
        "layer": "evidence_pack",
        "cover_statement": _COVER,
        "m4_claim_allowed": False,
        "signoff_button": False,
        "sandbox_mode": bool(sandbox_mode),
        "domain_id": did,
        "goal_id": gid,
        "week": week or None,
        "posts": post_safe,
        "channels": channels,
        "kpis": kpis_safe,
        "usage": usage_safe,
        "value_translation": {
            "baseline_source": value.get("baseline_source"),
            "baseline_missing": value.get("baseline_missing"),
            "saved_person_hours": value.get("saved_person_hours"),
            "mtta_delta_seconds": value.get("mtta_delta_seconds"),
            "platform_kpis": value.get("platform_kpis"),
            "note": "价值翻译不是签收；无基线不编节省人时。",
        },
        "oncall": {
            "name": prog.get("oncall_name") or "",
            "contact": prog.get("oncall_contact") or "",
            "rollback_owner": prog.get("rollback_owner") or "",
            "intent_recorded": bool(prog.get("intent_recorded")),
        },
        "trace_summaries": summaries,
        "trace_limit": n,
        "trace_limit_cap": _MAX_TRACES,
        "approval_counts": _approval_counts(did, gid),
        "rollback_scope": rollback_scope(),
        "c5_auto": c5_auto,
        "c5_manual": c5_manual,
        "c5_pack_ready": bool(checklist.get("c5_pack_ready")),
        "blank_sign_table": sign_table,
        "truncated": truncated,
        "authority_note": "导出只读。材料包就绪不等于客户已签字。",
    }
    if as_markdown:
        pack["markdown"] = _to_markdown(pack)
        if len(pack["markdown"]) >= 40000:
            pack["truncated"] = True
    return pack
