"""
ConversationIngestor — 对话→Wiki 自动管线 (CodeAlmanac sync 对齐)

从 memory_messages 表中扫描 AI 对话记录，LLM 判断是否有长期价值，
有价值则提取主题 + 生成 Markdown Wiki 页面写入知识库。

核心判断标准 (CodeAlmanac 的"是否值得写"):
  ✅ 有长期价值: "为什么"类决策推理、"被纠正过"类的修正记录、"供未来复用"的可复用模式
  ❌ 无长期价值: 临时调试、单次错误修复、环境配置类对话

调用者: CronScheduler (每5h) / REST API POST /knowledge/ingest-conversations
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import sqlite3 as _sqlite3
import time as _time
import uuid as _uuid
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── IngestionResult ──────────────────────────────────────────────────────

class IngestionResult:
    def __init__(self):
        self.total_scanned = 0
        self.worth_writing = 0
        self.skipped = 0
        self.wiki_pages_created = 0
        self.errors = 0
        self.details: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_scanned": self.total_scanned,
            "worth_writing": self.worth_writing,
            "skipped": self.skipped,
            "wiki_pages_created": self.wiki_pages_created,
            "errors": self.errors,
            "details": self.details[:20],
        }


# ── ConversationIngestor ─────────────────────────────────────────────────

class ConversationIngestor:
    """对话自动摄入器.

    使用方式:
        ingestor = ConversationIngestor()
        result = await ingestor.ingest_recent(hours=5, max_messages=50)
    """

    def __init__(self):
        self._processed_file = _Path(
            _os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")
        ) / "data" / ".conversation_ingested.json"
        self._db_path = _os.path.expanduser("~/.aiplat/data/aiplat_platform.sqlite3")

    async def ingest_recent(
        self,
        *,
        hours: float = 5,
        max_messages: int = 50,
        domain_id: str = "",
        target_dir: str = "",
    ) -> IngestionResult:
        """扫描最近 N 小时的对话，提取有价值知识写入 Wiki.

        Args:
            hours: 扫描最近多少小时的对话
            max_messages: 最多处理多少条消息
            domain_id: 写入哪个域的知识库 (留空=从对话上下文推断)
            target_dir: 额外输出目录 (如项目 almanac/ 路径)

        Returns:
            IngestionResult
        """
        result = IngestionResult()

        # 获取已处理的消息ID
        processed = self._load_processed()

        # 扫描 memory_messages
        messages = self._scan_messages(hours, max_messages, processed)
        result.total_scanned = len(messages)

        if not messages:
            logger.debug("No new messages to ingest")
            return result

        # 对每条消息用 LLM 判断是否有长期价值
        for msg in messages:
            try:
                # Phase 57: Skip messages with cognitive risk patterns
                content = (msg.get("content") or "").lower()
                # Built-in engine keywords (infrastructure-level)
                skip_keywords = ["final_answer", "safety_audit"]
                # User-configured domain-specific keywords via env var
                extra = os.getenv("AIPLAT_INGEST_SKIP_KEYWORDS", "")
                if extra:
                    skip_keywords.extend(kw.strip() for kw in extra.split(",") if kw.strip())
                if any(kw in content for kw in skip_keywords):
                    result.skipped += 1
                    continue

                worth, topic_slug, wiki_content = await self._judge_and_extract(msg)
                if worth and topic_slug and wiki_content:
                    result.worth_writing += 1
                    # 写入 Wiki
                    written = self._write_wiki(topic_slug, wiki_content, domain_id or msg.get("domain", ""), target_dir)
                    if written:
                        result.wiki_pages_created += 1
                        result.details.append({
                            "msg_id": msg.get("id"),
                            "topic": topic_slug,
                            "preview": wiki_content[:100],
                        })
                else:
                    result.skipped += 1

                # 标记已处理
                if msg.get("id"):
                    processed.add(str(msg["id"]))

            except Exception as e:
                result.errors += 1
                logger.debug("Ingestion failed for msg %s: %s", msg.get("id"), e)

        # 持久化已处理标记
        self._save_processed(processed)

        logger.info("Ingestion complete: %d scanned, %d written, %d skipped",
                     result.total_scanned, result.wiki_pages_created, result.skipped)
        return result

    def _scan_messages(
        self,
        hours: float,
        max_count: int,
        already_processed: set,
    ) -> List[Dict[str, Any]]:
        """从 memory_messages 表扫描未处理的对话."""
        if not _os.path.exists(self._db_path):
            return []

        try:
            conn = _sqlite3.connect(self._db_path)
            conn.row_factory = _sqlite3.Row
            cutoff = _time.time() - hours * 3600

            # 查询 assistant 角色的消息（包含有价值的技术讨论）
            rows = conn.execute(
                """SELECT id, content, role, metadata_json, created_at, session_id, run_id
                   FROM memory_messages
                   WHERE role = 'assistant'
                     AND created_at > ?
                     AND LENGTH(content) > 100
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (cutoff, max_count),
            ).fetchall()
            conn.close()

            messages = []
            for r in rows:
                mid = str(r["id"]) if r["id"] else ""
                if mid and mid in already_processed:
                    continue
                msg = dict(r)
                # Parse metadata
                try:
                    meta = _json.loads(msg.get("metadata_json", "{}"))
                except Exception:
                    meta = {}
                msg["metadata"] = meta
                msg["domain"] = meta.get("domain_id", "") or meta.get("collection_id", "")
                messages.append(msg)

            return messages

        except Exception as e:
            logger.warning("Message scan failed: %s", e)
            return []

    async def _judge_and_extract(
        self,
        msg: Dict[str, Any],
    ) -> tuple:
        """LLM 判断对话是否有长期价值，如有则提取主题和 Wiki 内容.

        Returns:
            (worth_writing: bool, topic_slug: str, wiki_content: str)
        """
        content = (msg.get("content") or "")[:3000]
        meta = msg.get("metadata", {})
        context = _json.dumps({
            "skills_used": meta.get("skills_used", []),
            "strategy": meta.get("strategy", ""),
            "mode": meta.get("mode", ""),
        }, ensure_ascii=False)

        try:
            from core.harness.utils.model_injection import best_model_for_purpose
            from core.harness.syscalls.llm import sys_llm_generate

            prompt = f"""判断以下 AI 对话内容是否有长期价值，值得写入项目知识库。

判断标准:
  ✅ 有价值: "为什么"类的决策推理、"被纠正过"的修正记录、"供未来复用"的可复用模式
  ❌ 无价值: 临时调试、单次错误修复、环境配置类对话

对话内容:
{content[:2500]}

上下文:
{context}

请返回 JSON:
{{
  "worth_writing": true/false,
  "topic_slug": "不超过5个词的英文主题名(如 auth-module-design)",
  "reason": "简短判断理由",
  "wiki_markdown": "如果worth_writing=true，输出完整的Markdown格式Wiki页面内容(含标题、正文、代码示例)。如果false则为空字符串。"
}}

只返回 JSON，不要其他内容。"""

            result = await sys_llm_generate(
                messages=[{"role": "user", "content": prompt}],
                model=best_model_for_purpose("doc_llm"),
                temperature=0.1,
                max_tokens=2000,
            )
            content_str = result.get("content", "") if isinstance(result, dict) else str(result)

            # Parse JSON
            data = self._extract_json(content_str)
            worth = data.get("worth_writing", False)
            topic = data.get("topic_slug", "")[:50]
            wiki = data.get("wiki_markdown", "")

            return (bool(worth), str(topic), str(wiki))

        except Exception as e:
            logger.debug("LLM judge failed: %s", e)
            return (False, "", "")

    def _write_wiki(
        self,
        topic_slug: str,
        wiki_content: str,
        domain_id: str,
        target_dir: str = "",
    ) -> bool:
        """写入 Wiki 页面.

        同时写入两个位置:
          1. ~/.aiplat/wiki/collections/{domain}/ (平台级)
          2. {project}/almanac/ (项目级, 可选)
        """
        written = False

        # 1. 平台级 Wiki
        try:
            wiki_dir = _Path(
                _os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")
            ) / "wiki" / "collections" / (domain_id or "default")
            wiki_dir.mkdir(parents=True, exist_ok=True)
            page_path = wiki_dir / f"{topic_slug}.md"

            # Phase 52: Conflict detection — don't overwrite user-modified content
            if page_path.exists():
                existing = page_path.read_text(encoding="utf-8", errors="ignore")
                # User modification heuristic: if content differs significantly (>30%) from AI-generated, keep user version
                if len(existing) > 0 and abs(len(existing) - len(wiki_content)) / max(len(existing), 1) > 0.3:
                    conflict_path = wiki_dir / f"{topic_slug}.aiplat_conflict"
                    conflict_path.write_text(
                        f"# Conflict: {topic_slug}\n\n"
                        f"## AI-generated version (not applied)\n\n{wiki_content}\n\n"
                        f"## User-modified version (kept)\n\n{existing}\n",
                        encoding="utf-8",
                    )
                    logger.warning("Wiki conflict for '%s': user version preserved, AI version saved to %s", topic_slug, conflict_path)
                    written = True  # Don't fail — conflict was handled
                else:
                    page_path.write_text(wiki_content, encoding="utf-8")
                    written = True
            else:
                page_path.write_text(wiki_content, encoding="utf-8")
                written = True
            logger.debug("Wiki page written: %s", page_path)
        except Exception as e:
            logger.warning("Platform wiki write failed: %s", e)

        # 2. 项目级 almanac/ (repo wiki) — repo priority: user modifications win
        if target_dir:
            try:
                almanac_dir = _Path(target_dir) / "almanac"
                almanac_dir.mkdir(parents=True, exist_ok=True)
                page_path = almanac_dir / f"{topic_slug}.md"

                if page_path.exists():
                    existing = page_path.read_text(encoding="utf-8", errors="ignore")
                    if len(existing) > 0 and abs(len(existing) - len(wiki_content)) / max(len(existing), 1) > 0.15:
                        # Repo has priority — user modified, keep their version
                        logger.info("Repo wiki preserved for '%s': user-modified content kept (diff=%.0f%%)",
                                    topic_slug, abs(len(existing) - len(wiki_content)) / max(len(existing), 1) * 100)
                    else:
                        page_path.write_text(wiki_content, encoding="utf-8")
                else:
                    page_path.write_text(wiki_content, encoding="utf-8")
                logger.debug("Repo wiki written: %s", page_path)
            except Exception as e:
                logger.debug("Repo wiki write failed: %s", e)

        return written

    # ── Processed State ──────────────────────────────────────────────

    def _load_processed(self) -> set:
        try:
            if self._processed_file.exists():
                with open(self._processed_file) as f:
                    data = _json.load(f)
                return set(data.get("processed_ids", []))
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
        return set()

    def _save_processed(self, ids: set) -> None:
        try:
            self._processed_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._processed_file, "w") as f:
                _json.dump({"processed_ids": list(ids)[-500:]}, f)
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """从 LLM 输出中提取 JSON."""
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            parts = text.split("```")
            for p in parts:
                p = p.strip()
                if p.startswith("{"):
                    text = p
                    break
        start = text.find("{")
        if start >= 0:
            end = text.rfind("}")
            if end > start:
                try:
                    return _json.loads(text[start:end + 1])
                except Exception:
                    logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
        return {}
