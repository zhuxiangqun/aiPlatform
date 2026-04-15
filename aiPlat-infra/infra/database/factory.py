from typing import Optional
from .schemas import DatabaseConfig
from .base import DatabaseClient


def create(config: Optional[DatabaseConfig] = None) -> DatabaseClient:
    """创建数据库客户端（便捷函数）"""
    return create_database_client(config)


def create_database_client(config: Optional[DatabaseConfig] = None) -> DatabaseClient:
    config = config or DatabaseConfig()

    if config.type == "postgres":
        from .postgres import PostgresClient

        return PostgresClient(config)
    elif config.type == "mysql":
        try:
            from .mysql import MySqlClient

            return MySqlClient(config)
        except ImportError:
            raise ImportError(
                "aiomysql is required for MySQL support. Install with: pip install aiomysql"
            )
    elif config.type == "mongodb":
        try:
            from .mongodb import MongoClient

            return MongoClient(config)
        except ImportError:
            raise ImportError(
                "motor is required for MongoDB support. Install with: pip install motor"
            )
    elif config.type == "sqlite":
        try:
            from .sqlite import SqliteClient

            return SqliteClient(config)
        except ImportError:
            raise ImportError(
                "aiosqlite is required for SQLite support. Install with: pip install aiosqlite"
            )
    else:
        raise ValueError(f"Unknown database type: {config.type}")
