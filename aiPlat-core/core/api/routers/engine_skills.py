from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime
from typing import Any, Annotated, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from core.api.deps.rbac import actor_from_http, rbac_guard
from core.api.utils.governance import governance_links
from core.api.utils.run_contract import wrap_execution_result_as_run_summary
from core.api.utils.skills_meta import load_skill_spec_v2_schema, permission_catalog, req_tenant_channel, schema_version, skill_governance_preview
from core.apps.skills import get_skill_registry
from core.harness.integration import get_harness, KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.kernel.types import ExecutionRequest
from core.schemas import SkillCreateRequest, SkillExecuteRequest

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


def _skill_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "skill_manager", None) if rt else None


def _ws_skill_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "workspace_skill_manager", None) if rt else None


def _ws_agent_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "workspace_agent_manager", None) if rt else None


def _ws_mcp_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "workspace_mcp_manager", None) if rt else None


def _mcp_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "mcp_manager", None) if rt else None


def _job_scheduler(rt: Optional[KernelRuntime]):
    return getattr(rt, "job_scheduler", None) if rt else None


def _approval_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "approval_manager", None) if rt else None


def _trace_service(rt: Optional[KernelRuntime]):
    return getattr(rt, "trace_service", None) if rt else None


async def _record_changeset(
    rt: Optional[KernelRuntime],
    *,
    name: str,
    target_type: str,
    target_id: str,
    status: str = "success",
    args: Dict[str, Any] | None = None,
    result: Dict[str, Any] | None = None,
    error: str | None = None,
    trace_id: str | None = None,
    run_id: str | None = None,
    user_id: str = "admin",
    session_id: str | None = None,
    approval_request_id: str | None = None,
    tenant_id: str | None = None,
) -> None:
    from core.governance.changeset import record_changeset

    return await record_changeset(
        store=_store(rt),
        name=name,
        target_type=target_type,
        target_id=target_id,
        status=status,
        args=args,
        result=result,
        error=error,
        trace_id=trace_id,
        run_id=run_id,
        user_id=user_id,
        session_id=session_id,
        approval_request_id=approval_request_id,
        tenant_id=tenant_id,
    )


def _new_change_id() -> str:
    return f"chg-{uuid.uuid4().hex[:12]}"


def _gov_links(*, change_id: str | None = None, approval_request_id: str | None = None, run_id: str | None = None, trace_id: str | None = None) -> Dict[str, Any]:
    return governance_links(
        change_id=str(change_id) if change_id else None,
        approval_request_id=str(approval_request_id) if approval_request_id else None,
        run_id=str(run_id) if run_id else None,
        trace_id=str(trace_id) if trace_id else None,
    )


def _inject_http_request_context(payload: Any, http_request: Request, *, entrypoint: str) -> Any:
    """
    Best-effort: inject tenant/actor/request identity from headers into payload.context.
    Used for PR-01 tenant/actor propagation into harness/syscalls.
    """
    if not isinstance(payload, dict):
        return payload
    try:
        ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        ctx = dict(ctx) if isinstance(ctx, dict) else {}
        ctx.setdefault("entrypoint", str(entrypoint or "api"))

        tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID") or http_request.headers.get("x-aiplat-tenant-id")
        actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID") or http_request.headers.get("x-aiplat-actor-id")
        actor_role = http_request.headers.get("X-AIPLAT-ACTOR-ROLE") or http_request.headers.get("x-aiplat-actor-role")
        req_id = http_request.headers.get("X-AIPLAT-REQUEST-ID") or http_request.headers.get("x-aiplat-request-id")
        if tenant_id:
            ctx.setdefault("tenant_id", str(tenant_id))
        if actor_id:
            ctx.setdefault("actor_id", str(actor_id))
        if actor_role:
            ctx.setdefault("actor_role", str(actor_role))
        if req_id:
            ctx.setdefault("request_id", str(req_id))
        payload["context"] = ctx
    except Exception:
        return payload
    return payload


async def _audit_execute(
    rt: Optional[KernelRuntime],
    *,
    http_request: Request,
    payload: Optional[Dict[str, Any]],
    resource_type: str,
    resource_id: str,
    resp: Dict[str, Any],
    action: Optional[str] = None,
) -> None:
    """PR-06: enterprise audit for execute entrypoints (best-effort)."""
    store = _store(rt)
    if not store:
        return
    try:
        actor = actor_from_http(http_request, payload)
        await store.add_audit_log(
            action=action or f"execute_{resource_type}",
            status=str(resp.get("legacy_status") or resp.get("status") or ("ok" if resp.get("ok") else "failed")),
            tenant_id=str(actor.get("tenant_id") or "") or None,
            actor_id=str(actor.get("actor_id") or "") or None,
            actor_role=str(actor.get("actor_role") or "") or None,
            resource_type=str(resource_type),
            resource_id=str(resource_id),
            request_id=str(resp.get("request_id") or "") or (http_request.headers.get("X-AIPLAT-REQUEST-ID") or http_request.headers.get("x-aiplat-request-id")),
            run_id=str(resp.get("run_id") or resp.get("execution_id") or "") or None,
            trace_id=str(resp.get("trace_id") or "") or None,
            detail={"status": resp.get("status"), "legacy_status": resp.get("legacy_status"), "error": resp.get("error")},
        )
    except Exception:
        return


