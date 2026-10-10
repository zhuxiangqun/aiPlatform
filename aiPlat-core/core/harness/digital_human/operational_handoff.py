"""Operational intent → governed handoff (not free-chat completion).

When the user asks to deploy / approve / start a pipeline / create a factory
project, the digital human must not pretend to execute. It appends an
``[ACTION:handoff:<path>]`` marker so the UI shows a confirm card that routes
into Factory / HITL surfaces.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

# (keywords substring, route, short label for UI card)
_HANDOFF_RULES: Tuple[Tuple[Tuple[str, ...], str, str], ...] = (
    (
        ("部署", "deploy", "上线", "发布到", "deploy-to-app"),
        "/app/factory",
        "应用工厂 · 部署/签收",
    ),
    (
        ("审批", "approve", "驳回", "reject", "待审批", "HITL"),
        "/governance",
        "治理 · 审批确认",
    ),
    (
        (
            "启动流水线",
            "跑流水线",
            "开始构建",
            "确认并构建",
            "pipeline.start",
            "创建项目",
            "应用工厂",
            "一键构建",
        ),
        "/app/factory",
        "应用工厂 · 确认并构建",
    ),
    (
        ("取消运行", "cancel run", "停止 pipeline", "中止运行"),
        "/core/runs",
        "执行记录 · 取消运行",
    ),
)


def classify_operational_handoff(question: str) -> Optional[Dict[str, str]]:
    """Return handoff dict if question is operational; else None."""
    q = (question or "").strip()
    if not q:
        return None
    ql = q.lower()
    for keys, route, label in _HANDOFF_RULES:
        for k in keys:
            if k.lower() in ql or k in q:
                return {"route": route, "label": label, "matched": k}
    return None


def handoff_card_payload(question: str) -> Optional[Dict[str, Any]]:
    """Structured payload for APIs/UI (route + label)."""
    info = classify_operational_handoff(question)
    if not info:
        return None
    return {
        "kind": "operational_handoff",
        "route": info["route"],
        "label": info["label"],
        "matched": info["matched"],
    }


def append_handoff_action(answer: str, question: str) -> str:
    """Ensure operational Q&A ends with a handoff ACTION (idempotent)."""
    text = answer or ""
    if re.search(r"\[ACTION:handoff:", text):
        return text
    info = handoff_card_payload(question)
    if not info:
        return text
    route = info["route"]
    label = info["label"]
    # Prefer handoff over silent navigate for the same path
    text = re.sub(r"\s*\[ACTION:navigate:[^\]]+\]\s*", "\n", text).rstrip()
    suffix = (
        f"\n\n下一步请到「{label}」由你确认后再执行（我不会代点部署/审批/启动）。"
        f"\n[ACTION:handoff:{route}]"
    )
    return text + suffix
