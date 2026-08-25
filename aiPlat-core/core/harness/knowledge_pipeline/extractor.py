"""
Knowledge Pipeline — LLM-driven document entity extraction (Phase 1, 2026-07-30).

Three-step pipeline:
  1. DocumentIngestor: PDF/Word/text → chunked segments
  2. EntityExtractor: LLM call → entities + relations + confidence
  3. DraftYamlWriter: output to ~/.aiplat/ontologies/drafts/

Confidence routing:
  ≥ 0.85 → auto-write draft YAML
  0.60–0.85 → pending_extractions (FDE workbench review)
  < 0.60 → discarded (logged)
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Literal

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Data models
# ═══════════════════════════════════════════════════════════

@dataclass
class ExtractedEntity:
    name: str
    class_type: str  # 人物|组织|产品|地点|时间|事件|文档|概念|方法
    attributes: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    evidence: str = ""
    source_doc: str = ""
    source_offset: int = 0
    entity_id: str = ""


@dataclass
class ExtractedRelation:
    source_entity: str
    relation_type: str  # 属于|参与|负责|包含|依赖|导致|演化为|部署于|开始于|结束于
    target_entity: str
    confidence: float = 0.0
    evidence: str = ""
    source_doc: str = ""


@dataclass
class ExtractionResult:
    extraction_id: str
    domain_id: str
    source_doc: str
    entities: List[ExtractedEntity] = field(default_factory=list)
    relations: List[ExtractedRelation] = field(default_factory=list)
    overall_confidence: float = 0.0
    status: str = "pending"  # pending | confirmed | rejected | auto_accepted
    created_at: str = ""
    draft_yaml_path: str = ""


# ═══════════════════════════════════════════════════════════
# Prompt template
# ═══════════════════════════════════════════════════════════

EXTRACTION_PROMPT = """你是企业知识抽取专家。从以下文本中抽取实体和关系。

预定义实体类型（只使用这些）:
  人物, 组织, 产品, 地点, 时间, 事件, 文档, 概念, 方法

预定义关系类型（只使用这些）:
  属于, 参与, 负责, 包含, 依赖, 导致, 演化为, 部署于, 开始于, 结束于

输出严格 JSON（不含 markdown 标记）:
{
  "entities": [
    {"name": "实体名", "class_type": "预定义类型", "attributes": {}, "evidence": "原文证据"}
  ],
  "relations": [
    {"source": "实体A", "type": "关系类型", "target": "实体B", "evidence": "原文证据"}
  ],
  "overall_confidence": 0.0
}

