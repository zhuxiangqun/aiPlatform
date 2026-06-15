"""
Knowledge Ontology Action — first-class abstraction for operations on ontology entities.

Defines:
  - EntityLifecycleState: 7-state lifecycle for all ontology entities
  - OntologyAction: semantic action with pre/post-conditions, audit trail, state machine
  - execute_action(): dispatches an action against the ontology, modifying the A-Box

Design reference: Palantir Ontology 'Action' — not an API call, but a semantic operation
with constraint validation, permission checks, audit trail, side effects, and state transition.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from core.harness.knowledge.knowledge_ontology import KnowledgeOntology, OntologyTriple

AI = "http://aiplat.local/knowledge#"

logger = logging.getLogger(__name__)


class EntityLifecycleState(str, Enum):
    PROPOSED = "proposed"
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    CONTRADICTED = "contradicted"


STATE_TRANSITIONS: Dict[EntityLifecycleState, List[EntityLifecycleState]] = {
    EntityLifecycleState.PROPOSED: [
        EntityLifecycleState.DRAFT,
        EntityLifecycleState.UNDER_REVIEW,
    ],
    EntityLifecycleState.DRAFT: [
        EntityLifecycleState.UNDER_REVIEW,
        EntityLifecycleState.PROPOSED,
    ],
    EntityLifecycleState.UNDER_REVIEW: [
        EntityLifecycleState.PUBLISHED,
        EntityLifecycleState.DRAFT,
    ],
    EntityLifecycleState.PUBLISHED: [
        EntityLifecycleState.DEPRECATED,
        EntityLifecycleState.CONTRADICTED,
        EntityLifecycleState.UNDER_REVIEW,
    ],
    EntityLifecycleState.DEPRECATED: [
        EntityLifecycleState.ARCHIVED,
    ],
    EntityLifecycleState.CONTRADICTED: [
        EntityLifecycleState.PUBLISHED,
        EntityLifecycleState.UNDER_REVIEW,
    ],
    EntityLifecycleState.ARCHIVED: [
        EntityLifecycleState.PUBLISHED,
    ],
}


def validate_state_transition(from_state: str, to_state: str) -> Tuple[bool, str]:
    current = EntityLifecycleState(from_state)
    target = EntityLifecycleState(to_state)
    allowed = STATE_TRANSITIONS.get(current, [])
    if target in allowed:
        return True, ""
    return False, (
        f"Invalid state transition: {from_state} → {to_state}. "
        f"Allowed: {[s.value for s in allowed]}"
    )


class ActionVerb(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    CITE = "cite"
    CONTRADICT = "contradict"
    VALIDATE = "validate"
    DEPRECATE = "deprecate"
    ARCHIVE = "archive"
    RESOLVE = "resolve"


@dataclass
class OntologyAction:
    action_id: str
    verb: ActionVerb
    target_entity_uri: str
    actor: str
    payload: Dict[str, Any] = field(default_factory=dict)

    status: str = "pending"
    result: Optional[Dict[str, Any]] = None

    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    required_scopes: List[str] = field(default_factory=list)

    trace_id: Optional[str] = None
    pipeline_stage_id: Optional[str] = None
    session_id: Optional[str] = None

    created_at: str = ""
    completed_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_triples(self) -> List[Any]:
        from core.harness.knowledge.knowledge_ontology import OntologyTriple

        action_uri = f"{AI}Action_{self.action_id}"
        triples: List[OntologyTriple] = []

        triples.append(OntologyTriple(action_uri, "rdf:type", f"{AI}OntologyAction"))
        triples.append(OntologyTriple(action_uri, f"{AI}actionId", f'"{self.action_id}"'))
        triples.append(OntologyTriple(action_uri, f"{AI}verb", f'"{self.verb.value}"'))
        triples.append(OntologyTriple(action_uri, f"{AI}targetEntity", self.target_entity_uri))
        triples.append(OntologyTriple(action_uri, f"{AI}actor", f'"{self.actor}"'))
        triples.append(OntologyTriple(action_uri, f"{AI}status", f'"{self.status}"'))
        if self.trace_id:
            triples.append(OntologyTriple(action_uri, f"{AI}traceId", f'"{self.trace_id}"'))
        if self.session_id:
            triples.append(OntologyTriple(action_uri, f"{AI}sessionId", f'"{self.session_id}"'))

        if self.payload:
            for key, value in self.payload.items():
                if isinstance(value, (str, int, float, bool)):
                    triples.append(OntologyTriple(
                        action_uri, f"{AI}payload_{key}", f'"{value}"'
                    ))

        return triples


@dataclass
class OntologyActionResult:
    action_id: str
    success: bool
    triples_added: int = 0
    triples_removed: int = 0
    state_transition: Optional[Tuple[str, str]] = None
    violations: List[str] = field(default_factory=list)
    error: Optional[str] = None


def execute_action(
    action: OntologyAction,
    onto: KnowledgeOntology,
    *,
    collection_id: str = "default",
) -> OntologyActionResult:
    from core.harness.knowledge.knowledge_ontology import OntologyTriple

    triples_added = 0
    violations: List[str] = []

    if action.status == "completed":
        return OntologyActionResult(
            action_id=action.action_id,
            success=True,
            triples_added=0,
            error="Action already completed",
        )

    # Check preconditions
    for precond in action.preconditions:
        if not _check_precondition(precond, onto, action.target_entity_uri):
            violations.append(f"Precondition failed: {precond}")
            return OntologyActionResult(
                action_id=action.action_id,
                success=False,
                violations=violations,
                error=f"Precondition '{precond}' not satisfied",
            )

    action.status = "executing"

    try:
        if action.verb == ActionVerb.CREATE:
            result = _execute_create(action, onto, collection_id)
        elif action.verb == ActionVerb.UPDATE:
            result = _execute_update(action, onto)
        elif action.verb == ActionVerb.CITE:
            result = _execute_cite(action, onto)
        elif action.verb == ActionVerb.CONTRADICT:
            result = _execute_contradict(action, onto)
        elif action.verb == ActionVerb.VALIDATE:
            result = _execute_validate(action, onto, collection_id)
        elif action.verb == ActionVerb.DEPRECATE:
            result = _execute_state_transition(action, onto, EntityLifecycleState.DEPRECATED)
        elif action.verb == ActionVerb.ARCHIVE:
            result = _execute_state_transition(action, onto, EntityLifecycleState.ARCHIVED)
        elif action.verb == ActionVerb.RESOLVE:
            result = _execute_resolve(action, onto)
        else:
            return OntologyActionResult(
                action_id=action.action_id,
                success=False,
                error=f"Unknown verb: {action.verb}",
            )

        triples_added = result.get("triples_added", 0)
        state_transition = result.get("state_transition")

        # Audit: write action triples to A-Box
        action.status = "completed"
        action.completed_at = datetime.now(timezone.utc).isoformat()
        action_triples = action.to_triples()
        onto.triples.extend(action_triples)
        triples_added += len(action_triples)

        # Phase 5: trigger writebacks to external systems (fire-and-forget)
        _trigger_writebacks(action, collection_id)

        # Check postconditions
        for postcond in action.postconditions:
            if not _check_postcondition(postcond, onto, action.target_entity_uri):
                violations.append(f"Postcondition failed: {postcond}")

        execution_error = result.get("error") if isinstance(result, dict) else None
        success = (
            len([v for v in violations if "Precondition" in v]) == 0
            and execution_error is None
        )

        return OntologyActionResult(
            action_id=action.action_id,
            success=success,
            triples_added=triples_added,
            state_transition=state_transition,
            violations=violations,
            error=execution_error,
        )

    except Exception as e:
        action.status = "failed"
        logger.warning(f"OntologyAction failed: {action.action_id} — {e}")
        return OntologyActionResult(
            action_id=action.action_id,
            success=False,
            triples_added=triples_added,
            error=str(e),
        )


def _execute_create(
    action: OntologyAction, onto: KnowledgeOntology, collection_id: str
) -> Dict[str, Any]:
    from core.harness.knowledge.knowledge_ontology import OntologyTriple, _safe_uri

    triples_added = 0
    payload = action.payload
    entity_uri = action.target_entity_uri
    category = payload.get("category", "entities")
    title = payload.get("title", "")

    # Class assignment
    class_map = {
        "entities": f"{AI}ConceptPage",
        "topics": f"{AI}TopicPage",
        "contradictions": f"{AI}ContradictionPage",
        "atoms": f"{AI}KnowledgeAtom",
    }
    cls_uri = class_map.get(category, f"{AI}WikiPage")
    onto.triples.append(OntologyTriple(entity_uri, "rdf:type", cls_uri))
    triples_added += 1

    # Data properties
    if title:
        onto.triples.append(OntologyTriple(entity_uri, f"{AI}title", f'"{title}"'))
        triples_added += 1
    if payload.get("body"):
        onto.triples.append(OntologyTriple(entity_uri, f"{AI}body", f'"{str(payload["body"])[:5000]}"'))
        triples_added += 1
    if payload.get("summary"):
        onto.triples.append(OntologyTriple(entity_uri, f"{AI}summary", f'"{str(payload["summary"])[:300]}"'))
        triples_added += 1
    if payload.get("category"):
        onto.triples.append(OntologyTriple(entity_uri, f"{AI}category", f'"{payload["category"]}"'))
        triples_added += 1

    # Lifecycle state
    lifecycle = payload.get("lifecycle_state", EntityLifecycleState.PROPOSED.value)
    onto.triples.append(OntologyTriple(entity_uri, f"{AI}lifecycleState", f'"{lifecycle}"'))
    triples_added += 1

    # Source articles → hasSource
    for src in (payload.get("source_articles") or []):
        if isinstance(src, str) and src.strip():
            kb_uri = f"{AI}{_safe_uri(str(src))}"
            onto.triples.append(OntologyTriple(entity_uri, f"{AI}hasSource", kb_uri))
            triples_added += 1

    # Related → cites
    for rel in (payload.get("related") or []):
        if isinstance(rel, str) and rel.strip():
            target_uri = f"{AI}{_safe_uri(rel)}"
            onto.triples.append(OntologyTriple(entity_uri, f"{AI}cites", target_uri))
            triples_added += 1

    # Tags
    for tag in (payload.get("tags") or []):
        if isinstance(tag, str) and tag.strip():
            onto.triples.append(OntologyTriple(entity_uri, f"{AI}tags", f'"{tag}"'))
            triples_added += 1

    # Generation provenance
    if payload.get("_generated_by"):
        gen = payload["_generated_by"]
        gen_str = json.dumps(gen, ensure_ascii=False)
        onto.triples.append(OntologyTriple(entity_uri, f"{AI}generatedBy", f'"{gen_str[:500]}"'))
        triples_added += 1

    return {"triples_added": triples_added}


def _execute_update(action: OntologyAction, onto: KnowledgeOntology) -> Dict[str, Any]:
    triples_added = 0
    triples_removed = 0
    entity_uri = action.target_entity_uri
    payload = action.payload

    for field, value in payload.items():
        if field.startswith("_") or field in ("lifecycle_state", "related", "source_articles"):
            continue
        prop_uri = f"{AI}{field}"
        for t in onto.triples:
            if t.subject == entity_uri and t.predicate == prop_uri:
                onto.triples.remove(t)
                triples_removed += 1
        if value:
            onto.triples.append(
                OntologyTriple(entity_uri, prop_uri, f'"{str(value)[:5000]}"')
            )
            triples_added += 1

    # Lifecycle state transition
    new_state = payload.get("lifecycle_state")
    if new_state:
        current_state = _get_lifecycle_state(entity_uri, onto)
        if current_state and current_state != new_state:
            valid, reason = validate_state_transition(current_state, new_state)
            if not valid:
                return {"triples_added": triples_added, "triples_removed": triples_removed, "error": reason}
            _set_lifecycle_state(entity_uri, new_state, onto)
            triples_added += 1

    return {
        "triples_added": triples_added,
        "triples_removed": triples_removed,
        "state_transition": (current_state, new_state) if new_state else None if current_state else None,
    }


def _execute_cite(action: OntologyAction, onto: KnowledgeOntology) -> Dict[str, Any]:
    target = action.payload.get("target_entity_uri", "")
    if not target:
        return {"triples_added": 0, "error": "No target_entity_uri in payload"}

    from core.harness.knowledge.knowledge_ontology import OntologyTriple
    onto.triples.append(OntologyTriple(action.target_entity_uri, f"{AI}cites", target))
    return {"triples_added": 1}


def _execute_contradict(action: OntologyAction, onto: KnowledgeOntology) -> Dict[str, Any]:
    target = action.payload.get("target_entity_uri", "")
    if not target:
        return {"triples_added": 0, "error": "No target_entity_uri in payload"}

    from core.harness.knowledge.knowledge_ontology import OntologyTriple
    onto.triples.append(
        OntologyTriple(action.target_entity_uri, f"{AI}contradicts", target)
    )
    onto.triples.append(
        OntologyTriple(target, f"{AI}contradicts", action.target_entity_uri)
    )
    _set_lifecycle_state(action.target_entity_uri, EntityLifecycleState.CONTRADICTED.value, onto)
    _set_lifecycle_state(target, EntityLifecycleState.CONTRADICTED.value, onto)
    return {"triples_added": 2}


def _execute_validate(
    action: OntologyAction, onto: KnowledgeOntology, collection_id: str
) -> Dict[str, Any]:
    from core.harness.knowledge.knowledge_validator import validate_entity
    result = validate_entity(action.target_entity_uri, onto)
    return {
        "triples_added": 0,
        "validation": {
            "is_valid": result.get("is_valid", True),
            "issues": result.get("issues", []),
            "axiom_violations": result.get("axiom_violations", []),
        },
    }


def _execute_state_transition(
    action: OntologyAction, onto: KnowledgeOntology, target_state: EntityLifecycleState
) -> Dict[str, Any]:
    entity_uri = action.target_entity_uri
    current = _get_lifecycle_state(entity_uri, onto)
    target_str = target_state.value

    if current:
        valid, reason = validate_state_transition(current, target_str)
        if not valid:
            return {"triples_added": 0, "error": reason}
    else:
        current = EntityLifecycleState.PROPOSED.value

    _set_lifecycle_state(entity_uri, target_str, onto)
    return {
        "triples_added": 1,
        "state_transition": (current, target_str),
    }


def _execute_resolve(action: OntologyAction, onto: KnowledgeOntology) -> Dict[str, Any]:
    entity_uri = action.target_entity_uri
    _set_lifecycle_state(entity_uri, EntityLifecycleState.PUBLISHED.value, onto)

    # Remove contradicts edges to/from this entity
    from core.harness.knowledge.knowledge_ontology import OntologyTriple
    removed = 0
    new_triples = []
    for t in onto.triples:
        if t.predicate == f"{AI}contradicts" and (t.subject == entity_uri or t.object == entity_uri):
            removed += 1
            continue
        new_triples.append(t)
    onto.triples = new_triples

    return {
        "triples_added": 1,
        "state_transition": (EntityLifecycleState.CONTRADICTED.value, EntityLifecycleState.PUBLISHED.value),
    }


def _get_lifecycle_state(entity_uri: str, onto: KnowledgeOntology) -> Optional[str]:
    for t in onto.triples:
        if t.subject == entity_uri and t.predicate == f"{AI}lifecycleState":
            return t.object.strip('"')
    return None


def _set_lifecycle_state(entity_uri: str, state: str, onto: KnowledgeOntology) -> None:
    from core.harness.knowledge.knowledge_ontology import OntologyTriple
    for i, t in enumerate(onto.triples):
        if t.subject == entity_uri and t.predicate == f"{AI}lifecycleState":
            onto.triples[i] = OntologyTriple(entity_uri, f"{AI}lifecycleState", f'"{state}"')
            return
    onto.triples.append(OntologyTriple(entity_uri, f"{AI}lifecycleState", f'"{state}"'))


def _check_precondition(condition: str, onto: KnowledgeOntology, entity_uri: str) -> bool:
    if "must complete without error" in condition.lower():
        return True
    if "must exist" in condition.lower():
        exists = any(
            t.subject == entity_uri and t.predicate.endswith("title")
            for t in onto.triples
        )
        return exists
    if "must have source" in condition.lower():
        return any(
            t.subject == entity_uri and t.predicate == f"{AI}hasSource"
            for t in onto.triples
        )
    return True


def _check_postcondition(condition: str, onto: KnowledgeOntology, entity_uri: str) -> bool:
    if "pass schema validation" in condition.lower():
        return True
    if "must have source" in condition.lower():
        return any(
            t.subject == entity_uri and t.predicate == f"{AI}hasSource"
            for t in onto.triples
        )
    return True


def get_entity_lifecycle_summary(
    onto: KnowledgeOntology,
    collection_id: str = "default",
) -> Dict[str, Any]:
    state_counts: Dict[str, int] = {}
    contradicted_entities: List[str] = []

    for t in onto.triples:
        if t.predicate == f"{AI}lifecycleState":
            state = t.object.strip('"')
            state_counts[state] = state_counts.get(state, 0) + 1
            if state == EntityLifecycleState.CONTRADICTED.value:
                entity_name = t.subject.replace(AI, "")
                if entity_name not in contradicted_entities:
                    contradicted_entities.append(entity_name)

    return {
        "total_entities": sum(state_counts.values()),
        "by_state": state_counts,
        "published_count": state_counts.get(EntityLifecycleState.PUBLISHED.value, 0),
        "contradicted_count": state_counts.get(EntityLifecycleState.CONTRADICTED.value, 0),
        "pending_review_count": state_counts.get(EntityLifecycleState.UNDER_REVIEW.value, 0),
        "contradicted_entities": contradicted_entities[:20],
    }


def new_action_id() -> str:
    return f"action_{uuid.uuid4().hex[:12]}"


def _trigger_writebacks(action: OntologyAction, collection_id: str = "default") -> None:
    u"""Fire-and-forget writeback trigger. Runs in background thread.

    Writeback failures are logged but never block the ontology action.
    """
    import asyncio
    import threading

    def _run():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            from core.harness.knowledge.knowledge_writeback import trigger_writebacks
            results = loop.run_until_complete(trigger_writebacks(action, collection_id=collection_id))
            for r in results:
                if not r.get("success"):
                    logger.warning("Writeback failed: %s → %s", r.get("target"), r.get("error"))
            loop.close()
        except Exception as e:
            logger.debug("Writeback trigger skipped: %s", str(e)[:100])

    t = threading.Thread(target=_run, daemon=True)
    t.start()
