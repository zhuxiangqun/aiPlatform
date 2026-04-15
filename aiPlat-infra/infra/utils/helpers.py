"""
Helpers - 通用辅助函数

文档位置：docs/utils/index.md
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs


def now_utc() -> datetime:
    """获取当前UTC时间"""
    return datetime.now(timezone.utc)


def format_timestamp(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化时间戳"""
    return dt.strftime(fmt)


def parse_timestamp(ts: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> datetime:
    """解析时间戳"""
    return datetime.strptime(ts, fmt)


def safe_json_loads(data: str, default: Any = None) -> Any:
    """安全的 JSON 解析"""
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return default


def safe_json_dumps(obj: Any, default: str = "{}") -> str:
    """安全的 JSON 序列化"""
    try:
        return json.dumps(obj)
    except (TypeError, ValueError):
        return default


def parse_url(url: str) -> Dict[str, Optional[str]]:
    """解析URL"""
    parsed = urlparse(url)
    return {
        "scheme": parsed.scheme,
        "netloc": parsed.netloc,
        "path": parsed.path,
        "params": parsed.params,
        "query": dict(parse_qs(parsed.query)),
        "fragment": parsed.fragment,
    }


def truncate(text: str, max_length: int, suffix: str = "...") -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def deep_merge(base: Dict, override: Dict) -> Dict:
    """深度合并字典"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
