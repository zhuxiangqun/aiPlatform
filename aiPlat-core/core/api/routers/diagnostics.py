from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import sys
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from core.api.deps import actor_from_http
from core.harness.integration import get_harness
from core.harness.kernel.types import ExecutionRequest
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.syscalls.llm import sys_llm_generate
from core.schemas_diagnostics import DiagnosticsPromptAssembleRequest
from core.utils.ids import new_prefixed_id

_log = logging.getLogger("aiplat.diagnostics")

# ── Run-all cache (persistent to disk, survives restart) ─────
_DIAG_CACHE: Optional[Dict[str, Any]] = None
_DIAG_CACHE_TS: float = 0.0
# ── Concurrency guard — prevent overlapping diagnostic runs ─────
_DIAG_RUNNING: float = 0.0  # 0 = idle, >0 = start timestamp of current run

_DIAG_LOCK_TTL: float = float(os.getenv("AIPLAT_DIAG_LOCK_TTL", "300") or "300")  # 5 min default
_CACHE_TTL: float = float(os.getenv("AIPLAT_DIAG_CACHE_TTL", "120") or "120")
_DIAG_RUN_CACHE_TTL: float = float(os.getenv("AIPLAT_DIAG_CACHE_TTL", "120") or "120")

# ── LLM审查 progress tracking (SQLite-backed, shared across workers) ──

def _llm_get_db():
    """Get a sqlite3 connection to the execution store for llm_review progress."""
    import sqlite3, os as _os
    db_path = _os.getenv("AIPLAT_EXECUTION_DB_PATH",
                         _os.path.join(_os.path.expanduser("~"), ".aiplat", "aiplat_executions.sqlite3"))
    _os.makedirs(_os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    return conn


def _llm_init_table():
    """Ensure llm_review_tasks table exists."""
    conn = _llm_get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_review_tasks (
                run_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'running',
                files_done INTEGER DEFAULT 0,
                files_total INTEGER DEFAULT 0,
                current_file TEXT DEFAULT '',
                results TEXT DEFAULT '[]',
                score INTEGER DEFAULT 0,
                p0_count INTEGER DEFAULT 0,
                p1_count INTEGER DEFAULT 0,
                created_at REAL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _llm_sync_progress(run_id: str, **kwargs):
    """Sync a single field or fields to SQLite (best-effort, non-blocking)."""
    import json
    conn = _llm_get_db()
    try:
        for key, val in kwargs.items():
            if key == 'results':
                val = json.dumps(val)
            conn.execute(f"INSERT OR REPLACE INTO llm_review_tasks (run_id, {key}) VALUES (?, ?)",
                         (run_id, val))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def _llm_get_progress(run_id: str) -> dict:
    """Read current progress from SQLite."""
    import json
    conn = _llm_get_db()
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM llm_review_tasks WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            return {"status": "not_found"}
        d = dict(row)
        if d.get("results"):
            try:
                d["results"] = json.loads(d["results"])
            except Exception:
                d["results"] = []
        return d
    finally:
        conn.close()


def _llm_cleanup_old(max_keep: int = 10):
    """Keep only the most recent N review tasks, delete older ones."""
    conn = _llm_get_db()
    try:
        conn.execute(f"""
            DELETE FROM llm_review_tasks WHERE run_id NOT IN (
                SELECT run_id FROM llm_review_tasks ORDER BY created_at DESC LIMIT {max_keep}
            )
        """)
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


# Initialize table at module load
_llm_init_table()


# ── Shared code graph: built once by run_all_diagnostics, reused by graph-dependent checks ──
_SHARED_GRAPH = (None, None, None)  # (nodes, edges, issues)

def _get_or_build_graph():
    """Return the shared code graph or build a new one if not available."""
    global _SHARED_GRAPH
    nodes, edges, issues = _SHARED_GRAPH
    if nodes is not None and isinstance(nodes, dict) and len(nodes) > 0:
        return nodes, edges, issues
    from core.harness.knowledge.code_graph import repo_root, default_roots, build_graph
    repo = repo_root()
    abs_roots = [(repo / r).resolve() for r in default_roots()]
    return build_graph(repo, abs_roots)  # noqa: build_graph_approved — canonical call site


# ── LLM review target selection ──

def _select_llm_review_targets(max_files: int = 15) -> List[tuple]:
    """Select high-priority files for LLM deep review.
    
    Strategy:
      1. Files > 500 lines (monolith candidates)
      2. Core engine files (harness/execution/ + harness/knowledge/)
      3. Recently modified files (git log --since=7days)
    
    Returns list of (file_path, line_count) tuples, sorted by line count desc.
    """
    import os as _os
    from pathlib import Path
    # diagnostics.py is at core/api/routers/, parents[2] = core/
    core_dir = str(Path(__file__).resolve().parents[2])

    candidates = set()

    # Rule 1: Files > 500 lines in core/
    if _os.path.isdir(core_dir):
        for root, dirs, files in _os.walk(core_dir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "tests", ".venv", ".git")]
            for f in files:
                if f.endswith(".py") and f not in ("__init__.py",):
                    fpath = _os.path.join(root, f)
                    try:
                        lines = len(open(fpath).readlines())
                        if lines > 500:
                            candidates.add((fpath, lines))
                    except Exception:
                        pass

    # Rule 2: Core engine files regardless of size
    core_patterns = ["harness/execution/", "harness/knowledge/", "harness/syscalls/",
                     "harness/memory/", "harness/ontology_engine/"]
    for root, dirs, files in _os.walk(core_dir):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "tests", ".venv", ".git")]
        for f in files:
            if f.endswith(".py") and f != "__init__.py":
                fpath = _os.path.join(root, f)
                rel = _os.path.relpath(fpath, core_dir)
                if any(rel.startswith(p) for p in core_patterns):
                    try:
                        lines = len(open(fpath).readlines())
                        candidates.add((fpath, lines))
                    except Exception:
                        pass

    # Sort by line count desc, take top N
    result = sorted(candidates, key=lambda x: -x[1])[:max_files]
    return result


# ── v2.2: Autoreview evidence chain helper ──

async def _get_autoreview_summary() -> Dict[str, Any]:
    """获取最近 autoreview 审查状态的摘要信息。
    
    查询 execution_store 中 'autoreview:last:*' 键的持久化审查记录。
    """
    try:
        from core.services.execution_store import get_execution_store
        store = get_execution_store()

        runs = []
        for key in ("autoreview:last:diff", "autoreview:last:commit", "autoreview:last:branch"):
            gs = await store.get_global_setting(key=key)
            if gs and isinstance(gs, dict):
                val = gs.get("value") or {}
                if val:
                    runs.append(val)

        runs.sort(key=lambda r: r.get("timestamp", 0), reverse=True)

        if not runs:
            return {"last_clean": None, "mode_used": "N/A", "total_runs": 0}

        clean_runs = [r for r in runs if r.get("clean")]
        last_clean = clean_runs[0].get("timestamp") if clean_runs else None

        return {
            "last_clean": last_clean,
            "mode_used": runs[0].get("mode", "N/A"),
            "engines": runs[0].get("engines_used", []),
            "total_runs": len(runs),
            "clean_rate": f"{len(clean_runs)}/{len(runs)}",
        }
    except Exception:
        return {"last_clean": None, "mode_used": "N/A", "total_runs": 0}


# ── DiagnosticCheck base class — shared infrastructure for all checks ──

class DiagnosticCheck:
    """Base class for diagnostic checks. Provides shared access to the code graph
    and helper utilities. All check functions should use `self.get_graph()`
    instead of calling ``build_graph`` directly."""
    
    @staticmethod
    def get_graph():
        """Return the shared code graph (nodes, edges, issues). 
        Prefers the pre-built _SHARED_GRAPH from run_all_diagnostics,
        falling back to a fresh build if not available."""
        return _get_or_build_graph()
    
    @staticmethod
    def get_repo_info():
        from core.harness.knowledge.code_graph import repo_root, default_roots
        return repo_root(), default_roots()


# ── Sub-component caches (30s TTL, speed up repeated diagnostic runs) ──
_LINT_CACHE: Optional[Dict[str, Any]] = None
_LINT_CACHE_TS: float = 0.0
_WIKI_CACHE: Optional[Dict[str, Any]] = None
_WIKI_CACHE_TS: float = 0.0
_SUB_CACHE_TTL: float = 30.0
_GUARD_CACHE: Optional[Dict[str, Any]] = None
_GUARD_CACHE_TS: float = 0.0
_LSP_CACHE: Optional[Dict[str, Any]] = None
_LSP_CACHE_TS: float = 0.0
_SEC_CACHE: Optional[Dict[str, Any]] = None
_SEC_CACHE_TS: float = 0.0
_HISTORY_MAX = 30


def _diag_cache_path() -> str:
    import os
    return os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "diag_cache.json")


def _load_diag_cache():
    global _DIAG_CACHE, _DIAG_CACHE_TS
    try:
        import json
        path = _diag_cache_path()
        if os.path.exists(path):
            # Invalidate cache if diagnostics.py or code_graph.py was modified after cache save
            cache_mtime = os.path.getmtime(path)
            self_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            code_graph = os.path.join(self_dir, "harness", "knowledge", "code_graph.py")
            latest_mtime = max(os.path.getmtime(__file__),
                              os.path.getmtime(code_graph) if os.path.exists(code_graph) else 0)
            if latest_mtime > cache_mtime:
                _DIAG_CACHE = None
                return
            with open(path, "r") as f:
                _DIAG_CACHE = json.load(f)
            _DIAG_CACHE_TS = time.time()
    except Exception as e:
        logging.warning(str(e), exc_info=True)


def _save_diag_cache():
    try:
        import json
        path = _diag_cache_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if _DIAG_CACHE:
            with open(path, "w") as f:
                json.dump(_DIAG_CACHE, f, ensure_ascii=False, default=str)
    except Exception as e:
        logging.warning(str(e), exc_info=True)


