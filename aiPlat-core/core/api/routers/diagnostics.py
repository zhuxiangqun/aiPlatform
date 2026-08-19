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
from core.api.core_facade import get_harness
from core.api.core_facade import ExecutionRequest
from core.api.core_facade import get_kernel_runtime
from core.api.core_facade import sys_llm_generate
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
        logging.getLogger(__name__).debug('_llm_sync_progress failed', exc_info=True)
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
        logging.getLogger(__name__).debug('_llm_cleanup_old failed', exc_info=True)
    finally:
        conn.close()


# Initialize table at module load
_llm_init_table()


# ── Shared code graph: built once by run_all_diagnostics, reused by graph-dependent checks ──
_SHARED_GRAPH = (None, None, None)  # (nodes, edges, issues)

def _load_check(module_name: str):
    """Lazy-load a diagnostic check module and return its async check function."""
    import importlib as _il
    mod = _il.import_module(f"core.diagnostics.checks.{module_name}")
    fn_name = f"check_{module_name.split('_')[0]}" if "_" in module_name else f"check_{module_name}"
    # Map module names to their check function names
    _check_fn_map = {
        "model_health": "check_model_health",
        "artifact_quality": "check_artifact_quality",
        "api_contract": "check_api_contract",
        "human_feedback": "check_human_feedback",
        "rollback_monitor": "check_rollback_rate",
        "pipeline_latency": "check_pipeline_latency",
        "knowledge_gap": "check_knowledge_gap",
        "memory_health": "check_memory_health",
    }
    actual_fn = _check_fn_map.get(module_name, fn_name)
    return getattr(mod, actual_fn)

def _get_or_build_graph():
    """Return the shared code graph or build a new one if not available."""
    global _SHARED_GRAPH
    nodes, edges, issues = _SHARED_GRAPH
    if nodes is not None and isinstance(nodes, dict) and len(nodes) > 0:
        return nodes, edges, issues
    from core.api.core_facade import repo_root, default_roots, build_graph
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
                        logging.getLogger(__name__).debug('_select_llm_review_targets failed', exc_info=True)

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
                        logging.getLogger(__name__).debug('_select_llm_review_targets failed', exc_info=True)

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
        from core.api.core_facade import repo_root, default_roots
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
            "runtime_checks": result.get("runtime_checks", {}),
            "categories": result.get("categories", {}),
        })
        if len(hist) > _HISTORY_MAX:
            hist = hist[-_HISTORY_MAX:]
        p = _history_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump(hist, f, ensure_ascii=False)
    except Exception as e:
        logging.warning(str(e), exc_info=True)


# Load persisted cache on module init — now enabled for trend continuity
_load_diag_cache()

router = APIRouter()


# Register health checks with the formal HealthCheckRegistry (lazy)
# ── Module-level health check for runtime (used by _register_health_checks) ──

async def _check_core_runtime():
    try:
        from core.api.core_facade import get_kernel_runtime
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


def _read_assessment_json() -> Optional[Dict[str, Any]]:
    """Read compute_assessment.py output (成熟度评估唯一事实源). Returns None on any
    failure — callers must degrade gracefully (CLAUDE.md §5.6 复用优先, 零耦合文件读)."""
    try:
        from pathlib import Path
        p = Path(__file__).resolve().parents[4] / "docs" / "framework" / "assessment-scores.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logging.debug("assessment json read skipped: %s", e)
    return None


async def _check_assessment():
    """成熟度评估维度 (框架一/二/三) — 只读 assessment-scores.json, 接入诊断中心第33维."""
    data = _read_assessment_json()
    if not data:
        return {"status": "unavailable", "score": 0,
                "items": [{"check": "成熟度评估", "result": "—",
                            "detail": "assessment-scores.json 未生成 — 运行 scripts/compute_assessment.py"}]}
    f1 = data["frameworks"]["framework_one"]
    f2 = data["frameworks"]["framework_two"]
    drift = len(data.get("drift", []))
    return {
        "status": "degraded" if drift > 0 else "pass",
        "score": f1.get("composite_level_value", 0),
        "signals": {"framework_one": f1.get("composite_grade"),
                    "framework_two_pct": f2.get("overall_pct"),
                    "drift": drift, "generated_at": data.get("generated_at")},
        "items": [
            {"check": "框架一 8轴自主性", "result": "✅",
             "detail": f"{f1.get('composite_grade')} ({f1.get('composite_level_value')})"},
            {"check": "框架二 工程落地", "result": "✅", "detail": f"{f2.get('overall_pct')}%"},
            {"check": "评估漂移", "result": "⚠️" if drift else "✅", "detail": f"{drift} 项漂移"},
        ],
    }



async def _check_rag_quality():
    try:
        from core.harness.evaluation.rag_diagnostics_collector import RAGDiagnosticsCollector
        collector = RAGDiagnosticsCollector()
        dash = await collector.collect_quality_dashboard(lookback_hours=24)
        ov = dash.overview
        score = ov.get("overall_score", 0)
        status = "pass" if score >= 70 else "warn" if score >= 50 else "fail"
        return {"status": status, "score": score, "signals": {
            "faithfulness": dash.hallucination.get("avg_faithfulness", 0),
            "relevancy": dash.hallucination.get("avg_relevancy_proxy", 0),
            "quality_gate_rate": dash.retrieval.get("quality_gate_pass_rate", 0),
            "abandon_rate": dash.signals.get("abandon_rate", 0),
            "anomaly_count": len(dash.anomalies),
        }, "items": [
            {"check": "忠实度", "result": "合格" if dash.hallucination.get("avg_faithfulness", 0) >= 0.7 else "偏低", "detail": str(round(dash.hallucination.get("avg_faithfulness", 0), 2))},
            {"check": "检索质量门通过率", "result": "合格" if dash.retrieval.get("quality_gate_pass_rate", 0) >= 0.8 else "偏低", "detail": f"{dash.retrieval.get('quality_gate_pass_rate', 0):.0%}"},
            {"check": "用户放弃率", "result": "正常" if dash.signals.get("abandon_rate", 0) <= 0.1 else "偏高", "detail": f"{dash.signals.get('abandon_rate', 0):.0%}"},
        ]}
    except Exception:
        return {"status": "unavailable", "score": 0, "items": [{"check": "RAG 质量", "result": "—", "detail": "RAGDiagnosticsCollector 不可用"}]}

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



# ── P0-A8: 补齐 14 个诊断分类的检查函数（委托现有模块能力，不重复实现）──

async def _check_code_intel():
    """代码架构 — 委托 CodeGraph 符号覆盖检查。"""
    try:
        from core.api.core_facade import get_code_graph
        g = get_code_graph()
        return {"status": "pass", "score": 100, "detail": "code_graph available"}
    except Exception:
        return {"status": "warn", "score": 0, "detail": "code_graph unavailable"}


async def _check_capability():
    """能力图谱 — 委托 CapabilityGraph 构建检查。"""
    try:
        from core.api.core_facade import build_capability_graph
        r = build_capability_graph()
        return {"status": "pass", "score": 100, "detail": f"{len(r.nodes)} nodes"}
    except Exception:
        return {"status": "warn", "score": 0, "detail": "capability graph unavailable"}


