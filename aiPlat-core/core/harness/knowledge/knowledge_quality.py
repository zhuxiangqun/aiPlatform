"""
Knowledge Quality — feedback loop from pipeline execution to ontology health.

Tracks quality signals from pipeline runs, computes health triggers, and
auto-creates curation tasks when ontology health degrades.

Key flows:
  1. Pipeline stage completes → record_quality_signal(entity_uri, assessment)
  2. Entity accumulates 3+ negative signals → auto-flag as contradicted
  3. A1 violations >10 days unresolved → escalate
  4. Health score < 60 → create full curation task

callers:
  - pipeline_engine._exec_single_stage (record quality signals)
  - pipeline_engine._crystallize_skill (establish TaskSkill↔WikiPage links)
  - wiki.py GET /ontology/health/triggers
  - core_facade.check_ontology_health_triggers()
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.harness.knowledge.knowledge_ontology import KnowledgeOntology

AI = "http://aiplat.local/knowledge#"

logger = logging.getLogger(__name__)


@dataclass
class QualitySignal:
    entity_uri: str
    signal_type: str              # "pipeline_reflection", "schema_validation", "manual_review"
    signal_value: Dict[str, Any]  # quality_assessment, issues_found, etc.
    source: str = ""              # pipeline_stage_id, session_id, reviewer name
    recorded_at: str = ""
    severity: str = "info"        # info, warning, error

    def __post_init__(self):
        if not self.recorded_at:
            self.recorded_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_uri": self.entity_uri,
            "signal_type": self.signal_type,
            "signal_value": self.signal_value,
            "source": self.source,
            "recorded_at": self.recorded_at,
            "severity": self.severity,
        }


def _quality_path(collection_id: str = "default") -> str:
    home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))
    return _os.path.join(home, "wiki", "collections", collection_id, "quality_signals.json")


def sync_quality_to_abox(entity_uri: str, collection_id: str = "default") -> None:
    u"""Sync the latest quality score to the ontology A-Box.

    Call this after recording new quality signals to keep the A-Box
    qualityScore data property in sync with the signal history.
    """
    try:
        score_data = get_entity_quality_score(entity_uri, collection_id=collection_id)
        score = score_data.get("score", 70)
        from core.harness.knowledge.knowledge_ontology import get_ontology, OntologyTriple
        onto = get_ontology()
        # Replace or add qualityScore triple
        for i, t in enumerate(onto.triples):
            if t.subject == entity_uri and t.predicate == f"{AI}qualityScore":
                onto.triples[i] = OntologyTriple(entity_uri, f"{AI}qualityScore", f'"{score}"')
                return
        onto.triples.append(OntologyTriple(entity_uri, f"{AI}qualityScore", f'"{score}"'))
    except Exception as e:
        logger.debug("Sync quality to A-Box skipped: %s", str(e)[:100])


def record_quality_signal(
    entity_uri: str,
    signal_type: str,
    signal_value: Dict[str, Any],
    *,
    source: str = "",
    severity: str = "info",
    collection_id: str = "default",
) -> QualitySignal:
    u"""Record a quality signal for an ontology entity.

    Parameters:
      - signal_type: "pipeline_reflection", "schema_validation", "manual_review"
      - signal_value: dict with quality_assessment, issues_found, etc.
      - source: pipeline stage ID, session ID, or reviewer name.
      - severity: info, warning, error.

    Signals persist to ~/.aiplat/wiki/collections/{id}/quality_signals.json
    """
    signal = QualitySignal(
        entity_uri=entity_uri,
        signal_type=signal_type,
        signal_value=signal_value,
        source=source,
        severity=severity,
    )

    path = _quality_path(collection_id)
    _os.makedirs(_os.path.dirname(path), exist_ok=True)

    existing: List[Dict] = []
    if _os.path.exists(path):
        try:
            existing = _json.load(open(path, "r", encoding="utf-8"))
        except Exception:
            existing = []

    existing.append(signal.to_dict())

    # Keep max 1000 signals to avoid unbounded growth
    if len(existing) > 1000:
        existing = existing[-1000:]

    with open(path, "w", encoding="utf-8") as f:
        _json.dump(existing, f, indent=2, ensure_ascii=False)

    return signal


def get_quality_signals(
    entity_uri: str = "",
    *,
    limit: int = 50,
    collection_id: str = "default",
) -> List[Dict[str, Any]]:
    u"""Get quality signals, optionally filtered by entity_uri.

    Returns signals sorted newest-first.
    """
    path = _quality_path(collection_id)
    if not _os.path.exists(path):
        return []

    try:
        all_signals = _json.load(open(path, "r", encoding="utf-8"))
    except Exception:
        return []

    if entity_uri:
        filtered = [s for s in all_signals if s.get("entity_uri") == entity_uri]
    else:
        filtered = all_signals

    return sorted(filtered, key=lambda s: s.get("recorded_at", ""), reverse=True)[:limit]


def get_entity_quality_score(
    entity_uri: str,
    *,
    collection_id: str = "default",
) -> Dict[str, Any]:
    u"""Compute a 0-100 quality score for an entity based on accumulated signals."""
    signals = get_quality_signals(entity_uri, limit=100, collection_id=collection_id)
    if not signals:
        return {"entity_uri": entity_uri, "score": 70, "signal_count": 0, "assessment": "no_signals"}

    total_weight = 0
    weighted_score = 0
    negative_count = 0
    assessments: Dict[str, int] = {}

    for s in signals:
        weight = 1.0
        age_days = 0
        try:
            recorded = datetime.fromisoformat(s.get("recorded_at", "").replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - recorded).total_seconds() / 86400
            weight = max(0.1, 1.0 - age_days * 0.05)
        except Exception:
            pass

        assessment = s.get("signal_value", {}).get("quality", "")
        if assessment:
            assessments[assessment] = assessments.get(assessment, 0) + 1
            if assessment in ("poor", "outdated", "failed"):
                weighted_score += 0 * weight
                negative_count += 1
            elif assessment in ("adequate", "pass"):
                weighted_score += 60 * weight
            elif assessment in ("good", "acceptable"):
                weighted_score += 80 * weight
            elif assessment in ("excellent", "high"):
                weighted_score += 100 * weight
            else:
                weighted_score += 50 * weight
        else:
            weighted_score += 50 * weight
        total_weight += weight

    if total_weight == 0:
        return {"entity_uri": entity_uri, "score": 70, "signal_count": len(signals), "assessment": "no_weighted_signals"}

    score = int(weighted_score / total_weight)
    assessment = _score_to_assessment(score)

    return {
        "entity_uri": entity_uri,
        "score": score,
        "signal_count": len(signals),
        "negative_signals": negative_count,
        "assessment": assessment,
        "assessment_breakdown": assessments,
    }


def _score_to_assessment(score: int) -> str:
    if score >= 85:
        return "healthy"
    if score >= 70:
        return "stable"
    if score >= 50:
        return "degrading"
    if score >= 30:
        return "at_risk"
    return "critical"


def check_ontology_health_triggers(collection_id: str = "default") -> List[Dict[str, Any]]:
    u"""Run health checks and return triggered curation tasks.

    Triggers:
      1. Overall health score < 60 → full_curation
      2. Entity with 3+ negative quality signals → mark_contradicted
      3. A1 violations older than 10 days → escalate_violation
      4. Entity score < 30 → review_required
    """
    triggers: List[Dict[str, Any]] = []

    # Trigger 1: Overall health from axiom validation
    try:
        from core.harness.knowledge.knowledge_validator import validate_all
        report = validate_all(collection_id=collection_id)
        if report.score < 60:
            triggers.append({
                "type": "full_curation",
                "trigger": "health_score_low",
                "reason": f"Ontology health score dropped to {report.score}/100",
                "violations_top5": [
                    {"axiom": v.axiom_id, "description": v.description, "entities": v.entities[:3]}
                    for v in report.violations[:5]
                ],
                "auto_created": True,
                "created_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            })
    except Exception:
        pass

    # Trigger 2: Accumulated negative quality signals per entity
    try:
        from core.harness.knowledge.knowledge_ontology import get_ontology
        onto = get_ontology()
        entity_uris = set()
        for t in onto.triples:
            if t.predicate == "rdf:type" and "WikiPage" in t.object:
                entity_uris.add(t.subject)

        for uri in list(entity_uris)[:100]:
            quality = get_entity_quality_score(uri, collection_id=collection_id)
            if quality.get("negative_signals", 0) >= 3:
                triggers.append({
                    "type": "mark_contradicted",
                    "trigger": "accumulated_negative_signals",
                    "entity_uri": uri,
                    "reason": f"Entity has {quality['negative_signals']} negative quality signals (score={quality['score']})",
                    "auto_created": True,
                    "created_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                })
            elif quality.get("score", 100) < 30:
                triggers.append({
                    "type": "review_required",
                    "trigger": "entity_score_critical",
                    "entity_uri": uri,
                    "reason": f"Entity quality score is critical ({quality['score']}/100)",
                    "auto_created": True,
                    "created_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                })
    except Exception:
        pass

    # Trigger 3: Aged A1 violations
    try:
        from core.harness.knowledge.knowledge_validator import validate_all
        report = validate_all(collection_id=collection_id)
        now = datetime.now(timezone.utc)
        for v in report.violations:
            if v.axiom_id == "A1":
                age_days = 0
                try:
                    if hasattr(v, 'first_seen') and v.first_seen:
                        age_days = (now - v.first_seen).total_seconds() / 86400
                except Exception:
                    age_days = 1
                if age_days > 10:
                    triggers.append({
                        "type": "escalate_violation",
                        "trigger": "aged_axiom_violation",
                        "axiom_id": "A1",
                        "entity": v.entities[:5],
                        "age_days": round(age_days, 1),
                        "reason": f"A1 violation ({v.description}) unresolved for {round(age_days)} days",
                        "auto_created": True,
                        "created_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                    })
    except Exception:
        pass

    return triggers
