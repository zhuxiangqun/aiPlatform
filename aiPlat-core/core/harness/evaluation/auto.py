"""
Auto evaluation (P1 UI convenience).

This is a pragmatic "one-click" evaluator:
- It uses an LLM to review run summary + run_events and produces a JSON evaluation report
- It does NOT require Playwright; it is safe to run in most environments

Later upgrades can add optional URL-driven UI testing (Playwright/MCP) and merge evidence.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


REPORT_SCHEMA_HINT = {
    "pass": False,
    "score": {"functionality": 0, "product_depth": 0, "design_ux": 0, "code_architecture": 0, "overall": 0},
    "issues": [
        {
            "severity": "P0",
            "title": "",
            "repro_steps": [],
            "expected": "",
            "actual": "",
            "evidence": {"run_events": [], "syscalls": []},
            "suggested_fix": "",
        }
    ],
    "positive_notes": [],
    "next_actions_for_generator": [],
}


def build_auto_eval_prompt(
    *,
    run: Dict[str, Any],
    events: List[Dict[str, Any]],
    extra: Optional[Dict[str, Any]] = None,
    browser_evidence: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """
    Returns a chat message list for LLMAdapter.generate().
    """
    extra = extra or {}
    # Keep payload small; the LLM only needs high-signal fields
    run0 = {k: run.get(k) for k in ["run_id", "status", "target_type", "target_id", "trace_id", "output", "error", "created_at", "start_time", "end_time"]}
    ev0 = []
    for e in events[:200]:
        ev0.append({"seq": e.get("seq"), "type": e.get("type"), "created_at": e.get("created_at"), "payload": e.get("payload")})

    content = (
        "你是一个严格的 QA evaluator。你将根据一次系统 run 的执行摘要与事件日志，输出一份结构化评估报告 JSON。\n"
        "要求：\n"
        "1) 只输出 JSON（不要 Markdown，不要解释性文字）。\n"
        "2) 给出 pass(true/false) + score（0-10） + issues（可复现、可操作）。\n"
        "3) 如果信息不足以确认通过，倾向于 fail，并在 issues 中写清楚缺少的证据/下一步如何补齐。\n"
        "4) 尽量引用 run_events 的 seq/type 作为证据。\n"
        "5) 若提供 browser_evidence（页面快照/截图/console/network），需要将其纳入判断，并引用其关键字段作为证据。\n"
        "\n"
        f"JSON schema 示例（仅供字段参考，不要照抄数值）：\n{json.dumps(REPORT_SCHEMA_HINT, ensure_ascii=False)}\n"
        "\n"
        f"Run summary:\n{json.dumps(run0, ensure_ascii=False)}\n"
        f"Run events (truncated):\n{json.dumps(ev0, ensure_ascii=False)}\n"
    )
    if extra:
        content += f"\nExtra context:\n{json.dumps(extra, ensure_ascii=False)}\n"
    if browser_evidence:
        content += f"\nBrowser evidence:\n{json.dumps(browser_evidence, ensure_ascii=False)[:200000]}\n"

    return [
        {"role": "system", "content": "You are a strict software QA evaluator."},
        {"role": "user", "content": content},
    ]


def parse_json_report(text: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Best-effort parse the model output into JSON report.
    """
    raw = str(text or "").strip()
    if not raw:
        return None, "empty_output"
    # Try strict JSON first
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj, "ok"
    except Exception:
        pass
    # Try to extract JSON object from surrounding text
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            obj = json.loads(raw[start : end + 1])
            if isinstance(obj, dict):
                return obj, "ok_extracted"
    except Exception:
        pass
    return None, "invalid_json"


def try_parse_json(text: Any) -> Any:
    """
    Best-effort: parse a JSON string; otherwise return original.
    """
    if not isinstance(text, str):
        return text
    s = text.strip()
    if not s:
        return text
    try:
        return json.loads(s)
    except Exception:
        return text
