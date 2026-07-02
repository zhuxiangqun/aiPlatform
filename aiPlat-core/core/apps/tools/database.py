"""
Database Tool

Provides database query capabilities for agents.
Supports SQLite (built-in), PostgreSQL (asyncpg), and MySQL (aiomysql).
"""

from typing import Any, Dict, List, Optional
import asyncio
import json
import os
import sqlite3
import sys

from ...harness.interfaces import ToolConfig, ToolResult
from .base import BaseTool


class DatabaseTool(BaseTool):
    """Database Tool — Execute SQL queries with safety validation."""

    SUPPORTED_OPERATIONS = ["query", "execute", "schema"]
    SUPPORTED_DB_TYPES = ["postgresql", "mysql", "sqlite"]

    MAX_ROWS = 1000
    DEFAULT_TIMEOUT = 60000  # 60 seconds

    # Dangerous SQL patterns
    DANGEROUS_PATTERNS = [
        (r"\bDROP\s+", "DROP statement"),
        (r"\bTRUNCATE\s+", "TRUNCATE statement"),
        (r"\bDELETE\s+FROM\s+\w+\s*(?!.*\bWHERE\b)", "DELETE without WHERE"),
        (r"\bALTER\s+", "ALTER statement"),
    ]

    WRITE_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "TRUNCATE")

    def __init__(
        self,
        connections: Optional[Dict[str, Dict]] = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_rows: int = MAX_ROWS,
        allow_writes: bool = False,
    ):
        self._connections = connections or {}
        self._timeout = timeout / 1000
        self._max_rows = max_rows
        self._allow_writes = allow_writes or os.getenv("AIPLAT_DB_TOOL_ALLOW_WRITES", "false").lower() in ("1", "true", "yes")

        config = ToolConfig(
            name="database",
            description="执行数据库查询",
            parameters={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "description": "Database operation",
                        "enum": self.SUPPORTED_OPERATIONS,
                        "default": "query"
                    },
                    "connection": {
                        "type": "string",
                        "description": "Connection name or DSN"
                    },
                    "sql": {
                        "type": "string",
                        "description": "SQL statement"
                    }
                },
                "required": ["operation", "sql"]
            },
            metadata={
                "risk_level": "dangerous",
                "risk_weight": 50,
            },
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute database operation"""
        operation = params.get("operation", "query")
        connection_name = params.get("connection", "default")
        sql = params.get("sql", "")

        if not sql:
            return ToolResult(success=False, error="SQL is required")

        # Validate SQL for dangerous patterns
        for pattern, description in self.DANGEROUS_PATTERNS:
            import re
            if re.search(pattern, sql, re.IGNORECASE):
                return ToolResult(success=False, error=f"Dangerous operation blocked: {description}")

        # Write protection gate
        sql_upper = sql.strip().upper()
        is_write = any(sql_upper.startswith(kw) for kw in self.WRITE_KEYWORDS)
        if is_write and not self._allow_writes:
            return ToolResult(
                success=False,
                error="Write operations are disabled. Set AIPLAT_DB_TOOL_ALLOW_WRITES=true to enable."
            )

        # Resolve connection config
        conn_cfg = self._resolve_connection(connection_name)

        try:
            db_type = conn_cfg.get("type", "sqlite")
            if db_type == "sqlite":
                result = await self._execute_sqlite(sql, conn_cfg, operation)
            elif db_type == "postgresql":
                result = await self._execute_postgresql(sql, conn_cfg, operation)
            elif db_type == "mysql":
                result = await self._execute_mysql(sql, conn_cfg, operation)
            else:
                return ToolResult(success=False, error=f"Unsupported db type: {db_type}")

            return result
        except Exception as e:
            return ToolResult(success=False, error=f"Database error: {str(e)[:500]}")

    def _resolve_connection(self, name: str) -> Dict[str, Any]:
        """Resolve connection config from registered connections or env vars."""
        if name in self._connections:
            return self._connections[name]

        # Auto-detect from env vars
        db_url = os.getenv("AIPLAT_DB_URL", "")
        if db_url:
            if db_url.startswith("sqlite:"):
                return {"type": "sqlite", "path": db_url.replace("sqlite:///", "").replace("sqlite:", "")}
            elif "postgres" in db_url:
                return {"type": "postgresql", "dsn": db_url}
            elif "mysql" in db_url:
                return {"type": "mysql", "dsn": db_url}

        # Default: in-memory SQLite
        return {"type": "sqlite", "path": ":memory:"}

    async def _execute_sqlite(self, sql: str, conn_cfg: Dict, operation: str) -> ToolResult:
        """Execute SQL on SQLite database."""
        db_path = conn_cfg.get("path", ":memory:")

        def _run():
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(sql)
                if operation in ("query", "schema"):
                    rows = cursor.fetchmany(self._max_rows)
                    columns = [d[0] for d in cursor.description] if cursor.description else []
                    result_rows = [dict(r) for r in rows]
                    conn.commit()
                    return ToolResult(
                        success=True,
                        data={
                            "columns": columns,
                            "rows": result_rows,
                            "row_count": len(result_rows),
                        },
                    )
                else:
                    conn.commit()
                    return ToolResult(
                        success=True,
                        data={"affected_rows": cursor.rowcount if cursor.rowcount >= 0 else 0},
                    )
            except sqlite3.Error as e:
                return ToolResult(success=False, error=str(e))
            finally:
                conn.close()

        return await asyncio.to_thread(_run)

    async def _execute_postgresql(self, sql: str, conn_cfg: Dict, operation: str) -> ToolResult:
        """Execute SQL on PostgreSQL via asyncpg."""
        try:
            import asyncpg
        except ImportError:
            return ToolResult(success=False, error="PostgreSQL driver not installed. Run: pip install asyncpg")

        dsn = conn_cfg.get("dsn", "")
        if not dsn:
            dsn = "postgresql://localhost:5432/postgres"

        try:
            conn = await asyncio.wait_for(
                asyncpg.connect(dsn, statement_cache_size=0),
                timeout=self._timeout,
            )
            try:
                if operation in ("query", "schema"):
                    rows = await conn.fetch(sql)
                    result_rows = [dict(r) for r in rows[:self._max_rows]]
                    return ToolResult(
                        success=True,
                        data={
                            "columns": list(rows[0].keys()) if rows else [],
                            "rows": result_rows,
                            "row_count": len(result_rows),
                        },
                    )
                else:
                    result = await conn.execute(sql)
                    return ToolResult(
                        success=True,
                        data={"affected_rows": int(result.split()[-1]) if " " in result else 0},
                    )
            finally:
                await conn.close()
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _execute_mysql(self, sql: str, conn_cfg: Dict, operation: str) -> ToolResult:
        """Execute SQL on MySQL via aiomysql."""
        try:
            import aiomysql
        except ImportError:
            return ToolResult(success=False, error="MySQL driver not installed. Run: pip install aiomysql")

        dsn = conn_cfg.get("dsn", "")
        if not dsn:
            host = "localhost"
            port = 3306
            user = "root"
            password = ""
            database = "mysql"
            if dsn:
                try:
                    from urllib.parse import urlparse
                    p = urlparse(dsn) if "://" in dsn else None
                    if p:
                        host = p.hostname or host
                        port = p.port or port
                        user = p.username or user
                        password = p.password or password
                        database = (p.path or "/mysql").lstrip("/")
                except Exception:
                    pass

        try:
            pool = await aiomysql.create_pool(
                host=host, port=port, user=user, password=password, db=database,
                minsize=1, maxsize=1, connect_timeout=self._timeout,
            )
            try:
                async with pool.acquire() as conn:
                    async with conn.cursor(aiomysql.DictCursor) as cursor:
                        await cursor.execute(sql)
                        if operation in ("query", "schema"):
                            rows = await cursor.fetchmany(self._max_rows)
                            return ToolResult(
                                success=True,
                                data={
                                    "columns": list(rows[0].keys()) if rows else [],
                                    "rows": rows,
                                    "row_count": len(rows),
                                },
                            )
                        else:
                            return ToolResult(
                                success=True,
                                data={"affected_rows": cursor.rowcount},
                            )
            finally:
                pool.close()
                await pool.wait_closed()
        except Exception as e:
            return ToolResult(success=False, error=str(e))