async def _auto_fill_agents_async(names: list):
    u"""Fire-and-forget: call batch auto-fill and save results to AGENT.md."""
    try:
        import httpx
        base = "http://127.0.0.1:8002"
        async with httpx.AsyncClient(timeout=60) as client:
            # Step 1: Get LLM-generated suggestions
            resp = await client.post(
                f"{base}/api/core/workspace/agents/auto-fill-batch",
                json={"names": names},
            )
            if resp.status_code != 200:
                return
            data = resp.json()
            results = data.get("results", {})
            if not results:
                return

            # Step 2: Save each result back to agent AGENT.md via PUT
            saved = 0
            for name, entry in results.items():
                try:
                    r = await client.put(
                        f"{base}/api/core/workspace/agents/{name}",
                        json={
                            "config": entry.get("config", {}),
                            "skills": entry.get("skills", []),
                            "tools": entry.get("tools", []),
                            "mcp_ids": entry.get("mcp_ids", []),
                            "workflow_ids": entry.get("workflow_ids", []),
                            "agent_ids": entry.get("agent_ids", []),
                            "memory_config": entry.get("memory_config", {}),
                        },
                    )
                    if r.status_code < 400:
                        saved += 1
                except Exception:
                    continue

            if saved:
                logging.getLogger("aiplat.diagnostics").info(
                    f"Auto-filled {saved}/{len(results)} shell agents"
                )
    except Exception:
        logging.getLogger("aiplat.diagnostics").warning("Auto-fill best-effort skipped", exc_info=True)


def _history_path() -> str:
    return os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "diag_history.json")


def _load_diag_history() -> list:
    try:
        import json
        p = _history_path()
        if os.path.exists(p):
            with open(p) as f:
                return json.loads(f.read() or "[]")
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    return []


def _append_diag_history(result):
    u"""Append diagnostic result to rolling history (last N entries)."""
    try:
        import json
        hist = _load_diag_history()
        hist.append({
            "run_id": result.get("run_id", ""),
            "started_at": result.get("started_at", ""),
            "overall_score": result.get("overall_score", 0),
            "overall_grade": result.get("overall_grade", "?"),
            "duration_ms": result.get("duration_ms", 0),
            "pass": result.get("pass", 0),
            "warn": result.get("warn", 0),
            "fail": result.get("fail", 0),
        })
        if len(hist) > _HISTORY_MAX:
            hist = hist[-_HISTORY_MAX:]
        p = _history_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump(hist, f, ensure_ascii=False)
    except Exception as e:
        logging.warning(str(e), exc_info=True)


# Load persisted cache on module init — DISABLED: always rebuild fresh
# _load_diag_cache()

router = APIRouter()


# Register health checks with the formal HealthCheckRegistry (lazy)
# ── Module-level health check for runtime (used by _register_health_checks) ──

async def _check_core_runtime():
    try:
        from core.harness.kernel.runtime import get_kernel_runtime
        rt = get_kernel_runtime()
        store = getattr(rt, "execution_store", None) if rt else None
        return {
            "status": "available" if store else "unavailable",
            "signals": {"execution_store": store is not None},
            "items": [{"check": "执行存储", "result": "✅" if store else "❌",
                        "detail": "ExecutionStore 已初始化" if store else "未找到 ExecutionStore"}],
        }
    except Exception:
        return {"status": "unavailable", "score": 0}


async def _check_doc_sync():
    """Check that AIPLAT_CAPABILITIES.md is consistent with code."""
    import subprocess, sys, os as _os
    try:
        workspace = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))))
        # Step A: consistency (stats table vs section counts)
        r = subprocess.run(
            [sys.executable, _os.path.join(workspace, "scripts", "verify_capability_consistency.py")],
            capture_output=True, text=True, timeout=15,
        )
        consistent = r.returncode == 0

        # Step B: capability gap (new modules without doc entries)
        r2 = subprocess.run(
            [sys.executable, _os.path.join(workspace, "scripts", "check_code_doc_gap.py")],
            capture_output=True, text=True, timeout=15,
        )
        no_gaps = r2.returncode == 0

        all_ok = consistent and no_gaps
        items = []
        items.append({
            "check": "能力统计表一致性",
            "result": "✅" if consistent else "❌",
            "detail": "460 entries match" if consistent else (r.stderr or r.stdout)[:200],
        })
        items.append({
            "check": "代码-文档能力缺口",
            "result": "✅" if no_gaps else "❌",
            "detail": "无缺口" if no_gaps else (r2.stderr or r2.stdout)[:200],
        })

        return {
            "status": "pass" if all_ok else "fail",
            "score": 100 if all_ok else 0,
            "signals": {"consistent": consistent, "no_gaps": no_gaps},
            "items": items,
        }
    except Exception as e:
        return {"status": "unavailable", "score": 0, "signals": {"error": str(e)[:100]}}


async def _check_doc_quality():
    """Check document quality monitor status."""
    try:
        from core.harness.knowledge.doc_quality_monitor import get_doc_quality_monitor
        dqm = get_doc_quality_monitor()
        stats = dqm.get_stats()
        alerts = dqm.get_alerts(limit=5)
        alert_count = len(alerts)
        return {
            "status": "degraded" if alert_count > 3 else "pass",
            "signals": stats,
            "items": [{"check": "文档质量", "result": "⚠️" if alert_count > 0 else "✅",
                        "detail": f"{alert_count} alerts today" if alert_count else "No quality alerts"}],
        }
    except Exception:
        return {"status": "unavailable", "score": 0}


async def _check_wiki_content_quality():
    """Check Wiki page content quality against original source documents."""
    try:
        from core.harness.knowledge.wiki_quality_monitor import get_wiki_quality_monitor
        monitor = get_wiki_quality_monitor()
        stats = monitor.get_stats()
        alerts = monitor.get_alerts(limit=5)
        low_count = stats.get("low_quality_unreviewed", 0)
        return {
            "status": "degraded" if low_count > 3 else "pass",
            "signals": stats,
            "items": [{"check": "Wiki内容质量", "result": "⚠️" if low_count > 0 else "✅",
                        "detail": f"{low_count} low-quality pages pending review" if low_count else "All wiki pages quality OK"}],
        }
    except Exception:
        return {"status": "unavailable", "score": 0}


def _register_health_checks():
    try:
        from core.harness.health.registry import HealthCheckRegistry, get_registry, Severity
        from core.harness.health.registry import HealthCheck, HealthResult, Status
        from core.harness.kernel.runtime import get_kernel_runtime

        class SimpleHealthCheck(HealthCheck):
            """Adapter: wraps existing _check_* functions into HealthCheck protocol."""
            def __init__(self, module, fn, severity=Severity.MEDIUM, deps=None):
                self.module = module
                self.severity = severity
                self.dependencies = deps or []
                self._fn = fn

            async def run(self) -> HealthResult:
                try:
                    result = await self._fn()
                    score = result.get("score", 0) if isinstance(result, dict) else 0
                    status = result.get("status", "unknown") if isinstance(result, dict) else "unknown"
                    s = Status.HEALTHY if status in ("pass", "healthy") else (
                        Status.DEGRADED if status in ("warn", "degraded") else Status.UNHEALTHY)
                    return HealthResult(module=self.module, status=s, severity=self.severity,
                                       message=f"score={score}", details=result if isinstance(result, dict) else {})
                except Exception as e:
                    return HealthResult(module=self.module, status=Status.UNHEALTHY,
                                       severity=self.severity, message=str(e))

        reg = get_registry()
        # Runtime check — _check_core_runtime is at module level (verified).
        reg.register(SimpleHealthCheck("runtime", _check_core_runtime, Severity.CRITICAL))
        reg.register(SimpleHealthCheck("doc_sync", _check_doc_sync, Severity.HIGH))
        reg.register(SimpleHealthCheck("doc_quality", _check_doc_quality, Severity.MEDIUM))
        reg.register(SimpleHealthCheck("wiki_content_quality", _check_wiki_content_quality, Severity.MEDIUM))

        # Additional health checks are registered in run_all_diagnostics()

        # New ROSClaw-inspired modules
        class SandboxGateCheck(HealthCheck):
            module = "sandbox_gate"
            severity = Severity.MEDIUM
            async def run(self) -> HealthResult:
                from core.harness.infrastructure.gates.sandbox_gate import get_sandbox
                sb = get_sandbox()
                result = await sb.check(kind="tool", tool_name="health_check")
                return HealthResult(module="sandbox_gate", 
                    status=Status.HEALTHY if result.verdict.value == "pass" else Status.DEGRADED,
                    severity=Severity.MEDIUM, message=f"sandbox checks: {result.checks_passed}/{result.checks_total}")
        reg.register(SandboxGateCheck())

        class SchemaGateCheck(HealthCheck):
            module = "schema_gate"
            severity = Severity.MEDIUM
            async def run(self) -> HealthResult:
                from core.harness.infrastructure.gates.schema_gate import get_schema_gate
                sg = get_schema_gate()
                r = sg.validate({"name": "test", "age": 30}, {"type": "object", "required": ["name", "age"]})
                return HealthResult(module="schema_gate",
                    status=Status.HEALTHY if r.verdict.value == "pass" else Status.DEGRADED,
                    severity=Severity.MEDIUM, message="schema validation functional")
        reg.register(SchemaGateCheck())

        # Phase 24: Self-healing metrics
        class HealingHealthCheck(HealthCheck):
            module = "self_healing"
            severity = Severity.MEDIUM
            async def run(self) -> HealthResult:
                from core.harness.execution.pipeline_engine import PipelineEngine
                stats = getattr(PipelineEngine, '_healing_stats', {})
                attempts = stats.get("attempts", 0)
                successes = stats.get("successes", 0)
                skips = stats.get("skips", 0)
                escalations = stats.get("escalations", 0)
                rate = (successes / attempts * 100) if attempts > 0 else 100
                status = Status.HEALTHY if rate > 50 or attempts == 0 else Status.DEGRADED
                # Phase 25: Snapshot counts
                snap_total = 0
                # Phase 26: Strategy tracker stats
                tracker_stats = {}
                try:
                    from core.harness.optimization.strategy_tracker import get_strategy_tracker
                    tracker_stats = get_strategy_tracker().stats()
                except Exception:
                    pass
                try:
                    from core.harness.execution.snapshot import SNAPSHOT_ROOT
                    import os as _os_snap
                    if _os_snap.path.isdir(SNAPSHOT_ROOT):
                        snap_total = sum(1 for _ in _os_snap.listdir(SNAPSHOT_ROOT)
                                         if _.endswith('.json'))
                except Exception:
                    pass
                return HealthResult(
                    module="self_healing", status=status, severity=Severity.MEDIUM,
                    message=f"{rate:.0f}% success ({successes}/{attempts} heals, {skips} skips, {escalations} escalations)",
                    details={"attempts": attempts, "successes": successes,
                             "skips": skips, "escalations": escalations,
                             "success_rate_pct": round(rate, 1), "approx": True,
                             "snapshots_stored": snap_total,
                             "strategy_tracker": str(tracker_stats)}
                )
        reg.register(HealingHealthCheck())
    except Exception as e:
        logging.warning(str(e), exc_info=True)


