"""
ClassMapper — 文本实体 → 域本体类映射。

策略: 从 YAML 域本体动态读取 class label + description 作为关键词，
     计算文本 overlap → 排序 → 返回最佳匹配。
     零硬编码——所有匹配规则来自配置。
"""

from __future__ import annotations

import re as _re
from typing import Any, Dict, List, Optional, Tuple

from core.harness.knowledge.knowledge_ontology import OntologyClass
from core.harness.knowledge.ontology_loader import OntologyDomain, load_ontology_from_yaml


class ClassMapper:
    """Map text entities to ontology domain classes."""

    def __init__(self, domain: OntologyDomain):
        self._domain = domain
        # Build keyword index: {keyword_string → class_label}
        self._keyword_index: Dict[str, List[str]] = self._build_keyword_index()

    def _build_keyword_index(self) -> Dict[str, List[str]]:
        """Build inverted index from class labels + descriptions → keywords."""
        index: Dict[str, List[str]] = {}
        for cls in self._domain.classes:
            keywords = set()
            # Add label words (split Chinese+English)
            for word in self._tokenize(cls.label):
                if len(word) >= 2:
                    keywords.add(word.lower())
            # Add description words
            for word in self._tokenize(cls.description):
                if len(word) >= 2:
                    keywords.add(word.lower())
            for kw in keywords:
                if kw not in index:
                    index[kw] = []
                index[kw].append(cls.label)
        return index

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize mixed Chinese+English text."""
        tokens = []
        # Chinese: character bigrams
        chinese = _re.findall(r'[\u4e00-\u9fff]+', text)
        for seg in chinese:
            for i in range(len(seg) - 1):
                tokens.append(seg[i:i+2])
        # English: word tokens
        eng = _re.findall(r'[a-zA-Z]+', text)
        tokens.extend(w.lower() for w in eng if len(w) >= 2)
        return tokens

    def map_entities(
        self,
        entities: List[Dict[str, Any]],
        chunk_text: str = "",
        threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Map a list of named entities to ontology classes.

        Args:
            entities: [{"text": "RAG", "type": "TECHNIQUE"}, ...]
            chunk_text: full chunk text for context scoring
            threshold: minimum confidence to accept a mapping

        Returns:
            [{"entity_text": "RAG", "class_name": "AITechnique", "confidence": 0.92, "matched_keywords": ["检索", "方法"]}, ...]
        """
        results = []
        for ent in entities:
            ent_text = str(ent.get("text", "") or "").strip()
            if not ent_text:
                continue
            scores = self._score_classes(ent_text, chunk_text)
            if not scores:
                continue
            best_class = max(scores, key=scores.get)
            best_score = scores[best_class]
            if best_score >= threshold:
                # Find which keywords matched
                matched_kw = []
                tokens = self._tokenize(ent_text)
                for cls in self._domain.classes:
                    if cls.label == best_class:
                        for t in tokens:
                            if t.lower() in cls.label.lower() or t.lower() in cls.description.lower():
                                matched_kw.append(t)
                        break
                results.append({
                    "entity_text": ent_text,
                    "class_name": best_class,
                    "confidence": round(best_score, 3),
                    "matched_keywords": matched_kw[:5],
                    "alternatives": sorted(
                        [(c, round(s, 3)) for c, s in scores.items() if c != best_class and s >= threshold],
                        key=lambda x: -x[1],
                    )[:2],
                })
        return results

    def _score_classes(self, entity_text: str, context_text: str) -> Dict[str, float]:
        """Score each class against entity text + context.
        
        Uses sigmoid-like normalization to produce well-distributed confidence scores
        across [0.15, 0.95] range, avoiding the collapse into [0.6-0.8) seen with min-max.
        """
        scores: Dict[str, float] = {}
        tokens = self._tokenize(entity_text)
        ctx_tokens = self._tokenize(context_text)[:30] if context_text else []

        for cls in self._domain.classes:
            score = 0.0
            label_low = cls.label.lower()
            desc_low = cls.description.lower()
            # 1) Entity token matches class label/description
            for t in tokens:
                if t in label_low:
                    score += 3.0
                elif t in desc_low:
                    score += 2.0
            # 2) Context token matches (weaker signal)
            for ct in ctx_tokens[:10]:
                if ct in label_low:
                    score += 0.5
                elif ct in desc_low:
                    score += 0.3
            if score > 0:
                scores[cls.label] = score

        if not scores:
            return scores

        # ── Sigmoid-normalize: expands the narrow band into [0.15, 0.95] ──
        max_s = max(scores.values())
        for k in scores:
            raw_ratio = scores[k] / max(max_s, 0.001)
            # Sigmoid: map [0,1] → [0.15, 0.95] with good spread
            # tanh approach with tunable sharpness
            sharpness = 3.0
            normalized = 1.0 / (1.0 + 2.718 ** (-sharpness * (raw_ratio - 0.4)))
            # Scale to [0.15, 0.95]
            scores[k] = round(0.15 + normalized * 0.80, 3)

        return scores

    def classify_text(
        self,
        text: str,
        threshold: float = 0.5,
    ) -> Optional[str]:
        """Classify raw text to the best ontology class.

        Returns class_name or None.
        """
        tokens = self._tokenize(text)
        if not tokens:
            return None
        scores = self._score_classes_text(tokens)
        if not scores:
            return None
        best = max(scores, key=scores.get)
        return best if scores[best] >= threshold else None

    def _score_classes_text(self, tokens: List[str]) -> Dict[str, float]:
        """Score classes against word tokens (no entity extraction)."""
        scores: Dict[str, float] = {}
        for cls in self._domain.classes:
            score = 0.0
            for t in tokens:
                if t.lower() in cls.label.lower():
                    score += 2.0
                elif t.lower() in cls.description.lower():
                    score += 1.0
            if score > 0:
                scores[cls.label] = score
        if scores:
            max_s = max(scores.values())
            for k in scores:
                scores[k] = scores[k] / max_s  # normalize
        return scores
