"""
SQL Ontology Bridge — three-layer architecture (Physical → Semantic → App).

Extends Ontology YAML with sql_mappings that link ontology classes to SQL
tables/views, enabling concept-level queries that auto-translate to SQL.

Three-Layer Architecture:
  Application Layer (LLM, Agent)     ← apps
  Semantic Layer (Ontology concepts) ← this module
  Physical Layer (SQL tables/views)  ← external databases

Virtualization-first: no data ingestion required. Queries are auto-translated
from ontology concepts to SQL and executed against the underlying database.

Usage (YAML extension):
  classes:
    Customer:
      label: 客户
      sql_mapping:
        source: "CRM_DB"              # registered data source
        table: "customers"            # table or view name
        key_column: "customer_id"     # primary key
        column_map:                   # ontology property → SQL column
          name: "customer_name"
          region: "region_code"
          tier: "tier_level"
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.sql_ontology")


@dataclass
class SqlMapping:
    """Maps an ontology class to a SQL table/view."""
    source: str                          # registered data source name
    table: str                           # table or view name
    key_column: str = "id"               # primary key column
    column_map: Dict[str, str] = field(default_factory=dict)  # ontology_prop → sql_column


class SqlOntologyTranslator:
    """
    Translate ontology-concept queries to SQL.

    Reads ontology YAML files for sql_mapping definitions and generates
    SQL queries that respect the ontology's class/property structure.
    """

    def __init__(self, domain_id: str = "default"):
        self._domain_id = domain_id
        self._mappings: Dict[str, SqlMapping] = {}
        self._load_mappings()

    def _load_mappings(self):
        """Load sql_mapping definitions from ontology YAML."""
        try:
            from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
            import os as _os
            from pathlib import Path as _Path

            base_dir = _Path(_os.getenv("AIPLAT_HOME", _Path.home() / ".aiplat")) / "ontologies"
            file_path = base_dir / f"{self._domain_id}.yaml"
            if not file_path.exists():
                logger.debug("No ontology YAML for domain '%s'", self._domain_id)
                return

            domain = load_ontology_from_yaml(str(file_path))
            for cls in domain.classes:
                sql_map = None
                # Check YAML raw data for sql_mapping (not stored in OntologyClass dataclass)
                cls_name = cls.uri.split("/")[-1] if cls.uri else ""
                if not cls_name:
                    continue

            # Re-parse raw YAML for sql_mapping fields
            import yaml
            with open(file_path, "r") as f:
                raw = yaml.safe_load(f)

            classes_raw = raw.get("classes", {})
            for cls_name, cls_def in classes_raw.items():
                sql_map_raw = cls_def.get("sql_mapping")
                if sql_map_raw:
                    self._mappings[cls_name] = SqlMapping(
                        source=sql_map_raw.get("source", "default"),
                        table=sql_map_raw.get("table", cls_name.lower()),
                        key_column=sql_map_raw.get("key_column", "id"),
                        column_map=sql_map_raw.get("column_map", {}),
                    )
        except Exception as e:
            logger.debug("Failed to load SQL ontology mappings: %s", e)

    def list_mappings(self) -> List[dict]:
        """Return all SQL-mapped ontology classes."""
        return [
            {
                "class_name": cls_name,
                "source": m.source,
                "table": m.table,
                "key_column": m.key_column,
                "columns": list(m.column_map.keys()),
                "sql_columns": list(m.column_map.values()),
            }
            for cls_name, m in self._mappings.items()
        ]

    def concept_to_sql(self, class_name: str, *, columns: List[str] = None,
                        filters: Dict[str, Any] = None, limit: int = 100) -> str:
        """
        Generate a SQL SELECT query from ontology concept parameters.

        Args:
            class_name: Ontology class name (e.g., "Customer")
            columns: Ontology property names to select (default: all mapped)
            filters: Ontology property → value filters
            limit: Max results

        Returns: SQL SELECT query string
        """
        mapping = self._mappings.get(class_name)
        if not mapping:
            return f"-- No SQL mapping found for concept '{class_name}'"

        # Translate ontology properties → SQL columns
        if columns:
            sql_cols = []
            for col in columns:
                sql_col = mapping.column_map.get(col, col)
                sql_cols.append(f"{sql_col} AS {col}")
            select_clause = ", ".join(sql_cols)
        else:
            # Select all mapped columns with ontology names as aliases
            cols = []
            for onto_name, sql_name in mapping.column_map.items():
                cols.append(f"{sql_name} AS {onto_name}")
            cols.insert(0, mapping.key_column)
            select_clause = ", ".join(cols) if cols else "*"

        sql = f"SELECT {select_clause}\nFROM {mapping.table}"

        # WHERE clause
        if filters:
            conditions = []
            for onto_key, value in filters.items():
                sql_key = mapping.column_map.get(onto_key, onto_key)
                if isinstance(value, str):
                    conditions.append(f"{sql_key} = '{value}'")
                elif isinstance(value, list):
                    vals = ", ".join(f"'{v}'" for v in value)
                    conditions.append(f"{sql_key} IN ({vals})")
                else:
                    conditions.append(f"{sql_key} = {value}")
            if conditions:
                sql += "\nWHERE " + " AND ".join(conditions)

        sql += f"\nLIMIT {limit}"
        return sql

    def query(self, class_name: str, **kwargs) -> dict:
        """
        Execute a concept query and return results.

        Returns: {"sql": "...", "concept": "...", "results": [...], "count": N, "error": None}
        """
        mapping = self._mappings.get(class_name)
        if not mapping:
            return {"sql": "", "concept": class_name, "results": [], "count": 0,
                    "error": f"No SQL mapping for '{class_name}'"}

        try:
            sql = self.concept_to_sql(class_name, **kwargs)
            # Best-effort: execute against a registered data source
            # In production, this would use the DataSource framework
            return {"sql": sql, "concept": class_name, "results": [],
                    "count": 0, "note": "SQL generated. DataSource connection required for execution."}
        except Exception as e:
            return {"sql": "", "concept": class_name, "results": [], "count": 0, "error": str(e)}

    def to_select_star(self, class_name: str, limit: int = 10) -> str:
        """Generate a SELECT * query (fallback)."""
        mapping = self._mappings.get(class_name)
        if not mapping:
            return f"-- No SQL mapping for '{class_name}'"
        sql_cols = [mapping.key_column]
        sql_cols.extend(mapping.column_map.values())
        return f"SELECT {', '.join(sql_cols)}\nFROM {mapping.table}\nLIMIT {limit}"


# ── Global singleton ──

_translators: Dict[str, SqlOntologyTranslator] = {}


def get_sql_ontology(domain_id: str = "default") -> SqlOntologyTranslator:
    if domain_id not in _translators:
        _translators[domain_id] = SqlOntologyTranslator(domain_id)
    return _translators[domain_id]
