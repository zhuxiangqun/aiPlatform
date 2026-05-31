#!/usr/bin/env python3
"""
MCP Database Query — Agent 通过此工具查询数据库。

协议: JSON-RPC over stdio
支持: SQLite (内置), PostgreSQL (psycopg2), MySQL (pymysql)
"""
import sys, json, os

# ═══ 配置 ═══
DATABASE_URL = os.environ.get("MCP_DB_URL", "sqlite:////tmp/test.db")
READONLY = os.environ.get("MCP_DB_READONLY", "true").lower() in ("1", "true", "yes")
# ═══ ═══ ═══

TOOLS = [
    {
        "name": "db_query",
        "description": "执行 SQL 查询。返回 JSON 数组格式的结果，最多 500 行。",
        "schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SQL 查询语句"}
            },
            "required": ["sql"]
        }
    },
    {
        "name": "db_tables",
        "description": "列出数据库中所有表名。",
        "schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "db_execute",
        "description": "执行 INSERT/UPDATE/DELETE 等写操作。readonly 模式下自动禁用。",
        "schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "INSERT/UPDATE/DELETE 语句"}
            },
            "required": ["sql"]
        }
    },
]


def _get_conn():
    if DATABASE_URL.startswith("sqlite"):
        import sqlite3
        path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"
    elif DATABASE_URL.startswith("postgresql"):
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        return conn, "postgres"
    elif DATABASE_URL.startswith("mysql"):
        import pymysql
        from urllib.parse import urlparse
        u = urlparse(DATABASE_URL)
        conn = pymysql.connect(host=u.hostname, port=u.port or 3306, user=u.username, password=u.password, database=u.path.lstrip("/"))
        return conn, "mysql"
    else:
        raise ValueError(f"Unsupported database URL: {DATABASE_URL}")


def handle_list_tools():
    return {"tools": TOOLS}

def handle_call_tool(name: str, arguments: dict):
    try:
        conn, db_type = _get_conn()
        cur = conn.cursor()

        if name == "db_query":
            sql = arguments.get("sql", "").strip()
            if not sql:
                conn.close()
                return {"content": "Empty SQL", "is_error": True}
            if READONLY and not sql.upper().strip().startswith("SELECT"):
                conn.close()
                return {"content": "Only SELECT allowed in readonly mode", "is_error": True}

            cur.execute(sql)
            if db_type == "sqlite":
                rows = [dict(r) for r in cur.fetchmany(500)]
            else:
                cols = [d[0] for d in cur.description] if cur.description else []
                rows = [dict(zip(cols, r)) for r in cur.fetchmany(500)]
            result = {"rows": rows, "count": len(rows)}

        elif name == "db_tables":
            if db_type == "sqlite":
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                rows = [r["name"] for r in cur.fetchall()]
            elif db_type == "postgres":
                cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
                rows = [r[0] for r in cur.fetchall()]
            elif db_type == "mysql":
                cur.execute("SHOW TABLES")
                rows = [r[0] for r in cur.fetchall()]
            else:
                rows = []
            result = {"tables": rows}

        elif name == "db_execute":
            if READONLY:
                conn.close()
                return {"content": "db_execute not available in readonly mode", "is_error": True}
            sql = arguments.get("sql", "").strip()
            if not sql:
                conn.close()
                return {"content": "Empty SQL", "is_error": True}
            cur.execute(sql)
            conn.commit()
            result = {"affected_rows": cur.rowcount, "status": "executed"}

        else:
            conn.close()
            return {"content": "Unknown tool: " + name, "is_error": True}

        conn.close()
        return {"content": json.dumps(result, ensure_ascii=False, indent=2)}

    except Exception as e:
        return {"content": str(e), "is_error": True}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = req.get("method", "")
        req_id = req.get("id")

        if method == "list_tools":
            resp = handle_list_tools()
        elif method == "call_tool":
            params = req.get("params", {})
            resp = handle_call_tool(params.get("name", ""), params.get("arguments", {}))
        else:
            resp = {"error": "Unknown method: " + method}

        out = {"jsonrpc": "2.0", "id": req_id, "result": resp}
        print(json.dumps(out, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
