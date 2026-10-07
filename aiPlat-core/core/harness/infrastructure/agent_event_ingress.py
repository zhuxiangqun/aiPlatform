"""Agent event ingress — external events wake workspace agents.

Two paths (opt-in via AIPLAT_AGENT_EVENT_INGRESS=true):
1. File inbox: ~/.aiplat/agent_events/inbox/*.json  (zero infra deps)
2. Messaging: Redis/Kafka when AIPLAT_MESSAGING_BACKEND is set

Payload JSON:
  {"agent_id": "...", "message": "...", "session_id": "", "max_steps": 10}

callers: core/server.py lifespan
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

_log = logging.getLogger("aiplat.agent_event_ingress")

RunAgentFn = Callable[..., Awaitable[Dict[str, Any]]]

_INBOX = Path(os.path.expanduser(
    os.getenv("AIPLAT_AGENT_EVENT_INBOX", "~/.aiplat/agent_events/inbox")
))
_PROCESSED = _INBOX.parent / "processed"
_POLL_INTERVAL = float(os.getenv("AIPLAT_AGENT_EVENT_POLL_SECONDS", "15") or "15")


class AgentEventIngress:
    """Poll file inbox (+ optional messaging) and dispatch run_workspace_agent."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        run_agent: Optional[RunAgentFn] = None,
    ):
        self._enabled = enabled
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._dispatched = 0
        self._errors = 0
        self._messaging_client = None
        self._run_agent = run_agent

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "running": self._running,
            "dispatched": self._dispatched,
            "errors": self._errors,
            "inbox": str(_INBOX),
            "messaging": bool(self._messaging_client),
        }

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        _INBOX.mkdir(parents=True, exist_ok=True)
        _PROCESSED.mkdir(parents=True, exist_ok=True)
        await self._try_start_messaging()
        self._task = asyncio.create_task(self._loop())
        _log.info(
            "AgentEventIngress started inbox=%s messaging=%s",
            _INBOX,
            bool(self._messaging_client),
        )

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        if self._messaging_client is not None:
            try:
                await self._messaging_client.close()
            except Exception:
                _log.debug("messaging client close failed", exc_info=True)
            self._messaging_client = None

    async def _try_start_messaging(self) -> None:
        backend = (os.getenv("AIPLAT_MESSAGING_BACKEND") or "").strip().lower()
        if not backend or backend in ("none", "off", "disabled"):
            return
        try:
            from infra.messaging.schemas import MessagingConfig
            from infra.messaging.factory import create_messaging_client

            hosts_raw = os.getenv("AIPLAT_MESSAGING_HOSTS", "localhost")
            hosts = [h.strip() for h in hosts_raw.split(",") if h.strip()]
            cfg = MessagingConfig(backend=backend, hosts=hosts or ["localhost"])
            client = create_messaging_client(cfg)
            topic = os.getenv("AIPLAT_AGENT_EVENT_TOPIC", "agent.wake")
            await client.subscribe(topic, self._on_message)
            self._messaging_client = client
            _log.info("AgentEventIngress subscribed topic=%s backend=%s", topic, backend)
        except Exception:
            _log.warning(
                "AgentEventIngress messaging unavailable; file inbox only",
                exc_info=True,
            )

    def _on_message(self, message: Any) -> None:
        """Sync callback from messaging client — schedule async dispatch."""
        try:
            body = message.body if hasattr(message, "body") else message
            if isinstance(body, bytes):
                body = body.decode("utf-8", errors="replace")
            payload = json.loads(body) if isinstance(body, str) else body
            if not isinstance(payload, dict):
                return
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._dispatch(payload, source="messaging"))
            except RuntimeError:
                asyncio.run(self._dispatch(payload, source="messaging"))
        except Exception:
            self._errors += 1
            _log.debug("messaging payload handle failed", exc_info=True)

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._scan_inbox()
            except asyncio.CancelledError:
                break
            except Exception:
                _log.debug("inbox scan error", exc_info=True)
            await asyncio.sleep(_POLL_INTERVAL)

    async def _scan_inbox(self) -> None:
        if not self._enabled or not _INBOX.is_dir():
            return
        for path in sorted(_INBOX.glob("*.json")):
            try:
                raw = path.read_text(encoding="utf-8")
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    continue
                await self._dispatch(payload, source=f"file:{path.name}")
                dest = _PROCESSED / path.name
                try:
                    path.rename(dest)
                except OSError:
                    path.unlink(missing_ok=True)  # noqa: cleanup-best-effort
            except Exception:
                self._errors += 1
                _log.warning("failed to process agent event file %s", path, exc_info=True)

    async def _dispatch(self, payload: Dict[str, Any], *, source: str) -> None:
        agent_id = str(payload.get("agent_id") or "").strip()
        message = str(payload.get("message") or payload.get("input") or "").strip()
        if not agent_id or not message:
            _log.warning("agent event missing agent_id/message source=%s", source)
            self._errors += 1
            return
        try:
            agent_info = None
            if self._run_agent is None:
                from core.harness.integration import get_agent_registry

                registry = get_agent_registry()
                if registry is not None:
                    get_fn = getattr(registry, "get", None) or getattr(registry, "get_agent", None)
                    if callable(get_fn):
                        agent_info = get_fn(agent_id)
            if agent_info is None:
                # Minimal stand-in so run_workspace_agent can resolve id/prompt
                class _Info:
                    id = agent_id
                    config: Dict[str, Any] = {}

                agent_info = _Info()

            run_fn = self._run_agent
            if run_fn is None:
                from core.api.core_facade import run_workspace_agent as run_fn

            result = await run_fn(
                agent_info,
                message,
                max_steps=int(payload.get("max_steps") or 10),
                session_id=str(payload.get("session_id") or ""),
                stream=bool(payload.get("stream", True)),
            )
            self._dispatched += 1
            _log.info(
                "agent event dispatched source=%s agent_id=%s run_id=%s",
                source,
                agent_id,
                (result or {}).get("run_id"),
            )
        except Exception:
            self._errors += 1
            _log.warning(
                "agent event dispatch failed source=%s agent_id=%s",
                source,
                agent_id,
                exc_info=True,
            )


_ingress: Optional[AgentEventIngress] = None


def get_agent_event_ingress() -> AgentEventIngress:
    global _ingress
    if _ingress is None:
        enabled = os.getenv("AIPLAT_AGENT_EVENT_INGRESS", "false").lower() in (
            "1", "true", "yes", "y",
        )
        _ingress = AgentEventIngress(enabled=enabled)
    return _ingress
