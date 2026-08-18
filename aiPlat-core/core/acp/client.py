"""ACP (Agent Communication Protocol) client — WebSocket edition.

P1-A3: makes ACPProvider's external subagent backend actually usable.

The ACP server (core/acp/server.py) exposes an IDE-style chat protocol
(chat/diff/exec/status over ws://host:port/acp). This client wraps that
protocol into the SubagentProvider contract (start / continue / stop):

  start(name, task)      → send {"type":"chat","content":task} → chat_response
  continue(instance_id)  → subsequent chat turns reuse the server session_id
  stop(instance_id)      → best-effort (server is stateless chat)

Failures are surfaced loudly (fail-loud), matching ACPProvider's design.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger("aiplat.acp.client")


class ACPClient:
    """Minimal WebSocket client for the aiPlat ACP server chat protocol."""

    def __init__(self, endpoint: str = "ws://localhost:8005/acp"):
        self._endpoint = endpoint
        self._session_ids: Dict[str, str] = {}

    async def _chat(self, content: str, session_id: str = "") -> Dict[str, Any]:
        """Send one chat message; return parsed response dict."""
        import websockets  # noqa: F401  — runtime dep; ACP is opt-in
        import websockets.asyncio.client as ws_client

        payload = {"type": "chat", "content": content}
        if session_id:
            payload["session_id"] = session_id

        async with ws_client.connect(self._endpoint) as ws:
            await ws.send(json.dumps(payload))
            raw = await ws.recv()
            return json.loads(raw) if isinstance(raw, str) else raw

    async def start_agent(self, name: str, task: str) -> Dict[str, Any]:
        """Start an agent turn — maps to an ACP chat message.

        Returns SubagentProvider-compatible dict: ok/output/error/instance_id.
        """
        try:
            sid = str(uuid.uuid4())[:12]
            resp = await self._chat(task, session_id=sid)
            self._session_ids[name] = sid
            if resp.get("type") == "chat_response" and resp.get("error"):
                return {
                    "ok": False,
                    "error": str(resp.get("error", "unknown ACP error"))[:300],
                    "output": "", "instance_id": sid, "can_continue": False,
                }
            content = str(resp.get("content") or "")
            return {
                "ok": bool(content),
                "output": content,
                "error": "" if content else "empty ACP response",
                "instance_id": sid,
                "can_continue": bool(content),
            }
        except Exception as e:  # noqa: BLE001 — fail-loud surface
            logger.debug("acp start_agent failed: %s", e, exc_info=True)
            return {
                "ok": False,
                "error": f"ACP client error: {str(e)[:300]}",
                "output": "", "instance_id": "", "can_continue": False,
            }

    async def continue_agent(self, instance_id: str, task: str) -> Dict[str, Any]:
        """Continue a session — send another chat turn on the same session."""
        try:
            resp = await self._chat(task, session_id=instance_id)
            content = str(resp.get("content") or "")
            return {
                "ok": bool(content),
                "output": content,
                "error": "" if content else "empty ACP response",
                "instance_id": instance_id,
                "can_continue": bool(content),
            }
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False,
                "error": f"ACP client error: {str(e)[:300]}",
                "output": "", "instance_id": instance_id, "can_continue": False,
            }


__all__ = ["ACPClient"]
