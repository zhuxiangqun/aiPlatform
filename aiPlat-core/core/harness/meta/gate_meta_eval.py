"""Gate meta-evaluation — calibrate merge gates from measured JSONL (not vibes).

Append-only events under ``$AIPLAT_HOME/org/gate_meta/runs.jsonl``:
  - ``run``    — each physical/testability check outcome
  - ``skip``   — SKIP_PHYSICAL_GATES / SKIP_TESTABILITY bypass
  - ``appeal`` — human false-positive / mis-kill appeal

Window rates (default 30d) drive duty-board watch/block when thresholds breach.
Never invent rates below ``min_runs``. Production callers: check script,
pre-commit skip log, CoreFacade, collect_merge_gates_posture.
"""

from __future__ import annotations
from core.utils.paths import get_aiplat_home, get_aiplat_data_dir

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

_KINDS = frozenset({"run", "skip", "appeal"})

_DEFAULT_THRESHOLDS: Dict[str, float] = {
    "gate_meta_window_days": 30.0,
    "gate_meta_min_runs": 5.0,
    "gate_exemption_rate_watch": 0.15,
    "gate_exemption_rate_block": 0.35,
    "gate_skip_rate_watch": 0.05,
    "gate_skip_rate_block": 0.15,
    "gate_appeal_rate_watch": 0.10,
    "gate_appeal_rate_block": 0.25,
    # Informational — high block alone is not bad (legitimate vetoes).
    "gate_block_rate_watch": 0.50,
}


def gate_meta_dir() -> Path:
    """JSONL home — env AIPLAT_GATE_META_DIR overrides AIPLAT_HOME/org/gate_meta."""
    env = (os.getenv("AIPLAT_GATE_META_DIR") or "").strip()
    if env:
        return Path(env).expanduser()
    home = Path(get_aiplat_home())
    return home / "org" / "gate_meta"


def gate_meta_jsonl_path() -> Path:
    return gate_meta_dir() / "runs.jsonl"


