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

    def test_get_channel_adapter_extended_14_channels(self):
        """渠道广度延伸 10→14：signal/matrix/mattermost/line 可解析。"""
        from channels.adapter import get_channel_adapter

        for name in ["signal", "matrix", "mattermost", "line"]:
            adapter = get_channel_adapter(name)
            assert adapter is not None, name
            assert hasattr(adapter, "parse_message")
            assert hasattr(adapter, "format_response")

    def test_signal_adapter_parses_signal_cli(self):
        """signal-cli receive 输出 → ChannelMessage。"""
        from channels.adapter import get_channel_adapter

        adapter = get_channel_adapter("signal")
        msg = adapter.parse_message({
            "envelope": {"source": "+15551234567", "sourceUuid": "abc-123",
                         "timestamp": 1710000000000,
                         "dataMessage": {"message": "signal hello", "timestamp": 1710000000000}},
        })
        assert msg.text == "signal hello"
        assert msg.user_id == "+15551234567"
        assert msg.channel.value == "signal"
        resp = adapter.format_response(type("R", (), {"message_id": "+15551234567", "text": "hi", "markdown": None, "buttons": None})())
        assert resp["recipient"] == "+15551234567"
        assert resp["message"] == "hi"

    def test_matrix_adapter_parses_event(self):
        """Matrix m.room.message event → ChannelMessage。"""
        from channels.adapter import get_channel_adapter

        adapter = get_channel_adapter("matrix")
        msg = adapter.parse_message({
            "type": "m.room.message",
            "content": {"msgtype": "m.text", "body": "matrix hello"},
            "sender": "@alice:server", "event_id": "$ev1", "room_id": "!room1:server",
        })
        assert msg.text == "matrix hello"
        assert msg.chat_id == "!room1:server"
        assert msg.user_id == "@alice:server"
        assert msg.metadata["msgtype"] == "m.text"
        resp = adapter.format_response(type("R", (), {"message_id": "!room1:server", "text": "hi", "markdown": None, "buttons": None})())
        assert resp["msgtype"] == "m.text"
        assert resp["body"] == "hi"

    def test_mattermost_adapter_parses_webhook(self):
        """Mattermost webhook → ChannelMessage。"""
        from channels.adapter import get_channel_adapter

        adapter = get_channel_adapter("mattermost")
        msg = adapter.parse_message({
            "text": "mattermost hello", "user_name": "bot", "user_id": "u1",
            "channel_name": "town-square",
        })
        assert msg.text == "mattermost hello"
        assert msg.chat_id == "town-square"
        assert msg.user_id == "u1"
        resp = adapter.format_response(type("R", (), {"message_id": "town-square", "text": "hi", "markdown": None, "buttons": None})())
        assert resp["channel"] == "town-square"
        assert resp["text"] == "hi"

    def test_line_adapter_parses_webhook(self):
        """LINE webhook events → ChannelMessage。"""
        from channels.adapter import get_channel_adapter

        adapter = get_channel_adapter("line")
        msg = adapter.parse_message({
            "events": [{
                "type": "message", "replyToken": "rt1",
                "source": {"groupId": "g1", "userId": "u1"},
                "message": {"id": "m1", "type": "text", "text": "line hello"},
            }],
        })
        assert msg.text == "line hello"
        assert msg.chat_id == "g1"
        assert msg.user_id == "u1"
        assert msg.metadata["reply_token"] == "rt1"
        resp = adapter.format_response(type("R", (), {"message_id": "rt1", "text": "hi", "markdown": None, "buttons": None})())
        assert resp["replyToken"] == "rt1"
        assert resp["messages"][0]["text"] == "hi"

    def test_get_channel_adapter_extended_18_channels(self):
        """渠道广度延伸 14→18：qq/reddit/github/sms 可解析。"""
        from channels.adapter import get_channel_adapter

        for name in ["qq", "reddit", "github", "sms"]:
            adapter = get_channel_adapter(name)
            assert adapter is not None, name
            assert hasattr(adapter, "parse_message")
            assert hasattr(adapter, "format_response")

    def test_qq_adapter_parses_bot_message(self):
        """QQ 机器人回调 → ChannelMessage。"""
        from channels.adapter import get_channel_adapter

        adapter = get_channel_adapter("qq")
        msg = adapter.parse_message({"event": {"message": {
            "id": "m1", "content": "qq hello", "chat_id": "g1", "from_id": "u1"}}})
        assert msg.text == "qq hello"
        assert msg.chat_id == "g1"
        assert msg.user_id == "u1"
        assert msg.channel.value == "qq"
        resp = adapter.format_response(type("R", (), {"message_id": "g1", "text": "hi", "markdown": None, "buttons": None})())
        assert resp["msg_type"] == "text"
        assert resp["content"] == "hi"

    def test_reddit_adapter_parses_comment(self):
        """Reddit comment → ChannelMessage。"""
        from channels.adapter import get_channel_adapter

        adapter = get_channel_adapter("reddit")
        msg = adapter.parse_message({"data": {
            "name": "t1_c1", "author": "alice", "subreddit": "programming",
            "body": "reddit hello", "link_title": "a post"}})
        assert msg.text == "reddit hello"
        assert msg.chat_id == "r/programming"
        assert msg.user_id == "alice"
        assert msg.metadata["link_title"] == "a post"
        resp = adapter.format_response(type("R", (), {"message_id": "t1_c1", "text": "hi", "markdown": None, "buttons": None})())
        assert resp["body"] == "hi"

    def test_github_adapter_parses_issue_comment(self):
        """GitHub webhook (comment) → ChannelMessage。"""
        from channels.adapter import get_channel_adapter

        adapter = get_channel_adapter("github")
        msg = adapter.parse_message({
            "action": "created", "repository": {"full_name": "org/repo"},
            "issue": {"number": 5}, "sender": {"login": "bob"},
            "comment": {"id": 100, "body": "github hello", "user": {"login": "bob"}},
        })
        assert "github hello" in msg.text
        assert msg.chat_id == "org/repo#5"
        assert msg.user_id == "bob"
        assert msg.metadata["action"] == "created"
        resp = adapter.format_response(type("R", (), {"message_id": "org/repo#5", "text": "hi", "markdown": None, "buttons": None})())
        assert resp["body"] == "hi"

    def test_sms_adapter_parses_twilio(self):
        """Twilio-style SMS webhook → ChannelMessage。"""
        from channels.adapter import get_channel_adapter

        adapter = get_channel_adapter("sms")
        msg = adapter.parse_message({
            "From": "+15551234567", "To": "+15559876543",
            "Body": "sms hello", "MessageSid": "SM1"})
        assert msg.text == "sms hello"
        assert msg.user_id == "+15551234567"
        assert "+15551234567" in msg.chat_id
        assert msg.channel.value == "sms"
        resp = adapter.format_response(type("R", (), {"message_id": "+15551234567", "text": "hi", "markdown": None, "buttons": None})())
        assert resp["To"] == "+15551234567"
        assert resp["Body"] == "hi"

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

    def test_get_channel_adapter_22_channels(self):
        """渠道广度延伸 18→22：google_chat/homeassistant/irc/ntfy 可解析。"""
        from channels.adapter import get_channel_adapter

        for name in ["google_chat", "homeassistant", "irc", "ntfy"]:
            adapter = get_channel_adapter(name)
            assert adapter is not None, name
            assert hasattr(adapter, "parse_message")
            assert hasattr(adapter, "format_response")

    def test_google_chat_adapter_parses_event(self):
        """Google Chat event → ChannelMessage。"""
        from channels.adapter import get_channel_adapter

        adapter = get_channel_adapter("google_chat")
        msg = adapter.parse_message({
            "type": "MESSAGE",
            "space": {"name": "spaces/AAA", "type": "ROOM"},
            "message": {"name": "spaces/AAA/messages/1",
                        "sender": {"name": "users/alice"},
                        "text": "google hello",
                        "thread": {"name": "spaces/AAA/threads/t1"}}})
        assert msg.text == "google hello"
        assert msg.chat_id == "spaces/AAA"
        assert msg.user_id == "users/alice"
        assert msg.channel.value == "google_chat"
        resp = adapter.format_response(type("R", (), {"message_id": "1", "text": "hi", "markdown": None, "buttons": None})())
        assert resp["text"] == "hi"

    def test_homeassistant_adapter_parses_event(self):
        """Home Assistant event → ChannelMessage。"""
        from channels.adapter import get_channel_adapter

        adapter = get_channel_adapter("homeassistant")
        msg = adapter.parse_message({
            "origin": "ha",
            "event": {"id": 1, "event_type": "call_service",
                      "data": {"entity_id": "light.living", "message": "ha hello"}}})
        assert msg.text == "ha hello"
        assert msg.chat_id == "light.living"
        assert msg.channel.value == "homeassistant"
        resp = adapter.format_response(type("R", (), {"message_id": "light.living", "text": "hi", "markdown": None, "buttons": None})())
        assert resp["message"] == "hi"

    def test_irc_adapter_parses_privmsg(self):
        """IRC PRIVMSG → ChannelMessage。"""
        from channels.adapter import get_channel_adapter

        adapter = get_channel_adapter("irc")
        msg = adapter.parse_message({
            "prefix": "nick!user@host", "command": "PRIVMSG",
            "params": ["#room", "irc hello"]})
        assert msg.text == "irc hello"
        assert msg.chat_id == "#room"
        assert msg.user_id == "nick"
        assert msg.channel.value == "irc"
        resp = adapter.format_response(type("R", (), {"message_id": "#room", "text": "hi", "markdown": None, "buttons": None})())
        assert resp["command"] == "PRIVMSG"

    def test_ntfy_adapter_parses_publish(self):
        """ntfy.sh publish → ChannelMessage。"""
        from channels.adapter import get_channel_adapter

        adapter = get_channel_adapter("ntfy")
        msg = adapter.parse_message({
            "id": "n1", "topic": "alerts", "title": "Alert",
            "message": "ntfy hello", "priority": 5, "tags": ["warning"]})
        assert "ntfy hello" in msg.text
        assert "Alert" in msg.text
        assert msg.chat_id == "alerts"
        assert msg.channel.value == "ntfy"
        resp = adapter.format_response(type("R", (), {"message_id": "alerts", "text": "hi", "markdown": None, "buttons": None})())
        assert resp["message"] == "hi"
