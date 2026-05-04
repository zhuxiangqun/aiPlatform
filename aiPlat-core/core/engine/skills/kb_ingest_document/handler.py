from __future__ import annotations

from typing import Any, Dict

from core.apps.skills.base import BaseSkill
from core.harness.interfaces import SkillConfig, SkillContext, SkillResult


class KBIngestDocumentSkill(BaseSkill):
    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        tenant_id = str(params.get("tenant_id") or "").strip() or str(context.tenant_id or "default")
        collection_id = str(params.get("collection_id") or "").strip() or "default"
        file_path = str(params.get("file_path") or "").strip()
        kind = str(params.get("kind") or "pdf").strip()
        ocr_lang = str(params.get("ocr_lang") or "zh").strip()
        ocr_engine = str(params.get("ocr_engine") or "").strip() or None
        dpi = int(params.get("dpi") or 240)
        max_pages = params.get("max_pages", 60)
        max_pages = int(max_pages) if max_pages is not None else None
        name = str(params.get("collection_name") or "").strip()

        if not file_path:
            return SkillResult(success=False, error="file_path_required")

        try:
            from core.apps.multimodal_kb.service import enqueue_ingest

            out = enqueue_ingest(
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
            return SkillResult(success=True, output=out, metadata={"category": "knowledge"})
        except Exception as e:
            return SkillResult(success=False, error=str(e))


def build_skill(*args, **kwargs):
    cfg = SkillConfig(
        name="kb_ingest_document",
        description="多模态知识库入库：PDF/扫描件→渲染→OCR→预算表结构化→写入多租户 SQLite（MVP）。",
        input_schema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "description": "租户ID（多租户隔离）"},
                "collection_id": {"type": "string", "description": "知识库集合ID（默认 default）"},
                "collection_name": {"type": "string", "description": "可选：集合展示名"},
                "file_path": {"type": "string", "description": "待入库文件绝对路径（PDF 优先）"},
                "kind": {"type": "string", "description": "文件类型（默认 pdf）"},
                "ocr_lang": {"type": "string", "description": "OCR 语言（默认 zh）"},
                "ocr_engine": {"type": "string", "description": "paddleocr|tesseract|auto（默认 auto）"},
                "dpi": {"type": "integer", "description": "PDF 渲染 DPI（默认 240）"},
                "max_pages": {"type": "integer", "description": "最多处理页数（默认 60）"},
            },
            "required": ["file_path"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "collection_id": {"type": "string"},
                "doc_id": {"type": "string"},
                "pages": {"type": "integer"},
                "budget_rows": {"type": "integer"},
                "budget_pages": {"type": "array", "items": {"type": "integer"}},
                "assets_dir": {"type": "string"},
            },
        },
        metadata={
            "category": "knowledge",
            "version": "0.1.0",
            "skill_kind": "executable",
            "permissions": ["kb:write"],
            "auto_trigger_allowed": False,
            "requires_approval": True,
        },
    )
    return KBIngestDocumentSkill(cfg)
