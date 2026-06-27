"""
External Data Source Connector — Palantir-style multi-source data integration.

Provides an abstraction layer for connecting external data sources (SQL, API, files)
and mapping raw data to ontology instances without moving data into the system.

Architecture:
  DataSource(ABC)
    ├── SQLDataSource     → PostgreSQL/MySQL/SQLite
    ├── APIDataSource     → REST/GraphQL APIs
    └── FileDataSource    → CSV/JSON/Excel files

  DataSourceRegistry
    └── YAML config at ~/.aiplat/datasources/{name}.yaml
"""

from __future__ import annotations
import logging

import json as _json
import os as _os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional


@dataclass
class DataSourceConfig:
    name: str
    source_type: str  # "sql" | "api" | "file"
    connection: Dict[str, Any] = field(default_factory=dict)
    mapping: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str) -> DataSourceConfig:
        import yaml
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls(
            name=data.get("name", ""),
            source_type=data.get("type", "sql"),
            connection=data.get("connection", {}),
            mapping=data.get("mapping", {}),
        )


class DataSource(ABC):
    """Abstract base for external data sources."""

    def __init__(self, config: DataSourceConfig):
        self.config = config

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection. Returns True if successful."""
        ...

    @abstractmethod
    def fetch_all(self, *, limit: int = 1000) -> List[Dict[str, Any]]:
        """Fetch all records from the source."""
        ...

    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """Get the source schema (columns, types)."""
        ...


class SQLDataSource(DataSource):
    """SQL database connector (PostgreSQL/MySQL/SQLite)."""

    def connect(self) -> bool:
        try:
            from sqlalchemy import create_engine, text as _text
            conn_str = self.config.connection.get("connection_string", "")
            if not conn_str:
                driver = self.config.connection.get("driver", "sqlite")
                host = self.config.connection.get("host", "localhost")
                port = self.config.connection.get("port", 5432)
                db = self.config.connection.get("database", "")
                user = self.config.connection.get("user", "")
                pwd = self.config.connection.get("password", "")
                if driver == "sqlite":
                    conn_str = f"sqlite:///{db}"
                elif driver == "postgresql":
                    conn_str = f"postgresql://{user}:{pwd}@{host}:{port}/{db}"
                elif driver == "mysql":
                    conn_str = f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}"
            self._engine = create_engine(conn_str, echo=False)
            # Test query
            with self._engine.connect() as c:
                c.execute(_text("SELECT 1"))
            return True
        except Exception:
            return False

    def fetch_all(self, *, limit: int = 1000) -> List[Dict[str, Any]]:
        table = self.config.connection.get("table", "")
        if not table:
            return []
        try:
            from sqlalchemy import text as _text
            query = self.config.mapping.get("query") or f"SELECT * FROM {table} LIMIT {limit}"
            with self._engine.connect() as conn:
                result = conn.execute(_text(query))
                columns = list(result.keys())
                return [{columns[i]: val for i, val in enumerate(row)} for row in result.fetchall()]
        except Exception:
            return []

    def get_schema(self) -> Dict[str, Any]:
        table = self.config.connection.get("table", "")
        return {"type": "sql", "table": table, "connection": self.config.connection.get("driver", "sqlite")}


class APIDataSource(DataSource):
    """REST API data source."""

    def connect(self) -> bool:
        url = self.config.connection.get("base_url", "")
        return bool(url)

    def fetch_all(self, *, limit: int = 1000) -> List[Dict[str, Any]]:
        import urllib.request
        url = self.config.connection.get("base_url", "")
        endpoint = self.config.connection.get("endpoint", "")
        auth = self.config.connection.get("auth_header", "")
        full_url = f"{url.rstrip('/')}/{endpoint.lstrip('/')}?limit={limit}"
        try:
            req = urllib.request.Request(full_url)
            if auth:
                req.add_header("Authorization", auth)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read())
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    items = data.get("items", data.get("data", data.get("results", [])))
                    return items if isinstance(items, list) else [data]
            return []
        except Exception:
            return []

    def get_schema(self) -> Dict[str, Any]:
        return {"type": "api", "base_url": self.config.connection.get("base_url", "")}


class FileDataSource(DataSource):
    """CSV/JSON/Excel file data source."""

    def connect(self) -> bool:
        path = self.config.connection.get("file_path", "")
        return bool(path) and _Path(path).exists()

    def fetch_all(self, *, limit: int = 1000) -> List[Dict[str, Any]]:
        path = self.config.connection.get("file_path", "")
        fmt = self.config.connection.get("format", "csv")
        try:
            if fmt == "csv":
                import csv
                with open(path, newline="") as f:
                    reader = csv.DictReader(f)
                    return list(reader)[:limit]
            elif fmt == "json":
                data = _json.loads(_Path(path).read_text())
                if isinstance(data, list):
                    return data[:limit]
                return [data] if isinstance(data, dict) else []
            elif fmt == "excel":
                try:
                    import pandas as pd
                    df = pd.read_excel(path)
                    return df.to_dict(orient="records")[:limit]
                except ImportError:
                    return []
        except Exception:
            return []

    def get_schema(self) -> Dict[str, Any]:
        return {"type": "file", "file_path": self.config.connection.get("file_path", "")}


class DataSourceRegistry:
    """Global registry for data sources, loaded from YAML config directory."""

    _sources: Dict[str, DataSource] = {}
    _configs: Dict[str, DataSourceConfig] = {}

    @classmethod
    def load_from_dir(cls, dir_path: str = "") -> int:
        d = _Path(dir_path or _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "datasources")
        if not d.exists():
            return 0
        count = 0
        for f in d.glob("*.yaml"):
            try:
                config = DataSourceConfig.from_yaml(str(f))
                cls._configs[f.stem] = config
                count += 1
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        return count

    @classmethod
    def get_source(cls, source_id: str) -> Optional[DataSource]:
        if source_id in cls._sources:
            return cls._sources[source_id]
        config = cls._configs.get(source_id)
        if not config:
            return None
        ds = cls._create_source(config)
        if ds and ds.connect():
            cls._sources[source_id] = ds
            return ds
        return None

    @classmethod
    def list_sources(cls) -> List[Dict[str, Any]]:
        return [
            {"id": sid, "name": c.name, "type": c.source_type, "connected": sid in cls._sources}
            for sid, c in cls._configs.items()
        ]

    @classmethod
    def _create_source(cls, config: DataSourceConfig) -> Optional[DataSource]:
        if config.source_type == "sql":
            return SQLDataSource(config)
        elif config.source_type == "api":
            return APIDataSource(config)
        elif config.source_type == "file":
            return FileDataSource(config)
        return None

    @classmethod
    def map_to_ontology(
        cls,
        raw_record: Dict[str, Any],
        source_id: str,
    ) -> Dict[str, Any]:
        """Map a raw data record to ontology instance properties."""
        config = cls._configs.get(source_id)
        if not config:
            return raw_record

        mapping = config.mapping
        target_class = mapping.get("target_class", "")
        field_map = mapping.get("field_mapping", [])

        properties = {}
        for fm in field_map:
            src_field = fm.get("source", "")
            tgt_field = fm.get("target", "")
            if src_field in raw_record:
                properties[tgt_field] = raw_record[src_field]

        return {
            "class_name": target_class,
            "entity_text": properties.get("name", properties.get("id", str(raw_record.get(list(raw_record.keys())[0], ""))[:40])),
            "properties": properties,
            "source_id": source_id,
            "source_type": config.source_type,
        }
