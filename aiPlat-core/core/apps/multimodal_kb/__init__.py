"""
Multimodal Knowledge Base (Phase A)

提供多租户隔离的 KB 存储（SQLite）与最小能力：
- ingest_document: PDF/扫描件 → 渲染 → OCR → 预算表结构化 → 入库
- query: 针对“投资预算”类问题从库中返回结构化条目与 citations（页码/bbox/asset_path）
"""

from .service import ingest_document, query

__all__ = ["ingest_document", "query"]

