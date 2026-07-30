"""
文档 → Wiki 自动同步模块。

B. 启动时同步：sync_docs_to_wiki() — 遍历 docs/ 导入全部文件
C. 文件监视：   start_docs_watcher()  — 监视 docs/ 变更，增量同步
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_docs_dir() -> Path:
    """获取项目 docs/ 目录的绝对路径。"""
    return Path(__file__).resolve().parent.parent.parent.parent.parent / "docs"


def _md_file_to_wiki_title(md_file: Path, docs_root: Path) -> str:
    """将文件系统路径转换为 Wiki 页面标题。"""
    return str(md_file.relative_to(docs_root)).replace("/", " / ").replace(".md", "")


def _needs_sync(md_file: Path, title: str, collection: str) -> bool:
    """比较文件 mtime 与 Wiki 页面的 last_updated。
    返回 True 表示需要重新导入（文件更新或 Wiki 中不存在）。
    """
    try:
        from core.harness.knowledge.wiki_engine import read_page
        import time, calendar
    except (ImportError, ModuleNotFoundError):
        return True  # 无法检查 → 保守导入

    page = read_page(title, category="topics", collection_id=collection)
    if not page:
        return True  # Wiki 中不存在

    file_mtime = md_file.stat().st_mtime

    last_updated = page.get("last_updated", "")
    if not last_updated:
        return True  # 无时间戳 → 保守导入

    try:
        # 解析 Wiki 页面的 last_updated（多种 ISO 格式）
        # "2026-07-25T07:09:11.499+00:00" 或 "2026-07-25T15:54:00Z"
        ts_str = last_updated.replace("Z", "+00:00")
        if "." in ts_str:
            ts_str = ts_str.split(".")[0] + ts_str[ts_str.index("+") if "+" in ts_str else len(ts_str):]
        elif "+" not in ts_str:
            ts_str += "+00:00"
        page_ts = calendar.timegm(time.strptime(ts_str, "%Y-%m-%dT%H:%M:%S%z"))
    except ValueError:
        return True  # 解析失败 → 保守导入

    return file_mtime > page_ts


def sync_docs_to_wiki(collection: str = "system_docs") -> dict:
    """差分同步：仅导入有变更的文档。首次运行全量，后续仅增量。"""
    from core.harness.knowledge.wiki_engine import write_page

    docs_root = _get_docs_dir()
    if not docs_root.is_dir():
        logger.warning("Docs dir not found: %s", docs_root)
        return {"created": 0, "skipped": 0, "errors": 1}

    created = skipped = errors = 0
    for md_file in docs_root.rglob("*.md"):
        fp = str(md_file)
        if ".venv" in fp or "node_modules" in fp or "__pycache__" in fp:
            continue
        try:
            title = _md_file_to_wiki_title(md_file, docs_root)
            if not _needs_sync(md_file, title, collection):
                skipped += 1
                continue
            body = md_file.read_text(encoding="utf-8")
            write_page(
                title=title,
                body=body[:200000],
                category="topics",
                tags=["documentation", md_file.parent.name],
                collection_id=collection,
                status="draft",
            )
            created += 1
        except Exception as e:
            logger.debug("sync_docs_to_wiki: %s → %s", md_file.name, str(e)[:100])
            errors += 1

    logger.info("Docs sync: %d created/updated, %d skipped, %d errors", created, skipped, errors)
    return {"created": created, "skipped": skipped, "errors": errors}


def start_docs_watcher(collection: str = "system_docs"):
    """启动文档目录的变更监视（文件增删改 → 增量同步 Wiki）。"""
    docs_root = _get_docs_dir()
    if not docs_root.is_dir():
        return

    try:
        from infra.management.file_watcher import get_file_watcher
        watcher = get_file_watcher()
    except (ImportError, ModuleNotFoundError):
        return

    def _on_docs_change(filepath: str):
        md_path = Path(filepath)
        if not md_path.exists():
            try:
                title = _md_file_to_wiki_title(md_path, docs_root)
                from core.harness.knowledge.wiki_engine import delete_page
                delete_page(title, collection_id=collection)
                logger.info("Wiki page deleted: %s", title)
            except Exception as e:
                logger.debug("docs_watcher delete: %s", str(e)[:200])
            return
        if not md_path.suffix == ".md":
            return
        try:
            title = _md_file_to_wiki_title(md_path, docs_root)
            body = md_path.read_text(encoding="utf-8")
            from core.harness.knowledge.wiki_engine import write_page
            write_page(
                title=title,
                body=body[:200000],
                category="topics",
                tags=["documentation", md_path.parent.name],
                collection_id=collection,
                status="published",
            )
            logger.info("Wiki page synced: %s", title)
        except Exception as e:
            logger.debug("docs_watcher sync: %s", str(e)[:200])

    watcher.watch(str(docs_root), _on_docs_change)
    logger.info("Docs watcher started on %s", docs_root)
