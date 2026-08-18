"""
CredentialPool — multi-API-key round-robin pool with cooldown.

Architecture: aiPlat-infra (Layer 0) — infrastructure-level, no internal deps.
Provides factory get_credential_pool() → next(provider) for core to consume.

Keys are read from SQLite adapters table — single source of truth.
Encrypted keys (api_key_enc) supported via AIPLAT_SECRET_KEY Fernet.
No env var fallback.

The pool uses round-robin with per-key cooldown to avoid "chain reaction"
rate limits: when a key receives a 429, it's placed in cooldown and skipped
in the next round, preventing a single rate-limited key from blocking all iterations.
"""

from __future__ import annotations
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
import logging


def _is_valid_key(key: str) -> bool:
    """True for a plausible API key; false for placeholder/corrupted/sentinel blobs.

    Rejects:
      - empty / whitespace
      - local scan sentinels (``__local*``)
      - placeholders containing "test" / "validation"
      - corrupted non-``sk-`` blobs (e.g. JSON written into the api_key column)
    """
    k = (key or "").strip()
    if not k:
        return False
    if k.startswith("__local"):
        return False
    if not k.lower().startswith("sk-"):
        return False
    _l = k.lower()
    if "test" in _l or "validation" in _l:
        return False
    return True


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
                f"Register this model via Management UI → 模型管理, or insert into SQLite adapters table."
            )

    @staticmethod
    def _load_keys(provider: str) -> List[str]:
        """Load keys for a provider, deduped and validity-filtered.

        Primary source: SQLite adapters table (management UI — single source of truth).
        Fallback: ``{PROVIDER}_KEYS`` / ``{PROVIDER}_API_KEY`` env vars (comma-separated
        multi-key or single key), used for dev/CI without the management UI.

        Loads ALL valid keys (for round-robin), preferring exact provider match
        over api_base_url LIKE, and filtering placeholder/corrupted blobs.
        """
        keys: List[str] = []
        seen = set()

        # ── Primary: SQLite adapters table ──
        try:
            db_path = os.getenv("AIPLAT_EXECUTION_DB_PATH",
                                os.path.expanduser("~/.aiplat/aiplat_executions.sqlite3"))
            if os.path.isfile(db_path):
                import sqlite3
                conn = sqlite3.connect(db_path, timeout=3.0)
                try:
                    # Exact provider match first, then api_base_url LIKE fallback.
                    # No LIMIT — load every key so the round-robin pool actually rotates.
                    rows = conn.execute(
                        "SELECT api_key, api_key_enc FROM adapters "
                        "WHERE status='active' AND (provider=? OR (api_base_url LIKE ?)) "
                        "AND (api_key IS NOT NULL OR api_key_enc IS NOT NULL) "
                        "ORDER BY (provider=?) DESC",
                        (provider, f"%{provider}%", provider)
                    ).fetchall()
                    for row in rows:
                        key = row[0] or ""
                        if _is_valid_key(key):
                            if key not in seen:
                                seen.add(key)
                                keys.append(key)
                            continue
                        # Try decrypted key
                        enc = row[1] or ""
                        if enc.strip():
                            try:
                                from cryptography.fernet import Fernet
                                secret = os.getenv("AIPLAT_SECRET_KEY", "")
                                if secret:
                                    f = Fernet(secret.encode() if isinstance(secret, str) else secret)
                                    key = f.decrypt(enc.encode() if isinstance(enc, str) else enc).decode()
                                    if _is_valid_key(key) and key not in seen:
                                        seen.add(key)
                                        keys.append(key)
                            except Exception:
                                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
                finally:
                    conn.close()
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        # ── Fallback: env vars ({PROVIDER}_KEYS comma-separated, {PROVIDER}_API_KEY single) ──
        if not keys:
            _up = provider.upper().replace("-", "_")
            env_keys = os.getenv(f"{_up}_KEYS", "") or os.getenv(f"{_up}_API_KEY", "") or ""
            for k in env_keys.split(","):
                k = k.strip()
                if _is_valid_key(k) and k not in seen:
                    seen.add(k)
                    keys.append(k)

        return keys

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
# Bounded by _MAX_POOLS: provider keys come from callers; cap prevents
# arbitrary keys from growing the pool registry.
_MAX_POOLS = 64

_pools: Dict[str, CredentialPool] = {}


def get_credential_pool(provider: str) -> CredentialPool:
    """Get or create a credential pool for a provider (singleton per provider)."""
    key = provider.lower()
    if key not in _pools:
        if len(_pools) >= _MAX_POOLS:
            _pools.pop(next(iter(_pools)), None)
        _pools[key] = CredentialPool(provider)
    return _pools[key]
