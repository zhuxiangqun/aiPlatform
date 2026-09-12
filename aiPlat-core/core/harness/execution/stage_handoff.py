"""Frozen stage handoff / schema field names (C0) + thin envelope writer (F3).

Shared by factory envelope writers (F3) and pipeline gate_check (C1+).
Do not rename without a clause-sync; empty schemas = compatible no-op.

F3 writes a domain-agnostic envelope from stage config + artifact shape —
no agent_id / phase string branching.

C2: schema-gate HITL audit + resume re-check helpers.
C3: structured upstream artifact slices (prefer fields over prose).
C4: stage outcome samples via stage_outcome_samples (query only; no topology mutate).
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

# Envelope keys written into stage artifact meta / state["_handoff"][artifact]
HANDOFF_SUMMARY = "summary"
HANDOFF_ARTIFACT_REF = "artifact_ref"
HANDOFF_VERIFY = "verify"
HANDOFF_KNOWN_ISSUES = "known_issues"
HANDOFF_NEXT = "next"

HANDOFF_FIELDS: tuple[str, ...] = (
    HANDOFF_SUMMARY,
    HANDOFF_ARTIFACT_REF,
    HANDOFF_VERIFY,
    HANDOFF_KNOWN_ISSUES,
    HANDOFF_NEXT,
)

# PipelineStageConfig.gate_on_fail values (empty = no hard gate, backward compatible)
GATE_ON_FAIL_BLOCK = "block"
GATE_ON_FAIL_HITL = "hitl"
GATE_ON_FAIL_FAIL_PIPELINE = "fail_pipeline"
GATE_ON_FAIL_VALUES = frozenset(
    {"", GATE_ON_FAIL_BLOCK, GATE_ON_FAIL_HITL, GATE_ON_FAIL_FAIL_PIPELINE}
)

STATE_HANDOFF_KEY = "_handoff"
STATE_HITL_AUDIT_KEY = "_hitl_audit"
STATE_SCHEMA_GATE_PHASE = "_schema_gate_phase"

# C3: prefer these keys over raw_output when injecting upstream context
STRUCTURED_ARTIFACT_KEYS: tuple[str, ...] = (
    "title",
    "description",
    "functional_requirements",
    "user_stories",
    "decisions",
    "constraints",
    "scope",
    "open_questions",
    "acceptance_criteria",
    "components",
    "architecture_mode",
)


def empty_handoff() -> Dict[str, Any]:
    return {k: "" if k != HANDOFF_KNOWN_ISSUES else [] for k in HANDOFF_FIELDS}


def normalize_handoff(raw: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Return a complete handoff dict with frozen keys only."""
    base = empty_handoff()
    if not isinstance(raw, Mapping):
        return base
    for k in HANDOFF_FIELDS:
        if k not in raw:
            continue
        val = raw[k]
        if k == HANDOFF_KNOWN_ISSUES:
            if isinstance(val, list):
                base[k] = [str(x) for x in val]
            elif val:
                base[k] = [str(val)]
            else:
                base[k] = []
        else:
            base[k] = "" if val is None else str(val)
    return base


def attach_handoff(
    target: MutableMapping[str, Any],
    handoff: Optional[Mapping[str, Any]],
    *,
    meta_key: str = "handoff",
) -> Dict[str, Any]:
    """Write normalized handoff under target[meta_key]; return the normalized dict."""
    norm = normalize_handoff(handoff)
    target[meta_key] = norm
    return norm


def schema_is_active(schema: Any) -> bool:
    """False when schema is empty → gate must no-op (compat)."""
    if schema in (None, "", {}, []):
        return False
    if isinstance(schema, Mapping) and not schema:
        return False
    return True