async def _get_trusted_skill_pubkeys_map(rt: Optional[KernelRuntime]) -> Dict[str, str]:
    """
    Global trusted public keys for skill signature verification.
    Stored in global_setting: trusted_skill_pubkeys = {"keys":[{"key_id","public_key"}]}
    """
    from core.security.skill_signature_gate import get_trusted_skill_pubkeys_map

    return await get_trusted_skill_pubkeys_map(_store(rt))


async def _maybe_verify_and_audit_skill_signature(rt: Optional[KernelRuntime], *, skill: Any, scope: str) -> None:
    """
    Best-effort: compute verification status and record a changeset event.
    """
    try:
        meta = getattr(skill, "metadata", None)
        if not isinstance(meta, dict):
            return
        prov = meta.get("provenance") if isinstance(meta.get("provenance"), dict) else {}
        integ = meta.get("integrity") if isinstance(meta.get("integrity"), dict) else {}
        if not prov.get("signature") or not integ.get("bundle_sha256"):
            return

        trusted = await _get_trusted_skill_pubkeys_map(rt)
        mgr = _skill_mgr(rt)
        if not mgr:
            return
        prov2 = mgr.compute_skill_signature_verification(skill, trusted)
        if prov2:
            meta["provenance"] = prov2

        status = "success" if bool(prov2.get("signature_verified")) else "failed"
        if not trusted:
            status = "failed"
        await _record_changeset(
            rt,
            name="skill_signature_verify",
            target_type="skill",
            target_id=str(getattr(skill, "id", "") or ""),
            status=status,
            args={"scope": scope, "trusted_keys_count": len(trusted)},
            result={
                "bundle_sha256": integ.get("bundle_sha256"),
                "signature_verified": prov2.get("signature_verified"),
                "signature_verified_key_id": prov2.get("signature_verified_key_id"),
                "signature_verified_reason": prov2.get("signature_verified_reason"),
            },
        )
    except Exception:
        return


