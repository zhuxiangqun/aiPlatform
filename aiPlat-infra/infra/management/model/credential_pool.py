"""
CredentialPool — multi-API-key round-robin pool with cooldown.

Architecture: aiPlat-infra (Layer 0) — infrastructure-level, no internal deps.
Provides factory get_credential_pool() → next(provider) for core to consume.

Keys are read from environment variables:
  - Single key:  DEEPSEEK_API_KEY=sk-xxx
  - Multi keys:  DEEPSEEK_KEYS=sk-aaa,sk-bbb,sk-ccc

The pool uses round-robin with per-key cooldown to avoid "chain reaction"
rate limits: when a key receives a 429, it's placed in cooldown and skipped
in the next round, preventing a single rate-limited key from blocking all iterations.

P0: Single-key mode (default). Multi-key requires DEEPSEEK_KEYS env var.
P1+: Vault/AWS Secrets Manager integration.
"""

from __future__ import annotations
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional


# ══════════════════════════════════════════════════════════════
# Data model
# ══════════════════════════════════════════════════════════════

@dataclass
class KeyState:
    """Single API key with cooldown tracking."""
    key: str
    cooldown_until: float = 0.0
    total_requests: int = 0
    total_errors: int = 0


class CredentialPool:
    """Round-robin pool with per-key cooldown.

    Usage:
        pool = CredentialPool("deepseek")
        key = pool.next()          # → "sk-aaa"
        pool.mark_rate_limited(key, retry_after=10)  # put key in cooldown for 10s
        pool.mark_success(key)     # reset cooldown
    """

    def __init__(self, provider: str):
        self.provider = provider
        keys = self._load_keys(provider)
        self._keys: List[KeyState] = []
        self._index = 0

        for k in keys:
            if k.strip():
                self._keys.append(KeyState(key=k.strip()))

        if not self._keys:
            raise RuntimeError(
                f"CredentialPool: no API keys found for provider '{provider}'. "
                f"Set {provider.upper()}_API_KEY or {provider.upper()}_KEYS environment variable."
            )

    @staticmethod
    def _load_keys(provider: str) -> List[str]:
        """Load keys: env var (primary) → SQLite adapters table (fallback).

        Order: {PROVIDER}_KEYS → {PROVIDER}_API_KEY → adapters.api_key
        """
        env_multi = f"{provider.upper()}_KEYS"
        env_single = f"{provider.upper()}_API_KEY"

        multi = os.getenv(env_multi, "").strip()
        if multi:
            return [k.strip() for k in multi.split(",") if k.strip()]

        single = os.getenv(env_single, "").strip()
        if single:
            return [single]

        # Fallback: SQLite adapters table (Management UI registered)
        try:
            db_path = os.getenv("AIPLAT_EXECUTION_DB_PATH",
                                os.path.expanduser("~/.aiplat/data/execution.db"))
            if os.path.isfile(db_path):
                import sqlite3
                conn = sqlite3.connect(db_path, timeout=3.0)
                try:
                    # Match provider by name or openai_compatible with provider base_url
                    rows = conn.execute(
                        "SELECT api_key, api_key_enc FROM adapters "
                        "WHERE status='active' AND (provider=? OR (api_base_url LIKE ?)) "
                        "AND (api_key IS NOT NULL OR api_key_enc IS NOT NULL) "
                        "LIMIT 1",
                        (provider, f"%{provider}%")
                    ).fetchall()
                    for row in rows:
                        key = row[0] or ""
                        if key.strip():
                            return [key.strip()]
                        # Try decrypted key
                        enc = row[1] or ""
                        if enc.strip():
                            try:
                                from cryptography.fernet import Fernet
                                secret = os.getenv("AIPLAT_SECRET_KEY", "")
                                if secret:
                                    f = Fernet(secret.encode() if isinstance(secret, str) else secret)
                                    key = f.decrypt(enc.encode() if isinstance(enc, str) else enc).decode()
                                    if key.strip():
                                        return [key.strip()]
                            except Exception:
                                pass
                finally:
                    conn.close()
        except Exception:
            pass

        return []

    def next(self) -> str:
        """Return the next available key (skips keys in cooldown).

        If all keys are in cooldown, returns the one that will cool down first.
        """
        if len(self._keys) == 1:
            return self._keys[0].key

        now = time.time()
        # Try to find a key not in cooldown, starting from current index
        for _ in range(len(self._keys)):
            ks = self._keys[self._index]
            self._index = (self._index + 1) % len(self._keys)
            if ks.cooldown_until <= now:
                return ks.key

        # All keys in cooldown — return the one that will be ready first
        earliest = min(self._keys, key=lambda ks: ks.cooldown_until)
        return earliest.key

    def mark_rate_limited(self, key: str, retry_after: float = 0.0) -> None:
        """Mark a key as rate-limited. Puts it in cooldown."""
        wait = max(5.0, min(60.0, retry_after or 10.0))  # clamp [5, 60]
        for ks in self._keys:
            if ks.key == key:
                ks.cooldown_until = time.time() + wait
                ks.total_errors += 1
                return

    def mark_success(self, key: str) -> None:
        """Reset cooldown for a key after successful call."""
        for ks in self._keys:
            if ks.key == key:
                ks.cooldown_until = 0.0
                ks.total_requests += 1
                return

    @property
    def key_count(self) -> int:
        return len(self._keys)

    @property
    def available_count(self) -> int:
        now = time.time()
        return sum(1 for ks in self._keys if ks.cooldown_until <= now)

    def status(self) -> Dict[str, object]:
        """Masked pool health for observability (keys are never exposed in full)."""
        now = time.time()
        return {
            "provider": self.provider,
            "key_count": len(self._keys),
            "available_count": self.available_count,
            "keys": [
                {
                    "suffix": ks.key[-4:] if len(ks.key) >= 4 else "****",
                    "in_cooldown": ks.cooldown_until > now,
                    "cooldown_remaining": max(0.0, round(ks.cooldown_until - now, 1)),
                    "total_requests": ks.total_requests,
                    "total_errors": ks.total_errors,
                }
                for ks in self._keys
            ],
        }


# ── Process-wide singleton cache ──

_pools: Dict[str, CredentialPool] = {}


def get_credential_pool(provider: str) -> CredentialPool:
    """Get or create a credential pool for a provider (singleton per provider)."""
    key = provider.lower()
    if key not in _pools:
        _pools[key] = CredentialPool(provider)
    return _pools[key]