def _coerce_artifact_payload(artifact: Any) -> Any:
    """Prefer parsed JSON object from raw_output when validating object schemas.

    C3: when the artifact already carries structured keys (e.g. functional_requirements),
    merge them over a sparse/empty JSON ``raw_output`` so gates see the patched fields.
    """
    if not isinstance(artifact, Mapping):
        return artifact
    base = {k: v for k, v in artifact.items() if k != "raw_output"}
    raw = artifact.get("raw_output")
    if isinstance(raw, str) and raw.strip():
        text = raw.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    merged = dict(parsed)
                    for k, v in base.items():
                        if v in (None, "", [], {}):
                            continue
                        # Explicit structured fields win over empty/missing raw JSON keys
                        if k not in merged or merged.get(k) in (None, "", [], {}):
                            merged[k] = v
                    return merged
                return parsed
            except Exception:
                pass  # noqa: cleanup-best-effort
        # Markdown / FILE dump — keep structured siblings
        return {"raw_output": text, **base}
    # Structured artifact without raw_output (e.g. materialized PRD)
    return dict(artifact)


def _validate_payload_against_schema(payload: Any, schema: Mapping[str, Any]) -> List[str]:
    """Lightweight required/type checks (stage opt-in; no ControlProfile bypass)."""
    errors: List[str] = []
    schema_type = str(schema.get("type") or "object")
    if schema_type == "object" and not isinstance(payload, dict):
        errors.append(f"Expected object (dict), got {type(payload).__name__}")
        return errors
    if schema_type == "string" and not isinstance(payload, str):
        errors.append(f"Expected string, got {type(payload).__name__}")
        return errors
    if schema_type == "array" and not isinstance(payload, list):
        errors.append(f"Expected array, got {type(payload).__name__}")
        return errors

    required = schema.get("required") or []
    if isinstance(required, list) and isinstance(payload, dict):
        missing = [f for f in required if f not in payload]
        if missing:
            errors.append(f"Missing required field(s): {', '.join(str(m) for m in missing)}")

    properties = schema.get("properties") or {}
    if isinstance(properties, Mapping) and isinstance(payload, dict):
        _type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "object": dict,
            "array": list,
        }
        for prop_name, prop_schema in properties.items():
            if prop_name not in payload or not isinstance(prop_schema, Mapping):
                continue
            expected = str(prop_schema.get("type") or "")
            if not expected:
                continue
            py = _type_map.get(expected)
            if py and not isinstance(payload[prop_name], py):
                errors.append(
                    f"Field '{prop_name}': expected {expected}, got {type(payload[prop_name]).__name__}"
                )
                continue
            # C3: one-level nested required (e.g. prd.functional_requirements)
            if expected == "object" and isinstance(payload[prop_name], dict):
                nested_req = prop_schema.get("required") or []
                if isinstance(nested_req, list):
                    missing_n = [
                        f for f in nested_req if f not in payload[prop_name]
                    ]
                    if missing_n:
                        errors.append(
                            f"Field '{prop_name}': missing required nested "
                            f"field(s): {', '.join(str(m) for m in missing_n)}"
                        )
                nested_props = prop_schema.get("properties") or {}
                if isinstance(nested_props, Mapping):
                    for nk, ns in nested_props.items():
                        if nk not in payload[prop_name] or not isinstance(ns, Mapping):
                            continue
                        nt = str(ns.get("type") or "")
                        npy = _type_map.get(nt)
                        if npy and not isinstance(payload[prop_name][nk], npy):
                            errors.append(
                                f"Field '{prop_name}.{nk}': expected {nt}, "
                                f"got {type(payload[prop_name][nk]).__name__}"
                            )
    return errors


def _build_input_payload(stage: Any, state: Mapping[str, Any], schema: Mapping[str, Any]) -> Any:
    keys: List[str] = []
    arts = getattr(stage, "input_artifacts", None) or []
    if isinstance(arts, (list, tuple)):
        keys.extend(str(k) for k in arts if k)
    req = schema.get("required") or []
    if isinstance(req, list):
        for k in req:
            sk = str(k)
            if sk and sk not in keys:
                keys.append(sk)
    if not keys and isinstance(schema.get("properties"), Mapping):
        keys.extend(str(k) for k in schema["properties"].keys())
    payload: Dict[str, Any] = {}
    for k in keys:
        if k not in state:
            continue
        payload[k] = _coerce_artifact_payload(state.get(k))
    return payload