@router.get("/skills")
async def list_skills(
    category: Optional[str] = None,
    enabled_only: bool = False,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    rt: RuntimeDep = None,
):
    """List all skills (engine scope)."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")

    skills = await mgr.list_skills(category, status, limit, offset)

    trusted_keys = await _get_trusted_skill_pubkeys_map(rt)
    result = []
    for s in skills:
        if enabled_only and getattr(s, "status", None) != "enabled":
            continue
        try:
            if trusted_keys and isinstance(getattr(s, "metadata", None), dict):
                prov2 = mgr.compute_skill_signature_verification(s, trusted_keys)
                if prov2:
                    s.metadata["provenance"] = prov2
        except Exception:
            pass
        result.append(
            {
                "id": s.id,
                "name": s.name,
                "category": s.type,
                "description": s.description,
                "status": s.status,
                "enabled": s.status == "enabled",
                "config": s.config or {},
                "input_schema": s.input_schema or {},
                "output_schema": s.output_schema or {},
                "metadata": s.metadata or {},
            }
        )

    total = 0
    try:
        total = int((mgr.get_skill_count() or {}).get("total", 0))
    except Exception:
        total = len(result)

    return {"skills": result, "total": total, "limit": limit, "offset": offset}


@router.post("/skills")
async def create_skill(request: SkillCreateRequest, rt: RuntimeDep = None):
    """Create a new skill (engine scope)."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")

    md = request.metadata or {}
    if getattr(request, "skill_kind", None):
        md["skill_kind"] = request.skill_kind
    if getattr(request, "permissions", None) is not None:
        md["permissions"] = request.permissions
    if getattr(request, "trigger_conditions", None) is not None:
        md["trigger_conditions"] = request.trigger_conditions
    if getattr(request, "decision_tree", None) is not None:
        md["decision_tree"] = request.decision_tree
    if getattr(request, "resources", None) is not None:
        md["resources"] = request.resources

    skill = await mgr.create_skill(
        name=str(getattr(request, "display_name", None) or request.name),
        skill_id=getattr(request, "skill_id", None),
        skill_type=request.category,
        description=request.description,
        config=request.config or {},
        input_schema=request.input_schema or {},
        output_schema=request.output_schema or {},
        metadata=md,
        version=getattr(request, "version", None),
        status=getattr(request, "status", None),
    )
    try:
        await _record_changeset(
            rt,
            name="skill_upsert",
            target_type="skill",
            target_id=str(skill.id),
            args={"scope": "engine", "category": request.category, "name": request.name},
            result={
                "status": "created",
                "integrity": (getattr(skill, "metadata", None) or {}).get("integrity") if isinstance(getattr(skill, "metadata", None), dict) else None,
                "provenance": (getattr(skill, "metadata", None) or {}).get("provenance") if isinstance(getattr(skill, "metadata", None), dict) else None,
            },
        )
    except Exception:
        pass
    try:
        await _maybe_verify_and_audit_skill_signature(rt, skill=skill, scope="engine")
    except Exception:
        pass
    return {"id": skill.id, "status": "created", "name": skill.name}


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str, rt: RuntimeDep = None):
    """Get skill details (engine scope)."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {
        "id": skill.id,
        "name": skill.name,
        "type": skill.type,
        "category": skill.type,
        "description": skill.description,
        "status": skill.status,
        "enabled": skill.status == "enabled",
        "config": skill.config or {},
        "input_schema": skill.input_schema or {},
        "output_schema": skill.output_schema or {},
        "metadata": skill.metadata or {},
    }


def _skill_tokenize_for_conflict(skill: Any) -> Dict[str, Any]:
    """Best-effort tokenization for conflict detection (no external deps)."""
    try:
        sid = str(getattr(skill, "id", "") or (skill.get("id") if isinstance(skill, dict) else "") or "")
    except Exception:
        sid = ""
    name = str(getattr(skill, "name", "") or (skill.get("name") if isinstance(skill, dict) else "") or "")
    meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
    meta = meta if isinstance(meta, dict) else {}
    tc = meta.get("trigger_conditions") or meta.get("trigger_keywords") or []
    kw = meta.get("keywords") if isinstance(meta.get("keywords"), dict) else {}
    neg = meta.get("negative_triggers") or []

    def _norm(x: str) -> str:
        s = str(x or "").strip().lower()
        s = re.sub(r"[\s\-\._/]+", " ", s)
        s = re.sub(r"[^\w\u4e00-\u9fff ]+", "", s)
        return s.strip()

    tokens = set()
    for it in (tc if isinstance(tc, list) else [tc]):
        s = _norm(str(it))
        if not s:
            continue
        tokens.add(s)
        for w in s.split():
            if len(w) >= 2:
                tokens.add(w)
    for k in ("objects", "actions", "constraints", "synonyms"):
        for it in (kw.get(k) or []) if isinstance(kw, dict) else []:
            s = _norm(str(it))
            if s:
                tokens.add(s)
    for it in (neg if isinstance(neg, list) else [neg]):
        s = _norm(str(it))
        if s:
            tokens.add(s)
    return {"skill_id": sid, "name": name, "tokens": sorted(list(tokens))}


async def _enrich_conflicts_for_skill(rt: Optional[KernelRuntime], *, skill_id: str, scope: str, raw_items: list) -> list:
    """
    Enrich conflict items with the opponent skill's detail (best-effort).
    This is used only for lint/fix generation (not persisted).
    """
    try:
        mgr = _ws_skill_mgr(rt) if scope == "workspace" else _skill_mgr(rt)
        if mgr is None:
            return raw_items
        out = []
        for it in raw_items or []:
            if not isinstance(it, dict):
                continue
            a = (it.get("skill_a") or {}) if isinstance(it.get("skill_a"), dict) else {}
            b = (it.get("skill_b") or {}) if isinstance(it.get("skill_b"), dict) else {}
            a_id = str(a.get("skill_id") or "")
            b_id = str(b.get("skill_id") or "")
            other_id = b_id if a_id == str(skill_id) else a_id
            other = None
            try:
                if other_id:
                    other = await mgr.get_skill(other_id)
            except Exception:
                other = None
            other_meta = (getattr(other, "metadata", None) or {}) if other is not None and isinstance(getattr(other, "metadata", None), dict) else {}
            other_obj = {
                "skill_id": other_id,
                "name": str(getattr(other, "name", "") or other_id),
                "trigger_conditions": other_meta.get("trigger_conditions") or [],
                "negative_triggers": other_meta.get("negative_triggers") or [],
                "keywords": other_meta.get("keywords") if isinstance(other_meta.get("keywords"), dict) else {},
                "description": str(getattr(other, "description", "") or ""),
            }
            it2 = dict(it)
            it2["other_skill"] = other_obj
            out.append(it2)
        return out
    except Exception:
        return raw_items


@router.get("/skills/meta/lint-conflicts")
async def lint_conflicts_engine_skills(
    tenant_id: Optional[str] = None,
    threshold: float = 0.35,
    min_overlap: int = 3,
    limit: int = 100,
    rt: RuntimeDep = None,
):
    """Detect likely routing conflicts among engine skills."""
    _ = tenant_id
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    threshold = float(threshold or 0.35)
    min_overlap = max(1, int(min_overlap or 3))
    limit = max(1, min(int(limit or 100), 500))

    skills = await mgr.list_skills(None, None, 500, 0)
    rows = [_skill_tokenize_for_conflict(s) for s in (skills or [])]
    conflicts = []
    for i in range(len(rows)):
        a = rows[i]
        ta = set(a["tokens"])
        if not ta:
            continue
        for j in range(i + 1, len(rows)):
            b = rows[j]
            tb = set(b["tokens"])
            if not tb:
                continue
            inter = ta & tb
            if len(inter) < min_overlap:
                continue
            uni = ta | tb
            score = float(len(inter) / max(1, len(uni)))
            if score < threshold:
                continue
            conflicts.append(
                {
                    "scope": "engine",
                    "skill_a": {"skill_id": a["skill_id"], "name": a["name"]},
                    "skill_b": {"skill_id": b["skill_id"], "name": b["name"]},
                    "jaccard": score,
                    "overlap_tokens": sorted(list(inter))[:30],
                    "suggestions": ["为两者补充 negative_triggers（明确不适用场景）", "为其中一个补充 constraints（如：按租户/按项目/仅后端/仅SQL）以提高区分度"],
                }
            )
    conflicts.sort(key=lambda x: float(x.get("jaccard") or 0.0), reverse=True)
    return {"status": "ok", "items": conflicts[:limit], "total": len(conflicts), "threshold": threshold, "min_overlap": min_overlap}


async def _skill_invocation_metrics(rt: Optional[KernelRuntime], *, tenant_id: Optional[str], since_hours: int, limit: int) -> Dict[str, Any]:
    store = _store(rt)
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
        x = by_name.setdefault(nm, {"name": nm, "total": 0, "counts": {}, "avg_duration_ms": 0.0, "p95_duration_ms": None, "durations_ms": []})
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


async def _skill_routing_funnel(rt: Optional[KernelRuntime], *, tenant_id: Optional[str], since_hours: int, limit: int) -> Dict[str, Any]:
    from core.observability.routing_service import skill_routing_funnel

    return await skill_routing_funnel(store=_store(rt), tenant_id=tenant_id, since_hours=since_hours, limit=limit, coding_policy_profile=None)


@router.get("/skills/observability/skill-metrics")
async def engine_skill_metrics(tenant_id: Optional[str] = None, since_hours: int = 24, limit: int = 5000, rt: RuntimeDep = None):
    """Aggregate syscall_events(kind=skill) into a skill-level metrics view (engine scope)."""
    return {"status": "ok", **(await _skill_invocation_metrics(rt, tenant_id=tenant_id, since_hours=since_hours, limit=limit))}


@router.get("/skills/{skill_id}/lint")
async def lint_engine_skill(skill_id: str, rt: RuntimeDep = None):
    """Lint an engine skill (read-only)."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    s = await mgr.get_skill(skill_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    from core.management.skill_linter import lint_skill, propose_skill_fixes

    try:
        fun = await _skill_routing_funnel(rt, tenant_id=None, since_hours=24, limit=20000)
        row = next((x for x in (fun.get("items") or []) if str(x.get("name") or "") == str(skill_id)), None)
        if row:
            md = s.metadata if isinstance(getattr(s, "metadata", None), dict) else {}
            md = {**md, "_observability": {"scope": "engine", **row}}
            try:
                s.metadata = md
            except Exception:
                pass
    except Exception:
        pass

    try:
        conf = await lint_conflicts_engine_skills(rt=rt, tenant_id=None, threshold=0.2, min_overlap=2, limit=200)
        items = conf.get("items") if isinstance(conf, dict) else None
        items = items if isinstance(items, list) else []
        related = []
        for it in items:
            if not isinstance(it, dict):
                continue
            a = (it.get("skill_a") or {}) if isinstance(it.get("skill_a"), dict) else {}
            b = (it.get("skill_b") or {}) if isinstance(it.get("skill_b"), dict) else {}
            if str(a.get("skill_id") or "") == str(skill_id) or str(b.get("skill_id") or "") == str(skill_id):
                related.append(it)
        related.sort(key=lambda x: float(x.get("jaccard") or 0.0), reverse=True)
        if related:
            related = await _enrich_conflicts_for_skill(rt, skill_id=str(skill_id), scope="engine", raw_items=related[:5])
            md = s.metadata if isinstance(getattr(s, "metadata", None), dict) else {}
            md = {**md, "_conflicts": related}
            try:
                s.metadata = md
            except Exception:
                pass
    except Exception:
        pass

    lint = lint_skill(s)
    fixes = propose_skill_fixes(skill=s, lint=lint)
    return {"skill_id": str(skill_id), "lint": lint, "fixes": fixes.get("fixes") or [], "fix_summary": fixes.get("summary") or {}}


