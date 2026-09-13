"""C4: stage success/failure sample bank (AFlow data prep only).

Records compact, queryable outcomes. Never mutates pipeline topology.
Kernel-generic: uses stage config fields only (no agent_id branching).
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

logger = logging.getLogger(__name__)

_SAMPLES_MAX = 1000
_SAMPLES_FILENAME = "stage_outcome_samples.json"

OUTCOME_OK = "ok"
OUTCOME_FAILED = "failed"
OUTCOME_GATE_HITL = "schema_gate_hitl"
OUTCOME_GATE_BLOCK = "schema_gate_block"
OUTCOME_GATE_FAIL = "schema_gate_fail_pipeline"


def stage_outcome_samples_path() -> Path:
    home = Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat"))
    return home / "wiki" / _SAMPLES_FILENAME


def _structured_keys_present(artifact: Any) -> List[str]:
    if not isinstance(artifact, Mapping):
        return []
    skip = {"raw_output", "handoff", "_sanitize_meta", "sanitize", "status", "error"}
    keys: List[str] = []
    for k, v in artifact.items():
        if str(k) in skip or str(k).startswith("_"):
            continue
        if v in (None, "", [], {}):
            continue
        keys.append(str(k)[:64])
        if len(keys) >= 24:
            break
    return keys


def _load_samples(path: Path) -> List[Any]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_samples(path: Path, samples: List[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(samples) > _SAMPLES_MAX:
        samples = samples[-_SAMPLES_MAX:]
    path.write_text(json.dumps(samples, ensure_ascii=False), encoding="utf-8")


def record_stage_outcome_sample(
    *,
    outcome: str,
    stage: Any = None,
    state: Optional[Mapping[str, Any]] = None,
    artifact_key: str = "",
    error: str = "",
    handoff: Optional[Mapping[str, Any]] = None,
    gate_errors: Optional[Sequence[str]] = None,
    source: str = "",
) -> Dict[str, Any]:
    """Append one stage outcome sample. Best-effort; never raises to callers."""
    st = state if isinstance(state, Mapping) else {}
    sid = str(getattr(stage, "id", "") or "")[:128] if stage is not None else ""
    skill = (
        str(getattr(stage, "skill_name", "") or "")[:128] if stage is not None else ""
    )
    out_art = str(
        artifact_key
        or (getattr(stage, "output_artifact", "") if stage is not None else "")
        or ""
    ).strip()[:128]
    art = st.get(out_art) if out_art else None
    summary = ""
    if isinstance(handoff, Mapping):
        summary = str(handoff.get("summary") or "")[:240]
    elif isinstance(art, Mapping) and isinstance(art.get("handoff"), Mapping):
        summary = str(art["handoff"].get("summary") or "")[:240]

    row: Dict[str, Any] = {
        "ts": time.time(),
        "outcome": str(outcome or "")[:64],
        "stage_id": sid,
        "skill_name": skill,
        "output_artifact": out_art,
        "project_id": str(st.get("project_id") or "")[:128],
        "run_id": str(st.get("run_id") or st.get("_run_id") or "")[:128],
        "error": str(error or "")[:400],
        "handoff_summary": summary,
        "structured_keys": _structured_keys_present(art),
        "gate_errors": [str(e)[:200] for e in (gate_errors or [])][:8],
        "source": str(source or "")[:64],
    }
    try:
        path = stage_outcome_samples_path()
        samples = _load_samples(path)
        samples.append(row)
        _save_samples(path, samples)
    except Exception:
        logger.debug("record_stage_outcome_sample failed", exc_info=True)
    return row


def record_from_handoff(
    state: MutableMapping[str, Any],
    *,
    stage: Any,
    artifact_key: str,
    handoff: Mapping[str, Any],
    status: str = "ok",
    error: str = "",
) -> Dict[str, Any]:
    """C4 hook from write_stage_handoff (success/fail envelope)."""
    st = str(status or "ok").strip().lower()
    outcome = OUTCOME_FAILED if st in ("failed", "error") or error else OUTCOME_OK
    return record_stage_outcome_sample(
        outcome=outcome,
        stage=stage,
        state=state,
        artifact_key=artifact_key,
        error=error,
        handoff=handoff,
        source="write_stage_handoff",
    )


def record_from_gate_failure(
    state: MutableMapping[str, Any],
    *,
    stage: Any,
    gate_result: Mapping[str, Any],
) -> Dict[str, Any]:
    """C4 hook from apply_gate_failure (schema gate pause/fail)."""
    action = str(gate_result.get("action") or "").strip().lower()
    if action == "hitl":
        outcome = OUTCOME_GATE_HITL
    elif action == "fail_pipeline":
        outcome = OUTCOME_GATE_FAIL
    elif action == "block":
        outcome = OUTCOME_GATE_BLOCK
    else:
        outcome = OUTCOME_GATE_BLOCK
    errors = [str(e) for e in (gate_result.get("errors") or [])]
    return record_stage_outcome_sample(
        outcome=outcome,
        stage=stage,
        state=state,
        artifact_key=str(getattr(stage, "output_artifact", "") or ""),
        error="; ".join(errors)[:400],
        gate_errors=errors,
        source="apply_gate_failure",
    )


def query_stage_outcome_samples(
    *,
    limit: int = 50,
    outcome: Optional[str] = None,
    stage_id: Optional[str] = None,
    project_id: Optional[str] = None,
    skill_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Query recent samples (newest last). Does not alter topology."""
    samples = _load_samples(stage_outcome_samples_path())
    out: List[Dict[str, Any]] = []
    for row in samples:
        if not isinstance(row, Mapping):
            continue
        if outcome is not None and str(row.get("outcome") or "") != str(outcome):
            continue
        if stage_id is not None and str(row.get("stage_id") or "") != str(stage_id):
            continue
        if project_id is not None and str(row.get("project_id") or "") != str(project_id):
            continue
        if skill_name is not None and str(row.get("skill_name") or "") != str(skill_name):
            continue
        out.append(dict(row))
    lim = max(1, min(int(limit or 50), _SAMPLES_MAX))
    return out[-lim:]


def summarize_stage_outcome_samples(
    samples: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Aggregate counts by outcome (for diagnostics)."""
    rows = list(samples) if samples is not None else query_stage_outcome_samples(limit=_SAMPLES_MAX)
    by_outcome: Dict[str, int] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        key = str(row.get("outcome") or "unknown")
        by_outcome[key] = by_outcome.get(key, 0) + 1
    return {"total": len(rows), "by_outcome": by_outcome}
