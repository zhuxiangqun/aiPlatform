"""
Reddit Channel Adapter (渠道广度延伸批次 14→18)

Parses Reddit mention/webhook payloads into the unified ChannelMessage
format and formats responses for Reddit API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class RedditAdapter(ChannelAdapter):
    """Reddit 适配器 (mention/comment)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        # Reddit: {"data": {"name": "t1_...", "author": "...", "subreddit": "...",
        #                   "body": "...", "link_title": "..."}}（comment 或 mention）
        data = raw_data.get("data") or raw_data
        text = str(data.get("body", "") or data.get("selftext", "") or "")
        author = str(data.get("author", ""))
        subreddit = str(data.get("subreddit", "") or "")
        # chat_id = subreddit（频道级）；user_id = author
        return ChannelMessage(
            message_id=str(data.get("name", "") or data.get("id", "")),
            channel=ChannelType.REDDIT,
            chat_id=f"r/{subreddit}" if subreddit else "r/all",
            user_id=author,
            text=text,
            timestamp=datetime.now(),
            metadata={"link_title": data.get("link_title", ""), "raw": raw_data},
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "parent_id": response.message_id,
            "body": response.text,
        }
