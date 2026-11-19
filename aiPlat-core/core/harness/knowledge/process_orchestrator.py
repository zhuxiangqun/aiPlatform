u"""
Process Orchestrator — 跨实体 + 跨域业务流程编排 (v2.7).

Loads ``processes`` key from domain YAML and orchestrates multi-entity business flows:
  - order_fulfillment: Order → PickingTask → Shipment → Invoice

Each step specifies: entity_class, target_state, depends_on, auto_create, on_failure.

Cross-domain support:
  - ``domains: [...]`` declares which domains the process spans.
  - ``domain: xxx`` on individual steps overrides the default for per-step routing.
  - Steps without ``domain`` use the first domain in the process's ``domains`` list.
  - Cross-domain processes are loaded lazily from YAML files.

Process instances tracked in SQLite (process_instances table) in state_changes.db.
"""
from __future__ import annotations
from core.utils.paths import get_aiplat_home, get_aiplat_data_dir

from core.harness.knowledge.domain_router import DomainRouter
import json as _json
import logging
import os as _os
import sqlite3 as _sqlite3
import time as _time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("process_orchestrator")


def _db_path() -> str:
    """与 state_history 共用库，避免 process_instances 与状态变更分裂。

    Returns:
        state_changes.db 绝对路径。
    """
    # 为什么：N09 K12 — 旧实现旁路 get_aiplat_data_dir，与 K11 监控库不一致
    from core.harness.ontology_engine.state_history import _db_path as _hist_db

    return _hist_db()


def _tid(tenant_id: str | None) -> str:
    return (tenant_id or "").strip() or DomainRouter.default_tenant()


def _ensure_schema():
    """Ensure process_instances schema including physical tenant_id."""
    conn = _sqlite3.connect(_db_path(), timeout=5.0)
    # 为什么：N09 K12/K51 — DDL DEFAULT 与回填值均走 default_tenant SSOT
    default_tid = DomainRouter.default_tenant()
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS process_instances (
            id TEXT PRIMARY KEY,
            process_name TEXT NOT NULL,
            domain_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL DEFAULT '{default_tid}',
            current_step INTEGER DEFAULT 0,
            starter_entity TEXT NOT NULL,
            status TEXT DEFAULT 'running',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
    """)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(process_instances)").fetchall()}
    if "tenant_id" not in cols:
        conn.execute(
            f"ALTER TABLE process_instances ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '{default_tid}'"
        )
    conn.execute(
        "UPDATE process_instances SET tenant_id = ? "
        "WHERE tenant_id IS NULL OR trim(tenant_id) = ''",
        (default_tid,),
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_proc_domain ON process_instances(domain_id, process_name)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_proc_tenant_domain ON process_instances(tenant_id, domain_id)"
    )
    conn.commit()
    conn.close()


def load_processes(domain_yaml_raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Load process definitions from domain YAML raw dict.

    Args:
        domain_yaml_raw: domain_yaml_raw 参数。
    """
    raw_processes = domain_yaml_raw.get("processes", {})
    if not isinstance(raw_processes, dict):
        return []
    result: List[Dict[str, Any]] = []
    for pname, pdef in raw_processes.items():
        pdef = dict(pdef)
        pdef["name"] = pname
        domains = pdef.get("domains", [])
        default_domain = domains[0] if domains else ""
        steps = pdef.get("steps", [])
        for step in steps:
            step["default_domain"] = default_domain
        result.append(pdef)
    return result


def start_process(
    process_name: str,
    domain_id: str,
    starter_entity: str,
    process_def: Dict[str, Any],
    *,
    tenant_id: str = DomainRouter.default_tenant(),
) -> str:
    """Start a new process instance. Returns instance_id.

    Args:
        process_name: process_name 参数。
        domain_id: domain 标识。
        starter_entity: starter_entity 参数。
        process_def: process_def 参数。
        tenant_id: 租户；写入 process_instances 物理列（N09 K12）。
    """
    _ensure_schema()
    tid = _tid(tenant_id)
    pid = f"{process_name}:{starter_entity}:{int(_time.time())}"
    conn = _sqlite3.connect(_db_path(), timeout=5.0)
    now = _time.time()
    conn.execute(
        "INSERT INTO process_instances (id, process_name, domain_id, tenant_id, current_step, starter_entity, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (pid, process_name, domain_id, tid, 0, starter_entity, "running", now, now),
    )
    conn.commit()
    conn.close()
    logger.info("Process %s started: %s", process_name, pid)
    return pid


def check_step_completion(
    domain_id: str,
    entity_class: str,
    entity_name: str,
    new_state: str,
) -> List[Dict[str, Any]]:
    """Called after state_machine completes.

    Args:
        domain_id: domain 标识。
        entity_class: entity_class 参数。
        entity_name: entity_name 参数。
        new_state: new_state 参数。
    """
    base = _os.path.expanduser(_os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))

    results: List[Dict[str, Any]] = []
    _ensure_schema()
    conn = _sqlite3.connect(_db_path(), timeout=5.0)

    if not _os.path.isdir(base):
        conn.close()
        return results

    import yaml
    for fname in sorted(_os.listdir(base)):
        if not fname.endswith(".yaml"):
            continue
        yaml_path = _os.path.join(base, fname)
        yaml_domain = fname[:-5]

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except Exception:
            continue

        processes = raw.get("processes", {})
        for pname, pdef in processes.items():
            steps = pdef.get("steps", [])
            if not steps:
                continue

            proc_domains = pdef.get("domains", [yaml_domain])
            first_domain = proc_domains[0] if proc_domains else yaml_domain

            # Only process if at least one step targets this domain_id
            any_step_relevant = any(
                step.get("domain", first_domain) == domain_id
                for step in steps
            )
            if not any_step_relevant:
                continue

            cursor = conn.execute(
                "SELECT id, current_step FROM process_instances WHERE process_name = ? AND status = 'running'",
                (pname,),
            )
            for row in cursor:
                pid, current_step = row[0], row[1]
                for idx, step in enumerate(steps):
                    if idx != current_step:
                        continue

                    step_domain = step.get("domain", first_domain)
                    if step_domain != domain_id:
                        continue

                    if step.get("entity_class") != entity_class:
                        continue

                    target = step.get("target_state", "")
                    if target and target != new_state:
                        continue

                    next_step = steps[idx + 1] if idx + 1 < len(steps) else None
                    results.append({
                        "process_id": pid,
                        "process_name": pname,
                        "step_label": step.get("label", ""),
                        "next_step": next_step.get("label", "") if next_step else None,
                        "auto_create": next_step.get("auto_create", False) if next_step else False,
                        "next_entity_class": next_step.get("entity_class", "") if next_step else "",
                        "new_step_index": idx + 1,
                    })

                    if next_step:
                        conn.execute(
                            "UPDATE process_instances SET current_step = ?, updated_at = ? WHERE id = ?",
                            (idx + 1, _time.time(), pid),
                        )
                        if next_step.get("auto_create"):
                            logger.info("Process %s: auto-create %s for next step", pname, next_step.get("entity_class", ""))

    conn.commit()
    conn.close()
    return results