@router.post("/skills/{skill_id}/apply-lint-fix")
async def apply_lint_fix_engine_skill(skill_id: str, request: Optional[Dict[str, Any]] = None, rt: RuntimeDep = None):
    """
    Apply lint fixes to an engine skill (Phase-1: markdown/schema fixes only).
    High-level behavior:
    - compute lint + fixes
    - filter to requested issue_codes/fix_ids (or auto_applicable=true by default)
    - apply frontmatter_merge ops via SkillManager.update_skill (output_schema only in Phase-1)
    """
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    req = request or {}
    dry_run = bool(req.get("dry_run", False))

    change_id = _new_change_id()
    try:
        from core.governance.gating import autosmoke_enforce, gate_with_change_control

        if autosmoke_enforce(store=_store(rt)):
            change_id = await gate_with_change_control(
                store=_store(rt),
                operation="skill.apply_lint_fix",
                targets=[("skill", str(skill_id))],
                actor={"actor_id": "admin"},
                workspace_agent_manager=_ws_agent_mgr(rt),
                workspace_skill_manager=_ws_skill_mgr(rt),
                skill_manager=mgr,
                workspace_mcp_manager=_ws_mcp_mgr(rt),
                mcp_manager=_mcp_mgr(rt),
            )
    except HTTPException:
        raise
    except Exception:
        pass

    s = await mgr.get_skill(skill_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

    from core.management.skill_linter import lint_skill, propose_skill_fixes

    try:
        fun = await _skill_routing_funnel(rt, tenant_id=None, since_hours=24, limit=20000)
        row = next((x for x in (fun.get("items") or []) if str(x.get("name") or "") == str(skill_id)), None)
        if row:
            md = s.metadata if isinstance(getattr(s, "metadata", None), dict) else {}
            md = {**md, "_observability": {"scope": "engine", **row}}
            try:
                s.metadata = md
            except Exception:
                pass
    except Exception:
        pass

    try:
        conf = await lint_conflicts_engine_skills(rt=rt, tenant_id=None, threshold=0.2, min_overlap=2, limit=200)
        items = conf.get("items") if isinstance(conf, dict) else None
        items = items if isinstance(items, list) else []
        related = []
        for it in items:
            if not isinstance(it, dict):
                continue
            a = (it.get("skill_a") or {}) if isinstance(it.get("skill_a"), dict) else {}
            b = (it.get("skill_b") or {}) if isinstance(it.get("skill_b"), dict) else {}
            if str(a.get("skill_id") or "") == str(skill_id) or str(b.get("skill_id") or "") == str(skill_id):
                related.append(it)
        related.sort(key=lambda x: float(x.get("jaccard") or 0.0), reverse=True)
        if related:
            related = await _enrich_conflicts_for_skill(rt, skill_id=str(skill_id), scope="engine", raw_items=related[:5])
            md = s.metadata if isinstance(getattr(s, "metadata", None), dict) else {}
            md = {**md, "_conflicts": related}
            try:
                s.metadata = md
            except Exception:
                pass
    except Exception:
        pass

    lint = lint_skill(s)
    fx = propose_skill_fixes(skill=s, lint=lint)
    fixes = fx.get("fixes") or []

    want_fix_ids = {str(x).strip() for x in (req.get("fix_ids") or []) if str(x).strip()}
    want_issue_codes = {str(x).strip() for x in (req.get("issue_codes") or []) if str(x).strip()}
    if not want_fix_ids and not want_issue_codes:
        selected = [f for f in fixes if bool(f.get("auto_applicable"))]
    else:
        selected = []
        for f in fixes:
            if want_fix_ids and str(f.get("fix_id") or "") in want_fix_ids:
                selected.append(f)
                continue
            if want_issue_codes and str(f.get("issue_code") or "") in want_issue_codes:
                selected.append(f)
                continue

    allowed_out_keys = {"markdown", "change_plan", "changed_files", "unrelated_changes", "acceptance_criteria", "rollback_plan"}
    ops = []
    meta_ops = []
    for f in selected:
        patch = f.get("patch") if isinstance(f.get("patch"), dict) else {}
        if str(patch.get("format") or "") != "frontmatter_merge":
            continue
        for op in patch.get("ops") if isinstance(patch.get("ops"), list) else []:
            if not isinstance(op, dict):
                continue
            if op.get("op") != "upsert":
                continue
            path = op.get("path")
            if isinstance(path, list) and len(path) == 2 and str(path[0]) == "output_schema" and str(path[1]) in allowed_out_keys:
                ops.append(op)
                continue
            if path in (["negative_triggers"], ["trigger_conditions"], ["required_questions"], ["keywords"], ["description"], ["name"]):
                meta_ops.append(op)
                continue

    if dry_run:
        return {"status": "dry_run", "skill_id": str(skill_id), "change_id": change_id, "selected": selected, "ops": ops + meta_ops}

    if not ops and not meta_ops:
        return {"status": "noop", "skill_id": str(skill_id), "change_id": change_id, "selected": selected, "ops": []}

    out_patch: Dict[str, Any] = {}
    name_patch: Optional[str] = None
    desc_patch: Optional[str] = None
    trig_patch: Optional[Any] = None
    neg_patch: Optional[Any] = None
    reqq_patch: Optional[Any] = None
    kw_patch: Optional[Any] = None
    for op in ops:
        v = op.get("value")
        path = op.get("path") if isinstance(op.get("path"), list) else []
        if len(path) == 2 and path[0] == "output_schema" and isinstance(path[1], str) and isinstance(v, dict):
            out_patch[str(path[1])] = v
    for op in meta_ops:
        v = op.get("value")
        path = op.get("path") if isinstance(op.get("path"), list) else []
        if path == ["name"] and isinstance(v, str):
            name_patch = v
        elif path == ["description"] and isinstance(v, str):
            desc_patch = v
        elif path == ["trigger_conditions"]:
            trig_patch = v
        elif path == ["negative_triggers"]:
            neg_patch = v
        elif path == ["required_questions"]:
            reqq_patch = v
        elif path == ["keywords"] and isinstance(v, dict):
            kw_patch = v

    skill2 = await mgr.update_skill(
        skill_id,
        output_schema=out_patch if out_patch else None,
        name=name_patch,
        description=desc_patch,
        trigger_conditions=trig_patch,
        negative_triggers=neg_patch,
        required_questions=reqq_patch,
        keywords=kw_patch,
    )
    if not skill2:
        raise HTTPException(status_code=500, detail="Failed to update skill")

    try:
        await _record_changeset(
            rt,
            name="skill.apply_lint_fix",
            target_type="change",
            target_id=change_id,
            status="success",
            args={"targets": [{"type": "skill", "id": str(skill_id)}], "ops": ops + meta_ops},
            result={"status": "applied", "selected_fix_ids": [str(f.get("fix_id") or "") for f in selected]},
            user_id="admin",
        )
    except Exception:
        pass

    lint2 = lint_skill(skill2)
    fx2 = propose_skill_fixes(skill=skill2, lint=lint2)
    return {
        "status": "applied",
        "skill_id": str(skill_id),
        "change_id": change_id,
        "selected_fix_ids": [str(f.get("fix_id") or "") for f in selected],
        "lint": lint2,
        "fixes": fx2.get("fixes") or [],
        "fix_summary": fx2.get("summary") or {},
    }


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: str, request: dict, rt: RuntimeDep = None):
    """Update skill (engine scope)."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    try:
        skill = await mgr.update_skill(skill_id, name=request.get("name"), description=request.get("description"), config=request.get("config"), metadata=request.get("metadata"))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    try:
        await _record_changeset(
            rt,
            name="skill_upsert",
            target_type="skill",
            target_id=str(skill_id),
            args={"scope": "engine", "fields": list((request or {}).keys())[:50]},
            result={
                "status": "updated",
                "integrity": (getattr(skill, "metadata", None) or {}).get("integrity") if isinstance(getattr(skill, "metadata", None), dict) else None,
                "provenance": (getattr(skill, "metadata", None) or {}).get("provenance") if isinstance(getattr(skill, "metadata", None), dict) else None,
            },
        )
    except Exception:
        pass
    try:
        await _maybe_verify_and_audit_skill_signature(rt, skill=skill, scope="engine")
    except Exception:
        pass
    return {"status": "updated"}


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str, delete_files: bool = False, rt: RuntimeDep = None):
    """Delete skill (default: soft delete; delete_files=true for hard delete)."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    try:
        success = await mgr.delete_skill(skill_id, delete_files=delete_files)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not success:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {"status": "deleted" if delete_files else "deprecated"}


