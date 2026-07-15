"""
SQL Ontology Bridge API (P3: three-layer architecture).
"""

from typing import Any, Dict
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["wiki-ontology-sql"])


@router.get("/mappings", response_model=Dict[str, Any])
async def list_sql_mappings(domain_id: str = "default"):
    """List all ontology classes with SQL data source mappings."""
    from core.harness.knowledge.sql_ontology import get_sql_ontology
    translator = get_sql_ontology(domain_id)
    return {"domain_id": domain_id, "mappings": translator.list_mappings(),
            "total": len(translator.list_mappings())}


@router.post("/query", response_model=Dict[str, Any])
async def query_sql_ontology(
    class_name: str = "",
    domain_id: str = "default",
    columns: str = "",
    filters: str = "",
    limit: int = 100,
):
    """
    Translate an ontology concept query to SQL and execute it.
    
    Example:
      POST /ontology/sql/query
      {
        "class_name": "Customer",
        "domain_id": "sales-domain", 
        "columns": "name,region",
        "filters": "region=华东",
        "limit": 50
      }
    
    Returns: { "sql": "SELECT ...", "concept": "Customer", "results": [...], "count": 0 }
    """
    if not class_name:
        raise HTTPException(status_code=400, detail="class_name is required")

    col_list = [c.strip() for c in columns.split(",") if c.strip()] if columns else None
    filter_dict = {}
    if filters:
        for pair in filters.split(","):
            kv = pair.strip().split("=", 1)
            if len(kv) == 2:
                filter_dict[kv[0].strip()] = kv[1].strip()

    from core.harness.knowledge.sql_ontology import get_sql_ontology
    translator = get_sql_ontology(domain_id)
    result = translator.query(class_name, columns=col_list, filters=filter_dict or None, limit=limit)
    return result


@router.get("/preview", response_model=Dict[str, Any])
async def preview_sql_query(
    class_name: str = "",
    domain_id: str = "default",
    limit: int = 10,
):
    """Preview SQL for a concept query (SELECT * equivalent, no execution)."""
    if not class_name:
        raise HTTPException(status_code=400, detail="class_name is required")
    from core.harness.knowledge.sql_ontology import get_sql_ontology
    translator = get_sql_ontology(domain_id)
    sql = translator.to_select_star(class_name, limit=limit)
    return {"class_name": class_name, "domain_id": domain_id, "sql": sql, "limit": limit}
