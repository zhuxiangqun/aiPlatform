"""Wiki 读模型硬门（v4.3.1）：禁止人工把 Wiki 当事实源直接改。

职责：判断 collection 是否处于读模型模式；人工 HTTP 写入口调用
``assert_manual_wiki_write_allowed``。编译器路径（synthesis / ingest /
docs_sync / write_page 直调）不经过本门。

集合名单仅由 ``AIPLAT_WIKI_READ_MODEL_COLLECTIONS``（逗号分隔）配置驱动，
禁止在 harness 内硬编码业务域/collection（内核无关）。

非目标：不实现重建分类契约、ObjectSet、全局禁写、管理端 UX。
"""
from __future__ import annotations

import logging
import os
from typing import FrozenSet

logger = logging.getLogger(__name__)

REASON_WIKI_IS_READ_MODEL = "wiki_is_read_model"


class WikiManualWriteDenied(PermissionError):
    """读模型 collection 上禁止人工直接写 Wiki。"""

    def __init__(self, collection_id: str, reason: str = REASON_WIKI_IS_READ_MODEL):
        """记录被拒的 collection 与稳定 reason 码。

        Args:
            collection_id: 被拦截的 Wiki collection。
            reason: 对外 detail（默认 ``wiki_is_read_model``）。
        """
        self.collection_id = collection_id
        self.reason = reason
        super().__init__(reason)


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes", "y")


def wiki_manual_write_break_glass() -> bool:
    """True 时允许绕过读模型硬门（运维破窗；须显式 env）。"""
    return _flag("AIPLAT_WIKI_ALLOW_MANUAL_WRITE")


def read_model_collections() -> FrozenSet[str]:
    """返回处于读模型模式的 collection 集合。

    Returns:
        collection_id 集合；未配置时为空（门不生效，需显式配置试点名单）。
    """
    # 为什么：名单 env 含 MODEL 字样但非 LLM 模型解析；豁免 §40.2 误报
    raw = (os.getenv("AIPLAT_WIKI_READ_MODEL_COLLECTIONS") or "").strip()  # noqa: env-legacy
    if not raw:
        return frozenset()
    return frozenset(x.strip() for x in raw.split(",") if x.strip())


def is_wiki_read_model_collection(collection_id: str) -> bool:
    """collection 是否按读模型（禁止人工直接写）。

    Args:
        collection_id: Wiki collection 标识。
    """
    cid = (collection_id or "default").strip() or "default"
    return cid in read_model_collections()


def assert_manual_wiki_write_allowed(collection_id: str) -> None:
    """人工写入口前置检查；读模型 collection 且无破窗则拒绝。

    Args:
        collection_id: Wiki collection 标识。

    Raises:
        WikiManualWriteDenied: 已配置为读模型且未开破窗。
    """
    cid = (collection_id or "default").strip() or "default"
    if not is_wiki_read_model_collection(cid):
        return
    if wiki_manual_write_break_glass():
        # 破窗必须可观测，避免静默绕过读模型铁律
        logger.warning(
            "wiki manual write break-glass allowed collection_id=%s",
            cid,
        )
        return
    raise WikiManualWriteDenied(cid)
