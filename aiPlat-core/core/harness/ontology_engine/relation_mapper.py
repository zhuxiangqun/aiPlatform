"""
RelationMapper — 从文档结构和语义中识别本体实例间的关系类型。

策略:
  1. 基于同现: 同一 chunk 内的实体 → 可能有关系
  2. 基于 LLM: 发送 entity pairs + 关系类型定义 → LLM 判断关系类型
  3. 基于文档结构: 嵌套的 heading 层级 → 父子关系
"""

from __future__ import annotations

import json as _json
import re as _re
from typing import Any, Dict, List, Optional, Set, Tuple

from core.harness.knowledge.ontology_loader import OntologyDomain


class RelationMapper:
    """Map relationships between ontology instances."""

    def __init__(self, domain: OntologyDomain):
        self._domain = domain
        self._relation_types = self._build_relation_types()

    def _build_relation_types(self) -> Dict[str, Dict[str, Any]]:
        """Build relation type definitions from object_properties."""
        types = {}
        for prop in self._domain.object_properties:
            types[prop.label] = {
                "name": prop.label,
                "uri": prop.uri,
                "domain": prop.domain,
                "range": prop.range,
                "inverse": prop.inverse_of or prop.inverse_label or "",
                "transitive": prop.is_transitive,
                "symmetric": prop.is_symmetric,
            }
        return types

    def detect_co_occurrence(
        self,
        instances: List[Dict[str, Any]],
        chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Detect potential relationships via co-occurrence in same chunk.

        Returns: [{"source": "RAG", "target": "模型幻觉", "candidate_types": ["solves"], "confidence": 0.7}, ...]
        """
        relations = []

        # Group instances by chunk_id
        chunk_groups: Dict[str, List[Dict]] = {}
        for inst in instances:
            cid = inst.get("chunk_id", "default")
            if cid not in chunk_groups:
                chunk_groups[cid] = []
            chunk_groups[cid].append(inst)

        for cid, group in chunk_groups.items():
            for i, inst_a in enumerate(group):
                for inst_b in group[i + 1:]:
                    candidates = self._infer_relation_types(
                        inst_a.get("class_name", ""),
                        inst_b.get("class_name", ""),
                    )
                    if candidates:
                        relations.append({
                            "source": inst_a.get("entity_text", ""),
                            "target": inst_b.get("entity_text", ""),
                            "candidate_types": candidates,
                            "confidence": 0.7,
                            "detection": "co_occurrence",
                            "chunk_id": cid,
                        })

        return relations

    def _infer_relation_types(self, class_a: str, class_b: str) -> List[str]:
        """Infer possible relation types between two class instances."""
        candidates = []
        for rel_name, rel_def in self._relation_types.items():
            domains = rel_def.get("domain", [])
            ranges = rel_def.get("range", [])
            # A→B
            if class_a in domains and class_b in ranges:
                candidates.append(rel_name)
            # B→A (inverse)
            if class_b in domains and class_a in ranges:
                candidates.append(f"{rel_name}(inverse)")
        return candidates

    def build_llm_verification_prompt(
        self,
        pairs: List[Dict[str, Any]],
        instances: List[Dict[str, Any]],
    ) -> str:
        """Build LLM prompt to verify and type relationships between instance pairs.

        Dynamically reads relation definitions from domain.
        """
        # Build instance context
        instance_lines = []
        for inst in instances:
            props = inst.get("properties", {})
            desc = props.get("description", "") or props.get("definition", "") or ""
            name = inst.get("entity_text", inst.get("properties", {}).get("name", "?"))
            cls = inst.get("class_name", "")
            instance_lines.append(f"  [{cls}] {name}: {str(desc)[:200]}")

        # Build relation types
        rel_lines = []
        for rel_name, rel_def in self._relation_types.items():
            dom = ", ".join(rel_def.get("domain", []))
            rng = ", ".join(rel_def.get("range", []))
            inv = rel_def.get("inverse", "")
            rel_lines.append(f"  - {rel_name}: {dom} → {rng}" + (f" (反向: {inv})" if inv else ""))

        # Build pair list
        pair_lines = []
        for p in pairs:
            pair_lines.append(f"  {p.get('source', '?')} ←→ {p.get('target', '?')}")

        return (
            f"判断以下实体对之间是否存在关系，并指定关系类型。\n\n"
            f"实体列表:\n{chr(10).join(instance_lines)}\n\n"
            f"可用关系类型:\n{chr(10).join(rel_lines)}\n\n"
            f"待判断的实体对:\n{chr(10).join(pair_lines)}\n\n"
            f'输出JSON: {{"relations":[{{"source":"实体A","target":"实体B","type":"关系类型","confidence":0.85,"reason":"理由"}}]}}\n'
            f"规则: 如果无明显关系,不要强行关联。来源和目标必须使用实体列表中的名称。关系类型必须从可用列表中选择。"
        )

    async def verify_with_llm(
        self,
        pairs: List[Dict[str, Any]],
        instances: List[Dict[str, Any]],
        *,
        model_name: str = "",
        timeout: int = 60,
    ) -> List[Dict[str, Any]]:
        """Use LLM to verify and type relationships."""
        from core.harness.utils.model_injection import best_model_for_purpose, create_selected_adapter
        from core.adapters.llm.base import LLMConfig

        prompt = self.build_llm_verification_prompt(pairs, instances)
        model = model_name or best_model_for_purpose("agent_creation")
        adapter = create_selected_adapter(model_name=model)
        config = LLMConfig(model="", timeout=timeout)

        try:
            resp = await adapter.generate(
                [{"role": "user", "content": prompt}],
                config=config,
            )
            content = resp.content if hasattr(resp, 'content') else str(resp)
            return self._parse_relations(content)
        except Exception:
            return []

    def _parse_relations(self, content: str) -> List[Dict[str, Any]]:
        clean = content.strip()
        if clean.startswith("```"):
            clean = _re.sub(r'^```\w*\n?', '', clean)
            clean = _re.sub(r'\n?```$', '', clean)
        match = _re.search(r'\{[\s\S]*\}', clean)
        if not match:
            return []
        try:
            data = _json.loads(match.group(0))
            return data.get("relations", []) if isinstance(data, dict) else []
        except (_json.JSONDecodeError, TypeError):
            return []
