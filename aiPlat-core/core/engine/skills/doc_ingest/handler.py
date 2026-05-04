from __future__ import annotations

from typing import Any, Dict

from core.apps.skills.base import BaseSkill
from core.harness.interfaces import SkillConfig, SkillContext, SkillResult


class DocIngestSkill(BaseSkill):
    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        tenant_id = (
            str(params.get("tenant_id") or "").strip()
            or str(getattr(context, "tenant_id", "") or "")
            or str((context.metadata or {}).get("tenant_id") or "")
            or "default"
        )
        collection_id = str(params.get("collection_id") or "").strip() or "default"
        file_path = str(params.get("file_path") or "").strip()
        url = str(params.get("url") or "").strip()
        kind = str(params.get("kind") or "").strip().lower()
        ocr_lang = str(params.get("ocr_lang") or "zh").strip()
        ocr_engine = str(params.get("ocr_engine") or "").strip() or None
        dpi = int(params.get("dpi") or 240)
        max_pages = params.get("max_pages", 60)
        max_pages = int(max_pages) if max_pages is not None else None
        force_reingest = bool(params.get("force_reingest") or False)

        if not file_path and not url:
            return SkillResult(success=False, error="file_path_or_url_required")

        try:
            from core.apps.document_intelligence.service import enqueue_doc_ingest

            out = enqueue_doc_ingest(
                tenant_id=tenant_id,
                collection_id=collection_id,
                file_path=file_path or None,
                url=url or None,
                kind=kind,
                ocr_lang=ocr_lang,
                ocr_engine=ocr_engine,
                dpi=dpi,
                max_pages=max_pages,
                force_reingest=force_reingest,
            )
            return SkillResult(success=True, output=out, metadata={"category": "document"})
        except Exception as e:
            return SkillResult(success=False, error=str(e))


def build_skill(*args, **kwargs):
    cfg = SkillConfig(
        name="doc_ingest",
        description="通用资料导入（本地文件/URL）并解析为统一内容元素（kb_elements），支持异步 job（MVP 先支持 PDF）。",
        input_schema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "collection_id": {"type": "string"},
                "file_path": {"type": "string"},
                "url": {"type": "string"},
                "kind": {"type": "string"},
                "ocr_lang": {"type": "string"},
                "ocr_engine": {"type": "string"},
                "dpi": {"type": "integer"},
                "max_pages": {"type": "integer"},
                "force_reingest": {"type": "boolean"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "collection_id": {"type": "string"},
                "doc_id": {"type": "string"},
                "job_id": {"type": "string"},
            },
        },
        metadata={
            "category": "document",
            "version": "0.1.0",
            "skill_kind": "executable",
            "permissions": ["doc:write"],
            "auto_trigger_allowed": False,
            "requires_approval": True,
        },
    )
    return DocIngestSkill(cfg)
