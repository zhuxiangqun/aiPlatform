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
from pathlib import Path
import re

from core.harness.kernel.execution_context import get_active_workspace_context


Message = Dict[str, Any]


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

        # Phase R1: project context injection (best-effort, gated).
        # If the execution has an active repo_root, we prepend AGENTS.md/AIPLAT.md
        # as a system message. This mirrors Hermes-style "project context files".
        try:
            if str(meta.get("enable_project_context", "")).lower() in ("0", "false", "no"):
                raise RuntimeError("project context disabled by metadata")
            ctx = get_active_workspace_context()
            if ctx and ctx.repo_root:
                content, used_path, blocked_reason = self._load_project_context(ctx.repo_root)
                if blocked_reason:
                    meta["project_context_blocked"] = blocked_reason
                if content and used_path:
                    # Avoid duplication if caller already injected it.
                    if not (msgs and isinstance(msgs[0], dict) and msgs[0].get("role") == "system" and "# Project Context" in str(msgs[0].get("content", ""))):
                        msgs = [{"role": "system", "content": f"# Project Context\n\n{content}"}] + msgs
                    meta["project_context_file"] = used_path
                    meta["repo_root"] = str(ctx.repo_root)
                    meta["project_context_sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
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

    # -----------------------------
    # Project context (Phase R1)
    # -----------------------------
    _INJECTION_PATTERNS = [
        (re.compile(r"ignore\\s+(previous|all|above|prior)\\s+instructions", re.I), "prompt_injection"),
        (re.compile(r"do\\s+not\\s+tell\\s+the\\s+user", re.I), "deception_hide"),
        (re.compile(r"system\\s+prompt\\s+override", re.I), "sys_prompt_override"),
    ]
    _INVISIBLE_CHARS = {
        "\u200b", "\u200c", "\u200d", "\u2060", "\ufeff",
        "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
    }
    _MAX_CONTEXT_CHARS = 20_000

    def _load_project_context(self, repo_root: str) -> tuple[str, Optional[str], Optional[str]]:
        """
        Load project context from repo root (best-effort).

        Search order (first hit wins):
        - AGENTS.md
        - AIPLAT.md
        - .aiplat.md

        Returns: (content, used_path, blocked_reason)
        """
        root = Path(str(repo_root)).expanduser()
        candidates = [root / "AGENTS.md", root / "AIPLAT.md", root / ".aiplat.md"]
        for p in candidates:
            try:
                if not p.is_file():
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
                text = text.strip()
                if not text:
                    continue
                text, blocked = self._scan_project_context(text)
                if blocked:
                    return "", str(p), blocked
                if len(text) > self._MAX_CONTEXT_CHARS:
                    text = text[: self._MAX_CONTEXT_CHARS] + "\n\n[TRUNCATED]"
                return text, str(p), None
            except Exception:
                continue
        return "", None, None

    def _scan_project_context(self, content: str) -> tuple[str, Optional[str]]:
        findings: list[str] = []
        for ch in self._INVISIBLE_CHARS:
            if ch in content:
                findings.append(f"invisible_unicode_U+{ord(ch):04X}")
        for pat, reason in self._INJECTION_PATTERNS:
            if pat.search(content):
                findings.append(reason)
        if findings:
            # Block injection-like content: do not feed into LLM.
            return "", ",".join(findings)
        return content, None
