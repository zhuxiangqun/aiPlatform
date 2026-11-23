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
from core.utils.paths import get_aiplat_home, get_aiplat_data_dir
import logging

import hashlib
import json as _json
import os as _os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 为什么：N01 Raw 强制快照按 Core source_type 轴声明矩阵；非 PG/MySQL 等 vendor 全量认证
DATASOURCE_RAW_CONNECTOR_MATRIX: Tuple[str, ...] = ("file", "sql", "api")

# 为什么：N01 residual — SQL vendor 驱动声明轴；oracle 无内置驱动，禁止假绿
DATASOURCE_VENDOR_DRIVER_MATRIX: Tuple[str, ...] = (
    "sqlite",
    "postgresql",
    "mysql",
    "oracle",
)

# vendor → 软依赖探测规格（importlib；非生产连库验收）
_DATASOURCE_VENDOR_DRIVER_SPECS: Dict[str, Dict[str, Any]] = {
    "sqlite": {
        "dialect": "sqlite",
        "status": "soft_probe",
        "required_modules": ("sqlalchemy",),
        "driver_any_of": (),
    },
    "postgresql": {
        "dialect": "postgresql",
        "status": "soft_probe",
        "required_modules": ("sqlalchemy",),
        "driver_any_of": ("psycopg2", "psycopg", "asyncpg"),
    },
    "mysql": {
        "dialect": "mysql",
        "status": "soft_probe",
        "required_modules": ("sqlalchemy",),
        "driver_any_of": ("pymysql",),
    },
    "oracle": {
        "dialect": "oracle",
        "status": "declared_unavailable",
        "required_modules": (),
        "driver_any_of": (),
    },
}


class DataSourceIntegrityError(ValueError):
    """DataSource 内容 hash / 快照契约错误（N01 加深）。"""


def datasource_raw_connector_matrix() -> Dict[str, Any]:
    """返回 N01 Raw 强制快照支持的连接器矩阵（Core ``source_type`` 轴）。

    Returns:
        connectors / snapshot_modes；``certified`` 恒 false。
    """
    return {
        "connectors": list(DATASOURCE_RAW_CONNECTOR_MATRIX),
        "snapshot_modes": {
            "file": "raw_file_bytes",
            "sql": "stable_json_records",
            "api": "stable_json_records",
        },
        "certified": False,
        "n01_full_conformance": False,
        "note": (
            "Core source_type matrix (file/sql/api) with hash-forced snapshots; "
            "not vendor-driver matrix / not N01 certified"
        ),
    }


def require_datasource_raw_connector(source_type: str) -> str:
    """校验 ``source_type`` 属于 Raw 连接器矩阵。

    Args:
        source_type: 数据源类型（file/sql/api）。

    Returns:
        规范化小写类型名。

    Raises:
        DataSourceIntegrityError: 不在矩阵内。
    """
    st = (source_type or "").strip().lower()
    if st not in DATASOURCE_RAW_CONNECTOR_MATRIX:
        raise DataSourceIntegrityError(
            f"snapshot_datasource_bytes unsupported source_type={source_type!r}; "
            f"matrix={list(DATASOURCE_RAW_CONNECTOR_MATRIX)}"
        )
    return st


def _module_available(name: str) -> bool:
    """importlib 探测模块是否可导入（不执行副作用连接）。

    Args:
        name: 模块名（如 sqlalchemy / pymysql）。
    """
    import importlib.util

    return importlib.util.find_spec(name) is not None


def probe_vendor_driver(vendor: str) -> Dict[str, Any]:
    """软依赖探测 SQL vendor 驱动可用性（非生产连库验收）。

    Args:
        vendor: sqlite / postgresql / mysql / oracle。

    Returns:
        vendor / status / available / missing / certified=false。

    Raises:
        DataSourceIntegrityError: vendor 不在声明轴内。
    """
    key = (vendor or "").strip().lower()
    if key not in DATASOURCE_VENDOR_DRIVER_MATRIX:
        raise DataSourceIntegrityError(
            f"probe_vendor_driver unsupported vendor={vendor!r}; "
            f"matrix={list(DATASOURCE_VENDOR_DRIVER_MATRIX)}"
        )
    spec = _DATASOURCE_VENDOR_DRIVER_SPECS[key]
    status = str(spec["status"])
    # 为什么：oracle 无内置驱动路径；声明不可用，禁止因偶然装了 oracledb 而假绿
    if status == "declared_unavailable":
        return {
            "vendor": key,
            "dialect": spec["dialect"],
            "status": "declared_unavailable",
            "available": False,
            "required_modules": list(spec["required_modules"]),
            "driver_any_of": list(spec["driver_any_of"]),
            "missing": ["declared_unavailable"],
            "present": [],
            "certified": False,
            "n01_full_conformance": False,
            "note": "no built-in oracle driver; declared unavailable (not fake-green)",
        }

    missing: List[str] = []
    present: List[str] = []
    for mod in spec["required_modules"]:
        if _module_available(mod):
            present.append(mod)
        else:
            missing.append(mod)
    driver_any = tuple(spec.get("driver_any_of") or ())
    driver_hit = ""
    if driver_any:
        for mod in driver_any:
            if _module_available(mod):
                present.append(mod)
                driver_hit = mod
                break
        if not driver_hit:
            missing.append(f"driver_any_of:{'|'.join(driver_any)}")

    available = not missing
    return {
        "vendor": key,
        "dialect": spec["dialect"],
        "status": "available" if available else "unavailable",
        "available": available,
        "required_modules": list(spec["required_modules"]),
        "driver_any_of": list(driver_any),
        "driver_selected": driver_hit or None,
        "missing": missing,
        "present": present,
        "certified": False,
        "n01_full_conformance": False,
        "note": (
            "soft importlib probe only; not production cluster acceptance / "
            "not N01 certified"
        ),
    }