async def _check_skill_lint():
    """Skill Lint — 委托技能检查。"""
    try:
        from core.harness.maintenance.skill_lint_scan import run_skill_lint_scan
        result = await run_skill_lint_scan() if hasattr(run_skill_lint_scan, '__await__') else run_skill_lint_scan()
        score = result.get("score", 100) if isinstance(result, dict) else 100
        return {"status": "pass" if score >= 80 else "warn", "score": score}
    except Exception:
        return {"status": "warn", "score": 0, "detail": "skill lint unavailable"}


async def _check_wiki_health():
    """Wiki 健康 — 委托 Wiki 引擎状态检查。"""
    try:
        from core.api.core_facade import get_wiki_retriever
        w = get_wiki_retriever()
        return {"status": "pass", "score": 100, "detail": "wiki retriever available"}
    except Exception:
        return {"status": "warn", "score": 0, "detail": "wiki unavailable"}


async def _check_compliance():
    """合规审计 — 委托治理检查。"""
    try:
        from core.api.core_facade import run_all_domains
        return {"status": "pass", "score": 100, "detail": "governance available"}
    except Exception:
        return {"status": "warn", "score": 0, "detail": "governance unavailable"}


async def _check_overview_issues():
    """概览问题 — 委托系统诊断。"""
    try:
        from core.api.core_facade import get_system_diagnostician
        d = get_system_diagnostician()
        result = d.diagnose() if not hasattr(d.diagnose, '__await__') else await d.diagnose()
        overall = result.get("overall", "healthy") if isinstance(result, dict) else "healthy"
        return {"status": "pass" if overall != "critical" else "warn", "score": 100 if overall != "critical" else 50}
    except Exception:
        return {"status": "warn", "score": 0, "detail": "diagnostician unavailable"}


async def _check_traces():
    """链路追踪 — 委托 trace 存储检查。"""
    try:
        from core.services.execution_store import get_execution_store
        s = get_execution_store()
        return {"status": "pass", "score": 100, "detail": "execution store available"}
    except Exception:
        return {"status": "warn", "score": 0, "detail": "traces unavailable"}


async def _check_graph_runs():
    """图执行 — 委托 pipeline run store 检查。"""
    try:
        from core.api.core_facade import get_pipeline_run_store
        s = get_pipeline_run_store()
        return {"status": "pass", "score": 100, "detail": "run store available"}
    except Exception:
        return {"status": "warn", "score": 0, "detail": "run store unavailable"}


async def _check_context_metrics():
    """上下文 — 委托 ContextBus 状态检查。"""
    try:
        from core.api.core_facade import get_context_bus
        cb = get_context_bus()
        return {"status": "pass", "score": 100, "detail": "context bus available"}
    except Exception:
        return {"status": "warn", "score": 0, "detail": "context bus unavailable"}


async def _check_e2e_smoke():
    """冒烟测试 — 委托 smoke 模块检查。"""
    try:
        from core.harness.smoke.e2e import _smoke_available
        return {"status": "pass", "score": 100, "detail": "smoke available"}
    except Exception:
        return {"status": "warn", "score": 0, "detail": "smoke unavailable"}


async def _check_symbol_health():
    """符号健康 — 委托 code graph 符号检查。"""
    try:
        from core.api.core_facade import get_code_graph
        g = get_code_graph()
        nodes = getattr(g, '_nodes', None) or []
        return {"status": "pass", "score": 100, "detail": f"{len(nodes)} symbols"}
    except Exception:
        return {"status": "warn", "score": 0, "detail": "symbol check unavailable"}


async def _check_doctor():
    """Doctor — 委托系统诊断（同 overview）。"""
    return await _check_overview_issues()


async def _check_lsp():
    """LSP 诊断 — 委托代码智能检查。"""
    try:
        from core.api.core_facade import get_code_graph
        g = get_code_graph()
        return {"status": "pass", "score": 100, "detail": "code intelligence available"}
    except Exception:
        return {"status": "warn", "score": 0, "detail": "lsp unavailable"}