待抽取文本:
{chunk_text}"""

# P2-3 闭环（2026-08-25）：EXTRACTION_PROMPT 注册进 prompt_loader（模板治理，§17 内容归属）。
# prompt_loader 约定 ${var} 占位符；模块常量用 .format() 的 {var}——注册时转换占位符。
# 模块级常量保留向后兼容；新路径经 prompt_loader._sync_resolve("knowledge-extraction") 读取。
try:
    from core.harness.utils.prompt_loader import _register as _register_prompt
    _register_prompt(
        "knowledge-extraction",
        EXTRACTION_PROMPT.replace("{chunk_text}", "${chunk_text}"),
        category="knowledge",
        variables=["chunk_text"],
        version="1.0.0",
    )
except Exception:  # noqa: BLE001  # 注册失败不影响导入（prompt_loader 为可选依赖）
    pass


# ═══════════════════════════════════════════════════════════
# Step 1: Document Ingestor
# ═══════════════════════════════════════════════════════════

class DocumentIngestor:
    """Split document text into LLM-friendly chunks (~2000 chars each)."""

    MAX_CHUNK_SIZE = 2000

    def ingest(self, text: str, doc_name: str = "unknown") -> List[Dict[str, Any]]:
        """Return list of {offset, text, doc_name} chunks."""
        chunks = []
        offset = 0
        while offset < len(text):
            chunk = text[offset:offset + self.MAX_CHUNK_SIZE]
            # Try to break at sentence boundary
            if len(chunk) == self.MAX_CHUNK_SIZE and offset + self.MAX_CHUNK_SIZE < len(text):
                last_period = max(chunk.rfind("。"), chunk.rfind(". "), chunk.rfind("\n"), 0)
                if last_period > self.MAX_CHUNK_SIZE // 2:
                    chunk = chunk[:last_period + 1]
            chunks.append({"offset": offset, "text": chunk.strip(), "doc_name": doc_name})
            offset += len(chunk)
        return chunks


# ═══════════════════════════════════════════════════════════
# Step 2: Entity Extractor (LLM-driven)
# ═══════════════════════════════════════════════════════════

class EntityExtractor:
    """Call LLM to extract entities and relations from a text chunk."""

    # P2-3/Q3 闭环（2026-08-25）：VALID_CLASS_TYPES 从硬编码改为配置驱动——
    # 有 domain_id 时读域本体 YAML 类清单（ontology_loader），无则回退通用默认集。
    # 硬编码默认集保留为兜底（非域上下文抽取仍可用）。
    VALID_CLASS_TYPES = {"人物", "组织", "产品", "地点", "时间", "事件", "文档", "概念", "方法"}
    VALID_RELATION_TYPES = {"属于", "参与", "负责", "包含", "依赖", "导致", "演化为", "部署于", "开始于", "结束于"}

    @staticmethod
    def _domain_class_types(domain_id: str) -> Optional[set]:
        """读域本体 YAML 的类清单（含 synonyms/categories）；无 domain 或加载失败返回 None。"""
        if not domain_id:
            return None
        try:
            import os as _os
            path = _os.path.expanduser(f"~/.aiplat/ontologies/{domain_id}.yaml")
            if not _os.path.exists(path):
                return None
            from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
            domain = load_ontology_from_yaml(path)
            labels = set()
            for cls in domain.classes:
                labels.add(cls.label)
                labels.update(cls.allowed_categories or [])
                labels.update(cls.synonyms or [])
            return labels if labels else None
        except Exception:  # noqa: BLE001
            return None

    def _effective_class_types(self, domain_id: str) -> set:
        return self._domain_class_types(domain_id) or self.VALID_CLASS_TYPES

    async def extract(self, chunk: Dict[str, Any], domain_id: str = "") -> Dict[str, Any]:
        """Extract entities + relations from one chunk via LLM."""
        # P2-3：提示词经 prompt_loader 解析（模板治理），域类清单注入
        class_types = self._effective_class_types(domain_id)
        class_list = ", ".join(sorted(class_types))
        prompt = self._build_prompt(chunk["text"], class_list)

        try:
            # Use the system LLM call
            result_text = await self._call_llm(prompt)
            parsed = self._parse_response(result_text, chunk["doc_name"], chunk["offset"])
            # 过滤非法 class_type（域类清单外）——Q3 校验落地
            if parsed.get("entities"):
                parsed["entities"] = [
                    e for e in parsed["entities"]
                    if not e.get("class_type") or e["class_type"] in class_types
                ]
            return parsed
        except Exception as e:
            logger.warning("Extraction failed for chunk at offset %d: %s", chunk.get("offset", 0), e, exc_info=True)
            return {"entities": [], "relations": [], "overall_confidence": 0.0}

    @staticmethod
    def _build_prompt(chunk_text: str, class_list: str) -> str:
        """构建抽取提示词：优先 prompt_loader 注册模板，回退模块级 EXTRACTION_PROMPT。"""
        try:
            from core.harness.utils.prompt_loader import _sync_resolve
            return _sync_resolve("knowledge-extraction", chunk_text=chunk_text)
        except Exception:  # noqa: BLE001
            return EXTRACTION_PROMPT.format(chunk_text=chunk_text)

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM via the harness syscall channel."""
        try:
            from core.harness.syscalls.llm import sys_llm_generate
            messages = [{"role": "user", "content": prompt}]
            result = await sys_llm_generate(messages, purpose="doc_llm")
            return result.get("content", "") or str(result)
        except Exception:
            logger.warning("sys_llm_generate unavailable, using fallback", exc_info=True)
            return ""
        # If sys_llm_generate not available, try adapter
        try:
            from core.harness.utils.model_injection import create_selected_adapter
            adapter = create_selected_adapter("doc_llm")
            return adapter.generate([{"role": "user", "content": prompt}])
        except Exception:
            logger.warning("LLM adapter also unavailable", exc_info=True)
            return ""

    def _parse_response(self, result_text: str, doc_name: str, offset: int) -> Dict[str, Any]:
        """Parse LLM JSON response, handle noise."""
        # Strip markdown code fences
        cleaned = re.sub(r'```(?:json)?\s*', '', result_text)
        cleaned = cleaned.replace('```', '').strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to extract JSON from mixed text
            match = re.search(r'\{[\s\S]*\}', cleaned)
            if not match:
                return {"entities": [], "relations": [], "overall_confidence": 0.0}
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return {"entities": [], "relations": [], "overall_confidence": 0.0}

        entities = []
        for e in data.get("entities", []):
            class_type = e.get("class_type", "概念")
            if class_type not in self.VALID_CLASS_TYPES:
                class_type = "概念"
            entities.append(ExtractedEntity(
                entity_id=str(uuid.uuid4())[:12],
                name=e.get("name", "unknown"),
                class_type=class_type,
                attributes=e.get("attributes", {}),
                confidence=data.get("overall_confidence", 0.5),
                evidence=e.get("evidence", ""),
                source_doc=doc_name,
                source_offset=offset,
            ))

        relations = []
        for r in data.get("relations", []):
            rel_type = r.get("type", "属于")
            if rel_type not in self.VALID_RELATION_TYPES:
                rel_type = "属于"
            relations.append(ExtractedRelation(
                source_entity=r.get("source", ""),
                relation_type=rel_type,
                target_entity=r.get("target", ""),
                confidence=data.get("overall_confidence", 0.5),
                evidence=r.get("evidence", ""),
                source_doc=doc_name,
            ))

        return {
            "entities": entities,
            "relations": relations,
            "overall_confidence": data.get("overall_confidence", 0.5),
        }


