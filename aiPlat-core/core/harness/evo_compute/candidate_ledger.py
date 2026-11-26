"""候选 HUMAN_GATE 审批台账（生产加深 D1）。

落盘审批记录供覆盖审计消费；不写生产路由/配置、不宣称 G3 完成。
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.harness.evo_compute.status import normalize_status

_PRODUCTION_PATH_STATUSES = frozenset(
    {"approved", "canary", "production", "retired", "rolled_back"}
)

_LEDGER: Optional[Dict[str, Dict[str, Any]]] = None


def _ledger_path() -> Path:
    """台账落盘路径。"""
    root = os.environ.get("AIPLAT_HOME") or os.path.expanduser("~/.aiplat")
    p = Path(root) / "evo_compute"
    try:
        p.mkdir(parents=True, exist_ok=True)
        return p / "candidate_ledger.json"
    except OSError:
        p = Path(tempfile.gettempdir()) / "aiplat_evo_compute"
        p.mkdir(parents=True, exist_ok=True)
        return p / "candidate_ledger.json"


def _load() -> Dict[str, Dict[str, Any]]:
    global _LEDGER
    if _LEDGER is not None:
        return _LEDGER
    path = _ledger_path()
    data: Dict[str, Dict[str, Any]] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("candidates"), dict):
                data = {str(k): dict(v) for k, v in raw["candidates"].items() if isinstance(v, dict)}
            elif isinstance(raw, dict):
                data = {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}
        except (OSError, json.JSONDecodeError):
            data = {}
    _LEDGER = data
    return _LEDGER


def _save(data: Dict[str, Dict[str, Any]]) -> None:
    path = _ledger_path()
    blob = {"schema": "aiplat.evo_candidate_ledger.v1", "candidates": data}
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clear_ledger_for_tests() -> None:
    """测试用：清空进程内台账（不删磁盘，除非随后 persist）。"""
    global _LEDGER
    _LEDGER = {}


def record_human_gate_decision(
    *,
    candidate_id: str,
    status: str,
    actor: str,
    evidence_ref: str,
    human_gate_passed: bool = True,
    persist: bool = True,
) -> Dict[str, Any]:
    """记录候选 HUMAN_GATE 决策到台账。

    Args:
        candidate_id: 候选 id。
        status: Candidate.status。
        actor: 审批人。
        evidence_ref: 证据引用。
        human_gate_passed: 是否过门。
        persist: 是否落盘。

    Returns:
        回执；``production_write`` 恒 false（仅台账，非生产配置）。
    """
    cid = str(candidate_id or "").strip()
    act = str(actor or "").strip()
    evid = str(evidence_ref or "").strip()
    st = normalize_status(status)
    out: Dict[str, Any] = {
        "ok": False,
        "candidate_id": cid,
        "error": "",
        "production_write": False,
        "g3_foundation": True,
        "g3_complete": False,
        "certified": False,
        "e2_claimed": False,
        "source": "ledger",
    }
    if not cid:
        out["error"] = "candidate_id_required"
        return out
    if human_gate_passed and (not act or not evid):
        out["error"] = "actor_and_evidence_required_when_passed"
        return out

    row = {
        "candidate_id": cid,
        "status": st,
        "human_gate_passed": bool(human_gate_passed),
        "human_gate_actor": act,
        "human_gate_evidence_ref": evid,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data = _load()
    data[cid] = row
    if persist:
        try:
            _save(data)
        except OSError as exc:
            out["error"] = f"persist_failed:{exc}"
            return out
    out["ok"] = True
    out["row"] = row
    return out


def list_production_path_candidates(
    *,
    production_path_only: bool = True,
) -> Dict[str, Any]:
    """列出台账中（可选仅生产路径）的候选行。

    Args:
        production_path_only: 仅 approved 及之后状态。

    Returns:
        ``candidates`` 列表与 ``source=ledger``；空台账诚实上报。
    """
    data = _load()
    rows: List[Dict[str, Any]] = []
    for row in data.values():
        st = normalize_status(str(row.get("status") or ""))
        if production_path_only and st not in _PRODUCTION_PATH_STATUSES:
            continue
        rows.append(dict(row))
    return {
        "ok": True,
        "candidates": rows,
        "count": len(rows),
        "empty": len(rows) == 0,
        "source": "ledger",
        "production_write": False,
        "g3_foundation": True,
        "g3_complete": False,
        "certified": False,
        "e2_claimed": False,
        "note": "ledger listing; empty ≠ production traffic claim",
    }
