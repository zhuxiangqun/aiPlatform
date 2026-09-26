"""H4 — sandbox queue auto-pass. Sandbox switch on; live refused.

Changes queue status only. Never calls apply_ticket, never writes live YAML,
never writes cross-domain edges.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_AUDIT_ROLES = frozenset({"admin"})
_SCAN_ROLES = frozenset({"admin"})
_ACTOR = "h4-auto"


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def rules_path() -> Path:
    return _home() / "org" / "approval_rules.yaml"


def audit_path() -> Path:
    return _home() / "org" / "h4_audit.jsonl"


def _io_mode() -> str:
    return (os.getenv("AIPLAT_ORG_IO_MODE") or "sandbox").strip().lower()


def sandbox_switch_on() -> bool:
    """No rules file: sandbox/readonly_graph starts enabled. Live stays off."""
    return _io_mode() in ("", "sandbox", "readonly_graph")


def default_rules() -> Dict[str, Any]:
    return {
        "enabled": sandbox_switch_on(),
        "sandbox_only": True,
        "confidence_min": 0.95,
        "domains": ["it-ops"],
        "exact_strategies": ["exact"],
        "daily_auto_rate_max": 0.2,
        "min_sample": 5,
        "circuit_reason": "",
        "circuit_at": 0,
    }


def load_rules() -> Dict[str, Any]:
    path = rules_path()
    base = default_rules()
    if not path.is_file():
        return base
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        logger.warning("h4 rules unreadable", exc_info=True)
        return base
    if not isinstance(raw, dict):
        return base
    base.update({k: raw[k] for k in base if k in raw})
    base["enabled"] = bool(raw.get("enabled", False))
    return base


def _write_rules(rules: Dict[str, Any]) -> None:
    path = rules_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(rules, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _sandbox_ok(rules: Dict[str, Any]) -> bool:
    if not rules.get("sandbox_only", True):
        return False
    return sandbox_switch_on()


def _day() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def _read_audit() -> List[Dict[str, Any]]:
    path = audit_path()
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _append_audit(event: Dict[str, Any]) -> None:
    path = audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {**event, "ts": time.time(), "day": _day()}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def _today_stats() -> Dict[str, int]:
    day = _day()
    auto_n = skip_n = live_refused = 0
    for row in _read_audit():
        if row.get("day") != day:
            continue
        kind = row.get("event")
        if kind == "auto_pass":
            auto_n += 1
        elif kind == "skip":
            skip_n += 1
        elif kind == "live_refused":
            live_refused += 1
    return {"auto": auto_n, "skip": skip_n, "live_refused": live_refused}


def _rate(stats: Dict[str, int]) -> float:
    seen = int(stats["auto"]) + int(stats["skip"])
    if seen <= 0:
        return 0.0
    return int(stats["auto"]) / float(seen)


def sandbox_live_delta(stats: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Read-only sandbox vs live pass comparison. Never enables live auto-pass."""
    st = stats if isinstance(stats, dict) else _today_stats()
    sandbox_seen = int(st.get("auto") or 0) + int(st.get("skip") or 0)
    live_refused = int(st.get("live_refused") or 0)
    mode = _io_mode() or "sandbox"
    sandbox_rate = (_rate(st) if sandbox_seen else None)
    live_rate = 0.0 if live_refused > 0 or mode == "live" else None
    return {
        "io_mode": mode,
        "sandbox_auto": int(st.get("auto") or 0),
        "sandbox_skip": int(st.get("skip") or 0),
        "sandbox_pass_rate": sandbox_rate,
        "live_refused_today": live_refused,
        "live_auto_pass_rate": live_rate,
        "auto_applied_shadow": False,
        "wrote_live_yaml": False,
        "delta_note": (
            "live 拒绝自动通过，不是灰度放行。"
            if live_refused or mode == "live"
            else "尚无 live 拒绝记录；沙箱通过率仅供对照，不代表可切 live。"
        ),
    }


def _tripped(rules: Dict[str, Any], stats: Dict[str, int]) -> bool:
    seen = int(stats["auto"]) + int(stats["skip"])
    if seen < int(rules.get("min_sample") or 5):
        return False
    return _rate(stats) > float(rules.get("daily_auto_rate_max") or 0.2)


def _disable(rules: Dict[str, Any], reason: str) -> None:
    rules["enabled"] = False
    rules["circuit_reason"] = reason
    rules["circuit_at"] = time.time()
    _write_rules(rules)
    _append_audit({"event": "circuit_open", "reason": reason, "level": "critical"})
    logger.error("h4 circuit open: %s", reason)