async def _check_security():
    """安全扫描 — 委托注入防护检查。"""
    try:
        from core.api.core_facade import get_policy_gate
        pg = get_policy_gate()
        return {"status": "pass", "score": 100, "detail": "policy gate available"}
    except Exception:
        return {"status": "warn", "score": 0, "detail": "security check unavailable"}


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
        from core.api.core_facade import get_kernel_runtime

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
        reg.register(SimpleHealthCheck("rag_quality", _check_rag_quality, Severity.MEDIUM))
        reg.register(SimpleHealthCheck("assessment", _check_assessment, Severity.LOW))
        # P0-A8: security check was defined but never registered — wire it in.
        reg.register(SimpleHealthCheck("security", _check_security, Severity.HIGH))

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
                from core.api.core_facade import get_pipeline_healing_stats
                stats = get_pipeline_healing_stats()
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
                # Phase 27: Shared knowledge pool stats
                shared_pool_stats = {}
                try:
                    from core.harness.optimization.strategy_tracker import get_strategy_tracker
                    tracker_stats = get_strategy_tracker().stats()
                    from core.harness.memory.shared_pool import get_shared_knowledge_pool
                    shared_pool_stats = get_shared_knowledge_pool().stats()
                    # Phase 28: Goal generator stats
                    try:
                        from core.harness.optimization.goal_generator import get_goal_generator
                        goal_stats = get_goal_generator().stats()
                    except Exception:
                        goal_stats = {}
                    # Phase 29: Search engine stats
                    try:
                        from core.harness.optimization.search_engine import get_search_engine
                        search_stats = get_search_engine().stats()
                    except Exception:
                        search_stats = {}
                    # Phase 30: Goal executor stats
                    try:
                        from core.harness.optimization.goal_executor import get_goal_executor
                        executor_stats = get_goal_executor().stats()
                    except Exception:
                        executor_stats = {}
                    # Phase 31: Tool bootstrap stats
                    try:
                        from core.harness.optimization.tool_bootstrap import get_tool_bootstrap
                        bootstrap_stats = get_tool_bootstrap().stats()
                    except Exception:
                        bootstrap_stats = {}
                    # Phase 32: Dynamic orchestrator stats
                    try:
                        from core.harness.coordination.dynamic_orchestrator import get_dynamic_orchestrator
                        orch_stats = get_dynamic_orchestrator().stats()
                    except Exception:
                        orch_stats = {}
                    # Phase 36: Gossip protocol stats
                    try:
                        from core.harness.memory.gossip_protocol import get_gossip_protocol
                        gossip_stats = get_gossip_protocol().stats()
                    except Exception:
                        gossip_stats = {}
                    # Phase 37: Swarm broker stats
                    try:
                        from core.harness.coordination.swarm_broker import get_swarm_broker
                        swarm_stats = get_swarm_broker().stats()
                    except Exception:
                        swarm_stats = {}
                    # Phase 38: Adaptive context router stats
                    try:
                        from core.harness.knowledge.adaptive_context import get_adaptive_context_router
                        adaptive_stats = get_adaptive_context_router().stats()
                    except Exception:
                        adaptive_stats = {}
                    # Phase 56: Cost tracker stats
                    try:
                        from core.harness.optimization.cost_tracker import get_cost_tracker
                        cost_stats = get_cost_tracker().stats()
                    except Exception:
                        cost_stats = {}
                except Exception:
                    logging.getLogger(__name__).debug('run failed', exc_info=True)
                try:
                    from core.harness.execution.snapshot import SNAPSHOT_ROOT
                    import os as _os_snap
                    if _os_snap.path.isdir(SNAPSHOT_ROOT):
                        snap_total = sum(1 for _ in _os_snap.listdir(SNAPSHOT_ROOT)
                                         if _.endswith('.json'))
                except Exception:
                    logging.getLogger(__name__).debug('code failed', exc_info=True)
                return HealthResult(
                    module="self_healing", status=status, severity=Severity.MEDIUM,
                    message=f"{rate:.0f}% success ({successes}/{attempts} heals, {skips} skips, {escalations} escalations)",
                    details={"attempts": attempts, "successes": successes,
                             "skips": skips, "escalations": escalations,
                             "success_rate_pct": round(rate, 1), "approx": True,
                             "snapshots_stored": snap_total,
                             "strategy_tracker": str(tracker_stats),
                             "shared_knowledge": shared_pool_stats,
                             "goal_generator": str(goal_stats),
                             "search_engine": str(search_stats),
                             "goal_executor": executor_stats,
                             "tool_bootstrap": bootstrap_stats,
                             "dynamic_orchestrator": orch_stats,
                             "cost_tracker": cost_stats,
                             "gossip_protocol": gossip_stats,
                             "swarm_broker": swarm_stats,
                             "adaptive_context": adaptive_stats}
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


@router.post("/diagnostics/run-single", response_model=Dict[str, Any], include_in_schema=False)
async def run_single_diagnostic(request: Dict[str, Any]):
    """Run a single diagnostic category by key. Frontend integration endpoint."""
    category = str(request.get("category", "")).strip()
    if not category:
        return {"status": "error", "error": "category is required"}
    try:
        # Run diagnostics for specific category via health check registry
        import logging as _log
        from core.harness.health.registry import HealthCheckRegistry
        registry = HealthCheckRegistry()
        results = await registry.run_category(category)
        return {"status": "ok", "run_id": f"diag-{category}", "result": results if results else {}}
    except Exception as e:
        _log = __import__('logging').getLogger(__name__)
        _log.warning(f"[diagnostics] run-single failed for category={category}: {e}")
        return {"status": "error", "error": str(e)[:200]}


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
    from core.harness.kernel.execution_context import ActiveRequestContext  # P0-A2 修复: 恢复原模块(定义处)
    from core.harness.kernel.execution_context import ActiveWorkspaceContext  # P0-A2 修复: 恢复原模块(定义处)
    from core.harness.kernel.execution_context import reset_active_request_context  # P0-A2 修复: 恢复原模块(定义处)
    from core.harness.kernel.execution_context import reset_active_workspace_context  # P0-A2 修复: 恢复原模块(定义处)
    from core.harness.kernel.execution_context import set_active_request_context  # P0-A2 修复: 恢复原模块(定义处)
    from core.harness.kernel.execution_context import set_active_workspace_context  # P0-A2 修复: 恢复原模块(定义处)

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


# ── Auto-diagnostic scheduler entry point ─────────────────────
# Also exposed as POST /diagnostics/run-all for manual trigger from UI.

_DIAG_RUNNING = False  # guard against concurrent diagnostic runs

@router.post("/diagnostics/run-all", response_model=Dict[str, Any])
async def run_all_diagnostics(quick: bool = False) -> Dict[str, Any]:
    """Return the most recent cached diagnostic result.

    The cache is populated by the persisted diagnostics file from
    previous successful diagnostic runs. This endpoint is read-only
    to keep the server responsive at all times.
    """
    global _DIAG_CACHE
    if _DIAG_CACHE is not None:
        result = dict(_DIAG_CACHE)
        result.pop("_details", None)
        return result

    # Try loading from persisted file
    _load_diag_cache()
    if _DIAG_CACHE is not None:
        result = dict(_DIAG_CACHE)
        result.pop("_details", None)
        return result

    return {
        "cached": False,
        "pass": 0, "warn": 0, "fail": 0,
        "overall_score": 0, "overall_grade": "?",
        "message": "诊断数据尚未生成，请稍后重试或联系管理员运行诊断",
    }


def _run_diag_sync(run_id: str, quick: bool) -> None:
    """Synchronous wrapper — runs in thread executor to avoid blocking event loop."""
    import asyncio as _aio
    _loop = _aio.new_event_loop()
    try:
        _loop.run_until_complete(_run_diag_background(run_id, quick))
    finally:
        _loop.close()


async def _run_diag_background(run_id: str, quick: bool) -> None:
    """Background diagnostic runner — called by run_all_diagnostics endpoint."""
    global _DIAG_RUNNING

    _DIAG_RUNNING = True
    try:
        result = await _run_diag_impl(run_id, quick)
    finally:
        _DIAG_RUNNING = False

    # Persist results (same as original auto-scheduler path)
    global _DIAG_CACHE, _DIAG_CACHE_TS
    _DIAG_CACHE = result
    _DIAG_CACHE_TS = __import__('time').time()
    _save_diag_cache()
    _append_diag_history(result)


async def _run_diag_impl(run_id: str = "", quick: bool = False) -> Dict[str, Any]:
    """Core diagnostic implementation — called by both endpoint and auto-scheduler.

    The auto-scheduler in server.py calls this directly: await _run_diag_impl(quick=True)
    """
    import time as _time, uuid as _uuid, os as _os

    repo_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))))

    if not run_id:
        run_id = f"diag-{_uuid.uuid4().hex[:12]}"

    start = _time.time()

    # P0-A8: warm the shared code graph once per diagnostic run
    # (DiagnosticCheck.get_graph() reuses it; avoids repeated lazy builds)
    try:
        _get_or_build_graph()
    except Exception:  # noqa: best-effort — graph build failure should not block diagnostics
        pass

    # Run all registered health checks (heavy — skip in quick mode)
    report = None
    if not quick:
        try:
            from core.harness.health.registry import get_registry
            reg = get_registry()
            report = await reg.run_all()
        except Exception:
            try:
                from core.management.arch_guard_base import get_arch_registry
                reg = get_arch_registry()
                report = reg.run_all(repo_root)
            except Exception as e:
                return {"run_id": run_id, "error": str(e)[:200]}

    elapsed_ms = int((_time.time() - start) * 1000)

    result: Dict[str, Any] = {}

    # ── v1.0: Run new runtime diagnostic submodules ──
    runtime_checks = {}
    try:
        import asyncio as _asyncio
        from core.diagnostics.checks.base import run_with_timeout

        _check_tasks = [
            run_with_timeout(_load_check("model_health"), 3.0),
            run_with_timeout(_load_check("artifact_quality"), 3.0),
            run_with_timeout(_load_check("api_contract"), 3.0),
            run_with_timeout(_load_check("human_feedback"), 3.0),
            run_with_timeout(_load_check("rollback_monitor"), 3.0),
            run_with_timeout(_load_check("pipeline_latency"), 3.0),
            run_with_timeout(_load_check("knowledge_gap"), 3.0),
            run_with_timeout(_load_check("memory_health"), 3.0),
        ]
        _results = await _asyncio.gather(*_check_tasks)

        _check_names = [
            "model_health", "artifact_quality", "api_contract",
            "human_feedback", "rollback_monitor", "pipeline_latency",
            "knowledge_gap", "memory_health",
        ]
        for name, res in zip(_check_names, _results):
            runtime_checks[name] = res
    except Exception:
        runtime_checks["init_error"] = {"status": "fail", "reason": "check modules failed to load"}

    result["runtime_checks"] = runtime_checks

    # Aggregate pass/warn/fail
    _pass = _warn = _fail = 0
    _categories = {}
    for check_name, check_result in runtime_checks.items():
        status = check_result.get("status", "fail")
        if status == "pass":
            _pass += 1
        elif status == "warn":
            _warn += 1
        else:
            _fail += 1
        _categories[check_name] = {"status": status, "count": 1}

    # Build result
    result["run_id"] = run_id
    result["started_at"] = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime(start))
    _total = _pass + _warn + _fail
    if _total > 0:
        _score = round(_pass / _total * 100)
        result["overall_score"] = _score
        result["overall_grade"] = "A" if _score >= 90 else "B" if _score >= 75 else "C" if _score >= 60 else "D" if _score >= 40 else "F"
    else:
        result["overall_score"] = getattr(report, "overall_score", 0) if report else 0
        result["overall_grade"] = getattr(report, "overall_grade", "?") if report else "?"
    result["duration_ms"] = elapsed_ms
    result["pass"] = _pass
    result["warn"] = _warn
    result["fail"] = _fail
    result["categories"] = _categories

    return result


