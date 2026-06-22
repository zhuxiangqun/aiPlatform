"""
Enterprise Gateway — 企业渠道消息网关

支持: 飞书 (Feishu) / 企业微信 (WeCom) / Slack

架构:
  外部队列消息 → Gateway → CoreFacade → Agent 响应 → Gateway → 渠道回复

仅支持 3 个企业渠道 (坚守企业定位, 不做 Signal/WhatsApp/Telegram)。
"""

from __future__ import annotations

import asyncio, json, os, hashlib, time, uuid, logging
from typing import Any, Dict, List, Optional, Callable

_log = logging.getLogger("aiplat.gateway")


class GatewayMessage:
    """标准化网关消息。"""
    def __init__(self, *, channel: str, channel_chat_id: str, user_id: str = "",
                 text: str = "", message_type: str = "text", raw: Dict[str, Any] = None):
        self.id = f"gw-{uuid.uuid4().hex[:12]}"
        self.channel = channel
        self.channel_chat_id = channel_chat_id
        self.user_id = user_id
        self.text = text.strip() if text else ""
        self.message_type = message_type
        self.raw = raw or {}
        self.timestamp = time.time()

    def session_id(self) -> str:
        return f"{self.channel}:{self.channel_chat_id}"


class EnterpriseGateway:
    """企业渠道消息网关。

    Usage:
        gateway = EnterpriseGateway()
        gateway.register("feishu", FeishuAdapter(webhook_url="..."))
        gateway.register("wecom", WeComAdapter(webhook_url="..."))
        gateway.register("slack", SlackAdapter(bot_token="...", signing_secret="..."))
        await gateway.start()
    """

    def __init__(self, *, core_url: str = ""):
        self._core_url = core_url or os.getenv("AIPLAT_CORE_URL", "http://localhost:8002")
        self._adapters: Dict[str, Any] = {}
        self._handler: Optional[Callable] = None
        self._session_store: Dict[str, List[Dict[str, str]]] = {}
        self._rate_limits: Dict[str, List[float]] = {}
        self._rate_limit_per_minute: int = 100

    def register(self, channel_name: str, adapter: Any):
        """注册渠道适配器。"""
        self._adapters[channel_name] = adapter
        adapter.gateway = self
        _log.info(f"Gateway: registered channel '{channel_name}'")

    def on_message(self, handler: Callable):
        """注册消息处理器。"""
        self._handler = handler

    async def start(self):
        """启动所有渠道适配器。"""
        for name, adapter in self._adapters.items():
            try:
                await adapter.start()
                _log.info(f"Gateway: '{name}' started")
            except Exception as e:
                _log.warning(f"Gateway: '{name}' failed to start: {e}")

    async def handle_message(self, msg: GatewayMessage) -> Dict[str, Any]:
        """处理入站消息 → 调用 Agent → 返回响应。"""
        if not msg.text:
            return {"ok": False, "error": "empty message"}

        # Rate limiting
        if not self._check_rate(msg.channel_chat_id):
            return {"ok": False, "error": "rate_limited"}

        # Build session context
        sid = msg.session_id()
        session_messages = self._session_store.get(sid, [])
        session_messages.append({"role": "user", "content": msg.text})

        try:
            import httpx
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self._core_url}/api/core/knowledge-graph/ask",
                    headers={"Content-Type": "application/json"},
                    json={
                        "question": msg.text,
                        "context": {"tenant_id": "default", "session_id": sid},
                        "options": {"stream": False, "max_tokens": 1000},
                    },
                )
                resp.raise_for_status()
                result = resp.json()
                answer = result.get("answer", "") or str(result.get("output", ""))
                if answer:
                    session_messages.append({"role": "assistant", "content": answer})
                self._session_store[sid] = session_messages[-50:]  # keep last 50
                return {"ok": True, "answer": answer, "run_id": result.get("run_id", "")}
        except Exception as e:
            _log.error(f"Gateway: agent call failed: {e}")
            return {"ok": False, "error": str(e)}

    def _check_rate(self, chat_id: str) -> bool:
        now = time.time()
        if chat_id not in self._rate_limits:
            self._rate_limits[chat_id] = []
        self._rate_limits[chat_id] = [t for t in self._rate_limits[chat_id] if now - t < 60]
        if len(self._rate_limits[chat_id]) >= self._rate_limit_per_minute:
            return False
        self._rate_limits[chat_id].append(now)
        return True


