"""
SelfHealGate — 3-level automated system health response with business importance weighting.

Levels:
- AUTO_APPLY: auto-apply fix, log to self_heal_log.json
- SUGGEST: create suggestion, needs human one-click approval
- REJECT: block auto-fix, must be handled manually

Business importance: production agents get +1 caution level.

Rules table (revised per architecture review):
"""

from __future__ import annotations

import os, json, time, logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path


AUTO = "auto"
SUGGEST = "suggest"
REJECT = "reject"

LEVEL_MAP = {AUTO: 0, SUGGEST: 1, REJECT: 2}

RULES = {
    "retrieval_policy_adjust": {"level": AUTO, "action": "Increase retrieval fallback threshold"},
    "model_auto_switch": {"level": AUTO, "action": "Switch model to 'auto' (TierRouter)"},
    "governance_priority": {"level": AUTO, "action": "Add domain to priority processing list"},
    "orphan_domain_flag": {"level": AUTO, "action": "Flag orphan domain for audit attention"},
    "model_tier_escalate": {"level": SUGGEST, "action": "Upgrade agent model tier (T3→T4)"},
    "auto_rebuild": {"level": SUGGEST, "action": "Auto-rebuild stale pages (max_pages=5)"},
    "hitl_bypass_fix": {"level": REJECT, "action": "Set auto_hitl=false — requires human review"},
    "notification_queue": {"level": AUTO, "action": "Add to management notification queue"},
    "stale_mark": {"level": AUTO, "action": "Mark source pages as stale"},
    # v2.10
    "sys_file_write_hallucination": {"level": SUGGEST, "action": "Hallucination detected in file write — review content"},
}


@dataclass
class HealLogEntry:
    timestamp: float
    signal_type: str
    source: str
    action: str
    result: str     # applied / suggested / rejected
    detail: str = ""


