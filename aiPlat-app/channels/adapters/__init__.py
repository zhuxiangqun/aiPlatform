"""
Channel adapter registry (P1-A4) — all adapters registered here.

Extend by adding a new adapter file and registering it in ADAPTERS.
"""
from __future__ import annotations

from ..adapter import ChannelType
from .discord import DiscordAdapter
from .wecom import WeComAdapter
from .email import EmailAdapter
from .dingtalk import DingTalkAdapter
from .whatsapp import WhatsAppAdapter
from .lark import LarkAdapter
from .teams import TeamsAdapter
from .signal import SignalAdapter
from .matrix import MatrixAdapter
from .mattermost import MattermostAdapter
from .line import LineAdapter
from .qq import QQAdapter
from .reddit import RedditAdapter
from .github import GitHubAdapter
from .sms import SMSAdapter
from .google_chat import GoogleChatAdapter
from .homeassistant import HomeAssistantAdapter
from .irc import IRCAdapter
from .ntfy import NtfyAdapter

# channel → adapter class
ADAPTERS = {
    ChannelType.DISCORD: DiscordAdapter,
    ChannelType.WECHAT: WeComAdapter,
    ChannelType.EMAIL: EmailAdapter,
    ChannelType.DINGTALK: DingTalkAdapter,
    ChannelType.WHATSAPP: WhatsAppAdapter,
    ChannelType.LARK: LarkAdapter,
    ChannelType.TEAMS: TeamsAdapter,
    ChannelType.SIGNAL: SignalAdapter,
    ChannelType.MATRIX: MatrixAdapter,
    ChannelType.MATTERMOST: MattermostAdapter,
    ChannelType.LINE: LineAdapter,
    ChannelType.QQ: QQAdapter,
    ChannelType.REDDIT: RedditAdapter,
    ChannelType.GITHUB: GitHubAdapter,
    ChannelType.SMS: SMSAdapter,
    ChannelType.GOOGLE_CHAT: GoogleChatAdapter,
    ChannelType.HOMEASSISTANT: HomeAssistantAdapter,
    ChannelType.IRC: IRCAdapter,
    ChannelType.NTFY: NtfyAdapter,
}

__all__ = [
    "ADAPTERS", "DiscordAdapter", "WeComAdapter", "EmailAdapter", "DingTalkAdapter",
    "WhatsAppAdapter", "LarkAdapter", "TeamsAdapter",
    "SignalAdapter", "MatrixAdapter", "MattermostAdapter", "LineAdapter",
    "QQAdapter", "RedditAdapter", "GitHubAdapter", "SMSAdapter",
    "GoogleChatAdapter", "HomeAssistantAdapter", "IRCAdapter", "NtfyAdapter",
]


def get_adapter(channel: ChannelType):
    """Get adapter instance for a channel type."""
    cls = ADAPTERS.get(channel)
    if cls is None:
        raise ValueError(f"No adapter registered for channel: {channel}")
    return cls()
