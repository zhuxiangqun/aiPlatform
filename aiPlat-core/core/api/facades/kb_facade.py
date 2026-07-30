"""KB Facade — knowledge base operations (no core_facade dependency)."""

from __future__ import annotations

from typing import Any, Dict, Optional

import logging




def kb_retrieve(query: str, doc_ids: Any, tenant_id: Optional[str] = None, **kwargs: Any) -> Any:

    """Retrieve relevant KB document content through the syscall boundary.

    

    Args:

        tenant_id: Required for multi-tenant data isolation (§5.62). 

                   If not provided, the syscall boundary will enforce tenant isolation

                   based on the current execution context.

    """

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





# Kind normalisation map (kind strings → canonical extensions for registry lookup)

_KIND_TO_EXT = {

    "docx": ".docx", "word": ".docx",

    "pptx": ".pptx", "ppt": ".pptx",

    "xlsx": ".xlsx", "xls": ".xlsx",

    "pdf": ".pdf",

    "html": ".html", "htm": ".html",

    "csv": ".csv",

    "md": ".md", "markdown": ".md",

    "json": ".json",

    "eml": ".eml",

    "audio": ".mp3", "mp3": ".mp3", "wav": ".wav", "m4a": ".m4a",

    "image": ".png", "png": ".png", "jpg": ".jpg", "jpeg": ".jpeg",

    "txt": ".txt", "text": ".txt", "plain": ".txt",

    "video": ".mp4", "mp4": ".mp4",

}



# Canonical kind names (synonym → canonical)

_KIND_CANONICAL = {

    "word": "docx", "doc": "docx", "docx": "docx",

    "ppt": "pptx", "pptx": "pptx",

    "xls": "xlsx", "xlsx": "xlsx",

    "pdf": "pdf",

    "html": "html", "htm": "html",

    "csv": "csv",

    "md": "markdown", "markdown": "markdown",

    "json": "json",

    "eml": "eml",

    "mp3": "audio", "wav": "audio", "m4a": "audio", "ogg": "audio",

    "flac": "audio", "aac": "audio", "opus": "audio", "wma": "audio",

    "audio": "audio",

    "png": "image", "jpg": "image", "jpeg": "image", "bmp": "image",

    "tiff": "image", "tif": "image", "webp": "image",

    "image": "image",

    "txt": "txt", "text": "txt", "plain": "txt",

    "mp4": "video", "mov": "video", "mkv": "video", "avi": "video",

    "webm": "video", "m4v": "video",

    "video": "video",

}





def normalize_kind(kind: str) -> str:

    """Normalize a document kind string to its canonical form."""

    return _KIND_CANONICAL.get(str(kind).lower(), str(kind).lower())





def kb_parse_document(file_path: str, kind: str) -> Any:

    """Parse a document file via the ConverterRegistry with full fallback chain.

    

    Uses convert_with_fallback() — tries all accepting converters in priority order.

    Each failure is collected; if no converter succeeds, FileConversionException is raised.

    """

    from core.harness.document.protocol import get_document_registry, StreamInfo

    from core.harness.document.parsers import _elements_to_dicts

    import os



    _kind = str(kind).lower()

    ext = _KIND_TO_EXT.get(_kind, os.path.splitext(file_path)[1].lower())

    registry = get_document_registry()

    info = StreamInfo(local_path=file_path, extension=ext)



    try:

        with open(file_path, "rb") as f:

            elements = registry.convert_with_fallback(f, info)

            return _elements_to_dicts(elements)

    except Exception:

        # Ultimate fallback: raw text read

        try:

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:

                text = f.read()

            if text.strip():

                return [{"type": "text", "text": text.strip(), "page_idx": 0,

                         "cells": None, "meta": {"source": _kind, "fallback": True}}]

        except Exception:

            logging.getLogger(__name__).debug('kb_parse_document failed', exc_info=True)
        return []





def kb_chunk_document(elements: Any, kind: str = "pdf", target_size: int = 1000, overlap: int = 150) -> Any:

    from core.harness.document.chunker import chunk_document

    return chunk_document(elements, kind=kind, target_size=target_size, overlap=overlap)





def get_document_categories() -> list:

    """Get supported document category labels (from ConverterRegistry — single source of truth)."""

    from core.harness.document.protocol import get_document_registry

    return get_document_registry().get_available_categories()





def set_knowledge_providers(*args: Any, **kwargs: Any) -> None:

    """Register platform-level knowledge provider callbacks for core KB operations.

    

    Callbacks registered:

        ingest_fn      → set_knowledge_ingest_fn()

        query_fn       → set_kb_query_fn()

        enqueue_fn     → set_kb_enqueue_ingest_fn()

        load_doc_kinds_fn → set_kb_load_doc_kinds_fn()

    """

    from core.apps.document_intelligence.kb_provider import (

        set_knowledge_ingest_fn, set_kb_query_fn,

        set_kb_enqueue_ingest_fn, set_kb_load_doc_kinds_fn,

    )

    if "ingest_fn" in kwargs and kwargs["ingest_fn"] is not None:

        set_knowledge_ingest_fn(kwargs["ingest_fn"])

    if "query_fn" in kwargs and kwargs["query_fn"] is not None:

        set_kb_query_fn(kwargs["query_fn"])

    if "enqueue_fn" in kwargs and kwargs["enqueue_fn"] is not None:

        set_kb_enqueue_ingest_fn(kwargs["enqueue_fn"])

    if "load_doc_kinds_fn" in kwargs and kwargs["load_doc_kinds_fn"] is not None:

        set_kb_load_doc_kinds_fn(kwargs["load_doc_kinds_fn"])





def get_embedding_model_name() -> str:

    """Return the currently configured embedding model name via infra resolution chain."""

    try:

        from core.harness.infrastructure.base_model_adapter import resolve_model_name

        return resolve_model_name("embedding")

    except Exception:

        return "unknown"

