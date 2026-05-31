"""Security facade — secrets and permissions (no core_facade dependency)."""
from __future__ import annotations
from typing import Any, Optional

from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RequestStatus, RuleType
from core.harness.infrastructure.crypto.secretbox import is_configured as is_crypto_configured


def secret_configured(key_id: str = "") -> bool:
    """Check if a secret key is configured."""
    return bool(key_id)


def get_secret(name: str) -> Optional[str]:
    from core.harness.infrastructure.secrets_manager import get_secrets_manager
    return get_secrets_manager().get(name)


def set_secret(name: str, value: str) -> None:
    from core.harness.infrastructure.secrets_manager import get_secrets_manager
    get_secrets_manager().set(name, value)


def get_permission_manager() -> Any:
    from core.apps.tools.permission import get_permission_manager as _get
    return _get()


async def get_exec_backend() -> Any:
    """Get the ExecBackend singleton via DI or direct import."""
    from core.apps.exec_drivers.registry import get_exec_backend as _get
    return await _get()
