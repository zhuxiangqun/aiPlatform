"""Unique Core path: generate / inspect Agent eval artifacts.

Consumers (HTTP / 上架钩子 / Skill handler / 诊断页) MUST call these functions.
Do not reimplement LLM scoring-dimension writes in routers.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_SKILL_EVAL_GEN = "eval_code_generator"


def _plat_home() -> Path:
    env = (os.environ.get("AIPLAT_HOME") or "").strip()
    if env:
        return Path(env).expanduser()
    return Path(os.path.expanduser("~/.aiplat"))


def _agents_root() -> Path:
    return _plat_home() / "agents"


def _eval_dir(agent_id: str) -> Path:
    return _plat_home() / "eval" / str(agent_id)


def _exec_db_path() -> str:
    return str(_plat_home() / "aiplat_executions.sqlite3")


def _split_agent_md(raw: str) -> Tuple[Dict[str, Any], str]:
    fm: Dict[str, Any] = {}
    body = raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml

                loaded = yaml.safe_load(parts[1]) or {}
                if isinstance(loaded, dict):
                    fm = loaded
            except Exception:
                fm = {}
            body = parts[2]
    return fm, body


def _read_agent_md(agent_id: str) -> Optional[Dict[str, Any]]:
    path = _agents_root() / str(agent_id) / "AGENT.md"
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8")
    fm, body = _split_agent_md(raw)
    return {"path": str(path), "raw": raw, "frontmatter": fm, "body": body}


def _bound_skills(fm: Dict[str, Any]) -> List[str]:
    skills: List[str] = []
    for key in ("required_skills", "skills"):
        raw = fm.get(key) or []
        if isinstance(raw, list):
            skills.extend(str(x).strip() for x in raw if str(x).strip())
    return skills


def _has_eval_files(agent_id: str) -> bool:
    d = _eval_dir(agent_id)
    return (d / "eval_metric.py").is_file() and (d / "eval_runner.py").is_file()


def _scoring_list(fm: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = fm.get("scoring_dimensions")
    if not isinstance(raw, list):
        return []
    return [d for d in raw if isinstance(d, dict) and str(d.get("name") or "").strip()]


def _count_agent_traces(agent_id: str, limit: int = 50) -> Tuple[int, List[str]]:
    """Count recent executions for this agent; return (n, status samples)."""
    db = _exec_db_path()
    if not os.path.isfile(db):
        return 0, []
    try:
        conn = sqlite3.connect(db, timeout=3)
        conn.execute("PRAGMA busy_timeout=3000")
        try:
            rows = conn.execute(
                "SELECT status FROM agent_executions WHERE agent_id=? "
                "ORDER BY COALESCE(start_time, created_at) DESC LIMIT ?",
                (str(agent_id), int(limit)),
            ).fetchall()
            statuses = [str(r[0] or "") for r in rows]
            return len(rows), statuses
        finally:
            conn.close()
    except Exception:
        logger.debug("count traces failed agent_id=%s", agent_id, exc_info=True)
        return 0, []


def _read_last_action(agent_id: str) -> Dict[str, Any]:
    path = _eval_dir(agent_id) / "last_action.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_last_action(agent_id: str, payload: Dict[str, Any]) -> None:
    d = _eval_dir(agent_id)
    try:
        d.mkdir(parents=True, exist_ok=True)
        slim = {
            "agent_id": agent_id,
            "action": payload.get("action"),
            "message": payload.get("message"),
            "at": payload.get("generated_at") or datetime.now(timezone.utc).isoformat(),
            "trace_count": payload.get("trace_count"),
            "has_eval_files": payload.get("has_eval_files"),
            "wrote_scoring_dimensions": payload.get("wrote_scoring_dimensions"),
        }
        (d / "last_action.json").write_text(
            json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        logger.debug("write last_action failed agent_id=%s", agent_id, exc_info=True)


def inspect_agent_eval(agent_id: str) -> Dict[str, Any]:
    """Read-only snapshot: dimensions, files, traces. Never writes."""
    aid = str(agent_id or "").strip()
    info = _read_agent_md(aid) if aid else None
    if not aid:
        return {"agent_id": "", "found": False, "action": "skip", "message": "missing agent_id"}
    if not info:
        return {"agent_id": aid, "found": False, "action": "skip", "message": f"Agent {aid} not found"}
    fm = info.get("frontmatter") or {}
    dims = _scoring_list(fm if isinstance(fm, dict) else {})
    n_traces, statuses = _count_agent_traces(aid)
    skills = _bound_skills(fm if isinstance(fm, dict) else {})
    is_generator = _SKILL_EVAL_GEN in skills
    files_ok = _has_eval_files(aid)
    last = _read_last_action(aid)
    report: Dict[str, Any] = {}
    report_path = _eval_dir(aid) / "last_report.json"
    if report_path.is_file():
        try:
            loaded = json.loads(report_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                report = loaded
        except Exception:
            report = {}
    return {
        "agent_id": aid,
        "found": True,
        "is_eval_generator": is_generator,
        "has_scoring": bool(dims),
        "scoring_dimensions": dims,
        "eval_dir": str(_eval_dir(aid)),
        "has_eval_files": files_ok,
        "trace_count": n_traces,
        "recent_status": statuses[:8],
        "complete": bool(dims) and files_ok,
        "last_action": last or None,
        "last_report": report or None,
    }


def _heuristic_dimensions(fm: Dict[str, Any]) -> List[Dict[str, Any]]:
    desc = str(fm.get("description") or fm.get("display_name") or "")[:80]
    return [
        {
            "name": "task_completion",
            "weight": 0.4,
            "threshold": 7.0,
            "description": f"任务是否按 AGENT.md 完成（{desc}）",
        },
        {
            "name": "output_substance",
            "weight": 0.3,
            "threshold": 6.0,
            "description": "产出是否有可验收正文（非空、非占位）",
        },
        {
            "name": "error_recovery",
            "weight": 0.3,
            "threshold": 6.0,
            "description": "失败/超时是否可诊断，而非静默成功",
        },
    ]


def _normalize_dims(dims: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for d in dims:
        if not isinstance(d, dict):
            continue
        name = str(d.get("name") or "").strip()
        if not name:
            continue
        w = d.get("weight", 0.2)
        try:
            w = float(w)
        except (TypeError, ValueError):
            w = 0.2
        if w > 1.5:
            w = w / 100.0
        th = d.get("threshold", 6.0)
        try:
            th = float(th)
        except (TypeError, ValueError):
            th = 6.0
        out.append(
            {
                "name": name[:64],
                "weight": round(w, 4),
                "threshold": th,
                "description": str(d.get("description") or d.get("criteria") or "")[:240],
            }
        )
        if len(out) >= 5:
            break
    total = sum(x["weight"] for x in out) or 1.0
    if out and abs(total - 1.0) > 0.05:
        for x in out:
            x["weight"] = round(x["weight"] / total, 4)
    return out


async def _llm_dimensions(fm: Dict[str, Any], history: str) -> List[Dict[str, Any]]:
    from core.api.core_facade import (
        _async_prompt_resolve,
        best_model_for_purpose,
        create_selected_adapter,
        sys_llm_generate,
    )

    name = str(fm.get("display_name") or fm.get("name") or "")
    prompt = await _async_prompt_resolve(
        "eval-metrics-design",
        name=name,
        agent_type=str(fm.get("agent_type") or "conversational"),
        description=str(fm.get("description") or "")[:300],
        history=(history or "(none)")[:1000],
    )
    model_name = best_model_for_purpose("eval_code") or best_model_for_purpose("chat")
    model = create_selected_adapter(model_name=model_name)
    messages = [
        {"role": "system", "content": await _async_prompt_resolve("eval-metrics-system")},
        {"role": "user", "content": prompt},
    ]
    resp = await sys_llm_generate(
        model,
        messages,
        trace_context={"skip_claude_md": True, "source": "agent_eval"},
    )
    llm_text = getattr(resp, "content", None) or str(resp)
    clean = str(llm_text).strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```\w*\n?", "", clean)
        clean = re.sub(r"\n?```$", "", clean)
    match = re.search(r"\[[\s\S]*\]", clean)
    if not match:
        return []
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, list):
        return []
    return _normalize_dims(parsed)


def _write_scoring(info: Dict[str, Any], dims: List[Dict[str, Any]]) -> None:
    import yaml

    path = Path(info["path"])
    fm = dict(info.get("frontmatter") or {})
    fm["scoring_dimensions"] = dims
    body = info.get("body") or ""
    fm_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip("\n")
    path.write_text(f"---\n{fm_text}\n---{body}", encoding="utf-8")


def _metric_source(agent_id: str, dims: List[Dict[str, Any]]) -> str:
    payload = json.dumps(dims, ensure_ascii=False, indent=2)
    return (
        '"""Auto-generated by generate_agent_eval (eval_code_generator).\n'
        f"Target Agent: {agent_id}\n"
        '"""\n'
        "from __future__ import annotations\n\n"
        "from typing import Any, Dict, List\n\n"
        f"DIMENSIONS: List[Dict[str, Any]] = {payload}\n\n"
        "def score_runs(runs: List[Dict[str, Any]]) -> Dict[str, Any]:\n"
        "    total = len(runs)\n"
        "    completed = sum(1 for r in runs if str(r.get('status') or '').lower() in ('completed', 'ok', 'success'))\n"
        "    failed = sum(1 for r in runs if str(r.get('status') or '').lower() in ('failed', 'error', 'timeout'))\n"
        "    rate = (completed / total * 10.0) if total else 0.0\n"
        "    scores = {}\n"
        "    for d in DIMENSIONS:\n"
        "        name = str(d.get('name') or '')\n"
        "        if name == 'error_recovery':\n"
        "            scores[name] = 10.0 if failed == 0 else max(0.0, 10.0 - failed)\n"
        "        elif name == 'output_substance':\n"
        "            nonempty = sum(1 for r in runs if str(r.get('output') or r.get('output_json') or '').strip())\n"
        "            scores[name] = (nonempty / total * 10.0) if total else 0.0\n"
        "        else:\n"
        "            scores[name] = round(rate, 2)\n"
        "    weights = {str(d.get('name')): float(d.get('weight') or 0) for d in DIMENSIONS}\n"
        "    composite = sum(scores.get(k, 0) * w for k, w in weights.items())\n"
        "    return {\n"
        "        'total_runs': total,\n"
        "        'completed': completed,\n"
        "        'failed': failed,\n"
        "        'scores': scores,\n"
        "        'composite': round(composite, 2),\n"
        "    }\n"
    )