def datasource_vendor_driver_matrix() -> Dict[str, Any]:
    """返回 N01 SQL vendor 驱动声明矩阵 + 软依赖探测结果。

    Returns:
        vendors / probes；``certified`` / ``n01_full_conformance`` 恒 false。
    """
    probes = {v: probe_vendor_driver(v) for v in DATASOURCE_VENDOR_DRIVER_MATRIX}
    return {
        "vendors": list(DATASOURCE_VENDOR_DRIVER_MATRIX),
        "probes": probes,
        "available_vendors": [
            v for v, p in probes.items() if p.get("available") is True
        ],
        "declared_unavailable": [
            v
            for v, p in probes.items()
            if p.get("status") == "declared_unavailable"
        ],
        "certified": False,
        "n01_full_conformance": False,
        "note": (
            "SQL vendor soft-probe matrix (sqlite/postgresql/mysql; "
            "oracle declared_unavailable); not production acceptance / "
            "not N01 certified"
        ),
    }

@dataclass
class DataSourceConfig:
    """外部数据源配置（YAML）；可选 content_hash 用于 Raw 完整性强制。

    Args:
        name: 显示名。
        source_type: sql | api | file。
        connection: 连接参数。
        mapping: 字段映射。
        content_hash: 期望 sha256（小写 hex）；空表示未声明。
        locator: 可选定位符（URI/路径说明）。
    """

    name: str
    source_type: str  # "sql" | "api" | "file"
    connection: Dict[str, Any] = field(default_factory=dict)
    mapping: Dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    locator: str = ""

    @classmethod
    def from_yaml(cls, path: str) -> DataSourceConfig:
        """从 YAML 加载配置。

        Args:
            path: YAML 文件路径。
        """
        import yaml
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        return cls(
            name=data.get("name", ""),
            source_type=data.get("type", "sql"),
            connection=data.get("connection", {}) or {},
            mapping=data.get("mapping", {}) or {},
            content_hash=str(data.get("content_hash") or data.get("sha256") or "").strip().lower(),
            locator=str(data.get("locator") or "").strip(),
        )


def sha256_bytes(data: bytes) -> str:
    """计算内容 sha256（小写 hex）。

    Args:
        data: 原始字节。
    """
    return hashlib.sha256(data).hexdigest()


def read_file_datasource_bytes(config: DataSourceConfig) -> bytes:
    """读取 file 型 DataSource 的原始文件字节。

    Args:
        config: 须为 source_type=file 且 connection.file_path 存在。

    Returns:
        文件字节。

    Raises:
        DataSourceIntegrityError: 类型不对或文件缺失。
    """
    if (config.source_type or "").strip().lower() != "file":
        raise DataSourceIntegrityError(
            f"read_file_datasource_bytes requires source_type=file, got {config.source_type!r}"
        )
    path = str((config.connection or {}).get("file_path") or "").strip()
    if not path:
        raise DataSourceIntegrityError("file datasource missing connection.file_path")
    p = _Path(path).expanduser()
    if not p.is_file():
        raise DataSourceIntegrityError(f"file datasource path missing: {p}")
    return p.read_bytes()


def validate_datasource_content_hash(
    config: DataSourceConfig,
    content: bytes,
    *,
    require_hash: bool = True,
) -> Dict[str, Any]:
    """校验 DataSourceConfig.content_hash 与内容一致（N01 加深）。

    Args:
        config: 数据源配置。
        content: 待校验字节（file 原文或抓取快照）。
        require_hash: True 时缺 content_hash 即失败（强制路径）。

    Returns:
        回执：ok / expected / actual / name。

    Raises:
        DataSourceIntegrityError: 缺 hash（require 时）或 mismatch。
    """
    expected = str(config.content_hash or "").strip().lower()
    actual = sha256_bytes(content)
    name = config.name or "(unnamed)"
    if not expected:
        if require_hash:
            raise DataSourceIntegrityError(
                f"datasource {name!r} missing content_hash (N01 enforce)"
            )
        return {
            "ok": True,
            "name": name,
            "expected": "",
            "actual": actual,
            "hash_declared": False,
        }
    if expected != actual:
        raise DataSourceIntegrityError(
            f"datasource {name!r} content_hash mismatch: expected={expected} actual={actual}"
        )
    return {
        "ok": True,
        "name": name,
        "expected": expected,
        "actual": actual,
        "hash_declared": True,
    }


