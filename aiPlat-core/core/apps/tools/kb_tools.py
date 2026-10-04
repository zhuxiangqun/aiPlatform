"""KB ingest / query as atomic Tools (executable logic; SKILL.md stays declarative)."""

from __future__ import annotations

import logging
from typing import Any, Dict

from ...harness.interfaces import ToolConfig
from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class KBIngestTool(BaseTool):
    """Ingest a document into the knowledge base."""

    def __init__(self) -> None:
        super().__init__(
            ToolConfig(
                name="kb_ingest",
                description="将文档摄入知识库（支持 OCR/分页）；file_path 必填。",
                parameters={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "待摄入文件路径"},
                        "tenant_id": {"type": "string", "description": "租户，默认 default"},
                        "collection_id": {"type": "string", "description": "集合/域，默认 default（可按内容自动分类）"},
                        "kind": {"type": "string", "description": "文档类型，默认 pdf"},
                        "ocr_lang": {"type": "string", "description": "OCR 语言，默认 zh"},
                        "ocr_engine": {"type": "string", "description": "可选 OCR 引擎"},
                        "dpi": {"type": "integer", "description": "OCR DPI，默认 240"},
                        "max_pages": {"type": "integer", "description": "可选最大页数"},
                        "collection_name": {"type": "string", "description": "可选集合显示名"},
                    },
                    "required": ["file_path"],
                },
            )
        )

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
                        logger.debug("execute failed", exc_info=True)

                if content_sample.strip():
                    detected = DomainRouter().classify(content_sample)
                    if detected and detected != collection_id:
                        collection_id = detected
                        params["collection_id"] = detected
                        logger.info("Auto-detected domain '%s' for %s", detected, file_path[:80])
            except Exception:
                logger.debug("execute failed", exc_info=True)

        try:
            from core.apps.document_intelligence.kb_provider import get_kb_enqueue_ingest_fn

            enqueue = get_kb_enqueue_ingest_fn()
            out = enqueue(
                tenant_id=tenant_id,
                collection_id=collection_id,
                file_path=file_path,
                kind=kind,
                ocr_lang=ocr_lang,
                ocr_engine=ocr_engine,
                dpi=dpi,
                max_pages=max_pages,
                name=name,
            )
            return ToolResult(success=True, output=out)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class KBQueryTool(BaseTool):
    """Query the knowledge base for structured answers."""

    def __init__(self) -> None:
        super().__init__(
            ToolConfig(
                name="kb_query",
                description="按问题检索知识库并返回结构化结果；question 必填。",
                parameters={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "查询问题"},
                        "tenant_id": {"type": "string", "description": "租户，默认 default"},
                        "collection_id": {"type": "string", "description": "集合/域，默认 default"},
                        "year": {"type": "integer", "description": "可选年份过滤"},
                        "limit": {"type": "integer", "description": "返回条数，默认 50"},
                    },
                    "required": ["question"],
                },
            )
        )

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
            out = query_fn(
                tenant_id=tenant_id,
                collection_id=collection_id,
                question=question,
                year=year,
                limit=limit,
            )
            return ToolResult(success=True, output=out)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
