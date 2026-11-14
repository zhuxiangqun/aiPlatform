"""
Knowledge system callback Protocols — Platform → Core reverse-injection contracts.

Core defines the callback signatures it needs. Platform implements them
and registers via kb_provider. This is dependency inversion:
Core depends on the Protocol, not on Platform's concrete types.

Per boundary-standard.md §5.3.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class KBIngestCallback(Protocol):
    """Core → Platform：同步文档摄取回调。"""

    def __call__(
        self,
        *,
        tenant_id: str,
        collection_id: str,
        file_path: str,
        kind: str = "pdf",
        ocr_lang: str = "zh",
        ocr_engine: Optional[str] = None,
        dpi: int = 240,
        max_pages: Optional[int] = 60,
        name: str = "",
        progress_cb: Optional[Any] = None,
        last_job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """同步摄取文档并返回结果。

        Args:
            tenant_id: 租户 ID。
            collection_id: 知识库集合 ID。
            file_path: 待摄取文件路径。
            kind: 文档类型，默认 pdf。
            ocr_lang: OCR 语言，默认 zh。
            ocr_engine: OCR 引擎名；None 表示平台默认。
            dpi: 渲染 DPI。
            max_pages: 最大页数上限；None 表示不限。
            name: 文档显示名。
            progress_cb: 可选进度回调。
            last_job_id: 续跑时的上一任务 ID。
        """
        ...


class KBQueryCallback(Protocol):
    """Core → Platform：同步 KB 查询回调（当前偏预算场景）。"""

    def __call__(
        self,
        *,
        tenant_id: str,
        collection_id: str,
        question: str,
        year: Optional[int] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """执行 KB 查询并返回结果。

        Args:
            tenant_id: 租户 ID。
            collection_id: 知识库集合 ID。
            question: 查询问题。
            year: 可选年份过滤。
            limit: 返回条数上限。
        """
        ...


class KBEnqueueIngestCallback(Protocol):
    """Core → Platform：异步文档摄取入队回调。"""

    def __call__(
        self,
        *,
        tenant_id: str,
        collection_id: str,
        file_path: str,
        kind: str = "pdf",
        ocr_lang: str = "zh",
        ocr_engine: Optional[str] = None,
        dpi: int = 240,
        max_pages: Optional[int] = 60,
        name: str = "",
    ) -> Dict[str, Any]:
        """将摄取任务入队并返回受理结果。

        Args:
            tenant_id: 租户 ID。
            collection_id: 知识库集合 ID。
            file_path: 待摄取文件路径。
            kind: 文档类型，默认 pdf。
            ocr_lang: OCR 语言，默认 zh。
            ocr_engine: OCR 引擎名；None 表示平台默认。
            dpi: 渲染 DPI。
            max_pages: 最大页数上限；None 表示不限。
            name: 文档显示名。
        """
        ...


class KBLoadDocKindsCallback(Protocol):
    """Core → Platform：批量加载文档 kind 元数据。"""

    def __call__(
        self,
        *,
        tenant_id: str,
        doc_ids: List[str],
    ) -> List[str]:
        """按 doc_ids 返回对应 kind 列表。

        Args:
            tenant_id: 租户 ID。
            doc_ids: 文档 ID 列表。
        """
        ...


__all__ = [
    "KBIngestCallback",
    "KBQueryCallback",
    "KBEnqueueIngestCallback",
    "KBLoadDocKindsCallback",
]