@router.post("/skills/{skill_id}/enable")
async def enable_skill(skill_id: str, rt: RuntimeDep = None):
    """Enable skill (engine scope)."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    change_id = _new_change_id()
    try:
        from core.governance.gating import autosmoke_enforce, gate_with_change_control

        if autosmoke_enforce(store=_store(rt)):
            change_id = await gate_with_change_control(
                store=_store(rt),
                operation="skill.enable",
                targets=[("skill", str(skill_id))],
                actor={"actor_id": "admin"},
                workspace_agent_manager=_ws_agent_mgr(rt),
                workspace_skill_manager=_ws_skill_mgr(rt),
                skill_manager=mgr,
                workspace_mcp_manager=_ws_mcp_mgr(rt),
                mcp_manager=_mcp_mgr(rt),
            )
    except HTTPException:
        raise
    except Exception:
        pass
    success = await mgr.enable_skill(skill_id)
    if not success:
        raise HTTPException(status_code=400, detail=f"Skill {skill_id} cannot be enabled (maybe deprecated; use restore)")
    await _record_changeset(rt, name="skill.enable", target_type="change", target_id=change_id, status="success", args={"targets": [{"type": "skill", "id": str(skill_id)}]}, user_id="admin")
    return {"status": "enabled", "change_id": change_id, "links": _gov_links(change_id=change_id)}


@router.post("/skills/{skill_id}/disable")
async def disable_skill(skill_id: str, rt: RuntimeDep = None):
    """Disable skill (engine scope)."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    success = await mgr.disable_skill(skill_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {"status": "disabled"}


