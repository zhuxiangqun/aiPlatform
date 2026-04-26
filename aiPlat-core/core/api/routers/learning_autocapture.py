from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from core.harness.kernel.runtime import get_kernel_runtime
from core.learning.pipeline import summarize_syscall_events
from core.learning.workspace_target import ensure_workspace_target

router = APIRouter()


def _rt():
    return get_kernel_runtime()


def _store():
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None


def _managers():
    rt = _rt()
    return {
        "engine_skill_manager": getattr(rt, "skill_manager", None) if rt else None,
        "workspace_skill_manager": getattr(rt, "workspace_skill_manager", None) if rt else None,
        "engine_agent_manager": getattr(rt, "agent_manager", None) if rt else None,
        "workspace_agent_manager": getattr(rt, "workspace_agent_manager", None) if rt else None,
    }


@router.post("/learning/autocapture")
async def autocapture_learning_suggestion(request: dict, http_request: Request):
    """
    Roadmap-4 (minimal): create a reviewable learning artifact from one execution.
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    from core.learning.types import LearningArtifact, LearningArtifactKind, LearningArtifactStatus

    target_type = str((request or {}).get("target_type") or "").strip()
    target_id = str((request or {}).get("target_id") or "").strip()
    trace_id = (request or {}).get("trace_id")
    run_id = (request or {}).get("run_id")
    reason = (request or {}).get("reason") or ""
    if not target_type or not target_id:
        raise HTTPException(status_code=400, detail="target_type and target_id are required")
    if not trace_id and not run_id:
        raise HTTPException(status_code=400, detail="trace_id or run_id is required")

    # Ensure learning artifacts land in workspace scope (fork engine target if needed).
    ms = _managers()
    ensured = await ensure_workspace_target(
        target_type=target_type,
        target_id=target_id,
        http_request=http_request,
        engine_skill_manager=ms.get("engine_skill_manager"),
        workspace_skill_manager=ms.get("workspace_skill_manager"),
        engine_agent_manager=ms.get("engine_agent_manager"),
        workspace_agent_manager=ms.get("workspace_agent_manager"),
        store=store,
        strict=False,  # autocapture is an observability flow; fail-open
    )
    if isinstance(ensured, dict):
        target_type = str(ensured.get("target_type") or target_type)
        target_id = str(ensured.get("target_id") or target_id)

    # Collect syscall events
    events_res = await store.list_syscall_events(
        limit=500,
        offset=0,
        trace_id=str(trace_id) if trace_id else None,
        run_id=str(run_id) if run_id else None,
    )
    events = (events_res or {}).get("items") or []
    summary = summarize_syscall_events(events)

    # Collect execution record (best-effort)
    exec_rec: Optional[Dict[str, Any]] = None
    try:
        if target_type == "agent" and run_id:
            exec_rec = await store.get_agent_execution(str(run_id))
        if target_type == "skill" and run_id:
            exec_rec = await store.get_skill_execution(str(run_id))
    except Exception:
        exec_rec = None

    # Basic recommendations (best-effort, deterministic)
    failed = [e for e in events if str(e.get("status") or "").lower() in ("failed", "error")]
    top_failed: Dict[str, int] = {}
    for e in failed:
        k = f"{e.get('kind')}:{e.get('name')}"
        top_failed[k] = top_failed.get(k, 0) + 1
    top_failed_list = sorted(top_failed.items(), key=lambda kv: kv[1], reverse=True)[:10]

    feedback = {
        "reason": str(reason),
        "execution": exec_rec or {},
        "syscalls_summary": summary,
        "top_failed_syscalls": [{"key": k, "count": v} for k, v in top_failed_list],
        "notes": [
            "该 artifact 仅用于审核/分析，不会自动改变线上行为。",
            "如需自动修复/沉淀为技能包，请基于该 artifact 人工生成 prompt_revision/skill_evolution 后再发布。",
        ],
    }

    artifact = LearningArtifact(
        artifact_id=f"auto-{uuid.uuid4().hex[:12]}",
        kind=LearningArtifactKind.FEEDBACK_SUMMARY,
        target_type=target_type,
        target_id=target_id,
        version=f"auto:{int(time.time())}",
        status=LearningArtifactStatus.DRAFT,
        trace_id=str(trace_id) if trace_id else None,
        run_id=str(run_id) if run_id else None,
        payload={"feedback": feedback},
        metadata={"source": "autocapture", "event_count": len(events)},
    )
    await store.upsert_learning_artifact(artifact.to_record())
    return await store.get_learning_artifact(artifact.artifact_id)


@router.post("/learning/autocapture/to_prompt_revision")
async def autocapture_to_prompt_revision(request: dict, http_request: Request):
    """
    Convert a feedback_summary artifact into a draft prompt_revision,
    optionally wrapping it into a draft release_candidate.
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    from core.learning.types import LearningArtifact, LearningArtifactKind, LearningArtifactStatus

    artifact_id = str((request or {}).get("artifact_id") or "").strip()
    if not artifact_id:
        raise HTTPException(status_code=400, detail="artifact_id is required")
    src = await store.get_learning_artifact(artifact_id)
    if not src:
        raise HTTPException(status_code=404, detail="artifact_not_found")
    if src.get("kind") != "feedback_summary":
        raise HTTPException(status_code=400, detail="artifact_kind_must_be_feedback_summary")

    target_type = str(src.get("target_type") or "")
    target_id = str(src.get("target_id") or "")
    trace_id = src.get("trace_id")
    run_id = src.get("run_id")
    fb = (src.get("payload") or {}).get("feedback") if isinstance(src.get("payload"), dict) else None
    fb = fb if isinstance(fb, dict) else {}

    # Ensure workspace scope (fail-open for autocapture conversion)
    ms = _managers()
    ensured = await ensure_workspace_target(
        target_type=target_type,
        target_id=target_id,
        http_request=http_request,
        engine_skill_manager=ms.get("engine_skill_manager"),
        workspace_skill_manager=ms.get("workspace_skill_manager"),
        engine_agent_manager=ms.get("engine_agent_manager"),
        workspace_agent_manager=ms.get("workspace_agent_manager"),
        store=store,
        strict=False,
    )
    if isinstance(ensured, dict):
        target_type = str(ensured.get("target_type") or target_type)
        target_id = str(ensured.get("target_id") or target_id)

    patch = (request or {}).get("patch") if isinstance((request or {}).get("patch"), dict) else None
    if patch is None:
        # Auto-generate a minimal prepend patch from feedback (deterministic, reviewable).
        top_failed = fb.get("top_failed_syscalls") if isinstance(fb.get("top_failed_syscalls"), list) else []
        lines = []
        reason = fb.get("reason")
        if isinstance(reason, str) and reason.strip():
            lines.append(f"【背景】{reason.strip()}")
        if top_failed:
            lines.append("【近期失败 syscall Top】")
            for x in top_failed[:10]:
                if not isinstance(x, dict):
                    continue
                k = x.get("key")
                c = x.get("count")
                if k:
                    lines.append(f"- {k}: {c}")
        lines.append("【要求】当执行失败时：优先给出可操作的下一步（包括需要的参数、检查点、以及可复现步骤）。")
        patch = {"prepend": "\n".join(lines)}

    pr_id = f"pr-auto-{uuid.uuid4().hex[:12]}"
    meta: Dict[str, Any] = {"source": "autocapture", "source_artifact_id": artifact_id}
    if (request or {}).get("priority") is not None:
        meta["priority"] = (request or {}).get("priority")
    if isinstance((request or {}).get("exclusive_group"), str) and (request or {}).get("exclusive_group"):
        meta["exclusive_group"] = (request or {}).get("exclusive_group")

    pr = LearningArtifact(
        artifact_id=pr_id,
        kind=LearningArtifactKind.PROMPT_REVISION,
        target_type=target_type,
        target_id=target_id,
        version=f"auto:{int(time.time())}",
        status=LearningArtifactStatus.DRAFT,
        trace_id=str(trace_id) if trace_id else None,
        run_id=str(run_id) if run_id else None,
        payload={"patch": patch},
        metadata=meta,
    )
    await store.upsert_learning_artifact(pr.to_record())

    out: Dict[str, Any] = {"prompt_revision": await store.get_learning_artifact(pr_id)}
    if bool((request or {}).get("create_release_candidate", False)):
        rc_id = f"rc-auto-{uuid.uuid4().hex[:12]}"
        summary = (request or {}).get("summary")
        if not isinstance(summary, str) or not summary.strip():
            summary = f"auto from {artifact_id}"
        rc = LearningArtifact(
            artifact_id=rc_id,
            kind=LearningArtifactKind.RELEASE_CANDIDATE,
            target_type=target_type,
            target_id=target_id,
            version=f"auto:{int(time.time())}",
            status=LearningArtifactStatus.DRAFT,
            trace_id=str(trace_id) if trace_id else None,
            run_id=str(run_id) if run_id else None,
            payload={"artifact_ids": [pr_id], "summary": str(summary)},
            metadata={"source": "autocapture", "source_artifact_id": artifact_id},
        )
        await store.upsert_learning_artifact(rc.to_record())
        out["release_candidate"] = await store.get_learning_artifact(rc_id)
    return out