def _persist_enabled() -> bool:
    flag = (os.getenv("AIPLAT_GATE_META_PERSIST") or "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None


def append_gate_event(event: Mapping[str, Any]) -> Optional[str]:
    """Append one event. Returns path or None on skip/failure."""
    if not _persist_enabled():
        return None
    kind = str(event.get("kind") or "").strip().lower()
    if kind not in _KINDS:
        logger.debug("gate_meta append skipped: bad kind=%r", kind)
        return None
    row = {k: v for k, v in dict(event).items() if v is not None}
    row["kind"] = kind
    row.setdefault("written_at", _now_iso())
    row.setdefault("ts", time.time())
    try:
        out_dir = gate_meta_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        path = gate_meta_jsonl_path()
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return str(path)
    except Exception as e:
        logger.debug("gate_meta append failed: %s", e, exc_info=True)
        return None


def record_gate_run(
    *,
    physical: Optional[Mapping[str, Any]] = None,
    testability: Optional[Mapping[str, Any]] = None,
    exit_blocked: bool = False,
    source: str = "check",
    staged: bool = False,
) -> Optional[str]:
    """Persist one gate check outcome (from check_physical_merge_gates)."""
    phys = dict(physical or {})
    tb = dict(testability or {})
    ex = phys.get("exemptions_applied") or []
    if not isinstance(ex, list):
        ex = []
    findings = phys.get("findings") or []
    codes: List[str] = []
    for f in findings:
        if isinstance(f, Mapping) and f.get("code"):
            codes.append(str(f["code"])[:80])
    for f in tb.get("findings") or []:
        if isinstance(f, Mapping) and f.get("code"):
            codes.append(str(f["code"])[:80])
    phys_ok = bool(phys.get("ok", True))
    phys_mode = str(phys.get("mode") or "")
    # would_block: findings that matter in block mode (even if currently warn)
    would_block = (not phys_ok) or (
        bool(findings) and phys_mode in ("warn", "block")
    )
    tb_ok = bool(tb.get("ok", True)) if tb else True
    return append_gate_event(
        {
            "kind": "run",
            "source": str(source or "check")[:40],
            "staged": bool(staged),
            "physical_ok": phys_ok,
            "physical_mode": phys_mode[:16],
            "physical_would_block": bool(would_block),
            "exemptions_applied": [str(x)[:64] for x in ex[:16]],
            "exemption_used": bool(ex),
            "testability_ok": tb_ok,
            "testability_mode": str(tb.get("mode") or "")[:16],
            "finding_codes": codes[:32],
            "exit_blocked": bool(exit_blocked),
            "profile": str(phys.get("profile") or "")[:40],
        }
    )


def record_gate_skip(
    *,
    env: str = "SKIP_PHYSICAL_GATES",
    gate: str = "physical",
    source: str = "pre-commit",
    note: str = "",
) -> Optional[str]:
    """Persist SKIP_* bypass (must be visible — not silent)."""
    return append_gate_event(
        {
            "kind": "skip",
            "source": str(source or "pre-commit")[:40],
            "gate": str(gate or "physical")[:40],
            "env": str(env or "SKIP_PHYSICAL_GATES")[:64],
            "note": str(note or "")[:200],
        }
    )


def record_gate_appeal(
    *,
    code: str,
    owner: str,
    note: str = "",
    gate: str = "physical",
    source: str = "manual",
) -> Optional[str]:
    """Persist false-positive / mis-kill appeal for meta calibration."""
    code_s = str(code or "").strip()
    owner_s = str(owner or "").strip()
    if not code_s or not owner_s:
        logger.debug("gate_meta appeal skipped: code and owner required")
        return None
    return append_gate_event(
        {
            "kind": "appeal",
            "source": str(source or "manual")[:40],
            "gate": str(gate or "physical")[:40],
            "code": code_s[:80],
            "owner": owner_s[:80],
            "note": str(note or "")[:300],
        }
    )


def list_gate_events(
    *,
    limit: int = 500,
    path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Read JSONL events (oldest→newest); returns last ``limit`` rows."""
    p = path or gate_meta_jsonl_path()
    if not p.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and str(obj.get("kind") or "") in _KINDS:
                rows.append(obj)
    except OSError:
        return []
    lim = max(1, min(int(limit or 500), 5000))
    return rows[-lim:]


def summarize_gate_meta(
    events: Optional[Sequence[Mapping[str, Any]]] = None,
    *,
    window_days: float = 30.0,
    min_runs: float = 5.0,
    now_ts: Optional[float] = None,
    thresholds: Optional[Mapping[str, float]] = None,
) -> Dict[str, Any]:
    """Fold JSONL → rates + severity (go|watch|block|unavailable).

    Rates (window):
      block_rate     = exit_blocked runs / n_runs
      exemption_rate = exemption_used runs / n_runs
      skip_rate      = n_skips / (n_runs + n_skips)
      appeal_rate    = n_appeals / n_runs  (0 if no runs)
    """
    thr = dict(_DEFAULT_THRESHOLDS)
    if isinstance(thresholds, Mapping):
        for k, v in thresholds.items():
            if k in thr and v is not None:
                try:
                    thr[k] = float(v)
                except (TypeError, ValueError):
                    continue
    wd = float(window_days if window_days is not None else thr["gate_meta_window_days"])
    mr = float(min_runs if min_runs is not None else thr["gate_meta_min_runs"])
    if events is None:
        events = list_gate_events(limit=2000)
    now = float(now_ts if now_ts is not None else time.time())
    cutoff = now - max(1.0, wd) * 86400.0

    runs: List[Mapping[str, Any]] = []
    skips: List[Mapping[str, Any]] = []
    appeals: List[Mapping[str, Any]] = []
    for ev in events or []:
        if not isinstance(ev, Mapping):
            continue
        ts = _parse_ts(ev.get("ts") or ev.get("written_at"))
        if ts is None or ts < cutoff:
            continue
        kind = str(ev.get("kind") or "")
        if kind == "run":
            runs.append(ev)
        elif kind == "skip":
            skips.append(ev)
        elif kind == "appeal":
            appeals.append(ev)

    n_runs = len(runs)
    n_skips = len(skips)
    n_appeals = len(appeals)
    n_blocked = sum(1 for r in runs if r.get("exit_blocked"))
    n_exempt = sum(1 for r in runs if r.get("exemption_used") or r.get("exemptions_applied"))
    denom_skip = n_runs + n_skips

    def _rate(num: int, den: int) -> Optional[float]:
        if den <= 0:
            return None
        return round(num / den, 4)

    block_rate = _rate(n_blocked, n_runs)
    exemption_rate = _rate(n_exempt, n_runs)
    skip_rate = _rate(n_skips, denom_skip)
    appeal_rate = _rate(n_appeals, n_runs) if n_runs > 0 else (0.0 if n_appeals == 0 else None)

    reasons: List[str] = []
    severity = "go"
    status = "ok"

    if n_runs < mr and n_skips == 0 and n_appeals == 0:
        return {
            "status": "unavailable",
            "severity": "unavailable",
            "window_days": wd,
            "min_runs": mr,
            "n_runs": n_runs,
            "n_skips": n_skips,
            "n_appeals": n_appeals,
            "n_blocked": n_blocked,
            "n_exempt": n_exempt,
            "block_rate": block_rate,
            "exemption_rate": exemption_rate,
            "skip_rate": skip_rate,
            "appeal_rate": appeal_rate,
            "reasons": [
                f"gate_meta_insufficient_runs={n_runs}<{int(mr)} — do not invent rates"
            ],
            "thresholds": {
                k: thr[k]
                for k in (
                    "gate_exemption_rate_watch",
                    "gate_exemption_rate_block",
                    "gate_skip_rate_watch",
                    "gate_skip_rate_block",
                    "gate_appeal_rate_watch",
                    "gate_appeal_rate_block",
                    "gate_block_rate_watch",
                )
            },
            "jsonl": str(gate_meta_jsonl_path()),
        }

    # When only skips/appeals exist without enough runs, still surface skip/appeal.
    if n_runs < mr:
        status = "sparse"
        reasons.append(f"gate_meta_sparse_runs={n_runs}<{int(mr)}")

    def _breach(rate: Optional[float], watch: float, block: float, label: str) -> None:
        nonlocal severity
        if rate is None:
            return
        if rate >= block:
            severity = "block"
            reasons.append(f"{label}={rate}>={block}")
        elif rate >= watch:
            if severity != "block":
                severity = "watch"
            reasons.append(f"{label}={rate}>={watch}")

    _breach(
        exemption_rate,
        thr["gate_exemption_rate_watch"],
        thr["gate_exemption_rate_block"],
        "exemption_rate",
    )
    _breach(
        skip_rate,
        thr["gate_skip_rate_watch"],
        thr["gate_skip_rate_block"],
        "skip_rate",
    )
    _breach(
        appeal_rate,
        thr["gate_appeal_rate_watch"],
        thr["gate_appeal_rate_block"],
        "appeal_rate",
    )
    # block_rate: watch only (informational — high veto may be healthy)
    if (
        block_rate is not None
        and block_rate >= thr["gate_block_rate_watch"]
        and severity == "go"
    ):
        severity = "watch"
        reasons.append(
            f"block_rate={block_rate}>={thr['gate_block_rate_watch']} (informational)"
        )

    if not reasons and severity == "go":
        reasons.append("gate_meta_rates_in_band")

    return {
        "status": status,
        "severity": severity,
        "window_days": wd,
        "min_runs": mr,
        "n_runs": n_runs,
        "n_skips": n_skips,
        "n_appeals": n_appeals,
        "n_blocked": n_blocked,
        "n_exempt": n_exempt,
        "block_rate": block_rate,
        "exemption_rate": exemption_rate,
        "skip_rate": skip_rate,
        "appeal_rate": appeal_rate,
        "reasons": reasons,
        "thresholds": {
            k: thr[k]
            for k in (
                "gate_exemption_rate_watch",
                "gate_exemption_rate_block",
                "gate_skip_rate_watch",
                "gate_skip_rate_block",
                "gate_appeal_rate_watch",
                "gate_appeal_rate_block",
                "gate_block_rate_watch",
            )
        },
        "jsonl": str(gate_meta_jsonl_path()),
    }


def assess_gate_meta(
    *,
    events: Optional[Sequence[Mapping[str, Any]]] = None,
    thresholds: Optional[Mapping[str, float]] = None,
    now_ts: Optional[float] = None,
) -> Dict[str, Any]:
    """Summarize with optional duty-board thresholds (no reverse import)."""
    thr = load_gate_meta_thresholds_from_duty(thresholds)
    return summarize_gate_meta(
        events,
        window_days=thr["gate_meta_window_days"],
        min_runs=thr["gate_meta_min_runs"],
        now_ts=now_ts,
        thresholds=thr,
    )


def load_gate_meta_thresholds_from_duty(
    duty_thr: Optional[Mapping[str, float]] = None,
) -> Dict[str, float]:
    """Merge duty-board floats into gate-meta defaults (for posture wiring)."""
    out = dict(_DEFAULT_THRESHOLDS)
    if isinstance(duty_thr, Mapping):
        for k in out:
            if k in duty_thr and duty_thr[k] is not None:
                try:
                    out[k] = float(duty_thr[k])
                except (TypeError, ValueError):
                    continue
    return out
