"""
Compaction Prompt Template — configurable compression prompt for ReActLoop.

Design principle (§8, §5.29):
  Engine code MUST NOT contain business SOP prompts. The compaction prompt
  lives here as a template module, overridable via AIPLAT_COMPACTION_PROMPT
  environment variable. If unset, the default template (below) is used.
"""

from __future__ import annotations

import os
from typing import List

_DEFAULT_PROMPT = (
    "You are a conversation compressor. Compress the conversation history below "
    "into a summary that allows task execution to continue.\n\n"
    "Requirements:\n"
    "1) Preserve key conclusions, ongoing plans, and unresolved issues.\n"
    "2) Strictly preserve and output any identifiers (UUIDs, hashes, file names, paths, IDs) verbatim.\n"
    "3) Do not fabricate facts not present in the history.\n\n"
    "Identifiers to preserve (if present): {identifiers}\n\n"
    "History to compress:\n{history}\n\n"
    "Output format:\n"
    "- Active tasks: (tasks currently in progress, preserve user instructions verbatim)\n"
    "- Completed actions: (numbered list, each with tool name + result)\n"
    "- Current state: (key variable values, open files, running processes)\n"
    "- Blockers: (unresolved issues, items requiring human decision)\n"
    "- Key decisions: (important decisions made and rationale)\n"
    "- Pending: (questions or requests user has not yet responded to)\n"
    "- Key files: (list of file paths referenced)\n"
    "- Remaining work: (items to complete next)"
)


def get_compaction_prompt(identifiers: List[str], history_lines: List[str]) -> str:
    prompt_template = os.getenv("AIPLAT_COMPACTION_PROMPT", "").strip()
    if not prompt_template:
        prompt_template = _DEFAULT_PROMPT
    return prompt_template.format(
        identifiers=", ".join(identifiers) if identifiers else "(none)",
        history="\n".join(history_lines),
    )