def get_process_status(
    domain_id: str, process_name: str = "", *, tenant_id: str = DomainRouter.default_tenant()
) -> List[Dict[str, Any]]:
    """Get status of all running process instances.

    Args:
        domain_id: domain 标识。
        process_name: process_name 参数。
        tenant_id: 租户；召回前过滤（N09 K12）。
    """
    _ensure_schema()
    tid = _tid(tenant_id)
    conn = _sqlite3.connect(_db_path(), timeout=5.0)
    if process_name:
        rows = conn.execute(
            "SELECT id, process_name, current_step, starter_entity, status, created_at, updated_at FROM process_instances WHERE tenant_id = ? AND domain_id = ? AND process_name = ? ORDER BY updated_at DESC",
            (tid, domain_id, process_name),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, process_name, current_step, starter_entity, status, created_at, updated_at FROM process_instances WHERE tenant_id = ? AND domain_id = ? ORDER BY updated_at DESC",
            (tid, domain_id),
        ).fetchall()
    conn.close()

    results = []
    for row in rows:
        results.append({
            "id": row[0],
            "process_name": row[1],
            "current_step": row[2],
            "starter_entity": row[3],
            "status": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        })
    return results


def get_bottlenecks(
    domain_id: str, limit: int = 10, *, tenant_id: str = DomainRouter.default_tenant()
) -> List[Dict[str, Any]]:
    """Find process instances stuck at the same step the longest.

    Args:
        domain_id: domain 标识。
        limit: 返回条数上限。
        tenant_id: 租户；召回前过滤（N09 K12）。
    """
    _ensure_schema()
    tid = _tid(tenant_id)
    conn = _sqlite3.connect(_db_path(), timeout=5.0)
    now = _time.time()
    rows = conn.execute(
        "SELECT id, process_name, current_step, starter_entity, updated_at FROM process_instances WHERE tenant_id = ? AND domain_id = ? AND status = 'running' ORDER BY updated_at ASC LIMIT ?",
        (tid, domain_id, limit),
    ).fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "process_name": row[1],
            "current_step": row[2],
            "starter_entity": row[3],
            "stuck_seconds": round(now - row[4]),
        }
        for row in rows
    ]


def load_processes_cross_domain(ontologies_dir: str = "") -> Dict[str, Any]:
    """Load all processes across all domains.

    Args:
        ontologies_dir: ontologies_dir 参数。
    """
    base = _os.path.expanduser(ontologies_dir or _os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))
    result: Dict[str, Any] = {}

    if not _os.path.isdir(base):
        return result

    import yaml
    for fname in sorted(_os.listdir(base)):
        if not fname.endswith(".yaml"):
            continue
        yaml_path = _os.path.join(base, fname)
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except Exception:
            continue

        processes = raw.get("processes", {})
        for pname, pdef in processes.items():
            domains = pdef.get("domains", [])
            if not domains:
                domains = [fname[:-5]]
            result[pname] = {
                "definition": pdef,
                "domains": domains,
                "source_domain": fname[:-5],
            }

    return result
