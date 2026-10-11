"""Organization harness metrics — Amdahl/J-curve dark ledger.

Pure aggregator: no parallel store. Consumes pipeline run events, HITL audit,
approval_requests, and code_review_gold JSONL reports (P/R + P0 miss).

Production callers: CoreFacade.org_harness_status, GET /governance/org-harness,
governance eval_observability (optional slice).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Defaults match historical hardcoded bands (docs / duty_board seed).
_DEFAULT_DUTY_THRESHOLDS: Dict[str, float] = {
    "p0_miss_rate_block": 0.2,
    "serial_ratio_watch": 0.2,
    "serial_ratio_high": 0.4,
    "approval_pending_watch": 5.0,
    "approval_latency_sec_watch": 3600.0,
    "hitl_rejection_rate_watch": 0.3,
    "howl_interventions_watch": 20.0,
}

# Event types that open / close a serial human wait (pipeline_run_events)
_HITL_OPEN = frozenset({
    "hitl_requested",
    "stage_paused",
    "pipeline_paused",
    "approval_required",
})
_HITL_CLOSE = frozenset({
    "hitl_resolved",
    "hitl_approved",
    "hitl_rejected",
    "pipeline_resumed",
    "stage_started",  # soft close after pause when resume continues
})

# In-state _hitl_audit action names
_AUDIT_OPEN = frozenset({
    "hitl_requested",
    "escalate_to_hitl",
    "schema_gate_paused",
    "hitl_pause",
})
_AUDIT_CLOSE = frozenset({
    "hitl_approved",
    "hitl_rejected",
    "hitl_resolved",
    "hitl_human_input",
    "schema_gate_resumed",
})


def _ts(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            try:
                from datetime import datetime

                return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
            except Exception:
                return None
    # datetime-like
    try:
        return float(v.timestamp())  # type: ignore[attr-defined]
    except Exception:
        return None


def _first_ts(*vals: Any) -> Optional[float]:
    """Pick first parseable timestamp; 0.0 is valid (do not use `or`)."""
    for v in vals:
        if v is None or v == "":
            continue
        t = _ts(v)
        if t is not None:
            return t
    return None


def _pair_waits(
    opens: List[Dict[str, Any]],
    closes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Greedy pair open→next close with t_close >= t_open."""
    episodes: List[Dict[str, Any]] = []
    used: set = set()
    for op in opens:
        t0 = _ts(op.get("t"))
        if t0 is None:
            continue
        best_i = -1
        best_t: Optional[float] = None
        for i, cl in enumerate(closes):
            if i in used:
                continue
            t1 = _ts(cl.get("t"))
            if t1 is None or t1 < t0:
                continue
            if best_t is None or t1 < best_t:
                best_t = t1
                best_i = i
        if best_i < 0 or best_t is None:
            episodes.append({
                "open_kind": op.get("kind"),
                "close_kind": None,
                "wait_sec": None,
                "open_at": t0,
                "stage_id": op.get("stage_id") or "",
                "unresolved": True,
            })
            continue
        used.add(best_i)
        episodes.append({
            "open_kind": op.get("kind"),
            "close_kind": closes[best_i].get("kind"),
            "wait_sec": round(best_t - t0, 3),
            "open_at": t0,
            "close_at": best_t,
            "stage_id": op.get("stage_id") or closes[best_i].get("stage_id") or "",
            "unresolved": False,
        })
    return episodes