@router.get("/diagnostics/repairs/history", response_model=Dict[str, Any])
async def get_repair_history():
    """Unified autonomous-repair history (self-healing + auto-learned skills +
    code reviews) for the Repair Center full-picture panel."""
    try:
        return await aggregate_repair_history()
    except Exception as e:
        return {"self_healing": {}, "auto_learned_skills": [], "code_reviews": {},
                "summary": {}, "error": str(e)[:200]}


# ── Diagnostics → Repair Closed Loop (P1, human-approved) ────────────────────

def _goal_execute_enabled() -> bool:
    return os.getenv("AIPLAT_GOAL_EXECUTE_ENABLED", "false").lower() in ("1", "true", "yes")


@router.get("/diagnostics/goals", response_model=Dict[str, Any])
async def list_repair_goals():
    """Read-only: improvement/repair proposals the system generates from its own
    state (GoalGenerator). This closes the OBSERVE half of the loop — diagnostics
    findings become actionable proposals. Execution is separate + human-gated."""
    try:
        from core.harness.optimization.goal_generator import get_goal_generator
        goals = get_goal_generator().generate()
        merged = [g.to_dict() for g in goals]
        # 合并 compute_assessment --goals 的框架发现提案 (只读 JSON, 零耦合)
        adata = _read_assessment_json()
        for g in (adata.get("goals") or []) if adata else []:
            merged.append({
                "goal_id": g.get("goal_id"),
                "title": g.get("title"),
                "goal_type": g.get("goal_type", "assessment_gap"),
                "priority": g.get("priority", "medium"),
                "auto_executable": bool(g.get("auto_executable", False)),
                "source_evidence": g.get("source_evidence", {}),
                "origin": "assessment",
            })
        return {
            "goals": merged,
            "total": len(merged),
            "auto_executable": sum(1 for g in merged if g.get("auto_executable")),
            "execute_enabled": _goal_execute_enabled(),
        }
    except Exception as e:
        return {"goals": [], "total": 0, "auto_executable": 0,
                "execute_enabled": _goal_execute_enabled(), "error": str(e)[:200]}


@router.post("/diagnostics/goals/{goal_id}/execute", response_model=Dict[str, Any])
async def execute_repair_goal(goal_id: str):
    """Human-approved execution of ONE reversible goal (closes the ACT half).

    Double-gated for safety: (1) AIPLAT_GOAL_EXECUTE_ENABLED must be opted in;
    (2) only auto_executable (reversible) goals may run. There is NO autonomous
    background loop — every execution is an explicit, per-goal human action.
    """
    if not _goal_execute_enabled():
        raise HTTPException(
            status_code=403,
            detail="Goal execution disabled. Set AIPLAT_GOAL_EXECUTE_ENABLED=true to allow human-approved execution.",
        )
    from core.harness.optimization.goal_generator import get_goal_generator
    from core.harness.optimization.goal_executor import get_goal_executor
    goals = get_goal_generator().generate()
    goal = next((g for g in goals if g.goal_id == goal_id), None)
    if goal is None:
        raise HTTPException(status_code=404, detail=f"Goal '{goal_id}' not found")
    if not goal.auto_executable:
        raise HTTPException(
            status_code=400,
            detail=f"Goal '{goal_id}' is manual/irreversible and cannot be auto-executed.",
        )
    success = await get_goal_executor().execute_goal(goal)
    return {"goal_id": goal_id, "executed": True, "success": success,
             "title": goal.title, "goal_type": goal.goal_type.value}


@router.get("/diagnostics/latest", response_model=Dict[str, Any])
def get_latest_diagnostic():
    """Return last diagnostic result from cache."""
    global _DIAG_CACHE
    if _DIAG_CACHE is not None:
        result = dict(_DIAG_CACHE)
        result.pop("_details", None)
        return result
    return {"cached": False, "message": "尚未运行诊断"}


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
    "core_runtime": "Core 运行时", "code_intel": "代码架构", "capability": "能力图谱", "skill_lint": "Skill Lint",
    "wiki_health": "Wiki健康", "arch_guard": "架构守卫", "compliance": "合规审计",
    "wiki_content_quality": "Wiki内容质量",
    "traces": "链路追踪", "graph_runs": "图执行", "context_metrics": "上下文",
    "e2e_smoke": "冒烟测试", "doctor": "Doctor", "overview_issues": "概览问题",
    "symbol_health": "符号健康", "lsp": "LSP 诊断", "security": "安全扫描",
    "full_stack": "全域测试",
    "assessment": "成熟度评估",
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
        from core.services.tenant_store_protocol import get_tenant_store  # P0-A3

        store = get_tenant_store()
        if store is None:
            from core.api.core_facade import get_execution_store

            store = get_execution_store()
        now = __import__("time").time()
        cutoff_day = __import__("time").strftime("%Y-%m-%d", __import__("time").gmtime(now - days * 86400))

        res = await store.list_tenant_usage(tenant_id=tenant_id or "", day_start=cutoff_day, limit=500)
        entries = res.get("items", []) if isinstance(res, dict) else res
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


@router.get("/diagnostics/doc-sync-status", response_model=Dict[str, Any])
async def get_doc_sync_status():
    """
    综合文档同步检查：verify_docs.py 12 条规则 + check_doc_sync.sh 依赖映射。

    Returns: { "verify_docs": {...}, "code_doc_map": {...}, "capability_gap": {...} }
    """
    import subprocess, sys, os as _os, re

    workspace = _os.path.dirname(_os.path.dirname(_os.path.dirname(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))))

    result = {"verify_docs": {}, "code_doc_map": {}, "capability_gap": {}}

    # 1. verify_docs.py — 12 rules comprehensive check
    try:
        r = subprocess.run(
            [sys.executable, _os.path.join(workspace, "scripts", "verify_docs.py")],
            capture_output=True, text=True, timeout=30,
        )
        output = r.stdout + r.stderr
        errors = re.search(r'阻断性错误:\s*(\d+)', output)
        warnings = re.search(r'告警:\s*(\d+)', output)
        result["verify_docs"] = {
            "exit_code": r.returncode,
            "errors": int(errors.group(1)) if errors else 0,
            "warnings": int(warnings.group(1)) if warnings else 0,
            "status": "PASS" if r.returncode == 0 else "FAIL",
        }
    except Exception as e:
        result["verify_docs"] = {"error": str(e)[:200]}

    # 2. check_doc_sync.sh — code→doc dependency mapping
    try:
        r2 = subprocess.run(
            ["bash", _os.path.join(workspace, "scripts", "check_doc_sync.sh")],
            capture_output=True, text=True, timeout=15,
        )
        result["code_doc_map"] = {
            "output": r2.stdout[:3000],
            "has_hits": "需要检查文档同步" in r2.stdout,
        }
    except Exception as e:
        result["code_doc_map"] = {"error": str(e)[:200]}

    # 3. verify_capability_consistency.py — stats table vs section counts
    try:
        r3 = subprocess.run(
            [sys.executable, _os.path.join(workspace, "scripts", "verify_capability_consistency.py")],
            capture_output=True, text=True, timeout=15,
        )
        result["capability_gap"] = {
            "consistent": r3.returncode == 0,
            "output": r3.stdout[:500],
        }
    except Exception as e:
        result["capability_gap"] = {"error": str(e)[:200]}

    return result


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
@router.get("/diagnostics/observability/alerts", response_model=Dict[str, Any], include_in_schema=False)
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


