"""IDE capture → governed coding handoff (Factory), never auto-start a run.

When an IDE/Cursor turn looks like a coding/delegate request, return a
structured handoff so operators confirm in Factory (sandbox + done_verify +
autoreview defaults). Core must not spawn pipelines from capture hooks.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

# (keywords, route, label)
_RULES: Tuple[Tuple[Tuple[str, ...], str, str], ...] = (
    (
        (
            "写代码",
            "生成代码",
            "实现功能",
            "修 bug",
            "修bug",
            "修复bug",
            "code_generation",
            "delegate coding",
            "委托编码",
            "一键构建",
            "确认并构建",
            "## FILE:",
        ),
        "/app/factory",
        "应用工厂 · 受治理编码（沙箱/验收/审阅）",
    ),
)


def classify_ide_coding_handoff(
    prompt: str = "",
    *,
    result: str = "",
    tools: Optional[Sequence[str]] = None,
    tags: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, str]]:
    """Return handoff if text/tools look like a coding delivery ask."""
    blob = " ".join(
        [
            str(prompt or ""),
            str(result or "")[:400],
            " ".join(str(t) for t in (tools or [])),
            " ".join(str(t) for t in (tags or [])),
        ]
    ).strip()
    if not blob:
        return None
    bl = blob.lower()
    for keys, route, label in _RULES:
        for k in keys:
            if k.lower() in bl or k in blob:
                return {"route": route, "label": label, "matched": k}
    return None


def ide_coding_handoff_payload(
    prompt: str = "",
    *,
    result: str = "",
    tools: Optional[Sequence[str]] = None,
    tags: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Structured payload for ingest/API/CLI (kind + route + label)."""
    info = classify_ide_coding_handoff(
        prompt, result=result, tools=tools, tags=tags
    )
    if not info:
        return None
    return {
        "kind": "ide_governed_coding_handoff",
        "route": info["route"],
        "label": info["label"],
        "matched": info["matched"],
        "hint": (
            "IDE capture does not start a coding run. "
            "Confirm in Factory so sandbox / done_verify / autoreview apply."
        ),
    }