def summarize_run_events(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Fold pipeline_run_events → HITL wait episodes + Amdahl-ish ratio."""
    opens: List[Dict[str, Any]] = []
    closes: List[Dict[str, Any]] = []
    times: List[float] = []
    by_type: Dict[str, int] = {}
    for e in events or []:
        if not isinstance(e, dict):
            continue
        et = str(e.get("event_type") or e.get("type") or "").strip()
        if not et:
            continue
        by_type[et] = by_type.get(et, 0) + 1
        t = _first_ts(e.get("created_at"), e.get("timestamp"), e.get("t"))
        if t is not None:
            times.append(t)
        row = {"kind": et, "t": t, "stage_id": str(e.get("stage_id") or "")}
        if et in _HITL_OPEN:
            opens.append(row)
        elif et in _HITL_CLOSE:
            closes.append(row)

    episodes = _pair_waits(opens, closes)
    waits = [float(ep["wait_sec"]) for ep in episodes if ep.get("wait_sec") is not None]
    serial = round(sum(waits), 3) if waits else 0.0
    wall = round(max(times) - min(times), 3) if len(times) >= 2 else None
    ratio = round(serial / wall, 4) if wall and wall > 0 else None
    return {
        "event_count": len(events or []),
        "by_type": by_type,
        "hitl_open_count": len(opens),
        "hitl_close_count": len(closes),
        "hitl_episodes": episodes,
        "hitl_wait_sec_total": serial,
        "hitl_wait_sec_avg": round(sum(waits) / len(waits), 3) if waits else None,
        "wall_sec": wall,
        "serial_ratio": ratio,  # HITL wait / observed wall (Amdahl proxy)
        "open_unresolved": sum(1 for ep in episodes if ep.get("wait_sec") is None),
    }


def summarize_hitl_audit(audit: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Fold state['_hitl_audit'] rows into wait episodes."""
    opens: List[Dict[str, Any]] = []
    closes: List[Dict[str, Any]] = []
    for row in audit or []:
        if not isinstance(row, dict):
            continue
        action = str(row.get("action") or "").strip()
        t = _ts(row.get("timestamp") or row.get("t"))
        item = {"kind": action, "t": t, "stage_id": str(row.get("detail") or "")[:80]}
        if action in _AUDIT_CLOSE:
            closes.append(item)
        elif action in _AUDIT_OPEN:
            opens.append(item)
    episodes = _pair_waits(opens, closes)
    waits = [float(ep["wait_sec"]) for ep in episodes if ep.get("wait_sec") is not None]
    return {
        "audit_count": len(audit or []),
        "hitl_episodes": episodes,
        "hitl_wait_sec_total": round(sum(waits), 3) if waits else 0.0,
        "hitl_wait_sec_avg": round(sum(waits) / len(waits), 3) if waits else None,
        "open_unresolved": sum(1 for ep in episodes if ep.get("wait_sec") is None),
    }


def summarize_approvals(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Approval request latency + counts (PolicyGate dark ledger)."""
    by_status: Dict[str, int] = {}
    latencies: List[float] = []
    per_run: Dict[str, int] = {}
    pending = 0
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        st = str(rec.get("status") or "unknown").lower()
        by_status[st] = by_status.get(st, 0) + 1
        if st == "pending":
            pending += 1
        t0 = _ts(rec.get("created_at"))
        t1_src = rec.get("updated_at")
        if t1_src is None:
            result = rec.get("result")
            if isinstance(result, dict):
                t1_src = result.get("timestamp")
        t1 = _ts(t1_src)
        if t0 is not None and t1 is not None and st not in ("pending",):
            latencies.append(max(0.0, t1 - t0))
        meta = rec.get("metadata") if isinstance(rec.get("metadata"), dict) else {}
        rid = str(rec.get("run_id") or meta.get("run_id") or "").strip()
        if rid:
            per_run[rid] = per_run.get(rid, 0) + 1
    avg_lat = round(sum(latencies) / len(latencies), 3) if latencies else None
    per_run_vals = list(per_run.values())
    return {
        "approval_count": len(records or []),
        "pending": pending,
        "by_status": by_status,
        "avg_latency_sec": avg_lat,
        "p95_latency_sec": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 3) if len(latencies) >= 2 else avg_lat,
        "runs_with_approvals": len(per_run),
        "avg_approvals_per_run": round(sum(per_run_vals) / len(per_run_vals), 3) if per_run_vals else None,
    }


def _metric_delta(cur: Any, prev: Any) -> Optional[float]:
    if cur is None or prev is None:
        return None
    try:
        return round(float(cur) - float(prev), 4)
    except (TypeError, ValueError):
        return None


def _gold_trend_points(rows: Sequence[Dict[str, Any]], *, limit: int = 20) -> List[Dict[str, Any]]:
    """Last N gold reports as plottable points (reuse JSONL; no parallel store)."""
    pts: List[Dict[str, Any]] = []
    for r in list(rows)[-max(1, int(limit or 20)) :]:
        if not isinstance(r, dict):
            continue
        pts.append(
            {
                "written_at": r.get("written_at"),
                "precision": r.get("precision"),
                "recall": r.get("recall"),
                "p0_recall": r.get("p0_recall"),
                "avg_comment_count": r.get("avg_comment_count"),
                "elapsed_sec": r.get("elapsed_sec"),
                "profile": r.get("profile"),
            }
        )
    return pts


def _gold_trend_summary(trend: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Compact first→last direction for duty board (informational; verdict stays on regressing)."""
    pts = [p for p in (trend or []) if isinstance(p, dict)]
    if not pts:
        return {"n": 0, "direction": "unavailable", "first": None, "last": None}
    first, last = pts[0], pts[-1]
    direction = "flat"
    try:
        a = first.get("p0_recall")
        b = last.get("p0_recall")
        if a is not None and b is not None:
            d = float(b) - float(a)
            if d < -0.02:
                direction = "down"
            elif d > 0.02:
                direction = "up"
        elif last.get("precision") is not None and first.get("precision") is not None:
            d = float(last["precision"]) - float(first["precision"])
            if d < -0.02:
                direction = "down"
            elif d > 0.02:
                direction = "up"
    except (TypeError, ValueError):
        direction = "flat"
    return {
        "n": len(pts),
        "direction": direction,
        "first": {
            "precision": first.get("precision"),
            "recall": first.get("recall"),
            "p0_recall": first.get("p0_recall"),
            "written_at": first.get("written_at"),
        },
        "last": {
            "precision": last.get("precision"),
            "recall": last.get("recall"),
            "p0_recall": last.get("p0_recall"),
            "written_at": last.get("written_at"),
        },
    }


def summarize_gold_regression(reports: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Fold code_review_gold JSONL reports → P/R trend + P0 miss + four-metric card.

    p0_miss_rate = 1 - latest.p0_recall (gold P0 漏检代理；无平行库).
    ``trend`` = last N points for Governance strip; ``trend_summary`` = first→last direction.
    """
    rows = [r for r in (reports or []) if isinstance(r, dict)]
    if not rows:
        return {
            "report_count": 0,
            "latest": None,
            "delta_vs_prev": None,
            "p0_miss_rate": None,
            "regressing": False,
            "harness_factor_delta": {},
            "trend": [],
            "trend_summary": {"n": 0, "direction": "unavailable", "first": None, "last": None},
        }
    latest = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else None
    p0 = latest.get("p0_recall")
    miss: Optional[float] = None
    if p0 is not None:
        try:
            miss = round(max(0.0, 1.0 - float(p0)), 4)
        except (TypeError, ValueError):
            miss = None
    delta = None
    if prev is not None:
        delta = {
            "precision": _metric_delta(latest.get("precision"), prev.get("precision")),
            "recall": _metric_delta(latest.get("recall"), prev.get("recall")),
            "p0_recall": _metric_delta(latest.get("p0_recall"), prev.get("p0_recall")),
            "avg_comment_count": _metric_delta(
                latest.get("avg_comment_count"), prev.get("avg_comment_count"),
            ),
            "elapsed_sec": _metric_delta(latest.get("elapsed_sec"), prev.get("elapsed_sec")),
        }
    regressing = bool(
        delta
        and (
            (delta.get("precision") is not None and float(delta["precision"]) < -0.02)
            or (delta.get("p0_recall") is not None and float(delta["p0_recall"]) < -0.02)
            or (delta.get("recall") is not None and float(delta["recall"]) < -0.02)
        )
    )
    factor_delta: Dict[str, Any] = {}
    try:
        from core.harness.evaluation.harness_factors import harness_factors_delta

        factor_delta = harness_factors_delta(
            latest.get("harness_factors") if isinstance(latest.get("harness_factors"), dict) else {},
            (prev or {}).get("harness_factors") if isinstance((prev or {}).get("harness_factors"), dict) else {},
        )
    except Exception:
        factor_delta = {}
    trend = _gold_trend_points(rows, limit=20)
    return {
        "report_count": len(rows),
        "latest": {
            "precision": latest.get("precision"),
            "recall": latest.get("recall"),
            "p0_recall": latest.get("p0_recall"),
            "novel_count": latest.get("novel_count"),
            "avg_comment_count": latest.get("avg_comment_count"),
            "elapsed_sec": latest.get("elapsed_sec"),
            "profile": latest.get("profile"),
            "written_at": latest.get("written_at"),
            "case_count": len(latest.get("case_ids") or []) or latest.get("case_count"),
            "harness_factors": latest.get("harness_factors"),
        },
        "delta_vs_prev": delta,
        "p0_miss_rate": miss,
        "regressing": regressing,
        "harness_factor_delta": factor_delta,
        "trend": trend,
        "trend_summary": _gold_trend_summary(trend),
    }


def _duty_seed_path() -> Path:
    # org_harness_metrics.py → meta → harness → core → aiPlat-core/workspace_seeds
    return (
        Path(__file__).resolve().parents[3]
        / "workspace_seeds"
        / "org"
        / "duty_board.yaml"
    )


def _coerce_threshold(raw: Any, default: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


_DEFAULT_DUTY_PLAYBOOK: Dict[str, List[str]] = {
    "go": [
        "Gold match-only (limit=5) before each release; confirm P/R/P0 on duty board",
        "Keep org-harness on the board; re-check gold after model/harness changes",
    ],
    "watch": [
        "Inspect serial_ratio / approval_pending / HITL / Howl — clear friction first",
        "Run Gold match-only; treat Δ P0 down as watch→block candidate",
    ],
    "block": [
        "Do not release / do not upgrade model",
        "Run Gold match-only + inspect p0_miss_rate and gold_regressing",
    ],
    "unavailable": [
        "bash scripts/ops_harness_ready_check.sh",
        "Gold match-only; never invent success_rate",
    ],
}


def _load_duty_board_raw(
    *,
    override: Optional[Mapping[str, Any]] = None,
) -> Tuple[Optional[Mapping[str, Any]], str]:
    """Shared YAML load for thresholds + playbook."""
    if isinstance(override, Mapping) and override:
        return override, "override"
    candidates: List[Path] = []
    env_path = (os.getenv("AIPLAT_DUTY_BOARD_CONFIG") or "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())
    home = Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))
    candidates.append(home / "org" / "duty_board.yaml")
    candidates.append(_duty_seed_path())
    for path in candidates:
        if not path.is_file():
            continue
        try:
            import yaml

            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(data, Mapping):
                return data, str(path)
        except Exception as e:
            logger.debug("duty_board load skipped %s: %s", path, e)
    return None, "defaults"


def load_duty_board_thresholds(
    *,
    override: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, float], str]:
    """Load duty-board bands (config-driven; never invent success_rate).

    Priority:
      1. ``override`` mapping (tests / caller)
      2. ``AIPLAT_DUTY_BOARD_CONFIG`` path
      3. ``$AIPLAT_HOME/org/duty_board.yaml``
      4. workspace seed ``workspace_seeds/org/duty_board.yaml``
      5. built-in defaults

    Returns ``(thresholds, source)`` where source is override|path|defaults.
    """
    thr: Dict[str, float] = dict(_DEFAULT_DUTY_THRESHOLDS)
    loaded, source = _load_duty_board_raw(override=override)

    if isinstance(loaded, Mapping):
        for key, default in _DEFAULT_DUTY_THRESHOLDS.items():
            if key in loaded and loaded[key] is not None:
                thr[key] = _coerce_threshold(loaded[key], default)

    return thr, source


def load_duty_board_playbook(
    *,
    override: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, List[str]], str]:
    """Load go/watch/block/unavailable action lists (duty-officer playbook)."""
    loaded, source = _load_duty_board_raw(override=override)
    out: Dict[str, List[str]] = {
        k: list(v) for k, v in _DEFAULT_DUTY_PLAYBOOK.items()
    }
    raw = None
    if isinstance(loaded, Mapping):
        raw = loaded.get("playbook")
    if isinstance(raw, Mapping):
        for key in ("go", "watch", "block", "unavailable"):
            items = raw.get(key)
            if isinstance(items, list) and items:
                out[key] = [str(x).strip() for x in items if str(x).strip()]
    return out, source


def collect_merge_gates_posture() -> Dict[str, Any]:
    """Merge-gate posture for duty board — exemptions as visible debt (no silent backdoor).

    Surfaces inflation/shape + testability mode / block_after / active exemptions
    plus exemption debt ledger (owner/cap/expired-unreviewed).
    Does not invent pass rates. Failures → empty slices with status unavailable.
    """
    from datetime import date, datetime, timezone

    today = datetime.now(timezone.utc).date()

    def _days_until(ba: str) -> Optional[int]:
        s = (ba or "").strip()
        if not s:
            return None
        try:
            return (date.fromisoformat(s[:10]) - today).days
        except ValueError:
            return None

    empty_debt: Dict[str, Any] = {
        "max_active": 3,
        "active_count": 0,
        "active": [],
        "excess": [],
        "invalid": [],
        "expired": [],
        "over_cap": False,
        "severity": "unavailable",
        "reasons": [],
        "policy": "",
    }
    physical: Dict[str, Any] = {
        "status": "unavailable",
        "mode": "unavailable",
        "block_after": "",
        "days_until_block": None,
        "config_source": "",
        "exemptions": [],
        "exemption_debt": dict(empty_debt),
    }
    testability: Dict[str, Any] = {
        "status": "unavailable",
        "mode": "unavailable",
        "block_after": "",
        "days_until_block": None,
        "config_source": "",
    }
    debt: Dict[str, Any] = dict(empty_debt)
    try:
        from core.harness.meta.physical_merge_gates import (
            assess_exemption_debt,
            load_physical_gates_config,
            resolve_mode,
        )

        cfg, src = load_physical_gates_config()
        mode = resolve_mode(cfg, now=today)
        debt = assess_exemption_debt(cfg, now=today)
        ex_rows = []
        for ex in debt.get("active") or []:
            ex_rows.append(
                {
                    "id": str(ex.get("id") or ""),
                    "owner": str(ex.get("owner") or ""),
                    "reason": str(ex.get("reason") or "")[:160],
                    "expires": str(ex.get("expires") or "")[:10],
                    "gates": [str(g) for g in (ex.get("gates") or [])][:8],
                }
            )
        ba = str(cfg.get("block_after") or "")
        physical = {
            "status": "ok",
            "mode": mode,
            "block_after": ba,
            "days_until_block": _days_until(ba),
            "config_source": src,
            "exemptions": ex_rows,
            "exemption_debt": debt,
        }
    except Exception as e:
        logger.debug("physical merge gates posture skipped: %s", e, exc_info=True)

    try:
        from core.harness.meta.testability_gate import (
            load_testability_config,
            resolve_mode as resolve_testability_mode,
        )

        tcfg, tsrc = load_testability_config()
        tmode = resolve_testability_mode(tcfg, now=today)
        tba = str(tcfg.get("block_after") or "")
        testability = {
            "status": "ok",
            "mode": tmode,
            "block_after": tba,
            "days_until_block": _days_until(tba),
            "config_source": tsrc,
        }
    except Exception as e:
        logger.debug("testability gates posture skipped: %s", e, exc_info=True)

    n_ex = int(debt.get("active_count") or len(physical.get("exemptions") or []))
    return {
        "physical": physical,
        "testability": testability,
        "active_exemption_count": n_ex,
        "exemptions_visible": True,  # policy: never silent
        "exemption_debt": debt,
        "debt_severity": str(debt.get("severity") or "unavailable"),
    }


def load_adoption_snapshot() -> Dict[str, Any]:
    """Best-effort HITL/Howl snapshot for duty_board (never invent rates).

    Returns empty dict when stores/howl unavailable — caller treats as no adoption.
    """
    out: Dict[str, Any] = {}
    try:
        from core.harness.evaluation.adoption_metrics import AdoptionTracker

        report = AdoptionTracker().compute_metrics()
        out.update(
            {
                "total_agent_calls": report.total_agent_calls,
                "total_users": report.total_users,
                "active_users_7d": report.active_users_7d,
                "grill_trigger_rate": report.grill_trigger_rate,
                "grill_completion_rate": report.grill_completion_rate,
                "hitl_approval_rate": report.hitl_approval_rate,
                "hitl_rejection_rate": report.hitl_rejection_rate,
                "adoption_trend": report.adoption_trend,
                "computed_at": report.computed_at,
            }
        )
    except Exception as e:
        logger.debug("adoption snapshot skipped: %s", e, exc_info=True)
    try:
        from core.harness.intervention.howl import get_howl_stats

        howl = get_howl_stats() or {}
        out["howl_interventions"] = howl.get("total_interventions")
        out["howl_by_reason"] = howl.get("by_reason") or {}
        out["howl_status"] = howl.get("status")
    except Exception as e:
        logger.debug("howl snapshot skipped: %s", e, exc_info=True)
        out.setdefault("howl_status", "unavailable")
        out.setdefault("howl_interventions", None)
    return out


def build_duty_board(
    payload: Optional[Mapping[str, Any]] = None,
    *,
    adoption: Optional[Mapping[str, Any]] = None,
    thresholds: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Duty-board verdict for Governance / release habit (never invent success_rate).

    status:
      - unavailable — no runs / gold / approvals (and no adoption signals)
      - block — gold regressing or P0 miss too high
      - watch — high serial_ratio / approval backlog / HITL reject heat
      - go — data present and no block/watch signals

    Facts only from org-harness (+ optional adoption). Fake-green forbidden:
    missing gold → availability.gold=false, not "ok".
    Bands from ``load_duty_board_thresholds`` (YAML / env / override).
    """
    thr, thr_source = load_duty_board_thresholds(override=thresholds)
    p0_block = thr["p0_miss_rate_block"]
    serial_watch = thr["serial_ratio_watch"]
    serial_high = thr["serial_ratio_high"]
    pending_watch = thr["approval_pending_watch"]
    lat_watch = thr["approval_latency_sec_watch"]
    hitl_watch = thr["hitl_rejection_rate_watch"]
    howl_watch = thr["howl_interventions_watch"]

    pl = payload if isinstance(payload, dict) else {}
    sm = pl.get("summary") if isinstance(pl.get("summary"), dict) else {}
    avail = pl.get("availability") if isinstance(pl.get("availability"), dict) else {}
    data_available = bool(pl.get("data_available"))
    if not avail:
        # Derive when fleet path omitted availability
        gold_ok = sm.get("gold_precision") is not None or sm.get("p0_miss_rate") is not None
        runs_ok = bool(sm.get("runs_scanned") or sm.get("hitl_episode_count") or sm.get("serial_ratio") is not None or sm.get("avg_serial_ratio") is not None)
        appr_ok = int(sm.get("approval_count") or 0) > 0 or int(sm.get("approval_pending") or 0) > 0
        avail = {"runs": runs_ok, "gold": gold_ok, "approvals": appr_ok}
        data_available = data_available or runs_ok or gold_ok or appr_ok

    ad = adoption if isinstance(adoption, dict) else {}
    if not ad and isinstance(pl.get("adoption"), dict):
        ad = pl["adoption"]  # type: ignore[assignment]
    has_adoption = bool(
        ad.get("total_agent_calls") is not None
        or ad.get("hitl_rejection_rate") is not None
        or ad.get("howl_interventions") is not None
    )

    reasons: List[str] = []
    status = "go"

    # Threshold override dicts (p0_miss_rate_block=…) must not swallow YAML playbook.
    playbook_override = (
        thresholds
        if isinstance(thresholds, Mapping) and "playbook" in thresholds
        else None
    )
    playbook_all, playbook_source = load_duty_board_playbook(override=playbook_override)
    gr = pl.get("gold_regression") if isinstance(pl.get("gold_regression"), dict) else {}
    gold_trend_summary = gr.get("trend_summary") if isinstance(gr.get("trend_summary"), dict) else None
    merge_gates = collect_merge_gates_posture()

    if not data_available and not has_adoption:
        return {
            "status": "unavailable",
            "label": "unavailable",
            "reasons": ["no runs / gold / approvals / adoption — do not invent success_rate"],
            "availability": avail,
            "checks": {
                "gold": "unavailable",
                "serial": "unavailable",
                "approvals": "unavailable",
                "hitl": "unavailable",
                "howl": "unavailable",
                "merge_gates": "unavailable",
                "envelope": "unavailable",
            },
            "thresholds": thr,
            "thresholds_source": thr_source,
            "release_habit": "run ops_harness_ready_check.sh + gold match-only before release",
            "playbook": list(playbook_all.get("unavailable") or []),
            "playbook_source": playbook_source,
            "gold_trend_summary": gold_trend_summary,
            "merge_gates": merge_gates,
            "envelope": {
                "issue_count": 0,
                "missing_envelope": 0,
                "by_status": {},
                "by_confidence": {},
                "confirmed_count": 0,
                "suspected_count": 0,
                "allow_block_count": 0,
                "block_allowed": False,
                "primary": None,
                "whys": [],
            },
        }

    checks: Dict[str, str] = {
        "gold": "unavailable",
        "serial": "unavailable",
        "approvals": "unavailable",
        "hitl": "unavailable",
        "howl": "unavailable",
        "merge_gates": "go",
    }

    # --- gold ---
    if avail.get("gold"):
        if sm.get("gold_regressing"):
            checks["gold"] = "block"
            reasons.append("gold_regressing")
            status = "block"
        else:
            try:
                miss = sm.get("p0_miss_rate")
                if miss is not None and float(miss) > p0_block:
                    checks["gold"] = "block"
                    reasons.append(f"p0_miss_rate={miss}>{p0_block}")
                    status = "block"
                else:
                    checks["gold"] = "go"
            except (TypeError, ValueError):
                checks["gold"] = "watch"
                reasons.append("p0_miss_rate unparseable")
                if status == "go":
                    status = "watch"
    else:
        checks["gold"] = "unavailable"
        reasons.append("gold unavailable (no reports)")

    # --- serial ---
    ratio = sm.get("avg_serial_ratio")
    if ratio is None:
        ratio = sm.get("serial_ratio")
    try:
        r = float(ratio) if ratio is not None else None
    except (TypeError, ValueError):
        r = None
    if r is not None:
        if r >= serial_high:
            checks["serial"] = "watch"
            reasons.append(f"serial_ratio={r}≥{serial_high}")
            if status == "go":
                status = "watch"
        elif r >= serial_watch:
            checks["serial"] = "watch"
            reasons.append(f"serial_ratio={r}≥{serial_watch}")
            if status == "go":
                status = "watch"
        else:
            checks["serial"] = "go"
    elif avail.get("runs"):
        checks["serial"] = "unavailable"
        reasons.append("serial_ratio unavailable (no wall/HITL timing)")

    # --- approvals ---
    try:
        pending = int(sm.get("approval_pending") or 0)
    except (TypeError, ValueError):
        pending = 0
    try:
        lat = float(sm["avg_approval_latency_sec"]) if sm.get("avg_approval_latency_sec") is not None else None
    except (TypeError, ValueError):
        lat = None
    if avail.get("approvals") or pending or lat is not None:
        if pending >= pending_watch or (lat is not None and lat >= lat_watch):
            checks["approvals"] = "watch"
            if pending >= pending_watch:
                reasons.append(f"approval_pending={pending}≥{int(pending_watch)}")
            if lat is not None and lat >= lat_watch:
                reasons.append(f"avg_approval_latency_sec={lat}≥{lat_watch}")
            if status == "go":
                status = "watch"
        else:
            checks["approvals"] = "go"

    # --- HITL / Howl from adoption (optional; never invent rates) ---
    try:
        rej = float(ad["hitl_rejection_rate"]) if ad.get("hitl_rejection_rate") is not None else None
    except (TypeError, ValueError):
        rej = None
    howl = ad.get("howl_interventions")
    howl_status = str(ad.get("howl_status") or "").strip().lower()
    if rej is not None:
        if rej > hitl_watch:
            checks["hitl"] = "watch"
            reasons.append(f"hitl_rejection_rate={rej}>{hitl_watch}")
            if status == "go":
                status = "watch"
        else:
            checks["hitl"] = "go"

    if howl is not None and howl_status not in ("unavailable", "error", "disabled"):
        try:
            howl_n = int(howl)
        except (TypeError, ValueError):
            howl_n = None
        if howl_n is not None:
            # Howl presence is informational; high absolute count → watch (ops attention)
            if howl_n >= howl_watch:
                checks["howl"] = "watch"
                reasons.append(f"howl_interventions={howl_n}≥{int(howl_watch)}")
                if status == "go":
                    status = "watch"
            else:
                checks["howl"] = "go"
    elif howl_status in ("unavailable", "error", "disabled"):
        checks["howl"] = "unavailable"
        reasons.append("howl unavailable")

    # --- merge gates posture (exemptions = debt; expired/invalid/over_cap → block) ---
    n_ex = int(merge_gates.get("active_exemption_count") or 0)
    phys = merge_gates.get("physical") if isinstance(merge_gates.get("physical"), dict) else {}
    debt_sev = str(merge_gates.get("debt_severity") or "").strip().lower()
    debt = merge_gates.get("exemption_debt") if isinstance(merge_gates.get("exemption_debt"), dict) else {}
    if debt_sev == "block":
        checks["merge_gates"] = "block"
        for r in (debt.get("reasons") or [])[:4]:
            reasons.append(str(r))
        if not debt.get("reasons"):
            reasons.append("exemption_debt_block")
        status = "block"
    elif n_ex > 0 or debt_sev == "watch":
        checks["merge_gates"] = "watch"
        ids = ",".join(
            str(x.get("id") or "?") for x in (phys.get("exemptions") or [])[:4]
        )
        owners = ",".join(
            str(x.get("owner") or "?") for x in (phys.get("exemptions") or [])[:4]
        )
        reasons.append(f"merge_gate_exemptions_active={n_ex} owners=[{owners}] ({ids})")
        if status == "go":
            status = "watch"
    elif phys.get("status") == "unavailable":
        checks["merge_gates"] = "unavailable"
        reasons.append("merge_gates posture unavailable")
    else:
        checks["merge_gates"] = "go"
        pmode = str(phys.get("mode") or "")
        if pmode == "warn":
            days = phys.get("days_until_block")
            if isinstance(days, int) and 0 <= days <= 14:
                reasons.append(f"physical_gates warn→block in {days}d ({phys.get('block_after')})")
                if status == "go":
                    status = "watch"
                    checks["merge_gates"] = "watch"

    if status == "go" and checks["gold"] == "unavailable" and not avail.get("runs"):
        # Only gold missing with no runs → still unavailable for release habit
        if not avail.get("approvals") and not has_adoption:
            status = "unavailable"

    # --- Evidence Envelope: findings fold + gold BLOCK (measured+limitations) ---
    from core.harness.meta.evidence_envelope import (
        envelope_for_exemption_debt_block,
        envelope_for_gold_block,
        fold_findings_for_duty,
        gate_duty_status_with_envelopes,
        summarize_envelopes,
    )

    findings_raw = pl.get("findings") if isinstance(pl.get("findings"), list) else []
    fold = fold_findings_for_duty(
        findings_raw,
        run_id=str(pl.get("run_id") or ""),
    )
    fold_hint = str(fold.get("status_hint") or "go")
    if fold_hint == "block":
        status = "block"
        reasons.extend(list(fold.get("reasons") or []))
    elif fold_hint == "watch" and status == "go":
        status = "watch"
        reasons.extend(list(fold.get("reasons") or []))

    envelopes: List[Dict[str, Any]] = []
    for env in fold.get("envelopes") or []:
        if isinstance(env, Mapping):
            envelopes.append(dict(env))
    if checks.get("gold") == "block":
        gold_reason = next(
            (r for r in reasons if "gold" in r or "p0_miss" in r),
            "gold_block",
        )
        latest = gr.get("latest") if isinstance(gr.get("latest"), dict) else {}
        envelopes.append(
            envelope_for_gold_block(
                reason=str(gold_reason),
                p0_miss_rate=sm.get("p0_miss_rate"),
                regressing=bool(sm.get("gold_regressing")),
                written_at=str(latest.get("written_at") or ""),
            )
        )
    if checks.get("merge_gates") == "block" or debt_sev == "block":
        debt_reason = next(
            (r for r in reasons if "exemption_debt" in r),
            "exemption_debt_block",
        )
        envelopes.append(
            envelope_for_exemption_debt_block(
                reason=str(debt_reason),
                expired_count=len(debt.get("expired") or []),
                invalid_count=len(debt.get("invalid") or []),
                over_cap=bool(debt.get("over_cap")),
                active_count=int(merge_gates.get("active_exemption_count") or 0),
                max_active=debt.get("max_active"),
            )
        )

    prev_status = status
    status, env_extras, env_rows = gate_duty_status_with_envelopes(status, envelopes)
    reasons.extend(env_extras)
    if prev_status == "block" and status != "block":
        if checks.get("gold") == "block":
            checks["gold"] = "watch"
        checks["envelope"] = "watch"
    elif status == "block" and any(r.get("allow_block") for r in env_rows):
        checks["envelope"] = "block"
    elif fold_hint == "watch" or (fold.get("issues") and status != "block"):
        checks["envelope"] = "watch"
    elif envelopes:
        checks["envelope"] = "go"
    else:
        checks["envelope"] = "unavailable"

    envelope_summary = summarize_envelopes(
        [{"evidence_envelope": r["envelope"]} for r in env_rows]
    )
    fold_summary = fold.get("summary") if isinstance(fold.get("summary"), dict) else {}
    envelope_summary["allow_block_count"] = sum(
        1 for r in env_rows if r.get("allow_block")
    )
    envelope_summary["release_block_ok"] = int(
        fold_summary.get("release_block_ok")
        or envelope_summary["allow_block_count"]
        or 0
    )
    envelope_summary["block_allowed"] = bool(
        status == "block" and any(r.get("allow_block") for r in env_rows)
    )
    envelope_summary["primary"] = (
        env_rows[0]["envelope"] if env_rows else None
    )
    envelope_summary["whys"] = [str(r.get("why") or "") for r in env_rows]
    envelope_summary["findings_folded"] = int(len(fold.get("issues") or []))

    label = {
        "go": "GO",
        "watch": "WATCH",
        "block": "BLOCK",
        "unavailable": "UNAVAILABLE",
    }.get(status, status.upper())

    return {
        "status": status,
        "label": label,
        "reasons": reasons or (["metrics within band"] if status == "go" else []),
        "availability": avail,
        "checks": checks,
        "thresholds": thr,
        "thresholds_source": thr_source,
        "release_habit": (
            "BLOCK: hold model upgrade / fix harness before release"
            if status == "block"
            else "WATCH: clear HITL/approvals friction before celebrating AI speedup"
            if status == "watch"
            else "UNAVAILABLE: run gold match-only + pipeline samples; never invent success_rate"
            if status == "unavailable"
            else "GO: keep org-harness on the duty board; re-check gold after each release"
        ),
        "playbook": list(playbook_all.get(status) or playbook_all.get("unavailable") or []),
        "playbook_source": playbook_source,
        "gold_trend_summary": gold_trend_summary,
        "merge_gates": merge_gates,
        "envelope": envelope_summary,
    }


def serial_chain_recommendations(
    summary: Dict[str, Any],
    *,
    thresholds: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, str]]:
    """Actionable Amdahl / HITL redesign hints (ops, not a parallel workflow engine)."""
    thr, _ = load_duty_board_thresholds(override=thresholds)
    serial_high = thr["serial_ratio_high"]
    serial_watch = thr["serial_ratio_watch"]
    pending_watch = thr["approval_pending_watch"]
    lat_watch = thr["approval_latency_sec_watch"]
    p0_block = thr["p0_miss_rate_block"]

    sm = summary if isinstance(summary, dict) else {}
    tips: List[Dict[str, str]] = []
    ratio = sm.get("avg_serial_ratio")
    if ratio is None:
        ratio = sm.get("serial_ratio")
    try:
        r = float(ratio) if ratio is not None else None
    except (TypeError, ValueError):
        r = None
    if r is not None and r >= serial_high:
        tips.append({
            "severity": "high",
            "action": "redesign_hitl_chain",
            "detail": (
                f"serial_ratio={r} ≥ {serial_high} — AI 加速被 HITL/审批吃掉；"
                "合并串行闸口、并行化独立审批、或把低风险路径改为 async notify"
            ),
        })
    elif r is not None and r >= serial_watch:
        tips.append({
            "severity": "medium",
            "action": "trim_approval_steps",
            "detail": f"serial_ratio={r} — 审计每任务审批次数，去掉重复 PolicyGate/HITL",
        })
    pending = sm.get("approval_pending")
    try:
        if pending is not None and int(pending) >= pending_watch:
            tips.append({
                "severity": "medium",
                "action": "clear_approval_backlog",
                "detail": f"pending approvals={pending} — 积压抬高 wall time，优先清理或分派",
            })
    except (TypeError, ValueError):
        pass  # noqa: parse-best-effort
    lat = sm.get("avg_approval_latency_sec")
    try:
        if lat is not None and float(lat) >= lat_watch:
            tips.append({
                "severity": "high",
                "action": "sla_on_approvals",
                "detail": f"avg approval latency={lat}s ≥ {lat_watch}s — 设 SLA / 值班轮转，勿只升模型",
            })
    except (TypeError, ValueError):
        pass  # noqa: parse-best-effort
    if sm.get("gold_regressing"):
        tips.append({
            "severity": "high",
            "action": "hold_model_upgrade",
            "detail": "黄金集回归中 — 先修 harness/prompt，再换模型",
        })
    if sm.get("p0_miss_rate") is not None:
        try:
            if float(sm["p0_miss_rate"]) > p0_block:
                tips.append({
                    "severity": "high",
                    "action": "raise_p0_recall",
                    "detail": f"p0_miss_rate={sm['p0_miss_rate']} — 提高 high_coverage 档位或补 gold P0 用例",
                })
        except (TypeError, ValueError):
            pass  # noqa: parse-best-effort
    if not tips:
        tips.append({
            "severity": "info",
            "action": "monitor",
            "detail": "串行比与审批延迟在可接受范围；继续用 org-harness 盯趋势",
        })
    return tips

def _load_gold_reports(*, tenant_id: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    try:
        from core.harness.evaluation.code_review_gold import list_eval_reports

        return list(list_eval_reports(tenant_id=tenant_id or "", limit=limit) or [])
    except Exception as e:
        logger.debug("org_harness gold reports skipped: %s", e, exc_info=True)
        return []


def aggregate_org_harness(
    *,
    events: Optional[Sequence[Dict[str, Any]]] = None,
    hitl_audit: Optional[Sequence[Dict[str, Any]]] = None,
    approvals: Optional[Sequence[Dict[str, Any]]] = None,
    gold_reports: Optional[Sequence[Dict[str, Any]]] = None,
    run_id: str = "",
) -> Dict[str, Any]:
    """Unified org-harness dashboard payload (Amdahl serial vs wall + gold/P0)."""
    ev = summarize_run_events(events or [])
    au = summarize_hitl_audit(hitl_audit or [])
    ap = summarize_approvals(approvals or [])
    gold = summarize_gold_regression(gold_reports or [])

    serial = float(ev.get("hitl_wait_sec_total") or 0) + float(au.get("hitl_wait_sec_total") or 0)
    # Prefer event-derived wall; audit alone has no wall
    wall = ev.get("wall_sec")
    ratio = round(serial / wall, 4) if wall and wall > 0 else ev.get("serial_ratio")
    latest = gold.get("latest") or {}

    report_count = int(gold.get("report_count") or 0)
    approval_count = int(ap.get("approval_count") or 0)
    hitl_eps = len(ev.get("hitl_episodes") or []) + len(au.get("hitl_episodes") or [])
    has_events = bool(events) or bool(hitl_audit)
    has_gold = report_count > 0
    has_approvals = approval_count > 0
    data_available = has_events or has_gold or has_approvals

    out = {
        "ok": True,
        "data_available": data_available,
        "availability": {
            "runs": has_events,
            "gold": has_gold,
            "approvals": has_approvals,
        },
        "run_id": run_id or "",
        "summary": {
            "hitl_wait_sec_total": round(serial, 3),
            "wall_sec": wall,
            "serial_ratio": ratio,
            "approval_count": ap.get("approval_count"),
            "approval_pending": ap.get("pending"),
            "avg_approval_latency_sec": ap.get("avg_latency_sec"),
            "avg_approvals_per_run": ap.get("avg_approvals_per_run"),
            "hitl_episode_count": hitl_eps,
            "open_unresolved": (ev.get("open_unresolved") or 0) + (au.get("open_unresolved") or 0),
            "gold_precision": latest.get("precision"),
            "gold_recall": latest.get("recall"),
            "gold_p0_recall": latest.get("p0_recall"),
            "p0_miss_rate": gold.get("p0_miss_rate"),
            "gold_regressing": gold.get("regressing"),
            "gold_novel_count": latest.get("novel_count"),
            "gold_avg_comment_count": latest.get("avg_comment_count"),
            "gold_elapsed_sec": latest.get("elapsed_sec"),
        },
        "run_events": ev,
        "hitl_audit": au,
        "approvals": ap,
        "gold_regression": gold,
        "recommendations": serial_chain_recommendations({
            "serial_ratio": ratio,
            "approval_pending": ap.get("pending"),
            "avg_approval_latency_sec": ap.get("avg_latency_sec"),
            "gold_regressing": gold.get("regressing"),
            "p0_miss_rate": gold.get("p0_miss_rate"),
        }),
        "notes": [
            "serial_ratio ≈ HITL wait / observed wall (Amdahl proxy; not CPU parallel speedup)",
            "p0_miss_rate = 1 − gold p0_recall (ReviewBench-aligned leak proxy)",
            "Complementary capital: redesign serial approvals, do not only upgrade models",
            "duty_board merges adoption/HITL/Howl when available — never invents success_rate",
        ],
    }
    adoption = load_adoption_snapshot()
    if adoption:
        out["adoption"] = {
            k: adoption.get(k)
            for k in (
                "hitl_approval_rate",
                "hitl_rejection_rate",
                "howl_interventions",
                "howl_status",
                "adoption_trend",
                "total_agent_calls",
            )
            if k in adoption
        }
    out["duty_board"] = build_duty_board(out, adoption=adoption or None)
    return out


def _load_run_events(run_id: str, *, limit: int = 2000) -> List[Dict[str, Any]]:
    if not run_id:
        return []
    try:
        from core.harness.execution.pipeline_run_store import get_pipeline_run_store

        return list(get_pipeline_run_store().list_run_events(run_id, limit=limit) or [])
    except Exception as e:
        logger.debug("org_harness events load skipped: %s", e, exc_info=True)
        return []


def _execution_db_path() -> str:
    import os

    env = (os.environ.get("AIPLAT_EXECUTION_DB_PATH") or os.environ.get("AIPLAT_EXECUTION_DB") or "").strip()
    if env:
        return env
    try:
        from core.services.execution_store import get_execution_store

        return str(getattr(getattr(get_execution_store(), "_config", None), "db_path", "") or "")
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".aiplat", "aiplat_executions.sqlite3")


def _load_approvals_sync(
    *,
    run_id: str = "",
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Best-effort sync read of approval_requests (no async event loop required)."""
    try:
        import json
        import os
        import sqlite3

        db_path = _execution_db_path()
        if not db_path or not os.path.isfile(db_path):
            return []
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(approval_requests)").fetchall()}
            if "request_id" not in cols:
                return []
            select_cols = ["request_id", "status", "created_at", "updated_at"]
            for optional in ("run_id", "metadata_json"):
                if optional in cols:
                    select_cols.append(optional)
            col_sql = ", ".join(select_cols)
            if run_id and "run_id" in cols:
                rows = conn.execute(
                    f"SELECT {col_sql} FROM approval_requests WHERE run_id=? "
                    f"ORDER BY created_at DESC LIMIT ?",
                    (run_id, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT {col_sql} FROM approval_requests "
                    f"ORDER BY created_at DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
        finally:
            conn.close()
        out: List[Dict[str, Any]] = []
        for r in rows or []:
            meta: Dict[str, Any] = {}
            try:
                raw = r["metadata_json"] if "metadata_json" in r.keys() else None
                if raw:
                    meta = json.loads(raw) if isinstance(raw, str) else {}
            except Exception:
                meta = {}
            out.append({
                "request_id": r["request_id"],
                "status": r["status"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "run_id": (r["run_id"] if "run_id" in r.keys() else "") or "",
                "metadata": meta if isinstance(meta, dict) else {},
            })
        return out
    except Exception as e:
        logger.debug("org_harness approvals load skipped: %s", e, exc_info=True)
        return []


def collect_org_harness(
    *,
    run_id: str = "",
    hitl_audit: Optional[Sequence[Dict[str, Any]]] = None,
    approvals: Optional[Sequence[Dict[str, Any]]] = None,
    gold_reports: Optional[Sequence[Dict[str, Any]]] = None,
    recent_limit: int = 10,
    load_approvals: bool = True,
    load_gold: bool = True,
    tenant_id: str = "",
) -> Dict[str, Any]:
    """Load stores → aggregate. Empty run_id → fleet view over recent pipeline runs."""
    rid = (run_id or "").strip()
    gold = list(gold_reports) if gold_reports is not None else (
        _load_gold_reports(tenant_id=tenant_id, limit=20) if load_gold else []
    )
    if rid:
        events = _load_run_events(rid)
        ap = list(approvals) if approvals is not None else (
            _load_approvals_sync(run_id=rid) if load_approvals else []
        )
        out = aggregate_org_harness(
            events=events,
            hitl_audit=hitl_audit,
            approvals=ap,
            gold_reports=gold,
            run_id=rid,
        )
        out["scope"] = "run"
        return out

    # Fleet: average serial_ratio across recent runs + global approvals + gold
    recent: List[Dict[str, Any]] = []
    try:
        from core.harness.execution.pipeline_run_store import get_pipeline_run_store

        recent = list(get_pipeline_run_store().list_recent_runs(limit=max(1, min(int(recent_limit or 10), 50))) or [])
    except Exception as e:
        logger.debug("org_harness recent runs skipped: %s", e, exc_info=True)

    per_run: List[Dict[str, Any]] = []
    ratios: List[float] = []
    serial_sum = 0.0
    for row in recent:
        r_id = str(row.get("run_id") or "").strip()
        if not r_id:
            continue
        one = aggregate_org_harness(
            events=_load_run_events(r_id),
            hitl_audit=None,
            approvals=[],
            gold_reports=[],  # gold is tenant-scoped, attached once below
            run_id=r_id,
        )
        sm = one.get("summary") or {}
        per_run.append({
            "run_id": r_id,
            "phase": row.get("phase"),
            "serial_ratio": sm.get("serial_ratio"),
            "hitl_wait_sec_total": sm.get("hitl_wait_sec_total"),
            "wall_sec": sm.get("wall_sec"),
            "hitl_episode_count": sm.get("hitl_episode_count"),
        })
        if sm.get("serial_ratio") is not None:
            ratios.append(float(sm["serial_ratio"]))
        serial_sum += float(sm.get("hitl_wait_sec_total") or 0)

    ap = list(approvals) if approvals is not None else (
        _load_approvals_sync(limit=300) if load_approvals else []
    )
    ap_sum = summarize_approvals(ap)
    gold_sum = summarize_gold_regression(gold)
    latest = gold_sum.get("latest") or {}
    has_gold = int(gold_sum.get("report_count") or 0) > 0
    has_runs = len(per_run) > 0
    has_approvals = int(ap_sum.get("approval_count") or 0) > 0
    data_available = has_gold or has_runs or has_approvals
    out = {
        "ok": True,
        "scope": "fleet",
        "run_id": "",
        "data_available": data_available,
        "availability": {
            "runs": has_runs,
            "gold": has_gold,
            "approvals": has_approvals,
        },
        "summary": {
            "runs_scanned": len(per_run),
            "hitl_wait_sec_total": round(serial_sum, 3),
            "avg_serial_ratio": round(sum(ratios) / len(ratios), 4) if ratios else None,
            "approval_count": ap_sum.get("approval_count"),
            "approval_pending": ap_sum.get("pending"),
            "avg_approval_latency_sec": ap_sum.get("avg_latency_sec"),
            "avg_approvals_per_run": ap_sum.get("avg_approvals_per_run"),
            "gold_precision": latest.get("precision"),
            "gold_recall": latest.get("recall"),
            "gold_p0_recall": latest.get("p0_recall"),
            "p0_miss_rate": gold_sum.get("p0_miss_rate"),
            "gold_regressing": gold_sum.get("regressing"),
            "gold_novel_count": latest.get("novel_count"),
            "gold_avg_comment_count": latest.get("avg_comment_count"),
            "gold_elapsed_sec": latest.get("elapsed_sec"),
        },
        "runs": per_run,
        "approvals": ap_sum,
        "gold_regression": gold_sum,
        "recommendations": serial_chain_recommendations({
            "avg_serial_ratio": round(sum(ratios) / len(ratios), 4) if ratios else None,
            "approval_pending": ap_sum.get("pending"),
            "avg_approval_latency_sec": ap_sum.get("avg_latency_sec"),
            "gold_regressing": gold_sum.get("regressing"),
            "p0_miss_rate": gold_sum.get("p0_miss_rate"),
        }),
        "notes": [
            "Fleet serial_ratio = mean of per-run HITL wait / wall (Amdahl dark ledger)",
            "p0_miss_rate = 1 − gold p0_recall; regressing if P/R/P0 drops >0.02 vs prior run",
            "Upgrade models only after serial_ratio drops — redesign HITL chains first",
            "duty_board.status unavailable ≠ go — never invent success_rate",
            "duty_board merges adoption/HITL/Howl when available",
        ],
    }
    adoption = load_adoption_snapshot()
    if adoption:
        out["adoption"] = {
            k: adoption.get(k)
            for k in (
                "hitl_approval_rate",
                "hitl_rejection_rate",
                "howl_interventions",
                "howl_status",
                "adoption_trend",
                "total_agent_calls",
            )
            if k in adoption
        }
    out["duty_board"] = build_duty_board(out, adoption=adoption or None)
    return out


def org_harness_status(
    *,
    run_id: str = "",
    recent_limit: int = 10,
    tenant_id: str = "",
) -> Dict[str, Any]:
    """Public entry used by CoreFacade / governance API."""
    return collect_org_harness(
        run_id=run_id,
        recent_limit=recent_limit,
        tenant_id=tenant_id or "",
    )
