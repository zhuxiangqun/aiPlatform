"""
TextCleaner — 可配置的文本清洗规则引擎。

从 ~/.aiplat/cleanup_rules.yaml 加载清洗规则（启动时一次）。
支持三种 action: remove（删除匹配行）、replace（替换为空）、mask（替换为 [MASKED]）。

合并策略：
  1. 加载内置默认规则（core/harness/ontology_engine/cleanup_rules.yaml）
  2. 加载用户自定义规则（~/.aiplat/cleanup_rules.yaml）
  3. 用户规则覆盖同名默认规则；enabled: false 禁用该规则
"""
from __future__ import annotations

import logging
import os
import re
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aiplat.text_cleaner")


class TextCleaner:
    def __init__(self):
        self._rules: List[dict] = []
        self._load_rules()

    def _load_rules(self):
        """Load rules: built-in defaults first, then user overrides."""
        builtin_path = Path(__file__).parent / "cleanup_rules.yaml"
        user_path = Path(os.path.expanduser("~/.aiplat/cleanup_rules.yaml"))

        # Load built-in defaults
        default_rules = {}
        if builtin_path.exists():
            try:
                with open(builtin_path, "r") as f:
                    data = yaml.safe_load(f)
                for rule in data.get("rules", []):
                    name = rule.get("name", "")
                    if not rule.get("enabled", True):
                        continue
                    default_rules[name] = rule
            except Exception as e:
                logger.debug("Failed to load built-in cleanup rules: %s", e)

        # Load user overrides
        user_rules = {}
        if user_path.exists():
            try:
                with open(user_path, "r") as f:
                    data = yaml.safe_load(f)
                for rule in data.get("rules", []):
                    name = rule.get("name", "")
                    if not rule.get("enabled", True):
                        user_rules[name] = rule  # also track disabled user rules
                        continue
                    user_rules[name] = rule
            except Exception as e:
                logger.debug("Failed to load user cleanup rules: %s", e)

        # Merge: user rules override defaults
        merged = dict(default_rules)
        for name, rule in user_rules.items():
            if not rule.get("enabled", True):
                merged.pop(name, None)  # user explicitly disabled
            else:
                merged[name] = rule  # user override

        self._rules = list(merged.values())
        logger.info("TextCleaner: loaded %d rules (%d built-in, %d user)",
                     len(self._rules), len(default_rules), len(user_rules))

    def clean(self, text: str) -> Tuple[str, int]:
        """
        Apply all enabled rules to the text.

        Returns: (cleaned_text, removed_count)
        """
        if not text or not self._rules:
            return text, 0

        removed = 0
        result = text
        for rule in self._rules:
            pattern = rule.get("pattern", "")
            action = rule.get("action", "remove")
            if not pattern:
                continue
            try:
                regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                if action == "mask":
                    result, n = regex.subn("[MASKED]", result)
                else:
                    # remove and replace both remove matching content
                    result, n = regex.subn("", result)
                removed += n
            except re.error as e:
                logger.debug("Invalid regex in rule '%s': %s", rule.get("name"), e)

        # Post-clean: compress multiple blank lines
        result = re.sub(r"\n{3,}", "\n\n", result)
        result = result.strip()
        return result, removed

    def get_stats(self) -> dict:
        return {
            "total_rules": len(self._rules),
            "rules": [
                {"name": r["name"], "action": r.get("action", "remove"),
                 "pattern": r.get("pattern", "")[:60]}
                for r in self._rules
            ],
        }


# ── Global singleton ──

_text_cleaner: Optional[TextCleaner] = None


def get_text_cleaner() -> TextCleaner:
    global _text_cleaner
    if _text_cleaner is None:
        _text_cleaner = TextCleaner()
    return _text_cleaner