@router.post("/skills/{skill_id}/restore")
async def restore_skill(skill_id: str, rt: RuntimeDep = None):
    """Restore a deprecated skill (status -> enabled)."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    success = await mgr.restore_skill(skill_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {"status": "enabled"}


@router.post("/skills/governance-preview")
async def preview_engine_skill_governance(request: Dict[str, Any], rt: RuntimeDep = None):
    """Preview governance/risk/approval hints for wizard UX (engine scope)."""
    req = dict(request or {})
    req.setdefault("actor_id", "admin")
    req.setdefault("tenant_id", "ops")
    return skill_governance_preview(scope="engine", payload=req, approval_manager=_approval_mgr(rt))


@router.get("/skills/meta/permissions-catalog")
async def engine_permissions_catalog(http_request: Request, tenant_id: Optional[str] = None, channel: Optional[str] = None):
    """Permissions catalog for UI (engine scope)."""
    from core.services.config_registry_store import ConfigRegistryKey, get_config_registry_store

    ctx = req_tenant_channel(http_request, tenant_id=tenant_id, channel=channel)
    store = get_config_registry_store()
    key = ConfigRegistryKey(asset_type="permissions_catalog", scope="engine", tenant_id=ctx["tenant_id"], channel=ctx["channel"])
    published = await store.get_published(key=key)
    if published:
        ver, payload = published
        if isinstance(payload, dict) and "items" in payload:
            out = dict(payload)
            out["source"] = "published"
            out["version"] = ver
            out["tenant_id"] = ctx["tenant_id"]
            out["channel"] = ctx["channel"]
            return out
    out = permission_catalog(scope="engine")
    out.update({"source": "default", "tenant_id": ctx["tenant_id"], "channel": ctx["channel"], "version": "default"})
    return out


@router.get("/skills/meta/skill-spec-v2-schema")
async def engine_skill_spec_v2_schema(http_request: Request, tenant_id: Optional[str] = None, channel: Optional[str] = None):
    """SkillSpec v2 schema registry endpoint (engine scope)."""
    from core.services.config_registry_store import ConfigRegistryKey, get_config_registry_store

    ctx = req_tenant_channel(http_request, tenant_id=tenant_id, channel=channel)
    store = get_config_registry_store()
    key = ConfigRegistryKey(asset_type="skill_spec_v2_schema", scope="engine", tenant_id=ctx["tenant_id"], channel=ctx["channel"])
    published = await store.get_published(key=key)
    if published:
        ver, payload = published
        if isinstance(payload, dict) and "properties" in payload:
            return {"schema": payload, "version": ver, "source": "published", **ctx}
    s = load_skill_spec_v2_schema()
    return {"schema": s, "version": schema_version(s), "source": "default", **ctx}


@router.get("/skills/{skill_id}/agents")
async def get_skill_agents(skill_id: str, rt: RuntimeDep = None):
    """Get agents bound to skill (engine scope)."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    agent_ids = await mgr.get_bound_agents(skill_id)
    return {"agents": [{"id": a} for a in agent_ids], "total": len(agent_ids)}


