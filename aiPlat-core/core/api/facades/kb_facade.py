"""KB Facade — knowledge base operations (no core_facade dependency)."""
from __future__ import annotations
from typing import Any, Dict, Optional


def kb_retrieve(query: str, doc_ids: Any, **kwargs: Any) -> Any:
    """Retrieve relevant KB document content through the syscall boundary."""
    from core.harness.syscalls.retrieval import sys_kb_retrieve
    return sys_kb_retrieve(query, doc_ids, **kwargs)


def wiki_retrieve(query: str, wiki_titles: list = None, **kwargs: Any) -> Any:
    from core.harness.syscalls.retrieval import sys_wiki_retrieve
    return sys_wiki_retrieve(query, wiki_titles, **kwargs)


def kb_chunk_elements(elements: Any, kind: str = "pdf", target_size: int = 1000, overlap: int = 150) -> Any:
    from core.apps.document_intelligence.chunking import chunk_elements
    return chunk_elements(elements, kind=kind, target_size=target_size, overlap=overlap)


def kb_transcribe_audio(audio_path: str, language: str = "auto", diagnostics: Any = None) -> Any:
    from core.harness.document.transcriber import transcribe_audio
    return transcribe_audio(audio_path, language=language or None, diagnostics=diagnostics)


def kb_transcribe_audio_chunked(audio_path: str, language: str = "auto", chunk_seconds: int = 60) -> Any:
    from core.harness.document.transcriber import transcribe_audio_chunked
    return transcribe_audio_chunked(audio_path, language=language or None, chunk_seconds=chunk_seconds)


def kb_embed_text(text: str, dim: int = 128) -> Any:
    """Embed text into a vector. Safe to call from sync or async context."""
    import asyncio as _asyncio, concurrent.futures as _cf
    from core.harness.knowledge.embedder import embed_text as _embed_async, hash_embed
    try:
        try:
            loop = _asyncio.get_running_loop()
            with _cf.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(_asyncio.run, _embed_async(text, dim)).result(timeout=30)
        except RuntimeError:
            return _asyncio.run(_embed_async(text, dim))
    except Exception:
        return hash_embed(text, dim)


def kb_embed_text_sync(text: str, dim: int = 128) -> Any:
    from core.harness.knowledge.embedder import hash_embed
    return hash_embed(text, dim)


def kb_extract_keywords(text: str) -> Any:
    from core.harness.knowledge.utils import extract_keywords
    return extract_keywords(text)


def kb_classify_document(elements: Any, kind: str) -> Any:
    from core.apps.document_intelligence.classifier import classify_document
    return classify_document(elements, kind)


def kb_element_source(element: Any) -> Any:
    from core.harness.knowledge.utils import element_source
    return element_source(element)


def kb_score_text(text: str, keywords: Any) -> Any:
    from core.harness.knowledge.utils import score_text
    return score_text(text, list(keywords) if keywords else [])


def kb_kind_category(kind: str) -> Any:
    from core.apps.document_intelligence.classifier import kind_category
    return kind_category(kind)


def kb_get_ingest_fn() -> Any:
    from core.apps.document_intelligence.kb_provider import get_ingest_fn
    return get_ingest_fn()


def kb_get_tenant_storage(tenant_id: str) -> Any:
    from core.apps.document_intelligence.kb_provider import get_tenant_storage
    return get_tenant_storage(tenant_id)


def kb_create_infra_db_client(db_path: str) -> Any:
    from core.harness.infrastructure.infra_bridge import create_infra_database_client
    return create_infra_database_client(db_path)


create_infra_database_client = kb_create_infra_db_client


def kb_llm_chat_complete(system_prompt: str, user_prompt: str, temperature: float = 0.1, max_tokens: int = 700) -> Any:
    from core.apps.document_intelligence.llm_client import chat_complete
    return chat_complete(system_prompt=system_prompt, user_prompt=user_prompt, temperature=temperature, max_tokens=max_tokens)


def kb_llm_enabled() -> bool:
    from core.apps.document_intelligence.llm_client import llm_enabled
    return llm_enabled()


async def kb_summarize_document(*, tenant_id: str, collection_id: str, doc_id: str, profile: str = "key_points", **kwargs: Any) -> Any:
    from core.apps.document_intelligence.summarizer import summarize_document
    return await summarize_document(tenant_id=tenant_id, collection_id=collection_id, doc_id=doc_id, profile=profile, **kwargs)


def kb_parse_document(file_path: str, kind: str) -> Any:
    from core.harness.document import parsers
    dispatch = {
        # Office formats → MarkItDown (preserves heading/table/list structure)
        "docx": parsers.parse_markitdown, "word": parsers.parse_markitdown,
        "pptx": parsers.parse_markitdown, "ppt": parsers.parse_markitdown,
        "xlsx": parsers.parse_markitdown, "xls": parsers.parse_markitdown,
        "pdf": parsers.parse_markitdown,
        "html": parsers.parse_html, "htm": parsers.parse_html,
        # Lightweight formats → dedicated parsers
        "csv": parsers.parse_csv,
        "md": parsers.parse_markdown, "markdown": parsers.parse_markdown,
        "json": parsers.parse_json_document,
        "eml": parsers.parse_eml,
        # Media → keep existing pipelines (Whisper/OCR)
        "audio": parsers.parse_audio, "mp3": parsers.parse_audio, "wav": parsers.parse_audio,
        "image": parsers.parse_image, "png": parsers.parse_image, "jpg": parsers.parse_image,
    }
    parser = dispatch.get(str(kind).lower())
    return parser(file_path) if parser else []


def kb_chunk_document(elements: Any, kind: str = "pdf", target_size: int = 1000, overlap: int = 150) -> Any:
    from core.harness.document.chunker import chunk_document
    return chunk_document(elements, kind=kind, target_size=target_size, overlap=overlap)


def get_document_categories() -> list:
    return ["pdf", "docx", "pptx", "xlsx", "html", "txt", "markdown", "image", "audio", "video"]


def set_knowledge_providers(*args: Any, **kwargs: Any) -> None:
    pass


def get_embedding_model_name() -> str:
    """Return the currently configured embedding model name via infra resolution chain."""
    try:
        from core.harness.infrastructure.base_model_adapter import resolve_model_name
        return resolve_model_name("embedding")
    except Exception:
        return "unknown"
