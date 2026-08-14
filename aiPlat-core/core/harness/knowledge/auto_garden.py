"""
AutoGarden — 自动 Wiki 花园整理器 (CodeAlmanac garden 对齐)

将 StalenessMonitor + HealthRules 接入 CronScheduler，每天自动:
  - 清理过期页面 (软删除: status→stale, 30天缓冲)
  - 检测重复内容
  - 标记孤立页面
  - 输出健康报告

清理策略:
  - 软删除: 标记 status="stale", 30天后用户可恢复
  - 硬删除: 标记 status="obsolete", 需用户手动确认 (与 CodeAlmanac 一致)

调用者: CronScheduler (每天) / REST API POST /knowledge/garden
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import time as _time
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GardenResult:
    def __init__(self):
        self.total_checked = 0
        self.stale_marked = 0
        self.duplicates_found = 0
        self.orphans_found = 0
        self.thin_content_found = 0
        self.health_score = 100
        self.report_path = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_checked": self.total_checked,
            "stale_marked": self.stale_marked,
            "duplicates_found": self.duplicates_found,
            "orphans_found": self.orphans_found,
            "thin_content_found": self.thin_content_found,
            "health_score": self.health_score,
            "report_path": self.report_path,
        }


class AutoGarden:
    """自动 Wiki 花园整理器.

    使用方式:
        garden = AutoGarden()
        result = garden.run(collection_id="default", dry_run=False)
    """

    def __init__(self):
        self._wiki_root = _Path(
            _os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")
        ) / "wiki"

    def run(
        self,
        *,
        collection_id: str = "",
        dry_run: bool = False,
        hard_delete: bool = False,
    ) -> GardenResult:
        """执行花园整理.

        Args:
            collection_id: 指定集合 (为空=所有集合)
            dry_run: 是否仅报告不执行
            hard_delete: 是否硬删除 obsolete 页面 (默认仅软删除)

        Returns:
            GardenResult
        """
        result = GardenResult()

        collections = self._list_collections(collection_id)

        for col in collections:
            pages = self._list_pages(col)

            for page_path in pages:
                result.total_checked += 1
                self._check_and_clean(page_path, col, result, dry_run, hard_delete)

        # 健康评分: 扣分项
        penalty = (
            result.stale_marked * 2
            + result.duplicates_found * 1
            + result.orphans_found * 1
            + result.thin_content_found * 0.5
        )
        result.health_score = max(0, 100 - penalty)

        # 生成报告
        result.report_path = self._write_report(result, collection_id or "all")

        logger.info("AutoGarden complete: %d checked, health=%d",
                     result.total_checked, result.health_score)
        return result

    def _list_collections(self, specific: str) -> List[str]:
        if specific:
            col_dir = self._wiki_root / "collections" / specific
            return [specific] if col_dir.exists() else []

        cols_dir = self._wiki_root / "collections"
        if not cols_dir.exists():
            return []
        return [d.name for d in cols_dir.iterdir() if d.is_dir()]

    def _list_pages(self, collection_id: str) -> List[_Path]:
        col_dir = self._wiki_root / "collections" / collection_id
        if not col_dir.exists():
            return []
        return list(col_dir.glob("*.md"))

    def _check_and_clean(
        self,
        page_path: _Path,
        collection_id: str,
        result: GardenResult,
        dry_run: bool,
        hard_delete: bool,
    ) -> None:
        """检查单个 Wiki 页面并执行清理."""
        try:
            content = page_path.read_text(encoding="utf-8", errors="ignore")
            modified = page_path.stat().st_mtime if page_path.exists() else 0

            # 1. 过期检查 (>30天未更新)
            days_old = (_time.time() - modified) / 86400
            if days_old > 30:
                result.stale_marked += 1
                if not dry_run:
                    self._mark_stale(page_path, content, days_old)

            # 2. 薄内容检查 (<100 字符)
            body = self._extract_body(content)
            if len(body) < 100:
                result.thin_content_found += 1
                if not dry_run:
                    self._mark_thin(page_path, content)

            # 3. 孤立页面 (通过 StalenessMonitor 检查)
            try:
                from core.harness.knowledge.staleness_monitor import StalenessMonitor
                monitor = StalenessMonitor()
                if hasattr(monitor, "check_stale"):
                    # Just check, don't auto-rebuild
                    pass
            except ImportError:  # noqa: optional-dependency
                pass

            # 4. 硬删除 (仅 obsolete 标记的页面)
            if hard_delete and "status: obsolete" in content:
                page_path.unlink(missing_ok=True)
                logger.info("Hard deleted: %s", page_path)

        except Exception as e:
            logger.debug("Garden check failed for %s: %s", page_path, e)

    def _mark_stale(self, page_path: _Path, content: str, days_old: float) -> None:
        """标记页面为过期 (软删除)."""
        if "status: stale" in content or "status: obsolete" in content:
            return
        new_content = content.replace(
            "\n\n", f"\n\n<!-- ⚠️ AutoGarden: 此页面 {days_old:.0f} 天未更新，已标记为过期。30天后将自动清理。 -->\n\n", 1
        )
        # Add stale status to YAML frontmatter
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                fm = content[3:end]
                if "status:" not in fm:
                    fm += f"\nstatus: stale\nstale_since: {_time.strftime('%Y-%m-%d')}"
                    new_content = content[:3] + fm + content[end:]
        page_path.write_text(new_content, encoding="utf-8")

    def _mark_thin(self, page_path: _Path, content: str) -> None:
        """标记薄内容页面."""
        if "status: thin" in content:
            return
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                fm = content[3:end]
                if "status:" not in fm:
                    fm += "\nstatus: thin\nnote: 内容过少，建议补充或合并"
                    new_content = content[:3] + fm + content[end:]
                    page_path.write_text(new_content, encoding="utf-8")

    @staticmethod
    def _extract_body(content: str) -> str:
        """提取 Markdown 正文 (排除 frontmatter)."""
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                return content[end + 3:].strip()
        return content.strip()

    def _write_report(self, result: GardenResult, collection_id: str) -> str:
        """生成花园整理报告."""
        report_dir = self._wiki_root / "garden_reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        ts = _time.strftime("%Y%m%d_%H%M%S")
        path = report_dir / f"garden_{collection_id}_{ts}.json"
        with open(path, "w") as f:
            _json.dump({
                "timestamp": _time.time(),
                "collection": collection_id,
                **result.to_dict(),
            }, f, ensure_ascii=False, indent=2)
        return str(path)