def snapshot_datasource_bytes(
    config: DataSourceConfig,
    *,
    records: Optional[List[Dict[str, Any]]] = None,
) -> bytes:
    """生成 DataSource Raw 快照字节（N01 process 接线）。

    file：原始文件字节；sql/api：抓取 records 的稳定 JSON 快照。

    Args:
        config: 数据源配置。
        records: sql/api 必填的抓取结果；file 可省略。

    Returns:
        用于 content_hash 校验与 FactLedger 登记的字节。

    Raises:
        DataSourceIntegrityError: 类型不在矩阵或缺 records。
    """
    st = require_datasource_raw_connector(config.source_type)
    if st == "file":
        return read_file_datasource_bytes(config)
    if records is None:
        raise DataSourceIntegrityError(
            f"datasource {config.name or '(unnamed)'!r} sql/api snapshot requires records"
        )
    # 为什么：稳定序列化，避免键序漂移导致同内容不同 hash
    payload = {
        "name": config.name or "",
        "records": records,
        "source_type": st,
    }
    return _json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def datasource_require_raw_ingest_enabled(
    *,
    explicit: Optional[bool] = None,
) -> bool:
    """是否启用 process_from_datasource → Raw ingest（默认强制；可显式/环境 opt-out）。

    Args:
        explicit: 调用方显式开关；None 时读 ``AIPLAT_DATASOURCE_REQUIRE_RAW_INGEST``
            （缺省 ``1``=强制；``0``/false/off 关闭）。
    """
    if explicit is not None:
        return bool(explicit)
    # 为什么：N01 加深默认强制；无 env 时视为 on，避免静默跳过 Raw
    raw = str(_os.getenv("AIPLAT_DATASOURCE_REQUIRE_RAW_INGEST", "1")).strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return True


class DataSource(ABC):
    """Abstract base for external data sources."""

    def __init__(self, config: DataSourceConfig):
        """初始化。

        Args:
            config: 数据源配置。
        """
        self.config = config

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection. Returns True if successful."""
        ...

    @abstractmethod
    def fetch_all(self, *, limit: int = 1000) -> List[Dict[str, Any]]:
        """Fetch all records from the source.

        Args:
            limit: 返回条数上限。
        """
        ...

    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """Get the source schema (columns, types)."""
        ...


class SQLDataSource(DataSource):
    """SQL database connector (PostgreSQL/MySQL/SQLite)."""

    def connect(self) -> bool:
        """connect。
        """
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
        """fetch_all。

        Args:
            limit: 返回条数上限。
        """
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
        """获取 schema。
        """
        table = self.config.connection.get("table", "")
        return {"type": "sql", "table": table, "connection": self.config.connection.get("driver", "sqlite")}


class APIDataSource(DataSource):
    """REST API data source."""

    def connect(self) -> bool:
        """connect。
        """
        url = self.config.connection.get("base_url", "")
        return bool(url)

    def fetch_all(self, *, limit: int = 1000) -> List[Dict[str, Any]]:
        """fetch_all。

        Args:
            limit: 返回条数上限。
        """
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
        """获取 schema。
        """
        return {"type": "api", "base_url": self.config.connection.get("base_url", "")}


class FileDataSource(DataSource):
    """CSV/JSON/Excel file data source."""

    def connect(self) -> bool:
        """connect。
        """
        path = self.config.connection.get("file_path", "")
        return bool(path) and _Path(path).exists()

    def fetch_all(self, *, limit: int = 1000) -> List[Dict[str, Any]]:
        """fetch_all。

        Args:
            limit: 返回条数上限。
        """
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
        """获取 schema。
        """
        return {"type": "file", "file_path": self.config.connection.get("file_path", "")}


class DataSourceRegistry:
    """Global registry for data sources, loaded from YAML config directory."""

    _sources: Dict[str, DataSource] = {}
    _configs: Dict[str, DataSourceConfig] = {}

    @classmethod
    def load_from_dir(cls, dir_path: str = "") -> int:
        """load_from_dir。

        Args:
            dir_path: dir_path 参数。
        """
        d = _Path(dir_path or _Path(get_aiplat_home()) / "datasources")
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
        """获取 source。

        Args:
            source_id: source 标识。
        """
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
        """列出 sources。
        """
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
        """Map a raw data record to ontology instance properties.

        Args:
            raw_record: raw_record 参数。
            source_id: source 标识。
        """
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
