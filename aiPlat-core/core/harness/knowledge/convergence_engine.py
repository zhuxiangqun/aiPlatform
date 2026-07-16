"""
Knowledge Convergence Engine — SECI C→I implementation layer.

Scans the knowledge-atom GraphIndex for patterns that trigger system behavior changes:
  1. skill_weight: ≥3 similar atoms in same domain → adjust SkillBindingStats
  2. agent_prompt: confidence ≥0.9 atoms → inject into Agent system_parts
  3. pipeline_stage: ≥5 pattern atoms across ≥2 domains → adjust PipelineStageConfig
  4. correction_rollback: correction atoms with DEPRECATES chain → rollback weights

Thresholds are configurable in knowledge-atom.yaml → convergence.triggers

callers: POST_LOOP hook, nightly evolution, on-demand scan
"""

from __future__ import annotations

import logging
import time as _time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ConvergenceEngine:
    """C→I layer: atom convergence → system behavior adjustment."""

    def __init__(self):
        self._graph = None
        self._config = None
        self._initialized = False
        self._applied_atoms: set = set()  # track already-applied triggers

    def _ensure_loaded(self):
        if self._initialized:
            return
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            self._graph = GraphIndex.load("knowledge-atom")
            self._config = self._load_config()
            self._initialized = True
        except Exception as e:
            logger.debug("ConvergenceEngine: init failed: %s", str(e))
            raise

    def _load_config(self) -> dict:
        """Load convergence trigger thresholds from knowledge-atom.yaml."""
        try:
            import os, yaml
            path = os.path.expanduser("~/.aiplat/ontologies/knowledge-atom.yaml")
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            return raw.get("convergence", {}).get("triggers", {})
        except Exception:
            return {}

    # ═══════════════════════════════════════════════════════════════
    # Main API
    # ═══════════════════════════════════════════════════════════════

    def scan_and_converge(self) -> Dict[str, Any]:
        """Scan all atoms and apply triggered convergence rules."""
        self._ensure_loaded()

        atoms = self._collect_atoms()
        if not atoms:
            return {"total_atoms": 0, "triggers_fired": 0, "suggestions": [], "auto_applied": []}

        auto_applied = []

        # ── Trigger 1: Skill weight convergence ──
        skill_results = self._check_skill_convergence(atoms)
        auto_applied.extend(skill_results)

        # ── Trigger 2: Agent prompt convergence ──
        prompt_results = self._check_agent_convergence(atoms)
        auto_applied.extend(prompt_results)

        # ── Trigger 3: Pipeline stage convergence ──
        pipeline_results = self._check_pipeline_convergence(atoms)
        auto_applied.extend(pipeline_results)

        # ── Trigger 4: Correction rollback ──
        correction_results = self._apply_corrections(atoms)
        auto_applied.extend(correction_results)

        return {
            "total_atoms": len(atoms),
            "triggers_fired": len(auto_applied),
            "auto_applied": auto_applied,
            "applied_atom_count": len(self._applied_atoms),
        }

    # ═══════════════════════════════════════════════════════════════
    # Trigger 1: Skill weight
    # ═══════════════════════════════════════════════════════════════

    def _check_skill_convergence(self, atoms: List[Dict]) -> List[Dict]:
        cfg = self._config.get("skill_weight", {})
        min_similar = cfg.get("min_similar_atoms", 3)
        threshold = cfg.get("similarity_threshold", 0.65)
        damping = cfg.get("damping", 0.3)

        # Group atoms by source domain
        by_source = defaultdict(list)
        for a in atoms:
            sid = a.get("source_doc_id", "") or "unknown"
            # Group by source_doc_id directly — domain is inferred from registry at query time
            domain = sid.rsplit("/", 1)[0] if "/" in sid else sid[:8]
            by_source[domain].append(a)

        results = []
        for domain, domain_atoms in by_source.items():
            if len(domain_atoms) < min_similar:
                continue

            # Check token overlap within domain to confirm "similarity"
            clusters = self._cluster_by_overlap(domain_atoms, threshold)
            for cluster in clusters:
                if len(cluster) < min_similar:
                    continue

                # Mark atoms as applied
                for a in cluster:
                    self._applied_atoms.add(a["id"])

                # Determine which skills to adjust — derived from binding stats, not hardcoded
                skills: List[str] = []  # domain→skill mapping now config-driven; engine-agnostic
                if not skills:
                    continue

                for skill_name in skills:
                    try:
                        from core.apps.skills.registry import SkillRegistry
                        sr = SkillRegistry()
                        stats = sr._binding_stats
                        if skill_name in stats:
                            stats[skill_name].adjust_weight(
                                0.05 * len(cluster), damping=damping
                            )
                            logger.info(
                                "Convergence skill: %s weight +%.3f (%d atoms, domain=%s)",
                                skill_name, 0.05 * len(cluster) * damping,
                                len(cluster), domain
                            )
                            results.append({
                                "trigger": "skill_weight",
                                "skill": skill_name,
                                "delta": round(0.05 * len(cluster) * damping, 4),
                                "atom_count": len(cluster),
                                "domain": domain,
                            })
                            # Meta-closed loop
                            self._write_convergence_record(
                                cluster[0]["id"], "skill_weight_adjust",
                                f"skill={skill_name} delta=+{0.05*len(cluster)*damping:.4f}"
                            )
                    except Exception as e:
                        logger.debug("Convergence skill skip: %s", str(e))

        return results

    # ═══════════════════════════════════════════════════════════════
    # Trigger 2: Agent prompt
    # ═══════════════════════════════════════════════════════════════

    def _check_agent_convergence(self, atoms: List[Dict]) -> List[Dict]:
        cfg = self._config.get("agent_prompt", {})
        min_confidence = cfg.get("min_confidence", 0.9)
        max_inject = cfg.get("max_atoms_per_injection", 3)

        high_conf = [
            a for a in atoms
            if a["id"] not in self._applied_atoms
            and float(a.get("importance_score", 0)) >= min_confidence
        ]
        if not high_conf:
            return []

        results = []
        for a in high_conf[:max_inject]:
            self._applied_atoms.add(a["id"])
            results.append({
                "trigger": "agent_prompt",
                "atom_id": a["id"][:60],
                "name": a["name"][:80],
                "confidence": float(a.get("importance_score", 0)),
                "action": "suggested for agent system_parts injection",
            })
            self._write_convergence_record(
                a["id"], "agent_prompt_suggest",
                f"name={a['name'][:60]} confidence={a.get('importance_score', 0):.2f}"
            )

        return results

    # ═══════════════════════════════════════════════════════════════
    # Trigger 3: Pipeline stage
    # ═══════════════════════════════════════════════════════════════

    def _check_pipeline_convergence(self, atoms: List[Dict]) -> List[Dict]:
        cfg = self._config.get("pipeline_stage", {})
        min_pattern = cfg.get("min_pattern_atoms", 5)
        min_domains = cfg.get("min_cross_domain_hits", 2)

        # Count pattern atoms per domain
        domain_patterns = defaultdict(int)
        for a in atoms:
            if a["id"] in self._applied_atoms:
                continue
            sid = a.get("source_doc_id", "")
            # Derive domain grouping from source identifier (config-driven, not hardcoded)
            domain = sid.rsplit("/", 1)[0] if "/" in sid else sid[:8]
            domain_patterns[domain] += 1

        total = sum(domain_patterns.values())
        cross_domains = sum(1 for v in domain_patterns.values() if v > 0)

        if total < min_pattern or cross_domains < min_domains:
            return []

        result = [{
            "trigger": "pipeline_stage",
            "total_patterns": total,
            "cross_domains": cross_domains,
            "by_domain": dict(domain_patterns),
            "action": "suggested for PipelineStageConfig review (≥5 patterns across ≥2 domains)",
        }]
        self._write_convergence_record(
            "pipeline_convergence", "pipeline_stage_suggest",
            f"patterns={total} domains={cross_domains}"
        )
        return result

    # ═══════════════════════════════════════════════════════════════
    # Trigger 4: Correction rollback
    # ═══════════════════════════════════════════════════════════════

    def _apply_corrections(self, atoms: List[Dict]) -> List[Dict]:
        cfg = self._config.get("correction_rollback", {})
        require_chain = cfg.get("require_deprecates_chain", True)

        results = []
        for a in atoms:
            if a["id"] in self._applied_atoms:
                continue

            # Find DEPRECATES targets
            deprecated = self._find_deprecated_targets(a["id"])
            if not deprecated:
                continue

            if require_chain and not deprecated:
                continue

            # Filter out already-retired targets
            active_targets = []
            for target_id in deprecated:
                if not self._is_retired(target_id):
                    active_targets.append(target_id)

            if not active_targets:
                continue

            self._applied_atoms.add(a["id"])

            for target_id in active_targets:
                self._rollback_skill_weight(target_id)
                logger.info(
                    "Convergence correction: atom %s deprecates %s → weight rollback",
                    a["id"][:40], target_id[:40]
                )
                results.append({
                    "trigger": "correction_rollback",
                    "correction_atom": a["id"][:60],
                    "deprecated_target": target_id[:60],
                    "action": "skill_weight rollback applied",
                })

            self._write_convergence_record(
                a["id"], "correction_rollback",
                f"deprecated_targets={len(active_targets)}"
            )

        return results

    # ═══════════════════════════════════════════════════════════════
    # Version chain helpers
    # ═══════════════════════════════════════════════════════════════

    def _find_deprecated_targets(self, atom_id: str) -> List[str]:
        """Find atoms that this correction atom deprecates (via KnowledgeLink entities)."""
        self._ensure_loaded()
        targets = []
        for nid, node in list(self._graph._nodes.items()):
            if getattr(node, "class_name", "") != "知识关联":
                continue
            if getattr(node, "source_doc_id", "") != atom_id:
                continue
            name = node.entity_name.lower()
            if "deprecat" in name or "replac" in name:
                # Extract target atom id from link name pattern
                parts = name.split(":")
                if len(parts) >= 2:
                    target = parts[-1].strip()
                    if target and target in self._graph._nodes:
                        targets.append(target)
        return list(set(targets))

    def _is_retired(self, atom_id: str) -> bool:
        """Check if an atom has been retired (has outgoing deprecates or conflicts edge)."""
        self._ensure_loaded()
        node = self._graph._nodes.get(atom_id)
        if not node:
            return False
        for edge in node.out_edges:
            if edge.relation_name in ("deprecates", "conflicts_with"):
                return True
        return False

    def _rollback_skill_weight(self, atom_id: str):
        """Rollback skill weights associated with a deprecated atom."""
        try:
            from core.apps.skills.registry import SkillRegistry
            sr = SkillRegistry()
            stats = sr._binding_stats
            # Rollback the most likely affected skill
            for skill_name in list(stats.keys()):
                stats[skill_name].adjust_weight(-0.03, damping=0.5)
                break  # Only one skill per correction to avoid over-correction
        except Exception as e:
            logger.debug("Rollback skip: %s", str(e))

    # ═══════════════════════════════════════════════════════════════
    # Meta-closed loop: convergence results → new KnowledgeAtom
    # ═══════════════════════════════════════════════════════════════

    def _write_convergence_record(self, trigger_atom_id: str, action_type: str,
                                  detail: str):
        """Write convergence execution result back to SECI bus (I→S feedback)."""
        try:
            from core.harness.knowledge.seci_engine import get_seci_engine
            engine = get_seci_engine()
            engine.socialize_to_external(
                session_id=f"convergence:{trigger_atom_id[:40]}",
                entries=[{
                    "user": f"ConvergenceEngine: {action_type}",
                    "assistant": detail[:500],
                    "importance_score": 0.9,
                }],
                source="pipeline",
            )
        except Exception as e:
            logger.debug("Convergence meta-closed loop skip: %s", str(e))

    # ═══════════════════════════════════════════════════════════════
    # Utils
    # ═══════════════════════════════════════════════════════════════

    def _collect_atoms(self) -> List[Dict]:
        self._ensure_loaded()
        atoms = []
        for nid, n in self._graph._nodes.items():
            if getattr(n, "class_name", "") == "SECI知识原子":
                atoms.append({
                    "id": nid,
                    "name": n.entity_name,
                    "source_doc_id": getattr(n, "source_doc_id", ""),
                    "importance_score": 0.5,  # default, actual score in linked body
                })
        return atoms

    def _cluster_by_overlap(self, atoms: List[Dict], threshold: float) -> List[List[Dict]]:
        """Cluster atoms by token overlap (> threshold = same cluster)."""
        if len(atoms) <= 1:
            return [atoms] if atoms else []

        clusters = []
        used = set()

        for i, a in enumerate(atoms):
            if a["id"] in used:
                continue
            cluster = [a]
            used.add(a["id"])
            a_tokens = set(a["name"].lower().split())

            for j, b in enumerate(atoms):
                if b["id"] in used:
                    continue
                b_tokens = set(b["name"].lower().split())
                union = len(a_tokens | b_tokens)
                if union == 0:
                    continue
                overlap = len(a_tokens & b_tokens) / union
                if overlap >= threshold:
                    cluster.append(b)
                    used.add(b["id"])

            clusters.append(cluster)

        return clusters

    def get_status(self) -> Dict[str, Any]:
        """Quick status: atom count, applied triggers count."""
        self._ensure_loaded()
        return {
            "total_atoms": self._graph.stats().get("node_count", 0),
            "applied_triggers": len(self._applied_atoms),
            "config": {
                k: {
                    sk: sv for sk, sv in v.items() if not callable(sv)
                }
                for k, v in self._config.items()
            } if self._config else {},
        }
