"""schemas：模块接口。"""

import os
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class FileConfig:
    """FileConfig。"""
    base_path: str = ""
    max_file_size: str = "100MB"
    allowed_extensions: List[str] = field(
        default_factory=lambda: ["pdf", "txt", "json", "csv", "png", "jpg"]
    )


@dataclass
class ObjectConfig:
    """ObjectConfig。"""
    type: str = "s3"
    bucket: str = os.getenv("AIPLAT_STORAGE_BUCKET", "")
    region: str = "us-east-1"
    access_key: str = ""
    secret_key: str = ""
    endpoint: Optional[str] = None


@dataclass
class TempConfig:
    """TempConfig。"""
    path: str = os.getenv("AIPLAT_STORAGE_PATH", "")
    max_size: str = "1GB"
    cleanup_interval: int = 3600


@dataclass
class StorageConfig:
    """StorageConfig。"""
    type: str = "file"
    file: Optional[FileConfig] = None
    object: Optional[ObjectConfig] = None
    temp: Optional[TempConfig] = None