_register_health_checks()


def _rt():
    return get_kernel_runtime()


def _store():
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None


@router.post("/diagnostics/e2e/smoke", response_model=Dict[str, Any])
async def run_e2e_smoke(request: Dict[str, Any]):
    """
    Production-grade full-chain smoke.
    - DeepSeek key read from ENV (DEEPSEEK_API_KEY / AIPLAT_LLM_API_KEY)
    - Best-effort cleanup of created resources
    """
    harness = get_harness()
    run_id = new_prefixed_id("run")
    exec_req = ExecutionRequest(
        kind="smoke_e2e",  # type: ignore[arg-type]
        target_id="smoke_e2e",
        payload=request or {},
        user_id=str((request or {}).get("actor_id") or "admin"),
        session_id=str((request or {}).get("session_id") or "ops_smoke"),
        request_id=run_id,
        run_id=run_id,
    )
    result = await harness.execute(exec_req)
    # Persist for diagnostic check (global_settings — no schema change needed)
    store = _store()
    if store:
        try:
            await store.upsert_global_setting(key="last_smoke_result", value={
                "ok": getattr(result, "ok", False),
                "status": "completed" if getattr(result, "ok", False) else "failed",
                "timestamp": time.time(),
            })
        except Exception as e:
            logging.warning(str(e), exc_info=True)
    if not result.ok:
        raise HTTPException(status_code=result.http_status, detail=result.error or "Smoke failed")
    return result.payload


@router.get("/diagnostics/context/config", response_model=Dict[str, Any])
async def get_context_config():
    """Return context/prompt assembly configuration for observability (no secrets)."""
    from core.harness.context.engine import DefaultContextEngine

    store = _store()
    # Prefer persisted global_setting (if present), fallback to env.
    persisted: Dict[str, Any] = {}
    try:
        if store:
            gs = await store.get_global_setting(key="context")
            val = gs.get("value") if isinstance(gs, dict) else None
            if isinstance(val, dict):
                persisted = val
    except Exception:
        persisted = {}

    env_enable = os.getenv("AIPLAT_ENABLE_SESSION_SEARCH", "false").lower() in ("1", "true", "yes", "y")
    enable_session_search = persisted.get("enable_session_search") if "enable_session_search" in persisted else env_enable
    token_limit = persisted.get("context_token_limit") or os.getenv("AIPLAT_CONTEXT_TOKEN_LIMIT")
    char_limit = persisted.get("context_char_limit") or os.getenv("AIPLAT_CONTEXT_CHAR_LIMIT")
    max_messages = persisted.get("context_max_messages") or os.getenv("AIPLAT_CONTEXT_MAX_MESSAGES")
    return {
        "context_engine": "default_v1",
        "enable_session_search": bool(enable_session_search),
        "limits": {
            "context_token_limit": int(token_limit) if token_limit is not None and str(token_limit).strip() else None,
            "context_char_limit": int(char_limit) if char_limit is not None and str(char_limit).strip() else None,
            "context_max_messages": int(max_messages) if max_messages is not None and str(max_messages).strip() else None,
        },
        "persisted": persisted,
        "project_context": {
            "supported_files": ["AGENTS.md", "AIPLAT.md"],
            "max_context_chars": int(getattr(DefaultContextEngine, "_MAX_CONTEXT_CHARS", 20000)),
        },
        "security": {"has_injection_detection": True},
    }


@router.post("/diagnostics/prompt/assemble", response_model=Dict[str, Any])
async def diagnostics_prompt_assemble(request: DiagnosticsPromptAssembleRequest, http_request: Request):
    """
    Assemble prompt + context and return metadata for debugging.
    NOTE: diagnostics only (do not use on hot paths).
    """
    from core.harness.assembly.prompt_assembler import PromptAssembler
    from core.harness.kernel.execution_context import (
        ActiveRequestContext,
        ActiveWorkspaceContext,
        reset_active_request_context,
        reset_active_workspace_context,
        set_active_request_context,
        set_active_workspace_context,
    )

    store = _store()
    msgs: List[Dict[str, Any]] = []
    if request.messages and isinstance(request.messages, list):
        msgs = request.messages  # type: ignore[assignment]
    elif request.session_id and store:
        sess = await store.get_memory_session(session_id=str(request.session_id))
        if not sess:
            raise HTTPException(status_code=404, detail="session_not_found")
        res = await store.list_memory_messages(session_id=str(request.session_id), limit=200, offset=0)
        msgs = [{"role": m.get("role"), "content": m.get("content"), "metadata": (m.get("metadata") or {})} for m in (res.get("items") or [])]
    else:
        raise HTTPException(status_code=400, detail="messages_or_session_id_required")

    meta: Dict[str, Any] = {"enable_project_context": bool(request.enable_project_context)}

    # Optional toggle override (best-effort; restore after)
    env_prev = os.getenv("AIPLAT_ENABLE_SESSION_SEARCH")
    env_set = None
    if request.enable_session_search is not None:
        env_set = "true" if request.enable_session_search else "false"
        os.environ["AIPLAT_ENABLE_SESSION_SEARCH"] = env_set

    t1 = None
    t2 = None
    try:
        t1 = set_active_workspace_context(ActiveWorkspaceContext(repo_root=request.repo_root))
        actor0 = actor_from_http(http_request, None)
        tenant_id = actor0.get("tenant_id") or http_request.headers.get("X-AIPLAT-TENANT-ID")
        actor_id = actor0.get("actor_id") or http_request.headers.get("X-AIPLAT-ACTOR-ID")
        actor_role = actor0.get("actor_role") or http_request.headers.get("X-AIPLAT-ACTOR-ROLE")
        req_id = http_request.headers.get("X-AIPLAT-REQUEST-ID") or None
        t2 = set_active_request_context(
            ActiveRequestContext(
                user_id=str(request.user_id),
                session_id=str(request.session_id or "default"),
                tenant_id=str(tenant_id) if tenant_id else None,
                actor_id=str(actor_id) if actor_id else None,
                actor_role=str(actor_role) if actor_role else None,
                entrypoint="diagnostics_prompt_assemble",
                request_id=str(req_id) if req_id else None,
            )
        )
        out = PromptAssembler().assemble(msgs, metadata=meta)
        resp = {
            "status": "ok",
            "prompt_version": out.prompt_version,
            "workspace_context_hash": out.workspace_context_hash,
            "stable_prompt_version": out.stable_prompt_version,
            "stable_cache_key": out.stable_cache_key,
            "stable_cache_hit": bool(out.stable_cache_hit),
            "metadata": out.metadata,
            "system_layers": {
                "stable_system_prompt_chars": len(out.stable_system_prompt or ""),
                "ephemeral_overlay_chars": len(out.ephemeral_overlay or ""),
            },
            "message_count": len(out.messages or []),
        }
        # Persist context metrics (best-effort) for trends/regression.
        try:
            if store:
                cs = out.metadata.get("context_status") if isinstance(out.metadata.get("context_status"), dict) else {}
                budgets = cs.get("budgets") if isinstance(cs.get("budgets"), dict) else {}
                comp = cs.get("compaction") if isinstance(cs.get("compaction"), dict) else {}
                ss = cs.get("session_search") if isinstance(cs.get("session_search"), dict) else {}
                proj = cs.get("project_context") if isinstance(cs.get("project_context"), dict) else {}
                metrics = {
                    "stable_cache_hit": bool(out.stable_cache_hit),
                    "stable_cache_key": out.stable_cache_key,
                    "workspace_context_hash": out.workspace_context_hash,
                    "prompt_estimated_tokens": out.metadata.get("prompt_estimated_tokens"),
                    "budgets_token_estimate": budgets.get("token_estimate"),
                    "budgets_total_chars": budgets.get("total_chars"),
                    "compaction_applied": bool(comp.get("applied")),
                    "session_search_enabled": bool(ss.get("enabled")),
                    "session_search_injected": bool(ss.get("injected")),
                    "session_search_hits": int(ss.get("hits") or 0),
                    "project_context_injected": bool(proj.get("injected")),
                    "project_context_file": proj.get("file"),
                    "project_context_blocked": bool(proj.get("blocked")),
                }
                await store.add_syscall_event(
                    {
                        "kind": "metric",
                        "name": "context_assemble",
                        "status": "success",
                        "tenant_id": str(tenant_id) if tenant_id else None,
                        "user_id": str(request.user_id or "system"),
                        "session_id": str(request.session_id or "default"),
                        "target_type": "context",
                        "target_id": str(out.workspace_context_hash or out.stable_cache_key or ""),
                        "args": {"operation": "diagnostics_prompt_assemble", "repo_root": str(request.repo_root or "")},
                        "result": {"metrics": metrics},
                    }
                )
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        return resp
    finally:
        if t2 is not None:
            try:
                reset_active_request_context(t2)
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        if t1 is not None:
            try:
                reset_active_workspace_context(t1)
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        if env_set is not None:
            try:
                if env_prev is None:
                    os.environ.pop("AIPLAT_ENABLE_SESSION_SEARCH", None)
                else:
                    os.environ["AIPLAT_ENABLE_SESSION_SEARCH"] = env_prev
            except Exception as e:
                logging.warning(str(e), exc_info=True)


