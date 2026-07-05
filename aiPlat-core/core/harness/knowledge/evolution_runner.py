"""
EvolutionRunner — Artificial Knowledge Evolution (AKE) scheduler.

Orchestrates generation-based evolution of wiki knowledge:
  Assess (fitness scores) → Select (low-fitness pages) →
  Mutate (LLM curation/atomize/backfill) → Evaluate (compare scores) →
  Accept/Revert → Record (generation history).

Uses local LLM (qwen2.5:7b via Ollama) for zero API cost.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import os as _os
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EvolutionSnapshot:
    """Snapshot of wiki state before a generation for rollback."""
    collection_id: str
    generation_id: int
    index_backup: Optional[Dict] = None
    metrics_before: Optional[Dict] = None
    created_at: float = 0.0

    def create(self):
        """Backup current index.json for rollback."""
        self.created_at = _time.time()
        wiki_root = _os.path.expanduser(
            _os.getenv("AIPLAT_HOME", "~/.aiplat"))
        idx_path = _os.path.join(
            wiki_root, "wiki", "collections", self.collection_id, "index.json")
        if _os.path.exists(idx_path):
            self.index_backup = _json.loads(open(idx_path).read())
        else:
            self.index_backup = {"pages": {}}
        logger.info(f"Evolution snapshot created for gen {self.generation_id}")

    def rollback(self):
        """Restore index from backup."""
        if not self.index_backup:
            logger.warning("No snapshot to rollback")
            return
        wiki_root = _os.path.expanduser(
            _os.getenv("AIPLAT_HOME", "~/.aiplat"))
        idx_path = _os.path.join(
            wiki_root, "wiki", "collections", self.collection_id, "index.json")
        _os.makedirs(_os.path.dirname(idx_path), exist_ok=True)
        open(idx_path, "w").write(
            _json.dumps(self.index_backup, indent=2, ensure_ascii=False))
        # Rebuild A-Box
        try:
            from core.harness.knowledge.knowledge_ontology import reset_ontology
            from core.harness.knowledge.knowledge_abox_builder import rebuild_full
            reset_ontology()
            rebuild_full(collection_id=self.collection_id)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        logger.info(f"Evolution snapshot rolled back for gen {self.generation_id}")


@dataclass
class PageFitness:
    """Fitness score for a single wiki page."""
    title: str
    score: float
    has_violations: bool = False
    missing_evidence: bool = False
    has_stale_refs: bool = False
    schema_issues: List[str] = field(default_factory=list)


class EvolutionRunner:
    """Orchestrates generation-based knowledge evolution."""

    def __init__(self, collection_id: str = "default",
                 max_mutations: int = 5):
        self.collection_id = collection_id
        self.max_mutations = max_mutations
        self.generation_id = self._load_last_generation_id()
        self._recent_deltas: List[float] = []
        self.auto_apply_previous_onto_mutations()  # Restore in-memory ontology state

    # ── Public API ──

    def can_evolve(self, *, force: bool = False) -> bool:
        """Check if evolution should proceed — event-driven, not timer-driven.

        Triggers:
          1. New pages since last generation >= 3 (new knowledge injected)
          2. Golden pass_rate dropped >= 10% (quality degradation)
          3. force=True (manual trigger from frontend)
        """
        if force:
            return True

        # Local model must be available
        try:
            from core.harness.utils.model_injection import best_model_for_purpose
            model = best_model_for_purpose("wiki_curation")
            if not model:
                return False
        except Exception:
            return False

        # Trigger 1: New pages since last generation
        new_count = self._new_pages_since_last_gen()
        if new_count >= 3:
            logger.info(f"Evolution trigger: {new_count} new pages since last gen")
            return True

        # Trigger 2: Golden pass_rate dropped significantly
        if self._golden_quality_degraded():
            logger.info("Evolution trigger: Golden pass_rate degraded")
            return True

        # Stall detection (even for event-driven, stop if no progress)
        if len(self._recent_deltas) >= 5 and all(d <= 0 for d in self._recent_deltas[-5:]):
            logger.info("Evolution stalled — 5 consecutive non-positive deltas")
            return False

        return False

    async def run_one_generation(self, force: bool = False) -> Dict[str, Any]:
        """Execute a single generation of evolution.

        Args:
            force: If True, bypass can_evolve() checks (manual/frontend trigger).

        Returns:
            {generation_id, fitness_before, fitness_after, delta, verdict, mutations, new_pages, deleted_pages}
        """
        if not self.can_evolve(force=force):
            return {"generation_id": self.generation_id, "verdict": "SKIPPED",
                    "reason": "can_evolve() returned False — no trigger (new pages, quality drop, or force required)"}

        # ── Phase 1: Assess ──
        from core.harness.knowledge.knowledge_validator import compute_ontology_metrics
        baseline = compute_ontology_metrics(self.collection_id, force_fresh=True)
        page_scores = self._compute_page_fitness_scores()
        targets = self._select_targets(page_scores)

        if not targets:
            return {"generation_id": self.generation_id, "verdict": "SKIPPED",
                    "reason": "no targets to evolve", "fitness_before": baseline.get("golden_regression", {}).get("pass_rate", 0)}

        # ── Phase 2: Snapshot ──
        snapshot = EvolutionSnapshot(self.collection_id, self.generation_id)
        snapshot.create()
        snapshot.metrics_before = baseline

        # ── Phase 3: Mutate (Wiki) ──
        mutations = []
        for target in targets[:self.max_mutations]:
            try:
                result = await self._apply_mutation(target)
                mutations.append(result)
            except Exception as e:
                mutations.append({"page": target.title, "type": "error", "error": str(e)})
            await asyncio.sleep(1.0)  # Rate limit

        # ── Phase 3.5: Ontology Evolution (every 5 Wiki generations) ──
        onto_mutations = []
        if self.should_run_ontology_phase():
            onto_mutations = self._run_ontology_phase()

        # ── Phase 4: Evaluate ──
        after = compute_ontology_metrics(self.collection_id, force_fresh=True)
        before_pass = baseline.get("golden_regression", {}).get("pass_rate", 0)
        after_pass = after.get("golden_regression", {}).get("pass_rate", 0)
        delta = after_pass - before_pass

        if delta < 0:
            snapshot.rollback()
            verdict = "REVERTED"
            after_metrics = baseline
        else:
            verdict = "ACCEPTED"
            after_metrics = after

        self._recent_deltas.append(delta)
        if len(self._recent_deltas) > 10:
            self._recent_deltas = self._recent_deltas[-10:]

        # ── Phase 5: Record ──
        self.generation_id += 1
        self._record_generation(baseline, after_metrics, mutations, verdict, delta, onto_mutations)

        return {
            "generation_id": self.generation_id - 1,
            "fitness_before": round(before_pass, 1),
            "fitness_after": round(after_metrics.get("golden_regression", {}).get("pass_rate", 0), 1),
            "delta": round(delta, 1),
            "verdict": verdict,
            "mutations": mutations,
            "onto_mutations": onto_mutations,
            "new_pages": sum(1 for m in mutations if m.get("type") == "seed"),
            "deleted_pages": sum(1 for m in mutations if m.get("type") == "delete"),
        }

    # ── Fitness Scoring ──

    def _compute_page_fitness_scores(self) -> List[PageFitness]:
        """Score all wiki pages on 0-100 fitness scale."""
        from core.harness.knowledge.wiki_engine import search_pages, read_page
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_validator import validate

        pages = search_pages(limit=1000, collection_id=self.collection_id)
        violations = self._get_violations_map()
        scores = []

        for p in pages:
            title = p.get("title", "")
            score = 20  # baseline (lower = more room for differentiation)
            page_viols = violations.get(title, [])
            has_violations = len(page_viols) > 0
            body = (read_page(title, collection_id=self.collection_id) or {}).get("body", "")

            # ── Penalty-first scoring (wider spread 20-100) ──
            if has_violations:
                score -= 25 * len(page_viols)  # -25 per violation
            else:
                score += 30  # clean page bonus

            if "<!-- evidence_text:" in (body or ""):
                score += 25  # strong bonus for evidence
            else:
                score -= 10  # evidence is important

            if p.get("stale_references"):
                score -= 5 * len(p.get("stale_references", []))
            else:
                score += 5

            related_count = len(p.get("related") or [])
            if related_count >= 2:
                score += 10
            elif related_count == 1:
                score += 5

            summary = p.get("summary", "")
            if len(summary) >= 20:
                score += 5
            elif len(summary) < 5:
                score -= 5

            tags_count = len(p.get("tags") or [])
            if tags_count >= 3:
                score += 5

            schema_issues = []
            if len(summary) < 5:
                schema_issues.append("short_summary")

            scores.append(PageFitness(
                title=title,
                score=max(0, min(100, score)),
                has_violations=has_violations,
                missing_evidence=("<!-- evidence_text:" not in (body or "")),
                has_stale_refs=bool(p.get("stale_references")),
                schema_issues=schema_issues,
            ))

        scores.sort(key=lambda x: x.score)
        return scores

    def _get_violations_map(self) -> Dict[str, List[str]]:
        """Build page → violation ids map from A-Box validator."""
        try:
            from core.harness.knowledge.knowledge_abox_builder import build_abox
            from core.harness.knowledge.knowledge_validator import validate
            report = validate(build_abox(collection_id=self.collection_id))
            vmap: Dict[str, List[str]] = {}
            for v in report.violations:
                for e in v.entities:
                    # Extract title from URI
                    short = e.replace("http://aiplat.local/knowledge#", "")
                    vmap.setdefault(short, []).append(v.axiom_id)
            return vmap
        except Exception:
            return {}

    def _select_targets(self, scores: List[PageFitness]) -> List[PageFitness]:
        """Select bottom-scoring pages for mutation."""
        return [s for s in scores if s.score < 70][:self.max_mutations]

    # ── Mutation ──

    async def _apply_mutation(self, target: PageFitness) -> Dict[str, Any]:
        """Apply the most appropriate mutation to a target page."""
        # Priority: violations → evidence → schema → stale → general curation
        if target.has_violations:
            return await self._mutate_curate(target)
        if target.missing_evidence:
            return self._mutate_backfill(target)
        if target.schema_issues:
            return await self._mutate_curate(target)
        if target.has_stale_refs:
            return self._mutate_clean_stale(target)
        return await self._mutate_curate(target)

    async def _mutate_curate(self, target: PageFitness) -> Dict:
        """LLM curation — rewrite page metadata."""
        from core.harness.knowledge.wiki_engine import (
            read_page, llm_curate_page, update_page, search_pages
        )
        page = read_page(target.title, collection_id=self.collection_id)
        if not page:
            return {"page": target.title, "type": "curate", "error": "not found"}

        existing = search_pages(limit=1000, collection_id=self.collection_id)
        existing_titles = [p["title"] for p in existing if p["title"] != target.title]
        curated = await llm_curate_page(
            target.title, page.get("body", ""),
            existing_titles=existing_titles,
        )
        if curated.get("error"):
            return {"page": target.title, "type": "curate", "error": curated["error"],
                    "before": target.score}

        update_page(target.title,
                    summary=curated.get("summary", ""),
                    tags=curated.get("tags", []),
                    related=curated.get("related", []),
                    collection_id=self.collection_id)
        return {"page": target.title, "type": "curate", "before": target.score,
                "new_title": curated.get("title", target.title)[:50]}

    def _mutate_backfill(self, target: PageFitness) -> Dict:
        """Evidence backfill for pages missing evidence."""
        from core.harness.knowledge.wiki_engine import backfill_evidence_for_page_sync
        r = backfill_evidence_for_page_sync(target.title, collection_id=self.collection_id)
        return {"page": target.title, "type": "backfill", "before": target.score,
                "updated": r.get("updated", False)}

    def _mutate_clean_stale(self, target: PageFitness) -> Dict:
        """Clean stale references from page."""
        from core.harness.knowledge.wiki_engine import clean_stale_references
        r = clean_stale_references(collection_id=self.collection_id)
        return {"page": target.title, "type": "clean_stale", "before": target.score,
                "stale_moved": r.get("stale_refs_moved", 0)}

    # ── Ontology Evolution (Structure Level) ────────────────────────

    def should_run_ontology_phase(self) -> bool:
        """Check if ontology phase should run (every 5 Wiki generations)."""
        last_onto = self._load_onto_state().get("last_onto_gen_id", 0)
        wiki_gens_since = self.generation_id - last_onto
        if wiki_gens_since < 5:
            return False
        try:
            from core.harness.knowledge.knowledge_validator import detect_ontology_patterns
            patterns = detect_ontology_patterns(self.collection_id)
            return (len(patterns.tag_clusters) >= 3 or
                    len(patterns.category_gaps) >= 1 or
                    len(patterns.undefined_relations) >= 1 or
                    len(patterns.cross_page_contradictions) >= 2)
        except Exception:
            return False

    def _run_ontology_phase(self) -> List[Dict]:
        """Execute ontology evolution for one generation. Returns mutations list."""
        from core.harness.knowledge.knowledge_validator import detect_ontology_patterns
        from core.harness.knowledge.knowledge_ontology import CLASSES, OBJECT_PROPERTIES, AI

        patterns = detect_ontology_patterns(self.collection_id)
        mutations = []
        onto_state = self._load_onto_state()

        # ── Step 1: Auto-add new classes from tag clusters ──
        for tc in patterns.tag_clusters:
            if tc.get("count", 0) < 5:
                continue
            tag = tc.get("root_tag", "")
            if not tag or len(tag) < 2:
                continue
            # Check if class already exists (by label)
            existing = [c for c in CLASSES if c.label == tag or tag in c.allowed_categories]
            if existing:
                continue
            result = self._auto_add_class(tag)
            if result:
                mutations.append(result)

        # ── Step 2: Auto-add new properties from undefined relations ──
        for ur in patterns.undefined_relations[:3]:
            rtype = ur.get("type_name", "")
            if not rtype or ur.get("count", 0) < 3:
                continue
            # Check if property already exists
            existing = [op for op in OBJECT_PROPERTIES 
                        if op.uri == f"{AI}{rtype}" or op.label == rtype]
            if existing:
                continue
            result = self._auto_add_property(rtype)
            if result:
                mutations.append(result)

        # ── Step 3: Record high-risk suggestions for human review ──
        suggestions_added = 0
        if patterns.category_gaps:
            from core.harness.knowledge.knowledge_ontology import add_suggestions_from_patterns
            add_suggestions_from_patterns(self.collection_id)
            suggestions_added = 1

        # ── Step 4: Rebuild A-Box and verify ──
        from core.harness.knowledge.knowledge_abox_builder import rebuild_full
        rebuild_full(collection_id=self.collection_id)

        onto_state["last_onto_gen_id"] = self.generation_id
        self._save_onto_state(onto_state)

        if suggestions_added:
            mutations.append({"type": "suggestions_generated", "count": suggestions_added})
        return mutations

    def _auto_add_class(self, tag: str) -> Optional[Dict]:
        """Auto-create a new T-Box class from a high-frequency tag."""
        from core.harness.knowledge.knowledge_ontology import CLASSES, AI
        class_name = ''.join(c for c in tag if c.isalnum() or c in '_-') or tag[:10]
        uri = f"{AI}{class_name}"
        # Double-check no duplicate
        if any(c.uri == uri for c in CLASSES):
            return None
        new_cls = __import__('core.harness.knowledge.knowledge_ontology', fromlist=['OntologyClass']).OntologyClass(
            uri=uri, label=tag,
            parent=f"{AI}ConceptPage",
            required_fields=["title", "body"],
            optional_fields=["summary", "tags", "related", "source_articles"],
            allowed_categories=["entities"],
            extraction_prompt=f"从文档中提取与'{tag}'相关的概念。",
        )
        CLASSES.append(new_cls)
        # Track in onto state
        state = self._load_onto_state()
        state.setdefault("auto_classes", []).append({"uri": uri, "label": tag, "added_at_gen": self.generation_id})
        self._save_onto_state(state)
        logger.info(f"Auto-added ontology class: {tag} ({uri})")
        return {"type": "new_class", "label": tag, "uri": uri}

    def _auto_add_property(self, rtype: str) -> Optional[Dict]:
        """Auto-create a new object property from an undefined relation."""
        from core.harness.knowledge.knowledge_ontology import OBJECT_PROPERTIES, AI
        uri = f"{AI}{rtype}"
        if any(op.uri == uri for op in OBJECT_PROPERTIES):
            return None
        new_prop = __import__('core.harness.knowledge.knowledge_ontology', fromlist=['OntologyObjectProperty']).OntologyObjectProperty(
            uri=uri, label=rtype,
            domain=[f"{AI}WikiPage"], range=[f"{AI}WikiPage"],
        )
        OBJECT_PROPERTIES.append(new_prop)
        state = self._load_onto_state()
        state.setdefault("auto_properties", []).append({"uri": uri, "label": rtype, "added_at_gen": self.generation_id})
        self._save_onto_state(state)
        logger.info(f"Auto-added ontology property: {rtype} ({uri})")
        return {"type": "new_property", "label": rtype, "uri": uri}

    # ── Ontology State Persistence ──────────────────────────────────

    def _onto_state_path(self) -> str:
        wiki_root = _os.path.expanduser(_os.getenv("AIPLAT_HOME", "~/.aiplat"))
        return _os.path.join(wiki_root, "wiki", "collections", self.collection_id,
                             "evolution_ontology_state.json")

    def _load_onto_state(self) -> Dict:
        path = self._onto_state_path()
        if _os.path.exists(path):
            try:
                return _json.loads(open(path).read())
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        return {}

    def _save_onto_state(self, state: Dict):
        path = self._onto_state_path()
        _os.makedirs(_os.path.dirname(path), exist_ok=True)
        _json.dump(state, open(path, "w"), indent=2, ensure_ascii=False)

    def auto_apply_previous_onto_mutations(self):
        """Re-apply auto-added classes/properties on startup (in-memory only)."""
        state = self._load_onto_state()
        if not state:
            return
        from core.harness.knowledge.knowledge_ontology import CLASSES, OBJECT_PROPERTIES, AI

        for ac in state.get("auto_classes", []):
            uri = ac.get("uri", "")
            label = ac.get("label", "")
            if uri and label and not any(c.uri == uri for c in CLASSES):
                new_cls = __import__('core.harness.knowledge.knowledge_ontology', fromlist=['OntologyClass']).OntologyClass(
                    uri=uri, label=label,
                    parent=f"{AI}ConceptPage",
                    required_fields=["title", "body"],
                    optional_fields=["summary", "tags", "related", "source_articles"],
                    allowed_categories=["entities"],
                )
                CLASSES.append(new_cls)

        for ap in state.get("auto_properties", []):
            uri = ap.get("uri", "")
            label = ap.get("label", "")
            if uri and label and not any(op.uri == uri for op in OBJECT_PROPERTIES):
                new_prop = __import__('core.harness.knowledge.knowledge_ontology', fromlist=['OntologyObjectProperty']).OntologyObjectProperty(
                    uri=uri, label=label,
                    domain=[f"{AI}WikiPage"], range=[f"{AI}WikiPage"],
                )
                OBJECT_PROPERTIES.append(new_prop)

    # ── Generation History ──

    def _history_path(self) -> str:
        wiki_root = _os.path.expanduser(
            _os.getenv("AIPLAT_HOME", "~/.aiplat"))
        return _os.path.join(
            wiki_root, "wiki", "collections", self.collection_id,
            "evolution_history.json")

    def _new_pages_since_last_gen(self) -> int:
        """Count pages created since last generation."""
        last_gen = self._load_last_generation_data()
        last_page_count = last_gen.get("page_count", 0) if last_gen else 0
        from core.harness.knowledge.wiki_engine import search_pages
        current = len(search_pages(limit=1000, collection_id=self.collection_id))
        return max(0, current - last_page_count)

    def _golden_quality_degraded(self) -> bool:
        """Check if Golden pass_rate dropped significantly since last generation."""
        last_gen = self._load_last_generation_data()
        if not last_gen:
            return False
        last_pass = last_gen.get("golden_pass_rate", 100)
        try:
            from core.harness.knowledge.knowledge_validator import run_golden_query_regression
            gr = run_golden_query_regression(self.collection_id, strict_mode=False)
            if gr.get("error"):
                return False  # Golden unavailable — not a real degradation
            current_pass = gr.get("pass_rate", 100)
            return (last_pass - current_pass) >= 10 and current_pass < 90
        except Exception:
            return False

    def _load_last_generation_data(self) -> Optional[Dict]:
        """Load last generation's record (page_count + golden_pass_rate)."""
        path = self._history_path()
        if _os.path.exists(path):
            try:
                history = _json.loads(open(path).read())
                if history:
                    return history[-1]
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        return None

    def _load_last_generation_id(self) -> int:
        path = self._history_path()
        if _os.path.exists(path):
            try:
                history = _json.loads(open(path).read())
                if history:
                    return max(h.get("id", 0) for h in history) + 1
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        return 1

    def _record_generation(self, before: Dict, after: Dict,
                           mutations: List[Dict], verdict: str, delta: float,
                           onto_mutations: List[Dict] = None):
        path = self._history_path()
        history = []
        if _os.path.exists(path):
            history = _json.loads(open(path).read())

        entry = {
            "id": self.generation_id - 1,
            "ts": _time.time(),
            "fitness_golden_before": before.get("golden_regression", {}).get("pass_rate", 0),
            "fitness_golden_after": after.get("golden_regression", {}).get("pass_rate", 0),
            "golden_pass_rate": after.get("golden_regression", {}).get("pass_rate", 0),
            "page_count": before.get("coverage", {}).get("total", 0),
            "delta": round(delta, 1),
            "verdict": verdict,
            "mutations_count": len(mutations),
            "onto_mutations_count": len(onto_mutations or []),
            "mutations": [{"page": m.get("page", ""), "type": m.get("type", ""),
                           "before": m.get("before", 0)}
                          for m in mutations[:10]],
            "onto_mutations": [{"type": m.get("type", ""), "label": m.get("label", "")}
                               for m in (onto_mutations or [])[:5]],
        }
        history.append(entry)
        _os.makedirs(_os.path.dirname(path), exist_ok=True)
        _json.dump(history[-50:], open(path, "w"), indent=2, ensure_ascii=False)
        logger.info(f"Generation {entry['id']} recorded: {verdict} (delta={delta})")


