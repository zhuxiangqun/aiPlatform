from __future__ import annotations

import os
import re
import time
import difflib
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from core.api.deps.rbac import actor_from_http, rbac_guard
from core.api.utils.governance import ui_url
from core.governance.changeset import record_changeset
from core.harness.kernel.runtime import get_kernel_runtime
from core.utils.ids import new_prefixed_id

router = APIRouter()


def _rt():
    return get_kernel_runtime()


def _store():
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None


def _norm(s: str) -> str:
    s0 = str(s or "").lower().strip()
    s0 = re.sub(r"[\s\-\._/]+", " ", s0)
    s0 = re.sub(r"[^\w\u4e00-\u9fff ]+", "", s0)
    return s0.strip()


def _tokenize(s: str) -> list[str]:
    s0 = _norm(s)
    if not s0:
        return []
    toks: list[str] = []
    for w in s0.split():
        if len(w) >= 2:
            toks.append(w)
    for seg in re.findall(r"[\u4e00-\u9fff]{2,}", s0):
        for i in range(0, max(0, len(seg) - 1)):
            toks.append(seg[i : i + 2])
    return toks


_STOP = {
    "一下",
    "帮我",
    "请",
    "如何",
    "怎么",
    "可以",
    "这个",
    "那个",
    "这些",
    "那些",
    "生成",
    "输出",
    "内容",
    "文章",
    "总结",
    "概括",
    "翻译",
    "帮",
    "我",
}

def _split_front_matter(raw: str) -> tuple[dict, str, str]:
    """
    Return (front_matter_map, front_matter_text, body_text).
    Minimal YAML-ish parsing for keys we touch (description/trigger_conditions/avoid_trigger_conditions).
    """
    txt = raw or ""
    if not txt.lstrip().startswith("---"):
        return ({}, "", txt)
    lines = txt.splitlines(True)
    if not lines or not lines[0].strip().startswith("---"):
        return ({}, "", txt)
    # find second '---'
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return ({}, "", txt)
    fm_lines = lines[1:end_idx]
    body = "".join(lines[end_idx + 1 :])
    fm_text = "".join(fm_lines)

    # Parse only top-level scalar + list fields.
    fm: dict = {}
    cur_list_key = None
    for ln in fm_lines:
        s = ln.rstrip("\n")
        if not s.strip() or s.strip().startswith("#"):
            continue
        if s.startswith(" ") or s.startswith("\t"):
            # list item
            if cur_list_key and s.strip().startswith("- "):
                fm.setdefault(cur_list_key, [])
                if isinstance(fm[cur_list_key], list):
                    fm[cur_list_key].append(s.strip()[2:].strip().strip("'").strip('"'))
            continue
        cur_list_key = None
        if ":" in s:
            k, v = s.split(":", 1)
            key = k.strip()
            val = v.strip()
            if val == "" or val == "[]":
                # list begin
                fm.setdefault(key, [])
                cur_list_key = key
            else:
                fm[key] = val.strip().strip("'").strip('"')
    return (fm, fm_text, body)


def _update_front_matter(
    raw: str,
    *,
    description: Optional[str],
    add_trigger: list[str],
    avoid_trigger: list[str],
) -> tuple[str, dict]:
    fm, _fm_text, body = _split_front_matter(raw)
    # normalize lists
    trig = fm.get("trigger_conditions")
    trig = trig if isinstance(trig, list) else []
    avoid = fm.get("avoid_trigger_conditions")
    avoid = avoid if isinstance(avoid, list) else []

    def _uniq(xs: list[str]) -> list[str]:
        out = []
        seen = set()
        for x in xs:
            s = str(x or "").strip()
            if not s:
                continue
            if s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    trig2 = _uniq(trig + (add_trigger or []))
    avoid2 = _uniq(avoid + (avoid_trigger or []))
    if description and str(description).strip():
        fm["description"] = str(description).strip()
    fm["trigger_conditions"] = trig2
    if avoid2:
        fm["avoid_trigger_conditions"] = avoid2

    # Re-render minimal front matter preserving key ordering roughly (stable for our keys).
    lines = ["---\n"]
    for key in ["name", "display_name", "displayName", "category", "version", "status"]:
        if key in fm and isinstance(fm[key], str) and fm[key].strip():
            lines.append(f"{key}: {fm[key]}\n")
    if "description" in fm and isinstance(fm["description"], str):
        # single-line scalar
        desc = fm["description"].replace("\n", " ").strip()
        lines.append(f"description: {desc}\n")
    for key in ["permissions", "tools", "capabilities", "trigger_conditions", "avoid_trigger_conditions"]:
        if key in fm and isinstance(fm[key], list):
            lines.append(f"{key}:\n")
            for it in fm[key][:80]:
                s = str(it).replace("\n", " ").strip()
                if s:
                    lines.append(f"  - {s}\n")
    # emit any other scalar keys (best-effort)
    for k, v in fm.items():
        if k in {"name", "display_name", "displayName", "category", "version", "status", "description", "permissions", "tools", "capabilities", "trigger_conditions", "avoid_trigger_conditions"}:
            continue
        if isinstance(v, str) and v.strip():
            lines.append(f"{k}: {v}\n")
    lines.append("---\n")
    new_raw = "".join(lines) + (body or "")
    return new_raw, fm


