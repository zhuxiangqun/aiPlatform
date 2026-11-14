"""P3.1 Case Pack calibration — difficulty labels + judge ticket loop.

Engineering calibration only. Never opens accuracy_claim / claim_eligible.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.case_pack_registry import (
    PackRegistryError,
    assert_pack_acl,
)
from core.utils.paths import get_aiplat_home

VALID_DIFFICULTY = frozenset({"easy", "medium", "hard"})
VALID_TICKET_STATUS = frozenset({"open", "in_progress", "closed"})


class CaseCalibrationError(ValueError):
    """Difficulty / judge calibration failure."""


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:  # noqa: cleanup-best-effort
                pass


def _calib_root(workspace_id: str) -> Path:
    wid = str(workspace_id or "").strip()
    if not wid:
        raise CaseCalibrationError("workspace_id required")
    return Path(get_aiplat_home()) / "workspaces" / wid / "eval_packs" / "calibration"


def _ticket_path(workspace_id: str, ticket_id: str) -> Path:
    tid = str(ticket_id or "").strip().replace("/", "_")
    if not tid:
        raise CaseCalibrationError("ticket_id required")
    return _calib_root(workspace_id) / "judge_tickets" / f"{tid}.json"


def _difficulty_path(workspace_id: str, pack_id: str, version: str) -> Path:
    pid = str(pack_id or "").strip().replace("/", "_")
    ver = str(version or "").strip().replace("/", "_")
    if not pid or not ver:
        raise CaseCalibrationError("pack_id and version required")
    return _calib_root(workspace_id) / "difficulty" / f"{pid}__{ver}.json"


def apply_difficulty_labels(
    cases: Sequence[Mapping[str, Any]],
    labels: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Apply human difficulty labels; mark engineering-calibrated (claim closed).

    Args:
        cases: 用例列表。
        labels: labels 参数。
    """
    by_id: Dict[str, str] = {}
    for i, lab in enumerate(labels or []):
        if not isinstance(lab, Mapping):
            raise CaseCalibrationError(f"labels[{i}] must be object")
        cid = str(lab.get("case_id") or "").strip()
        diff = str(lab.get("difficulty") or "").strip().lower()
        if not cid:
            raise CaseCalibrationError(f"labels[{i}].case_id required")
        if diff not in VALID_DIFFICULTY:
            raise CaseCalibrationError(
                f"labels[{i}].difficulty must be one of {sorted(VALID_DIFFICULTY)}"
            )
        by_id[cid] = diff
    if not by_id:
        raise CaseCalibrationError("labels required")
    out: List[Dict[str, Any]] = []
    hit = 0
    for c in cases:
        row = dict(c)
        cid = str(row.get("case_id") or "")
        if cid in by_id:
            hit += 1
            row["difficulty"] = by_id[cid]
            prev = row.get("difficulty_proposal")
            prev_d = dict(prev) if isinstance(prev, Mapping) else {}
            row["difficulty_proposal"] = {
                **prev_d,
                "method": "human_label_v1",
                "calibrated": True,
                "accuracy_claim": False,
                "label_source": "human",
            }
        out.append(row)
    if hit == 0:
        raise CaseCalibrationError("no labels matched case_id")
    return out


