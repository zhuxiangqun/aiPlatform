from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime


@dataclass
class FileConfig:
    path: str = "/var/log/ai-platform/infra.log"
    max_size: str = "100MB"
    backup_count: int = 10
    encoding: str = "utf-8"


@dataclass
class StructuredConfig:
    include_trace_id: bool = True
    include_request_id: bool = True
    include_user_id: bool = True
    exclude_fields: List[str] = field(
        default_factory=lambda: ["password", "token", "secret"]
    )


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "json"
    output: List[str] = field(default_factory=lambda: ["console"])
    file: Optional[FileConfig] = None
    structured: Optional[StructuredConfig] = None
    loggers: Dict[str, str] = field(default_factory=dict)


@dataclass
class LogEvent:
    timestamp: datetime
    level: str
    message: str
    logger: str
    trace_id: Optional[str] = None
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    extra: Dict[str, any] = field(default_factory=dict)


@dataclass
class LogRecord:
    level: str
    message: str
    timestamp: datetime
    logger_name: str
    trace_id: Optional[str] = None
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    extra: Dict[str, any] = field(default_factory=dict)
