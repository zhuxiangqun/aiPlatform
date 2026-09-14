"""FDE delivery pipeline session store — queryable server-side progress (Phase 1).

Does NOT invent a second PipelineEngine. Loads ``fde_delivery_v1`` template stages
and advances through HITL pauses with server-persisted state so the workbench can
start + poll honestly (no local fake progress).
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


TEMPLATE_ID = "fde_delivery_v1"


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))


def _sessions_dir() -> Path:
    d = _home() / "fde_delivery_sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _templates_dir() -> Path:
    return _home() / "workflow_templates"


def _seed_templates_dir() -> Path:
    """Repo workspace seed — fallback when AIPLAT_HOME has no template."""
    # core/apps/fde/service → parents[3] = core/
    return Path(__file__).resolve().parents[3] / "workspace_seeds" / "workflow_templates"


def load_delivery_template(name: str = TEMPLATE_ID) -> Dict[str, Any]:
    """Load workflow template as dict with ``stages`` list.

    Supports:
      - ``{name}.json``
      - ``{name}/workflow.yaml`` (frontmatter + JSON body, as installed by WorkflowInstaller)

    Search order: ``$AIPLAT_HOME/workflow_templates`` then workspace seeds.
    """
    safe = "".join(c for c in name if c.isalnum() or c in "_-").strip("_-")[:50]
    for d in (_templates_dir(), _seed_templates_dir()):
        json_fp = d / f"{safe}.json"
        if json_fp.is_file():
            return json.loads(json_fp.read_text(encoding="utf-8"))
        yaml_fp = d / safe / "workflow.yaml"
        if yaml_fp.is_file():
            return _parse_workflow_yaml(yaml_fp.read_text(encoding="utf-8"))

    raise FileNotFoundError(
        f"template not found: {safe} under {_templates_dir()} or {_seed_templates_dir()}"
    )


def _parse_workflow_yaml(text: str) -> Dict[str, Any]:
    """Extract JSON body after optional YAML frontmatter."""
    body = text
    if text.lstrip().startswith("---"):
        parts = re.split(r"^---\s*$", text, maxsplit=2, flags=re.M)
        # ['', frontmatter, body] or similar
        if len(parts) >= 3:
            body = parts[2]
        elif len(parts) == 2:
            body = parts[1]
    body = body.strip()
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("workflow body must be a JSON object")
    return data


def start_delivery_session(
    *,
    template_id: str = TEMPLATE_ID,
    customer_name: str = "",
    domain_id: str = "",
    actor: str = "fde_engineer",
    builder_project_id: str = "",
) -> Dict[str, Any]:
    """Create a queryable delivery session paused at first HITL (or first stage).

    Phase 3: optional ``builder_project_id`` links factory Builder products;
    workbench must not invent a parallel build path.
    """
    tpl = load_delivery_template(template_id)
    stages = list(tpl.get("stages") or [])
    if not stages:
        raise ValueError(f"template {template_id} has no stages")

    session_id = f"fde_del_{uuid.uuid4().hex[:12]}"
    idx = 0
    # Advance past non-HITL only after approve; on start pause at first stage
    # If first stage is human HITL, phase=paused immediately.
    first = stages[0]
    phase = "paused" if first.get("hitl") else "running"
    linked = bool((builder_project_id or "").strip())
    session = {
        "session_id": session_id,
        "template_id": template_id,
        "template_name": tpl.get("name") or template_id,
        "customer_name": customer_name,
        "domain_id": domain_id,
        "actor": actor,
        "builder_project_id": (builder_project_id or "").strip(),
        "builder_observation": None,
        "artifact_links": [],
        "eval_gate": None,
        "phase": phase,
        "current_stage_idx": idx,
        "current_stage_id": first.get("id", ""),
        "hitl_phase": first.get("hitl_phase") or "",
        "stages": [
            {
                "id": s.get("id"),
                "agent_id": s.get("agent_id"),
                "agent_name": s.get("agent_name"),
                "output_artifact": s.get("output_artifact"),
                "hitl": bool(s.get("hitl")),
                "hitl_phase": s.get("hitl_phase") or "",
                "status": "active" if i == 0 else "pending",
            }
            for i, s in enumerate(stages)
        ],
        "hitl_events": [],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "progress_pct": 0,
        "honesty": _honesty(linked),
    }
    _write(session)
    return session


def _honesty(builder_linked: bool) -> Dict[str, str]:
    if builder_linked:
        return {
            "mode": "builder_linked",
            "note": (
                "Phase 3: delivery session linked to Builder project_id; "
                "workbench only starts/observes/accepts factory products (no parallel build)"
            ),
        }
    return {
        "mode": "template_session",
        "note": (
            "Server-side stage cursor over fde_delivery_v1; agent LLM steps not auto-executed. "
            "Link a Builder project_id for Phase 3 factory products."
        ),
    }


def link_builder_project(session_id: str, builder_project_id: str) -> Dict[str, Any]:
    """Attach an existing Builder project_id (opaque link; no rebuild in FDE)."""
    session = get_delivery_session(session_id)
    if not session:
        raise FileNotFoundError(session_id)
    pid = (builder_project_id or "").strip()
    if not pid:
        raise ValueError("builder_project_id required")
    session["builder_project_id"] = pid
    session["honesty"] = _honesty(True)
    session["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    session.setdefault("hitl_events", []).append(
        {
            "action": "link_builder",
            "builder_project_id": pid,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )
    _write(session)
    return session


def attach_builder_observation(
    session_id: str,
    observation: Dict[str, Any],
    *,
    artifact_links: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Persist Builder observe snapshot from platform (caller fills via Facade)."""
    session = get_delivery_session(session_id)
    if not session:
        raise FileNotFoundError(session_id)
    if not isinstance(observation, dict):
        raise ValueError("observation must be a dict")
    session["builder_observation"] = {
        "phase": observation.get("phase") or observation.get("status") or "",
        "project_id": observation.get("project_id") or session.get("builder_project_id") or "",
        "detail": (observation.get("detail") or observation.get("error") or "")[:500],
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "raw_keys": sorted(list(observation.keys()))[:40],
    }
    if artifact_links is not None:
        session["artifact_links"] = list(artifact_links)[:50]
    else:
        session["artifact_links"] = _extract_artifact_links(observation)
    session["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write(session)
    return session


def _extract_artifact_links(observation: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Best-effort product links from Builder state (no IDE / no rebuild)."""
    links: List[Dict[str, Any]] = []
    for key in ("artifact_links", "artifacts", "outputs", "products"):
        raw = observation.get(key)
        if isinstance(raw, list):
            for item in raw[:20]:
                if isinstance(item, dict):
                    links.append(
                        {
                            "id": str(item.get("id") or item.get("name") or item.get("path") or "")[:120],
                            "url": str(item.get("url") or item.get("path") or item.get("href") or "")[:500],
                            "kind": str(item.get("kind") or item.get("type") or "artifact")[:40],
                        }
                    )
                elif isinstance(item, str) and item.strip():
                    links.append({"id": item[:120], "url": item[:500], "kind": "artifact"})
    state = observation.get("state")
    if isinstance(state, dict):
        for art_key in ("output_artifact", "last_artifact", "deploy_url", "app_url"):
            val = state.get(art_key)
            if isinstance(val, str) and val.strip():
                links.append({"id": art_key, "url": val[:500], "kind": "state"})
    # de-dupe by url
    seen = set()
    out = []
    for link in links:
        u = link.get("url") or link.get("id")
        if u and u not in seen:
            seen.add(u)
            out.append(link)
    return out[:30]


def evaluate_delivery_session(session_id: str) -> Dict[str, Any]:
    """Apply audit_schema ``fde_delivery_pipeline`` gate (Phase 3).

    When Builder is linked, require a non-failed observation before accept/done.
    Template-only sessions pass with honesty note (Phase 1 cursor still valid).
    """
    session = get_delivery_session(session_id)
    if not session:
        raise FileNotFoundError(session_id)

    gate_id = "fde_delivery_pipeline"
    linked = bool(session.get("builder_project_id"))
    reasons: List[str] = []
    passed = True

    if linked:
        obs = session.get("builder_observation") or {}
        phase = str(obs.get("phase") or "").lower()
        if not obs:
            passed = False
            reasons.append("builder_linked_but_not_observed")
        elif phase in {"failed", "error", "not_found"}:
            passed = False
            reasons.append(f"builder_phase_{phase or 'unknown'}")
        elif phase in {"done", "completed", "success", "ok", "accepted", "running", "paused", "executing"}:
            reasons.append(f"builder_phase_ok:{phase}")
        else:
            # Unknown phase: soft-fail closed for accept
            passed = False
            reasons.append(f"builder_phase_unrecognized:{phase or 'empty'}")
    else:
        reasons.append("template_session_no_builder_link")

    result = {
        "gate_id": gate_id,
        "passed": passed,
        "reasons": reasons,
        "builder_linked": linked,
        "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    session["eval_gate"] = result
    session["updated_at"] = result["evaluated_at"]
    _write(session)
    return result


def get_delivery_session(session_id: str) -> Optional[Dict[str, Any]]:
    fp = _sessions_dir() / f"{session_id}.json"
    if not fp.is_file():
        return None
    return json.loads(fp.read_text(encoding="utf-8"))


def list_delivery_sessions(limit: int = 20) -> List[Dict[str, Any]]:
    rows = []
    for fp in sorted(_sessions_dir().glob("fde_del_*.json"), reverse=True):
        try:
            rows.append(json.loads(fp.read_text(encoding="utf-8")))
        except Exception:
            continue
        if len(rows) >= limit:
            break
    return rows


def approve_delivery_session(session_id: str, feedback: str = "") -> Dict[str, Any]:
    """Resolve current HITL pause and advance; auto-skip non-HITL stages.

    Phase 3: when Builder is linked, final accept runs ``fde_delivery_pipeline`` eval.
    """
    session = get_delivery_session(session_id)
    if not session:
        raise FileNotFoundError(session_id)
    if session.get("phase") in {"done", "failed"}:
        return session
    # Allow retry after fixing Builder observation
    if session.get("phase") == "eval_blocked":
        gate = evaluate_delivery_session(session_id)
        session = get_delivery_session(session_id) or session
        if gate.get("passed"):
            session["phase"] = "done"
            session["hitl_phase"] = ""
            session["progress_pct"] = 100
            session.setdefault("hitl_events", []).append(
                {
                    "action": "eval_passed_retry",
                    "gate_id": gate.get("gate_id"),
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
            session["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _write(session)
        return session

    stages = session["stages"]
    idx = int(session.get("current_stage_idx") or 0)
    if idx < 0 or idx >= len(stages):
        session["phase"] = "done"
        session["progress_pct"] = 100
        _write(session)
        return session

    cur = stages[idx]
    cur["status"] = "done"
    session.setdefault("hitl_events", []).append(
        {
            "action": "approve",
            "stage_id": cur.get("id"),
            "feedback": (feedback or "")[:500],
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )

    idx += 1
    while idx < len(stages) and not stages[idx].get("hitl"):
        # Non-HITL stages: mark done without LLM (Phase 1 honesty)
        stages[idx]["status"] = "done_skipped_llm"
        session["hitl_events"].append(
            {
                "action": "auto_advance_non_hitl",
                "stage_id": stages[idx].get("id"),
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )
        idx += 1

    if idx >= len(stages):
        # Final accept — eval gate when Builder linked
        if session.get("builder_project_id"):
            _write(session)  # persist stage advances before evaluate
            gate = evaluate_delivery_session(session_id)
            session = get_delivery_session(session_id) or session
            if not gate.get("passed"):
                session["phase"] = "eval_blocked"
                session["current_stage_idx"] = len(stages) - 1
                session["current_stage_id"] = stages[-1].get("id", "")
                session["hitl_phase"] = "eval_gate"
                session["progress_pct"] = int(100 * (len(stages) - 1) / max(1, len(stages)))
                session["hitl_events"].append(
                    {
                        "action": "eval_blocked",
                        "gate_id": gate.get("gate_id"),
                        "reasons": gate.get("reasons"),
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                )
                session["stages"] = stages
                session["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                _write(session)
                return session
        session["phase"] = "done"
        session["current_stage_idx"] = len(stages) - 1
        session["current_stage_id"] = stages[-1].get("id", "")
        session["hitl_phase"] = ""
        session["progress_pct"] = 100
    else:
        stages[idx]["status"] = "active"
        session["phase"] = "paused"
        session["current_stage_idx"] = idx
        session["current_stage_id"] = stages[idx].get("id", "")
        session["hitl_phase"] = stages[idx].get("hitl_phase") or ""
        session["progress_pct"] = int(100 * idx / len(stages))

    session["stages"] = stages
    session["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write(session)
    return session


def _write(session: Dict[str, Any]) -> None:
    fp = _sessions_dir() / f"{session['session_id']}.json"
    tmp = fp.with_suffix(".tmp")
    tmp.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(fp)