def save_difficulty_calibration_record(
    *,
    workspace_id: str,
    pack_id: str,
    version: str,
    labels: Sequence[Mapping[str, Any]],
    rater: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """Persist label record under workspace calibration store.

    Args:
        workspace_id: workspace 标识。
        pack_id: pack 标识。
        version: 版本号。
        labels: labels 参数。
        rater: rater 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    wid = str(workspace_id or "").strip()
    assert_pack_acl(
        scope="workspace",
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
        write=True,
    )
    rec = {
        "schema": "eval.difficulty_calibration.v1",
        "pack_id": str(pack_id).strip(),
        "version": str(version).strip(),
        "workspace_id": wid,
        "rater": str(rater or ""),
        "labels": [dict(x) for x in labels],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "calibrated": True,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": "engineering difficulty labels only — not an accuracy claim",
    }
    path = _difficulty_path(wid, pack_id, version)
    _atomic_write_json(path, rec)
    return {**rec, "ok": True, "path": str(path)}


def create_judge_ticket(
    *,
    workspace_id: str,
    pack_id: str,
    version: str,
    sample_case_ids: Optional[Sequence[str]] = None,
    notes: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """Create + persist an open judge calibration ticket.

    Args:
        workspace_id: workspace 标识。
        pack_id: pack 标识。
        version: 版本号。
        sample_case_ids: sample_case_ids 参数。
        notes: notes 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    wid = str(workspace_id or "").strip()
    pid = str(pack_id or "").strip()
    ver = str(version or "").strip()
    if not wid or not pid or not ver:
        raise CaseCalibrationError("workspace_id, pack_id, version required")
    assert_pack_acl(
        scope="workspace",
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
        write=True,
    )
    ids = [str(x).strip() for x in (sample_case_ids or []) if str(x).strip()]
    ticket_id = f"jcal-{uuid.uuid4().hex[:12]}"
    ticket = {
        "ok": True,
        "ticket_id": ticket_id,
        "ticket_kind": "judge_calibration",
        "schema": "eval.judge_calibration_ticket.v1",
        "pack_id": pid,
        "version": ver,
        "workspace_id": wid,
        "sample_case_ids": ids,
        "status": "open",
        "notes": str(notes or ""),
        "ratings": [],
        "agreement": None,
        "calibrated": False,
        "claim_eligible": False,
        "accuracy_claim": False,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "closed_at": None,
        "honesty": (
            "ticket loop for engineering judge agreement — "
            "does not unlock accuracy_claim"
        ),
    }
    _atomic_write_json(_ticket_path(wid, ticket_id), ticket)
    return ticket


def load_judge_ticket(
    *,
    workspace_id: str,
    ticket_id: str,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """加载 judge_ticket。

    Args:
        workspace_id: workspace 标识。
        ticket_id: ticket 标识。
        caller_workspace_id: caller_workspace 标识。
    """
    wid = str(workspace_id or "").strip()
    assert_pack_acl(
        scope="workspace",
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
        write=False,
    )
    path = _ticket_path(wid, ticket_id)
    if not path.is_file():
        raise CaseCalibrationError(f"ticket not found: {ticket_id}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise CaseCalibrationError(f"ticket corrupt: {e}") from e
    if not isinstance(raw, dict):
        raise CaseCalibrationError("ticket root must be object")
    return raw


def compute_rating_agreement(
    ratings: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Pairwise same-score agreement per case_id (engineering metric).

    Args:
        ratings: ratings 参数。
    """
    by_case: Dict[str, List[Any]] = {}
    for i, r in enumerate(ratings or []):
        if not isinstance(r, Mapping):
            raise CaseCalibrationError(f"ratings[{i}] must be object")
        cid = str(r.get("case_id") or "").strip()
        if not cid:
            raise CaseCalibrationError(f"ratings[{i}].case_id required")
        if "score" not in r:
            raise CaseCalibrationError(f"ratings[{i}].score required")
        by_case.setdefault(cid, []).append(r.get("score"))
    case_rows = []
    agrees = 0
    pairs = 0
    for cid, scores in sorted(by_case.items()):
        n = len(scores)
        if n < 2:
            case_rows.append(
                {"case_id": cid, "n_raters": n, "agreement": None, "pairs": 0}
            )
            continue
        local_agree = 0
        local_pairs = 0
        for i in range(n):
            for j in range(i + 1, n):
                local_pairs += 1
                if scores[i] == scores[j]:
                    local_agree += 1
        pairs += local_pairs
        agrees += local_agree
        case_rows.append(
            {
                "case_id": cid,
                "n_raters": n,
                "pairs": local_pairs,
                "agreement": (local_agree / local_pairs) if local_pairs else None,
            }
        )
    overall = (agrees / pairs) if pairs else None
    return {
        "n_cases": len(by_case),
        "n_ratings": len(list(ratings or [])),
        "pairs": pairs,
        "agreement": overall,
        "by_case": case_rows,
        "calibrated": False,
        "accuracy_claim": False,
    }


def record_judge_ratings(
    *,
    workspace_id: str,
    ticket_id: str,
    ratings: Sequence[Mapping[str, Any]],
    rater: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """Append ratings to an open/in_progress ticket; recompute agreement.

    Args:
        workspace_id: workspace 标识。
        ticket_id: ticket 标识。
        ratings: ratings 参数。
        rater: rater 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    wid = str(workspace_id or "").strip()
    assert_pack_acl(
        scope="workspace",
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
        write=True,
    )
    ticket = load_judge_ticket(
        workspace_id=wid,
        ticket_id=ticket_id,
        caller_workspace_id=caller_workspace_id or wid,
    )
    st = str(ticket.get("status") or "")
    if st == "closed":
        raise CaseCalibrationError("cannot rate a closed ticket")
    if st not in ("open", "in_progress"):
        raise CaseCalibrationError(f"invalid ticket status={st!r}")
    cleaned: List[Dict[str, Any]] = []
    for i, r in enumerate(ratings or []):
        if not isinstance(r, Mapping):
            raise CaseCalibrationError(f"ratings[{i}] must be object")
        cid = str(r.get("case_id") or "").strip()
        if not cid:
            raise CaseCalibrationError(f"ratings[{i}].case_id required")
        if "score" not in r:
            raise CaseCalibrationError(f"ratings[{i}].score required")
        row = {
            "case_id": cid,
            "score": r.get("score"),
            "rater": str(r.get("rater") or rater or ""),
            "notes": str(r.get("notes") or ""),
        }
        cleaned.append(row)
    if not cleaned:
        raise CaseCalibrationError("ratings required")
    existing = list(ticket.get("ratings") or [])
    existing.extend(cleaned)
    ticket["ratings"] = existing
    ticket["status"] = "in_progress"
    ticket["agreement"] = compute_rating_agreement(existing)
    ticket["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ticket["claim_eligible"] = False
    ticket["accuracy_claim"] = False
    _atomic_write_json(_ticket_path(wid, ticket_id), ticket)
    return ticket


def close_judge_ticket(
    *,
    workspace_id: str,
    ticket_id: str,
    notes: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """Close ticket after ratings; still claim closed (engineering only).

    Args:
        workspace_id: workspace 标识。
        ticket_id: ticket 标识。
        notes: notes 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    wid = str(workspace_id or "").strip()
    assert_pack_acl(
        scope="workspace",
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
        write=True,
    )
    ticket = load_judge_ticket(
        workspace_id=wid,
        ticket_id=ticket_id,
        caller_workspace_id=caller_workspace_id or wid,
    )
    if str(ticket.get("status") or "") == "closed":
        raise CaseCalibrationError("ticket already closed")
    ratings = list(ticket.get("ratings") or [])
    if not ratings:
        raise CaseCalibrationError("cannot close ticket without ratings")
    agreement = compute_rating_agreement(ratings)
    ticket["agreement"] = agreement
    ticket["status"] = "closed"
    ticket["calibrated"] = True  # engineering flag only
    ticket["closed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if notes:
        prev = str(ticket.get("notes") or "")
        ticket["notes"] = f"{prev}\n{notes}".strip() if prev else str(notes)
    ticket["claim_eligible"] = False
    ticket["accuracy_claim"] = False
    ticket["honesty"] = (
        "closed engineering calibration — agreement recorded; "
        "accuracy_claim remains false"
    )
    _atomic_write_json(_ticket_path(wid, ticket_id), ticket)
    return ticket
