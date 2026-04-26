from __future__ import annotations

import time
from typing import Any, Dict, Optional

from fastapi import HTTPException


async def skill_invocation_metrics(*, store: Any, tenant_id: Optional[str], since_hours: int, limit: int) -> Dict[str, Any]:
    """Aggregate syscall_events(kind=skill) into a skill-level metrics view.

    NOTE: extracted from core.server.py to a service module for better reuse/testing.
    """
    if not store:
        return {"items": [], "total": 0}
    since_hours = max(1, min(int(since_hours or 24), 24 * 30))
    limit = max(100, min(int(limit or 5000), 20000))
    now = time.time()
    cutoff = now - since_hours * 3600
    res = await store.list_syscall_events(limit=limit, offset=0, tenant_id=tenant_id, kind="skill")
    items = res.get("items") or []
    items = [it for it in items if float(it.get("created_at") or 0) >= cutoff]
    by_name: Dict[str, Any] = {}
    for it in items:
        nm = str(it.get("name") or "<unknown>")
        st = str(it.get("status") or "unknown")
        dur = float(it.get("duration_ms") or 0.0)
        x = by_name.setdefault(
            nm,
            {
                "name": nm,
                "total": 0,
                "counts": {},
                "avg_duration_ms": 0.0,
                "p95_duration_ms": None,
                "durations_ms": [],
            },
        )
        x["total"] += 1
        x["counts"][st] = int(x["counts"].get(st, 0)) + 1
        if dur > 0:
            x["durations_ms"].append(dur)
    out = []
    for nm, x in by_name.items():
        durs = sorted(x.get("durations_ms") or [])
        avg = float(sum(durs) / len(durs)) if durs else 0.0
        p95 = None
        if durs:
            idx = int(max(0, min(len(durs) - 1, round(0.95 * (len(durs) - 1)))))
            p95 = float(durs[idx])
        out.append({"name": nm, "total": x["total"], "counts": x["counts"], "avg_duration_ms": avg, "p95_duration_ms": p95})
    out.sort(key=lambda r: int(r.get("total") or 0), reverse=True)
    return {"items": out, "total": len(out), "since_hours": since_hours}