def _build_output_payload(stage: Any, state: Mapping[str, Any]) -> Any:
    key = str(getattr(stage, "output_artifact", "") or "").strip()
    if not key:
        return None
    return _coerce_artifact_payload(state.get(key))


def gate_check(
    stage: Any,
    state: Mapping[str, Any],
    *,
    phase: str = "output",
) -> Dict[str, Any]:
    """C1 stage schema gate. Empty schema → ok/skipped (backward compatible).

    Returns dict:
      ok, skipped, phase, errors, action (""|block|hitl|fail_pipeline),
      handoff_missing (bool when handoff_required).
    """
    phase_l = str(phase or "output").strip().lower()
    if phase_l not in ("input", "output"):
        phase_l = "output"

    schema_attr = "input_schema" if phase_l == "input" else "output_schema"
    schema = getattr(stage, schema_attr, None) or {}
    action = str(getattr(stage, "gate_on_fail", "") or "").strip().lower()
    if action not in GATE_ON_FAIL_VALUES:
        action = ""

    result: Dict[str, Any] = {
        "ok": True,
        "skipped": False,
        "phase": phase_l,
        "errors": [],
        "action": action,
        "handoff_missing": False,
    }

    if not schema_is_active(schema):
        # Optional: handoff_required only applies on output
        if phase_l == "output" and bool(getattr(stage, "handoff_required", False)):
            key = str(getattr(stage, "output_artifact", "") or "").strip()
            art = state.get(key) if key else None
            handoff = art.get("handoff") if isinstance(art, Mapping) else None
            bucket = state.get(STATE_HANDOFF_KEY)
            if not isinstance(handoff, Mapping) and isinstance(bucket, Mapping) and key:
                handoff = bucket.get(key)
            summary = ""
            if isinstance(handoff, Mapping):
                summary = str(handoff.get(HANDOFF_SUMMARY) or "")
            if not summary:
                result["ok"] = False
                result["handoff_missing"] = True
                result["errors"] = ["handoff_required: missing handoff.summary"]
                return result
        result["skipped"] = True
        return result

    if phase_l == "input":
        payload = _build_input_payload(stage, state, schema if isinstance(schema, Mapping) else {})
    else:
        payload = _build_output_payload(stage, state)

    errors = _validate_payload_against_schema(
        payload, schema if isinstance(schema, Mapping) else {}
    )

    if phase_l == "output" and bool(getattr(stage, "handoff_required", False)):
        key = str(getattr(stage, "output_artifact", "") or "").strip()
        art = state.get(key) if key else None
        handoff = art.get("handoff") if isinstance(art, Mapping) else None
        if not (isinstance(handoff, Mapping) and str(handoff.get(HANDOFF_SUMMARY) or "")):
            errors.append("handoff_required: missing handoff.summary")
            result["handoff_missing"] = True

    if errors:
        result["ok"] = False
        result["errors"] = errors
    return result


