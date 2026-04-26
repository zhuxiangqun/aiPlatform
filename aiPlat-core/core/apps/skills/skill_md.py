"""
SKILL.md 解析工具（统一口径）

目标：
- 提供一个稳定、可复用的 SKILL.md 解析入口，避免 discovery / management / API 各自实现一套解析逻辑
- 支持常见格式：
  1) YAML Front Matter:  ---\\n...\\n---\\n<body>
  2) YAML code block（兼容历史/非标准写法）：```yaml ... ```
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
import re

import yaml


_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", flags=re.DOTALL)
_YAML_BLOCK_RE = re.compile(r"```yaml\s*\n(.*?)```", flags=re.DOTALL | re.IGNORECASE)


@dataclass
class SkillMDParseResult:
    front_matter: Optional[Dict[str, Any]]
    body: str
    format: str  # front_matter | yaml_block | none


def parse_skill_md(content: str) -> SkillMDParseResult:
    """
    解析 SKILL.md 内容，返回 YAML front matter（若存在）与正文 body。
    - 若 YAML 无法解析，front_matter 返回 {}（而不是抛异常）
    - 若找不到 YAML，front_matter 为 None，body 为原文
    """
    raw = content or ""

    # 1) YAML front matter（优先）
    if raw.startswith("---"):
        m = _FRONT_MATTER_RE.match(raw)
        if m:
            yaml_part = m.group(1)
            body = m.group(2) or ""
            fm = _safe_load_yaml_dict(yaml_part)
            return SkillMDParseResult(front_matter=fm, body=body, format="front_matter")

    # 2) YAML fenced code block（兼容）
    m2 = _YAML_BLOCK_RE.search(raw)
    if m2:
        yaml_part = m2.group(1) or ""
        fm = _safe_load_yaml_dict(yaml_part)
        # best-effort SOP：移除 YAML block 后剩余内容
        body = _YAML_BLOCK_RE.sub("", raw).strip()
        return SkillMDParseResult(front_matter=fm, body=body, format="yaml_block")

    return SkillMDParseResult(front_matter=None, body=raw, format="none")


def _safe_load_yaml_dict(yaml_text: str) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(yaml_text) or {}
        if isinstance(data, dict):
            return dict(data)
    except Exception:
        pass
    return {}


def truncate_text(text: str, max_chars: int, *, suffix: str = " …(truncated)") -> Tuple[str, bool]:
    """
    截断文本并返回 (new_text, truncated)。
    max_chars<=0 表示不截断。
    """
    s = str(text or "")
    if max_chars <= 0:
        return s, False
    if len(s) <= max_chars:
        return s, False
    # 预留 suffix 空间
    keep = max(0, max_chars - len(suffix))
    return (s[:keep] + suffix), True