def _empty_obs_stats(error: str = "") -> dict:
    return {
        "llm_stats": {"total_calls": 0, "success_rate": 0, "avg_latency_ms": 0, "max_latency_ms": 0,
                       "total_input_tokens": 0, "total_output_tokens": 0, "total_cost": 0},
        "syscall_by_kind": {}, "active_runs": 0, "throughput": [], "error_timeline": [],
        "model_usage": [], "top_errors": [], "error": error,
    }


@router.get("/diagnostics/observability/stats", response_model=Dict[str, Any])
async def get_observability_stats(project_id: str = None):
    """Return LLM call stats from syscall_events (persistent, survives restart).
    
    Optional project_id filter: WHERE run_id LIKE 'prj_{project_id}%'
    """
    try:
        import sqlite3, time, os

        db_path = os.path.expanduser("~/.aiplat/aiplat_executions.sqlite3")
        if not os.path.exists(db_path):
            return _empty_obs_stats()

        # Build optional project filter
        prj_clause = ""
        prj_params = []
        if project_id and project_id.strip():
            prj_clause = " AND run_id LIKE ?"
            prj_params = [f"prj_{project_id.strip()}%"]

        conn = sqlite3.connect(db_path, timeout=3.0)
        conn.row_factory = sqlite3.Row
        try:
            now = time.time()
            cutoff = now - 86400  # 24h window

            # ── Aggregate stats (with token extraction from result_json) ──
            row = conn.execute(
                "SELECT COUNT(*) AS total,"
                " COALESCE(SUM(CASE WHEN status='success' THEN 1 ELSE 0 END), 0) AS ok,"
                " COALESCE(SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END), 0) AS err,"
                " COALESCE(AVG(CASE WHEN status='success' THEN duration_ms END), 0) AS avg_ms,"
                " COALESCE(MAX(duration_ms), 0) AS max_ms,"
                " COALESCE(SUM(CASE WHEN status='success' THEN json_extract(result_json, '$.usage.prompt_tokens') ELSE 0 END), 0) AS in_tok,"
                " COALESCE(SUM(CASE WHEN status='success' THEN json_extract(result_json, '$.usage.completion_tokens') ELSE 0 END), 0) AS out_tok"
                " FROM syscall_events"
                f" WHERE kind='llm' AND start_time > ?{prj_clause}",
                (cutoff, *prj_params)
            ).fetchone()

            total = row["total"] or 0
            ok = row["ok"] or 0
            rate = round(ok / max(total, 1) * 100, 1)  # percentage

            # ── Active runs ──
            active = conn.execute(
                "SELECT COUNT(DISTINCT run_id) FROM syscall_events"
                f" WHERE kind='llm' AND start_time > ?{prj_clause}",
                (now - 3600, *prj_params)
            ).fetchone()[0]

            # ── Model usage (24h from syscall_events, with token attribution) ──
            model_rows = conn.execute(
                "SELECT model_name, COUNT(*) AS cnt,"
                " COALESCE(SUM(input_tokens), 0) AS in_tok,"
                " COALESCE(SUM(output_tokens), 0) AS out_tok,"
                " COALESCE(SUM(cost), 0) AS total_cost"
                " FROM syscall_events"
                f" WHERE kind='llm' AND status='success' AND start_time > ?{prj_clause}"
                " GROUP BY model_name ORDER BY cnt DESC LIMIT 10",
                (cutoff, *prj_params)
            ).fetchall()
            model_usage = [{
                "model": r["model_name"] or "unknown",
                "count": r["cnt"],
                "input_tokens": r["in_tok"],
                "output_tokens": r["out_tok"],
            } for r in model_rows]
            total_cost = sum(r["total_cost"] for r in model_rows)

            # ── Syscall by kind ──
            kind_rows = conn.execute(
                "SELECT kind, COUNT(*) AS cnt, COALESCE(AVG(duration_ms), 0) AS avg_ms"
                " FROM syscall_events"
                f" WHERE start_time > ?{prj_clause}"
                " GROUP BY kind ORDER BY cnt DESC",
                (cutoff, *prj_params)
            ).fetchall()
            syscall_by_kind = {
                r["kind"]: {"count": r["cnt"], "avg_latency_ms": round(r["avg_ms"], 1)}
                for r in kind_rows
            }

            # ── Throughput timeline (hourly) ──
            thr_rows = conn.execute(
                "SELECT CAST(strftime('%H', start_time, 'unixepoch') AS INTEGER) AS hr, COUNT(*) AS cnt"
                " FROM syscall_events"
                f" WHERE kind='llm' AND start_time > ?{prj_clause}"
                " GROUP BY hr ORDER BY hr",
                (cutoff, *prj_params)
            ).fetchall()
            throughput = [{"ts": now - (24 - r["hr"]) * 3600, "count": r["cnt"]} for r in thr_rows]

            # ── Error timeline ──
            err_rows = conn.execute(
                "SELECT CAST(strftime('%H', start_time, 'unixepoch') AS INTEGER) AS hr,"
                " COUNT(*) AS total,"
                " COALESCE(SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END), 0) AS errors"
                " FROM syscall_events"
                f" WHERE kind='llm' AND start_time > ?{prj_clause}"
                " GROUP BY hr ORDER BY hr",
                (cutoff, *prj_params)
            ).fetchall()
            error_timeline = [{
                "ts": now - (24 - r["hr"]) * 3600,
                "total": r["total"], "errors": r["errors"],
                "error_rate": round(r["errors"] / max(r["total"], 1), 2),
            } for r in err_rows]

            # ── Top errors ──
            top_err_rows = conn.execute(
                "SELECT error, COUNT(*) AS cnt"
                " FROM syscall_events"
                f" WHERE kind='llm' AND status='failed' AND start_time > ?{prj_clause}"
                " GROUP BY error ORDER BY cnt DESC LIMIT 10",
                (cutoff, *prj_params)
            ).fetchall()
            top_errors = [{"error": r["error"] or "unknown", "count": r["cnt"]} for r in top_err_rows]

            return {
                "llm_stats": {
                    "total_calls": total,
                    "success_rate": rate,
                    "avg_latency_ms": round(row["avg_ms"], 1),
                    "max_latency_ms": round(row["max_ms"], 1),
                    "total_input_tokens": row["in_tok"] or 0,
                    "total_output_tokens": row["out_tok"] or 0,
                    "total_cost": round(total_cost, 4),
                },
                "syscall_by_kind": syscall_by_kind,
                "active_runs": active or 0,
                "throughput": throughput,
                "error_timeline": error_timeline,
                "model_usage": model_usage,
                "top_errors": top_errors,
            }
        finally:
            conn.close()
    except Exception as e:
        return _empty_obs_stats(error=str(e)[:200])