async def skill_routing_funnel(
    *,
    store: Any,
    tenant_id: Optional[str],
    since_hours: int,
    limit: int,
    coding_policy_profile: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Funnel view per skill:
    - routing.selected / routing.policy_denied / routing.approval_required from syscall_events(kind=routing,name=skill_route)
    - execution success/failed from syscall_events(kind=skill)
    """
    if not store:
        return {"items": [], "total": 0}
    since_hours = max(1, min(int(since_hours or 24), 24 * 30))
    limit = max(200, min(int(limit or 20000), 20000))
    now = time.time()
    cutoff = now - since_hours * 3600
    prof = str(coding_policy_profile or "").strip().lower() or None

    # routing decision totals (denominator)
    totals = {"decision_total": 0, "skill_selected": 0, "tool_selected": 0, "no_action": 0}
    dr = await store.list_syscall_events(limit=limit, offset=0, tenant_id=tenant_id, kind="routing", name="routing_decision")
    ditems = [it for it in (dr.get("items") or []) if float(it.get("created_at") or 0) >= cutoff]
    seen_decisions: set[str] = set()
    decision_selected: Dict[str, Dict[str, str]] = {}
    for it in ditems:
        args = it.get("args") or {}
        if prof and str(args.get("coding_policy_profile") or "").strip().lower() != prof:
            continue
        did = str(args.get("routing_decision_id") or "")
        if did:
            if did in seen_decisions:
                continue
            seen_decisions.add(did)
        totals["decision_total"] += 1
        sk = str(args.get("selected_kind") or "")
        # prefer stable id field when available
        sn = str(args.get("selected_skill_id") or args.get("selected_name") or "")
        if sk == "skill":
            totals["skill_selected"] += 1
        elif sk == "tool":
            totals["tool_selected"] += 1
        else:
            totals["no_action"] += 1
        if did:
            decision_selected[did] = {"selected_kind": sk, "selected_name": sn}

    # strict eval events (numerator/denominator for strict miss rate)
    strict_totals = {
        "eligible_total": 0,
        "miss_total": 0,
        "miss_tool": 0,
        "miss_no_action": 0,
        "misroute": 0,
        "hit": 0,
        "no_eligible": 0,
    }
    strict_by_skill_top1: Dict[str, int] = {}
    strict_by_skill_misroute: Dict[str, int] = {}
    try:
        sr = await store.list_syscall_events(limit=limit, offset=0, tenant_id=tenant_id, kind="routing", name="routing_strict_eval")
        sitems = [it for it in (sr.get("items") or []) if float(it.get("created_at") or 0) >= cutoff]
        for it in sitems:
            args = it.get("args") or {}
            if prof and str(args.get("coding_policy_profile") or "").strip().lower() != prof:
                continue
            if bool(args.get("strict_eligible")):
                strict_totals["eligible_total"] += 1
            outc = str(args.get("strict_outcome") or "")
            if outc:
                strict_totals[outc] = int(strict_totals.get(outc, 0)) + 1
            if outc in ("miss_tool", "miss_no_action", "misroute"):
                strict_totals["miss_total"] += 1
            # per-skill attribution:
            top1_id = str(args.get("eligible_top1_skill_id") or "")
            if top1_id and outc in ("miss_tool", "miss_no_action", "misroute"):
                strict_by_skill_top1[top1_id] = int(strict_by_skill_top1.get(top1_id, 0)) + 1
            if outc == "misroute":
                sel = str(args.get("selected_skill_id") or args.get("selected_name") or "")
                if sel:
                    strict_by_skill_misroute[sel] = int(strict_by_skill_misroute.get(sel, 0)) + 1
    except Exception:
        pass

    # routing events (dedup by routing_decision_id when present)
    rr = await store.list_syscall_events(limit=limit, offset=0, tenant_id=tenant_id, kind="routing", name="skill_route")
    ritems = [it for it in (rr.get("items") or []) if float(it.get("created_at") or 0) >= cutoff]
    by_skill: Dict[str, Any] = {}
    seen_selected: set[str] = set()
    for it in ritems:
        args = it.get("args") or {}
        if prof and str(args.get("coding_policy_profile") or "").strip().lower() != prof:
            continue
        nm = str(args.get("skill") or it.get("name") or "<unknown>")
        st = str(it.get("status") or "unknown")
        x = by_skill.setdefault(nm, {"name": nm, "routing": {}, "exec": {}, "total_selected": 0})
        did = str(args.get("routing_decision_id") or "")
        if st == "selected" and did:
            key = f"{did}:{nm}"
            if key in seen_selected:
                continue
            seen_selected.add(key)
        x["routing"][st] = int(x["routing"].get(st, 0)) + 1
        if st == "selected":
            x["total_selected"] += 1

    # candidates snapshots (best-effort)
    cr = await store.list_syscall_events(limit=limit, offset=0, tenant_id=tenant_id, kind="routing", name="skill_candidates")
    citems = [it for it in (cr.get("items") or []) if float(it.get("created_at") or 0) >= cutoff]
    cr2 = await store.list_syscall_events(limit=limit, offset=0, tenant_id=tenant_id, kind="routing", name="skill_candidates_snapshot")
    citems += [it for it in (cr2.get("items") or []) if float(it.get("created_at") or 0) >= cutoff]
    seen_cand: set[str] = set()
    cand_map_top1: Dict[str, str] = {}
    cand_map_all: Dict[str, set] = {}
    cand_rank_map: Dict[str, Dict[str, int]] = {}
    cand_score_map: Dict[str, Dict[str, float]] = {}
    cand_meta_map: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for it in citems:
        args = it.get("args") or {}
        if prof and str(args.get("coding_policy_profile") or "").strip().lower() != prof:
            continue
        did = str(args.get("routing_decision_id") or "")
        cands = args.get("candidates") if isinstance(args.get("candidates"), list) else []
        for idx, c in enumerate(cands[:20]):
            if not isinstance(c, dict):
                continue
            sid = str(c.get("skill_id") or c.get("name") or "<unknown>")
            x = by_skill.setdefault(sid, {"name": sid, "routing": {}, "exec": {}, "total_selected": 0})
            if did:
                key = f"{did}:{sid}:{idx}"
                if key in seen_cand:
                    continue
                seen_cand.add(key)
                cand_map_all.setdefault(did, set()).add(sid)
                cand_rank_map.setdefault(did, {})[sid] = idx
                try:
                    cand_score_map.setdefault(did, {})[sid] = float(c.get("score") or 0.0)
                except Exception:
                    cand_score_map.setdefault(did, {})[sid] = 0.0
                cand_meta_map.setdefault(did, {})[sid] = {
                    "perm": c.get("perm"),
                    "exec_perm": c.get("exec_perm"),
                    "skill_kind": c.get("skill_kind"),
                    "scope": c.get("scope"),
                }
                if idx == 0 and did not in cand_map_top1:
                    cand_map_top1[did] = sid
            x["candidate_any"] = int(x.get("candidate_any") or 0) + 1
            if idx == 0:
                x["candidate_top1"] = int(x.get("candidate_top1") or 0) + 1

    # wrong selection metrics (per selected skill)
    for did, sel in decision_selected.items():
        if sel.get("selected_kind") != "skill":
            continue
        sn = sel.get("selected_name") or ""
        if not sn:
            continue
        x = by_skill.setdefault(sn, {"name": sn, "routing": {}, "exec": {}, "total_selected": 0})
        top1 = cand_map_top1.get(did)
        allset = cand_map_all.get(did)
        if top1 and sn != top1:
            x["selected_not_top1"] = int(x.get("selected_not_top1") or 0) + 1
            try:
                m = (cand_meta_map.get(did) or {}).get(top1) or {}
                if str(m.get("perm") or "") == "deny":
                    x["top1_permission_denied"] = int(x.get("top1_permission_denied") or 0) + 1
                if str(m.get("skill_kind") or "") == "executable" and str(m.get("exec_perm") or "") == "ask":
                    x["top1_approval_required"] = int(x.get("top1_approval_required") or 0) + 1
            except Exception:
                pass
        if allset is not None and len(allset) > 0 and sn not in allset:
            x["selected_not_in_candidates"] = int(x.get("selected_not_in_candidates") or 0) + 1
        try:
            rank = (cand_rank_map.get(did) or {}).get(sn)
            if isinstance(rank, int):
                x["selected_in_candidates_count"] = int(x.get("selected_in_candidates_count") or 0) + 1
                x["selected_rank_sum"] = int(x.get("selected_rank_sum") or 0) + int(rank)
                if rank >= 3:
                    x["selected_rank_ge3"] = int(x.get("selected_rank_ge3") or 0) + 1
        except Exception:
            pass
        try:
            ss = (cand_score_map.get(did) or {}).get(sn)
            ts = (cand_score_map.get(did) or {}).get(top1) if top1 else None
            if ss is not None:
                x["selected_score_sum"] = float(x.get("selected_score_sum") or 0.0) + float(ss)
                x["selected_score_cnt"] = int(x.get("selected_score_cnt") or 0) + 1
            if ts is not None:
                x["top1_score_sum"] = float(x.get("top1_score_sum") or 0.0) + float(ts)
                x["top1_score_cnt"] = int(x.get("top1_score_cnt") or 0) + 1
            if ss is not None and ts is not None:
                x["score_gap_sum"] = float(x.get("score_gap_sum") or 0.0) + float(ts - ss)
                x["score_gap_cnt"] = int(x.get("score_gap_cnt") or 0) + 1
        except Exception:
            pass

    em = await skill_invocation_metrics(store=store, tenant_id=tenant_id, since_hours=since_hours, limit=limit)
    for it in em.get("items") or []:
        nm = str(it.get("name") or "<unknown>")
        x = by_skill.setdefault(nm, {"name": nm, "routing": {}, "exec": {}, "total_selected": 0})
        x["exec"] = it.get("counts") or {}
        x["avg_duration_ms"] = it.get("avg_duration_ms")
        x["p95_duration_ms"] = it.get("p95_duration_ms")

    out = []
    for nm, x in by_skill.items():
        selected = int(x.get("routing", {}).get("selected", 0))
        appr = int(x.get("routing", {}).get("approval_required", 0))
        denied = int(x.get("routing", {}).get("policy_denied", 0))
        succ = int((x.get("exec") or {}).get("success", 0))
        fail = int((x.get("exec") or {}).get("failed", 0))
        executed = succ + fail
        cand_any = int(x.get("candidate_any") or 0)
        cand_top1 = int(x.get("candidate_top1") or 0)
        in_cnt = int(x.get("selected_in_candidates_count") or 0)
        rank_sum = int(x.get("selected_rank_sum") or 0)
        avg_rank = (float(rank_sum) / in_cnt) if in_cnt else None
        rank_ge3 = int(x.get("selected_rank_ge3") or 0)
        sel_sc_cnt = int(x.get("selected_score_cnt") or 0)
        top1_sc_cnt = int(x.get("top1_score_cnt") or 0)
        gap_cnt = int(x.get("score_gap_cnt") or 0)
        sel_sc_avg = (float(x.get("selected_score_sum") or 0.0) / sel_sc_cnt) if sel_sc_cnt else None
        top1_sc_avg = (float(x.get("top1_score_sum") or 0.0) / top1_sc_cnt) if top1_sc_cnt else None
        gap_avg = (float(x.get("score_gap_sum") or 0.0) / gap_cnt) if gap_cnt else None
        out.append(
            {
                "name": nm,
                "selected": selected,
                "approval_required": appr,
                "policy_denied": denied,
                "executed": executed,
                "success": succ,
                "failed": fail,
                "candidate_any": cand_any,
                "candidate_top1": cand_top1,
                "candidate_to_selected_rate": (selected / cand_any) if cand_any else None,
                "selected_rank_avg": avg_rank,
                "selected_rank_ge3": rank_ge3,
                "exec_success_rate": (succ / executed) if executed else None,
                "selected_to_executed_rate": (executed / selected) if selected else None,
                "avg_duration_ms": x.get("avg_duration_ms"),
                "p95_duration_ms": x.get("p95_duration_ms"),
                "selected_not_top1": int(x.get("selected_not_top1") or 0),
                "selected_not_in_candidates": int(x.get("selected_not_in_candidates") or 0),
                "selected_score_avg": sel_sc_avg,
                "top1_score_avg": top1_sc_avg,
                "score_gap_avg": gap_avg,
                "top1_permission_denied": int(x.get("top1_permission_denied") or 0),
                "top1_approval_required": int(x.get("top1_approval_required") or 0),
                "strict_missed_as_top1": int(strict_by_skill_top1.get(nm, 0)),
                "strict_misroute_count": int(strict_by_skill_misroute.get(nm, 0)),
            }
        )
    out.sort(key=lambda r: int(r.get("selected") or 0), reverse=True)
    decision_total = int(totals.get("decision_total") or 0)
    miss_rate = None
    if decision_total:
        miss_rate = float((totals.get("tool_selected", 0) + totals.get("no_action", 0)) / decision_total)
    strict_miss_rate = None
    if int(strict_totals.get("eligible_total") or 0) > 0:
        strict_miss_rate = float(int(strict_totals.get("miss_total") or 0) / int(strict_totals.get("eligible_total") or 1))
    return {
        "items": out,
        "total": len(out),
        "since_hours": since_hours,
        "totals": totals,
        "miss_rate": miss_rate,
        "strict": {"totals": strict_totals, "miss_rate": strict_miss_rate},
        "coding_policy_profile": prof or "all",
    }


async def routing_explain_events(
    *,
    store: Any,
    tenant_id: Optional[str],
    since_hours: int,
    limit: int,
    skill_id: Optional[str] = None,
    selected_kind: Optional[str] = None,
    coding_policy_profile: Optional[str] = None,
) -> Dict[str, Any]:
    if not store:
        return {"items": [], "total": 0}
    since_hours = max(1, min(int(since_hours or 24), 24 * 30))
    limit = max(50, min(int(limit or 500), 5000))
    now = time.time()
    cutoff = now - since_hours * 3600
    prof = str(coding_policy_profile or "").strip().lower() or None
    sk = str(selected_kind or "").strip().lower() or None
    sid = str(skill_id or "").strip() or None

    res = await store.list_syscall_events(limit=limit, offset=0, tenant_id=tenant_id, kind="routing", name="routing_explain")
    items = [it for it in (res.get("items") or []) if float(it.get("created_at") or 0) >= cutoff]
    out = []
    for it in items:
        args = it.get("args") or {}
        if prof and str(args.get("coding_policy_profile") or "").strip().lower() != prof:
            continue
        if sk and str(args.get("selected_kind") or "").strip().lower() != sk:
            continue
        if sid:
            s0 = str(args.get("selected_skill_id") or args.get("selected_name") or "")
            if s0 != sid:
                continue
        out.append(
            {
                "created_at": it.get("created_at"),
                "routing_decision_id": args.get("routing_decision_id"),
                "selected_kind": args.get("selected_kind"),
                "selected_name": args.get("selected_name"),
                "coding_policy_profile": args.get("coding_policy_profile"),
                "top1_skill_id": args.get("top1_skill_id"),
                "top1_score": args.get("top1_score"),
                "top1_gate_hint": args.get("top1_gate_hint"),
                "selected_rank": args.get("selected_rank"),
                "selected_score": args.get("selected_score"),
                "score_gap": args.get("score_gap"),
                "result_status": args.get("result_status"),
                "result_error": args.get("result_error"),
                "query_excerpt": args.get("query_excerpt"),
                "candidates_top": args.get("candidates_top"),
            }
        )
    out.sort(key=lambda x: float(x.get("created_at") or 0), reverse=True)
    return {"items": out, "total": len(out), "since_hours": since_hours, "coding_policy_profile": prof or "all"}


async def routing_replay(
    *,
    store: Any,
    tenant_id: Optional[str],
    routing_decision_id: str,
    since_hours: int,
    limit: int,
    coding_policy_profile: Optional[str] = None,
) -> Dict[str, Any]:
    if not store:
        return {"items": [], "total": 0}
    rid = str(routing_decision_id or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="missing_routing_decision_id")
    since_hours = max(1, min(int(since_hours or 24), 24 * 30))
    limit = max(200, min(int(limit or 2000), 20000))
    now = time.time()
    cutoff = now - since_hours * 3600
    prof = str(coding_policy_profile or "").strip().lower() or None

    dr = await store.list_syscall_events(limit=limit, offset=0, tenant_id=tenant_id, kind="routing", name="routing_decision")
    ditems = [it for it in (dr.get("items") or []) if float(it.get("created_at") or 0) >= cutoff]
    decision = None
    for it in ditems:
        args = it.get("args") or {}
        if str(args.get("routing_decision_id") or "") == rid:
            if prof and str(args.get("coding_policy_profile") or "").strip().lower() != prof:
                continue
            decision = it
            break
    if decision is None:
        raise HTTPException(status_code=404, detail="routing_decision_not_found")

    run_id = decision.get("run_id")
    trace_id = decision.get("trace_id")
    tid = decision.get("tenant_id") or tenant_id

    routing_events = []
    if run_id:
        rr = await store.list_syscall_events(limit=2000, offset=0, tenant_id=tid, run_id=str(run_id), kind="routing")
        routing_events = rr.get("items") or []
    if decision not in routing_events:
        routing_events.append(decision)

    routing_events2 = []
    for it in routing_events:
        args = it.get("args") or {}
        if str(args.get("routing_decision_id") or "") == rid or it.get("name") == "routing_decision":
            if prof and str(args.get("coding_policy_profile") or "").strip().lower() != prof:
                continue
            routing_events2.append(it)
    routing_events2.sort(key=lambda x: float(x.get("created_at") or 0))

    skills = []
    tools = []
    changesets = []
    if run_id:
        sr = await store.list_syscall_events(limit=500, offset=0, tenant_id=tid, run_id=str(run_id), kind="skill")
        skills = sr.get("items") or []
        tr = await store.list_syscall_events(limit=500, offset=0, tenant_id=tid, run_id=str(run_id), kind="tool")
        tools = tr.get("items") or []
        cr = await store.list_syscall_events(limit=500, offset=0, tenant_id=tid, run_id=str(run_id), kind="changeset")
        changesets = cr.get("items") or []

    approval_ids: set[str] = set()
    for it in (skills or []) + (tools or []) + (changesets or []) + (routing_events2 or []):
        aid = str(it.get("approval_request_id") or "").strip()
        if aid:
            approval_ids.add(aid)
        try:
            res = it.get("result") if isinstance(it.get("result"), dict) else {}
            aid2 = str(res.get("approval_request_id") or "").strip()
            if aid2:
                approval_ids.add(aid2)
        except Exception:
            pass
    linkages = {}
    try:
        if approval_ids:
            linkages = await store.get_change_linkages_for_approval_request_ids(sorted(list(approval_ids))[:50])
    except Exception:
        linkages = {}

    explain = next((x for x in routing_events2 if x.get("name") == "routing_explain"), None)
    strict = next((x for x in routing_events2 if x.get("name") == "routing_strict_eval"), None)
    candidates = next((x for x in routing_events2 if x.get("name") == "skill_candidates_snapshot"), None)

    return {
        "routing_decision_id": rid,
        "tenant_id": tid,
        "run_id": run_id,
        "trace_id": trace_id,
        "decision": decision,
        "explain": explain,
        "strict": strict,
        "candidates": candidates,
        "routing_events": routing_events2,
        "skill_syscalls": skills,
        "tool_syscalls": tools,
        "changesets": changesets,
        "linkages": linkages,
        "coding_policy_profile": prof or "all",
    }


async def routing_metrics(
    *,
    store: Any,
    tenant_id: Optional[str],
    since_hours: int,
    bucket_minutes: int,
    skill_id: Optional[str],
    scope: str,
    coding_policy_profile: Optional[str] = None,
    limit: int = 20000,
) -> Dict[str, Any]:
    if not store:
        return {"series": {}, "hists": {}, "meta": {}}
    since_hours = max(1, min(int(since_hours or 24), 24 * 30))
    bucket_minutes = max(1, min(int(bucket_minutes or 60), 24 * 60))
    limit = max(200, min(int(limit or 20000), 200000))
    now = time.time()
    cutoff = now - since_hours * 3600
    prof = str(coding_policy_profile or "").strip().lower() or None
    sid = str(skill_id or "").strip() or None
    bsec = bucket_minutes * 60

    strict_buckets: Dict[int, Dict[str, int]] = {}
    try:
        sr = await store.list_syscall_events(limit=limit, offset=0, tenant_id=tenant_id, kind="routing", name="routing_strict_eval")
        for it in (sr.get("items") or []):
            ts = float(it.get("created_at") or 0)
            if ts < cutoff:
                continue
            args = it.get("args") or {}
            if prof and str(args.get("coding_policy_profile") or "").strip().lower() != prof:
                continue
            if not bool(args.get("strict_eligible")):
                continue
            if sid and str(args.get("eligible_top1_skill_id") or "") != sid:
                continue
            b = int(ts // bsec) * bsec
            buck = strict_buckets.setdefault(
                b,
                {"eligible_total": 0, "miss_total": 0, "misroute": 0, "miss_tool": 0, "miss_no_action": 0, "hit": 0},
            )
            buck["eligible_total"] += 1
            outc = str(args.get("strict_outcome") or "")
            if outc in ("miss_tool", "miss_no_action", "misroute"):
                buck["miss_total"] += 1
            if outc in ("misroute", "miss_tool", "miss_no_action", "hit"):
                buck[outc] = int(buck.get(outc) or 0) + 1
    except Exception:
        pass

    strict_miss_series = []
    strict_misroute_series = []
    strict_miss_tool_series = []
    strict_miss_no_action_series = []
    for b in sorted(strict_buckets.keys()):
        buck = strict_buckets[b]
        et = int(buck.get("eligible_total") or 0)
        mt = int(buck.get("miss_total") or 0)
        mr = int(buck.get("misroute") or 0)
        mtool = int(buck.get("miss_tool") or 0)
        mno = int(buck.get("miss_no_action") or 0)
        strict_miss_series.append([b, (float(mt) / float(et)) if et else None, et, mt])
        strict_misroute_series.append([b, (float(mr) / float(et)) if et else None, et, mr])
        strict_miss_tool_series.append([b, (float(mtool) / float(et)) if et else None, et, mtool])
        strict_miss_no_action_series.append([b, (float(mno) / float(et)) if et else None, et, mno])

    gap_buckets: Dict[int, Dict[str, Any]] = {}
    rank_hist = {"0": 0, "1": 0, "2": 0, "3+": 0}
    try:
        er = await store.list_syscall_events(limit=limit, offset=0, tenant_id=tenant_id, kind="routing", name="routing_explain")
        for it in (er.get("items") or []):
            ts = float(it.get("created_at") or 0)
            if ts < cutoff:
                continue
            args = it.get("args") or {}
            if prof and str(args.get("coding_policy_profile") or "").strip().lower() != prof:
                continue
            if str(args.get("selected_kind") or "") != "skill":
                continue
            if sid and str(args.get("selected_name") or "") != sid:
                continue
            sg = args.get("score_gap")
            try:
                sgf = float(sg) if sg is not None else None
            except Exception:
                sgf = None
            if sgf is not None:
                b = int(ts // bsec) * bsec
                buck = gap_buckets.setdefault(b, {"sum": 0.0, "cnt": 0})
                buck["sum"] += float(sgf)
                buck["cnt"] += 1
            rnk = args.get("selected_rank")
            if isinstance(rnk, int):
                if rnk <= 0:
                    rank_hist["0"] += 1
                elif rnk == 1:
                    rank_hist["1"] += 1
                elif rnk == 2:
                    rank_hist["2"] += 1
                else:
                    rank_hist["3+"] += 1
    except Exception:
        pass

    gap_series = []
    for b in sorted(gap_buckets.keys()):
        buck = gap_buckets[b]
        cnt = int(buck.get("cnt") or 0)
        gap_series.append([b, (float(buck.get("sum") or 0.0) / cnt) if cnt else None, cnt])

    return {
        "series": {
            "strict_miss_rate": strict_miss_series,
            "strict_misroute_rate": strict_misroute_series,
            "strict_miss_tool_rate": strict_miss_tool_series,
            "strict_miss_no_action_rate": strict_miss_no_action_series,
            "score_gap_avg": gap_series,
        },
        "hists": {"selected_rank": rank_hist},
        "meta": {
            "scope": scope,
            "since_hours": since_hours,
            "bucket_minutes": bucket_minutes,
            "skill_id": sid,
            "coding_policy_profile": prof or "all",
        },
    }


def routing_metric_tags() -> Dict[str, Any]:
    return {
        "scalars": [
            {"tag": "strict_miss_rate", "display_name": "strict_miss_rate", "description": "严格未命中率（miss_total/eligible_total），按时间分桶。"},
            {"tag": "strict_misroute_rate", "display_name": "strict_misroute_rate", "description": "严格口径错路由率（misroute/eligible_total），按时间分桶。"},
            {"tag": "strict_miss_tool_rate", "display_name": "strict_miss_tool_rate", "description": "严格口径 miss_tool 率（miss_tool/eligible_total），按时间分桶。"},
            {"tag": "strict_miss_no_action_rate", "display_name": "strict_miss_no_action_rate", "description": "严格口径 miss_no_action 率（miss_no_action/eligible_total），按时间分桶。"},
            {"tag": "score_gap_avg", "display_name": "score_gap_avg", "description": "score_gap 的均值（eligible_top1_score - selected_score），按时间分桶。"},
        ],
        "hists": [
            {"tag": "selected_rank", "display_name": "selected_rank", "description": "selected_rank 的分布（0/1/2/3+），用于判断错路由长尾。"}
        ],
    }

