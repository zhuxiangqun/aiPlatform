"""T5: metrics-only team digest (no raw prompts / tool logs).

Aggregates adoption-style counters: pull/friction/Culture/bloat/gate outcomes.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

logger = logging.getLogger(__name__)


def aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")).expanduser()


def digest_store_path() -> Path:
    return aiplat_home() / "local" / "team_digest.json"


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def build_team_digest(
    *,
    project_id: str = "",
    project: Optional[Mapping[str, Any]] = None,
    lookback_sec: float = 7 * 24 * 3600,
) -> Dict[str, Any]:
    """Build a privacy-safe metrics digest slice (T5 / F-T5)."""
    now = time.time()
    since = now - max(3600.0, float(lookback_sec))
    proj = dict(project or {})
    pid = str(project_id or proj.get("project_id") or "")[:128]

    friction = _friction_counts(since=since, project_id=pid)
    outcomes = _outcome_summary(project_id=pid)
    culture = _culture_stats()
    pull = _pull_stats()
    bloat = _bloat_slice(proj)
    repair = _repair_slice(proj)
    style = _style_slice(proj)

    success = str(proj.get("phase") or "").lower() in ("done", "completed", "success")
    failed = str(proj.get("phase") or "").lower() in ("failed", "error")

    digest = {
        "ok": True,
        "generated_at": now,
        "lookback_sec": float(lookback_sec),
        "project_id": pid,
        "success": success,
        "failed": failed,
        "phase": str(proj.get("phase") or ""),
        "friction": friction,
        "outcomes": outcomes,
        "culture": culture,
        "pull": pull,
        "bloat": bloat,
        "repair": repair,
        "style": style,
        "view_rate": None,  # filled when UI records digest_viewed
        "privacy": "metrics_only",
    }
    digest["summary"] = _one_liner(digest)
    return digest


def record_digest_view(project_id: str = "") -> Dict[str, Any]:
    """Increment view counter for digest adoption metric."""
    path = digest_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: Dict[str, Any] = {"views": 0, "by_project": {}}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
    data["views"] = int(data.get("views") or 0) + 1
    data["last_view_at"] = time.time()
    if project_id:
        bp = data.setdefault("by_project", {})
        if isinstance(bp, dict):
            bp[str(project_id)] = int(bp.get(str(project_id)) or 0) + 1
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "views": data["views"]}


def _one_liner(d: Mapping[str, Any]) -> str:
    fr = d.get("friction") or {}
    bl = d.get("bloat") or {}
    oc = d.get("outcomes") or {}
    parts = [
        f"friction={int(fr.get('events') or 0)}",
        f"learnings={int(fr.get('learnings') or 0)}",
        f"gates={int(oc.get('gate_events') or 0)}",
    ]
    if bl.get("loc") is not None:
        parts.append(f"loc={bl.get('loc')}")
    if (d.get("repair") or {}).get("repair_exhausted"):
        parts.append("repair_exhausted")
    return " · ".join(parts)


def _friction_counts(*, since: float, project_id: str) -> Dict[str, Any]:
    out = {"events": 0, "learnings": 0, "by_signal": {}}
    try:
        from core.harness.team_friction import list_local_learnings

        learnings = list_local_learnings(limit=100)
        for row in learnings:
            if project_id and str(row.get("project_id") or "") not in ("", project_id):
                continue
            if _safe_float(row.get("created_at")) >= since or not since:
                out["learnings"] = int(out["learnings"]) + 1
    except Exception:
        logger.debug("digest friction learnings skipped", exc_info=True)

    try:
        path = aiplat_home() / "local" / "friction_state.json"
        if path.is_file():
            store = json.loads(path.read_text(encoding="utf-8"))
            events = store.get("events") if isinstance(store, dict) else []
            by: Dict[str, int] = {}
            n = 0
            if isinstance(events, list):
                for ev in events:
                    if not isinstance(ev, dict):
                        continue
                    if project_id and str(ev.get("project_id") or "") not in ("", project_id):
                        continue
                    if _safe_float(ev.get("ts")) < since:
                        continue
                    n += 1
                    sig = str(ev.get("signal") or "unknown")
                    by[sig] = int(by.get(sig) or 0) + 1
            out["events"] = n
            out["by_signal"] = by
    except Exception:
        logger.debug("digest friction events skipped", exc_info=True)
    return out


def _outcome_summary(*, project_id: str) -> Dict[str, Any]:
    try:
        from core.harness.execution.stage_outcome_samples import (
            query_stage_outcome_samples,
            summarize_stage_outcome_samples,
        )

        rows = query_stage_outcome_samples(project_id=project_id) if project_id else query_stage_outcome_samples()
        summary = summarize_stage_outcome_samples(rows)
        gate_events = 0
        by = summary.get("by_outcome") if isinstance(summary, dict) else {}
        if isinstance(by, dict):
            for k, v in by.items():
                if str(k).startswith("schema_gate"):
                    gate_events += int(v or 0)
        return {
            "total": int((summary or {}).get("total") or len(rows or [])),
            "by_outcome": by if isinstance(by, dict) else {},
            "gate_events": gate_events,
        }
    except Exception:
        logger.debug("digest outcomes skipped", exc_info=True)
        return {"total": 0, "by_outcome": {}, "gate_events": 0}


def _culture_stats() -> Dict[str, Any]:
    try:
        from core.harness.utils.team_culture import culture_body_hash, load_culture_text, estimate_tokens

        text = load_culture_text()
        return {
            "present": bool(str(text or "").strip()),
            "hash": culture_body_hash(text) if text else "",
            "tokens": estimate_tokens(text) if text else 0,
        }
    except Exception:
        return {"present": False, "hash": "", "tokens": 0}


def _pull_stats() -> Dict[str, Any]:
    try:
        from core.harness.team_harness import read_meta

        meta = read_meta() or {}
        return {
            "commit": str(meta.get("commit") or "")[:12],
            "pulled_at": meta.get("pulled_at"),
            "last_autosync_at": meta.get("last_autosync_at"),
            "branch": str(meta.get("branch") or ""),
        }
    except Exception:
        return {}


def _bloat_slice(proj: Mapping[str, Any]) -> Dict[str, Any]:
    bloat = proj.get("bloat_metrics") or {}
    if not isinstance(bloat, dict):
        return {}
    vs = bloat.get("vs_baseline") if isinstance(bloat.get("vs_baseline"), dict) else {}
    return {
        "loc": bloat.get("loc"),
        "new_files": bloat.get("new_files"),
        "new_deps": bloat.get("new_deps"),
        "delta_loc": vs.get("delta_loc"),
        "has_baseline": bool(vs.get("has_baseline")),
    }


def _repair_slice(proj: Mapping[str, Any]) -> Dict[str, Any]:
    last = proj.get("last_repair") if isinstance(proj.get("last_repair"), dict) else {}
    return {
        "repair_exhausted": bool(last.get("repair_exhausted")),
        "rounds": last.get("rounds"),
        "next": last.get("next") or "",
    }


def _style_slice(proj: Mapping[str, Any]) -> Dict[str, Any]:
    meta = proj.get("metadata") if isinstance(proj.get("metadata"), dict) else {}
    return {
        "output_style": str(proj.get("output_style") or meta.get("output_style") or ""),
        "factory_profile": str(proj.get("factory_profile") or meta.get("factory_profile") or ""),
    }