@router.post("/learning/autocapture/to_skill_evolution")
async def autocapture_to_skill_evolution(request: dict, http_request: Request):
    """
    Convert a feedback_summary into a draft skill_evolution suggestion artifact.
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    from core.learning.types import LearningArtifact, LearningArtifactKind, LearningArtifactStatus

    artifact_id = str((request or {}).get("artifact_id") or "").strip()
    if not artifact_id:
        raise HTTPException(status_code=400, detail="artifact_id is required")
    src = await store.get_learning_artifact(artifact_id)
    if not src:
        raise HTTPException(status_code=404, detail="artifact_not_found")
    if src.get("kind") != "feedback_summary":
        raise HTTPException(status_code=400, detail="artifact_kind_must_be_feedback_summary")

    target_type = str(src.get("target_type") or "")
    target_id = str(src.get("target_id") or "")
    trace_id = src.get("trace_id")
    run_id = src.get("run_id")
    fb = (src.get("payload") or {}).get("feedback") if isinstance(src.get("payload"), dict) else None
    fb = fb if isinstance(fb, dict) else {}

    ms = _managers()
    ensured = await ensure_workspace_target(
        target_type=target_type,
        target_id=target_id,
        http_request=http_request,
        engine_skill_manager=ms.get("engine_skill_manager"),
        workspace_skill_manager=ms.get("workspace_skill_manager"),
        engine_agent_manager=ms.get("engine_agent_manager"),
        workspace_agent_manager=ms.get("workspace_agent_manager"),
        store=store,
        strict=False,
    )
    if isinstance(ensured, dict):
        target_type = str(ensured.get("target_type") or target_type)
        target_id = str(ensured.get("target_id") or target_id)

    suggestion = (request or {}).get("suggestion")
    if not isinstance(suggestion, str) or not suggestion.strip():
        top_failed = fb.get("top_failed_syscalls") if isinstance(fb.get("top_failed_syscalls"), list) else []
        lines = []
        if fb.get("reason"):
            lines.append(f"【来源】{fb.get('reason')}")
        lines.append("【建议】基于失败 syscall 归因，补充技能 SOP 的前置条件/参数校验/失败分支处理。")
        if top_failed:
            lines.append("【失败 syscall Top】")
            for x in top_failed[:10]:
                if isinstance(x, dict) and x.get("key"):
                    lines.append(f"- {x.get('key')}: {x.get('count')}")
        suggestion = "\n".join(lines)

    se_id = f"se-auto-{uuid.uuid4().hex[:12]}"
    se = LearningArtifact(
        artifact_id=se_id,
        kind=LearningArtifactKind.SKILL_EVOLUTION,
        target_type=target_type,
        target_id=target_id,
        version=f"auto:{int(time.time())}",
        status=LearningArtifactStatus.DRAFT,
        trace_id=str(trace_id) if trace_id else None,
        run_id=str(run_id) if run_id else None,
        payload={"suggestion": suggestion},
        metadata={"source": "autocapture", "source_artifact_id": artifact_id},
    )
    await store.upsert_learning_artifact(se.to_record())
    out: Dict[str, Any] = {"skill_evolution": await store.get_learning_artifact(se_id)}

    if bool((request or {}).get("create_release_candidate", False)):
        rc_id = f"rc-auto-{uuid.uuid4().hex[:12]}"
        summary = (request or {}).get("summary")
        if not isinstance(summary, str) or not summary.strip():
            summary = f"auto from {artifact_id}"
        rc = LearningArtifact(
            artifact_id=rc_id,
            kind=LearningArtifactKind.RELEASE_CANDIDATE,
            target_type=target_type,
            target_id=target_id,
            version=f"auto:{int(time.time())}",
            status=LearningArtifactStatus.DRAFT,
            trace_id=str(trace_id) if trace_id else None,
            run_id=str(run_id) if run_id else None,
            payload={"artifact_ids": [se_id], "summary": str(summary)},
            metadata={"source": "autocapture", "source_artifact_id": artifact_id},
        )
        await store.upsert_learning_artifact(rc.to_record())
        out["release_candidate"] = await store.get_learning_artifact(rc_id)

    return out


@router.post("/learning/feedback")
async def record_learning_feedback(request: dict, http_request: Request):
    """
    Minimal feedback loop (M1):
    - Record a feedback artifact (accept/reject/edit) for traceability
    - Optionally auto-capture into a skill-eval suite (trigger/quality)

    Body:
      {
        "suite_id": "optional",
        "suite_kind": "trigger|quality",   // required if suite_id provided
        "decision": "accept|reject|edit",
        "query": "...",                    // required if suite_id provided
        "comment": "optional",
        "edited_output": "optional",       // used when decision=edit and suite_kind=quality
        "run_id": "optional",
        "trace_id": "optional"
      }
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    from core.learning.types import LearningArtifact, LearningArtifactKind, LearningArtifactStatus
    from core.governance.changeset import record_changeset

    body = request or {}
    decision = str(body.get("decision") or "").strip().lower()
    if decision not in {"accept", "reject", "edit"}:
        raise HTTPException(status_code=400, detail="decision must be accept|reject|edit")
    suite_id = str(body.get("suite_id") or "").strip()
    suite_kind = str(body.get("suite_kind") or "").strip().lower()
    query = str(body.get("query") or "").strip()
    comment = str(body.get("comment") or "")
    edited_output = body.get("edited_output")
    run_id = body.get("run_id")
    trace_id = body.get("trace_id")

    # Create a small feedback artifact
    fb = {
        "decision": decision,
        "query": query,
        "comment": comment,
        "edited_output": edited_output if isinstance(edited_output, str) else None,
        "suite_id": suite_id or None,
        "suite_kind": suite_kind or None,
        "trace_id": str(trace_id) if trace_id else None,
        "run_id": str(run_id) if run_id else None,
    }
    art = LearningArtifact(
        artifact_id=f"fb-{uuid.uuid4().hex[:12]}",
        kind=LearningArtifactKind.FEEDBACK_SUMMARY,
        target_type="suite" if suite_id else "run",
        target_id=suite_id if suite_id else (str(run_id) if run_id else (str(trace_id) if trace_id else "unknown")),
        version=f"fb:{int(time.time())}",
        status=LearningArtifactStatus.DRAFT,
        trace_id=str(trace_id) if trace_id else None,
        run_id=str(run_id) if run_id else None,
        payload={"feedback": fb},
        metadata={"source": "feedback_api"},
    )
    await store.upsert_learning_artifact(art.to_record())

    updated_suite = None
    if suite_id:
        if suite_kind not in {"trigger", "quality"}:
            raise HTTPException(status_code=400, detail="suite_kind must be trigger|quality when suite_id provided")
        if not query:
            raise HTTPException(status_code=400, detail="query is required when suite_id provided")
        suite = await store.get_skill_eval_suite(suite_id=suite_id)
        if not suite:
            raise HTTPException(status_code=404, detail="suite_not_found")
        cfg = suite.get("config") if isinstance(suite.get("config"), dict) else {}
        cfg = dict(cfg)
        now = time.time()
        if suite_kind == "trigger":
            pos = cfg.get("positive_queries") if isinstance(cfg.get("positive_queries"), list) else []
            neg = cfg.get("negative_queries") if isinstance(cfg.get("negative_queries"), list) else []
            pos = [str(x) for x in pos if isinstance(x, str)]
            neg = [str(x) for x in neg if isinstance(x, str)]
            if decision == "accept":
                if query not in pos:
                    pos.append(query)
            else:
                if query not in neg:
                    neg.append(query)
            cfg["positive_queries"] = pos
            cfg["negative_queries"] = neg
        else:
            cases = cfg.get("quality_cases") if isinstance(cfg.get("quality_cases"), list) else []
            cases = [x for x in cases if isinstance(x, dict)]
            expected_text = str(edited_output or "").strip() if decision == "edit" else ""
            if not expected_text:
                expected_text = "N/A"
            cases.append(
                {
                    "name": f"fb:{decision}:{int(now)}",
                    "input": {"query": query},
                    "expected": {"text": expected_text, "decision": decision},
                }
            )
            cfg["quality_cases"] = cases

        updated_suite = await store.upsert_skill_eval_suite(
            suite_id=str(suite_id),
            tenant_id=suite.get("tenant_id"),
            scope=str(suite.get("scope") or "workspace"),
            target_skill_id=str(suite.get("target_skill_id") or ""),
            name=str(suite.get("name") or ""),
            description=str(suite.get("description") or ""),
            config=cfg,
        )
        # governance record (traceable)
        try:
            await record_changeset(
                store=store,
                name="learning.feedback.captured_to_suite",
                target_type="skill_eval_suite",
                target_id=str(suite_id),
                status="success",
                args={"decision": decision, "suite_kind": suite_kind},
                result={"query": query, "artifact_id": art.artifact_id},
                user_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID") or "system"),
                tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID") or "") or None,
            )
        except Exception:
            pass
        try:
            await store.add_audit_log(
                action="learning_feedback_recorded",
                status="ok",
                tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID") or "") or None,
                actor_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID") or "") or None,
                actor_role=str(http_request.headers.get("X-AIPLAT-ACTOR-ROLE") or "") or None,
                resource_type="skill_eval_suite",
                resource_id=str(suite_id),
                detail={"decision": decision, "suite_kind": suite_kind, "artifact_id": art.artifact_id},
            )
        except Exception:
            pass

    return {"status": "ok", "artifact": await store.get_learning_artifact(art.artifact_id), "suite": updated_suite}
