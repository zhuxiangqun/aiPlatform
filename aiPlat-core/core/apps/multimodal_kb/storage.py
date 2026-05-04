from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TenantStorage:
    tenant_id: str
    root_dir: str

    @property
    def db_path(self) -> str:
        return str(Path(self.root_dir) / "kb.sqlite3")

    @property
    def assets_dir(self) -> str:
        return str(Path(self.root_dir) / "assets")

    @property
    def uploads_dir(self) -> str:
        """
        上传/下载暂存目录（platform 与 core 共用）。
        结构：
          <tenant_root>/uploads/...
        """
        return str(Path(self.root_dir) / "uploads")


def get_aiplat_home() -> Path:
    """
    统一的 aiplat home：
    - 默认 ~/.aiplat
    - 可通过 AIPLAT_HOME 覆盖
    """
    env = (os.getenv("AIPLAT_HOME", "") or "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".aiplat"


def get_tenant_storage(tenant_id: str) -> TenantStorage:
    """
    多租户隔离：每个 tenant 一个目录。
    结构：
      ~/.aiplat/kb/tenants/<tenant_id>/
        kb.sqlite3
        assets/...
    """
    tid = str(tenant_id or "").strip() or "default"
    base = get_aiplat_home() / "kb" / "tenants" / tid
    base.mkdir(parents=True, exist_ok=True)
    (base / "assets").mkdir(parents=True, exist_ok=True)
    (base / "uploads").mkdir(parents=True, exist_ok=True)
    return TenantStorage(tenant_id=tid, root_dir=str(base))
