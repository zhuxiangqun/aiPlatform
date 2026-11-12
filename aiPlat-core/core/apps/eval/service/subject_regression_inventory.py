"""Cross-Subject regression honesty inventory (claim stays false).

Aggregates per-Subject ``*_regression_status`` snapshots after OBJECT_TYPES
banks landed. Does not freeze packs, open claim, or run live exams.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

INVENTORY_SCHEMA = "eval.subject_regression_inventory.v1"

# (subject_kind, object_type_member, tab_id, loader)
# object_type_member=True → first-class OBJECT_TYPES; else Subject-local only.
_Loader = Callable[..., Dict[str, Any]]


def _loaders() -> List[Tuple[str, bool, str, _Loader]]:
    from core.apps.eval.service.api_capability_bank import api_regression_status
    from core.apps.eval.service.code_review_capability_bank import (
        code_review_regression_status,
    )
    from core.apps.eval.service.dataset_capability_bank import (
        dataset_regression_status,
    )
    from core.apps.eval.service.generated_app_capability_bank import (
        generated_app_regression_status,
    )
    from core.apps.eval.service.kb_capability_bank import kb_regression_status
    from core.apps.eval.service.model_capability_bank import model_regression_status
    from core.apps.eval.service.multi_agent_capability_bank import (
        multi_agent_regression_status,
    )
    from core.apps.eval.service.prompt_capability_bank import prompt_regression_status
    from core.apps.eval.service.session_capability_bank import (
        session_regression_status,
    )
    from core.apps.eval.service.skill_capability_bank import skill_regression_status
    from core.apps.eval.service.system_capability_bank import system_regression_status
    from core.apps.eval.service.tool_capability_bank import tool_regression_status
    from core.apps.eval.service.workflow_capability_bank import (
        workflow_regression_status,
    )

    return [
        ("agent", True, "p1-regression", _agent_regression_status),
        ("prompt", True, "prompt-regression", prompt_regression_status),
        ("skill", True, "skill-regression", skill_regression_status),
        ("workflow", True, "workflow-regression", workflow_regression_status),
        ("model", True, "model-regression", model_regression_status),
        ("api", True, "api-regression", api_regression_status),
        ("generated_app", True, "generated-app-regression", generated_app_regression_status),
        ("dataset", True, "dataset-regression", dataset_regression_status),
        ("system", True, "system-regression", system_regression_status),
        ("kb", False, "kb-regression", kb_regression_status),
        ("code_review", False, "code-review-regression", code_review_regression_status),
        ("session", False, "session-regression", session_regression_status),
        ("tool", False, "tool-regression", tool_regression_status),
        ("multi_agent", False, "multi-agent-regression", multi_agent_regression_status),
    ]


def _agent_regression_status(*, draft_sample_limit: int = 5) -> Dict[str, Any]:
    """Normalize P1 / agent.capability readiness into inventory row fields."""
    from collections import Counter

    from core.apps.eval.service.capability_case_bank import (
        PROFILE_ID,
        build_agent_capability_cases,
        load_pack_meta,
    )
    from core.apps.eval.service.capability_cert_readiness import (
        evaluate_certification_readiness,
    )

    cases = build_agent_capability_cases()
    meta = load_pack_meta()
    review_counts: Counter = Counter()
    draft_pending = 0
    _PURPOSE_OK = frozenset({"purpose_ok", "reviewed", "approved", "frozen"})
    for c in cases:
        rev = c.get("review") if isinstance(c.get("review"), dict) else {}
        st = str((rev or {}).get("status") or "draft").strip().lower() or "draft"
        review_counts[st] += 1
        if st not in _PURPOSE_OK:
            draft_pending += 1
    ready = evaluate_certification_readiness(
        profile_id=PROFILE_ID,
        cases=cases,
        compile_plan=True,
        pack_kind=str(meta.get("kind") or ""),
        pack_status=str(meta.get("status") or ""),
    )
    n_gaps = int((ready.get("coverage") or {}).get("n_gaps") or 0)
    purpose_ok_n = (
        int(review_counts.get("purpose_ok", 0))
        + int(review_counts.get("reviewed", 0))
        + int(review_counts.get("approved", 0))
        + int(review_counts.get("frozen", 0))
    )
    pack_status = str(meta.get("status") or "draft")
    profile_complete = bool(ready.get("profile_complete"))
    return {
        "schema": "eval.p1_regression_status.v1",
        "ok": bool(ready.get("ok")),
        "profile_id": PROFILE_ID,
        "pack_id": str(meta.get("pack_id") or "agent.capability"),
        "pack_version": str(meta.get("version") or ""),
        "pack_status": pack_status,
        "quota_inventory_ok": n_gaps == 0,
        "profile_complete": profile_complete,
        "case_count": len(cases),
        "purpose_ok_or_better": purpose_ok_n,
        "draft_pending": draft_pending,
        "accuracy_claim": False,
        "claim_eligible": False,
        "certification_eligible": False,
        "honesty": (
            "Agent P1 inventory only; "
            + (
                "seed purpose_ok + pack.meta frozen; "
                if profile_complete
                else "human purpose_ok/freeze still required; "
            )
            + "claim/cert stay false."
        ),
    }


def _row_from_status(
    *,
    subject_kind: str,
    object_type_member: bool,
    tab_id: str,
    status: Dict[str, Any],
    error: Optional[str] = None,
) -> Dict[str, Any]:
    st = status if isinstance(status, dict) else {}
    return {
        "subject_kind": subject_kind,
        "object_type_member": object_type_member,
        "tab_id": tab_id,
        "tab_href": f"/eval?tab={tab_id}",
        "ok": bool(st.get("ok")) and not error,
        "error": error,
        "profile_id": st.get("profile_id"),
        "pack_id": st.get("pack_id"),
        "pack_version": st.get("pack_version"),
        "pack_status": st.get("pack_status"),
        "quota_inventory_ok": bool(st.get("quota_inventory_ok")),
        "profile_complete": bool(st.get("profile_complete")),
        "case_count": int(st.get("case_count") or 0),
        "purpose_ok_or_better": int(st.get("purpose_ok_or_better") or 0),
        "draft_pending": int(st.get("draft_pending") or 0),
        "content_purpose_ok_count": int(st.get("content_purpose_ok_count") or 0),
        "content_purpose_ready": bool(st.get("content_purpose_ready")),
        "accuracy_claim": False,
        "claim_eligible": False,
        "certification_eligible": False,
        "honesty": st.get("honesty") or "",
    }


def _workspace_promote_snapshot(
    *,
    subject_kind: str,
    workspace_id: str,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """Look up workspace Case Pack freeze for one Subject (fail-soft)."""
    out: Dict[str, Any] = {
        "workspace_promoted": False,
        "workspace_pack_kind": "",
        "workspace_pack_status": "",
        "workspace_pack_id": "",
        "workspace_pack_version": "",
        "workspace_promote_error": "",
    }
    wid = str(workspace_id or "").strip()
    if not wid:
        return out
    try:
        from core.apps.eval.service.case_pack_registry import (
            PackRegistryError,
            get_pack_version,
        )
        from core.apps.eval.service.subject_capability_promote import _bank_specs

        spec = (_bank_specs() or {}).get(str(subject_kind or "").strip())
        if not isinstance(spec, dict):
            out["workspace_promote_error"] = "no_promotable_subject"
            return out
        pid = str(spec.get("pack_id") or "").strip()
        ver = str(spec.get("version") or "").strip()
        out["workspace_pack_id"] = pid
        out["workspace_pack_version"] = ver
        caller = str(caller_workspace_id or wid).strip() or wid
        cur = get_pack_version(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller,
        )
        kind = str(cur.get("kind") or "").strip().lower()
        status = str(cur.get("status") or "").strip().lower()
        out["workspace_pack_kind"] = kind
        out["workspace_pack_status"] = status
        # promote freeze writes kind=frozen (status often active)
        out["workspace_promoted"] = kind == "frozen"
    except PackRegistryError as exc:
        out["workspace_promote_error"] = str(exc)
    except Exception as exc:  # noqa: BLE001 — inventory fail-soft
        out["workspace_promote_error"] = f"{type(exc).__name__}:{exc}"
    return out


def subject_regression_inventory(
    *,
    draft_sample_limit: int = 5,
    workspace_id: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """Honesty matrix across Subject regression banks (claim stays false)."""
    rows: List[Dict[str, Any]] = []
    for kind, ot_member, tab_id, loader in _loaders():
        err: Optional[str] = None
        try:
            status = loader(draft_sample_limit=draft_sample_limit)
        except TypeError:
            try:
                status = loader()
            except Exception as exc:  # noqa: BLE001 — inventory fail-soft per row
                status = {}
                err = f"{type(exc).__name__}:{exc}"
        except Exception as exc:  # noqa: BLE001
            status = {}
            err = f"{type(exc).__name__}:{exc}"
        rows.append(
            _row_from_status(
                subject_kind=kind,
                object_type_member=ot_member,
                tab_id=tab_id,
                status=status if isinstance(status, dict) else {},
                error=err,
            )
        )

    # Enrich rows with ADR P1 content_purpose_ok audit (fail-soft per subject).
    try:
        from core.apps.eval.service.content_purpose_ok import (
            content_purpose_ok_for_subject,
        )

        for row in rows:
            kind = str(row.get("subject_kind") or "")
            try:
                crep = content_purpose_ok_for_subject(kind)
                row["content_purpose_ok_count"] = int(
                    crep.get("content_purpose_ok_count") or 0
                )
                row["content_purpose_ready"] = bool(crep.get("content_purpose_ready"))
            except Exception as exc:  # noqa: BLE001
                row["content_purpose_ok_count"] = 0
                row["content_purpose_ready"] = False
                if not row.get("error"):
                    row["error"] = f"content_purpose:{type(exc).__name__}:{exc}"
    except Exception:  # noqa: BLE001 — inventory still useful without content module
        pass

    wid = str(workspace_id or "").strip()
    caller = str(caller_workspace_id or wid).strip()
    if wid:
        for row in rows:
            snap = _workspace_promote_snapshot(
                subject_kind=str(row.get("subject_kind") or ""),
                workspace_id=wid,
                caller_workspace_id=caller,
            )
            row.update(snap)
    else:
        for row in rows:
            row.setdefault("workspace_promoted", False)
            row.setdefault("workspace_pack_kind", "")
            row.setdefault("workspace_pack_status", "")
            row.setdefault("workspace_pack_id", "")
            row.setdefault("workspace_pack_version", "")
            row.setdefault("workspace_promote_error", "")

    object_rows = [r for r in rows if r["object_type_member"]]
    quota_ok_n = sum(1 for r in rows if r["quota_inventory_ok"] and not r["error"])
    complete_n = sum(1 for r in rows if r["profile_complete"])
    draft_n = sum(int(r["draft_pending"] or 0) for r in rows)
    content_ready_n = sum(1 for r in rows if r.get("content_purpose_ready"))
    promoted_n = sum(1 for r in rows if r.get("workspace_promoted"))
    if not wid:
        next_action = (
            "Seed profile_complete may already be 14/14; bind a named workspace "
            "header to see workspace_promoted; use Inventory Promote / Promote 全部; "
            "claim/Certification stay closed."
        )
    elif promoted_n >= len(rows) and rows:
        next_action = (
            "All Subjects workspace-promoted (frozen) in this workspace; "
            "next: Case Pack compile-suite-profile → run exam; "
            "do not open claim/Certification from inventory alone."
        )
    elif promoted_n > 0:
        next_action = (
            f"Workspace promote partial ({promoted_n}/{len(rows)}); "
            "Promote remaining Subjects or Promote 全部; claim stays closed."
        )
    else:
        next_action = (
            "Seed packs are purpose_ok+frozen for profile_complete; "
            "workspace promote still pending — use Promote 当前/全部; "
            "claim/Certification stay closed."
        )
    return {
        "schema": INVENTORY_SCHEMA,
        "ok": all(r["ok"] for r in rows),
        "subject_count": len(rows),
        "object_type_subject_count": len(object_rows),
        "quota_inventory_ok_count": quota_ok_n,
        "profile_complete_count": complete_n,
        "draft_pending_total": draft_n,
        "content_purpose_ready_count": content_ready_n,
        "workspace_id": wid,
        "workspace_promoted_count": promoted_n,
        "subjects": rows,
        "accuracy_claim": False,
        "claim_eligible": False,
        "certification_eligible": False,
        "honesty": (
            "Cross-Subject inventory is engineering readiness only; "
            "quota_ok ≠ claim; content_purpose_ok gates promote stamp; "
            "profile_complete is seed-side; workspace_promoted is registry freeze; "
            "Method track (Arena/G2b/S1) excluded."
        ),
        "next_action": next_action,
        "review_links": {
            "method_track_tab": "/eval?tab=method-track",
            "case_packs_tab": "/eval?tab=case-packs",
            "p1_regression_tab": "/eval?tab=p1-regression",
            "content_purpose_ok_tab": "/eval?tab=subject-regression-inventory",
        },
    }