def h4_rules_view(*, role: str) -> Dict[str, Any]:
    if not (role or "").strip():
        return {"ok": False, "reason": "identity_missing", "writable": False}
    try:
        if sandbox_switch_on():
            from core.apps.org.service.org_h4_seed import ensure_approval_rules_seed

            ensure_approval_rules_seed()
    except Exception:
        logger.debug("h4 seed ensure skipped", exc_info=True)
    rules = load_rules()
    stats = _today_stats()
    delta = sandbox_live_delta(stats)
    return {
        "ok": True,
        "writable": False,
        "layer": "h4_rules",
        "enabled": bool(rules.get("enabled")),
        "sandbox_ok": _sandbox_ok(rules),
        "sandbox_only": bool(rules.get("sandbox_only", True)),
        "confidence_min": rules.get("confidence_min"),
        "domains": rules.get("domains"),
        "daily_auto_rate_max": rules.get("daily_auto_rate_max"),
        "today_auto": stats["auto"],
        "today_rate": round(_rate(stats), 4) if (stats["auto"] + stats["skip"]) else None,
        "circuit_open": bool(rules.get("circuit_reason")) and not rules.get("enabled"),
        "circuit_reason": rules.get("circuit_reason") or "",
        "io_mode": delta["io_mode"],
        "sandbox_pass_rate": delta["sandbox_pass_rate"],
        "live_refused_today": delta["live_refused_today"],
        "live_auto_pass_rate": delta["live_auto_pass_rate"],
        "auto_applied_shadow": False,
        "called_apply": False,
        "m4_claim_allowed": False,
        "delta_note": delta["delta_note"],
        "authority_note": "沙箱无规则文件时开关打开。live 拒绝。自动只改队列状态，不写活本体。差异看板只读，不是灰度。",
    }


def h4_auto_audit(*, role: str, limit: int = 50) -> Dict[str, Any]:
    role_n = (role or "").strip().lower()
    if not role_n:
        return {"ok": False, "reason": "identity_missing", "writable": False}
    if role_n not in _AUDIT_ROLES:
        return {"ok": False, "reason": "audit_forbidden", "writable": False}
    lim = min(100, max(1, int(limit or 50)))
    rows = [r for r in _read_audit() if r.get("day") == _day()]
    return {
        "ok": True,
        "writable": False,
        "items": rows[-lim:],
        "count": len(rows),
        "role": role_n,
    }


