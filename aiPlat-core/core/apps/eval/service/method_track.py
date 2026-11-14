"""Eval Method track — Arena / G2b / S1 stay methods (ADR refuse object_type).

Authority: ADR-EVAL-CAPABILITY-CASE-PACK-V1 §落地顺序 step 6 + decision table
「Arena/G2b/S1 升为 object_type → 拒绝」。
This module is the enforceable catalog + Subject refuse gate. No SubjectAdapter.
"""
from __future__ import annotations

from typing import Any, Dict, List

METHOD_TRACK_SCHEMA = "eval.method_track.v1"

# Canonical method kinds (not Subjects / not OBJECT_TYPES).
METHOD_KINDS = frozenset(
    {
        "arena",
        "g2b",
        "s1",
    }
)

_METHOD_ROWS: Dict[str, Dict[str, Any]] = {
    "arena": {
        "method_kind": "arena",
        "track": "method",
        "object_type_eligible": False,
        "subject_adapter_eligible": False,
        "claim_eligible": False,
        "default_evidence_level": "smoke",
        "honesty": (
            "Arena length-heuristic is smoke only; blind preference is Method, "
            "not a SubjectAdapter / OBJECT_TYPES member."
        ),
        "source_refs": ["package:arena", "eval-object-cards/05-arena.md"],
    },
    "g2b": {
        "method_kind": "g2b",
        "track": "method",
        "object_type_eligible": False,
        "subject_adapter_eligible": False,
        "claim_eligible": False,
        "default_evidence_level": "human_double_blind",
        "honesty": (
            "G2b is human double-blind Method (L1 independent); "
            "not a SubjectAdapter / OBJECT_TYPES member."
        ),
        "source_refs": ["core/apps/eval/service/g2b.py", "ADR-EVAL-CAPABILITY-CASE-PACK-V1"],
    },
    "s1": {
        "method_kind": "s1",
        "track": "method",
        "object_type_eligible": False,
        "subject_adapter_eligible": False,
        "claim_eligible": False,
        "default_evidence_level": "redteam_pack",
        "honesty": (
            "S1 redteam is Method/attack pack; not a SubjectAdapter / OBJECT_TYPES member."
        ),
        "source_refs": ["security_s1_disclosure", "ADR-EVAL-CAPABILITY-CASE-PACK-V1"],
    },
}


class MethodTrackError(ValueError):
    """Method kind misused as Subject / object_type (fail closed)."""


def list_method_kinds() -> List[str]:
    """列出 method_kinds。
    """
    return sorted(METHOD_KINDS)


def is_method_kind(kind: str) -> bool:
    """is_method_kind。

    Args:
        kind: kind 参数。
    """
    return (kind or "").strip().lower() in METHOD_KINDS


def method_catalog() -> List[Dict[str, Any]]:
    """method_catalog。
    """
    rows: List[Dict[str, Any]] = []
    for kind in list_method_kinds():
        row = dict(_METHOD_ROWS[kind])
        row["schema"] = METHOD_TRACK_SCHEMA
        rows.append(row)
    return rows


def assert_not_subject_method(kind: str) -> None:
    """Fail closed when a Method kind is requested as SubjectAdapter.

    Args:
        kind: kind 参数。
    """
    k = (kind or "").strip().lower()
    if k in METHOD_KINDS:
        raise MethodTrackError(f"method_track_not_subject:{k}")


def assert_subject_kinds_exclude_methods(subject_kinds: List[str]) -> Dict[str, Any]:
    """Validate a subject kind list never contains Method kinds.

    Args:
        subject_kinds: subject_kinds 参数。
    """
    bad = sorted({(k or "").strip().lower() for k in subject_kinds} & METHOD_KINDS)
    return {
        "schema": METHOD_TRACK_SCHEMA,
        "ok": not bad,
        "errors": [f"method_registered_as_subject:{k}" for k in bad],
        "method_kinds": list_method_kinds(),
        "claim_eligible": False,
    }
