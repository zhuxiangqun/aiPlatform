"""
KB Tools — knowledge base operations exposed as atomic Tools.

Converted from engine/skills/knowledge_ingest/handler.py and
engine/skills/knowledge_query/handler.py (per Skill unification —
all Skills are now pure declarative SKILL.md; executable logic
lives in Tools per §5.10 boundary rules).
"""

from __future__ import annotations

from typing import Any, Dict

from .base import BaseTool, ToolResult


class KBIngestTool(BaseTool):
    """Ingest a document into the knowledge base."""

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        tenant_id = str(params.get("tenant_id") or "").strip() or "default"
        collection_id = str(params.get("collection_id") or "").strip() or "default"
        file_path = str(params.get("file_path") or "").strip()
        kind = str(params.get("kind") or "pdf").strip()
        ocr_lang = str(params.get("ocr_lang") or "zh").strip()
        ocr_engine = str(params.get("ocr_engine") or "").strip() or None
        dpi = int(params.get("dpi") or 240)
        max_pages = params.get("max_pages")
        max_pages = int(max_pages) if max_pages is not None else None
        name = str(params.get("collection_name") or "").strip()

        if not file_path:
            return ToolResult(success=False, error="file_path_required")

        # Auto-detect domain for ingested document (HMESI Step 2: knowledge auto-classification)
        if collection_id == "default":
            try:
                import os as _os_ingest
                from core.harness.knowledge.domain_router import DomainRouter

                content_sample = ""
                if _os_ingest.isfile(file_path):
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as _f:
                            content_sample = _f.read(2000)
                    except Exception:
                        pass

                if content_sample.strip():
                    detected = DomainRouter().classify(content_sample)
                    if detected and detected != collection_id:
                        collection_id = detected
                        params["collection_id"] = detected
                        __import__("logging").getLogger(__name__).info(
                            "Auto-detected domain '%s' for %s", detected, file_path[:80]
                        )
            except Exception:
                pass

        try:
            from core.apps.document_intelligence.kb_provider import get_kb_enqueue_ingest_fn
            enqueue = get_kb_enqueue_ingest_fn()
            out = enqueue(
                tenant_id=tenant_id, collection_id=collection_id,
                file_path=file_path, kind=kind, ocr_lang=ocr_lang,
                ocr_engine=ocr_engine, dpi=dpi, max_pages=max_pages, name=name,
            )
            return ToolResult(success=True, output=out)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class KBQueryTool(BaseTool):
    """Query the knowledge base for structured answers."""

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        tenant_id = str(params.get("tenant_id") or "").strip() or "default"
        collection_id = str(params.get("collection_id") or "").strip() or "default"
        question = str(params.get("question") or "").strip()
        year = params.get("year")
        year = int(year) if year is not None and str(year).strip() else None
        limit = int(params.get("limit") or 50)

        if not question:
            return ToolResult(success=False, error="question_required")

        try:
            from core.apps.document_intelligence.kb_provider import get_kb_query_fn
            query_fn = get_kb_query_fn()
            out = query_fn(tenant_id=tenant_id, collection_id=collection_id,
                           question=question, year=year, limit=limit)
            return ToolResult(success=True, output=out)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