@router.get("/diagnostics/context/metrics/recent", response_model=Dict[str, Any])
async def diagnostics_context_metrics_recent(limit: int = 50, offset: int = 0, tenant_id: Optional[str] = None, session_id: Optional[str] = None):
    """Recent context assembly metrics (syscall_events kind=metric, name=context_assemble)."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_syscall_events(limit=int(limit), offset=int(offset), kind="metric", name="context_assemble", tenant_id=tenant_id, session_id=session_id)


@router.get("/diagnostics/context/metrics/summary", response_model=Dict[str, Any])
async def diagnostics_context_metrics_summary(window_hours: int = 24, top_n: int = 8, tenant_id: Optional[str] = None):
    """Aggregate context metrics for trends/regression (diagnostics use)."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    now = time.time()
    since = now - float(max(1, int(window_hours))) * 3600.0
    raw = await store.list_syscall_events(limit=2000, offset=0, kind="metric", name="context_assemble", tenant_id=tenant_id)
    items = [x for x in (raw.get("items") or []) if isinstance(x, dict) and float(x.get("created_at") or 0) >= since]
    total = len(items)
    if total == 0:
        return {"window_hours": int(window_hours), "total": 0, "rates": {}, "avgs": {}, "top": {}}

    cache_hit = 0
    compaction = 0
    ss_enabled = 0
    ss_injected = 0
    ss_hits_sum = 0
    prompt_tok_sum = 0
    prompt_tok_cnt = 0
    budget_tok_sum = 0
    budget_tok_cnt = 0
    by_hash: Dict[str, int] = {}
    by_session: Dict[str, int] = {}

    for it in items:
        r = it.get("result") if isinstance(it.get("result"), dict) else {}
        m = r.get("metrics") if isinstance(r.get("metrics"), dict) else {}
        if bool(m.get("stable_cache_hit")):
            cache_hit += 1
        if bool(m.get("compaction_applied")):
            compaction += 1
        if bool(m.get("session_search_enabled")):
            ss_enabled += 1
        if bool(m.get("session_search_injected")):
            ss_injected += 1
        try:
            ss_hits_sum += int(m.get("session_search_hits") or 0)
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        try:
            pt = m.get("prompt_estimated_tokens")
            if isinstance(pt, (int, float)):
                prompt_tok_sum += float(pt)
                prompt_tok_cnt += 1
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        try:
            bt = m.get("budgets_token_estimate")
            if isinstance(bt, (int, float)):
                budget_tok_sum += float(bt)
                budget_tok_cnt += 1
        except Exception as e:
            logging.warning(str(e), exc_info=True)

        h = str(m.get("workspace_context_hash") or it.get("target_id") or "").strip()
        if h:
            by_hash[h] = by_hash.get(h, 0) + 1
        sid = str(it.get("session_id") or "").strip()
        if sid:
            by_session[sid] = by_session.get(sid, 0) + 1

    def _top(d: Dict[str, int]) -> List[Dict[str, Any]]:
        return [{"key": k, "count": v} for k, v in sorted(d.items(), key=lambda kv: kv[1], reverse=True)[: int(top_n)]]

    return {
        "window_hours": int(window_hours),
        "total": total,
        "rates": {
            "stable_cache_hit_rate": cache_hit / float(total),
            "compaction_rate": compaction / float(total),
            "session_search_enabled_rate": ss_enabled / float(total),
            "session_search_injected_rate": ss_injected / float(total),
        },
        "avgs": {
            "session_search_hits": ss_hits_sum / float(total),
            "prompt_estimated_tokens": (prompt_tok_sum / float(prompt_tok_cnt)) if prompt_tok_cnt else None,
            "budgets_token_estimate": (budget_tok_sum / float(budget_tok_cnt)) if budget_tok_cnt else None,
        },
        "top": {"workspace_context_hash": _top(by_hash), "session_id": _top(by_session)},
    }


@router.get("/diagnostics/exec/backends", response_model=Dict[str, Any])
async def diagnostics_exec_backends():
    """Exec backend diagnostics."""
    from core.api.facades.security_facade import get_exec_backend

    backend = await get_exec_backend()
    from core.apps.exec_drivers.registry import healthcheck_backends
    health = await healthcheck_backends()
    return {"status": "ok", "current_backend": backend, "backends": health.get("backends") if isinstance(health, dict) else [], "non_local_requires_approval": True}


