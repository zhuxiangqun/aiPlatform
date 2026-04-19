from __future__ import annotations

import os
from typing import Dict, List, Optional

from core.harness.kernel.runtime import get_kernel_runtime

from .base import ExecDriver
from .docker import DockerExecDriver
from .local import LocalExecDriver


_DRIVERS: Dict[str, ExecDriver] = {
    "local": LocalExecDriver(),
    "docker": DockerExecDriver(),
}


async def get_exec_backend() -> str:
    """
    Resolve current exec backend.
    Priority:
    1) Env AIPLAT_EXEC_BACKEND
    2) global_settings(key="exec_backend")
    3) local
    """
    raw = (os.getenv("AIPLAT_EXEC_BACKEND") or "").strip()
    if raw:
        return raw
    try:
        rt = get_kernel_runtime()
        store = getattr(rt, "execution_store", None) if rt else None
        if store is not None:
            s = await store.get_global_setting(key="exec_backend")
            v = (s or {}).get("value") if isinstance(s, dict) else None
            if isinstance(v, dict) and v.get("backend"):
                return str(v.get("backend"))
            if isinstance(v, str) and v:
                return str(v)
    except Exception:
        pass
    return "local"


def get_exec_driver(backend: str) -> ExecDriver:
    return _DRIVERS.get(str(backend or "").strip(), _DRIVERS["local"])


def list_exec_backends() -> List[str]:
    return list(_DRIVERS.keys())


async def healthcheck_backends() -> Dict[str, object]:
    out: Dict[str, object] = {"backends": []}
    for k, drv in _DRIVERS.items():
        try:
            out["backends"].append(await drv.health())
        except Exception:
            out["backends"].append({"driver_id": k, "ok": False})
    return out