def _runner_source(agent_id: str) -> str:
    return (
        '"""Auto-generated eval runner. python eval_runner.py --agent_id='
        f"{agent_id}\n"
        '"""\n'
        "from __future__ import annotations\n\n"
        "import argparse\n"
        "import json\n"
        "import os\n"
        "import sqlite3\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
        "from eval_metric import score_runs\n\n"
        "def _db() -> str:\n"
        "    home = os.environ.get('AIPLAT_HOME') or os.path.join(os.path.expanduser('~'), '.aiplat')\n"
        "    return os.path.join(home, 'aiplat_executions.sqlite3')\n\n"
        "def load_runs(agent_id: str, limit: int = 50):\n"
        "    db = _db()\n"
        "    if not os.path.isfile(db):\n"
        "        return []\n"
        "    conn = sqlite3.connect(db, timeout=3)\n"
        "    conn.row_factory = sqlite3.Row\n"
        "    try:\n"
        "        rows = conn.execute(\n"
        "            'SELECT status, output_json FROM agent_executions WHERE agent_id=? '\n"
        "            'ORDER BY COALESCE(start_time, created_at) DESC LIMIT ?',\n"
        "            (agent_id, limit),\n"
        "        ).fetchall()\n"
        "        return [{'status': r['status'], 'output_json': r['output_json']} for r in rows]\n"
        "    finally:\n"
        "        conn.close()\n\n"
        "def main() -> int:\n"
        "    p = argparse.ArgumentParser()\n"
        "    p.add_argument('--agent_id', default="
        f"{json.dumps(agent_id)}"
        ")\n"
        "    p.add_argument('--limit', type=int, default=50)\n"
        "    args = p.parse_args()\n"
        "    runs = load_runs(args.agent_id, args.limit)\n"
        "    report = score_runs(runs)\n"
        "    report['agent_id'] = args.agent_id\n"
        "    out = Path(__file__).with_name('last_report.json')\n"
        "    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')\n"
        "    print(json.dumps(report, ensure_ascii=False, indent=2))\n"
        "    return 0\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )


def _write_eval_files(agent_id: str, dims: List[Dict[str, Any]]) -> Dict[str, str]:
    d = _eval_dir(agent_id)
    d.mkdir(parents=True, exist_ok=True)
    metric = d / "eval_metric.py"
    runner = d / "eval_runner.py"
    metric.write_text(_metric_source(agent_id, dims), encoding="utf-8")
    runner.write_text(_runner_source(agent_id), encoding="utf-8")
    return {"eval_metric.py": str(metric), "eval_runner.py": str(runner)}


def _try_run_eval(agent_id: str) -> Dict[str, Any]:
    import runpy
    import sys

    d = _eval_dir(agent_id)
    runner = d / "eval_runner.py"
    if not runner.is_file():
        return {"ok": False, "error": "missing_runner"}
    prev = list(sys.argv)
    prev_path = list(sys.path)
    try:
        sys.path.insert(0, str(d))
        sys.argv = [str(runner), "--agent_id", str(agent_id)]
        try:
            runpy.run_path(str(runner), run_name="__main__")
            exit_ok = True
            exit_code = 0
        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 0
            exit_ok = exit_code == 0
        report_path = d / "last_report.json"
        report = {}
        if report_path.is_file():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                report = {}
        out: Dict[str, Any] = {
            "ok": bool(exit_ok and report_path.is_file()),
            "exit_code": exit_code,
        }
        if report:
            out["report"] = report
            out["report_path"] = str(report_path)
        elif not out["ok"]:
            out["error"] = "missing_report" if exit_ok else f"exit_{exit_code}"
        return out
    except Exception as e:
        logger.warning("eval_runner failed agent_id=%s: %s", agent_id, e, exc_info=True)
        return {"ok": False, "error": str(e)[:300]}
    finally:
        sys.argv = prev
        sys.path[:] = prev_path


async def generate_agent_eval(
    agent_id: str,
    *,
    force: bool = False,
    max_traces: int = 50,
    run_runner: bool = True,
    use_llm: bool = True,
) -> Dict[str, Any]:
    """Generate scoring_dimensions + eval_metric/eval_runner for one Agent.

    Skip (auditable) when: not found / self-generator / already complete /
    no traces yet. Listing must not fail because of this call.
    """
    snap = inspect_agent_eval(agent_id)
    aid = str(snap.get("agent_id") or agent_id or "").strip()

    def _finish(out: Dict[str, Any]) -> Dict[str, Any]:
        if aid:
            _write_last_action(aid, out)
        return out

    if not snap.get("found"):
        return _finish({**snap, "action": "skip", "message": snap.get("message") or "not found"})
    if snap.get("is_eval_generator"):
        return _finish({
            **snap,
            "action": "skip",
            "message": "bound skill eval_code_generator — 不为评估生成器自身再生成评估代码",
        })
    if snap.get("complete") and not force:
        return _finish({
            **snap,
            "action": "skip",
            "message": f"Already has scoring_dimensions and eval files ({snap.get('trace_count')} traces)",
        })
    n_traces = int(snap.get("trace_count") or 0)
    if n_traces == 0 and not force:
        return _finish({
            **snap,
            "action": "skip",
            "message": "No execution traces yet — run the agent first",
        })

    info = _read_agent_md(aid)
    assert info is not None
    fm = info.get("frontmatter") or {}
    if not isinstance(fm, dict):
        fm = {}
    dims = _scoring_list(fm)
    wrote_dims = False
    if not dims or force:
        history = ",".join(str(s) for s in (snap.get("recent_status") or [])[:15])
        designed: List[Dict[str, Any]] = []
        if use_llm:
            try:
                designed = await _llm_dimensions(fm, history)
            except Exception as e:
                logger.warning("LLM scoring design failed agent_id=%s: %s", aid, e, exc_info=True)
        dims = designed or _heuristic_dimensions(fm)
        _write_scoring(info, dims)
        wrote_dims = True
        info = _read_agent_md(aid) or info

    files = _write_eval_files(aid, dims)
    run_result: Dict[str, Any] = {}
    if run_runner:
        run_result = _try_run_eval(aid)

    return _finish({
        "agent_id": aid,
        "found": True,
        "action": "generated",
        "wrote_scoring_dimensions": wrote_dims,
        "scoring_dimensions": dims,
        "files": files,
        "eval_dir": str(_eval_dir(aid)),
        "has_eval_files": True,
        "trace_count": n_traces,
        "runner": run_result,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "message": (
            f"Generated eval artifacts for {aid} "
            f"({'updated dimensions' if wrote_dims else 'kept dimensions'})"
        ),
    })


def enqueue_listed_agent_eval(agent_id: str) -> None:
    """Fire-and-forget after 上架. Failures are logged, never raise to the caller."""
    import asyncio

    aid = str(agent_id or "").strip()
    if not aid:
        return

    async def _job() -> None:
        try:
            out = await generate_agent_eval(aid)
            logger.info(
                "listed-agent-eval agent_id=%s action=%s msg=%s",
                aid,
                out.get("action"),
                str(out.get("message") or "")[:200],
            )
        except Exception:
            logger.warning("listed-agent-eval failed agent_id=%s", aid, exc_info=True)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_job())
    except RuntimeError:
        logger.debug("enqueue listed eval skipped (no running loop) agent_id=%s", aid)
