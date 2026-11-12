"""Last Suite Profile exam summary ledger (claim stays false)."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from core.utils.paths import get_aiplat_home

_LOCKS: Dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
SUMMARY_SCHEMA = "eval.suite_exam_summary.v1"


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


def _ledger_path(*, workspace_id: str = "") -> Path:
    home = Path(get_aiplat_home())
    wid = str(workspace_id or "").strip()
    if wid:
        return home / "workspaces" / wid / "eval_exam_summaries.json"
    return home / "eval_exam_summaries" / "default.json"


def _load(path: Path) -> Dict[str, Any]:
    empty: Dict[str, Any] = {"schema": SUMMARY_SCHEMA, "by_profile_id": {}}
    if not path.is_file():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty
    if not isinstance(data, dict) or not isinstance(data.get("by_profile_id"), dict):
        return empty
    data.setdefault("schema", SUMMARY_SCHEMA)
    return data


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def record_suite_exam_summary(
    exam: Mapping[str, Any], *, workspace_id: str = ""
) -> Dict[str, Any]:
    """Upsert last exam summary for profile_id (callers wrap fail-soft)."""
    profile_id = str(exam.get("profile_id") or "").strip()
    if not profile_id:
        return {}
    counts = exam.get("counts") if isinstance(exam.get("counts"), Mapping) else {}
    summary = {
        "schema": SUMMARY_SCHEMA,
        "profile_id": profile_id,
        "subject_kind": str(exam.get("subject_kind") or "").strip(),
        "ok": bool(exam.get("ok")),
        "live": bool(exam.get("live")),
        "run_id": str(exam.get("run_id") or "").strip(),
        "executed_case_count": int(exam.get("executed_case_count") or 0),
        "manifest_case_count": int(exam.get("manifest_case_count") or 0),
        "pass": int(counts.get("pass") or 0),
        "fail": int(counts.get("fail") or 0),
        "error": int(counts.get("error") or 0),
        "inconclusive": int(counts.get("inconclusive") or 0),
        "claim_eligible": False,
        "accuracy_claim": False,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "error": str(exam.get("error") or "")[:300],
    }
    path = _ledger_path(workspace_id=workspace_id)
    with _lock_for(path):
        doc = _load(path)
        by = dict(doc.get("by_profile_id") or {})
        by[profile_id] = summary
        doc.update(
            {
                "by_profile_id": by,
                "schema": SUMMARY_SCHEMA,
                "workspace_id": str(workspace_id or "").strip(),
            }
        )
        _atomic_write(path, doc)
    return summary


def get_suite_exam_summary(
    profile_id: str, *, workspace_id: str = ""
) -> Optional[Dict[str, Any]]:
    pid = str(profile_id or "").strip()
    if not pid:
        return None
    path = _ledger_path(workspace_id=workspace_id)
    with _lock_for(path):
        raw = (_load(path).get("by_profile_id") or {}).get(pid)
    if not isinstance(raw, dict):
        return None
    out = dict(raw)
    out["claim_eligible"] = out["accuracy_claim"] = False
    return out