@router.get("/skills/{skill_id}/binding-stats")
async def get_skill_binding_stats(skill_id: str):
    """Get skill binding statistics."""
    registry = get_skill_registry()
    stats = registry.get_binding_stats(skill_id)
    if not stats:
        return {"total_agents": 0, "total_calls": 0}
    return {"total_agents": len(stats.bound_agents), "total_calls": stats.total_executions, "avg_success_rate": stats.success_count / stats.total_executions if stats.total_executions > 0 else 0}


@router.get("/skills/{skill_id}/versions")
async def get_skill_versions(skill_id: str):
    """Get skill versions."""
    registry = get_skill_registry()
    versions = registry.get_versions(skill_id)
    return {"versions": [{"version": v.version, "is_active": v.is_active} for v in versions]}


@router.get("/skills/{skill_id}/versions/{version}")
async def get_skill_version(skill_id: str, version: str):
    """Get specific skill version."""
    registry = get_skill_registry()
    config = registry.get_version(skill_id, version)
    if not config:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    try:
        from dataclasses import asdict, is_dataclass

        cfg_dict = asdict(config) if is_dataclass(config) else dict(config)  # type: ignore[arg-type]
    except Exception:
        cfg_dict = {
            "name": getattr(config, "name", ""),
            "description": getattr(config, "description", ""),
            "input_schema": getattr(config, "input_schema", {}) or {},
            "output_schema": getattr(config, "output_schema", {}) or {},
            "timeout": getattr(config, "timeout", None),
            "metadata": getattr(config, "metadata", {}) or {},
        }
    return {"version": version, "config": cfg_dict}


@router.post("/skills/{skill_id}/versions/{version}/rollback")
async def rollback_skill_version(skill_id: str, version: str):
    """Rollback skill version."""
    registry = get_skill_registry()
    ok = registry.rollback_version(skill_id, version)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    active_version = registry.get_active_version(skill_id) if hasattr(registry, "get_active_version") else version
    active_config = registry.get_version(skill_id, active_version) if active_version else None
    cfg = None
    if active_config is not None:
        try:
            from dataclasses import asdict, is_dataclass

            cfg = asdict(active_config) if is_dataclass(active_config) else dict(active_config)  # type: ignore[arg-type]
        except Exception:
            cfg = {"name": getattr(active_config, "name", ""), "metadata": getattr(active_config, "metadata", {}) or {}}
    return {"status": "rolled_back", "active_version": active_version, "active_config": cfg}


@router.get("/skills/{skill_id}/active-version")
async def get_skill_active_version(skill_id: str):
    """Get currently active version for a skill."""
    registry = get_skill_registry()
    if not registry.get(skill_id):
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    active_version = registry.get_active_version(skill_id) if hasattr(registry, "get_active_version") else None
    return {"skill_id": skill_id, "active_version": active_version}


@router.post("/skills/{skill_id}/execute")
async def execute_skill(skill_id: str, request: SkillExecuteRequest, http_request: Request, rt: RuntimeDep = None):
    """Execute skill (engine scope)."""
    ctx_for_user: Dict[str, Any] = dict(request.context or {}) if isinstance(request.context, dict) else {}
    try:
        tmp = _inject_http_request_context({"context": dict(ctx_for_user)}, http_request, entrypoint="api")
        ctx_for_user = tmp.get("context") if isinstance(tmp, dict) and isinstance(tmp.get("context"), dict) else ctx_for_user
    except Exception:
        pass
    deny = await rbac_guard(http_request=http_request, payload={"context": ctx_for_user}, action="execute", resource_type="skill", resource_id=str(skill_id))
    if deny:
        return deny
    user_id = str(ctx_for_user.get("actor_id") or ctx_for_user.get("user_id") or "system")
    harness = get_harness()
    exec_req = ExecutionRequest(
        kind="skill",
        target_id=skill_id,
        payload={"input": request.input, "context": ctx_for_user, "mode": getattr(request, "mode", "inline"), "options": getattr(request, "options", None) or None},
        user_id=user_id,
        session_id=str(ctx_for_user.get("session_id") or "default"),
    )
    result = await harness.execute(exec_req)
    resp = wrap_execution_result_as_run_summary(result)
    try:
        await _audit_execute(rt, http_request=http_request, payload={"context": ctx_for_user}, resource_type="skill", resource_id=str(skill_id), resp=resp, action="execute_skill")
    except Exception:
        pass
    return JSONResponse(status_code=200 if resp.get("ok") else int(getattr(result, "http_status", 500) or 500), content=resp)


@router.get("/skills/executions/{execution_id}")
async def get_skill_execution(execution_id: str, rt: RuntimeDep = None):
    """Get skill execution."""
    store = _store(rt)
    mgr = _skill_mgr(rt)
    record = await store.get_skill_execution(execution_id) if store else None
    if not record and mgr:
        try:
            exec_ = await mgr.get_execution(execution_id)  # type: ignore[union-attr]
            if exec_:
                return {
                    "execution_id": exec_.id,
                    "skill_id": exec_.skill_id,
                    "status": exec_.status,
                    "input": exec_.input_data,
                    "output": exec_.output_data,
                    "error": exec_.error,
                    "start_time": exec_.start_time.isoformat() if exec_.start_time else None,
                    "end_time": exec_.end_time.isoformat() if exec_.end_time else None,
                    "duration_ms": exec_.duration_ms,
                }
        except Exception:
            pass
    if not record:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    return {
        "execution_id": record["id"],
        "skill_id": record["skill_id"],
        "status": record["status"],
        "input": record.get("input"),
        "output": record.get("output"),
        "error": record.get("error"),
        "trace_id": record.get("trace_id"),
        "start_time": datetime.utcfromtimestamp(record["start_time"]).isoformat() if record.get("start_time") else None,
        "end_time": datetime.utcfromtimestamp(record["end_time"]).isoformat() if record.get("end_time") else None,
        "duration_ms": record.get("duration_ms"),
    }