def apply_gate_failure(
    state: MutableMapping[str, Any],
    stage: Any,
    gate_result: Mapping[str, Any],
    *,
    stages: Optional[Sequence[Any]] = None,
) -> bool:
    """Apply gate_on_fail policy. Returns True if caller should pause (HITL/block)."""
    if gate_result.get("ok") or gate_result.get("skipped"):
        return False
    errors = [str(e) for e in (gate_result.get("errors") or [])]
    msg = "; ".join(errors)[:500] or "schema_gate_failed"
    phase = str(gate_result.get("phase") or "output")
    action = str(gate_result.get("action") or "").strip().lower()

    state[f"_schema_gate_{getattr(stage, 'id', '')}"] = dict(gate_result)
    state["_last_action_reason"] = f"schema_gate_{phase}:{getattr(stage, 'id', '')}"

    # Warn-only when gate_on_fail empty — continue pipeline (do not set state.error)
    if not action:
        warns = state.setdefault("_schema_warnings", [])
        if isinstance(warns, list):
            warns.append({"stage_id": getattr(stage, "id", ""), "phase": phase, "errors": errors})
        try:
            write_stage_handoff(
                state,
                stage=stage,
                artifact_key=str(getattr(stage, "output_artifact", "") or ""),
                status="ok",
                error=msg,
                stages=stages,
            )
        except Exception:
            pass  # noqa: cleanup-best-effort
        return False

    state["error"] = msg

    try:
        write_stage_handoff(
            state,
            stage=stage,
            artifact_key=str(getattr(stage, "output_artifact", "") or ""),
            status="failed",
            error=msg,
            stages=stages,
        )
    except Exception:
        pass  # noqa: cleanup-best-effort

    sid = str(getattr(stage, "id", "") or "")
    if action == GATE_ON_FAIL_FAIL_PIPELINE:
        state["phase"] = "failed"
        state["error_message"] = msg
        if sid:
            state[f"_stage_{sid}_done"] = True
        append_hitl_audit(
            state,
            action="schema_gate_fail_pipeline",
            detail=f"stage={sid} phase={phase} {msg}",
        )
        try:
            from core.harness.execution.stage_outcome_samples import record_from_gate_failure

            record_from_gate_failure(state, stage=stage, gate_result=gate_result)
        except Exception:
            pass  # noqa: cleanup-best-effort
        try:
            from core.harness.team_friction import record_schema_gate_friction

            record_schema_gate_friction(
                "schema_gate_fail_pipeline",
                project_id=str(state.get("project_id") or state.get("_project_id") or ""),
                stage_id=sid,
                detail=msg,
                state=state,
            )
        except Exception:
            pass  # noqa: cleanup-best-effort
        return False

    # block + hitl → pause for human patch / regenerate / approve
    state["phase"] = "paused"
    state["_hitl_stage_id"] = sid
    state["_hitl_phase_name"] = "schema_gate"
    state[STATE_SCHEMA_GATE_PHASE] = phase
    state["_hitl_output_artifact"] = str(getattr(stage, "output_artifact", "") or "")
    if sid:
        state[f"_stage_{sid}_done"] = True
    gate_action = "schema_gate_hitl" if action == GATE_ON_FAIL_HITL else "schema_gate_block"
    append_hitl_audit(
        state,
        action=gate_action,
        detail=f"stage={sid} phase={phase} {msg}",
    )
    try:
        from core.harness.execution.stage_outcome_samples import record_from_gate_failure

        record_from_gate_failure(state, stage=stage, gate_result=gate_result)
    except Exception:
        pass  # noqa: cleanup-best-effort
    try:
        from core.harness.team_friction import record_schema_gate_friction

        record_schema_gate_friction(
            gate_action,
            project_id=str(state.get("project_id") or state.get("_project_id") or ""),
            stage_id=sid,
            detail=msg,
            state=state,
        )
    except Exception:
        pass  # noqa: cleanup-best-effort
    return True


def append_hitl_audit(
    state: MutableMapping[str, Any],
    *,
    action: str,
    actor: str = "system",
    detail: str = "",
) -> None:
    """C2: append a HITL / schema-gate audit row (best-effort)."""
    try:
        row = {
            "action": str(action or ""),
            "actor": str(actor or "system"),
            "detail": str(detail or "")[:500],
            "timestamp": time.time(),
        }
        bucket = state.setdefault(STATE_HITL_AUDIT_KEY, [])
        if isinstance(bucket, list):
            bucket.append(row)
    except Exception:
        pass  # noqa: cleanup-best-effort


