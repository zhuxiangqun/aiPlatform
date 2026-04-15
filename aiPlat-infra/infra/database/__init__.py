from .base import DatabaseClient, ConnectionPool
from .schemas import DatabaseConfig, PoolConfig, SSLConfig, PoolStats
from .factory import create_database_client

__all__ = [
    "DatabaseClient",
    "ConnectionPool",
    "DatabaseConfig",
    "PoolConfig",
    "SSLConfig",
    "PoolStats",
    "create_database_client",
]

try:
    from .postgres import PostgresClient
    from .mysql import MySqlClient
    from .mongodb import MongoClient
    from .sqlite import SqliteClient

    __all__.extend(["PostgresClient", "MySqlClient", "MongoClient", "SqliteClient"])
except ImportError:
    pass
