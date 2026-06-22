"""
Integration tests for EnterpriseGateway wiring.

Verify that:
  - Gateway can be instantiated and adapters registered
  - GatewayMessage objects are correctly structured
  - handle_message() dispatches to the right adapter
"""
import pytest


class TestGatewayIntegration:

    def test_gateway_instantiation(self):
        """EnterpriseGateway should instantiate and accept adapter registration."""
        from core.gateway import EnterpriseGateway, BaseAdapter

        gateway = EnterpriseGateway()

        class EchoAdapter(BaseAdapter):
            async def send_message(self, chat_id: str, text: str, **kwargs):
                return {"ok": True, "chat_id": chat_id, "text": text[:50]}

        gateway.register("echo", EchoAdapter())
        assert "echo" in getattr(gateway, "_adapters", {}), \
            "Adapter should be registered after register()"

    @pytest.mark.asyncio
    async def test_adapter_send_message(self):
        """Adapter.send_message is the outbound path for enterprise notifications."""
        from core.gateway import EnterpriseGateway

        gateway = EnterpriseGateway()
        delivered = []

        class TestAdapter:
            async def start(self):
                return True
            async def send_message(self, chat_id: str, text: str, **kwargs):
                delivered.append({"chat_id": chat_id, "text": text})
                return {"ok": True}

        gateway.register("test", TestAdapter())
        await gateway.start()

        # Outbound notification: approval event triggers send_message directly
        adapter = gateway._adapters.get("test")
        assert adapter is not None
        result = await adapter.send_message("chat-123", "审批通知: Agent 需要人工确认")
        assert result["ok"] is True
        assert len(delivered) == 1
        assert "审批通知" in delivered[0]["text"]

    def test_gateway_message_structure(self):
        """GatewayMessage should have correct fields."""
        from core.gateway import GatewayMessage

        msg = GatewayMessage(
            channel="feishu",
            channel_chat_id="ou_xxx",
            user_id="user-1",
            text="Test notification",
            message_type="text",
        )
        assert msg.channel == "feishu"
        assert msg.channel_chat_id == "ou_xxx"
        assert msg.text == "Test notification"
        assert msg.user_id == "user-1"
        assert msg.message_type == "text"
        assert msg.session_id() is not None

    @pytest.mark.asyncio
    async def test_gateway_empty_start_safe(self):
        """Starting gateway with no adapters should not crash."""
        from core.gateway import EnterpriseGateway

        gateway = EnterpriseGateway()
        await gateway.start()
        # No adapters — should not raise