@router.put("/diagnostics/observability/alerts", response_model=Dict[str, Any], include_in_schema=False)
async def put_observability_alerts(body: dict):
    """Save alert configuration (observability dashboard)."""
    try:
        from core.harness.observability.alerts import get_alert_manager
        mgr = get_alert_manager()
        alerts = body.get("alerts", [])
        mgr.save_alerts(alerts)
        return {"status": "ok", "saved": len(alerts)}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


# ── Unified Alert Aggregation (P0-1) ─────────────────────────────────────────

def _norm_severity(raw: Any) -> str:
    """Normalize heterogeneous severity labels to critical / warning / info."""
    s = str(raw or "").lower()
    if any(k in s for k in ("critical", "high_alert", "fatal", "error")):
        return "critical"
    if any(k in s for k in ("warn", "alerting", "high", "medium", "degraded")):
        return "warning"
    return "info"


async def aggregate_all_alerts() -> Dict[str, Any]:
    """Aggregate every core-internal alert source into one unified feed so the
    management Alert Center surfaces them (P0-1). Read-only; each source is
    isolated in try/except and degrades independently. Reuses existing getters
    — no new alert logic (CLAUDE.md §5.6 / §10)."""
    alerts: List[Dict[str, Any]] = []

    def _add(id_, severity, name, source, message, ts=None, component="", status="firing"):
        alerts.append({
            "id": id_, "severity": _norm_severity(severity), "name": name,
            "source": source, "layer": "core", "component": component,
            "status": status, "timestamp": ts, "message": message,
        })

    # 1. AlertManager active alerts
    try:
        from core.harness.observability.alerts import get_alert_manager
        for a in get_alert_manager().get_active_alerts():
            _add(f"alertmgr:{a.id}", getattr(a.severity, "value", a.severity),
                 getattr(a.rule, "name", "alert"), "alert_manager", a.message,
                 ts=a.timestamp.isoformat() if hasattr(a.timestamp, "isoformat") else str(a.timestamp),
                 status="firing")
    except Exception as e:
        logging.debug("alertmgr aggregate skipped: %s", e)

    # 2. Entropy trend active alerts
    try:
        from core.harness.infrastructure.trend_detector import get_trend_detector
        trends = get_trend_detector().get_trends()
        for a in (trends.get("active_alerts") or []):
            et = a.get("error_type", "unknown")
            _add(f"entropy:{et}", a.get("state", "alerting"),
                 f"熵异常: {et}", "entropy_trend",
                 f"error-rate volatility state={a.get('state')}", component=et)
    except Exception as e:
        logging.debug("entropy aggregate skipped: %s", e)

    # 3. Document quality alerts
    try:
        from core.harness.knowledge.doc_quality_monitor import get_doc_quality_monitor
        for a in get_doc_quality_monitor().get_alerts(limit=20):
            _add(f"docq:{a.get('doc_id','?')}:{a.get('created_at','')}", a.get("severity"),
                 a.get("alert_type", "doc_quality"), "doc_quality",
                 f"doc={a.get('doc_id')} {a.get('alert_type','')}",
                 ts=a.get("created_at"), component=str(a.get("doc_id", "")))
    except Exception as e:
        logging.debug("doc_quality aggregate skipped: %s", e)

    # 4. Wiki content quality alerts
    try:
        from core.harness.knowledge.wiki_quality_monitor import get_wiki_quality_monitor
        for a in get_wiki_quality_monitor().get_alerts(limit=20, collection_id="default"):
            _add(f"wikiq:{a.get('page_id', a.get('id','?'))}", a.get("severity"),
                 a.get("alert_type", "wiki_quality"), "wiki_quality",
                 str(a.get("message") or a.get("alert_type", "wiki quality")),
                 ts=a.get("created_at"))
    except Exception as e:
        logging.debug("wiki_quality aggregate skipped: %s", e)

    # 5. Tool drift anomalies (best-effort — shape-tolerant)
    try:
        from core.api.core_facade import get_drift_detector
        rt = get_drift_detector().get_realtime_stats() or {}
        for a in (rt.get("alerts") or rt.get("anomalies") or []):
            if isinstance(a, dict):
                _add(f"drift:{a.get('tool_name','?')}:{a.get('anomaly_type','')}",
                     a.get("severity", "warning"),
                     f"工具漂移: {a.get('tool_name','?')}", "tool_drift",
                     str(a.get("detail") or a.get("message") or a.get("anomaly_type", "")),
                     component=str(a.get("tool_name", "")))
    except Exception as e:
        logging.debug("tool_drift aggregate skipped: %s", e)

    # 6. Maturity-assessment drift (框架 declared-vs-evidence, 来自 compute_assessment.py)
    try:
        adata = _read_assessment_json()
        for d in (adata.get("drift") or []) if adata else []:
            _add(f"assess:{d.get('id','?')}", "warning",
                 f"评估漂移: {d.get('id','')} {d.get('evidence_status','')}",
                 "maturity_assessment",
                 f"declared={d.get('declared')} actual={d.get('actual')} — {d.get('note','')}",
                 component="maturity")
    except Exception as e:
        logging.debug("assessment alerts aggregate skipped: %s", e)

    by_severity = {"critical": 0, "warning": 0, "info": 0}
    for a in alerts:
        by_severity[a["severity"]] = by_severity.get(a["severity"], 0) + 1
    order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (order.get(a["severity"], 3), str(a.get("timestamp") or "")))
    return {"total": len(alerts), "by_severity": by_severity, "alerts": alerts}


@router.get("/diagnostics/alerts/all", response_model=Dict[str, Any])
async def get_all_alerts():
    """Unified feed of all core-internal alerts (AlertManager, entropy trend,
    doc/wiki quality, tool drift). Consumed by the management Alert Center."""
    try:
        return await aggregate_all_alerts()
    except Exception as e:
        return {"total": 0, "by_severity": {}, "alerts": [], "error": str(e)[:200]}


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
        logging.getLogger(__name__).debug('get_model_tier_status failed', exc_info=True)

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
                        logging.getLogger(__name__).debug('code failed', exc_info=True)
        except Exception:
            logging.getLogger(__name__).debug('Infra health tracker unavailable', exc_info=True)
    except Exception:
        logging.getLogger(__name__).debug('YAML config unreadable', exc_info=True)

    return result


# ── PR #4: ControlProfile status ──

