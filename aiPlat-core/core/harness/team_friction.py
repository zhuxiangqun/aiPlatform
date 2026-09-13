"""T4a/T4b: friction → local learning drafts (no auto Git contribute).

Closed signals:
  T4a: hitl_reject · prd_gate_fail · regenerate_count>=2 (confirm/cooldown)
  T4b: schema_gate_hitl · schema_gate_block · schema_gate_fail_pipeline · repair_exhausted

Learnings land under ~/.aiplat/local/learnings/ — never team/ by default.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional

logger = logging.getLogger(__name__)

SIGNAL_HITL_REJECT = "hitl_reject"
SIGNAL_PRD_GATE_FAIL = "prd_gate_fail"
SIGNAL_REGENERATE = "regenerate_count"
SIGNAL_SCHEMA_GATE_HITL = "schema_gate_hitl"
SIGNAL_SCHEMA_GATE_BLOCK = "schema_gate_block"
SIGNAL_SCHEMA_GATE_FAIL = "schema_gate_fail_pipeline"
SIGNAL_REPAIR_EXHAUSTED = "repair_exhausted"

T4A_SIGNALS = frozenset(
    {SIGNAL_HITL_REJECT, SIGNAL_PRD_GATE_FAIL, SIGNAL_REGENERATE}
)
T4B_SIGNALS = frozenset(
    {
        SIGNAL_SCHEMA_GATE_HITL,
        SIGNAL_SCHEMA_GATE_BLOCK,
        SIGNAL_SCHEMA_GATE_FAIL,
        SIGNAL_REPAIR_EXHAUSTED,
    }
)
ALLOWED_SIGNALS = T4A_SIGNALS | T4B_SIGNALS

REGENERATE_THRESHOLD = 2
COOLDOWN_SEC = 24 * 3600
STATE_CTA_KEY = "_friction_share_cta"


def aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")).expanduser()


def local_learnings_dir() -> Path:
    d = aiplat_home() / "local" / "learnings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state_path() -> Path:
    return aiplat_home() / "local" / "friction_state.json"


def _load_store() -> Dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return {"regenerate_counts": {}, "cooldowns": {}, "events": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"regenerate_counts": {}, "cooldowns": {}, "events": []}
    except Exception:
        return {"regenerate_counts": {}, "cooldowns": {}, "events": []}


def _save_store(store: Mapping[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(store), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _scrub(text: str, limit: int = 400) -> str:
    """Drop obvious secrets / keep short — no raw prompt dumps."""
    s = str(text or "")
    for token in ("sk-", "api_key", "password=", "Authorization:"):
        if token.lower() in s.lower():
            s = "[redacted]"
            break
    return s[:limit]


def _rk(project_id: str, stage_id: str = "") -> str:
    return f"{project_id}::{stage_id or '_'}"


def note_regenerate(
    project_id: str,
    stage_id: str = "",
    *,
    detail: str = "",
) -> Dict[str, Any]:
    """Increment regenerate count; emit CTA when threshold reached (confirm/cooldown)."""
    store = _load_store()
    counts = store.setdefault("regenerate_counts", {})
    key = _rk(project_id, stage_id)
    count = int(counts.get(key) or 0) + 1
    counts[key] = count
    _save_store(store)

    out: Dict[str, Any] = {
        "ok": True,
        "signal": SIGNAL_REGENERATE,
        "count": count,
        "threshold": REGENERATE_THRESHOLD,
        "learning_id": "",
        "needs_confirm": False,
        "cta": None,
    }
    if count < REGENERATE_THRESHOLD:
        return out

    cool_key = f"{SIGNAL_REGENERATE}:{key}"
    cools = store.get("cooldowns") or {}
    last = float(cools.get(cool_key) or 0)
    if last and (time.time() - last) < COOLDOWN_SEC:
        out["skipped"] = "cooldown"
        out["cooldown_remaining_sec"] = int(COOLDOWN_SEC - (time.time() - last))
        return out

    cta = _make_cta(
        signal=SIGNAL_REGENERATE,
        project_id=project_id,
        stage_id=stage_id,
        detail=detail or f"regenerate_count={count}",
        needs_confirm=True,
        learning_id="",
    )
    out["needs_confirm"] = True
    out["cta"] = cta
    return out


def record_friction_event(
    signal: str,
    *,
    project_id: str = "",
    stage_id: str = "",
    detail: str = "",
    confirmed: bool = False,
) -> Dict[str, Any]:
    """Record a T4a/T4b friction signal; write local learning when allowed."""
    sig = str(signal or "").strip()
    if sig not in ALLOWED_SIGNALS:
        return {"ok": False, "error": f"unknown_signal:{sig}"}

    if sig == SIGNAL_REGENERATE and not confirmed:
        # regenerate path must go through note_regenerate + confirm
        return {
            "ok": False,
            "error": "regenerate_requires_confirm",
            "hint": "call note_regenerate then confirm_friction_share",
        }

    auto_draft = sig in (
        SIGNAL_HITL_REJECT,
        SIGNAL_PRD_GATE_FAIL,
        SIGNAL_SCHEMA_GATE_HITL,
        SIGNAL_SCHEMA_GATE_BLOCK,
        SIGNAL_SCHEMA_GATE_FAIL,
        SIGNAL_REPAIR_EXHAUSTED,
    ) or (sig == SIGNAL_REGENERATE and confirmed)

    learning_id = ""
    if auto_draft:
        learning_id = _write_learning_draft(
            signal=sig,
            project_id=project_id,
            stage_id=stage_id,
            detail=detail,
        )

    store = _load_store()
    events = store.setdefault("events", [])
    if isinstance(events, list):
        events.append(
            {
                "ts": time.time(),
                "signal": sig,
                "project_id": project_id,
                "stage_id": stage_id,
                "learning_id": learning_id,
            }
        )
        if len(events) > 200:
            store["events"] = events[-200:]
    if sig == SIGNAL_REGENERATE and confirmed:
        cools = store.setdefault("cooldowns", {})
        cools[f"{SIGNAL_REGENERATE}:{_rk(project_id, stage_id)}"] = time.time()
        # reset count after confirmed share
        counts = store.setdefault("regenerate_counts", {})
        counts[_rk(project_id, stage_id)] = 0
    _save_store(store)

    cta = _make_cta(
        signal=sig,
        project_id=project_id,
        stage_id=stage_id,
        detail=detail,
        needs_confirm=False,
        learning_id=learning_id,
    )
    return {
        "ok": True,
        "signal": sig,
        "learning_id": learning_id,
        "needs_confirm": False,
        "cta": cta,
        "local_only": True,
    }


def confirm_friction_share(
    *,
    project_id: str,
    stage_id: str = "",
    signal: str = SIGNAL_REGENERATE,
    detail: str = "",
) -> Dict[str, Any]:
    """User confirmed sharing a regenerate friction as local learning."""
    sig = str(signal or SIGNAL_REGENERATE).strip()
    if sig != SIGNAL_REGENERATE:
        # other signals already auto-drafted
        return record_friction_event(
            sig, project_id=project_id, stage_id=stage_id, detail=detail, confirmed=True
        )
    return record_friction_event(
        SIGNAL_REGENERATE,
        project_id=project_id,
        stage_id=stage_id,
        detail=detail or "user confirmed regenerate friction",
        confirmed=True,
    )


def attach_friction_cta(
    state: MutableMapping[str, Any],
    cta: Optional[Mapping[str, Any]],
) -> None:
    """Persist CTA on pipeline/project state for Factory polling."""
    if not cta:
        return
    state[STATE_CTA_KEY] = dict(cta)


def clear_friction_cta(state: MutableMapping[str, Any]) -> None:
    state.pop(STATE_CTA_KEY, None)


def record_schema_gate_friction(
    action: str,
    *,
    project_id: str = "",
    stage_id: str = "",
    detail: str = "",
    state: Optional[MutableMapping[str, Any]] = None,
) -> Dict[str, Any]:
    """T4b: map schema_gate_* audit actions → local friction learning."""
    sig = str(action or "").strip()
    if sig not in T4B_SIGNALS - {SIGNAL_REPAIR_EXHAUSTED}:
        if sig.startswith("schema_gate_"):
            # unknown schema_gate variant — ignore quietly
            return {"ok": False, "error": f"unknown_signal:{sig}"}
        return {"ok": False, "error": f"unknown_signal:{sig}"}
    result = record_friction_event(
        sig, project_id=project_id, stage_id=stage_id, detail=detail
    )
    if state is not None and result.get("cta"):
        attach_friction_cta(state, result.get("cta"))
    return result


def list_local_learnings(*, limit: int = 20) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    root = local_learnings_dir()
    files = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[: max(1, int(limit))]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                rows.append(data)
        except Exception:
            continue
    return rows


def _make_cta(
    *,
    signal: str,
    project_id: str,
    stage_id: str,
    detail: str,
    needs_confirm: bool,
    learning_id: str,
) -> Dict[str, Any]:
    messages = {
        SIGNAL_HITL_REJECT: "HITL 驳回已记入本地经验草稿，可稍后贡献到团队仓。",
        SIGNAL_PRD_GATE_FAIL: "PRD 门禁未过，已记入本地经验草稿。",
        SIGNAL_REGENERATE: "本阶段反复重做，是否沉淀为本地经验？（需确认）",
        SIGNAL_SCHEMA_GATE_HITL: "Schema 门禁转入人工，已记入本地经验草稿。",
        SIGNAL_SCHEMA_GATE_BLOCK: "Schema 门禁阻塞，已记入本地经验草稿。",
        SIGNAL_SCHEMA_GATE_FAIL: "Schema 门禁失败结束流水线，已记入本地经验草稿。",
        SIGNAL_REPAIR_EXHAUSTED: "自动修复轮次耗尽，已记入本地经验草稿。",
    }
    return {
        "signal": signal,
        "project_id": project_id,
        "stage_id": stage_id,
        "detail": _scrub(detail, 200),
        "needs_confirm": bool(needs_confirm),
        "learning_id": learning_id,
        "message": messages.get(signal, "检测到可分享的摩擦信号"),
        "ts": time.time(),
        "contribute_default": False,
    }


def _write_learning_draft(
    *,
    signal: str,
    project_id: str,
    stage_id: str,
    detail: str,
) -> str:
    lid = f"learn-{uuid.uuid4().hex[:12]}"
    payload = {
        "id": lid,
        "signal": signal,
        "project_id": str(project_id or "")[:128],
        "stage_id": str(stage_id or "")[:128],
        "detail": _scrub(detail),
        "created_at": time.time(),
        "local_only": True,
        "contributed": False,
    }
    path = local_learnings_dir() / f"{lid}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return lid