# ── Channel Adapters ──────────────────────────────────────────────────────

class BaseAdapter:
    gateway: EnterpriseGateway = None

    async def start(self): pass
    async def send_message(self, chat_id: str, text: str, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError

    def build_reply(self, answer: str, run_id: str = "") -> Dict[str, Any]:
        """构建标准回复结构。"""
        return {"text": answer, "run_id": run_id}


class FeishuAdapter(BaseAdapter):
    """飞书 适配器 — Webhook + 卡片消息。

    Usage:
        adapter = FeishuAdapter(webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/xxx")
        adapter.send_message(chat_id, "Hello from aiPlat")
    """

    def __init__(self, *, webhook_url: str = "", app_id: str = "", app_secret: str = ""):
        self._webhook_url = webhook_url or os.getenv("AIPLAT_FEISHU_WEBHOOK", "")
        self._app_id = app_id or os.getenv("AIPLAT_FEISHU_APP_ID", "")
        self._app_secret = app_secret or os.getenv("AIPLAT_FEISHU_APP_SECRET", "")

    async def start(self):
        if not self._webhook_url:
            _log.warning("Feishu: no webhook_url configured")

    async def send_message(self, chat_id: str, text: str, *, run_id: str = "", approval_card: bool = False) -> Dict[str, Any]:
        """发送飞书消息。

        Args:
            chat_id: 群聊/用户 open_id
            text: 消息文本
            run_id: Agent run_id (可选)
            approval_card: 是否发送审批卡片 (交互式)

        Returns:
            发送结果
        """
        import httpx
        card = self._build_card(text, run_id) if approval_card else None
        body = {"msg_type": "interactive", "content": {"config": {"wide_screen_mode": True}}} if card else {}
        if card and "elements" in card:
            body["card"] = card

        # Fallback: simple text message
        if not card:
            body = {"msg_type": "text", "content": {"text": text[:4000]}}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self._webhook_url, json=body)
                resp.raise_for_status()
                return {"ok": True, "channel": "feishu", "chat_id": chat_id}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _build_card(self, text: str, run_id: str) -> Dict[str, Any]:
        """构建飞书交互式卡片。"""
        return {
            "header": {"title": {"tag": "plain_text", "content": "aiPlat Agent"}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": text[:2000]}},
            ],
        }


class WeComAdapter(BaseAdapter):
    """企业微信 适配器 — Webhook 机器人。

    Usage:
        adapter = WeComAdapter(webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx")
    """

    def __init__(self, *, webhook_url: str = ""):
        self._webhook_url = webhook_url or os.getenv("AIPLAT_WECOM_WEBHOOK", "")

    async def start(self):
        if not self._webhook_url:
            _log.warning("WeCom: no webhook_url configured")

    async def send_message(self, chat_id: str, text: str, **kwargs) -> Dict[str, Any]:
        import httpx
        body = {"msgtype": "markdown", "markdown": {"content": f"**aiPlat Agent**\n\n{text[:4000]}"}}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self._webhook_url, json=body)
                resp.raise_for_status()
                return {"ok": True, "channel": "wecom", "chat_id": chat_id}
        except Exception as e:
            return {"ok": False, "error": str(e)}


class SlackAdapter(BaseAdapter):
    """Slack 适配器 — Bolt SDK app_mention 事件。

    Usage:
        adapter = SlackAdapter(bot_token="xoxb-xxx", signing_secret="xxx")
    """

    def __init__(self, *, bot_token: str = "", signing_secret: str = ""):
        self._token = bot_token or os.getenv("AIPLAT_SLACK_BOT_TOKEN", "")
        self._secret = signing_secret or os.getenv("AIPLAT_SLACK_SIGNING_SECRET", "")

    async def start(self):
        if not self._token:
            _log.warning("Slack: no bot_token configured")

    async def send_message(self, channel: str, text: str, **kwargs) -> Dict[str, Any]:
        import httpx
        body = {"channel": channel, "text": text[:4000], "mrkdwn": True}
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post("https://slack.com/api/chat.postMessage", headers=headers, json=body)
                resp.raise_for_status()
                return {"ok": True, "channel": "slack", "chat_id": channel}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ── Global singleton ─────────────────────────────────────────────────────

_gateway: Optional[EnterpriseGateway] = None

def get_enterprise_gateway() -> EnterpriseGateway:
    global _gateway
    if _gateway is None: _gateway = EnterpriseGateway()
    return _gateway
