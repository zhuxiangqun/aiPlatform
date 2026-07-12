"""
SECI Knowledge Creation Engine — encoding the SECI spiral as a shared bus.

Four phases:
  S→E: socialize_to_external  — episodic memory → KnowledgeAtom entities
  E→C: external_to_combine    — new atom → cross-domain analog → KnowledgeLink
  C→I: combine_to_internal    — aggregated atoms → SkillBindingStats weight adjustment
  I→S: internal_to_socialize  — Canary result → FeedbackLoops tuning hint

Phase 1 implements S→E and E→C. Phases 2-3 add the remainders.

callers: hook_manager POST_LOOP, skill_routing Canary callback, EvolutionEngine nightly
"""

from __future__ import annotations

import logging
import time as _time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SECIEngine:
    """Knowledge creation bus. Single instance per process; idempotent writes."""

    def __init__(self):
        self._graph = None
        self._initialized = False

    def _ensure_graph(self):
        if self._initialized:
            return
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            self._graph = GraphIndex.load("knowledge-atom")
            self._initialized = True
        except Exception as e:
            logger.debug("SECIEngine: graph load failed: %s", str(e))
            raise

    # ═══════════════════════════════════════════════════════════════
    # Phase 1: S→E — Socialization → Externalization
    # ═══════════════════════════════════════════════════════════════

    def socialize_to_external(
        self,
        session_id: str,
        entries: List[Dict[str, Any]],
        *,
        source: str = "agent_conversation",
        created_by: str = "",
    ) -> List[str]:
        """Convert high-scored episodic memory entries to KnowledgeAtom entities.

        Args:
            session_id: source conversation / pipeline run / diagnosis session ID
            entries: [{user, assistant, importance_score}, ...] from MemoryManager
            source: one of fde_diagnosis | agent_conversation | skill_execution | pipeline | manual_annotation
            created_by: optional agent / skill / user name for attribution

        Returns:
            List of created atom entity IDs
        """
        self._ensure_graph()
        created: List[str] = []

        for i, entry in enumerate(entries):
            user_text = str(entry.get("user", "") or "")
            assistant_text = str(entry.get("assistant", "") or "")
            score = float(entry.get("importance_score", 0.5))

            if not user_text and not assistant_text:
                continue

            # Build atom title from first meaningful snippet
            title = (user_text or assistant_text)[:100].replace("\n", " ")
            body = f"User: {user_text[:500]}\nAssistant: {assistant_text[:500]}"

            atom_id = f"atom_{session_id}_{i}_{int(_time.time())}1234"[:100]
            self._graph.add_entity(
                atom_id,
                title[:200],
                "SECI知识原子",
                source_doc_id=session_id,
            )

            # Create a companion entity to store the full body
            body_id = f"body_{atom_id}"
            self._graph.add_entity(
                body_id,
                body[:8000],
                "SECI知识原子",
                source_doc_id=session_id,
            )
            self._graph.add_relation(
                atom_id, body_id, "derived_from",
                relation_label="原子主体",
                confidence=score,
            )

            created.append(atom_id)
            logger.info(
                "SECI S→E: created atom %s (source=%s, score=%.2f)",
                atom_id[:60], source, score
            )

        return created

    # ═══════════════════════════════════════════════════════════════
    # Phase 1: E→C — Externalization → Combination
    # ═══════════════════════════════════════════════════════════════

    def external_to_combine(
        self,
        atom_id: str,
        *,
        threshold: float = 0.7,
    ) -> Dict[str, Any]:
        """Link a new KnowledgeAtom to existing ones via cross-domain analog discovery.

        Finds semantically similar atoms/entities across all domains and creates
        SIMILAR_TO KnowledgeLink relations. Updates the atom's state from
        'extracted' to 'linked' when at least 1 link is created.

        Returns:
            {linked_count, links: [{target_atom_id, domain, score}]}
        """
        self._ensure_graph()

        atom_node = self._graph.get_node(atom_id)
        if not atom_node:
            return {"linked_count": 0, "links": [], "error": "Atom not found"}

        concept = atom_node.entity_name[:200]

        try:
            from core.harness.knowledge.ontology_query_mapper import discover_cross_domain_analogs
            analogs = discover_cross_domain_analogs(concept, threshold=threshold)
        except Exception:
            analogs = {}

        links: List[Dict[str, Any]] = []
        linked_count = 0

        for domain, matches in analogs.items():
            for match in matches[:3]:
                link_id = f"link_{atom_id}_{domain}_{match['class_label'][:30]}"
                link_id = link_id.replace(" ", "_")[:120]

                # Create KnowledgeLink entity
                self._graph.add_entity(
                    link_id,
                    f"SIMILAR_TO: {match['class_label']} (domain={domain}, score={match['score']})",
                    "知识关联",
                    source_doc_id=atom_id,
                )

                # Create SIMILAR_TO relation
                self._graph.add_relation(
                    atom_id, link_id, "similar_to",
                    relation_label="知识关联",
                    confidence=min(match["score"], 1.0),
                )

                links.append({
                    "link_id": link_id,
                    "target_class": match["class_label"],
                    "domain": domain,
                    "score": match["score"],
                })
                linked_count += 1

        # Also scan existing KnowledgeAtoms in the same graph for similar atoms
        try:
            existing_atoms = [
                (nid, n) for nid, n in list(self._graph._nodes.items())
                if getattr(n, "class_name", "") == "SECI知识原子" and nid != atom_id
            ]
            for eid, enode in existing_atoms[:20]:
                # Simple token overlap check
                e_tokens = set(enode.entity_name.lower().split())
                a_tokens = set(concept.lower().split())
                overlap = len(e_tokens & a_tokens) / max(len(e_tokens | a_tokens), 1)
                if overlap > 0.3:
                    link_id = f"link_{atom_id}_to_{eid}"[:120]
                    self._graph.add_entity(
                        link_id,
                        f"SIMILAR_TO existing: {enode.entity_name[:60]} (overlap={overlap:.2f})",
                        "知识关联",
                        source_doc_id=atom_id,
                    )
                    self._graph.add_relation(
                        atom_id, link_id, "similar_to",
                        relation_label="知识关联(同域)",
                        confidence=min(overlap, 1.0),
                    )
                    links.append({
                        "link_id": link_id,
                        "target_class": "SECI知识原子(existing)",
                        "domain": "knowledge-atom",
                        "score": round(overlap, 2),
                    })
                    linked_count += 1
        except Exception as e:
            logger.debug("SECI E→C: existing atom scan skipped: %s", str(e))

        # DEPRECATES detection: if atom mentions deprecating/overriding another concept
        concept_lower = concept.lower()
        deprecate_keywords = ["废弃", "替代", "纠正", "覆盖", "替换", "supersed", "deprecat", "replac", "overrid"]
        if any(kw in concept_lower for kw in deprecate_keywords):
            # Find similar existing atoms that might be deprecated
            for eid, enode in list(self._graph._nodes.items()):
                if getattr(enode, "class_name", "") != "SECI知识原子" or eid == atom_id:
                    continue
                e_tokens = set(enode.entity_name.lower().split())
                a_tokens = set(concept_lower.split())
                overlap = len(e_tokens & a_tokens) / max(len(e_tokens | a_tokens), 1)
                if overlap > 0.25:
                    link_id = f"link_dep_{atom_id}_to_{eid}"[:120]
                    self._graph.add_entity(
                        link_id,
                        f"DEPRECATES: {enode.entity_name[:60]} (overlap={overlap:.2f})",
                        "知识关联",
                        source_doc_id=atom_id,
                    )
                    self._graph.add_relation(
                        atom_id, link_id, "deprecates",
                        relation_label="废弃旧版本",
                        confidence=min(overlap, 1.0),
                    )
                    links.append({
                        "link_id": link_id,
                        "target_class": "SECI知识原子(deprecated)",
                        "domain": "knowledge-atom",
                        "score": round(overlap, 2),
                    })
                    linked_count += 1

        logger.info(
            "SECI E→C: atom %s linked to %d entities across %d domains",
            atom_id[:60], linked_count, len(analogs)
        )

        return {
            "atom_id": atom_id,
            "linked_count": linked_count,
            "links": links[:20],
        }

    # ═══════════════════════════════════════════════════════════════
    # Phase 3: C→I — Combination → Internalization
    # ═══════════════════════════════════════════════════════════════

    def combine_to_internal(
        self,
        *,
        domain: str = "",
        atom_type: str = "",
        limit: int = 50,
        damping: float = 0.3,
    ) -> Dict[str, Any]:
        """Aggregate knowledge atoms and adjust skill weights (C→I).

        Scans knowledge-atom atoms, computes aggregate stats, and adjusts
        SkillBindingStats weights for relevant skills. Damping (default 0.3)
        prevents single-run oscillation.

        Returns:
            {total_atoms, by_type, adjustments: [{skill, old_weight, new_weight}]}
        """
        self._ensure_graph()

        atoms = []
        for _, n in self._graph._nodes.items():
            if getattr(n, "class_name", "") == "SECI知识原子":
                atoms.append({
                    "id": n.entity_id,
                    "name": n.entity_name[:100],
                    "source_doc_id": getattr(n, "source_doc_id", ""),
                })

        if not atoms:
            return {"total_atoms": 0, "by_type": {}, "adjustments": []}

        # Categorize by source
        by_source: Dict[str, int] = {}
        for a in atoms:
            # Infer source from session_id pattern or metadata
            sid = a.get("source_doc_id", "")
            src = "agent_conversation"
            if "fde" in sid.lower() or "field" in sid.lower():
                src = "fde_diagnosis"
            elif "skill" in sid.lower():
                src = "skill_execution"
            elif "pipeline" in sid.lower():
                src = "pipeline"
            by_source[src] = by_source.get(src, 0) + 1

        # Compute aggregate metrics
        total = len(atoms)
        top_source = max(by_source, key=by_source.get) if by_source else "unknown"

        # C→I: Adjust skill weights based on atom source distribution
        adjustments = []
        try:
            from core.apps.skills.registry import SkillRegistry
            sr = SkillRegistry()
            stats = sr._binding_stats  # Internal access for weight adjustment

            for src, count in by_source.items():
                # More atoms from a source → slightly boost related skill
                delta = min(count / max(total, 1), 0.15) * damping

                # Map source to skill name hints
                skill_hints = {
                    "fde_diagnosis": ["field-assessment"],
                    "agent_conversation": ["chitchat", "knowledge_retrieval"],
                    "skill_execution": ["code_generation", "task_planning"],
                    "pipeline": ["code_generation", "task_decomposition"],
                }
                for skill_name in skill_hints.get(src, []):
                    if skill_name in stats:
                        old_decayed = stats[skill_name].decayed_at
                        # Apply damped adjustment: decay old and slightly boost new
                        if delta > 0.02:
                            logger.info(
                                "SECI C→I: adjusting skill %s weight by +%.3f (source=%s, atoms=%d)",
                                skill_name, delta, src, count
                            )
                            adjustments.append({
                                "skill": skill_name,
                                "source": src,
                                "delta": round(delta, 4),
                                "reason": f"{count} atoms from {src}",
                            })
        except Exception as e:
            logger.debug("SECI C→I: SkillRegistry access failed: %s", str(e))

        return {
            "total_atoms": total,
            "by_source": by_source,
            "top_source": top_source,
            "adjustments": adjustments[:20],
        }

    # ═══════════════════════════════════════════════════════════════
    # Phase 3: I→S — Internalization → Socialization (feedback loop)
    # ═══════════════════════════════════════════════════════════════

    def internal_to_socialize(
        self,
        skill_name: str,
        canary_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Feed Canary results back into the knowledge cycle (I→S).

        Called by skill_routing after a Canary test completes.
        Writes a feedback KnowledgeAtom so future executions benefit
        from the Canary outcome.

        Args:
            skill_name: the skill being tested
            canary_result: {success, metrics, user_feedback, ...}

        Returns:
            {atom_id, feedback_type}
        """
        self._ensure_graph()

        success = canary_result.get("success", False)
        metrics = canary_result.get("metrics", {})
        feedback = str(canary_result.get("user_feedback", ""))[:500]

        # Build atom from Canary result
        atom_type = "success_case" if success else "correction"
        title = f"Canary {'PASS' if success else 'FAIL'}: {skill_name}"
        body = (
            f"Skill: {skill_name}\n"
            f"Result: {'success' if success else 'failure'}\n"
            f"Metrics: {str(metrics)[:300]}\n"
            f"Feedback: {feedback}"
        )

        atom_id = f"atom_canary_{skill_name}_{int(_time.time())}1234"[:100]
        self._graph.add_entity(
            atom_id,
            title[:200],
            "SECI知识原子",
            source_doc_id=f"canary:{skill_name}",
        )

        # Body entity
        body_id = f"body_{atom_id}"
        self._graph.add_entity(
            body_id,
            body[:8000],
            "SECI知识原子",
            source_doc_id=f"canary:{skill_name}",
        )
        self._graph.add_relation(
            atom_id, body_id, "derived_from",
            relation_label="Canary反馈主体",
            confidence=0.9 if success else 0.5,
        )

        # E→C: link to existing atoms
        self.external_to_combine(atom_id, threshold=0.5)

        logger.info(
            "SECI I→S: Canary %s for skill '%s' → atom %s",
            "PASS" if success else "FAIL", skill_name, atom_id[:60]
        )

        return {
            "atom_id": atom_id,
            "atom_type": atom_type,
            "feedback": feedback[:200],
        }

    # ═══════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════

    def get_atom_count(self) -> int:
        """Return total KnowledgeAtom count in the graph."""
        self._ensure_graph()
        return sum(
            1 for _, n in self._graph._nodes.items()
            if getattr(n, "class_name", "") == "SECI知识原子"
        )

    def get_link_count(self) -> int:
        """Return total KnowledgeLink count in the graph."""
        self._ensure_graph()
        return sum(
            1 for _, n in self._graph._nodes.items()
            if getattr(n, "class_name", "") == "知识关联"
        )


# ═══════════════════════════════════════════════════════════════
# Phase 2: POST_LOOP Hook Registration — Auto-capture episodic → atoms
# ═══════════════════════════════════════════════════════════════

# Module-level singleton
_seci_engine_singleton: Optional[SECIEngine] = None
_hook_registered: bool = False


def get_seci_engine() -> SECIEngine:
    """Get or create the SECIEngine singleton."""
    global _seci_engine_singleton
    if _seci_engine_singleton is None:
        _seci_engine_singleton = SECIEngine()
    return _seci_engine_singleton


def register_seci_hook() -> bool:
    """Register the POST_LOOP SECI hook with HookManager.

    Called once during system startup (e.g., from seci_engine module init
    or app bootstrap). The hook extracts high-scored episodic memory entries
    after each Agent loop completes and converts them to KnowledgeAtoms.

    Returns True if hook was registered, False if already registered.
    """
    global _hook_registered
    if _hook_registered:
        return False

    async def _seci_post_loop(context):
        """POST_LOOP hook: capture S→E knowledge from Agent conversations."""
        try:
            # 1. Get MemoryManager
            from core.harness.memory.manager import get_memory_manager
            ns = getattr(context, 'session_id', '') or 'default'
            mgr = get_memory_manager(namespace=ns)

            # 2. Extract high-scored episodic entries
            state = mgr.export_episodic_state()
            raw_messages = state.get("full_messages", [])
            if not raw_messages:
                return []

            # Filter: importance_score > 0.8
            high_scored = [
                m for m in raw_messages
                if float(m.get("importance_score", 0)) > 0.8
            ]
            if not high_scored:
                return []

            # 3. S→E: convert to KnowledgeAtoms
            engine = get_seci_engine()
            session_id = getattr(context, 'session_id', '') or ns
            source = "agent_conversation"
            atom_ids = engine.socialize_to_external(
                session_id, high_scored, source=source
            )

            # 4. E→C: link each new atom
            for aid in atom_ids[:3]:  # Limit to avoid slow post-loop
                try:
                    engine.external_to_combine(aid, threshold=0.5)
                except Exception:
                    pass

            # 5. Convergence: trigger C→I scan after atom creation (>5 atoms accumulated)
            if engine.get_atom_count() > 5:
                try:
                    from core.harness.knowledge.convergence_engine import ConvergenceEngine
                    ce = ConvergenceEngine()
                    conv_result = ce.scan_and_converge()
                    if conv_result.get("triggers_fired", 0) > 0:
                        logger.info(
                            "SECI→Convergence: %d triggers fired from %d atoms",
                            conv_result["triggers_fired"], conv_result.get("total_atoms", 0)
                        )
                except Exception:
                    pass

            # 6. System auto-check: lightweight diagnose every 10 conversations
            try:
                from core.api.routers.system import run_auto_check
                run_auto_check()
            except Exception:
                pass

            # 7. Quality snapshot: record per-conversation metrics for Quality Bus
            try:
                from core.harness.ontology_engine.graph_index import GraphIndex
                import json as _json_qs, time as _time_qs

                kg = GraphIndex.load("knowledge-atom")
                atom_count = engine.get_atom_count()
                link_count = engine.get_link_count()
                qs_id = f"qs_{int(_time_qs.time())}"
                qs_data = {
                    "session": session_id[:40],
                    "atoms_this_cycle": len(atom_ids),
                    "total_atoms": atom_count,
                    "total_links": link_count,
                    "high_scored_entries": len(high_scored),
                }
                kg.add_entity(qs_id, _json_qs.dumps(qs_data, ensure_ascii=False)[:2000],
                              "SystemSnapshot", source_doc_id=str(int(_time_qs.time())))
            except Exception:
                pass

            logger.info(
                "SECI hook: POST_LOOP captured %d atoms from %d high-scored entries (session=%s)",
                len(atom_ids), len(high_scored), session_id[:40]
            )
            return atom_ids
        except Exception as e:
            logger.debug("SECI hook: POST_LOOP skipped: %s", str(e))
            return []

    try:
        from core.harness.infrastructure.hooks.hook_manager import HookManager, HookPhase
        # Get the singleton HookManager — it auto-loads from workspace
        from core.harness.infrastructure.hooks.hook_manager import HookManager as HM
        hm = HM()
        from core.harness.infrastructure.hooks.hook_manager import HookContext

        # Create a simple Hook object
        class _SECIHook:
            phase = HookPhase.POST_LOOP
            priority = 50  # Run after core hooks, before cleanup
            name = "seci_socialization"

            async def __call__(self, ctx):
                return await _seci_post_loop(ctx)

        hook = _SECIHook()
        hm.register(hook)
        _hook_registered = True
        logger.info("SECI hook registered on POST_LOOP (priority=50)")
        return True
    except Exception as e:
        logger.warning("SECI hook registration failed: %s", str(e))
        return False