# ═══════════════════════════════════════════════════════════
# Step 3: Draft YAML Writer
# ═══════════════════════════════════════════════════════════

class DraftYamlWriter:
    """Write extracted entities/relations as draft YAML for expert review."""

    DRAFT_DIR = os.path.expanduser("~/.aiplat/ontologies/drafts")

    def __init__(self):
        os.makedirs(self.DRAFT_DIR, exist_ok=True)

    def write(self, result: ExtractionResult) -> str:
        """Write the extraction result to a draft YAML file. Returns file path."""
        import yaml

        safe_name = re.sub(r'[^\w\-]', '_', result.source_doc)[:40]
        path = os.path.join(self.DRAFT_DIR, f"{safe_name}_{result.extraction_id}.yaml")

        classes = {}
        relations = []
        for e in result.entities:
            cls_key = f"extracted_{e.class_type}"
            if cls_key not in classes:
                classes[cls_key] = {
                    "label": e.class_type,
                    "description": f"从文档自动抽取的{e.class_type}",
                    "required_fields": ["name"],
                    "extracted_from": result.source_doc,
                }
            # Track entities as YAML instances
            entities_list = classes[cls_key].setdefault("_entities", [])
            entities_list.append({
                "name": e.name,
                "confidence": e.confidence,
                "evidence": e.evidence[:200],
            })

        for r in result.relations:
            relations.append({
                "source": r.source_entity,
                "type": r.relation_type,
                "target": r.target_entity,
                "confidence": r.confidence,
                "evidence": r.evidence[:200],
            })

        draft_data = {
            "draft": True,
            "extraction_id": result.extraction_id,
            "domain_id": result.domain_id,
            "source_doc": result.source_doc,
            "overall_confidence": result.overall_confidence,
            "created_at": result.created_at,
            "classes": classes,
            "extracted_relations": relations,
        }

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(draft_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

        logger.info("Draft YAML written: %s (%d entities, %d relations)", path,
                     len(result.entities), len(result.relations))
        return path


# ═══════════════════════════════════════════════════════════
# Pipeline orchestrator
# ═══════════════════════════════════════════════════════════

class ExtractionPipeline:
    """Full pipeline: ingest → extract → route → write."""

    def __init__(self):
        self.ingestor = DocumentIngestor()
        self.extractor = EntityExtractor()
        self.writer = DraftYamlWriter()

    async def run(self, text: str, doc_name: str = "uploaded_doc",
                  domain_id: str = "default") -> List[ExtractionResult]:
        """Run full extraction pipeline on a document. Returns results by confidence tier."""
        chunks = self.ingestor.ingest(text, doc_name)
        logger.info("Document '%s' split into %d chunks", doc_name, len(chunks))

        all_entities: List[ExtractedEntity] = []
        all_relations: List[ExtractedRelation] = []
        total_confidence = 0.0
        chunk_count = 0

        for chunk in chunks:
            parsed = await self.extractor.extract(chunk, domain_id)
            entities = parsed.get("entities", [])
            relations = parsed.get("relations", [])
            conf = parsed.get("overall_confidence", 0.0)

            all_entities.extend(entities)
            all_relations.extend(relations)
            total_confidence += conf
            chunk_count += 1

        avg_conf = total_confidence / max(chunk_count, 1)
        extraction_id = str(uuid.uuid4())[:12]

        result = ExtractionResult(
            extraction_id=extraction_id,
            domain_id=domain_id,
            source_doc=doc_name,
            entities=all_entities,
            relations=all_relations,
            overall_confidence=round(avg_conf, 3),
            status=self._route_status(avg_conf),
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

        if result.status in ("auto_accepted", "pending"):
            path = self.writer.write(result)
            result.draft_yaml_path = path
            logger.info("Extraction %s → %s (confidence=%.2f, %d entities, %d relations)",
                        extraction_id, result.status, avg_conf, len(all_entities), len(all_relations))

        # ── P0-3 接线：抽取结果 → kb_graph（文档三元组）+ kb_embeddings（向量库）──
        # Best-effort: 无 LLM/embedding 模型时静默跳过，不阻断抽取主流程。
        try:
            await self._wire_kb(all_relations, chunks, doc_name, tenant_id)
        except Exception:
            logger.debug("kb wiring (graph/vector) failed", exc_info=True)
        return [result]

    async def _wire_kb(self, relations, chunks, doc_name, tenant_id) -> None:
        """P0-3: persist extraction output into kb_graph + kb_embeddings.

        - kb_graph: extracted relations as doc-level triples, consumed by
          graph_enhance_query (doc expansion in syscall retrieval).
        - kb_embeddings: chunk embeddings via embed_texts_semantic; skipped
          per-chunk when no embedding is produced (no model / hash backend).
        """
        import uuid as _uuid
        # 1. kb_graph: doc-level triples from extracted relations
        triples = [
            {"source_entity": r.source_entity, "relation": r.relation_type,
             "target_entity": r.target_entity}
            for r in relations
        ]
        if triples:
            from core.harness.knowledge.graph import _store_triples
            _store_triples(tenant_id, doc_name, triples)
            logger.info("kb_graph: %d triples stored for '%s' (tenant=%s)",
                        len(triples), doc_name, tenant_id)
        # 2. kb_embeddings: chunk-level vector entries
        if chunks:
            from core.harness.knowledge.embedder import embed_texts_semantic
            from core.harness.knowledge.sqlite_retriever import SqliteEmbeddingRetriever
            from core.harness.knowledge.types import (
                KnowledgeEntry, KnowledgeMetadata, KnowledgeSource, KnowledgeType)
            embeds = embed_texts_semantic([c["text"] for c in chunks])
            entries = []
            for i, chunk in enumerate(chunks):
                embedding = (embeds[i] if embeds and i < len(embeds) and embeds[i] else None)
                entries.append(KnowledgeEntry(
                    id=str(_uuid.uuid4()), type=KnowledgeType.DOCUMENT,
                    content=chunk["text"], title=doc_name, embedding=embedding,
                    metadata=KnowledgeMetadata(source=KnowledgeSource.SYSTEM,
                                               tags=[tenant_id])))
            retriever = SqliteEmbeddingRetriever(tenant_id=tenant_id)
            await retriever.add_batch(entries)
            with_emb = sum(1 for e in entries if e.embedding)
            logger.info("kb_embeddings: %d/%d chunks stored (tenant=%s)",
                        with_emb, len(entries), tenant_id)

    def _route_status(self, confidence: float) -> str:
        if confidence >= 0.85:
            return "auto_accepted"
        elif confidence >= 0.60:
            return "pending"
        return "rejected"


# ═══════════════════════════════════════════════════════════
# Pending extractions store (SQLite, same as execution_store)
# ═══════════════════════════════════════════════════════════

class PendingExtractionStore:
    """Persist pending extractions for FDE workbench review."""

    def __init__(self, db_path: str = "./data/execution_store.db"):
        self.db_path = db_path

    async def initialize(self) -> None:
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS pending_extractions (
                    extraction_id TEXT PRIMARY KEY,
                    domain_id TEXT,
                    source_doc TEXT,
                    overall_confidence REAL,
                    entity_count INTEGER,
                    relation_count INTEGER,
                    status TEXT DEFAULT 'pending',
                    draft_yaml_path TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            await db.commit()

    async def save(self, result: ExtractionResult) -> None:
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO pending_extractions
                (extraction_id, domain_id, source_doc, overall_confidence,
                 entity_count, relation_count, status, draft_yaml_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.extraction_id,
                result.domain_id,
                result.source_doc,
                result.overall_confidence,
                len(result.entities),
                len(result.relations),
                result.status,
                result.draft_yaml_path,
            ))
            await db.commit()

    async def list_pending(self, domain_id: str = "") -> List[Dict[str, Any]]:
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if domain_id:
                async with db.execute(
                    "SELECT * FROM pending_extractions WHERE domain_id=? AND status='pending' ORDER BY created_at DESC",
                    (domain_id,),
                ) as cur:
                    return [dict(r) for r in await cur.fetchall()]
            else:
                async with db.execute(
                    "SELECT * FROM pending_extractions WHERE status='pending' ORDER BY created_at DESC"
                ) as cur:
                    return [dict(r) for r in await cur.fetchall()]

    async def confirm(self, extraction_id: str) -> bool:
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "UPDATE pending_extractions SET status='confirmed' WHERE extraction_id=?",
                (extraction_id,),
            )
            await db.commit()
            return cur.rowcount > 0

    async def reject(self, extraction_id: str) -> bool:
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "UPDATE pending_extractions SET status='rejected' WHERE extraction_id=?",
                (extraction_id,),
            )
            await db.commit()
            return cur.rowcount > 0