# ── Phase 21: Champion management + accept/reject ──────────────────

def get_current_champion(agent_id: str) -> Optional[str]:
    """Return champion prompt from latest generation record."""
    record = _load_latest_generation(agent_id)
    return record.get("champion_prompt") if record else None


def get_champion_score(agent_id: str) -> float:
    """Return champion score from latest generation record."""
    record = _load_latest_generation(agent_id)
    return float(record.get("champion_score", 0)) if record else 0.0


def accept_or_reject(
    *,
    challenger_score: float,
    champion_score: float,
    train_val_split: float = 1.0,
) -> str:
    """Determine if challenger should replace champion.

    When train_val_split < 1.0, this is a placeholder — full train/val
    separation requires per-split score tracking in a future update.
    For now, applies a stricter threshold when split is enabled to
    prevent reward hacking via overfitting.
    """
    if train_val_split == 1.0:
        return "accept" if challenger_score > champion_score else "reject"

    # With train_val_split enabled, require 2% margin to prevent overfitting
    margin = 0.02
    return "accept" if challenger_score > champion_score + margin else "reject"


def _load_latest_generation(agent_id: str) -> Optional[Dict]:
    """Load the latest generation record for an agent."""
    import os as _os
    import json as _json
    path = _os.path.expanduser(f"~/.aiplat/evolution/{agent_id}_generations.json")
    if not _os.path.exists(path):
        return None
    history = _json.load(open(path))
    return history[-1] if history else None
