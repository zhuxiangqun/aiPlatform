"""
PromptAssembler (Phase 4 - minimal).

Phase 4 minimal contract:
- Accepts a prompt input (str or list[message dict])
- Produces a normalized message list and a stable prompt_version

Notes:
- This is intentionally *non-invasive*: by default it preserves the original
  content and only adds versioning metadata.
- Token budgeting / compaction will be handled by ContextAssembler in Phase 4.1+.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from core.harness.kernel.execution_context import get_active_workspace_context
from core.harness.context.engine import DefaultContextEngine


Message = Dict[str, Any]
_DEFAULT_CONTEXT_ENGINE = DefaultContextEngine()


@dataclass
class PromptAssemblyResult:
    messages: List[Message]
    prompt_version: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class PromptAssembler:
    """
    Kernel-side prompt assembler.

    Versioning:
    - prompt_version is a sha256 of canonical JSON serialization of messages.
    - This is deterministic and suitable for replay/debugging.
    """

    def assemble(
        self,
        prompt: Union[str, List[Message]],
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PromptAssemblyResult:
        msgs = self._normalize(prompt)
        meta = dict(metadata or {})

        # Roadmap-1 (Phase 1): ContextEngine handles project context injection.
        try:
            ctx = get_active_workspace_context()
            res = _DEFAULT_CONTEXT_ENGINE.apply(
                messages=msgs, metadata=meta, repo_root=str(ctx.repo_root) if ctx and ctx.repo_root else None
            )
            msgs, meta = res.messages, res.metadata
        except Exception:
            pass

        # Roadmap-1 (Phase 1): lightweight prompt stats (no behavior change).
        try:
            meta.setdefault("context_engine", "default_v1")
            meta.setdefault("prompt_message_count", len(msgs))
            meta.setdefault("prompt_estimated_tokens", self._estimate_tokens(msgs))
        except Exception:
            pass

        version = self._hash_messages(msgs)
        meta.setdefault("versioning", "sha256(messages)")
        return PromptAssemblyResult(messages=msgs, prompt_version=version, metadata=meta)

    # -----------------------------
    # Phase 4: centralized templates
    # -----------------------------

    def build_react_reasoning_messages(
        self,
        *,
        task: str,
        history: str,
        tools_desc: str,
        observation: str,
    ) -> List[Message]:
        prompt = f"""Task: {task}

History:
{history}

Available tools:
{tools_desc}

Observation: {observation}

Think about what to do next. If using a tool/skill, respond with:
1) 优先（结构化）：
```json
{{"tool":"tool_name","args":{{...}}}}
```

Skill（必须显式标注，避免误触发）：
```json
{{"skill":"skill_name","args":{{...}}}}
```

2) 兼容旧格式（tool）：
ACTION: tool_name: argument

兼容旧格式（skill）：
SKILL: skill_name: argument

If finished, respond with:
DONE: final_answer
"""
        return [{"role": "user", "content": prompt}]

    def build_plan_execute_plan_messages(self, *, task: str) -> List[Message]:
        prompt = (
            "请为任务生成可执行的步骤计划。\n"
            "要求：\n"
            "1) 普通步骤用自然语言描述即可。\n"
            "2) 若某一步需要调用工具，请用结构化 JSON 表达（单行）：\n"
            "   {\"tool\":\"tool_name\",\"args\":{...}}\n"
            "3) 若某一步需要调用 skill，也必须显式标注（单行）：\n"
            "   {\"skill\":\"skill_name\",\"args\":{...}}\n"
            f"\nTask: {task}\n"
        )
        return [{"role": "user", "content": prompt}]

    def build_plan_execute_step_messages(self, *, action: str, task: str) -> List[Message]:
        prompt = f"Execute this step: {action}\nContext: {task}"
        return [{"role": "user", "content": prompt}]

    def build_langgraph_reason_messages(
        self,
        *,
        history: str,
        reasoning: str,
        action: str,
        observation: str,
    ) -> List[Message]:
        prompt = f"""Current state:
- History: {history}
- Reasoning: {reasoning}
- Action: {action}
- Observation: {observation}

What should I do next?

优先使用结构化工具调用（推荐）：
```json
{{"tool":"tool_name","args":{{...}}}}
```

兼容旧格式：
ACTION: tool_name: {{json_or_text}}

If finished, respond with: DONE
"""
        return [{"role": "user", "content": prompt}]

    def build_langgraph_observe_messages(self, *, observation: str) -> List[Message]:
        prompt = f"""Observation from tool execution: {observation}

Based on this observation, what should I do next?
- If more work needed, respond with what to do
- If task complete, respond with DONE
- If error occurred, respond with ERROR: description
"""
        return [{"role": "user", "content": prompt}]

    def _normalize(self, prompt: Union[str, List[Message]]) -> List[Message]:
        if isinstance(prompt, str):
            return [{"role": "user", "content": prompt}]
        if isinstance(prompt, list):
            out: List[Message] = []
            for m in prompt:
                if not isinstance(m, dict):
                    continue
                role = m.get("role", "user")
                content = m.get("content", "")
                out.append({**m, "role": role, "content": content})
            return out
        # Fallback: coerce
        return [{"role": "user", "content": str(prompt)}]

    def _hash_messages(self, messages: List[Message]) -> str:
        canonical = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # Project context logic moved to ContextEngine (core.harness.context.engine)

    def _estimate_tokens(self, messages: List[Message]) -> int:
        """
        Best-effort token estimator.
        We intentionally avoid model-specific tokenizers at this phase.
        """
        total_chars = 0
        for m in messages or []:
            try:
                c = m.get("content", "")
                if c is None:
                    continue
                total_chars += len(str(c))
            except Exception:
                continue
        # heuristic: ~4 chars per token
        return int(total_chars / 4) + 1