@router.get("/skills/{skill_id}/executions")
async def list_skill_executions(skill_id: str, limit: int = 100, offset: int = 0, rt: RuntimeDep = None):
    """List skill executions."""
    store = _store(rt)
    if store:
        items, total = await store.list_skill_executions(skill_id, limit=limit, offset=offset)
        executions = [
            {
                "execution_id": r["id"],
                "skill_id": r["skill_id"],
                "status": r["status"],
                "input": r.get("input"),
                "output": r.get("output"),
                "error": r.get("error"),
                "trace_id": r.get("trace_id"),
                "start_time": datetime.utcfromtimestamp(r["start_time"]).isoformat() if r.get("start_time") else None,
                "end_time": datetime.utcfromtimestamp(r["end_time"]).isoformat() if r.get("end_time") else None,
                "duration_ms": r.get("duration_ms"),
            }
            for r in items
        ]
        return {"executions": executions, "total": total}
    return {"executions": [], "total": 0}


@router.get("/skills/{skill_id}/trigger-conditions")
async def get_skill_trigger_conditions(skill_id: str, rt: RuntimeDep = None):
    """Get skill trigger conditions (routing rules)."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {"skill_id": skill_id, "trigger_conditions": skill.metadata.get("trigger_conditions", []) if skill.metadata else []}


@router.put("/skills/{skill_id}/trigger-conditions")
async def update_skill_trigger_conditions(skill_id: str, request: dict, rt: RuntimeDep = None):
    """Update skill trigger conditions."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    trigger_conditions = request.get("trigger_conditions", [])
    await mgr.update_skill(skill_id, metadata={"trigger_conditions": trigger_conditions})
    return {"status": "updated", "trigger_conditions": trigger_conditions}


@router.post("/skills/{skill_id}/test-trigger")
async def test_skill_trigger(skill_id: str, request: dict, rt: RuntimeDep = None):
    """Test if skill would be triggered by given input."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    test_input = request.get("input", "")
    conditions = skill.metadata.get("trigger_conditions", []) if skill.metadata else []
    matched = False
    for condition in conditions:
        if condition.get("keyword") in str(test_input).lower():
            matched = True
            break
    return {"skill_id": skill_id, "would_trigger": matched, "matched_condition": condition if matched else None}


@router.get("/skills/{skill_id}/evolution")
async def get_skill_evolution_status(skill_id: str, rt: RuntimeDep = None):
    """Get skill evolution status (CAPTURED/FIX/DERIVED)."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    evolution = skill.metadata.get("evolution", {}) if skill.metadata else {}
    return {
        "skill_id": skill_id,
        "status": evolution.get("status", "stable"),
        "last_evolution": evolution.get("last_evolution", None),
        "evolution_count": evolution.get("evolution_count", 0),
        "parent_skill_id": evolution.get("parent_skill_id", None),
        "child_skill_ids": evolution.get("child_skill_ids", []),
    }


@router.post("/skills/{skill_id}/evolution")
async def trigger_skill_evolution(skill_id: str, request: dict, rt: RuntimeDep = None):
    """Manually trigger skill evolution."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    trigger_type = request.get("trigger_type", "manual")
    evolution = skill.metadata.get("evolution", {}) if skill.metadata else {}
    evolution["status"] = "capturing" if trigger_type == "capture" else "fixing"
    evolution["last_evolution"] = datetime.utcnow().isoformat()
    evolution["evolution_count"] = evolution.get("evolution_count", 0) + 1
    await mgr.update_skill(skill_id, metadata={"evolution": evolution})
    return {"status": "triggered", "evolution_type": trigger_type, "evolution_count": evolution["evolution_count"]}


@router.get("/skills/{skill_id}/lineage")
async def get_skill_lineage(skill_id: str, rt: RuntimeDep = None):
    """Get skill lineage (evolution history)."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    lineage = skill.metadata.get("lineage", []) if skill.metadata else []
    return {"skill_id": skill_id, "lineage": lineage, "total": len(lineage)}


@router.get("/skills/{skill_id}/captures")
async def get_skill_captures(skill_id: str, limit: int = 100, offset: int = 0):
    """Get captured interactions for skill (placeholder)."""
    return {"captures": [], "total": 0, "note": "Captures are stored in skill evolution module"}


@router.get("/skills/{skill_id}/fixes")
async def get_skill_fixes(skill_id: str, limit: int = 100, offset: int = 0, rt: RuntimeDep = None):
    """Get applied fixes for skill."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    evolution = skill.metadata.get("evolution", {}) if skill.metadata else {}
    fixes = evolution.get("fixes", [])
    return {"fixes": fixes[offset : offset + limit], "total": len(fixes)}


@router.get("/skills/{skill_id}/derived")
async def get_skill_derived(skill_id: str, rt: RuntimeDep = None):
    """Get derived skills (children) from this skill."""
    mgr = _skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    evolution = skill.metadata.get("evolution", {}) if skill.metadata else {}
    child_ids = evolution.get("child_skill_ids", [])
    return {"derived_skills": [{"id": c} for c in child_ids], "total": len(child_ids)}

