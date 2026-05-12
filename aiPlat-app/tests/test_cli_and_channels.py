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