def _resolve_skill_md_path(*, skill_id: str, scope: str) -> Optional[Path]:
    sid = str(skill_id or "").strip()
    if not sid:
        return None
    repo_root = Path(__file__).resolve().parents[3]  # aiPlat-core/
    if scope == "engine":
        base = repo_root / "core" / "engine" / "skills"
        paths_env = os.environ.get("AIPLAT_ENGINE_SKILLS_PATHS")
        if paths_env:
            parts = [p.strip() for p in paths_env.split(os.pathsep) if p.strip()]
            if parts:
                base = Path(parts[-1]).expanduser().resolve()
        single = os.environ.get("AIPLAT_ENGINE_SKILLS_PATH")
        if single:
            base = Path(single).expanduser().resolve()
    else:
        # workspace default mirrors SkillManager
        base = Path.home() / ".aiplat" / "skills"
        paths_env = os.environ.get("AIPLAT_WORKSPACE_SKILLS_PATHS")
        if paths_env:
            parts = [p.strip() for p in paths_env.split(os.pathsep) if p.strip()]
            if parts:
                base = Path(parts[-1]).expanduser().resolve()
        single = os.environ.get("AIPLAT_WORKSPACE_SKILLS_PATH")
        if single:
            base = Path(single).expanduser().resolve()
    p = (base / sid / "SKILL.md").resolve()
    return p