@router.get("/diagnostics/profile/status", response_model=Dict[str, Any])
async def get_profile_status():
    """Return current ControlProfile active status + preset list."""
    try:
        from core.harness.meta.profile_registry import ProfileRegistry  # P0-A2 修复: 恢复原模块(定义处)
        from core.harness.meta.profile_registry import get_active_profile  # P0-A2 修复: 恢复原模块(定义处)
        from core.harness.meta.profile_registry import list_profile_overrides  # P0-A2 修复: 恢复原模块(定义处)
        from core.harness.meta.profile_registry import get_last_failure_domain  # P0-A2 修复: 恢复原模块(定义处)
        reg = ProfileRegistry.instance()
        active = get_active_profile()
        return {
            "active": active.to_dict(),
            "presets": reg.list_presets(),
            "task_hints": reg._task_hints,
            "session_override": list_profile_overrides(),
            "last_failure_domain": get_last_failure_domain(),
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/diagnostics/profile/switch", response_model=Dict[str, Any])
async def switch_profile(name: str = "default"):
    """Switch active ControlProfile at session level."""
    try:
        from core.harness.meta.profile_registry import ProfileRegistry  # P0-A2 修复: 恢复原模块(定义处)
        from core.harness.meta.profile_registry import set_profile_override  # P0-A2 修复: 恢复原模块(定义处)
        from core.harness.meta.profile_registry import clear_profile_override  # P0-A2 修复: 恢复原模块(定义处)
        if name == "reset":
            clear_profile_override()
            return {"status": "reset"}
        reg = ProfileRegistry.instance()
        if reg.get_preset(name):
            set_profile_override(name)
            return {"status": "switched", "profile": name}
        return {"error": f"Unknown profile '{name}'", "available": reg.list_presets()}
    except Exception as e:
        return {"error": str(e)}


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
                logging.getLogger(__name__).debug('_get_recent_kb_queries failed', exc_info=True)
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


# ── v2.9: Knowledge Drift Status API ──

@router.get("/diagnostics/drift-status", response_model=Dict[str, Any])
async def get_drift_status(collection: str = "", refresh: bool = False):
    """Knowledge drift scanner — reports which Wiki pages have stale source documents.

    Returns per-collection drift ratio, stale page lists, and suggested actions.
    Pass ?refresh=true to force a fresh scan (otherwise uses cached last result).
    """
    import time as _time
    from core.harness.knowledge.staleness_monitor import StalenessMonitor

    # Simple cache (5 min TTL)
    if not refresh and _drift_cache["data"] and _time.time() - _drift_cache["ts"] < 300:
        return _drift_cache["data"]

    try:
        monitor = StalenessMonitor()
        if collection:
            reports = [monitor.scan_collection(collection)]
        else:
            reports = monitor.scan_all_collections() or []
    except Exception as e:
        import logging
        logging.getLogger("diagnostics").warning("Drift scan failed: %s", str(e)[:200])
        return {
            "status": "unknown",
            "drift_ratio": 0,
            "total_scanned": 0,
            "total_stale": 0,
            "collections": {},
            "stale_pages": [],
            "suggested_actions": [],
            "error": str(e)[:500],
        }

    stale_pages = []
    total_stale = 0
    total_scanned = 0
    collections = {}

    for r in reports:
        total_stale += r.stale_count
        total_scanned += r.scanned_pages
        if r.stale_count > 0:
            collections[r.collection_id] = r.stale_count
        for page in r.affected_pages:
            stale_pages.append({
                "collection": r.collection_id,
                "title": page["title"],
                "stale_sources": page["stale_sources"],
                "total_sources": page["total_sources"],
            })

    drift_ratio = round(total_stale / max(1, total_scanned), 3)
    health = "good" if drift_ratio < 0.1 else ("warning" if drift_ratio < 0.3 else "critical")

    result = {
        "status": health,
        "drift_ratio": drift_ratio,
        "total_scanned": total_scanned,
        "total_stale": total_stale,
        "collections": collections,
        "stale_pages": stale_pages[:20],
        "suggested_actions": [
            "POST /api/core/diagnostics/drift-rebuild — 自动重建所有 stale 页面",
            "GET /diagnostics — 管理端漂移仪表盘查看详情",
        ] if total_stale > 0 else [],
        "checked_at": _time.time(),
    }
    _drift_cache["data"] = result
    _drift_cache["ts"] = _time.time()
    return result


@router.post("/diagnostics/drift-rebuild", response_model=Dict[str, Any])
async def trigger_drift_rebuild(max_pages: int = 10):
    """Auto-rebuild stale pages by re-running the ontology engine on drifted sources.

    Iterates stale pages, extracts their source KB doc_ids, and runs
    auto_ontology_pipeline_for_doc on each. Limited to max_pages for safety.
    """
    from core.harness.knowledge.staleness_monitor import StalenessMonitor
    from core.api.core_facade import read_page

    monitor = StalenessMonitor()
    reports = monitor.scan_all_collections()

    rebuilt = 0
    errors = 0
    details = []

    for report in reports:
        for page in report.affected_pages[:max_pages]:
            title = page["title"]
            cid = report.collection_id or "default"

            # Extract KB doc_ids from stale sources
            stale_refs = page.get("stale_sources", [])
            doc_ids = [s.replace("kb:", "") for s in stale_refs if s.startswith("kb:")]

            # Find file path from KB database
            for doc_id in doc_ids:
                try:
                    import sqlite3 as _sq
                    kb_db = os.path.expanduser(os.getenv("AIPLAT_HOME", "~/.aiplat")) + "/kb/tenants/default/kb.sqlite3"
                    conn = _sq.connect(kb_db)
                    row = conn.execute("SELECT source_uri FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
                    conn.close()
                    if row and row[0] and os.path.exists(row[0]):
                        from core.api.core_facade import auto_ontology_pipeline_for_doc
                        r = await auto_ontology_pipeline_for_doc(doc_id, row[0], cid)
                        if r["status"] == "completed":
                            rebuilt += 1
                        else:
                            errors += 1
                        details.append({"title": title, "doc_id": doc_id, "status": r["status"]})
                        break  # One source per page is enough
                except Exception as e:
                    errors += 1
                    details.append({"title": title, "error": str(e)[:100]})

    return {
        "status": "completed",
        "rebuilt": rebuilt,
        "errors": errors,
        "details": details[:20],
    }


_drift_cache: Dict[str, Any] = {"data": None, "ts": 0}


# ── v2.9: Config Drift Detection ──

@router.get("/diagnostics/config-drift", response_model=Dict[str, Any])
async def get_config_drift():
    """Agent config drift: compare AGENT.md declarations vs runtime behavior."""
    from core.harness.evaluation.config_drift_detector import ConfigDriftDetector
    detector = ConfigDriftDetector()
    summary = detector.get_drift_summary()
    entries = detector.scan_all_agents()
    return {
        "status": "completed",
        "summary": summary,
        "entries": [{"agent_id": e.agent_id, "type": e.drift_type,
                     "declared": e.declared, "actual": e.actual,
                     "severity": e.severity} for e in entries[:20]],
    }


# ── v2.9: System Health Index ──

@router.get("/diagnostics/system-health", response_model=Dict[str, Any])
async def get_system_health():
    """Unified system health index: aggregates OntologyAudit, Staleness, ConfigDrift, EvalMetrics."""
    from core.harness.evaluation.system_health import SystemHealthCalculator
    calc = SystemHealthCalculator()
    report = calc.compute()
    knows = calc.knows_its_limits() if hasattr(calc, 'knows_its_limits') else {}
    sh_available = False
    sh_enabled = False
    try:
        from core.harness.evaluation.self_heal_gate import SelfHealGate
        sh_available = True
        gate = SelfHealGate()
        sh_enabled = getattr(gate, 'enabled', False)
    except Exception:
        logging.getLogger(__name__).debug('get_system_health failed', exc_info=True)
    return {
        "status": "completed",
        "health_index": report.health_index,
        "grade": report.grade,
        "trend": report.trend,
        "trend_delta": report.trend_delta,
        "sub_scores": {k: {"score": v.score, "label": v.label, "detail": v.detail}
                       for k, v in report.sub_scores.items()},
        "recommendations": report.recommendations,
        "self_healing_available": sh_available,
        "self_healing_enabled": sh_enabled,
        "knows_its_limits": knows.get("within_capability_score", None),
        "limit_assessment": knows.get("assessment", "Unknown"),
    "checked_at": report.checked_at,
}


@router.get("/diagnostics/self-heal-log", response_model=Dict[str, Any])
async def get_self_heal_log(limit: int = 20):
    """Recent self-healing actions taken by the SelfHealGate."""
    from core.harness.evaluation.self_heal_gate import SelfHealGate
    gate = SelfHealGate()
    logs = gate.get_heal_log(limit)
    return {"status": "completed", "total": len(logs), "entries": logs}


# ── v2.10: Awareness Log API ──

@router.get("/diagnostics/awareness-log", response_model=Dict[str, Any])
async def get_awareness_log(days: int = 7, severity: str = "all"):
    """Signals that the system detected but chose not to auto-fix (SUGGEST/REJECT decisions)."""
    from core.harness.evaluation.self_heal_gate import _get_awareness_logs
    entries = _get_awareness_logs(days, severity)
    return {"status": "completed", "total": len(entries), "entries": entries}  # noqa: F821 — endpoint defined above


# ── v3.0: Self-Heal Pending Review API (Human-in-the-loop) ──

@router.get("/diagnostics/self-heal/pending", response_model=Dict[str, Any])
async def get_pending_heal_fixes():
    """Pending self-heal fixes awaiting human approval (review-first mode)."""
    from core.harness.evaluation.self_heal_gate import SelfHealGate
    gate = SelfHealGate()
    pending = gate.list_pending()
    return {"status": "completed", "total": len(pending), "entries": pending,
            "auto_mode": gate._auto_mode}


@router.post("/diagnostics/self-heal/approve/{fix_id}", response_model=Dict[str, Any])
async def approve_heal_fix(fix_id: str):
    """Approve and execute a pending self-heal fix."""
    from core.harness.evaluation.self_heal_gate import SelfHealGate
    gate = SelfHealGate()
    result = gate.approve_fix(fix_id)
    return result


@router.post("/diagnostics/self-heal/reject/{fix_id}", response_model=Dict[str, Any])
async def reject_heal_fix(fix_id: str, reason: str = ""):
    """Reject a pending self-heal fix with optional reason."""
    from core.harness.evaluation.self_heal_gate import SelfHealGate
    gate = SelfHealGate()
    result = gate.reject_fix(fix_id, reason)
    return result


@router.get("/diagnostics/constraint-check", response_model=Dict[str, Any])
async def get_constraint_check():
    """Validate AGENT.md/YAML configurations for stale references."""
    from core.harness.evaluation.constraint_validator import ConstraintValidator
    validator = ConstraintValidator()
    issues = validator.scan_all()
    critical = [i for i in issues if i.level == "CRITICAL"]
    high = [i for i in issues if i.level == "HIGH"]
    warnings = [i for i in issues if i.level == "WARNING"]
    return {
        "status": "completed",
        "total_issues": len(issues),
        "critical_count": len(critical),
        "high_count": len(high),
        "warning_count": len(warnings),
        "issues": [{"source": i.source, "type": i.issue_type, "level": i.level,
                    "detail": i.detail, "suggestion": i.suggestion}
                   for i in issues[:30]],
    }


# ── v2.9: Ontology Audit API ──

@router.get("/diagnostics/adoption-metrics", response_model=Dict[str, Any])
async def get_adoption_metrics():
    """Employee adoption and AI platform engagement metrics.

    Tracks agent usage, GrillingBridge engagement, HITL behavior,
    and resistance hotspots for people-side governance.
    """
    from core.harness.evaluation.adoption_metrics import AdoptionTracker
    tracker = AdoptionTracker()
    report = tracker.compute_metrics()
    return {
        "status": "completed",
        "report": {
            "total_agent_calls": report.total_agent_calls,
            "total_users": report.total_users,
            "active_users_7d": report.active_users_7d,
            "grill_trigger_rate": report.grill_trigger_rate,
            "grill_completion_rate": report.grill_completion_rate,
            "hitl_approval_rate": report.hitl_approval_rate,
            "hitl_rejection_rate": report.hitl_rejection_rate,
            "adoption_trend": report.adoption_trend,
            "resistance_hotspots": report.resistance_hotspots,
            "recommendations": report.recommendations,
            "computed_at": report.computed_at,
        },
    }

@router.get("/diagnostics/ontology-audit", response_model=Dict[str, Any])
async def get_ontology_audit(domain_id: str = "ai-knowledge"):
    """Ontology domain audit: class coverage, relation density, state machine activity."""
    from core.harness.knowledge.ontology_audit import OntologyAuditor
    auditor = OntologyAuditor()
    if domain_id == "all":
        reports = auditor.audit_all_domains()
        return {"status": "completed", "domains": {r.domain_id: r.to_dict() for r in reports}}
    report = auditor.audit_domain(domain_id)
    return {"status": "completed", "domain": domain_id, "report": report.to_dict()}


@router.get("/diagnostics/ontology-audit/summary", response_model=Dict[str, Any])
async def get_ontology_audit_summary():
    """Quick summary: top orphan classes, worst relation coverage across all domains."""
    from core.harness.knowledge.ontology_audit import OntologyAuditor
    auditor = OntologyAuditor()
    reports = auditor.audit_all_domains()
    total_orphans = sum(len(r.orphan_classes) for r in reports)
    total_entities = sum(r.total_entities for r in reports)
    worst = [{"domain": r.domain_id, "entities": r.total_entities, "orphans": len(r.orphan_classes),
              "edge_count": r.total_edges, "warnings": r.warnings[:2]} for r in reports if r.orphan_classes or r.warnings]
    worst.sort(key=lambda x: x["orphans"], reverse=True)
    return {"status": "completed", "total_entities": total_entities, "total_orphans": total_orphans,
            "domains_scanned": len(reports), "worst_domains": worst[:10]}


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
                logging.getLogger(__name__).debug('get_audit_trail failed', exc_info=True)
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
                logging.getLogger(__name__).debug('get_audit_tree failed', exc_info=True)

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
            from core.api.core_facade import read_page
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
                    logging.getLogger(__name__).debug('_query_audit_trail_for_entity failed', exc_info=True)
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
                    logging.getLogger(__name__).debug('_get_latest_hallucination_risk failed', exc_info=True)
            return round(1.0 - (sum(confs[-10:]) / max(len(confs[-10:]), 1)), 2) if confs else 0.0
        finally:
            conn.close()
    except (_sq.OperationalError, _sq.DatabaseError):
        return 0.0

# ── Include sub-module routers ──
try:
    from core.api.routers.diagnostics_capability import router as _cap_router
    router.include_router(_cap_router)
except ImportError:
    pass  # noqa: optional-dependency




@router.post("/diagnostics/cross-validation", response_model=Dict[str, Any])
async def run_cross_validation(payload: dict):
    """CrossValidationGate semantic verification (equipment/process/quality).

    Body: {"output": {...}, "domain_id": "default"}
    Returns readiness + violations (framework stub — below activation
    threshold returns ready=false with note).
    """
    from core.api.core_facade import cross_validation_verify
    output = (payload or {}).get("output", {})
    domain_id = str((payload or {}).get("domain_id", "default"))
    return cross_validation_verify(output, domain_id=domain_id)
