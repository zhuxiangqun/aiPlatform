"""
DomainRouter — 3-tier config-driven domain classifier.

Hot-loadable: write YAML + registry.json = new domain auto-recognized.
Zero hardcoded keywords. All routing info from ontology YAMLs.

Tier 1 (<1ms):  label match — invert class.labels + categories + synonyms
Tier 2 (~50ms): embedding cosine similarity — weighted domain vectors
Tier 3 (~300ms): LLM binary classification — rare edge cases only

Callers:
  - core/apps/agents/materials_chat.py (primary — classify & config)
  - core/harness/syscalls/retrieval.py (collection_id ↔ domain_id resolution)
  - core/harness/knowledge/ontology_query_mapper.py (domain_id resolution)
"""

from __future__ import annotations
import logging
import sys as _sys

import json
import os
from typing import Any, Dict, List, Optional

import numpy as np


class DomainRouter:
    """3-tier config-driven domain classifier."""

    def __init__(self):
        self._label_index: Dict[str, str] = {}           # label_lower → domain_id
        self._domain_vectors: Dict[str, np.ndarray] = {}  # domain_id → embedding
        self._built = False
        self._registry_cache: Optional[dict] = None
        self._llm_model = os.environ.get("AIPLAT_DOMAIN_ROUTER_MODEL", "qwen2.5-coder:7b")
        self._route_stats: Dict[str, int] = {"t1_hits": 0, "t2_hits": 0, "t3_hits": 0, "total": 0}

    # ═══════════════════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════════════════

    def classify(self, query: str) -> str:
        u"""3-tier domain classification. Returns domain_id string."""
        self._ensure_built()
        domains = self.list_domains()
        if len(domains) <= 1:
            return domains[0] if domains else "ai-knowledge"

        q = query.lower()

        # ── Tier 1: Label match (<1ms) ──
        for label, did in self._label_index.items():
            if len(label) >= 2 and label in q:
                self._route_stats["t1_hits"] += 1; self._route_stats["total"] += 1
                return did

        # ── Tier 2: Embedding cosine similarity (~50ms) ──
        qvec = self._embed(query)
        if qvec is None:
            did = self._llm_classify(query)
        if self._route_stats["total"] % 10 == 0:  # Log every 10 classifications
            import logging as _logging; _logging.warning(
                "route_stats: T1=%.0f%% T2=%.0f%% T3=%.0f%% (total=%d, LLM calls avoided=%d)",
                self._route_stats["t1_hits"]*100/max(self._route_stats["total"],1),
                self._route_stats["t2_hits"]*100/max(self._route_stats["total"],1), 
                self._route_stats["t3_hits"]*100/max(self._route_stats["total"],1),
                self._route_stats["total"],
                self._route_stats["t1_hits"] + self._route_stats["t2_hits"], file=_sys.stderr)
        return did

        best_did, best_score, runner_up = None, 0.0, 0.0
        for did, dvec in self._domain_vectors.items():
            norm = np.linalg.norm(qvec) * np.linalg.norm(dvec)
            score = float(np.dot(qvec, dvec) / (norm + 1e-8))
            if score > best_score:
                runner_up = best_score
                best_score = score
                best_did = did

        routing_cfg = self._load_registry().get("routing", {}).get("embedding", {})
        min_conf = routing_cfg.get("min_confidence", 0.4)
        min_margin = routing_cfg.get("min_margin", 0.08)

        if best_did and best_score >= min_conf and (best_score - runner_up) >= min_margin:
            self._route_stats["t2_hits"] += 1; self._route_stats["total"] += 1
            return best_did

        # ── Tier 3: LLM classification (~300ms, rare) ──
        self._route_stats["t3_hits"] += 1; self._route_stats["total"] += 1
        did = self._llm_classify(query)
        if self._route_stats["total"] % 10 == 0:  # Log every 10 classifications
            import logging as _logging; _logging.warning(
                "route_stats: T1=%.0f%% T2=%.0f%% T3=%.0f%% (total=%d, LLM calls avoided=%d)",
                self._route_stats["t1_hits"]*100/max(self._route_stats["total"],1),
                self._route_stats["t2_hits"]*100/max(self._route_stats["total"],1), 
                self._route_stats["t3_hits"]*100/max(self._route_stats["total"],1),
                self._route_stats["total"],
                self._route_stats["t1_hits"] + self._route_stats["t2_hits"], file=_sys.stderr)
        return did

    def route_stats(self) -> Dict[str, Any]:
        """Return routing tier hit distribution and estimated LLM cost savings."""
        total = max(self._route_stats["total"], 1)
        t1 = self._route_stats["t1_hits"]
        t2 = self._route_stats["t2_hits"]
        t3 = self._route_stats["t3_hits"]
        # T3 is ~100 tokens per call, T1/T2 are 0 tokens
        llm_calls_avoided = t1 + t2
        estimated_token_saved = llm_calls_avoided * 100
        return {
            "total": total,
            "t1_label_pct": round(100 * t1 / total, 1),
            "t2_embedding_pct": round(100 * t2 / total, 1),
            "t3_llm_pct": round(100 * t3 / total, 1),
            "llm_calls_avoided": llm_calls_avoided,
            "estimated_token_saved": estimated_token_saved,
        }

    def per_domain_cost(self, query: str) -> Dict[str, Any]:
        """Estimate routing cost per domain for the given query.
        
        Returns a breakdown of which tier each domain would use,
        and the estimated LLM token cost avoided by T1/T2 hits.
        """
        self._ensure_built()
        domains = self.list_domains()
        if len(domains) <= 1:
            return {"domains": 1, "tier": "n/a", "llm_call_needed": False}

        q = query.lower()
        breakdown = {}
        for did in domains:
            # T1 check
            for label, lid in self._label_index.items():
                if lid == did and len(label) >= 2 and label in q:
                    breakdown[did] = {"tier": "T1_label", "tokens": 0}
                    break
            else:
                # T2 check
                qvec = self._embed(query)
                if qvec is not None and did in self._domain_vectors:
                    dvec = self._domain_vectors[did]
                    import numpy as np
                    norm = np.linalg.norm(qvec) * np.linalg.norm(dvec)
                    score = float(np.dot(qvec, dvec) / (norm + 1e-8))
                    if score >= 0.4:
                        breakdown[did] = {"tier": "T2_embedding", "tokens": 0, "confidence": round(score, 3)}
                    else:
                        breakdown[did] = {"tier": "T3_llm", "tokens": 100, "confidence": round(score, 3)}
                else:
                    breakdown[did] = {"tier": "T3_llm", "tokens": 100, "reason": "no embedding available"}

        # Aggregate
        t3_count = sum(1 for v in breakdown.values() if v["tier"] == "T3_llm")
        llm_tokens_saved = (len(domains) - t3_count) * 100
        return {
            "domains": len(domains),
            "t3_calls_needed": t3_count,
            "estimated_llm_tokens_saved": llm_tokens_saved,
            "per_domain": breakdown,
        }

    def resolve(self, collection_id: str) -> str:
        u"""collection_id → domain_id via registry.json."""
        registry = self._load_registry()
        for did, cfg in registry.get("domains", {}).items():
            if cfg.get("collection_id") == collection_id:
                return did
        return collection_id

    def resolve_collection(self, domain_id: str) -> str:
        u"""domain_id → collection_id via registry.json."""
        return self.domain_config(domain_id).get("collection_id", domain_id)

    def domain_config(self, domain_id: str) -> dict:
        u"""Get full domain config from registry."""
        return self._load_registry().get("domains", {}).get(domain_id, {})

    def list_domains(self) -> List[str]:
        u"""All registered domain IDs."""
        return list(self._load_registry().get("domains", {}).keys())

    def fallback_domains(self) -> List[str]:
        u"""Supplementary domains for cross-domain fallback."""
        return self._load_registry().get("fallback_domains", ["default"])

    def register_domain(self, domain_id: str, config: dict):
        u"""Hot-register a new domain at runtime (no restart)."""
        registry_path = os.path.expanduser("~/.aiplat/ontologies/registry.json")
        registry = self._load_registry()
        registry["domains"][domain_id] = config
        os.makedirs(os.path.dirname(registry_path), exist_ok=True)
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)
        self._registry_cache = registry
        self._built = False  # force rebuild on next classify

    # ═══════════════════════════════════════════════════════════════
    # Internal
    # ═══════════════════════════════════════════════════════════════

    def _ensure_built(self):
        u"""Lazy-build T1 label index + T2 weighted domain vectors from all YAMLs."""
        if self._built:
            return

        from core.harness.knowledge.ontology_loader import load_ontology_from_yaml

        self._label_index.clear()
        self._domain_vectors.clear()

        for did in self.list_domains():
            path = os.path.expanduser(f"~/.aiplat/ontologies/{did}.yaml")
            if not os.path.exists(path):
                continue
            domain = load_ontology_from_yaml(path)

            # Tier 1: invert class labels + categories + synonyms → index
            for cls in domain.classes:
                names = [cls.label] + list(cls.allowed_categories or [])
                names += list(cls.synonyms or [])
                for name in names:
                    if isinstance(name, str):
                        self._label_index[name.lower()] = did

            # Tier 2: weighted domain embedding
            text = (f"{domain.name} {domain.description} " * 3)
            text += " ".join(c.label for c in domain.classes)
            vec = self._embed(text)
            if vec is not None:
                self._domain_vectors[did] = vec

        self._built = True

    def _embed(self, text: str) -> Optional[np.ndarray]:
        u"""Embed text via InfraEmbeddingAdapter (reuses loaded model)."""
        try:
            from core.harness.knowledge.embedder import embed_text_semantic
            vec = embed_text_semantic(text)
            if vec is None:
                return None
            arr = np.array(vec, dtype=np.float32)
            return arr / (np.linalg.norm(arr) + 1e-8)
        except Exception:
            return None

    def _llm_classify(self, query: str) -> str:
        u"""LLM binary classification across registered domains."""
        domains = self.list_domains()
        if len(domains) <= 1:
            return domains[0] if domains else "ai-knowledge"

        domain_names = ", ".join(
            f"{did}({self.domain_config(did).get('name', did)})"
            for did in domains
        )
        prompt = (
            f"可用领域: {domain_names}。\n"
            f"判断以下问题属于哪个领域，只输出领域ID名称：\n{query[:500]}"
        )

        try:
            import asyncio
            from core.harness.syscalls.llm import sys_llm_generate

            async def _call():
                return await sys_llm_generate(
                    prompt=prompt,
                    model=self._llm_model,
                    max_tokens=16,
                    temperature=0.0,
                )

            try:
                loop = asyncio.get_running_loop()
                # Already in async context — use thread pool
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(asyncio.run, _call())
                    result = future.result(timeout=10)
            except RuntimeError:
                # No running loop — use asyncio.run()
                result = asyncio.run(_call())

            answer = str(result.get("content", "")).strip().lower()
            for did in domains:
                if did in answer:
                    return did
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        return self._load_registry().get("fallback_domain", "ai-knowledge")

    def _load_registry(self) -> dict:
        u"""Lazy-load registry.json (cached per instance)."""
        if self._registry_cache is not None:
            return self._registry_cache

        path = os.path.expanduser("~/.aiplat/ontologies/registry.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._registry_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._registry_cache = self._build_default_registry()
        return self._registry_cache

    def _build_default_registry(self) -> dict:
        u"""Auto-generate registry from existing ontology YAMLs."""
        from core.harness.knowledge.ontology_loader import load_all_domains

        domains = {}
        for did, dom in load_all_domains().items():
            domains[did] = {
                "name": dom.name,
                "description": dom.description,
                "ontology_file": f"{did}.yaml",
                "collection_id": "default" if did == "ai-knowledge" else did,
                "namespace": dom.namespace,
                "min_wiki_score": 0.25,
                "expand_subclasses": True,
                "system_prompt_id": f"domain-prompt-{did}",
                "min_cross_results": 3,
            }
        return {
            "version": "1.0.0",
            "domains": domains,
            "fallback_domain": "ai-knowledge",
            "fallback_domains": ["default"],
            "routing": {
                "tiers": ["label_match", "embedding", "llm"],
                "embedding": {"min_confidence": 0.4, "min_margin": 0.08},
            },
        }