@router.post("/skill-evals/suites")
async def upsert_skill_eval_suite(request: dict, http_request: Request):
    """
    创建/更新评测套件（Trigger Eval MVP）。

    Body:
      {
        "suite_id": "optional",
        "name": "...",
        "description": "...",
        "scope": "engine|workspace|all",
        "target_skill_id": "skill_id",
        "positive_queries": ["..."],
        "negative_queries": ["..."],
        "score_threshold": 0.12,
        "quality_cases": [{"name":"...","input":{...},"expected":{...}}]
      }
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    body = dict(request or {}) if isinstance(request, dict) else {}
    actor = actor_from_http(http_request, body)
    deny = await rbac_guard(
        http_request=http_request,
        payload=body,
        action="update",
        resource_type="skill_eval",
        resource_id=str(body.get("suite_id") or "suite"),
        run_id=None,
    )
    if deny:
        return deny

    suite_id = str(body.get("suite_id") or new_prefixed_id("evalsuite"))
    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="missing_name")
    target_skill_id = str(body.get("target_skill_id") or "").strip()
    if not target_skill_id:
        raise HTTPException(status_code=400, detail="missing_target_skill_id")
    scope = str(body.get("scope") or "all").strip().lower()
    if scope not in {"engine", "workspace", "all"}:
        scope = "all"

    pos = body.get("positive_queries") if isinstance(body.get("positive_queries"), list) else []
    neg = body.get("negative_queries") if isinstance(body.get("negative_queries"), list) else []
    pos = [str(x).strip() for x in pos if isinstance(x, str) and x.strip()]
    neg = [str(x).strip() for x in neg if isinstance(x, str) and x.strip()]
    score_threshold = body.get("score_threshold")
    try:
        score_threshold = float(score_threshold) if score_threshold is not None else None
    except Exception:
        score_threshold = None

    cfg = {
        "positive_queries": pos,
        "negative_queries": neg,
        "target_skill_id": target_skill_id,
        "tenant_id": actor.get("tenant_id"),
    }
    if score_threshold is not None:
        cfg["score_threshold"] = float(score_threshold)

    quality_cases = body.get("quality_cases") if isinstance(body.get("quality_cases"), list) else None
    if isinstance(quality_cases, list):
        # keep it small and json-safe
        out = []
        for c in quality_cases[:200]:
            if not isinstance(c, dict):
                continue
            out.append(
                {
                    "name": str(c.get("name") or "")[:120],
                    "input": c.get("input") if isinstance(c.get("input"), dict) else {},
                    "expected": c.get("expected") if isinstance(c.get("expected"), dict) else {},
                }
            )
        cfg["quality_cases"] = out
    row = await store.upsert_skill_eval_suite(
        suite_id=suite_id,
        tenant_id=actor.get("tenant_id"),
        scope=scope,
        target_skill_id=target_skill_id,
        name=name,
        description=str(body.get("description") or ""),
        config=cfg,
    )
    return {"status": "ok", "suite": row}


@router.get("/skill-evals/suites")
async def list_skill_eval_suites(limit: int = 50, offset: int = 0, tenant_id: Optional[str] = None):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    res = await store.list_skill_eval_suites(tenant_id=tenant_id, limit=int(limit), offset=int(offset))
    return res


@router.get("/skill-evals/suites/{suite_id}")
async def get_skill_eval_suite(suite_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    row = await store.get_skill_eval_suite(suite_id=str(suite_id))
    if not row:
        raise HTTPException(status_code=404, detail="not_found")
    return row


@router.delete("/skill-evals/suites/{suite_id}")
async def delete_skill_eval_suite(suite_id: str, http_request: Request):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(
        http_request=http_request,
        payload={},
        action="delete",
        resource_type="skill_eval",
        resource_id=str(suite_id),
        run_id=None,
    )
    if deny:
        return deny
    ok = await store.delete_skill_eval_suite(suite_id=str(suite_id))
    return {"status": "ok", "deleted": bool(ok)}


@router.post("/skill-evals/suites/{suite_id}/run")
async def run_skill_eval_suite(suite_id: str, request: dict, http_request: Request):
    """
    运行 Trigger Eval（同步）。

    Body:
      {
        "eval_kind": "trigger|quality",
        "mode": "heuristic|live",
        "max_cases": 200,
        "skills_override": [...]   // 可选：测试/离线覆盖技能目录
      }
    """
    store = _store()
    rt = _rt()
    if not store or not rt:
        raise HTTPException(status_code=503, detail="Runtime not initialized")

    body = dict(request or {}) if isinstance(request, dict) else {}
    actor = actor_from_http(http_request, body)
    deny = await rbac_guard(
        http_request=http_request,
        payload=body,
        action="execute",
        resource_type="skill_eval",
        resource_id=str(suite_id),
        run_id=None,
    )
    if deny:
        return deny

    # ensure suite exists
    suite = await store.get_skill_eval_suite(suite_id=str(suite_id))
    if not suite:
        raise HTTPException(status_code=404, detail="suite_not_found")

    eval_run_id = new_prefixed_id("evalrun")
    eval_kind = str(body.get("eval_kind") or "trigger").strip().lower()
    mode = str(body.get("mode") or "heuristic").strip().lower()
    max_cases = int(body.get("max_cases") or 200)
    skills_override = body.get("skills_override") if isinstance(body.get("skills_override"), list) else None

    # Execute internal eval skill under current permission model.
    if eval_kind == "quality":
        res = await rt.skill_manager.execute_skill(
            skill_id="skill_eval_quality",
            input_data={"suite_id": str(suite_id), "max_cases": max_cases},
            context={"user_id": actor.get("actor_id") or "system", "tenant_id": actor.get("tenant_id"), "timeout": 1800},
            execution_id=str(eval_run_id),
        )
    else:
        res = await rt.skill_manager.execute_skill(
            skill_id="skill_eval_trigger",
            input_data={"suite_id": str(suite_id), "mode": mode, "max_cases": max_cases, "skills_override": skills_override} if skills_override is not None else {"suite_id": str(suite_id), "mode": mode, "max_cases": max_cases},
            context={
                "user_id": actor.get("actor_id") or "system",
                "tenant_id": actor.get("tenant_id"),
                "timeout": 1200,
            },
            execution_id=str(eval_run_id),
        )
    run_row = await store.get_skill_eval_run(run_id=str(eval_run_id))
    return {"status": "ok", "run_id": str(eval_run_id), "result": res, "run": run_row}


@router.get("/skill-evals/runs/{run_id}")
async def get_skill_eval_run(run_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    row = await store.get_skill_eval_run(run_id=str(run_id))
    if not row:
        raise HTTPException(status_code=404, detail="not_found")
    return row


@router.get("/skill-evals/runs/{run_id}/results")
async def list_skill_eval_results(run_id: str, limit: int = 200, offset: int = 0):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_skill_eval_results(run_id=str(run_id), limit=int(limit), offset=int(offset))


@router.post("/skill-evals/runs/{run_id}/suggest")
async def suggest_trigger_improvements(run_id: str, request: dict, http_request: Request):
    """
    Analyzer-lite: generate heuristic suggestions from a completed Trigger Eval run:
    - add_keywords: tokens from false negatives to improve recall
    - avoid_keywords: tokens from false positives to reduce misfires
    - suggested_description: a tighter intent-focused description draft
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    body = dict(request or {}) if isinstance(request, dict) else {}
    deny = await rbac_guard(
        http_request=http_request,
        payload=body,
        action="read",
        resource_type="skill_eval",
        resource_id=str(run_id),
        run_id=None,
    )
    if deny:
        return deny

    rr = await store.get_skill_eval_run(run_id=str(run_id))
    if not rr:
        raise HTTPException(status_code=404, detail="not_found")
    metrics = rr.get("metrics") if isinstance(rr.get("metrics"), dict) else {}
    target_skill_id = str(metrics.get("target_skill_id") or "")
    if not target_skill_id:
        raise HTTPException(status_code=400, detail="missing_target_skill_id")

    max_tokens = int(body.get("max_tokens") or 12)
    max_tokens = max(3, min(max_tokens, 30))

    fn = metrics.get("false_negatives") if isinstance(metrics.get("false_negatives"), list) else []
    fp = metrics.get("false_positives") if isinstance(metrics.get("false_positives"), list) else []

    def _top_tokens(rows: list, *, limit: int) -> list[str]:
        freq: Dict[str, int] = {}
        for r in rows:
            q = r.get("query") if isinstance(r, dict) else ""
            for t in _tokenize(str(q)):
                if t in _STOP:
                    continue
                if len(t) < 2:
                    continue
                freq[t] = int(freq.get(t, 0)) + 1
        out = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
        return [k for k, _ in out[:limit]]

    add_keywords = _top_tokens(fn, limit=max_tokens)
    avoid_keywords = _top_tokens(fp, limit=max_tokens)

    # Simple description draft focusing on intent; this is a template for humans/LLM to refine.
    kw_hint = "、".join(add_keywords[:8]) if add_keywords else ""
    avoid_hint = "、".join(avoid_keywords[:6]) if avoid_keywords else ""
    suggested_description = (
        f"当用户明确想要使用“{target_skill_id}”完成特定任务时使用此技能。"
        f"优先匹配用户意图中的关键词/实体（例如：{kw_hint}）。"
        f"{'避免在仅包含以下泛化意图时触发：' + avoid_hint + '。' if avoid_hint else ''}"
        "如果用户目标不清晰或更像是泛化问答/总结/翻译，请不要触发。"
    )

    # Patch is a machine-applicable suggestion for suite (and later skill metadata).
    patch = {
        "suite": {
            "description": suggested_description,
            "config_merge": {
                # Keep raw suggestions for later analysis/iteration; do not overwrite eval queries.
                "suggested_add_keywords": add_keywords,
                "suggested_avoid_keywords": avoid_keywords,
            },
        }
    }

    return {
        "status": "ok",
        "run_id": str(run_id),
        "target_skill_id": target_skill_id,
        "add_keywords": add_keywords,
        "avoid_keywords": avoid_keywords,
        "suggested_description": suggested_description,
        "patch": patch,
    }


