"""
RunState (Restatement Artifact)

Purpose:
- Provide a structured, versioned, human-editable "current progress + next step" artifact.
- Support long-running tasks by restating key dynamic info near the end of the prompt.
"""

from __future__ import annotations

import time
import hashlib
from typing import Any, Dict, List, Optional


def default_run_state(*, run_id: str, task: str = "") -> Dict[str, Any]:
    return {
        "schema_version": "0.1",
        "run_id": str(run_id),
        "task": str(task or ""),
        "todo": [],  # [{id,title,status}]
        "open_issues": [],  # [{severity,title,suggested_fix,evidence?}]
        "next_step": "",
        "locked": False,
        "updated_at": time.time(),
        "updated_by": {"source": "auto"},
    }


def normalize_run_state(obj: Any, *, run_id: str) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        return default_run_state(run_id=run_id)
    out = default_run_state(run_id=run_id)
    for k in ["schema_version", "task", "todo", "open_issues", "next_step", "locked", "updated_at", "updated_by"]:
        if k in obj:
            out[k] = obj[k]
    out["run_id"] = str(run_id)
    out["locked"] = bool(out.get("locked"))
    if not isinstance(out.get("todo"), list):
        out["todo"] = []
    if not isinstance(out.get("open_issues"), list):
        out["open_issues"] = []
    if not isinstance(out.get("updated_by"), dict):
        out["updated_by"] = {"source": "unknown"}
    try:
        out["updated_at"] = float(out.get("updated_at") or time.time())
    except Exception:
        out["updated_at"] = time.time()
    out["next_step"] = str(out.get("next_step") or "")
    out["task"] = str(out.get("task") or "")
    return out


def _stable_id(prefix: str, title: str) -> str:
    s = (prefix + ":" + (title or "")).strip().encode("utf-8", errors="ignore")
    h = hashlib.sha1(s).hexdigest()[:10]
    return f"{prefix}-{h}"


def _severity_rank(sev: str) -> int:
    s = (sev or "").strip().upper()
    if s == "P0":
        return 0
    if s == "P1":
        return 1
    if s == "P2":
        return 2
    return 9


def _todo_status_rank(st: str) -> int:
    s = (st or "").strip().lower()
    if s in {"pending", "todo", "open"}:
        return 0
    if s in {"in_progress", "doing"}:
        return 1
    if s in {"done", "completed"}:
        return 9
    return 5


