from __future__ import annotations

from typing import Any, Dict, List

from core.apps.skills.base import BaseSkill
from core.harness.interfaces import SkillConfig, SkillContext, SkillResult


class DemoReadonlySummarizeSkill(BaseSkill):
    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        text = str(params.get("text") or "").strip()
        if not text:
            return SkillResult(success=False, error="text_required")
        try:
            max_bullets = int(params.get("max_bullets") or 6)
        except Exception:
            max_bullets = 6
        max_bullets = max(3, min(max_bullets, 12))

        # Very lightweight summarizer: split lines/sentences and take the first N meaningful ones.
        raw_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not raw_lines:
            raw_lines = [s.strip() for s in text.replace("。", "。\n").replace("！", "！\n").replace("？", "？\n").splitlines() if s.strip()]

        bullets: List[str] = []
        for ln in raw_lines:
            ln = ln.replace("\t", " ").strip()
            if len(ln) < 3:
                continue
            bullets.append(ln[:160])
            if len(bullets) >= max_bullets:
                break

        title = bullets[0][:32] if bullets else (text[:32] if len(text) >= 1 else "摘要")
        short = bullets[0][:80] if bullets else (text[:80] if len(text) >= 1 else "")

        return SkillResult(
            success=True,
            output={
                "title": title,
                "bullets": bullets,
                "short_summary": short,
            },
            metadata={"kind": "demo"},
        )


def build_skill(*args, **kwargs):
    # Note: server.py will call build_skill(discovered) when available.
    cfg = SkillConfig(
        name="demo_readonly_summarize",
        description="对输入文本做结构化摘要（示范）。",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "max_bullets": {"type": "integer"},
            },
            "required": ["text"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "bullets": {"type": "array", "items": {"type": "string"}},
                "short_summary": {"type": "string"},
            },
        },
        metadata={
            "category": "transformation",
            "version": "0.1.0",
            "skill_kind": "executable",
            "permissions": ["read_only"],
            "auto_trigger_allowed": True,
            "requires_approval": False,
        },
    )
    return DemoReadonlySummarizeSkill(cfg)
