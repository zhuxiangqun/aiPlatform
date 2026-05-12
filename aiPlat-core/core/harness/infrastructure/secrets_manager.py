"""Secrets Manager — AES-256-GCM encrypted credential storage.

Provides encrypted at-rest storage for API keys and other secrets,
with runtime decryption and audit logging.

Per CLAUDE.md §5.30: called from core/server.py lifespan.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

DEFAULT_KEY_PATH = Path.home() / ".aiplat" / "secrets.key"
DEFAULT_STORE_PATH = Path.home() / ".aiplat" / "secrets.enc"


def _derive_key_path() -> Path:
    return Path(os.getenv("AIPLAT_SECRETS_KEY_PATH", str(DEFAULT_KEY_PATH)))


def _derive_store_path() -> Path:
    return Path(os.getenv("AIPLAT_SECRETS_STORE_PATH", str(DEFAULT_STORE_PATH)))


class SecretsManager:
    """Encrypt/decrypt secrets with AES-256-GCM.

    Key source priority:
    1. AIPLAT_SECRETS_KEY env var (32-byte base64-encoded key)
    2. ~/.aiplat/secrets.key file (auto-generated if missing)
    """

    def __init__(self, key_path: Optional[Path] = None):
        self._store_path = _derive_store_path()
        self._key = self._load_or_create_key(key_path or _derive_key_path())
        self._cache: Dict[str, str] = {}
        self._loaded = False

    def _load_or_create_key(self, key_path: Path) -> bytes:
        env_key = os.getenv("AIPLAT_SECRETS_KEY", "")
        if env_key:
            try:
                return base64.b64decode(env_key)
            except Exception:
                pass
        if key_path.exists():
            return key_path.read_bytes()
        new_key = AESGCM.generate_key(bit_length=256)
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(new_key)
        os.chmod(key_path, 0o600)
        return new_key

    def _load_store(self) -> Dict[str, str]:
        if self._loaded:
            return self._cache
        self._loaded = True
        if not self._store_path.exists():
            return self._cache
        try:
            stored = json.loads(self._store_path.read_text())
            nonce = base64.b64decode(stored.get("_nonce", ""))
            ciphertext = base64.b64decode(stored.get("_data", ""))
            aesgcm = AESGCM(self._key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            self._cache = json.loads(plaintext) if plaintext else {}
        except Exception:
            logger.debug("Failed to load secrets store — starting fresh", exc_info=True)
        return self._cache

    def _save_store(self) -> None:
        aesgcm = AESGCM(self._key)
        nonce = secrets.token_bytes(12)
        plaintext = json.dumps(self._cache, ensure_ascii=False).encode()
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        stored = {
            "_nonce": base64.b64encode(nonce).decode(),
            "_data": base64.b64encode(ciphertext).decode(),
        }
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        self._store_path.write_text(json.dumps(stored, ensure_ascii=False))
        os.chmod(self._store_path, 0o600)

    def get(self, name: str) -> Optional[str]:
        """Get a secret by name. Falls back to env var if not in store."""
        self._load_store()
        if name in self._cache:
            self._audit("access", name)
            return self._cache[name]
        env_val = os.getenv(name)
        if env_val:
            self._audit("access_env", name)
            return env_val
        return None

    def set(self, name: str, value: str) -> None:
        """Store a secret (encrypted at rest)."""
        self._load_store()
        self._cache[name] = value
        self._save_store()
        self._audit("store", name)

    def delete(self, name: str) -> bool:
        """Delete a secret from the store."""
        self._load_store()
        existed = self._cache.pop(name, None) is not None
        if existed:
            self._save_store()
            self._audit("delete", name)
        return existed

    def _audit(self, action: str, name: str) -> None:
        try:
            from core.harness.runtime import get_kernel_runtime
            runtime = get_kernel_runtime()
            store = getattr(runtime, "execution_store", None) if runtime else None
            if store is None:
                return
            import asyncio
            asyncio.create_task(store.add_audit_log(
                action="secret_access",
                kind=f"secret_{action}",
                payload={"secret_name": name, "action": action, "timestamp": time.time()},
            ))
        except Exception:
            pass


_secrets_manager: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    """Get the singleton SecretsManager instance."""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
    return _secrets_manager