def try_resume_schema_gate(
    state: MutableMapping[str, Any],
    stage: Any,
    *,
    stages: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """C2: after human patch/approve, re-run the gate that paused the pipeline.

    Returns ``{ok, phase, gate_result, cleared}``. When ok, clears pause/error
    fields so the caller can execute (input) or advance (output).
    """
    phase = str(
        state.get(STATE_SCHEMA_GATE_PHASE)
        or (state.get(f"_schema_gate_{getattr(stage, 'id', '')}") or {}).get("phase")
        or "output"
    ).strip().lower()
    if phase not in ("input", "output"):
        phase = "output"
    gate_result = gate_check(stage, state, phase=phase)
    out: Dict[str, Any] = {
        "ok": bool(gate_result.get("ok") or gate_result.get("skipped")),
        "phase": phase,
        "gate_result": dict(gate_result),
        "cleared": False,
    }
    if not out["ok"]:
        append_hitl_audit(
            state,
            action="schema_gate_resume_failed",
            detail="; ".join(str(e) for e in (gate_result.get("errors") or []))[:500],
        )
        # Keep paused; refresh gate snapshot
        apply_gate_failure(state, stage, gate_result, stages=stages)
        return out

    # Cleared — drop pause markers for this schema gate
    state.pop("error", None)
    state.pop("error_message", None)
    if str(state.get("phase") or "") == "paused":
        state["phase"] = "executing"
    state.pop("_hitl_stage_id", None)
    if str(state.get("_hitl_phase_name") or "") == "schema_gate":
        state["_hitl_phase_name"] = ""
    state.pop(STATE_SCHEMA_GATE_PHASE, None)
    sid = str(getattr(stage, "id", "") or "")
    if sid:
        state.pop(f"_schema_gate_{sid}", None)
        # Allow re-execution when input gate previously marked done
        if phase == "input":
            state.pop(f"_stage_{sid}_done", None)
    append_hitl_audit(
        state,
        action="schema_gate_resumed",
        detail=f"stage={sid} phase={phase}",
    )
    out["cleared"] = True
    return out


def is_schema_gate_pause(state: Mapping[str, Any]) -> bool:
    """True when current pause is from C1/C2 schema gate (not stage.hitl review)."""
    if str(state.get("_hitl_phase_name") or "") == "schema_gate":
        return True
    if state.get(STATE_SCHEMA_GATE_PHASE):
        return True
    return False


def extract_structured_fields(artifact: Any) -> Optional[Dict[str, Any]]:
    """C3: return structured keys present on an artifact (no raw_output)."""
    if not isinstance(artifact, Mapping):
        return None
    out: Dict[str, Any] = {}
    for k in STRUCTURED_ARTIFACT_KEYS:
        val = artifact.get(k)
        if val in (None, "", [], {}):
            continue
        out[k] = val
    return out or None


def format_structured_artifact_block(
    artifact_name: str,
    artifact: Any,
    *,
    raw_fallback_limit: int = 12000,
) -> str:
    """C3: prefer structured JSON block; fall back to raw_output prose.

    When structured fields exist, do **not** dump full raw markdown — downstream
    must consume fields, not regex prose.
    """
    name = str(artifact_name or "artifact")
    structured = extract_structured_fields(artifact)
    if structured:
        body = json.dumps(structured, ensure_ascii=False, indent=2, default=str)
        if len(body) > raw_fallback_limit:
            body = body[:raw_fallback_limit] + "\n…(truncated)"
        return (
            f"## {name} (structured)\n"
            "Use these fields directly. Do not re-extract requirements from prose.\n"
            f"{body}\n\n"
        )
    if isinstance(artifact, Mapping):
        raw = artifact.get("raw_output")
        if raw is not None and str(raw).strip():
            text = str(raw)
            if len(text) > raw_fallback_limit:
                text = text[:raw_fallback_limit] + "\n…(truncated)"
            return f"## {name}\n{text}\n\n"
    return ""


def _raw_preview(artifact: Any, *, limit: int = 160) -> str:
    if artifact is None:
        return ""
    if isinstance(artifact, Mapping):
        raw = artifact.get("raw_output")
        if raw is None and artifact.get("title"):
            return str(artifact.get("title") or "")[:limit]
        text = str(raw if raw is not None else "")
    else:
        text = str(artifact)
    text = " ".join(text.split())
    return text[:limit]


def _issues_from_sanitize(meta: Optional[Mapping[str, Any]]) -> List[str]:
    if not isinstance(meta, Mapping) or not meta:
        return []
    out: List[str] = []
    for key, val in meta.items():
        if not val:
            continue
        if isinstance(val, Mapping):
            interesting = [
                f"{k}={v}"
                for k, v in val.items()
                if v not in (None, "", False, [], {}) and k not in ("ok",)
            ][:4]
            if interesting:
                out.append(f"{key}: {', '.join(interesting)}")
            else:
                out.append(str(key))
        else:
            out.append(f"{key}: {val}")
        if len(out) >= 5:
            break
    return out


def resolve_next_stage_hint(
    stage: Any,
    stages: Optional[Sequence[Any]] = None,
) -> str:
    """Next pipeline stage id/artifact for handoff.next (config-driven)."""
    if not stages:
        return ""
    sid = str(getattr(stage, "id", "") or "")
    art = str(getattr(stage, "output_artifact", "") or "")
    idx = -1
    for i, s in enumerate(stages):
        if str(getattr(s, "id", "") or "") == sid:
            idx = i
            break
        if art and str(getattr(s, "output_artifact", "") or "") == art:
            idx = i
            break
    if idx < 0 or idx + 1 >= len(stages):
        return ""
    nxt = stages[idx + 1]
    nid = str(getattr(nxt, "id", "") or "")
    nart = str(getattr(nxt, "output_artifact", "") or "")
    nname = str(getattr(nxt, "agent_name", "") or getattr(nxt, "agent_id", "") or "")
    parts = [p for p in (nid, nart, nname) if p]
    return " → ".join(parts[:2]) if parts else ""


def build_stage_handoff(
    *,
    stage: Any,
    artifact_key: str,
    artifact: Any = None,
    sanitize_meta: Optional[Mapping[str, Any]] = None,
    status: str = "ok",
    error: str = "",
    next_hint: str = "",
    existing: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a thin MetaGPT-style envelope from stage config + artifact shape.

    Domain-agnostic: uses PipelineStageConfig fields and artifact structure only.
    """
    seed = normalize_handoff(existing)
    if isinstance(artifact, Mapping) and isinstance(artifact.get("handoff"), Mapping):
        seed = normalize_handoff({**seed, **artifact["handoff"]})

    skill = str(getattr(stage, "skill_name", "") or "")
    agent = str(getattr(stage, "agent_id", "") or "")
    hitl = bool(getattr(stage, "hitl", False))
    elapsed = ""
    chars = 0
    if isinstance(artifact, Mapping):
        if artifact.get("elapsed_sec") is not None:
            elapsed = str(artifact.get("elapsed_sec"))
        raw = artifact.get("raw_output")
        if isinstance(raw, str):
            chars = len(raw)
        elif raw is not None:
            chars = len(str(raw))

    st = str(status or "ok").strip().lower()
    if not seed[HANDOFF_SUMMARY]:
        who = skill or agent or "stage"
        if st in ("failed", "error"):
            seed[HANDOFF_SUMMARY] = f"{who} failed for `{artifact_key}`"
        else:
            bits = [f"{who} → `{artifact_key}`"]
            if chars:
                bits.append(f"{chars} chars")
            if elapsed:
                bits.append(f"{elapsed}s")
            preview = _raw_preview(artifact)
            seed[HANDOFF_SUMMARY] = " · ".join(bits) + (f" — {preview}" if preview else "")

    if not seed[HANDOFF_ARTIFACT_REF]:
        seed[HANDOFF_ARTIFACT_REF] = f"state:{artifact_key}" if artifact_key else ""

    if not seed[HANDOFF_VERIFY]:
        if st in ("failed", "error"):
            seed[HANDOFF_VERIFY] = "Regenerate this stage with feedback; re-check quality_gate / smoke."
        elif hitl:
            seed[HANDOFF_VERIFY] = "Human review in Factory stage card, then Approve or Reject."
        else:
            seed[HANDOFF_VERIFY] = (
                "Open Factory stage output; run downstream gate / page smoke when available."
            )

    issues = list(seed[HANDOFF_KNOWN_ISSUES] or [])
    if error:
        issues.append(str(error)[:300])
    for item in _issues_from_sanitize(sanitize_meta):
        if item not in issues:
            issues.append(item)
    seed[HANDOFF_KNOWN_ISSUES] = issues[:8]

    if not seed[HANDOFF_NEXT]:
        if st in ("failed", "error"):
            seed[HANDOFF_NEXT] = "Regenerate this stage (handoff context attached)."
        elif next_hint:
            seed[HANDOFF_NEXT] = f"Continue to {next_hint}"
        elif hitl:
            seed[HANDOFF_NEXT] = "Await HITL approval, then continue pipeline."
        else:
            seed[HANDOFF_NEXT] = "Proceed to next pipeline stage."

    return normalize_handoff(seed)


def write_stage_handoff(
    state: MutableMapping[str, Any],
    *,
    stage: Any,
    artifact_key: str,
    artifact: Any = None,
    sanitize_meta: Optional[Mapping[str, Any]] = None,
    status: str = "ok",
    error: str = "",
    stages: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Attach handoff to artifact dict + ``state[_handoff][artifact_key]``."""
    key = str(artifact_key or getattr(stage, "output_artifact", "") or "").strip()
    if not key:
        return empty_handoff()

    stored = artifact if artifact is not None else state.get(key)
    existing = None
    if isinstance(stored, Mapping):
        existing = stored.get("handoff")
    bucket = state.get(STATE_HANDOFF_KEY)
    if isinstance(bucket, Mapping) and isinstance(bucket.get(key), Mapping):
        existing = {**(existing or {}), **bucket[key]}

    norm = build_stage_handoff(
        stage=stage,
        artifact_key=key,
        artifact=stored,
        sanitize_meta=sanitize_meta,
        status=status,
        error=error,
        next_hint=resolve_next_stage_hint(stage, stages),
        existing=existing if isinstance(existing, Mapping) else None,
    )

    if isinstance(stored, dict):
        stored["handoff"] = norm
        state[key] = stored
    elif stored is None:
        state[key] = {"handoff": norm, "raw_output": "", "status": status}

    handoffs = state.get(STATE_HANDOFF_KEY)
    if not isinstance(handoffs, dict):
        handoffs = {}
        state[STATE_HANDOFF_KEY] = handoffs
    handoffs[key] = norm

    # C4: compact success/fail sample (best-effort; never blocks handoff)
    try:
        from core.harness.execution.stage_outcome_samples import record_from_handoff

        record_from_handoff(
            state,
            stage=stage,
            artifact_key=key,
            handoff=norm,
            status=status,
            error=error,
        )
    except Exception:
        pass  # noqa: cleanup-best-effort

    return norm


def format_handoff_regenerate_feedback(handoff: Optional[Mapping[str, Any]]) -> str:
    """Compact feedback string for regenerate_stage (next + known_issues)."""
    h = normalize_handoff(handoff)
    lines = ["[handoff]"]
    if h.get(HANDOFF_SUMMARY):
        lines.append(f"summary: {h[HANDOFF_SUMMARY][:240]}")
    if h.get(HANDOFF_NEXT):
        lines.append(f"next: {h[HANDOFF_NEXT]}")
    issues = h.get(HANDOFF_KNOWN_ISSUES) or []
    if issues:
        lines.append("known_issues:")
        for item in issues[:5]:
            lines.append(f"- {item}")
    if h.get(HANDOFF_VERIFY):
        lines.append(f"verify: {h[HANDOFF_VERIFY][:200]}")
    return "\n".join(lines)
