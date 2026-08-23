"""L4.5 database schema migration engine (plan-app-factory-l45 §3.3/§3.4/§3.5).

- SchemaExtractor: AST-based model extraction (v1: SQLAlchemy Column + Pydantic
  Field → {table: {column: {type, nullable, primary}}}).
- SchemaDiffAnalyzer: old-vs-new schema diff (added/removed/type_changed tables
  & columns) with destructive classification (removed column/type change/removed
  table = destructive).
- MigrationGenerator: diff → paired up/down DDL (ADD/DROP/ALTER/CREATE TABLE).

Migration SQL is preview-only by default; real DB execution is opt-in via
AIPLAT_DB_EXECUTE (design §3.8).
"""
from __future__ import annotations

import ast
import re
import time
import uuid
from typing import Any, Dict, List

_SQLA_COLUMN_FN = ("Column", "mapped_column")
_PYDANTIC_BASES = ("BaseModel", "pydantic.BaseModel")
_TYPE_MAP = {
    "Integer": "INTEGER", "int": "INTEGER",
    "String": "TEXT", "str": "TEXT",
    "Boolean": "BOOLEAN", "bool": "BOOLEAN",
    "Float": "FLOAT", "float": "FLOAT",
    "DateTime": "DATETIME", "datetime": "DATETIME",
    "Text": "TEXT", "Date": "DATE", "date": "DATE",
    "Numeric": "NUMERIC", "Decimal": "NUMERIC",
}


# ── SchemaExtractor (§3.3) ───────────────────────────────────────────────────

def _snake(name: str) -> str:
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return s


def _find_tablename(node: ast.ClassDef) -> str:
    for stmt in node.body:
        if isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                if isinstance(t, ast.Name) and t.id == "__tablename__":
                    if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                        return stmt.value.value
    return ""


def _is_sqla_model(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id in ("Base", "DeclarativeBase"):
            return True
    return False


def _is_pydantic(node: ast.ClassDef) -> bool:
    for base in node.bases:
        name = base.id if isinstance(base, ast.Name) else (base.attr if isinstance(base, ast.Attribute) else "")
        if name in ("BaseModel", "Model"):
            return True
    return False


def _column_info(stmt: ast.Assign) -> Dict[str, Any]:
    """SQLAlchemy: id = Column(Integer, primary_key=True) / mapped_column(...)."""
    info: Dict[str, Any] = {"type": "TEXT", "nullable": True, "primary": False}
    call = stmt.value
    if not isinstance(call, ast.Call):
        return info
    fn = call.func
    fn_name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
    if fn_name not in _SQLA_COLUMN_FN:
        return info
    # type from first positional arg (or first keyword 'type')
    if call.args:
        arg = call.args[0]
        t = arg.id if isinstance(arg, ast.Name) else (arg.attr if isinstance(arg, ast.Attribute) else "")
        info["type"] = _TYPE_MAP.get(t, "TEXT")
    for kw in call.keywords:
        if kw.arg == "primary_key" and isinstance(kw.value, ast.Constant):
            info["primary"] = bool(kw.value.value)
        if kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
            info["nullable"] = bool(kw.value.value)
    return info


def _pydantic_field(stmt: ast.AnnAssign) -> Dict[str, Any]:
    """Pydantic: id: int  /  name: str = Field(...)."""
    info: Dict[str, Any] = {"type": "TEXT", "nullable": True, "primary": False}
    ann = stmt.annotation
    t = ""
    if isinstance(ann, ast.Name):
        t = ann.id
    elif isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name):
        t = ann.value.id  # Optional[int] / List[str] → base type
    info["type"] = _TYPE_MAP.get(t, "TEXT")
    return info


def extract_schema(code_files: Dict[str, str]) -> Dict[str, Any]:
    """Extract {table: {column: {type, nullable, primary}}} from code files."""
    schema: Dict[str, Dict[str, Any]] = {}
    for rel, content in (code_files or {}).items():
        if not rel.endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if _is_sqla_model(node):
                tablename = _find_tablename(node) or _snake(node.name)
                tbl = schema.setdefault(tablename, {})
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
                        col = _column_info(stmt)
                        if col.get("type") or any(isinstance(a, ast.Call) for a in [stmt.value]):
                            tbl[stmt.targets[0].id] = col
            elif _is_pydantic(node):
                tbl = schema.setdefault(_snake(node.name), {})
                for stmt in node.body:
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                        tbl[stmt.target.id] = _pydantic_field(stmt)
    return schema


