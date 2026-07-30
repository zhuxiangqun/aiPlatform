"""
Cross-Domain Entity Resolver (Phase 2, 2026-07-30).

Three-stage matching:
  1. Exact key match (phone, namespace, custom_id) — weight 0.6
  2. Name similarity (Jaro-Winkler, threshold 0.85) — weight 0.25
  3. Embedding cosine (InfraEmbeddingAdapter) — weight 0.15

Reads cross_domain_views from registry.json.
Stores resolved edges in GraphIndex.cross_domain_edges.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REGISTRY_PATH = os.path.expanduser("~/.aiplat/ontologies/registry.json")


@dataclass
class CrossDomainCandidate:
    left: Dict[str, Any]   # {domain, class, id, name}
    right: Dict[str, Any]  # {domain, class, id, name}
    score: float = 0.0
    evidence: Dict[str, Any] = field(default_factory=dict)
    strategy: str = ""      # exact | fuzzy | embedding


class CrossDomainResolver:
    """Scan entities across domains and propose merge candidates."""

    def __init__(self, registry_path: str = REGISTRY_PATH):
        self.registry_path = os.path.expanduser(registry_path)
        self._cache: Dict[str, Any] = {}
        self._cache_ts = 0.0
        self._cache_ttl = 120  # 2 min

    def _load_views(self) -> Dict[str, Any]:
        """Load cross_domain_views from registry.json with TTL cache."""
        now = time.time()
        if self._cache and (now - self._cache_ts < self._cache_ttl):
            return self._cache
        try:
            if not os.path.exists(self.registry_path):
                return {}
            with open(self.registry_path, encoding="utf-8") as f:
                data = json.load(f)
            self._cache = data.get("cross_domain_views", {})
            self._cache_ts = now
        except Exception:
            logger.warning("Failed to load registry cross_domain_views", exc_info=True)
        return self._cache

    def find_candidates(self, view_name: str, tenant_id: str = "default") -> List[CrossDomainCandidate]:
        """Find cross-domain merge candidates for a registered view.
        tenant_id scopes the search to a specific tenant partition."""
        views = self._load_views()
        view_def = views.get(view_name)
        if not view_def:
            logger.warning("View '%s' not found in registry.json cross_domain_views", view_name)
            return []

        sources = view_def.get("sources", [])
        if len(sources) < 2:
            return []

        ds1, ds2 = sources[0], sources[1]
        strategy = view_def.get("match_strategy", {})

        entities1 = self._load_entities(ds1["domain"], ds1.get("class", ""), tenant_id)
        entities2 = self._load_entities(ds2["domain"], ds2.get("class", ""), tenant_id)
        logger.info("CrossDomainResolver: %d entities from %s, %d from %s",
                     len(entities1), ds1["domain"], len(entities2), ds2["domain"])

        candidates = []
        for e1 in entities1:
            for e2 in entities2:
                score, strategy_used, evidence = self._compute_match(e1, e2, strategy, ds1, ds2)
                min_conf = strategy.get("min_confidence", 0.70)
                if score >= min_conf:
                    candidates.append(CrossDomainCandidate(
                        left={"domain": ds1["domain"], "class": ds1.get("class", ""),
                              "id": e1.get("id", e1.get("name", "")), "name": e1.get("name", "")},
                        right={"domain": ds2["domain"], "class": ds2.get("class", ""),
                               "id": e2.get("id", e2.get("name", "")), "name": e2.get("name", "")},
                        score=round(score, 4),
                        evidence=evidence,
                        strategy=strategy_used,
                    ))

        return sorted(candidates, key=lambda x: x.score, reverse=True)

    def _compute_match(self, e1: Dict, e2: Dict, strategy: Dict,
                       ds1: Dict, ds2: Dict) -> tuple[float, str, Dict]:
        """Compute multi-strategy match score. Returns (score, strategy_name, evidence)."""
        scores = []
        evidence = {}

        # Strategy 1: exact key match (weight 0.60)
        primary = strategy.get("primary", "")
        primary_keys = [k.strip() for k in primary.split("||") if k.strip()]
        exact_matched = False
        for key in primary_keys:
            v1 = str(e1.get(key, "")).strip()
            v2 = str(e2.get(key, "")).strip()
            if v1 and v2 and v1 == v2:
                evidence["exact_match"] = f"{key}: {v1} == {v2}"
                scores.append(("exact", 0.60))
                exact_matched = True
                break

        # Strategy 2: name similarity (weight 0.25)
        secondary = strategy.get("secondary", "")
        if secondary:
            n1 = str(e1.get("name", "")).strip()
            n2 = str(e2.get("name", "")).strip()
            if n1 and n2:
                sim = self._name_similarity(n1, n2)
                evidence["name_similarity"] = f"'{n1}' ↔ '{n2}' = {sim:.3f}"
                if sim >= 0.85:
                    scores.append(("fuzzy", 0.25 * min(1, sim)))
                elif sim >= 0.70:
                    scores.append(("fuzzy", 0.25 * (sim * 0.5)))

        # Strategy 3: embedding cosine (weight 0.15)
        tertiary = strategy.get("tertiary", "")
        if tertiary and "embedding" in tertiary:
            desc1 = e1.get("description", e1.get("name", ""))
            desc2 = e2.get("description", e2.get("name", ""))
            if desc1 and desc2:
                cos = self._embedding_similarity(desc1, desc2)
                evidence["embedding"] = f"cosine={cos:.3f}"
                if cos >= 0.78:
                    scores.append(("embedding", 0.15 * min(1, cos / 0.90)))

        total = sum(s for _, s in scores)
        strategy_names = "+".join(n for n, _ in scores) if scores else "none"
        return total, strategy_names, evidence

    def _name_similarity(self, a: str, b: str) -> float:
        """Jaro-Winkler string similarity."""
        try:
            import jellyfish
            return jellyfish.jaro_winkler_similarity(a, b)
        except ImportError:
            # Fallback: simple character overlap
            set_a = set(a)
            set_b = set(b)
            return len(set_a & set_b) / max(len(set_a | set_b), 1)

    def _embedding_similarity(self, a: str, b: str) -> float:
        """Cosine similarity via InfraEmbeddingAdapter."""
        try:
            from core.harness.utils.model_injection import create_selected_adapter
            adapter = create_selected_adapter("embedding")
            emb_a = adapter.embed(a)
            emb_b = adapter.embed(b)

            dot = sum(x * y for x, y in zip(emb_a, emb_b))
            norm_a = sum(x * x for x in emb_a) ** 0.5
            norm_b = sum(x * x for x in emb_b) ** 0.5
            return dot / max(norm_a * norm_b, 1e-8)
        except Exception:
            return 0.0

    @staticmethod
    def _load_entities(domain_id: str, class_name: str, tenant_id: str = "default") -> List[Dict[str, Any]]:
        """Load all entities of a given class from GraphIndex."""
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            g = GraphIndex.load(domain_id, tenant_id)
            if class_name:
                return g.get_entities_by_class(class_name) or []
            return list(g._nodes.values())
        except Exception:
            return []

    @staticmethod
    def resolve(view_name: str, left_id: str, right_id: str,
                left_domain: str, right_domain: str,
                confidence: float = 1.0) -> bool:
        """Create a cross-domain edge between two entities."""
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            g_left = GraphIndex.load(left_domain)
            g_right = GraphIndex.load(right_domain)

            # Store cross-domain edge as metadata in both graphs
            edge_data = {
                "view": view_name,
                "confidence": confidence,
                "resolved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

            # Write edge into both graphs
            g_left.add_entity_property(left_id, "_cross_domain", {
                "target_domain": right_domain,
                "target_id": right_id,
                "aligned_to": right_domain,
                **edge_data,
            })
            g_right.add_entity_property(right_id, "_cross_domain", {
                "target_domain": left_domain,
                "target_id": left_id,
                "aligned_to": left_domain,
                **edge_data,
            })

            logger.info("CrossDomainResolver: resolved %s/%s ↔ %s/%s (view=%s, confidence=%.2f)",
                         left_domain, left_id, right_domain, right_id, view_name, confidence)
            return True
        except Exception:
            logger.error("Failed to resolve cross-domain edge", exc_info=True)
            return False


# ═══════════════════════════════════════════════════════════
# Registry bootstrap — seed cross_domain_views config
# ═══════════════════════════════════════════════════════════

def seed_cross_domain_config() -> bool:
    """Add default cross_domain_views to registry.json if missing."""
    if not os.path.exists(REGISTRY_PATH):
        return False

    try:
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            reg = json.load(f)

        if "cross_domain_views" in reg:
            return False  # already exists

        reg["cross_domain_views"] = {
            "unified_customer": {
                "label": "统一客户视图",
                "description": "将锁安的客户现场与 FDE 的客户实体关联",
                "sources": [
                    {"domain": "lock-service", "class": "客户现场", "key_fields": ["phone", "name", "custom_id"]},
                    {"domain": "fde-delivery", "class": "客户", "key_fields": ["namespace", "email", "company_name"]},
                ],
                "match_strategy": {
                    "primary": "phone || namespace",
                    "secondary": "name_similarity",
                    "tertiary": "embedding_cos",
                    "min_confidence": 0.70,
                },
                "enable_auto_link": False,
            }
        }
        reg.setdefault("cross_domain_actions", {})

        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=2)

        logger.info("Seeded cross_domain_views in registry.json")
        return True
    except Exception:
        logger.warning("Failed to seed cross_domain config", exc_info=True)
        return False
