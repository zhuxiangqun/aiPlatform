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