@router.post("/skill-evals/suites/{suite_id}/apply-suggestion")
async def apply_skill_eval_suggestion(suite_id: str, request: dict, http_request: Request):
    """
    Apply a suggestion patch to a suite (MVP).

    Body:
      {
        "patch": { ... }    // from /runs/{run_id}/suggest
      }
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    body = dict(request or {}) if isinstance(request, dict) else {}
    deny = await rbac_guard(
        http_request=http_request,
        payload=body,
        action="update",
        resource_type="skill_eval",
        resource_id=str(suite_id),
        run_id=None,
    )
    if deny:
        return deny

    suite = await store.get_skill_eval_suite(suite_id=str(suite_id))
    if not suite:
        raise HTTPException(status_code=404, detail="suite_not_found")
    cfg = suite.get("config") if isinstance(suite.get("config"), dict) else {}

    patch = body.get("patch") if isinstance(body.get("patch"), dict) else {}
    sp = patch.get("suite") if isinstance(patch.get("suite"), dict) else {}
    new_desc = sp.get("description")
    cfg_merge = sp.get("config_merge") if isinstance(sp.get("config_merge"), dict) else {}

    # Merge into suite config (non-destructive, append-friendly)
    new_cfg = dict(cfg or {})
    for k, v in cfg_merge.items():
        if k in {"positive_queries", "negative_queries"}:
            continue
        new_cfg[k] = v
    new_cfg["applied_suggestion_at"] = time.time()

    # Update suite.description (optional)
    desc2 = str(new_desc) if isinstance(new_desc, str) and new_desc.strip() else str(suite.get("description") or "")

    updated = await store.upsert_skill_eval_suite(
        suite_id=str(suite_id),
        tenant_id=suite.get("tenant_id"),
        scope=str(suite.get("scope") or "all"),
        target_skill_id=str(suite.get("target_skill_id") or ""),
        name=str(suite.get("name") or ""),
        description=desc2,
        config=new_cfg,
    )
    return {"status": "ok", "suite": updated}


@router.post("/skill-evals/suites/{suite_id}/apply-skill-suggestion")
async def apply_skill_md_suggestion(suite_id: str, request: dict, http_request: Request):
    """
    Generate (and optionally apply) a SKILL.md front matter patch for the target skill in this suite.

    Body:
      {
        "patch": { ... },          // from /runs/{run_id}/suggest (optional)
        "apply": false,            // if true: only allowed for workspace scope
        "scope": "auto|engine|workspace",
        "create_change": true,     // when scope resolves to engine: create change-control/audit record
        "create_approval": true    // when scope resolves to engine: create an approval request and link it to change_id
      }
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    body = dict(request or {}) if isinstance(request, dict) else {}
    deny = await rbac_guard(
        http_request=http_request,
        payload=body,
        action="update",
        resource_type="skill_eval",
        resource_id=str(suite_id),
        run_id=None,
    )
    if deny:
        return deny

    suite = await store.get_skill_eval_suite(suite_id=str(suite_id))
    if not suite:
        raise HTTPException(status_code=404, detail="suite_not_found")
    cfg = suite.get("config") if isinstance(suite.get("config"), dict) else {}
    target_skill_id = str(suite.get("target_skill_id") or cfg.get("target_skill_id") or "").strip()
    if not target_skill_id:
        raise HTTPException(status_code=400, detail="missing_target_skill_id")

    # Extract suggestion content from patch (optional) or suite config suggested_*
    patch = body.get("patch") if isinstance(body.get("patch"), dict) else {}
    sp = patch.get("suite") if isinstance(patch.get("suite"), dict) else {}
    desc = sp.get("description") if isinstance(sp.get("description"), str) else None
    cfg_merge = sp.get("config_merge") if isinstance(sp.get("config_merge"), dict) else {}
    add_kw = cfg_merge.get("suggested_add_keywords")
    avoid_kw = cfg_merge.get("suggested_avoid_keywords")
    if not isinstance(add_kw, list):
        add_kw = cfg.get("suggested_add_keywords") if isinstance(cfg.get("suggested_add_keywords"), list) else []
    if not isinstance(avoid_kw, list):
        avoid_kw = cfg.get("suggested_avoid_keywords") if isinstance(cfg.get("suggested_avoid_keywords"), list) else []
    add_kw = [str(x) for x in add_kw if isinstance(x, str) and x.strip()][:30]
    avoid_kw = [str(x) for x in avoid_kw if isinstance(x, str) and x.strip()][:30]

    scope = str(body.get("scope") or "auto").strip().lower()
    if scope not in {"auto", "engine", "workspace"}:
        scope = "auto"
    apply = bool(body.get("apply", False))
    create_change = bool(body.get("create_change", True))
    create_approval = bool(body.get("create_approval", True))

    # Auto prefers workspace first, then engine.
    scopes = ["workspace", "engine"] if scope == "auto" else [scope]
    path = None
    chosen_scope = None
    for sc in scopes:
        p = _resolve_skill_md_path(skill_id=target_skill_id, scope=sc)
        if p and p.exists():
            path = p
            chosen_scope = sc
            break
    if not path or not chosen_scope:
        raise HTTPException(status_code=404, detail={"code": "skill_md_not_found", "skill_id": target_skill_id})

    raw = path.read_text(encoding="utf-8")
    updated_raw, fm = _update_front_matter(raw, description=desc, add_trigger=add_kw, avoid_trigger=avoid_kw)
    diff = "\n".join(
        difflib.unified_diff(
            raw.splitlines(),
            updated_raw.splitlines(),
            fromfile=str(path),
            tofile=str(path),
            lineterm="",
        )
    )

    if apply:
        if chosen_scope != "workspace":
            raise HTTPException(status_code=400, detail="apply_only_allowed_for_workspace_scope")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated_raw, encoding="utf-8")

    change_id = None
    approval_request_id = None
    links = {}
    # Engine scope: generate a change-control item so it flows into your existing evidence/audit pipeline.
    if chosen_scope == "engine" and create_change:
        try:
            actor0 = actor_from_http(http_request, body)
        except Exception:
            actor0 = {}
        tenant_id = actor0.get("tenant_id") or http_request.headers.get("X-AIPLAT-TENANT-ID")
        actor_id = actor0.get("actor_id") or http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")
        actor_role = actor0.get("actor_role") or http_request.headers.get("X-AIPLAT-ACTOR-ROLE")
        change_id = new_prefixed_id("change")
        diff_hash = hashlib.sha256((diff or "").encode("utf-8")).hexdigest()[:16]
        base_hash = hashlib.sha256((raw or "").encode("utf-8")).hexdigest()[:16]

        # Optional: request approval (creates approval_request_id and persists it).
        if create_approval:
            try:
                rt = get_kernel_runtime()
                mgr = getattr(rt, "approval_manager", None) if rt else None
                if mgr is not None:
                    from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RuleType

                    op = f"change:engine_skill_md_patch:{str(change_id)}"
                    rid = f"engine_skill_md_patch:{str(change_id)}"
                    mgr.register_rule(
                        ApprovalRule(
                            rule_id=rid,
                            rule_type=RuleType.SENSITIVE_OPERATION,
                            name="Engine Skill 补丁应用审批",
                            description="应用 engine skill 的 SKILL.md 变更补丁",
                            priority=1,
                            metadata={"sensitive_operations": [op]},
                        )
                    )
                    ctx = ApprovalContext(
                        session_id=str(actor0.get("session_id") or "ops"),
                        user_id=str(actor_id or "admin"),
                        operation=op,
                        operation_context={
                            "change_id": str(change_id),
                            "skill_id": str(target_skill_id),
                            "suite_id": str(suite_id),
                            "diff_hash": diff_hash,
                            "base_hash": base_hash,
                        },
                        metadata={
                            "tenant_id": str(tenant_id) if tenant_id else None,
                            "actor_id": str(actor_id) if actor_id else None,
                            "actor_role": str(actor_role) if actor_role else None,
                            "session_id": str(actor0.get("session_id") or "") or None,
                            "change_id": str(change_id),
                            "resource_type": "skill",
                            "resource_id": str(target_skill_id),
                        },
                    )
                    req = mgr.check_and_request(ctx)
                    approval_request_id = getattr(req, "request_id", None) or getattr(req, "request_id", None)  # compatibility
                    approval_request_id = approval_request_id or getattr(req, "request_id", None)
                    # Persist synchronously to avoid flakiness (manager persists async by default).
                    try:
                        if hasattr(store, "upsert_approval_request") and approval_request_id:
                            await store.upsert_approval_request(
                                {
                                    "request_id": str(req.request_id),
                                    "user_id": str(req.user_id),
                                    "operation": str(req.operation),
                                    "details": str(getattr(req, "details", "") or ""),
                                    "rule_id": getattr(req, "rule_id", None),
                                    "rule_type": (getattr(getattr(req, "rule_type", None), "value", None) or None),
                                    "status": str(getattr(getattr(req, "status", None), "value", None) or getattr(req, "status", None)),
                                    "amount": getattr(req, "amount", None),
                                    "batch_size": getattr(req, "batch_size", None),
                                    "is_first_time": bool(getattr(req, "is_first_time", False)),
                                    "created_at": float(getattr(req, "created_at").timestamp()) if getattr(req, "created_at", None) else time.time(),
                                    "updated_at": float(getattr(req, "updated_at").timestamp()) if getattr(req, "updated_at", None) else time.time(),
                                    "expires_at": float(getattr(req, "expires_at").timestamp()) if getattr(req, "expires_at", None) else None,
                                    "metadata": getattr(req, "metadata", None) or {},
                                    "result": (
                                        {
                                            "request_id": getattr(req.result, "request_id", None),
                                            "decision": getattr(getattr(req.result, "decision", None), "value", None),
                                            "comments": getattr(req.result, "comments", None),
                                            "approved_by": getattr(req.result, "approved_by", None),
                                            "timestamp": float(getattr(req.result, "timestamp").timestamp()) if getattr(req.result, "timestamp", None) else None,
                                            "metadata": getattr(req.result, "metadata", None) or {},
                                        }
                                        if getattr(req, "result", None) is not None
                                        else None
                                    ),
                                    "tenant_id": str(tenant_id) if tenant_id else None,
                                    "actor_id": str(actor_id) if actor_id else None,
                                    "actor_role": str(actor_role) if actor_role else None,
                                    "session_id": str(actor0.get("session_id") or "") or None,
                                    "run_id": None,
                                }
                            )
                    except Exception:
                        pass
                    try:
                        await store.add_audit_log(
                            action="engine_skill_md_patch_approval_requested",
                            status="ok",
                            tenant_id=str(tenant_id) if tenant_id else None,
                            actor_id=str(actor_id) if actor_id else None,
                            actor_role=str(actor_role) if actor_role else None,
                            resource_type="skill",
                            resource_id=str(target_skill_id),
                            request_id=str(req.request_id),
                            change_id=str(change_id),
                            detail={"suite_id": str(suite_id), "diff_hash": diff_hash},
                        )
                    except Exception:
                        pass
            except Exception:
                approval_request_id = None
        try:
            await record_changeset(
                store=store,
                name="skill_eval.engine_skill_md_patch_proposed",
                target_type="change",
                target_id=str(change_id),
                status="success",
                approval_request_id=str(approval_request_id) if approval_request_id else None,
                args={
                    "targets": [{"type": "skill", "id": target_skill_id}],
                    "suite_id": str(suite_id),
                    "skill_id": target_skill_id,
                    "scope": "engine",
                    "diff_hash": diff_hash,
                    "base_hash": base_hash,
                },
                result={"diff": diff, "path": str(path), "updated_raw": updated_raw, "base_hash": base_hash},
                user_id=str(actor_id or "admin"),
                tenant_id=str(tenant_id) if tenant_id else None,
                session_id=str(actor0.get("session_id") or "") or None,
            )
        except Exception:
            pass
        try:
            await store.add_audit_log(
                action="engine_skill_md_patch_proposed",
                status="success",
                tenant_id=str(tenant_id) if tenant_id else None,
                actor_id=str(actor_id) if actor_id else None,
                actor_role=str(actor_role) if actor_role else None,
                resource_type="skill",
                resource_id=str(target_skill_id),
                request_id=str(approval_request_id) if approval_request_id else None,
                change_id=str(change_id),
                detail={"suite_id": str(suite_id), "diff_hash": diff_hash, "base_hash": base_hash},
            )
        except Exception:
            pass
        try:
            links = {
                "change_control_ui": ui_url(f"/diagnostics/change-control/{str(change_id)}"),
                "audit_ui": ui_url(f"/diagnostics/audit?change_id={str(change_id)}"),
            }
        except Exception:
            links = {}

    return {
        "status": "ok",
        "skill_id": target_skill_id,
        "scope": chosen_scope,
        "path": str(path),
        "applied": bool(apply),
        "diff": diff,
        "front_matter": fm,
        "change_id": change_id,
        "approval_request_id": approval_request_id,
        "links": links,
    }