def _eligible_ticket(ticket: Dict[str, Any], rules: Dict[str, Any]) -> str:
    if str(ticket.get("status") or "") != "pending":
        return "not_pending"
    if ticket.get("applied"):
        return "already_applied"
    domains = set(rules.get("domains") or [])
    left = str(ticket.get("left_domain") or "")
    right = str(ticket.get("right_domain") or "")
    if left != right:
        return "cross_domain"
    if left not in domains:
        return "domain_not_allowed"
    strategies = set(rules.get("exact_strategies") or ["exact"])
    if str(ticket.get("strategy") or "") not in strategies:
        return "not_exact"
    try:
        conf = float(ticket.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    if conf < float(rules.get("confidence_min") or 0.95):
        return "below_threshold"
    if str(ticket.get("suggested") or "merge") not in ("merge", ""):
        return "not_merge"
    return ""


async def _eligible_extraction(row: Dict[str, Any], rules: Dict[str, Any]) -> str:
    if str(row.get("status") or "pending") != "pending":
        return "not_pending"
    domains = set(rules.get("domains") or [])
    did = str(row.get("domain_id") or "")
    if did not in domains:
        return "domain_not_allowed"
    try:
        conf = float(row.get("overall_confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    if conf < float(rules.get("confidence_min") or 0.95):
        return "below_threshold"
    raw = row.get("relations_json") or "[]"
    try:
        rels = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        rels = []
    if isinstance(rels, list):
        for rel in rels:
            if not isinstance(rel, dict):
                continue
            other = str(rel.get("domain_id") or rel.get("target_domain") or "")
            if other and other != did:
                return "cross_domain"
    return ""


async def run_h4_auto_pass(*, role: str, domain_id: str = "it-ops") -> Dict[str, Any]:
    """Pass eligible queue items. Does not write live YAML or edges."""
    role_n = (role or "").strip().lower()
    if not role_n:
        return {"ok": False, "reason": "identity_missing", "writable": False}
    if role_n not in _SCAN_ROLES:
        return {"ok": False, "reason": "scan_forbidden", "writable": False}

    rules = load_rules()
    if not rules.get("enabled"):
        return {
            "ok": False,
            "reason": "rules_disabled",
            "enabled": False,
            "called_apply": False,
            "writable": False,
        }
    if not _sandbox_ok(rules):
        _append_audit(
            {
                "event": "live_refused",
                "reason": "live_io_forbidden",
                "io_mode": _io_mode(),
                "domain_id": (domain_id or "").strip() or "it-ops",
            }
        )
        return {
            "ok": False,
            "reason": "live_io_forbidden",
            "called_apply": False,
            "writable": False,
            "auto_applied_shadow": False,
            "live_refused": True,
        }

    stats = _today_stats()
    if _tripped(rules, stats):
        _disable(rules, "daily_auto_rate")
        return {
            "ok": False,
            "reason": "circuit_open",
            "called_apply": False,
            "writable": False,
        }

    from core.apps.fde.service.k_wave_arbit import decide_ticket, list_tickets
    from core.apps.fde.service.k_wave_signal import confirm_extraction_k1, live_yaml_hash

    did = (domain_id or "").strip() or "it-ops"
    before = live_yaml_hash(did)
    passed: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    tickets = list_tickets(status="pending", domain_id=did).get("items") or []
    for ticket in tickets:
        why = _eligible_ticket(ticket, rules)
        tid = str(ticket.get("ticket_id") or "")
        if why:
            skipped.append({"kind": "arbitration", "id": tid, "reason": why})
            _append_audit({"event": "skip", "kind": "arbitration", "id": tid, "reason": why})
            continue
        out = decide_ticket(tid, decision="merge", actor=_ACTOR, note="h4 queue pass; not an edge")
        if not out.get("ok"):
            skipped.append({"kind": "arbitration", "id": tid, "reason": out.get("reason")})
            _append_audit({"event": "skip", "kind": "arbitration", "id": tid, "reason": out.get("reason")})
            continue
        body = out.get("ticket") or {}
        if body.get("applied") or body.get("edge_written"):
            _disable(rules, "queue_wrote_edge")
            return {
                "ok": False,
                "reason": "contract_breach",
                "called_apply": False,
                "writable": False,
            }
        passed.append({"kind": "arbitration", "id": tid, "status": body.get("status")})
        _append_audit({"event": "auto_pass", "kind": "arbitration", "id": tid})
        stats = _today_stats()
        if _tripped(rules, stats):
            _disable(rules, "daily_auto_rate")
            break

    if rules.get("enabled"):
        try:
            from core.harness.knowledge_pipeline.extractor import PendingExtractionStore

            store = PendingExtractionStore()
            await store.initialize()
            rows = await store.list_pending(did)
        except Exception:
            logger.debug("h4 extractions unavailable", exc_info=True)
            rows = []
        for row in rows:
            if not rules.get("enabled"):
                break
            why = await _eligible_extraction(row, rules)
            eid = str(row.get("extraction_id") or "")
            if why:
                skipped.append({"kind": "extraction", "id": eid, "reason": why})
                _append_audit({"event": "skip", "kind": "extraction", "id": eid, "reason": why})
                continue
            confirmed = await confirm_extraction_k1(eid, actor=_ACTOR, store=store)
            if not confirmed.get("ok") or confirmed.get("wrote_live_yaml"):
                _disable(rules, "extraction_wrote_yaml")
                return {
                    "ok": False,
                    "reason": "contract_breach",
                    "called_apply": False,
                    "writable": False,
                }
            passed.append({"kind": "extraction", "id": eid, "status": "confirmed"})
            _append_audit({"event": "auto_pass", "kind": "extraction", "id": eid})
            stats = _today_stats()
            if _tripped(rules, stats):
                _disable(rules, "daily_auto_rate")
                break

    after = live_yaml_hash(did)
    if before != after:
        _disable(load_rules(), "live_yaml_changed")
        return {
            "ok": False,
            "reason": "contract_breach",
            "yaml_unchanged": False,
            "called_apply": False,
            "writable": False,
        }

    fresh = load_rules()
    return {
        "ok": True,
        "writable": False,
        "enabled": bool(fresh.get("enabled")),
        "passed": passed,
        "skipped": skipped,
        "yaml_unchanged": True,
        "called_apply": False,
        "circuit_open": not bool(fresh.get("enabled")),
        "today_rate": round(_rate(_today_stats()), 4),
        "authority_note": "只改队列状态。未写活本体，未写边。",
    }