# ── SchemaDiffAnalyzer (§3.4) ────────────────────────────────────────────────

def diff_schema(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """Old-vs-new schema diff with destructive classification."""
    old_tables = set(old.keys())
    new_tables = set(new.keys())
    added_tables = sorted(new_tables - old_tables)
    removed_tables = sorted(old_tables - new_tables)
    added_columns: Dict[str, List[str]] = {}
    removed_columns: Dict[str, List[str]] = {}
    type_changed: Dict[str, Dict[str, tuple]] = {}

    for t in sorted(old_tables & new_tables):
        old_cols = old.get(t, {})
        new_cols = new.get(t, {})
        for c in new_cols:
            if c not in old_cols:
                added_columns.setdefault(t, []).append(c)
        for c in old_cols:
            if c not in new_cols:
                removed_columns.setdefault(t, []).append(c)
        for c in set(old_cols) & set(new_cols):
            otype = (old_cols[c] or {}).get("type")
            ntype = (new_cols[c] or {}).get("type")
            if otype and ntype and otype != ntype:
                type_changed.setdefault(t, {})[c] = (otype, ntype)

    destructive = bool(removed_columns or type_changed or removed_tables)
    return {
        "added_tables": added_tables,
        "removed_tables": removed_tables,
        "added_columns": added_columns,
        "removed_columns": removed_columns,
        "type_changed": type_changed,
        "destructive": destructive,
        "has_changes": bool(added_tables or removed_tables or added_columns
                            or removed_columns or type_changed),
    }


# ── MigrationGenerator (§3.5) ────────────────────────────────────────────────

def _column_ddl(tbl_schema: Dict[str, Any], col: str) -> str:
    info = tbl_schema.get(col) or {}
    parts = [col, info.get("type", "TEXT")]
    if info.get("primary"):
        parts.append("PRIMARY KEY")
    elif info.get("nullable") is False:
        parts.append("NOT NULL")
    return " ".join(parts)


def generate_migration(diff: Dict[str, Any], project_id: str,
                       new_schema: Dict[str, Any], module_id: str = "default") -> Dict[str, Any]:
    """diff → {id, up_sql, down_sql, destructive, created_at, module_id}. None if no changes."""
    if not diff.get("has_changes"):
        return None
    up: List[str] = []
    down: List[str] = []
    for t in diff.get("added_tables", []):
        cols = new_schema.get(t, {})
        if cols:
            col_sql = ", ".join(_column_ddl(cols, c) for c in cols)
            up.append(f"CREATE TABLE {t} ({col_sql});")
            down.append(f"DROP TABLE {t};")
    for t in diff.get("removed_tables", []):
        up.append(f"DROP TABLE {t};")
        down.append(f"CREATE TABLE {t} ();")  # placeholder — schema unknown for down
    for t, cols in (diff.get("added_columns") or {}).items():
        for c in cols:
            col_sql = _column_ddl((new_schema.get(t) or {}), c)
            up.append(f"ALTER TABLE {t} ADD COLUMN {col_sql};")
            down.append(f"ALTER TABLE {t} DROP COLUMN {c};")
    for t, cols in (diff.get("removed_columns") or {}).items():
        for c in cols:
            up.append(f"ALTER TABLE {t} DROP COLUMN {c};")
            down.append(f"ALTER TABLE {t} ADD COLUMN {c} TEXT;")  # best-effort restore
    for t, changes in (diff.get("type_changed") or {}).items():
        for c, (old_t, new_t) in changes.items():
            up.append(f"ALTER TABLE {t} ALTER COLUMN {c} TYPE {new_t};")
            down.append(f"ALTER TABLE {t} ALTER COLUMN {c} TYPE {old_t};")
    return {
        "id": f"mig_{uuid.uuid4().hex[:8]}",
        "project_id": project_id,
        "module_id": module_id,
        "up_sql": "\n".join(up),
        "down_sql": "\n".join(down) or "-- no-op (schema unknown for restore)",
        "destructive": bool(diff.get("destructive")),
        "summary": {
            "added_tables": diff.get("added_tables", []),
            "removed_tables": diff.get("removed_tables", []),
            "added_columns": diff.get("added_columns", {}),
            "removed_columns": diff.get("removed_columns", {}),
            "type_changed": diff.get("type_changed", {}),
        },
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "pending",
    }
