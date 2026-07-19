u"""
SLA Monitor — 时序触发器后台监控 (v2.6).

Periodically scans all domain instances for time_elapsed triggers.
Reads state_history.db timestamps, triggers state transitions on timeout.
Thread-safe: uses read-only snapshots, never directly mutates active GraphIndex.
"""
from __future__ import annotations

import logging
import os as _os
import sqlite3 as _sqlite3
import threading
import time as _time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("sla_monitor")

_INTERVAL_SECONDS = float(_os.getenv("AIPLAT_SLA_SCAN_INTERVAL", "60"))
_running = False
_thread: Optional[threading.Thread] = None


def start(interval_seconds: float = None) -> None:
    u"""Start the background SLA monitor thread."""
    global _running, _thread
    if _running:
        return
    _running = True
    iv = interval_seconds if interval_seconds is not None else _INTERVAL_SECONDS
    _thread = threading.Thread(target=_scan_loop, args=(iv,), daemon=True, name="sla-monitor")
    _thread.start()
    logger.info("SLA monitor started (interval=%ss)", iv)


def stop() -> None:
    u"""Stop the background SLA monitor thread."""
    global _running
    _running = False
    logger.info("SLA monitor stopped")


def scan_once(ontologies_dir: str = "") -> List[Dict[str, Any]]:
    u"""Run one scan cycle, returning triggered transitions."""
    triggered = []
    base = _os.path.expanduser(ontologies_dir or _os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))
    base_path = Path(base)
    if not base_path.exists():
        return triggered

    import yaml
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml

    for yaml_file in sorted(base_path.glob("*.yaml")):
        domain_id = yaml_file.stem

        try:
            domain = load_ontology_from_yaml(str(yaml_file))
        except Exception:
            continue

        for cls in domain.classes:
            transitions = getattr(cls, "transitions", []) or []
            time_triggers = [t for t in transitions
                             if isinstance(t.get("trigger", {}), dict)
                             and t["trigger"].get("type") == "time_elapsed"]
            if not time_triggers:
                continue

            for trans in time_triggers:
                triggered_instances = _check_class_timeout(
                    domain_id, cls.label, cls.uri.split("#")[-1], trans
                )
                triggered.extend(triggered_instances)

    return triggered


def _check_class_timeout(
    domain_id: str,
    class_label: str,
    class_name: str,
    transition: Dict[str, Any],
) -> List[Dict[str, Any]]:
    u"""Check all instances of a class for time_elapsed threshold violation."""
    trigger = transition.get("trigger", {})
    threshold_s = float(trigger.get("state_age_seconds", 0))
    threshold_d = float(trigger.get("state_age_days", 0))
    if not threshold_s and not threshold_d:
        return []
    if threshold_d and not threshold_s:
        threshold_s = threshold_d * 86400.0

    from_states = transition.get("from", [])
    if isinstance(from_states, str):
        from_states = [from_states]
    to_state = transition.get("to", "")

    db_path = _os.path.expanduser("~/.aiplat/state_changes.db")
    if not _os.path.exists(db_path):
        return []

    results = []
    try:
        conn = _sqlite3.connect(db_path, timeout=5.0)
        cursor = conn.execute(
            "SELECT entity_name, from_state, to_state, timestamp FROM state_changes WHERE domain_id = ? AND class_name = ? ORDER BY id DESC",
            (domain_id, class_label),
        )
        seen = set()
        for row in cursor:
            entity_name = row[0]
            if entity_name in seen:
                continue
            seen.add(entity_name)
            current_state = row[2] or row[1] or ""
            if current_state not in from_states:
                continue
            elapsed = _time.time() - float(row[3])
            if elapsed >= threshold_s:
                results.append({
                    "domain_id": domain_id,
                    "entity_name": entity_name,
                    "class_name": class_label,
                    "from_state": current_state,
                    "to_state": to_state,
                    "elapsed_seconds": round(elapsed),
                    "threshold_seconds": int(threshold_s),
                    "trigger_type": "time_elapsed",
                    "transition_desc": str(transition.get("description", "")),
                })
        conn.close()
    except Exception as e:
        logger.warning("SLA scan failed for %s/%s: %s", domain_id, class_label, e)

    return results


def _scan_loop(interval: float) -> None:
    u"""Background scan loop — runs scan_once() every interval seconds."""
    while _running:
        try:
            triggered = scan_once()
            if triggered:
                logger.info("SLA monitor: %d timeout(s) detected", len(triggered))
                for t in triggered:
                    from core.harness.infrastructure.gateway.fde_notifier import _notify_safe
                    _notify_safe("SLA 违约告警", t.get("domain_id", ""), t)
        except Exception as e:
            logger.warning("SLA monitor error: %s", e, exc_info=True)
        _time.sleep(interval)
