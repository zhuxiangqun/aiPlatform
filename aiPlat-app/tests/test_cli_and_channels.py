"""
Test Channel adapter structure and imports.
"""
import pytest


class TestChannelAdapter:
    """Test channel adapter module structure."""

    def test_slack_handler_importable(self):
        from channels.slack import SlackHandler
        assert SlackHandler is not None

    def test_slack_handler_has_methods(self):
        from channels.slack import SlackHandler
        handler = SlackHandler()
        assert hasattr(handler, "handle_event")
        assert hasattr(handler, "handle_command")
        assert hasattr(handler, "verify_request")

    def test_channel_adapter_imports(self):
        from channels.adapter import (
            ChannelAdapter, ChannelMessage, ChannelResponse, ChannelDispatcher,
        )
        assert ChannelAdapter is not None

    def test_get_channel_adapter_all_channels(self):
        """P1-A4 acceptance: all 7 channels resolve via get_channel_adapter."""
        from channels.adapter import get_channel_adapter

        for name in ["telegram", "slack", "webchat", "discord", "wecom", "email", "dingtalk"]:
            adapter = get_channel_adapter(name)
            assert adapter is not None, name
            assert hasattr(adapter, "parse_message")
            assert hasattr(adapter, "format_response")

    def test_get_channel_adapter_extended_10_channels(self):
        """渠道广度延伸：whatsapp/lark/teams 可解析（3 内置 + 7 扩展 = 10）。"""
        from channels.adapter import get_channel_adapter

        for name in ["whatsapp", "lark", "teams"]:
            adapter = get_channel_adapter(name)
            assert adapter is not None, name
            assert hasattr(adapter, "parse_message")
            assert hasattr(adapter, "format_response")

    def test_whatsapp_adapter_parses_cloud_api_payload(self):
        """WhatsApp Cloud API webhook → ChannelMessage。"""
        from channels.adapter import get_channel_adapter

        adapter = get_channel_adapter("whatsapp")
        msg = adapter.parse_message({
            "entry": [{"changes": [{"value": {
                "messages": [{"id": "wamid1", "from": "15551234567", "type": "text",
                              "text": {"body": "hello whatsapp"}}],
                "contacts": [{"wa_id": "15551234567", "profile": {"name": "Alice"}}],
            }}]}],
        })
        assert msg.text == "hello whatsapp"
        assert msg.user_id == "15551234567"
        assert msg.channel.value == "whatsapp"
        resp = adapter.format_response(type("R", (), {"message_id": "15551234567", "text": "hi", "markdown": None, "buttons": None})())
        assert resp["messaging_product"] == "whatsapp"
        assert resp["text"]["body"] == "hi"

    def test_lark_adapter_parses_event_callback(self):
        """Lark event callback（content JSON 字符串）→ ChannelMessage。"""
        from channels.adapter import get_channel_adapter

        adapter = get_channel_adapter("lark")
        msg = adapter.parse_message({
            "event": {
                "message": {"message_id": "om1", "chat_id": "oc1", "content": '{"text":"飞书你好"}'},
                "sender": {"sender_id": {"open_id": "ou1"}},
            },
        })
        assert msg.text == "飞书你好"
        assert msg.chat_id == "oc1"
        assert msg.user_id == "ou1"
        resp = adapter.format_response(type("R", (), {"message_id": "oc1", "text": "ok", "markdown": None, "buttons": None})())
        assert resp["msg_type"] == "text"
        assert resp["content"]["text"] == "ok"

    def test_teams_adapter_parses_activity(self):
        """Teams Bot Framework activity → ChannelMessage。"""
        from channels.adapter import get_channel_adapter

        adapter = get_channel_adapter("teams")
        msg = adapter.parse_message({
            "id": "a1", "text": "teams hello",
            "conversation": {"id": "conv1", "conversationType": "personal"},
            "from": {"id": "user1"}, "serviceUrl": "https://smba.trafficmanager.net/",
        })
        assert msg.text == "teams hello"
        assert msg.chat_id == "conv1"
        assert msg.user_id == "user1"
        assert msg.metadata["conversation_type"] == "personal"
        resp = adapter.format_response(type("R", (), {"message_id": "conv1", "text": "hi", "markdown": None, "buttons": None})())
        assert resp["type"] == "message"
        assert resp["text"] == "hi"

    def test_get_channel_adapter_unknown_raises(self):
        from channels.adapter import get_channel_adapter

        try:
            get_channel_adapter("no_such_channel")
            raise AssertionError("expected ValueError")
        except ValueError:
            pass

    def test_extended_adapter_dispatch(self):
        """Discord adapter parses a sample webhook payload."""
        from channels.adapter import get_channel_adapter

        adapter = get_channel_adapter("discord")
        msg = adapter.parse_message({"message": {"id": "m1", "author": {"id": "u1"},
                                                "channel": {"id": "c1"}, "content": "hello"}})
        assert msg.text == "hello"
        assert msg.chat_id == "c1"
