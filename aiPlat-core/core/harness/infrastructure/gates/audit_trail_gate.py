"""AuditTrailGate — capture reasoning trails for compliance audit.



Phase 20: extracts reasoning_path from Agent outputs, matches against

domain YAML audit_rules, generates standardized AuditStep records.



Domain-agnostic: same code works for finance/manufacturing/gov-service.

Agent-agnostic: integrated at integration.py unified exit, not per-agent.

"""



from __future__ import annotations



import json as _json

import hashlib

import logging

import time as _time

from datetime import datetime, timezone

from typing import Any, Dict, List, Optional



from core.harness.kernel.types import AuditStep, EvidenceFingerprint, _normalize_reasoning_path



logger = logging.getLogger("aiplat.audit_trail")





class AuditTrailGate:

    """Capture reasoning trails from Agent outputs into standardized audit records."""



    def capture(

        self,

        result: Any,

        domain_id: str,

        agent_id: str,

        tenant_id: str = "default",

        session_id: str = "",

    ) -> Optional[List[AuditStep]]:

        """Extract reasoning_path, match against domain audit_rules, persist.



        Short-circuits (returns None) when:

          - result is not successful

          - result has no reasoning_path or decision metadata

          - result is a trivial/working_only bypass

        """

        # Triple short-circuit: success, has reasoning, not trivial

        if not getattr(result, "success", False):

            return None



        metadata = getattr(result, "metadata", {}) or {}

        if metadata.get("is_trivial", False):

            return None



        # Extract reasoning data from various output formats

        reasoning_raw = (

            metadata.get("reasoning_path")

            or (metadata.get("decision", {}) or {}).get("reasoning_path")

            or (getattr(result, "output", {}) or {}).get("reasoning_path")

        )

        if not reasoning_raw:

            return None



        # Normalize heterogeneous formats

        reasoning = _normalize_reasoning_path(reasoning_raw)

        if not reasoning:

            return None



        # Load domain audit rules

        from core.harness.ontology_engine.audit_rules import load_audit_rules, match_rule_triggers



        rules = load_audit_rules(domain_id)

        if not rules:

            return None



        # Build decision data for trigger matching

        decision = metadata.get("decision", getattr(result, "output", {}))

        if isinstance(decision, dict):

            decision_data = decision

        else:

            decision_data = {}



        steps: List[AuditStep] = []

        timestamp = datetime.now(timezone.utc).isoformat()



        for i, step_data in enumerate(reasoning):

            parent_id = reasoning[i - 1].get("step") if i > 0 else None



            # Match against domain audit rules

            matched_rule = None

            for rule in rules:

                triggers = rule.get("triggers", [])

                if match_rule_triggers(decision_data, triggers):

                    matched_rule = rule

                    break



            # Build evidence fingerprints

            evidence = []

            if matched_rule:

                for src in matched_rule.get("evidence_sources", []):

                    step_text = str(step_data.get("conclusion", step_data.get("thought", "")))

                    evidence.append(EvidenceFingerprint(

                        source_id=domain_id,

                        source_version="1",

                        source_type=src.get("type", "unknown"),

                        snippet_hash=hashlib.sha256(step_text.encode()).hexdigest()[:16],

                        snippet_preview=step_text[:100],

                        retrieved_at=timestamp,

                        expiry_status="valid",

                    ))



            step = AuditStep(

                step_id=i + 1,

                parent_step_id=parent_id,

                timestamp=timestamp,

                agent=agent_id,

                domain=domain_id,

                session_id=session_id,

                tenant_id=tenant_id,

                trigger=str(step_data.get("trigger", step_data.get("thought", ""))),

                rule_ref=matched_rule["rule_id"] if matched_rule else "",

                evidence=evidence,

                conclusion=str(step_data.get("conclusion", step_data.get("to", step_data.get("thought", "")))),

                confidence=float(step_data.get("confidence", 0)),

                action_triggered=matched_rule.get("action_workflow", "") if matched_rule else "",

                action_target="",

                action_result="recorded",

            )

            steps.append(step)



        # Persist to execution_events

        self._persist_steps(steps)

        return steps



    def _persist_steps(self, steps: List[AuditStep]) -> None:

        """Write audit steps to execution_events table."""

        import os as _os

        import sqlite3 as _sq



        db_path = _os.path.expanduser(

            _os.getenv("AIPLAT_EXECUTION_DB_PATH", "~/.aiplat/aiplat_executions.sqlite3")

        )

        d = _os.path.dirname(db_path)

        if d and not _os.path.exists(d):

            return



        conn = _sq.connect(db_path)

        try:

            now = _time.time()

            for step in steps:

                conn.execute(

                    "INSERT INTO execution_events (event_type, payload, created_at) VALUES (?, ?, ?)",

                    ("audit_trail", _json.dumps(step.to_dict(), ensure_ascii=False), now),

                )

            conn.commit()

        except Exception:

            logging.getLogger(__name__).debug('_persist_steps failed', exc_info=True)
        finally:

            conn.close()

