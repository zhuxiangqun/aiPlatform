"""
Knowledge Synthesizer — Generate structured Wiki pages from GraphIndex data.

Three synthesis types:
  1. InferenceChain: GraphInference inferred edges → reasoning chain Wiki page
  2. FactCard: HyperEdge context_description → fact card Wiki page  
  3. CrossDocConclusion: 3+ hyperedges share same entity → merged conclusion page

All output goes to the Wiki store via write_page(), preserving editability and traceability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from collections import defaultdict


@dataclass
class SynthesisResult:
    pages_written: int = 0
    chains: List[Dict[str, Any]] = field(default_factory=list)
    fact_cards: List[Dict[str, Any]] = field(default_factory=list)
    conclusions: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pages_written": self.pages_written,
            "chains": self.chains,
            "fact_cards": self.fact_cards,
            "conclusions": self.conclusions,
            "errors": self.errors,
        }


class KnowledgeSynthesizer:
    """Synthesize graph knowledge into editable Wiki pages."""

    def __init__(self, graph):
        self._graph = graph

    def synthesize(self, *, domain_id: str = "default", write_to_wiki: bool = True) -> SynthesisResult:
        """Run all three synthesis types."""
        result = SynthesisResult()

        # 1. Inference chains → reasoning chain pages
        for nid, node in self._graph._nodes.items():
            for edge in node.out_edges:
                if not getattr(edge, "inferred", False):
                    continue
                page = self._build_chain_page(edge, node)
                result.chains.append(page)
                if write_to_wiki:
                    try:
                        self._write_page(page, domain_id)
                        result.pages_written += 1
                    except Exception as e:
                        result.errors.append(f"chain {page['title']}: {e}")

        # 2. HyperEdge fact cards
        for he_id, he in self._graph._hyperedges.items():
            page = self._build_fact_card(he)
            result.fact_cards.append(page)
            if write_to_wiki:
                try:
                    self._write_page(page, domain_id)
                    result.pages_written += 1
                except Exception as e:
                    result.errors.append(f"fact {page['title']}: {e}")

        # 3. Cross-document conclusions (entities in ≥3 hyperedges)
        entity_he_count: dict = defaultdict(int)
        entity_he_list: dict = defaultdict(list)
        for he_id, he in self._graph._hyperedges.items():
            for eid in he.entity_ids:
                entity_he_count[eid] += 1
                entity_he_list[eid].append(he_id)
        for eid, count in entity_he_count.items():
            if count >= 3:
                page = self._build_conclusion(eid, entity_he_list[eid])
                result.conclusions.append(page)
                if write_to_wiki:
                    try:
                        self._write_page(page, domain_id)
                        result.pages_written += 1
                    except Exception as e:
                        result.errors.append(f"conclusion {page['title']}: {e}")

        return result

    # ── Page builders ─────────────────────────────────────────────

    def _build_chain_page(self, edge, source_node) -> dict:
        """Build a reasoning chain Wiki page from an inferred edge."""
        tgt_node = self._graph.get_node(edge.target_id)
        title = f"{source_node.entity_name} →({edge.relation_label})→ {tgt_node.entity_name if tgt_node else edge.target_id}"
        rule = getattr(edge, "rule_name", "inferred")
        conf = getattr(edge, "inferred_confidence", edge.confidence)

        body = f"""# 推理链：{title}

## 推理步骤
**来源节点**: {source_node.entity_name} ({source_node.class_name})  
**目标节点**: {tgt_node.entity_name if tgt_node else edge.target_id} ({tgt_node.class_name if tgt_node else 'unknown'})  
**推断关系**: {edge.relation_label}  
**推理规则**: {rule}  
**置信度**: {conf:.2f}

## 结论
通过 {rule} 推理规则，{source_node.entity_name} 与 {tgt_node.entity_name if tgt_node else edge.target_id} 之间存在推断关系 '{edge.relation_label}'。
"""
        return {
            "title": title[:80],
            "body": body,
            "category": "synthesis",
            "tags": ["synthesized", "inferred", source_node.class_name, (tgt_node.class_name if tgt_node else "unknown")],
            "summary": f"推理链: {source_node.entity_name} → {edge.relation_label} → {tgt_node.entity_name if tgt_node else edge.target_id}",
            "confidence": conf,
            "source_instances": [source_node.entity_name, tgt_node.entity_name if tgt_node else edge.target_id],
            "synthesis_type": "reasoning_chain",
        }

    def _build_fact_card(self, he) -> dict:
        """Build a fact card Wiki page from a HyperEdge."""
        entity_names = []
        for eid in he.entity_ids:
            node = self._graph.get_node(eid)
            entity_names.append(node.entity_name if node else eid)
        title = " & ".join(entity_names[:3]) + ("等" if len(entity_names) > 3 else "") + " 事实卡"
        body = f"""# 事实卡：{title}

## 关联实体
{chr(10).join(f"- {n}" for n in entity_names)}

## 事项描述
{he.context_description or '（无描述）'}

## 来源
- 事件ID: {he.event_id}
- 来源Chunk: {he.source_chunk_id}
- 置信度: {he.confidence:.2f}
"""
        return {
            "title": title[:80],
            "body": body,
            "category": "synthesis",
            "tags": ["synthesized", "fact_card", "hyperedge"],
            "summary": f"{len(entity_names)}个关联实体的事实卡: {', '.join(entity_names[:3])}",
            "confidence": he.confidence,
            "source_instances": entity_names,
            "synthesis_type": "fact_card",
        }

    def _build_conclusion(self, entity_id: str, he_ids: List[str]) -> dict:
        """Build a cross-document conclusion page."""
        node = self._graph.get_node(entity_id)
        name = node.entity_name if node else entity_id
        title = f"{name} 综合结论"

        he_summaries = []
        for he_id in he_ids[:5]:
            he = self._graph.get_hyperedge(he_id)
            if he:
                entities = []
                for eid in he.entity_ids:
                    n = self._graph.get_node(eid)
                    entities.append(n.entity_name if n else eid)
                he_summaries.append(f"- **{he.event_id}**: {' | '.join(entities[:3])}\n  {he.context_description[:100]}")

        body = f"""# {title}

## 关联事实卡 ({len(he_ids)}个)
{''.join(he_summaries)}

## 结论
实体 '{name}' 在 {len(he_ids)} 个不同事实卡中出现，表明其在知识体系中具有中心地位。
建议进一步审查相关事实卡的完整性和一致性。
"""
        return {
            "title": title[:80],
            "body": body,
            "category": "synthesis",
            "tags": ["synthesized", "conclusion", "cross_document"],
            "summary": f"{name}出现在{len(he_ids)}个事实卡中的综合结论",
            "confidence": min(0.5 + len(he_ids) * 0.1, 0.95),
            "source_instances": [name],
            "synthesis_type": "comprehensive_conclusion",
        }

    def _write_page(self, page: dict, domain_id: str):
        """Write a synthesized page to the Wiki store."""
        from core.harness.knowledge.wiki_engine import write_page
        write_page(
            page["title"],
            page["body"],
            category=page.get("category", "synthesis"),
            tags=page.get("tags", []),
            summary=page.get("summary", "")[:200],
        )
