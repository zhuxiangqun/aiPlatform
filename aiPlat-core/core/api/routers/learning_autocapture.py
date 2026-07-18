from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from core.harness.kernel.runtime import get_kernel_runtime
from core.learning.pipeline import summarize_syscall_events
from core.learning.workspace_target import ensure_workspace_target
import logging

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


@router.post("/learning/feedback", response_model=Dict[str, Any])
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
        except Exception as e:
            logging.warning(str(e), exc_info=True)
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
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    return {"status": "ok", "artifact": await store.get_learning_artifact(art.artifact_id), "suite": updated_suite}