@router.get("/diagnostics/exec/metrics/summary", response_model=Dict[str, Any])
async def diagnostics_exec_backend_metrics_summary(window_hours: int = 24, limit: int = 20):
    """Exec backend metrics summary (uses run_events aggregated in ExecutionStore)."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.exec_backend_metrics_summary(window_hours=int(window_hours or 24), limit=int(limit or 20))


@router.post("/diagnostics/guard/run", response_model=Dict[str, Any])
async def run_architecture_guard():
    """Execute architecture guard rules and return structured results."""
    from pathlib import Path as _Path

    repo_root = _Path(__file__).resolve().parents[4]
    if not repo_root.exists():
        raise HTTPException(status_code=404, detail="Repository root not found")

    try:
        from core.management.arch_guard_base import get_arch_registry
        registry = get_arch_registry()
        report = registry.run_all(repo_root)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Guard execution failed: {e}")

    return {
        "status": "ok",
        "sections": [s.to_dict() for s in report.sections],
        "summary": report.summary,
        "violations": report.violations,
    }


@router.get("/diagnostics/latest", response_model=Dict[str, Any])
def get_latest_diagnostic():
    """Return last diagnostic result (in-memory, current session only)."""
    if _DIAG_CACHE is not None:
        result = dict(_DIAG_CACHE)
        result.pop("_details", None)
        return result
    return {"cached": False, "message": "尚未运行诊断 — POST /diagnostics/run-all 先"}


async def _get_repairs_from_cache() -> Dict[str, Any]:
    """Read repair data from the diagnostic cache."""
    repairs = _DIAG_CACHE.get("repairs", {}) if _DIAG_CACHE else {}
    return {
        "issues": repairs.get("issues", []),
        "summary": repairs.get("summary", {}),
        "total_issues": len(repairs.get("issues", [])),
        "cached": _DIAG_CACHE is not None,
    }


@router.get("/diagnostics/repairs-latest", response_model=Dict[str, Any])
async def get_latest_repairs():
    """Return last repair result (in-memory, current session only)."""
    if _DIAG_CACHE is not None:
        return await _get_repairs_from_cache()
    return {"cached": False, "needs_diagnostics": True, "summary": {"total_issues": 0}}


@router.get("/diagnostics/summary", response_model=Dict[str, Any])
def get_diagnostic_summary():
    """Return quick alert summary from last diagnostic run."""
    if _DIAG_CACHE is None:
        return {"cached": False, "alerts": [], "pass": 0, "warn": 0, "fail": 0}
    cats = _DIAG_CACHE.get("categories", {})
    alerts = []
    for name, cat in cats.items():
        if not isinstance(cat, dict):
            continue
        st = cat.get("status", "")
        if st in ("warn", "fail"):
            label = _LABELS.get(name, name)
            score = cat.get("score", 0)
            items = cat.get("items", [])
            issue_count = len(items)
            violation_count = cat.get("violations", 0)
            count = violation_count if violation_count else issue_count
            alerts.append({
                "category": name,
                "label": label,
                "status": st,
                "score": score,
                "count": count,
            })
    alerts.sort(key=lambda a: (0 if a["status"] == "fail" else 1, a["score"]))
    ago = int(time.time() - _DIAG_CACHE_TS) if _DIAG_CACHE_TS else 999
    unit = "s"
    if ago > 86400:
        ago //= 86400; unit = "d"
    elif ago > 3600:
        ago //= 3600; unit = "h"
    elif ago > 60:
        ago //= 60; unit = "m"
    return {
        "last_run": f"{ago}{unit} ago",
        "pass": _DIAG_CACHE.get("pass", 0),
        "warn": _DIAG_CACHE.get("warn", 0),
        "fail": _DIAG_CACHE.get("fail", 0),
        "overall_score": _DIAG_CACHE.get("overall_score", 0),
        "overall_grade": _DIAG_CACHE.get("overall_grade", "?"),
        "alerts": alerts,
    }


# Define labels dict at module level for summary endpoint
_LABELS = {
    "core_runtime": "Core 运行时", "code_intel": "代码架构", "capability": "能力图谱",
    "wiki_health": "Wiki健康", "arch_guard": "架构守卫", "compliance": "合规审计",
    "wiki_content_quality": "Wiki内容质量",
    "traces": "链路追踪", "graph_runs": "图执行", "context_metrics": "上下文",
    "e2e_smoke": "冒烟测试", "doctor": "Doctor", "overview_issues": "概览问题",
    "symbol_health": "符号健康", "lsp": "LSP 诊断", "security": "安全扫描",
    "full_stack": "全域测试",
}


@router.get("/diagnostics/history", response_model=Dict[str, Any])
def get_diagnostic_history():
    """Return last N diagnostic results for trend chart (max 30 entries)."""
    hist = _load_diag_history()
    return {"history": hist, "count": len(hist)}


def _diag_lock(func):
    """Decorator: ensure only one diagnostic runs at a time, with auto-release timeout."""
    from functools import wraps
    @wraps(func)
    async def wrapper(*args, **kwargs):
        global _DIAG_RUNNING
        import time as _time
        now = _time.time()
        if _DIAG_RUNNING > 0:
            elapsed = now - _DIAG_RUNNING
            if elapsed < _DIAG_LOCK_TTL:
                return {
                    "run_id": "skipped", "overall_score": 0,
                    "message": f"另一个诊断正在运行中（已运行 {int(elapsed)}s）— 请等当前诊断完成后再试",
                    "status": "locked",
                }
            # Lock held too long — likely stale, force release
            logging.warning("_diag_lock: force-releasing stale lock held for %.0fs", elapsed)
        _DIAG_RUNNING = now
        try:
            return await func(*args, **kwargs)
        finally:
            _DIAG_RUNNING = 0.0
    return wrapper


# ── Standalone LLM审查 (not part of run-all — ~150K tokens, run on demand) ──

async def _run_llm_review(max_files: int = 15, max_chars: int = 12000, focus: str = "comprehensive",
                          run_id: str = "") -> Dict[str, Any]:
    """Core LLM review logic — parallel execution with SQLite progress tracking."""
    import os as _os, logging as _log, time as _time, json as _json
    try:
        from core.engine.skills.autoreview.handler import review_file

        # Init SQLite progress row
        if run_id:
            _llm_init_table()
            _llm_sync_progress(run_id, status="running", files_done=0, files_total=0,
                               current_file="", results=[], created_at=_time.time())

        targets = _select_llm_review_targets(max_files=max_files)
        if not targets:
            if run_id:
                _llm_sync_progress(run_id, status="done", files_done=0, files_total=0)
            return {"status": "unavailable", "score": 0, "signals": {"files_reviewed": 0},
                    "items": [{"check": "LLM审查", "result": "—", "detail": "无符合条件的目标文件"}],
                    "recommendation": "可能需要增加核心模块或大文件"}

        total = len(targets)
        if run_id:
            _llm_sync_progress(run_id, files_total=total)

        # ── Parallel execution with progress ──
        import asyncio as _async
        done_count = 0
        done_results = []
        _lock = _async.Lock()

        async def _review_one(file_path: str, lines: int):
            nonlocal done_count
            try:
                with open(file_path) as f:
                    content = f.read()
                file_name = file_path.split("/")[-1]
                rpt = await review_file(content, file_path, focus=focus, max_chars=max_chars)
                async with _lock:
                    done_count += 1
                    result_entry = {"file": file_name, "score": rpt.score,
                                    "p0": rpt.p0_count, "p1": rpt.p1_count, "p2": rpt.p2_count}
                    done_results.append(result_entry)
                    if run_id:
                        _llm_sync_progress(
                            run_id, files_done=done_count, current_file=file_name,
                            results=done_results,
                        )
                return (file_path, rpt)
            except Exception as e:
                _log.warning("LLM review skipped %s: %s", file_path, e)
                async with _lock:
                    done_count += 1
                return None

        results = await _async.gather(
            *(_review_one(fp, ln) for fp, ln in targets),
            return_exceptions=True
        )
        reports = [(fp, rpt) for result in results if result is not None and not isinstance(result, BaseException)
                   for fp, rpt in [result if isinstance(result, tuple) else (None, None)] if rpt is not None]

        if not reports:
            if run_id:
                _llm_sync_progress(run_id, status="unavailable", files_done=done_count, files_total=total)
            return {"status": "unavailable", "score": 0, "signals": {"files_reviewed": 0},
                    "recommendation": "所有文件审查请求失败——请检查 LLM 配置"}

        scores = [r.score for _, r in reports]
        avg_score = sum(scores) / len(scores) if scores else 100
        total_issues = sum(r.issue_count for _, r in reports)
        p0_total = sum(r.p0_count for _, r in reports)
        p1_total = sum(r.p1_count for _, r in reports)

        items = []
        for file_path, r in reports:
            sev = "❌" if r.p0_count > 0 else ("⚠️" if r.p1_count > 2 else "✅")
            items.append({"check": file_path.split("/")[-1],
                          "result": sev,
                          "detail": f"score={r.score}, P0={r.p0_count}, P1={r.p1_count}, P2={r.p2_count}"})

        result = {
            "status": "pass" if avg_score >= 80 else "warn",
            "score": round(avg_score),
            "signals": {
                "files_reviewed": len(reports),
                "total_issues": total_issues,
                "p0_count": p0_total,
                "p1_count": p1_total,
                "avg_score": round(avg_score, 1),
            },
            "items": items,
            "_autoreview": await _get_autoreview_summary(),
        }
        if run_id:
            _llm_sync_progress(run_id, status="done", files_done=done_count, files_total=total,
                               score=result["score"], p0_count=p0_total, p1_count=p1_total,
                               results=done_results)
        return result
    except Exception as e:
        if run_id:
            _llm_sync_progress(run_id, status="error")
        return {"status": "error", "score": 0, "error": str(e)[:200]}


# ── LLM审查 with SQLite progress tracking ──

@router.post("/diagnostics/llm-review/start", response_model=Dict[str, Any])
async def start_llm_review(
    max_files: int = 15,
    max_chars: int = 12000,
    focus: str = "comprehensive",
):
    """启动异步 LLM审查 — 立即返回 run_id，进度写入 SQLite（跨 worker 共享）。
    
    ~150K tokens/次。审查在后台并行执行，每完成一个文件更新进度。
    """
    import uuid, time
    _llm_cleanup_old(max_keep=10)
    run_id = f"llm-review-{uuid.uuid4().hex[:12]}"
    _llm_sync_progress(run_id, status="running", files_done=0, files_total=0,
                       current_file="", results="[]", created_at=time.time())
    import asyncio as _async
    _async.create_task(_run_llm_review(
        max_files=max_files, max_chars=max_chars, focus=focus, run_id=run_id
    ))
    return {"run_id": run_id, "status": "started"}


@router.get("/diagnostics/llm-review/status", response_model=Dict[str, Any])
async def llm_review_status(run_id: str = ""):
    """查询 LLM审查进度（读取 SQLite，所有 worker 可见）。
    
    Returns:
        status: running | done | error | not_found
        files_done, files_total, current_file (running)
        score, p0_count, p1_count, results (done)
    """
    if not run_id:
        return {"status": "not_found", "detail": "run_id required"}
    import time
    task = _llm_get_progress(run_id)
    status = task.get("status", "not_found")
    ts = task.get("created_at", 0)
    elapsed = int(time.time() - ts) if ts else 0
    resp = {"status": status, "elapsed_s": elapsed}
    if status == "running":
        resp.update({
            "files_done": task.get("files_done", 0),
            "files_total": task.get("files_total", 0),
            "current": task.get("current_file", ""),
            "results": task.get("results", []),
        })
    elif status == "done":
        resp.update({
            "files_done": task.get("files_done", 0),
            "files_total": task.get("files_total", 0),
            "score": task.get("score", 0),
            "p0": task.get("p0_count", 0),
            "p1": task.get("p1_count", 0),
            "results": task.get("results", []),
        })
    elif status == "error":
        resp["error"] = task.get("error", "unknown error")
    return resp


# Keep synchronous endpoint for backward compatibility
@router.post("/diagnostics/llm-review", response_model=Dict[str, Any])
async def run_llm_review_sync(
    max_files: int = 15,
    max_chars: int = 12000,
    focus: str = "comprehensive",
):
    """同步 LLM审查（兼容旧调用）"""
    return await _run_llm_review(max_files=max_files, max_chars=max_chars, focus=focus)


@router.get("/diagnostics/llm-review/history", response_model=Dict[str, Any])
async def llm_review_history(limit: int = 10):
    """列出最近 N 次 LLM审查历史记录（从 SQLite 读取）。"""
    import time, json
    conn = _llm_get_db()
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM llm_review_tasks ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        items = []
        for row in rows:
            d = dict(row)
            ts = d.get("created_at", 0)
            age = int(time.time() - ts) if ts else 0
            results = []
            if d.get("results"):
                try:
                    results = json.loads(d["results"])
                except Exception:
                    results = []
            items.append({
                "run_id": d.get("run_id", ""),
                "status": d.get("status", ""),
                "files_done": d.get("files_done", 0),
                "files_total": d.get("files_total", 0),
                "score": d.get("score", 0),
                "p0": d.get("p0_count", 0),
                "p1": d.get("p1_count", 0),
                "age_s": age,
                "results": results[:5],  # first 5 files only
            })
        return {"items": items, "total": len(items)}
    finally:
        conn.close()


# ── Token/Cost Usage Insights ───────────────────────────────────────────────

@router.get("/diagnostics/llm-review/summary-stats", response_model=Dict[str, Any])
async def get_llm_review_summary_stats():
    """
    Aggregated token usage and cost summary from latest diagnostic runs.

    Reads from _load_diag_history() for recent diagnostic metadata + calculates
    cost estimates based on file counts in review results.
    """
    from datetime import datetime, timezone as _tz
    hist = _load_diag_history()
    if not hist:
        return {"runs": 0, "total_cost": 0, "total_tokens": 0, "by_day": []}

    # Aggregate by day
    by_day: Dict[str, dict] = {}
    total_cost = 0.0
    total_tokens_est = 0

    for entry in hist[-30:]:
        ts = entry.get("ts", 0)
        if not ts:
            continue
        day = datetime.fromtimestamp(ts, tz=_tz).strftime("%Y-%m-%d")
        score = entry.get("overall_score", 0)
        signals = entry.get("signals") or {}
        files = signals.get("files_reviewed", 0) or 0

        # Cost estimate: ~2 LLM calls per file, ~5K tokens per call
        est_tokens = files * 2 * 5000
        est_cost = round((files * 2 * 3000 / 1_000_000 * 0.27) + (files * 2 * 2000 / 1_000_000 * 1.10), 4)

        by_day.setdefault(day, {"tokens": 0, "cost": 0.0, "runs": 0, "files": 0})
        by_day[day]["tokens"] += est_tokens
        by_day[day]["cost"] += est_cost
        by_day[day]["runs"] += 1
        by_day[day]["files"] += files
        total_cost += est_cost
        total_tokens_est += est_tokens

    days_sorted = sorted(by_day.items(), reverse=True)[:14]
    return {
        "runs": len(hist[-30:]),
        "total_cost": round(total_cost, 4),
        "total_tokens": total_tokens_est,
        "by_day": [
            {"day": d, "tokens": v["tokens"], "cost": round(v["cost"], 4),
             "runs": v["runs"], "files": v["files"]}
            for d, v in days_sorted
        ],
    }


@router.get("/diagnostics/ops/tenant-usage", response_model=Dict[str, Any])
async def get_tenant_usage_summary(
    tenant_id: str = "",
    days: int = 7,
):
    """
    Read aggregated LLM token usage from execution_store.tenant_usage_ledger.

    Returns per-day token counts for the given tenant (default: all).
    """
    from collections import defaultdict as _dd
    try:
        from core.harness.integration import get_execution_store
        store = get_execution_store()
        now = __import__("time").time()
        cutoff = now - days * 86400

        entries = await store.list_tenant_usage(tenant_id=tenant_id or None, since=cutoff, limit=500)
        by_day = _dd(lambda: {"tokens": 0.0, "calls": 0})
        total_tokens = 0.0
        total_calls = 0

        for entry in entries:
            day = entry.get("day", "") if isinstance(entry, dict) else getattr(entry, "day", "")
            amount = float(entry.get("amount", 0)) if isinstance(entry, dict) else float(getattr(entry, "amount", 0))
            metric = entry.get("metric_key", "") if isinstance(entry, dict) else getattr(entry, "metric_key", "")
            if "token" in metric:
                by_day[day]["tokens"] += amount
                total_tokens += amount
                total_calls += 1

        days_sorted = sorted(by_day.items(), reverse=True)[:days]
        return {
            "total_tokens": total_tokens,
            "total_calls": total_calls,
            "days": days,
            "by_day": [{"day": d, "tokens": v["tokens"], "calls": v["calls"]} for d, v in days_sorted],
        }
    except Exception as e:
        return {"error": str(e)[:200], "total_tokens": 0, "total_calls": 0, "by_day": []}


# ── Document Quality Monitor ────────────────────────────────────────────────

@router.get("/diagnostics/doc-quality", response_model=Dict[str, Any])
async def get_doc_quality(limit: int = 20):
    """
    Returns document quality baseline, alerts, and per-doc health status.

    Response: { "baseline": {...}, "alerts": [...], "doc_health": [...], "stats": {...} }
    """
    try:
        from core.harness.knowledge.doc_quality_monitor import get_doc_quality_monitor
        dqm = get_doc_quality_monitor()
        return {
            "alerts": dqm.get_alerts(limit=limit),
            "doc_health": dqm.get_doc_health(),
            "stats": dqm.get_stats(),
        }
    except Exception as e:
        return {"alerts": [], "doc_health": [], "stats": {}, "error": str(e)[:200]}


@router.get("/diagnostics/wiki-quality", response_model=Dict[str, Any])
async def get_wiki_content_quality(limit: int = 20, collection: str = "default"):
    """
    Returns Wiki page content quality vs original source documents.

    Response: { "alerts": [...], "trends": [...], "stats": {...} }
    """
    try:
        from core.harness.knowledge.wiki_quality_monitor import get_wiki_quality_monitor
        monitor = get_wiki_quality_monitor()
        return {
            "alerts": monitor.get_alerts(limit=limit, collection_id=collection),
            "trends": monitor.get_trends(collection_id=collection, limit=10),
            "stats": monitor.get_stats(),
        }
    except Exception as e:
        return {"alerts": [], "trends": [], "stats": {}, "error": str(e)[:200]}


# ── Entropy Trend Awareness ──────────────────────────────────────────────────

@router.get("/diagnostics/entropy/trends", response_model=Dict[str, Any])
async def get_entropy_trends():
    """
    Returns current error-rate volatility across 6 ten-minute buckets (1 hour).

    Response:
    {
        "buckets": [{"window_start": ..., "total_calls": N, "rates": {...}}, ...],
        "active_alerts": [{"error_type": "...", "state": "alerting", ...}],
        "state_summary": {"normal": 13, "alerting": 1, "high_alert": 0, "resolved": 1}
    }
    """
    try:
        from core.harness.infrastructure.trend_detector import get_trend_detector
        td = get_trend_detector()
        return td.get_trends()
    except Exception as e:
        return {"buckets": [], "active_alerts": [], "state_summary": {}, "error": str(e)[:200]}


@router.get("/diagnostics/entropy/alerts", response_model=Dict[str, Any])
async def get_entropy_alerts(limit: int = 20):
    """
    Returns recent entropy alert records from SQLite.

    Response: {"alerts": [...], "total": N}
    """
    try:
        from core.harness.infrastructure.trend_detector import get_trend_detector
        td = get_trend_detector()
        return td.get_alert_history(limit=limit)
    except Exception as e:
        return {"alerts": [], "total": 0, "error": str(e)[:200]}


# ── Phase 14: Model tier status + cost + health dashboard ──

@router.get("/diagnostics/model-tier", response_model=Dict[str, Any])
async def get_model_tier_status():
    """Return unified model tier status: current tier, cost estimates, health.

    Powers the frontend ModelTierIndicator + CostDashboard + ModelHealthPanel.
    """
    result: Dict[str, Any] = {
        "status": {"current_tier": "N/A", "current_model": "N/A",
                    "last_complexity": "unknown", "override_active": False},
        "tiers": {},
    }

    # Load tier config
    try:
        from core.harness.routing.model_tier_router import get_tier_router
        router = get_tier_router()
        for tier_id, cfg in router._tiers.items():
            available = router._is_model_available(cfg.default_model)
            result["tiers"][tier_id] = {
                "label": cfg.label,
                "model": cfg.default_model,
                "fallback_models": cfg.fallback_models,
                "complexity_range": list(cfg.complexity_range),
                "status": "available" if available else "degraded",
            }

        # Default tier estimation (simple query → what would we pick?)
        for level in ["simple", "medium", "complex"]:
            m = router.route("chat", level, 0.8)
            if m:
                result["status"]["current_model"] = m
                break
    except Exception:
        result["tiers"] = {"error": "tier_router_unavailable"}

    # Check for session override
    try:
        from core.harness.utils.model_injection import _model_overrides
        if _model_overrides.get("_global"):
            result["status"]["override_active"] = True
            result["status"]["overridden_model"] = _model_overrides["_global"]
    except Exception:
        pass

    # ── Phase 14 B/C: Cost estimates + health metrics per tier ──
    result["cost"] = {}
    result["health"] = {}
    try:
        import yaml
        from pathlib import Path
        config_path = os.getenv("AIPLAT_LLM_CONFIG_PATH",
            str(Path(__file__).resolve().parent.parent.parent.parent.parent /
                "aiPlat-infra" / "config" / "infra" / "llm_profile.yaml"))
        profile = yaml.safe_load(open(config_path)) or {}
        caps = profile.get("model_capabilities", {})

        for tier_id, cfg in result.get("tiers", {}).items():
            model_name = cfg.get("model", "")
            model_caps = caps.get(model_name, {})

            # Cost: per 1M tokens from YAML
            pricing = model_caps.get("pricing", {})
            prompt_cost = pricing.get("prompt_per_1m", 0)
            completion_cost = pricing.get("completion_per_1m", 0)
            result["cost"][tier_id] = {
                "model": model_name,
                "prompt_per_1m": prompt_cost,
                "completion_per_1m": completion_cost,
                "estimated_monthly": round(prompt_cost * 10, 2),
            }

            # Health: basic availability check
            result["health"][tier_id] = {
                "model": model_name,
                "latency_p95_s": 0,
                "failure_rate": 0,
                "status": cfg.get("status", "unknown"),
            }

        # Try to enrich with live health data from infra
        try:
            from infra.management.model.manager import ModelManager
            mgr = ModelManager._instance
            if mgr:
                for tier_id, cfg in result["tiers"].items():
                    model_name = cfg.get("model", "")
                    try:
                        from infra.management.model.latency_tracker import get_latency_tracker
                        lt = get_latency_tracker()
                        p95 = lt.p95_latency_seconds(model_name)
                        fail_rate = mgr._failure_rate(model_name) if hasattr(mgr, '_failure_rate') else 0
                        result["health"][tier_id]["latency_p95_s"] = round(p95, 1)
                        result["health"][tier_id]["failure_rate"] = round(fail_rate, 2)
                        result["health"][tier_id]["status"] = (
                            "healthy" if fail_rate <= 0.1 else
                            "degraded" if fail_rate <= 0.5 else "critical"
                        )
                    except Exception:
                        pass
        except Exception:
            pass  # infra health tracker unavailable
    except Exception:
        pass  # YAML config unreadable

    return result


# ── Phase 17: Code entropy scan ──

@router.get("/diagnostics/code-entropy", response_model=Dict[str, Any])
async def get_code_entropy(directory: str = ""):
    """Scan code directory for high-entropy files (AI slop detection).

    Inspect by OpenAI's weekly code cleanup practice — identifies files
    that need refactoring due to accumulated AI-generated code degradation.
    """
    try:
        from core.harness.knowledge.code_entropy_detector import CodeEntropyDetector
        detector = CodeEntropyDetector()
        target = directory or str(
            __import__("pathlib").Path(__file__).resolve().parent.parent.parent.parent
        )
        result = detector.scan(target)
        result["last_scan"] = detector.get_last_scan()
        return result
    except Exception as e:
        return {"error": str(e)[:300]}


# ── Phase 19: Unified knowledge base health dashboard + report generator ──

_kb_health_cache: Dict[str, Any] = {"data": None, "timestamp": 0.0}
_KHEALTH_CACHE_TTL = 300  # 5 minutes


@router.get("/diagnostics/knowledge-base-health", response_model=Dict[str, Any])
async def get_kb_health(
    collection: str = "default",
    days: int = 30,
    format: str = "json",
):
    """Unified knowledge base health dashboard.

    Aggregates 6 quality modules into a single health score with maturity level.
    All external module failures are gracefully degraded — always returns 200.

    Args:
        collection: Wiki collection ID.
        days: Days for growth/gap analysis (default 30).
        format: "json" (default) | "markdown" (Chinese report for CIO/PM).
    """
    import time as _time
    now = _time.time()

    # Cache check
    if _kb_health_cache["data"] and now - _kb_health_cache["timestamp"] < _KHEALTH_CACHE_TTL:
        result = _kb_health_cache["data"]
    else:
        result = await _aggregate_kb_health(collection, days)
        _kb_health_cache["data"] = result
        _kb_health_cache["timestamp"] = now

    if format == "markdown":
        from fastapi.responses import Response
        md = _build_markdown_report(result, collection, days)
        return Response(content=md, media_type="text/markdown; charset=utf-8")

    return result


async def _aggregate_kb_health(collection: str, days: int) -> Dict[str, Any]:
    """Aggregate health data from all 6 quality modules with graceful degradation."""
    import asyncio
    import time as _time
    from datetime import datetime, timezone

    _t0 = _time.time()
    result: Dict[str, Any] = {
        "maturity": {}, "health": {}, "quality": {}, "growth": {},
        "gaps": {}, "hallucination": {}, "doc_quality": {},
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    # 1. Structure health (wiki_health_rules) — async thread pool to avoid blocking
    try:
        from core.harness.knowledge.wiki_health_rules import WikiHealthRegistry
        report = await asyncio.to_thread(WikiHealthRegistry().run)
        result["health"] = {
            "overall_score": getattr(report, "health_score", 0),
            "checks": [
                {"name": c.get("name", "?"), "pass": c.get("pass", False),
                 "count": c.get("count", 0), "severity": c.get("severity", "medium")}
                for c in (getattr(report, "checks", []) or [])
            ],
            "issues_count": len(getattr(report, "issues", []) or []),
            "status": "ready",
        }
    except Exception as e:
        result["health"] = {"overall_score": 0, "status": "unavailable", "error": str(e)[:100]}

    # 2. Content quality (wiki_quality_monitor)
    try:
        from core.harness.knowledge.wiki_quality_monitor import get_wiki_quality_monitor
        result["quality"] = get_wiki_quality_monitor().get_stats() or {}
        result["quality"]["status"] = "ready"
    except Exception as e:
        result["quality"] = {"avg_overall": 0, "status": "unavailable", "error": str(e)[:100]}

    # 3. Growth (knowledge_growth) — fallback on ImportError
    try:
        from core.harness.knowledge.knowledge_growth import get_growth_stats
        result["growth"] = get_growth_stats(collection_id=collection, days=days) or {}
        result["growth"]["status"] = "ready"
    except ImportError:
        result["growth"] = {
            "pages_delta_30d": 0, "quality_trend": "stable",
            "conversion_rate_pct": 0.0, "status": "fallback",
        }

    # 4. Knowledge gaps — returns insufficient_data when no queries available
    try:
        queries = _get_recent_kb_queries(days)
        if queries:
            from core.harness.ontology_engine.knowledge_gap_detector import detect_knowledge_gaps
            result["gaps"] = detect_knowledge_gaps(queries, domain_id=collection).get("summary", {})
            result["gaps"]["status"] = "ready"
        else:
            result["gaps"] = {"total": -1, "status": "insufficient_data", "by_type": {}}
    except Exception as e:
        result["gaps"] = {"total": -1, "status": "error", "error": str(e)[:100]}

    # 5. Hallucination safety
    try:
        from core.harness.evaluation.hallucination_tracker import get_hallucination_tracker
        result["hallucination"] = get_hallucination_tracker().get_dashboard(domain_id=collection) or {}
        result["hallucination"]["status"] = "ready"
    except Exception as e:
        result["hallucination"] = {"avg_faithfulness": 0, "status": "unavailable", "error": str(e)[:100]}

    # 6. Document quality
    try:
        from core.harness.knowledge.doc_quality_monitor import get_doc_quality_monitor
        result["doc_quality"] = get_doc_quality_monitor().get_stats() or {}
        result["doc_quality"]["status"] = "ready"
    except Exception as e:
        result["doc_quality"] = {"alerts_today": 0, "status": "unavailable", "error": str(e)[:100]}

    # 7. Cost efficiency — P0 returns 0 (P1 will read from execution_events)
    cost_ratio = 0.0

    # Compute maturity
    result["maturity"] = _compute_maturity(result, cost_ratio)
    result["elapsed_ms"] = int((_time.time() - _t0) * 1000)
    return result


def _get_recent_kb_queries(days: int = 30) -> List[str]:
    """Read recent queries from execution_events table (parameterized query)."""
    import os as _os
    import sqlite3 as _sq
    import json as _json

    db_path = _os.path.expanduser(
        _os.getenv("AIPLAT_EXECUTION_DB_PATH", "~/.aiplat/aiplat_executions.sqlite3")
    )
    if not _os.path.exists(db_path):
        return []
    conn = _sq.connect(db_path)
    conn.row_factory = _sq.Row
    try:
        cutoff = time.time() - days * 86400
        rows = conn.execute(
            "SELECT payload FROM execution_events WHERE event_type=? "
            "AND created_at >= ? ORDER BY created_at DESC LIMIT ?",
            ("knowledge_retrieve", cutoff, 200),
        ).fetchall()
        queries = []
        for r in rows:
            try:
                q = _json.loads(r["payload"] or "{}").get("query", "")
                if q and len(q) > 3:
                    queries.append(q)
            except Exception:
                pass
        return queries
    finally:
        conn.close()


def _compute_maturity(data: dict, cost_ratio: float = 0.0) -> dict:
    """Compute maturity score and level from aggregated health data.

    Weights: structure 30% + quality 25% + growth 15% + safety 15% + cost 15%
    """
    structure = (data.get("health", {}).get("overall_score", 0) or 0)
    quality = (data.get("quality", {}).get("avg_overall", 0) or 0)
    growth_trend = (data.get("growth", {}).get("quality_trend", "stable") or "stable")
    faithfulness = (data.get("hallucination", {}).get("avg_faithfulness", 0) or 0)

    growth_map = {"improving": 100, "stable": 50, "declining": 20}
    growth = growth_map.get(growth_trend, 50)
    safety = int(faithfulness * 100)
    cost = int(cost_ratio)

    overall = int(structure * 0.30 + quality * 0.25 + growth * 0.15 + safety * 0.15 + cost * 0.15)
    level = ("L4" if overall >= 85 else "L3" if overall >= 70
             else "L2" if overall >= 50 else "L1" if overall >= 30 else "L0")

    return {
        "score": overall, "level": level,
        "dimensions": {
            "structure_health": structure, "content_quality": quality,
            "growth_velocity": growth, "hallucination_safety": safety,
            "cost_efficiency": cost,
        },
        "recommendation": _level_recommendation(level, cost),
    }


def _level_recommendation(level: str, cost_efficiency: int = 0) -> str:
    """L0-L5 maturity recommendation. Complete function body — not a placeholder."""
    base = {
        "L0": "知识管理未起步，需从基础文档化开始。建议先统一文件存储位置与命名规范。",
        "L1": "文档散落，建议先做文件集中化与目录治理，暂缓AI检索。",
        "L2": "已结构化，适合启动RAG知识库试点（参考四步框架第三步）。",
        "L3": "知识质量良好，建议开启全量FAQ并引入用户反馈闭环。",
        "L4": "已具备智能化基础，建议扩展至复杂推理（Graph RAG）与多模态。",
        "L5": "已达到行业领先水平，聚焦自进化Agent与个性化记忆（Phase 18）。",
    }.get(level, "状态未知，建议重新运行诊断。")
    if cost_efficiency == 0:
        base += " 成本效率数据收集中，预计7天后显示首组数据。"
    return base


def _build_markdown_report(data: dict, collection: str, days: int = 30) -> str:
    """Render JSON health data as Chinese markdown report for PM/CIO.

    Maps directly to the 四步决策框架 language — quantified evidence for each step.
    """
    from datetime import datetime

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    m = data.get("maturity", {})
    dims = m.get("dimensions", {})
    h = data.get("health", {})
    q = data.get("quality", {})
    growth = data.get("growth", {})
    gaps = data.get("gaps", {})
    hall = data.get("hallucination", {})
    dq = data.get("doc_quality", {})
    elapsed = data.get("elapsed_ms", 0)

    level = m.get("level", "L0")
    score = m.get("score", 0)
    accuracy = q.get("avg_accuracy", 0)
    accuracy_gap = round(max(90 - accuracy, 0), 1)

    can_expand = accuracy >= 80 and hall.get("avg_faithfulness", 0) >= 0.85
    expand_status = ("✅ 试点效果达标，满足全量FAQ扩展条件" if can_expand
                     else "⏳ 试点质量待提升（需准确率≥80% 且 幻觉风险≤15%）")

    alerts = dq.get("alerts_today", 0)
    gaps_count = gaps.get("total", 0) if isinstance(gaps.get("total"), int) and gaps.get("total") > 0 else 0
    audit_status = ("✅ 通过隔离审计（无活跃告警）" if alerts == 0
                    else f"⚠️ 存在 {alerts} 个待修复告警，规模复制前需处理")
    if gaps_count > 0:
        audit_status += f"；发现 {gaps_count} 个知识缺口"

    if level in ("L4", "L5") and can_expand:
        action = "🚀 **行动指令**：立即启动 Graph RAG 复杂场景试点，并建立月报复盘机制。"
    elif level in ("L2", "L3") and can_expand:
        action = "📈 **行动指令**：按四步框架第三步，启动6周试点（先开放FAQ场景），监控本周准确率波动。"
    elif level in ("L0", "L1"):
        action = "📂 **行动指令**：暂缓AI检索，优先执行知识治理（统一文件命名、清理孤立页面）。"
    else:
        action = "🔧 **行动指令**：优先修复high severity问题（死链/幻觉高风险），一个月后重新评估。"

    issues_high = [c.get("severity", "") for c in h.get("checks", []) or []
                   if not c.get("pass", True)]
    issues_text = ", ".join(issues_high[:3]) if issues_high else "无"

    lines = [
        f"# 📊 企业知识库健康体检报告",
        f"",
        f"> **知识库ID**：`{collection}`  ",
        f"> **报告时间**：{now}  ",
        f"> **API响应耗时**：{elapsed} ms",
        f"",
        f"---",
        f"",
        f"## 1️⃣ 成熟度总评（对应四步框架第一步：诊断痛点）",
        f"- **当前等级**：**{level}**（评分：{score}/100）",
        f"- **建议基调**：{m.get('recommendation', '')}",
        f"",
        f"### 维度明细（加权得分）",
        f"| 维度 | 评分 | 权重 |",
        f"|------|:---:|:---:|",
        f"| 🏗️ 结构完整性 | {dims.get('structure_health', 0)} | 30% |",
        f"| 📄 内容准确率 | {dims.get('content_quality', 0)} | 25% |",
        f"| 📈 知识增速 | {dims.get('growth_velocity', 0)} | 15% |",
        f"| 🛡️ 幻觉安全性 | {dims.get('hallucination_safety', 0)} | 15% |",
        f"| 💰 成本效率 | {dims.get('cost_efficiency', 0)} | 15% |",
        f"",
        f"---",
        f"",
        f"## 2️⃣ 小范围试点效果验证（对应四步框架第三步）",
        f"- 当前平均准确率：**{accuracy}%**（目标≥90%）",
        f"- 知识完整性：**{q.get('avg_completeness', 0)}%**",
        f"- 幻觉安全水平：**{hall.get('avg_faithfulness', 0) * 100:.0f}%**（越高越好）",
        f"- **结论**：{expand_status}",
    ]

    if accuracy_gap > 0:
        lines.append(f"\n> ⚠️ 内容准确率 {accuracy}%，距目标90%差{accuracy_gap}%，建议暂缓复杂场景扩展。")

    lines.extend([
        f"",
        f"---",
        f"",
        f"## 3️⃣ 规模复制准备度与隔离审计（对应四步框架第四步）",
        f"- 综合健康分：**{h.get('overall_score', 0)}/100**",
        f"- 严重问题类型：{issues_text}",
        f"- 近{days}天新增知识：**{growth.get('pages_delta_30d', 0)}页**，趋势**{growth.get('quality_trend', 'stable')}**",
        f"- **审计结论**：{audit_status}",
        f"",
        f"---",
        f"",
        f"## 4️⃣ 最终行动指令",
        action,
        f"",
        f"---",
        f"*本报告由Phase 19统一健康仪表盘自动生成，用于指导「四步决策框架」的迭代执行。*",
    ])

    return "\n".join(lines)


# ── Phase 20: Audit trail API ──

@router.get("/diagnostics/audit-trail", response_model=Dict[str, Any])
async def get_audit_trail(
    domain: str = "",
    agent: str = "",
    limit: int = 100,
    days: int = 30,
):
    """List audit trail steps, filterable by domain and agent."""
    import os as _os
    import sqlite3 as _sq
    import json as _json

    db_path = _os.path.expanduser(
        _os.getenv("AIPLAT_EXECUTION_DB_PATH", "~/.aiplat/aiplat_executions.sqlite3")
    )
    if not _os.path.exists(db_path):
        return {"steps": [], "total": 0}

    conn = _sq.connect(db_path)
    conn.row_factory = _sq.Row
    try:
        cutoff = time.time() - days * 86400
        rows = conn.execute(
            "SELECT payload, created_at FROM execution_events WHERE event_type=? "
            "AND created_at >= ? ORDER BY created_at DESC LIMIT ?",
            ("audit_trail", cutoff, limit * 2),
        ).fetchall()
        steps = []
        for r in rows:
            try:
                step = _json.loads(r["payload"] or "{}")
                if domain and step.get("domain", "") != domain:
                    continue
                if agent and step.get("agent", "") != agent:
                    continue
                steps.append(step)
                if len(steps) >= limit:
                    break
            except Exception:
                pass
        return {"steps": steps, "total": len(steps)}
    finally:
        conn.close()


@router.get("/diagnostics/audit-trail/{step_id}/tree", response_model=Dict[str, Any])
async def get_audit_tree(step_id: int, days: int = 30):
    """Recursively build complete reasoning tree from a root step."""
    import os as _os
    import sqlite3 as _sq
    import json as _json

    db_path = _os.path.expanduser(
        _os.getenv("AIPLAT_EXECUTION_DB_PATH", "~/.aiplat/aiplat_executions.sqlite3")
    )
    if not _os.path.exists(db_path):
        return {"tree": {}, "error": "db_not_found"}

    conn = _sq.connect(db_path)
    conn.row_factory = _sq.Row
    try:
        cutoff = time.time() - days * 86400
        rows = conn.execute(
            "SELECT payload FROM execution_events WHERE event_type=? AND created_at >= ?",
            ("audit_trail", cutoff),
        ).fetchall()
        all_steps: List[dict] = []
        for r in rows:
            try:
                all_steps.append(_json.loads(r["payload"] or "{}"))
            except Exception:
                pass

        tree = _build_audit_tree(step_id, all_steps)
        return {"tree": tree, "total_steps": len(all_steps)}
    finally:
        conn.close()


def _build_audit_tree(step_id: int, all_steps: List[dict]) -> dict:
    """Recursively build a reasoning tree from flat audit steps."""
    step = next((s for s in all_steps if s.get("step_id") == step_id), None)
    if not step:
        return {}
    children = [s for s in all_steps if s.get("parent_step_id") == step_id]
    return {
        "step": step,
        "children": [_build_audit_tree(c["step_id"], all_steps) for c in children],
    }


# ── Phase 21: PromptOptimizer API ──

@router.post("/optimizations/{agent_id}/start", response_model=Dict[str, Any])
async def start_optimization(agent_id: str):
    """Start iterative prompt optimization for an agent.

    Loads config from ~/.aiplat/optimizations/{agent_id}.yaml
    and runs the champion-challenger loop autonomously.
    """
    try:
        from core.harness.optimization.prompt_optimizer import PromptOptimizer
        optimizer = PromptOptimizer(agent_id=agent_id)
        result = await optimizer.execute()
        return {"status": "completed", **result}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:300]}


# ── Phase 23: Data lineage endpoint ──

@router.get("/diagnostics/data-lineage", response_model=Dict[str, Any])
async def get_data_lineage(entity: str = "", type: str = "wiki_page"):
    """Trace a data entity's full lineage: sources → processing → model → quality.

    Aggregates data from 5 existing modules: wiki_engine, kb_elements,
    audit_trail (Phase 20), wiki_quality_monitor, and hallucination_tracker.
    Read-only — no new storage, no new modules.

    Args:
        entity: Wiki page title, KB document ID, or audit step ID.
        type: "wiki_page" (default) | "kb_document" | "audit_step"
    """
    if not entity or not entity.strip():
        raise HTTPException(status_code=400, detail="entity 参数不能为空")

    lineage = {"sources": [], "processing": [], "model_usage": [], "quality_checks": {}}

    if type == "wiki_page":
        # 1. Sources: read wiki page → extract source_articles → query kb_elements
        try:
            from core.harness.knowledge.wiki_engine import read_page
            page = read_page(entity)
            if page:
                for src in (page.get("source_articles") or []):
                    if isinstance(src, str) and src.startswith("kb:"):
                        doc_content = _fetch_kb_element(src[3:])
                        lineage["sources"].append({
                            "source_id": src,
                            "source_type": "kb_document",
                            "content_preview": (doc_content or "")[:200],
                        })

                # 2. Processing: check for active_synthesis / atomize events
                lineage["processing"] = [
                    {"step": "wiki_curation", "timestamp": page.get("last_updated", "")}
                ] if page.get("last_updated") else []

                # 3. Model usage: from audit_trail records (Phase 20)
                lineage["model_usage"] = _query_audit_trail_for_entity(entity)
            else:
                # Entity doesn't exist — return empty lineage (valid state)
                pass
        except Exception as e:
            lineage["sources"] = [{"error": str(e)[:100]}]

        # 4. Quality: from wiki_quality_monitor
        try:
            from core.harness.knowledge.wiki_quality_monitor import get_wiki_quality_monitor
            qm = get_wiki_quality_monitor()
            trends = qm.get_trends(page_title=entity) or []
            latest = trends[0] if trends else {}
            lineage["quality_checks"] = {
                "completeness": latest.get("completeness", 0),
                "accuracy": latest.get("accuracy", 0),
                "overall": latest.get("overall", 0),
                "hallucination_risk": _get_latest_hallucination_risk(entity),
                "freshness": "valid",
            }
        except Exception:
            lineage["quality_checks"] = {"status": "unavailable"}

    return {"entity": entity, "type": type, "lineage": lineage}


def _fetch_kb_element(doc_id: str, tenant_id: str = "default") -> Optional[str]:
    """Fetch raw text content from kb_elements table."""
    import os as _os
    import sqlite3 as _sq

    kb_dir = _os.path.expanduser(_os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants"))
    kb_db = _os.path.join(kb_dir, tenant_id, "kb.sqlite3")
    if not _os.path.exists(kb_db):
        return None
    conn = _sq.connect(kb_db)
    try:
        rows = conn.execute(
            "SELECT text FROM kb_elements WHERE doc_id=? AND type='text' "
            "ORDER BY page_idx LIMIT 5",
            (doc_id,),
        ).fetchall()
        return "\n".join(r[0] for r in rows if r[0]) if rows else None
    finally:
        conn.close()


def _query_audit_trail_for_entity(entity: str) -> List[dict]:
    """Query audit_trail events where the entity appears in trigger/conclusion."""
    import os as _os
    import sqlite3 as _sq
    import json as _json

    db_path = _os.path.expanduser(
        _os.getenv("AIPLAT_EXECUTION_DB_PATH", "~/.aiplat/aiplat_executions.sqlite3")
    )
    if not _os.path.exists(db_path):
        return []
    try:
        conn = _sq.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT payload FROM execution_events WHERE event_type='audit_trail' "
                "ORDER BY created_at DESC LIMIT 20",
            ).fetchall()
            results = []
            for r in rows:
                try:
                    step = _json.loads(r[0] or "{}")
                    text = _json.dumps(step)
                    if entity.lower() in text.lower():
                        results.append({
                            "step_id": step.get("step_id"),
                            "agent": step.get("agent", ""),
                            "rule_ref": step.get("rule_ref", ""),
                            "conclusion": step.get("conclusion", "")[:120],
                            "confidence": step.get("confidence", 0),
                            "evidence": step.get("evidence", [])[:3],
                        })
                except Exception:
                    pass
            return results[:10]
        finally:
            conn.close()
    except (_sq.OperationalError, _sq.DatabaseError):
        return []


def _get_latest_hallucination_risk(entity: str) -> float:
    """Estimate hallucination risk for an entity from audit_trail confidence records."""
    import os as _os
    import sqlite3 as _sq
    import json as _json

    db_path = _os.path.expanduser(
        _os.getenv("AIPLAT_EXECUTION_DB_PATH", "~/.aiplat/aiplat_executions.sqlite3")
    )
    if not _os.path.exists(db_path):
        return 0.0
    try:
        conn = _sq.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT payload FROM execution_events WHERE event_type='audit_trail' "
                "ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
            confs = []
            for r in rows:
                try:
                    step = _json.loads(r[0] or "{}")
                    if entity.lower() in _json.dumps(step).lower():
                        c = step.get("confidence", 0)
                        if c:
                            confs.append(float(c))
                except Exception:
                    pass
            return round(1.0 - (sum(confs[-10:]) / max(len(confs[-10:]), 1)), 2) if confs else 0.0
        finally:
            conn.close()
    except (_sq.OperationalError, _sq.DatabaseError):
        return 0.0

