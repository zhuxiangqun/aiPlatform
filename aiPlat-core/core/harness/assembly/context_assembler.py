"""
ContextAssembler (Phase 9 — production implementation).

Builds PromptContext with token budgeting, compaction, and source attribution.
Replaces the Phase 4 placeholder.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BudgetSpec:
    token_budget: int = 100_000
    compact_threshold: float = 0.90
    max_steps: int = 20
    timeout_ms: int = 120_000


@dataclass
class ContextSource:
    key: str
    origin: str = ""          # "memory", "artifact", "tool", "skill", "system"
    token_estimate: int = 0
    priority: str = "medium"  # "high" | "medium" | "low"


@dataclass
class PromptContext:
    messages: List[Dict[str, Any]] = field(default_factory=list)
    system_instructions: str = ""
    tool_schemas: List[Dict[str, Any]] = field(default_factory=list)
    skill_schemas: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    budgets: BudgetSpec = field(default_factory=BudgetSpec)
    prompt_template: str = ""
    prompt_version: str = ""
    sources: List[ContextSource] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def estimated_tokens(self) -> int:
        total_chars = 0
        for m in self.messages:
            c = str(m.get("content", ""))
            total_chars += len(c)
        total_chars += len(self.system_instructions)
        for t in self.tool_schemas:
            total_chars += len(json.dumps(t, ensure_ascii=False))
        for s in self.skill_schemas:
            total_chars += len(json.dumps(s, ensure_ascii=False))
        for v in self.artifacts.values():
            total_chars += len(str(v))
        return int(total_chars / 4) + 1

    def is_over_budget(self) -> bool:
        return self.estimated_tokens() > self.budgets.token_budget

    def compact_needed(self) -> bool:
        return self.estimated_tokens() > int(self.budgets.token_budget * self.budgets.compact_threshold)


@dataclass
class ContextAssemblyResult:
    context: PromptContext = field(default_factory=PromptContext)
    metadata: Dict[str, Any] = field(default_factory=dict)


class TokenBudgetManager:

    def assemble(
        self,
        messages: List[Dict[str, Any]],
        *,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        system_instructions: str = "",
        tool_schemas: Optional[List[Dict[str, Any]]] = None,
        skill_schemas: Optional[List[Dict[str, Any]]] = None,
        artifacts: Optional[Dict[str, Any]] = None,
        budgets: Optional[BudgetSpec] = None,
        sources: Optional[List[ContextSource]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContextAssemblyResult:
        ctx = PromptContext(
            messages=list(messages),
            system_instructions=system_instructions,
            tool_schemas=list(tool_schemas or []),
            skill_schemas=list(skill_schemas or []),
            artifacts=dict(artifacts or {}),
            budgets=budgets or BudgetSpec(),
            sources=list(sources or []),
        )

        meta = dict(metadata or {})
        meta.setdefault("phase", "9-production")
        if session_id:
            meta.setdefault("session_id", session_id)
        if user_id:
            meta.setdefault("user_id", user_id)

        before_tokens = ctx.estimated_tokens()
        ctx = self._apply_token_budget(ctx, meta)
        after_tokens = ctx.estimated_tokens()

        ctx.prompt_version = self._compute_version(ctx)
        meta.setdefault("prompt_version", ctx.prompt_version)
        meta.setdefault("estimated_tokens_before", before_tokens)
        meta.setdefault("estimated_tokens_after", after_tokens)
        meta.setdefault("compacted", before_tokens > after_tokens)
        meta.setdefault("budget", ctx.budgets.token_budget)
        meta.setdefault("compact_threshold", ctx.budgets.compact_threshold)

        return ContextAssemblyResult(context=ctx, metadata=meta)

    def _apply_token_budget(self, ctx: PromptContext, meta: Dict[str, Any]) -> PromptContext:
        if not ctx.is_over_budget():
            return ctx

        budget = ctx.budgets.token_budget

        current = ctx.estimated_tokens()
        while current > budget and ctx.sources:
            lowest = min(ctx.sources, key=lambda s: (0 if s.priority == "low" else 1 if s.priority == "medium" else 2))
            ctx.sources.remove(lowest)
            if lowest.origin == "artifact" and lowest.key in ctx.artifacts:
                summary = f"[Artifact '{lowest.key}' pruned — {lowest.token_estimate} tokens saved]"
                if ctx.messages:
                    ctx.messages[-1]["content"] = str(ctx.messages[-1].get("content", "")) + "\n" + summary
                del ctx.artifacts[lowest.key]
            elif lowest.origin in ("tool", "skill"):
                if ctx.messages:
                    for m in reversed(ctx.messages):
                        if lowest.key in str(m.get("content", "")):
                            m["content"] = f"[{lowest.origin} output '{lowest.key}' pruned — {lowest.token_estimate} tokens saved]"
                            break
            current = ctx.estimated_tokens()

        return ctx

    def _compute_version(self, ctx: PromptContext) -> str:
        payload = {
            "msg_count": len(ctx.messages),
            "system_instructions_hash": hashlib.sha256(
                ctx.system_instructions.encode("utf-8")
            ).hexdigest()[:16],
            "tool_count": len(ctx.tool_schemas),
            "skill_count": len(ctx.skill_schemas),
            "artifact_keys": sorted(ctx.artifacts.keys()),
            "budget": ctx.budgets.token_budget,
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

