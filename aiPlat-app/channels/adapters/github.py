"""
GitHub Channel Adapter (渠道广度延伸批次 14→18)

Parses GitHub webhook payloads (issue/comment/check) into the unified
ChannelMessage format and formats responses for GitHub API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..adapter import ChannelAdapter, ChannelMessage, ChannelResponse, ChannelType


class GitHubAdapter(ChannelAdapter):
    """GitHub 适配器 (webhook: issues/comments/checks)"""

    def parse_message(self, raw_data: dict) -> ChannelMessage:
        # GitHub webhook: {"action":"opened","issue":{...},"comment":{...},"repository":{"full_name":"..."}}
        action = str(raw_data.get("action", ""))
        repo = str((raw_data.get("repository") or {}).get("full_name", ""))
        comment = raw_data.get("comment") or {}
        issue = raw_data.get("issue") or {}
        sender = (raw_data.get("sender") or {}).get("login", "")

        if comment:
            text = f"[{action} comment on {repo}] {comment.get('body', '')}"
            msg_id = str(comment.get("id", ""))
            user = str(comment.get("user", {}).get("login", sender))
            chat = f"{repo}#{issue.get('number', '')}"
        elif issue:
            text = f"[{action} issue on {repo}] {issue.get('title', '')}\n{issue.get('body', '')}"
            msg_id = str(issue.get("id", ""))
            user = str(issue.get("user", {}).get("login", sender))
            chat = f"{repo}#{issue.get('number', '')}"
        else:
            text = f"[{action} on {repo}]"
            msg_id = str(raw_data.get("id", ""))
            user = sender
            chat = repo

        return ChannelMessage(
            message_id=msg_id,
            channel=ChannelType.GITHUB,
            chat_id=chat,
            user_id=user,
            text=text,
            timestamp=datetime.now(),
            metadata={"action": action, "repository": repo, "raw": raw_data},
        )

    def format_response(self, response: ChannelResponse) -> dict:
        return {
            "body": response.text,
        }
