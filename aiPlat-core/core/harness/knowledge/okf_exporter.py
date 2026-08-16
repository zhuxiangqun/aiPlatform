"""
OKF Exporter — aiPlat → OKF (Open Knowledge Format) 标准格式导出

将 aiPlat 的 GraphIndex 实体 + YAML 本体 + Markdown Wiki 导出为 OKF 标准格式。
每个概念对应一个 .okf.md 文件，支持增量导出。

OKF 文件结构:
  ---
  id: entity_id
  concept: ClassName
  aliases: [别名1, 别名2]
  relations:
    - type: relation_name
      target: target_entity_id
      label: 关系标签
  tags: [标签1, 标签2]
  ---
  # 概念名称
  (Markdown 正文 - 来自 Wiki 页面或 GraphIndex 元数据)

设计原则 (Karpathy LLM Wiki):
  - 标准之所以能留下来，是因为它们足够无聊和简单
  - 每个文件代表一个概念，文件之间的链接构成知识图谱
  - 知识应该像代码一样放进 Git、做版本控制

调用者: REST API POST /knowledge/export-okf
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import time as _time
import yaml as _yaml
from dataclasses import dataclass, field
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

OKF_EXPORT_DIR = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "okf_export"


# ── Data Models ──────────────────────────────────────────────────────────

@dataclass
class OKFEntity:
    """单个 OKF 实体."""
    id: str
    concept: str
    aliases: List[str] = field(default_factory=list)
    relations: List[Dict[str, str]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    body: str = ""                      # Markdown 正文

    def to_frontmatter(self) -> str:
        """生成 YAML Frontmatter."""
        fm: Dict[str, Any] = {
            "id": self.id,
            "concept": self.concept,
        }
        if self.aliases:
            fm["aliases"] = self.aliases
        if self.relations:
            fm["relations"] = self.relations
        if self.tags:
            fm["tags"] = self.tags
        return _yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def to_okf(self) -> str:
        """生成完整 OKF 文件内容."""
        frontmatter = self.to_frontmatter()
        return f"---\n{frontmatter}---\n\n{self.body}\n"


# ── OKFExporter ──────────────────────────────────────────────────────────

class OKFExporter:
    """OKF 格式导出器.

    使用方式:
        exporter = OKFExporter()
        result = await exporter.export(domain_id="ai-knowledge", incremental=True)
        → {"exported": 150, "skipped": 320, "dir": "~/.aiplat/okf_export/ai-knowledge/"}
    """

    def __init__(self):
        self._last_export_file = OKF_EXPORT_DIR / ".last_export.json"

    async def export(
        self,
        domain_id: str = "ai-knowledge",
        *,
        incremental: bool = False,
        output_dir: str = "",
    ) -> Dict[str, Any]:
        """导出域本体为 OKF 格式.

        Args:
            domain_id: 域ID
            incremental: 是否增量导出 (仅导出上次导出后变更的实体)
            output_dir: 输出目录 (留空自动生成)

        Returns:
            {"exported": int, "skipped": int, "total": int, "dir": str}
        """
        out = _Path(output_dir) if output_dir else OKF_EXPORT_DIR / domain_id
        out.mkdir(parents=True, exist_ok=True)
        start_time = _time.time()

        # 加载最后导出时间
        last_ts = 0.0
        if incremental and self._last_export_file.exists():
            try:
                with open(self._last_export_file) as f:
                    data = _json.load(f)
                last_ts = data.get("domains", {}).get(domain_id, {}).get("last_export_ts", 0.0)
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        # 从 GraphIndex 加载实体
        entities = await self._load_entities(domain_id)
        if not entities:
            return {"exported": 0, "skipped": 0, "total": 0, "dir": str(out), "error": "No entities found"}

        exported = 0
        skipped = 0

        for entity in entities:
            eid = entity.id

            # 增量模式: 检查是否变更
            if incremental and last_ts > 0:
                entity_file = out / f"{self._safe_filename(eid)}.okf.md"
                if entity_file.exists():
                    mtime = entity_file.stat().st_mtime
                    if mtime > last_ts:
                        # 实体自上次导出后未变更 → 跳过
                        skipped += 1
                        continue

            # 生成 OKF 文件
            okf_content = entity.to_okf()
            filename = self._safe_filename(eid)
            filepath = out / f"{filename}.okf.md"
            filepath.write_text(okf_content, encoding="utf-8")
            exported += 1

        # 生成索引文件 index.okf.md
        index = self._generate_index(entities, domain_id)
        (out / "index.okf.md").write_text(index, encoding="utf-8")

        # 更新最后导出时间
        self._update_last_export(domain_id, start_time)

        logger.info("OKF export complete: %d exported, %d skipped for domain %s",
                     exported, skipped, domain_id)
        return {
            "exported": exported,
            "skipped": skipped,
            "total": len(entities),
            "dir": str(out),
        }

    async def _load_entities(self, domain_id: str) -> List[OKFEntity]:
        """从 GraphIndex 加载实体并转换为 OKF 格式."""
        entities = []

        try:
            from core.harness.ontology_engine.graph_index import GraphIndex

            gi = GraphIndex(domain_id)
            gi.load(load_nodes=True)

            for nid, node in gi._nodes.items():
                # 提取别名 (从 entity_name 推断)
                aliases = []
                name = node.entity_name or nid
                if name != nid:
                    aliases.append(name)

                # 提取关系
                relations = []
                for edge in node.out_edges:
                    target_name = ""
                    target_node = gi._nodes.get(edge.target_id)
                    if target_node:
                        target_name = target_node.entity_name or edge.target_id
                    relations.append({
                        "type": edge.relation_name,
                        "target": edge.target_id,
                        "label": edge.relation_label or edge.relation_name,
                        "target_name": target_name,
                    })

                # 提取标签 (从 class_name)
                tags = [node.class_name] if node.class_name else []

                # 正文: 从 metadata 或 Wiki 获取
                body = self._build_body(node, gi)

                entities.append(OKFEntity(
                    id=nid,
                    concept=node.class_name or "Entity",
                    aliases=aliases,
                    relations=relations,
                    tags=tags,
                    body=body,
                ))

            gi.close()
            logger.debug("Loaded %d entities from GraphIndex domain=%s", len(entities), domain_id)

        except Exception as e:
            logger.warning("GraphIndex entity load failed for %s: %s", domain_id, e)

        return entities

    def _build_body(self, node: Any, gi: Any) -> str:
        """构建实体正文 Markdown."""
        parts = []

        # 标题
        name = node.entity_name or node.entity_id
        parts.append(f"# {name}\n")

        # 类型
        cls = getattr(node, "class_name", "") or "Entity"
        parts.append(f"**类型**: {cls}\n")

        # 元数据
        meta = getattr(node, "metadata", {})
        if isinstance(meta, dict) and meta:
            parts.append("\n## 元数据\n")
            for k, v in list(meta.items())[:10]:
                parts.append(f"- **{k}**: {str(v)[:200]}\n")

        # 入边摘要
        incoming = [e for n in gi._nodes.values() for e in n.out_edges if e.target_id == node.entity_id]
        if incoming:
            parts.append(f"\n## 入边 ({len(incoming)})\n")
            for e in incoming[:10]:
                src_name = gi._nodes.get(e.source_id)
                src_label = src_name.entity_name if src_name else e.source_id
                parts.append(f"- {src_label} → [{e.relation_label}]({e.relation_name})\n")

        # 出边摘要
        outgoing = node.out_edges if hasattr(node, "out_edges") else []
        if outgoing:
            parts.append(f"\n## 出边 ({len(outgoing)})\n")
            for e in outgoing[:10]:
                tgt_name = gi._nodes.get(e.target_id)
                tgt_label = tgt_name.entity_name if tgt_name else e.target_id
                parts.append(f"- [{e.relation_label}]({e.relation_name}) → {tgt_label}\n")

        return "".join(parts)

    def _generate_index(self, entities: List[OKFEntity], domain_id: str) -> str:
        """生成索引文件."""
        lines = [
            "---",
            f"id: {domain_id}-index",
            "concept: Index",
            "---",
            "",
            f"# {domain_id} - OKF Knowledge Index",
            "",
            f"**总计**: {len(entities)} 个概念",
            "",
            "## 概念列表",
            "",
        ]

        by_concept: Dict[str, List[OKFEntity]] = {}
        for e in entities:
            by_concept.setdefault(e.concept, []).append(e)

        for concept, items in sorted(by_concept.items()):
            lines.append(f"### {concept} ({len(items)})")
            for e in items[:50]:
                name = e.aliases[0] if e.aliases else e.id
                filename = self._safe_filename(e.id)
                rel_count = len(e.relations)
                lines.append(f"- [{name}]({filename}.okf.md) ({rel_count} 关系)")
            lines.append("")

        return "\n".join(lines)

    def _update_last_export(self, domain_id: str, ts: float) -> None:
        """更新最后导出时间."""
        try:
            data: Dict[str, Any] = {}
            if self._last_export_file.exists():
                with open(self._last_export_file) as f:
                    data = _json.load(f)
            data.setdefault("domains", {})
            data["domains"][domain_id] = {"last_export_ts": ts}
            self._last_export_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._last_export_file, "w") as f:
                _json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug("Failed to update last export time: %s", e)

    @staticmethod
    def _safe_filename(name: str) -> str:
        """安全文件名 (替换特殊字符)."""
        safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in name)
        return safe.strip().replace(" ", "_")[:100]
