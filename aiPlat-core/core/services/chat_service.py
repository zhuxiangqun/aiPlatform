"""
Universal Chat Service — reusable multi-turn conversation for any agent.
Sessions are in-memory only (no persistence across restarts).
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional

_CHAT_REPLY_PROMPT = os.getenv(
    "AIPLAT_CHAT_REPLY_PROMPT",
    "Based on the above conversation history and context, provide a helpful response.",
)


class ChatService:

    def __init__(self, model: Any = None):
        self._model = model
        self._sessions: Dict[str, Dict[str, Any]] = {}

    async def create_session(
        self,
        agent_id: str,
        system_prompt: str = "",
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        session_id = f"chat_{uuid.uuid4().hex[:8]}"
        self._sessions[session_id] = {
            "session_id": session_id,
            "agent_id": agent_id,
            "system_prompt": system_prompt,
            "context": initial_context or {},
            "messages": [],
            "metadata": {},
        }
        return session_id

    async def chat(self, session_id: str, message: str) -> Dict[str, Any]:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError("Session not found")

        session["messages"].append({"role": "user", "content": message})
        sp = session.get("system_prompt", "")
        ctx = session.get("context", {})

        full_prompt = f"""{sp}

## 会话历史
{json.dumps(session["messages"][-10:], ensure_ascii=False, indent=2)}

## 上下文
{json.dumps(ctx, ensure_ascii=False, indent=2)}

{_CHAT_REPLY_PROMPT}
"""
        reply = ""
        if self._model:
            from core.harness.syscalls.llm import sys_llm_generate
            result = await sys_llm_generate(self._model, [{"role": "user", "content": full_prompt}], trace_context={"source": "chat_service"})
            reply = result if isinstance(result, str) else getattr(result, "content", str(result))

        session["messages"].append({"role": "assistant", "content": reply})
        return {"reply": reply, "session_id": session_id, "messages": session["messages"]}

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._sessions.get(session_id)