@router.post("/skill-evals/compare")
async def compare_skill_eval_runs(request: dict, http_request: Request):
    """
    A/B compare two eval runs (MVP).
    Body:
      {
        "run_id_a": "...",
        "run_id_b": "...",
        "limit": 500
      }
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    body = dict(request or {}) if isinstance(request, dict) else {}
    deny = await rbac_guard(
        http_request=http_request,
        payload=body,
        action="read",
        resource_type="skill_eval",
        resource_id="compare",
        run_id=None,
    )
    if deny:
        return deny

    run_a = str(body.get("run_id_a") or "").strip()
    run_b = str(body.get("run_id_b") or "").strip()
    if not run_a or not run_b:
        raise HTTPException(status_code=400, detail="missing_run_ids")
    limit = int(body.get("limit") or 500)

    ra = await store.get_skill_eval_run(run_id=run_a)
    rb = await store.get_skill_eval_run(run_id=run_b)
    if not ra or not rb:
        raise HTTPException(status_code=404, detail="run_not_found")

    resa = await store.list_skill_eval_results(run_id=run_a, limit=limit, offset=0)
    resb = await store.list_skill_eval_results(run_id=run_b, limit=limit, offset=0)
    ma = {int(it.get("query_index") or 0): it for it in (resa.get("items") or []) if isinstance(it, dict)}
    mb = {int(it.get("query_index") or 0): it for it in (resb.get("items") or []) if isinstance(it, dict)}
    idxs = sorted(set(list(ma.keys()) + list(mb.keys())))

    flips = []
    for i in idxs:
        a = ma.get(i) or {}
        b = mb.get(i) or {}
        oka = bool(int(a.get("ok") or 0)) if isinstance(a.get("ok"), (int, float, str)) else bool(a.get("ok"))
        okb = bool(int(b.get("ok") or 0)) if isinstance(b.get("ok"), (int, float, str)) else bool(b.get("ok"))
        if oka != okb:
            flips.append(
                {
                    "query_index": i,
                    "query_text": a.get("query_text") or b.get("query_text"),
                    "expected": a.get("expected") or b.get("expected"),
                    "a": {"ok": oka, "selected_skill_id": a.get("selected_skill_id"), "selected_score": a.get("selected_score")},
                    "b": {"ok": okb, "selected_skill_id": b.get("selected_skill_id"), "selected_score": b.get("selected_score")},
                }
            )
        if len(flips) >= 100:
            break

    return {
        "status": "ok",
        "run_a": {"run_id": run_a, "suite_id": ra.get("suite_id"), "mode": ra.get("mode"), "metrics": ra.get("metrics")},
        "run_b": {"run_id": run_b, "suite_id": rb.get("suite_id"), "mode": rb.get("mode"), "metrics": rb.get("metrics")},
        "diff": {"flips": flips, "flip_count": len(flips)},
    }


@router.post("/skill-evals/suites/{suite_id}/jobs/create")
async def create_skill_eval_job(suite_id: str, request: dict, http_request: Request):
    """
    创建一个定时 Job（由 JobScheduler 周期性执行 skill_eval_trigger）。
    Body:
      {
        "cron": "0 2 * * *",
        "timezone": "Asia/Shanghai",
        "enabled": true,
        "mode": "heuristic"
      }
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    body = dict(request or {}) if isinstance(request, dict) else {}
    actor = actor_from_http(http_request, body)
    deny = await rbac_guard(
        http_request=http_request,
        payload=body,
        action="update",
        resource_type="job",
        resource_id=f"skill_eval:{suite_id}",
        run_id=None,
    )
    if deny:
        return deny

    cron = str(body.get("cron") or "0 2 * * *").strip()
    timezone = str(body.get("timezone") or "Asia/Shanghai").strip()
    enabled = bool(body.get("enabled", True))
    mode = str(body.get("mode") or "heuristic").strip().lower()

    job_id = new_prefixed_id("job")
    job = await store.create_job(
        job_id=job_id,
        name=f"skill-eval:{suite_id}",
        enabled=enabled,
        cron=cron,
        timezone=timezone,
        kind="skill",
        target_id="skill_eval_trigger",
        user_id=actor.get("actor_id") or "system",
        session_id=None,
        payload={"input": {"suite_id": str(suite_id), "mode": mode}, "context": {"tenant_id": actor.get("tenant_id")}},
        options={},
        delivery={},
    )
    return {"status": "ok", "job": job}
