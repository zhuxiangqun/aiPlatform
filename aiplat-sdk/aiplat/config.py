"""
aiplat.config — SDK 配置管理
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """aiPlat SDK 配置。

    Environment variables:
        AIPLAT_URL: Core API base URL (default: http://localhost:8002)
        AIPLAT_API_KEY: API key for authentication
        AIPLAT_TENANT_ID: Default tenant ID
        AIPLAT_DEFAULT_MODEL: Default model name
    """

    base_url: str = field(default_factory=lambda: os.getenv("AIPLAT_URL", "http://localhost:8002"))
    api_key: str = field(default_factory=lambda: os.getenv("AIPLAT_API_KEY", ""))
    tenant_id: str = field(default_factory=lambda: os.getenv("AIPLAT_TENANT_ID", "default"))
    default_model: str = field(default_factory=lambda: os.getenv("AIPLAT_DEFAULT_MODEL", "qwen2.5-coder:7b"))
    timeout: float = 120.0
    stream_timeout: float = 300.0

    def headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h


# ── Global singleton ──────────────────────────────────────────────────

_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config(config: Config):
    global _config
    _config = config