def pick_next_todo(todo: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Pick the highest-priority unfinished todo.
    """
    items = [t for t in (todo or []) if isinstance(t, dict)]
    unfinished = [t for t in items if str(t.get("status") or "").lower() not in {"done", "completed"}]
    if not unfinished:
        return None
    unfinished.sort(
        key=lambda x: (
            _severity_rank(str(x.get("priority") or "")),
            _todo_status_rank(str(x.get("status") or "")),
            str(x.get("title") or ""),
        )
    )
    return unfinished[0]


def auto_next_step_from_todo(cur: Dict[str, Any]) -> Dict[str, Any]:
    """
    If next_step is empty, fill it from top pending todo.
    """
    rs = normalize_run_state(cur, run_id=str(cur.get("run_id") or ""))
    if rs.get("locked") is True:
        return rs
    todo = rs.get("todo") if isinstance(rs.get("todo"), list) else []
    top = pick_next_todo(todo) if isinstance(todo, list) else None
    if top and not str(rs.get("next_step") or "").strip():
        rs["next_step"] = f"执行 todo: {str(top.get('title') or '')}"
        rs["updated_at"] = time.time()
        rs["updated_by"] = {"source": "auto_next_step"}
    return rs


def set_todo_status(cur: Dict[str, Any], *, todo_id: str, status: str, source: str = "auto") -> Dict[str, Any]:
    rs = normalize_run_state(cur, run_id=str(cur.get("run_id") or ""))
    if rs.get("locked") is True:
        return rs
    tid = str(todo_id or "").strip()
    if not tid:
        return rs
    todo = rs.get("todo") if isinstance(rs.get("todo"), list) else []
    out = []
    changed = False
    for t in todo:
        if not isinstance(t, dict):
            continue
        if str(t.get("id") or "") == tid:
            t2 = dict(t)
            t2["status"] = str(status or "completed")
            out.append(t2)
            changed = True
        else:
            out.append(t)
    if changed:
        rs["todo"] = out
        # if we completed the todo driving next_step, clear next_step so auto restatement can pick next one
        if str(rs.get("next_step") or "").strip().endswith(tid):
            rs["next_step"] = ""
        rs["updated_at"] = time.time()
        rs["updated_by"] = {"source": source, "todo_id": tid, "status": status}
        rs = auto_next_step_from_todo(rs)
    return rs


def merge_from_evaluation(
    current: Dict[str, Any],
    *,
    evaluation_report: Dict[str, Any],
    source: str = "evaluator",
) -> Dict[str, Any]:
    """
    Merge evaluator issues into run_state.open_issues and set next_step.
    Does NOT mutate input.
    """
    cur = normalize_run_state(current, run_id=str(current.get("run_id") or ""))
    if cur.get("locked") is True:
        return cur

    rep = evaluation_report if isinstance(evaluation_report, dict) else {}
    issues = rep.get("issues") if isinstance(rep.get("issues"), list) else []
    open_issues: List[Dict[str, Any]] = []
    for it in issues[:50]:
        if not isinstance(it, dict):
            continue
        open_issues.append(
            {
                "severity": str(it.get("severity") or "P1"),
                "title": str(it.get("title") or ""),
                "suggested_fix": str(it.get("suggested_fix") or ""),
                "evidence": it.get("evidence") if isinstance(it.get("evidence"), dict) else {},
            }
        )
    cur["open_issues"] = open_issues

    # ---- Generate TODO (keep completed items if stable id matches) ----
    existing_todo = cur.get("todo") if isinstance(cur.get("todo"), list) else []
    completed_map: Dict[str, Dict[str, Any]] = {}
    for t in existing_todo:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "").strip()
        if not tid:
            continue
        if str(t.get("status") or "").lower() in {"done", "completed"}:
            completed_map[tid] = t

    todo: List[Dict[str, Any]] = []
    # from issues
    for it in open_issues[:50]:
        title = str(it.get("title") or "").strip()
        if not title:
            continue
        tid = _stable_id("issue", title)
        if tid in completed_map:
            todo.append(completed_map[tid])
            continue
        todo.append(
            {
                "id": tid,
                "title": title,
                "status": "pending",
                "priority": str(it.get("severity") or "P1").upper(),
                "suggested_fix": str(it.get("suggested_fix") or ""),
            }
        )

    # from next_actions_for_generator
    na = rep.get("next_actions_for_generator")
    if isinstance(na, list):
        for x in na[:30]:
            title = str(x or "").strip()
            if not title:
                continue
            tid = _stable_id("next", title)
            if tid in completed_map:
                todo.append(completed_map[tid])
                continue
            todo.append({"id": tid, "title": title, "status": "pending", "priority": "P2"})

    # de-dup and sort
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for t in todo:
        tid = str(t.get("id") or "")
        if not tid or tid in seen:
            continue
        seen.add(tid)
        uniq.append(t)
    uniq.sort(key=lambda x: (_severity_rank(str(x.get("priority") or "")), str(x.get("title") or "")))
    cur["todo"] = uniq

    # Build next_step (prioritize P0/P1)
    p0 = [i for i in open_issues if str(i.get("severity")).upper() == "P0"]
    p1 = [i for i in open_issues if str(i.get("severity")).upper() == "P1"]
    if p0:
        cur["next_step"] = "优先修复所有 P0 问题（评估未通过）：\n- " + "\n- ".join([str(i.get("title") or "") for i in p0[:8]])
    elif p1:
        cur["next_step"] = "修复 P1 问题并重新评估：\n- " + "\n- ".join([str(i.get("title") or "") for i in p1[:8]])
    else:
        cur["next_step"] = "根据评估反馈进行小幅优化，并重新运行一次自动评估确认通过。"

    cur["updated_at"] = time.time()
    cur["updated_by"] = {"source": source}
    # If todo exists, and next_step is empty, fill from todo top item (Restatement)
    cur = auto_next_step_from_todo(cur)
    return cur


def restate_next_step(
    current: Dict[str, Any],
    *,
    step_count: int,
    last_error: Optional[str] = None,
    source: str = "loop",
) -> Dict[str, Any]:
    """
    Lightweight periodic restatement (no LLM):
    - If approval/policy denied, steer next_step accordingly.
    - Otherwise keep existing next_step.
    """
    cur = normalize_run_state(current, run_id=str(current.get("run_id") or ""))
    if cur.get("locked") is True:
        return cur
    err = str(last_error or "").strip().lower()
    if err == "approval_required":
        cur["next_step"] = "等待审批通过后恢复执行（resume），或调整方案使用更安全的工具/参数。"
    elif err == "policy_denied":
        cur["next_step"] = "策略拒绝：缩小影响范围/改用只读工具，或发起审批后再继续。"
    else:
        if not str(cur.get("next_step") or "").strip():
            cur = auto_next_step_from_todo(cur)
            if not str(cur.get("next_step") or "").strip():
                cur["next_step"] = "继续执行下一步：优先完成核心路径，再补齐边界情况与测试。"
    cur["updated_at"] = time.time()
    cur["updated_by"] = {"source": source, "step_count": int(step_count)}
    return cur


def format_run_state_for_prompt(run_state: Dict[str, Any]) -> str:
    """
    A compact prompt block placed at the END of the prompt (high attention region).
    """
    rs = run_state if isinstance(run_state, dict) else {}
    locked = bool(rs.get("locked"))
    task = str(rs.get("task") or "")
    next_step = str(rs.get("next_step") or "")
    issues = rs.get("open_issues") if isinstance(rs.get("open_issues"), list) else []
    p0 = [i for i in issues if isinstance(i, dict) and str(i.get("severity") or "").upper() == "P0"]
    todo = rs.get("todo") if isinstance(rs.get("todo"), list) else []
    cur_todo = pick_next_todo(todo) if isinstance(todo, list) else None
    lines = [
        "=== RUN STATE (Restatement, must follow) ===",
        f"locked: {locked}",
        f"task: {task[:800]}",
    ]
    if p0:
        lines.append("P0 issues:")
        for it in p0[:8]:
            lines.append(f"- {str(it.get('title') or '')[:200]}")
    if cur_todo:
        lines.append(f"current_todo_id: {str(cur_todo.get('id') or '')}")
        lines.append(f"current_todo_title: {str(cur_todo.get('title') or '')[:200]}")
    lines.append(f"next_step: {next_step[:1200]}")
    lines.append("IMPORTANT: 当你完成 current_todo 时，请在你的下一条回复末尾单独输出一行：")
    lines.append("TODO_DONE:<current_todo_id>")
    lines.append("=== END RUN STATE ===")
    return "\n".join(lines)