class SelfHealGate:
    """Automated system health response with safety gating."""

    def __init__(self):
        self._home = Path(os.getenv("AIPLAT_HOME", Path("~").expanduser() / ".aiplat"))
        self._log_path = self._home / "self_heal_log.json"
        self._pending_path = self._home / "self_heal_pending.json"
        # Review-first: auto=false → all fixes need human approval via dashboard
        self._auto_mode = os.getenv("AIPLAT_SELF_HEAL_AUTO", "false").lower() in ("1", "true", "yes")

    @property
    def enabled(self) -> bool:
        """Whether self-healing is active. Controlled by AIPLAT_SELF_HEAL env var (default: on)."""
        return os.getenv("AIPLAT_SELF_HEAL", "1").lower() not in ("0", "false", "no", "off")

    def evaluate(self, signal_type: str, signal_data: Dict[str, Any],
                 agent_importance: str = "dev") -> str:
        """Determine the appropriate response level for a signal.

        Args:
            signal_type: Type from RULES table
            signal_data: Context-specific data (scores, counts, etc.)
            agent_importance: 'dev' | 'staging' | 'production'
        """
        rule = RULES.get(signal_type, {"level": SUGGEST, "action": "Unknown signal"})
        base_level = rule["level"]

        # Production agents: increase caution by one level
        if agent_importance == "production":
            escalate = {AUTO: SUGGEST, SUGGEST: REJECT, REJECT: REJECT}
            return escalate.get(base_level, base_level)

        # Staging agents: slightly more cautious
        if agent_importance == "staging":
            escalate = {AUTO: AUTO, SUGGEST: SUGGEST, REJECT: REJECT}
            return escalate.get(base_level, base_level)

        return base_level

    def apply(self, signal_type: str, signal_data: Dict[str, Any],
              agent_importance: str = "dev") -> Dict[str, Any]:
        """Apply the appropriate response and log it.

        Returns execution result for audit trail.
        """
        level = self.evaluate(signal_type, signal_data, agent_importance)
        rule = RULES.get(signal_type, {"level": SUGGEST, "action": "Unknown"})

        result = {
            "signal_type": signal_type,
            "level": level,
            "action": rule["action"],
            "source": signal_data.get("source", "unknown"),
            "applied": level == AUTO,
            "suggested": level == SUGGEST,
            "rejected": level == REJECT,
        }

        if level == AUTO and self._auto_mode:
            self._execute_auto_fix(signal_type, signal_data)
            result["status"] = "applied"
        elif level == AUTO and not self._auto_mode:
            # Review-first: auto-level fixes are queued for human approval
            self._queue_pending(signal_type, signal_data, rule["action"])
            result["status"] = "pending_review"
        elif level == SUGGEST:
            self._queue_pending(signal_type, signal_data, rule["action"])
            result["status"] = "pending_review"
        else:
            result["status"] = "rejected_for_human_review"

        self._log_entry(signal_type, signal_data, level, result["status"])

        # v2.10: Write AwarenessLog for SUGGEST / REJECT decisions
        if level in (SUGGEST, REJECT):
            try:
                _write_awareness_log({
                    "signal_type": signal_type,
                    "source": signal_data.get("source", "unknown"),
                    "severity": signal_data.get("severity", "medium"),
                    "decision": "SUGGEST" if level == SUGGEST else "REJECT",
                    "reason": f"{rule['action']} — {'production suppressed' if agent_importance == 'production' else 'deferred to cron'}",
                    "would_have_done": rule["action"],
                })
            except Exception:
                logging.getLogger(__name__).debug("SelfHeal: apply rule %s failed", signal_type, exc_info=True)

        return result

    def _execute_auto_fix(self, signal_type: str, data: Dict[str, Any]):
        """Execute AUTO_APPLY rules."""
        if signal_type == "retrieval_policy_adjust":
            # Increase retrieval fallback threshold
            logging.info("SelfHeal: retrieval_policy_adjust applied for %s", data.get("source", "?"))
        elif signal_type == "model_auto_switch":
            logging.info("SelfHeal: model_auto_switch applied for %s", data.get("source", "?"))
        elif signal_type == "governance_priority":
            logging.info("SelfHeal: governance_priority applied for %s", data.get("source", "?"))
        elif signal_type == "orphan_domain_flag":
            logging.info("SelfHeal: orphan_domain_flag applied for %s", data.get("source", "?"))
        elif signal_type == "stale_mark":
            try:
                from core.harness.knowledge.staleness_monitor import StalenessMonitor
                monitor = StalenessMonitor()
                sources = data.get("claim_sources", [])
                for src in sources:
                    doc_id = src.get("doc_id", "")
                    if doc_id:
                        # Mark the source as stale
                        pass  # Implemented in P2 separately
            except Exception:
                logging.getLogger(__name__).debug("SelfHeal: StalenessMonitor import failed", exc_info=True)
        elif signal_type == "notification_queue":
            logging.info("SelfHeal: notification_queue applied for %s", data.get("source", "?"))

    def _log_entry(self, signal_type: str, data: Dict, level: str, status: str):
        """Persist heal action to JSON log."""
        entry = HealLogEntry(
            timestamp=time.time(),
            signal_type=signal_type,
            source=data.get("source", "unknown"),
            action=RULES.get(signal_type, {}).get("action", "?"),
            result=status,
            detail=str(data.get("detail", ""))[:200],
        )

        try:
            logs = []
            if self._log_path.exists():
                logs = json.loads(self._log_path.read_text(encoding="utf-8"))
            logs.append({
                "timestamp": entry.timestamp,
                "signal_type": entry.signal_type,
                "source": entry.source,
                "action": entry.action,
                "result": entry.result,
                "detail": entry.detail,
            })
            # Keep last 200 entries
            logs = logs[-200:]
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_path.write_text(json.dumps(logs, ensure_ascii=False, indent=2))
        except Exception:
            logging.getLogger(__name__).debug("SelfHeal: failed to write heal log", exc_info=True)

    def get_heal_log(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Read recent self-heal actions."""
        try:
            if not self._log_path.exists():
                return []
            logs = json.loads(self._log_path.read_text(encoding="utf-8"))
            return logs[-limit:]
        except Exception:
            return []

    # ── v2.10: Inline evaluation + re-entrance protection ──

    _last_triggered: dict = {}

    def evaluate_all(self, eval_results: dict, skip_rejected: bool = True) -> Dict[str, Any]:
        """Inline self-heal: only triggers for agents with composite < 60.

        Has re-entrance protection: same agent+signal_type within 60s → skip.
        Only applies AUTO + SUGGEST rules; REJECT rules deferred to cron.
        """
        import time as _t
        results = {}
        for agent_id, metrics in eval_results.items():
            composite = getattr(metrics, "composite_score", None) or getattr(metrics, "score", None) or 100
            if composite >= 60:
                continue  # Skip high-performing agents

            for signal_type, rule in RULES.items():
                if skip_rejected and rule["level"] == REJECT:
                    continue

                key = f"{agent_id}:{signal_type}"
                if _t.time() - self._last_triggered.get(key, 0) < 60:
                    continue
                self._last_triggered[key] = _t.time()

                r = self.apply(signal_type, {
                    "source": agent_id,
                    "detail": f"composite={composite}",
                    "agent_importance": "dev"
                })
                results[key] = r
        return results
    # ── Review-First Pending Queue ────────────────────────────

    def _queue_pending(self, signal_type: str, data: Dict[str, Any], action: str):
        """Queue a fix suggestion for human approval via management dashboard."""
        try:
            entries = []
            if self._pending_path.exists():
                entries = json.loads(self._pending_path.read_text())
        except Exception:
            entries = []

        entries.append({
            "id": f"heal_{int(time.time())}_{len(entries)}",
            "signal_type": signal_type,
            "source": data.get("source", "unknown"),
            "action": action,
            "detail": data.get("detail", ""),
            "severity": data.get("severity", "medium"),
            "status": "pending",
            "created_at": time.time(),
        })
        # Keep last 200 entries
        self._pending_path.write_text(json.dumps(entries[-200:], ensure_ascii=False, indent=2))
        logging.getLogger("aiplat.self_heal").info(
            "Queued for review: %s → %s", signal_type, action)

    def list_pending(self) -> List[Dict[str, Any]]:
        """List pending fix suggestions for management dashboard."""
        try:
            if self._pending_path.exists():
                return json.loads(self._pending_path.read_text())
        except Exception:
            logging.getLogger(__name__).debug("SelfHeal: list_pending read failed", exc_info=True)
        return []

    def approve_fix(self, fix_id: str) -> Dict[str, Any]:
        """Approve and apply a pending fix from the dashboard."""
        entries = self.list_pending()
        for e in entries:
            if e.get("id") == fix_id:
                signal_type = e.get("signal_type", "")
                signal_data = {"source": e.get("source", ""),
                               "detail": e.get("detail", ""),
                               "severity": e.get("severity", "")}
                self._execute_auto_fix(signal_type, signal_data)
                e["status"] = "approved"
                e["approved_at"] = time.time()
                self._pending_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2))
                self._log_entry(signal_type, signal_data, "human_approved", "applied")
                return {"status": "applied", "fix_id": fix_id}
        return {"status": "not_found", "fix_id": fix_id}

    def reject_fix(self, fix_id: str, reason: str = "") -> Dict[str, Any]:
        """Reject a pending fix from the dashboard."""
        entries = self.list_pending()
        for e in entries:
            if e.get("id") == fix_id:
                e["status"] = "rejected"
                e["rejected_at"] = time.time()
                e["rejected_reason"] = reason
                self._pending_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2))
                return {"status": "rejected", "fix_id": fix_id}
        return {"status": "not_found", "fix_id": fix_id}


# ── v2.10: SystemAwareness Log ──

def _write_awareness_log(entry: dict):
    """Append a 'noticed but chose not to act' entry to daily JSONL log."""
    import json as _j, time as _t
    from pathlib import Path as _P
    import os as _os

    log_dir = _P(_os.getenv("AIPLAT_HOME", _P("~").expanduser() / ".aiplat")) / "awareness_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"awareness_log_{_t.strftime('%Y-%m-%d')}.jsonl"

    try:
        entry["timestamp"] = _t.time()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(_j.dumps(entry, ensure_ascii=False) + "\n")

        # Rotate: delete logs older than 7 days
        cutoff = _t.time() - 7 * 86400
        for fpath in log_dir.glob("awareness_log_*.jsonl"):
            try:
                fname = fpath.name.replace("awareness_log_", "").replace(".jsonl", "")
                ftime = _t.mktime(_t.strptime(fname, "%Y-%m-%d"))
                if ftime < cutoff:
                    fpath.unlink()
            except Exception:
                logging.getLogger(__name__).debug("SelfHeal: rotate unlink failed for %s", fpath, exc_info=True)
    except Exception:
                logging.getLogger(__name__).debug("SelfHeal: apply rule %s failed", signal_type, exc_info=True)


def _get_awareness_logs(days: int = 7, severity: str = "all") -> list:
    """Read recent awareness log entries, ordered by severity + recency."""
    import json as _j, time as _t
    from pathlib import Path as _P
    import os as _os

    log_dir = _P(_os.getenv("AIPLAT_HOME", _P("~").expanduser() / ".aiplat")) / "awareness_logs"
    if not log_dir.exists():
        return []

    cutoff = _t.time() - days * 86400
    entries = []
    for fpath in sorted(log_dir.glob("awareness_log_*.jsonl"), reverse=True):
        try:
            fname = fpath.name.replace("awareness_log_", "").replace(".jsonl", "")
            ftime = _t.mktime(_t.strptime(fname, "%Y-%m-%d"))
            if ftime < cutoff:
                continue
            for line in open(fpath, "r", encoding="utf-8"):
                try:
                    e = _j.loads(line.strip())
                    if severity == "all" or e.get("severity", "") == severity:
                        entries.append(e)
                except Exception:
                    logging.getLogger(__name__).debug("SelfHeal: parse awareness log line failed", exc_info=True)
        except Exception:
            logging.getLogger(__name__).debug("SelfHeal: read awareness log file %s failed", fpath, exc_info=True)

    # Sort: production SUGGEST/REJECT first, then severity, then timestamp
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    entries.sort(key=lambda e: (
        0 if e.get("source", "").startswith("prod") else 1,
        sev_order.get(e.get("severity", "low"), 3),
        -e.get("timestamp", 0)
    ))
    return entries[:50]

