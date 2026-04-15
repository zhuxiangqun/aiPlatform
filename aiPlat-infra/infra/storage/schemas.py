from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class FileConfig:
    base_path: str = ""
    max_file_size: str = "100MB"
    allowed_extensions: List[str] = field(
        default_factory=lambda: ["pdf", "txt", "json", "csv", "png", "jpg"]
    )


@dataclass
class ObjectConfig:
    type: str = "s3"
    bucket: str = "ai-platform-bucket"
    region: str = "us-east-1"
    access_key: str = ""
    secret_key: str = ""
    endpoint: Optional[str] = None


@dataclass
class TempConfig:
    path: str = "/tmp/ai-platform"
    max_size: str = "1GB"
    cleanup_interval: int = 3600


@dataclass
class StorageConfig:
    type: str = "file"
    file: Optional[FileConfig] = None
    object: Optional[ObjectConfig] = None
    temp: Optional[TempConfig] = None
