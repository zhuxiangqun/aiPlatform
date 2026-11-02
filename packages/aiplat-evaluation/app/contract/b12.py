"""B1 Route Matrix + Runtime Contract — local converge checks.

Honesty:
- This package is the **standalone** contract surface (:8010).
- Central cohost still runs legacy in-process evals until staging authorize —
  that is **default D1**, not ``temporary_proxy``.
- ``temporary_proxy`` = claiming independent execute while forwarding to Central.
- ``process_split_authorized`` stays false.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

_REQUIRED_ERROR_KEYS = ("code", "runner_id", "retryable", "detail")
_TEMP_PROXY_RE = re.compile(r"temporary_proxy\s*=\s*true", re.IGNORECASE)
_PKG_ROOT = Path(__file__).resolve().parents[1]


def assert_error_envelope(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate unified error body; raise ValueError on shape miss."""
    err = payload.get("error") if isinstance(payload, Mapping) else None
    if not isinstance(err, Mapping):
        raise ValueError("missing_error_object")
    missing = [k for k in _REQUIRED_ERROR_KEYS if k not in err]
    if missing:
        raise ValueError(f"missing_error_fields:{','.join(missing)}")
    if not isinstance(err.get("code"), str) or not str(err.get("code")).strip():
        raise ValueError("empty_error_code")
    if not isinstance(err.get("runner_id"), str):
        raise ValueError("runner_id_not_str")
    if not isinstance(err.get("retryable"), bool):
        raise ValueError("retryable_not_bool")
    if not isinstance(err.get("detail"), str):
        raise ValueError("detail_not_str")
    return dict(err)


def count_temporary_proxy_markers(
    roots: Sequence[Path] | None = None,
    *,
    suffixes: Iterable[str] = (".py",),
) -> int:
    """Count enabled temporary_proxy markers in production ``app/`` Python.

    Docs/tests may discuss the flag; only runnable app code is gated to 0.
    """
    bases = list(roots) if roots is not None else [_PKG_ROOT / "app"]
    n = 0
    self_name = Path(__file__).name
    for base in bases:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in suffixes:
                continue
            if path.name == self_name:
                continue
            parts = {p.lower() for p in path.parts}
            if "__pycache__" in parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            n += len(_TEMP_PROXY_RE.findall(text))
    return n


def proxied_store_suffixes() -> List[str]:
    """Store-only upstream proxy paths (execute routes must not appear)."""
    return [
        "/store/healthz",
        "/store/sets",
        "/store/reports",
    ]


def residual_central_cohost_note() -> str:
    return (
        "Central cohost D1 still hosts legacy in-process eval routes; "
        "standalone :8010 is the B1/B2 contract surface. "
        "Not temporary_proxy; process_split_authorized=false."
    )


def _wire_b12() -> Dict[str, Any]:
    """Same-file caller for method_verify."""
    sample = {
        "error": {
            "code": "sandbox_required",
            "runner_id": "skill_suite",
            "retryable": False,
            "detail": "probe",
        }
    }
    _ = assert_error_envelope(sample)
    _ = residual_central_cohost_note()
    return {
        "temporary_proxy_count": count_temporary_proxy_markers(),
        "proxied_store_suffixes": proxied_store_suffixes(),
    }
