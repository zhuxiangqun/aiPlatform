"""
ProgrammaticCollector — programmatic result merge + loss detection (EvoMap EvoX aligned)

Bypasses LLM paraphrasing and structurally collects atomic task outputs from PipelineState by key.
Compares each atom's correct output vs the final aggregate to compute the information loss rate.

Design principles (EvoX):
  - The Agent solves problems; the application collects the results
  - Structured output is written to a fixed location (state[output_artifact])
  - The program collects directly by key; correct answers do not need to be re-read by another LLM
  - Loss detection: compare atomic correct results → aggregate result, and compute the loss rate

Callers: PipelineEngine → collector stage / REST API
"""

from __future__ import annotations

import json as _json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ── Data Models ────────────────────────────────────────────────────────────

@dataclass
class CollectResult:
    """Merge result."""
    total_atoms: int
    collected_atoms: int
    missed_atoms: List[str] = field(default_factory=list)  # atoms that produced no result
    merged_output: Dict[str, Any] = field(default_factory=dict)  # merged structured output
    merged_summary: str = ""           # human-readable summary


@dataclass
class LossReport:
    """Loss analysis report."""
    total_correct_in_atoms: int        # number of correct items at the atom stage
    total_correct_in_final: int        # number of correct items in the final aggregate
    loss_count: int                    # number of lost items
    loss_rate: float                   # loss rate (%)
    loss_details: List[Dict[str, Any]] = field(default_factory=list)  # details for each lost item
    root_causes: List[str] = field(default_factory=list)  # root-cause analysis
    retention_rate: float = 0.0        # retention rate (%)


# ── ProgrammaticCollector ──────────────────────────────────────────────────

class ProgrammaticCollector:
    """Programmatic result merge.

    Usage:
        collector = ProgrammaticCollector()
        result = collector.collect(state, atom_definitions)
        loss = collector.detect_loss(atom_outputs, final_output, atom_defs)
    """

    def collect(
        self,
        state: Dict[str, Any],
        atom_definitions: List[Dict[str, Any]],
        *,
        merge_strategy: str = "by_schema",
    ) -> CollectResult:
        """Structurally collect all atomic outputs from PipelineState by key.

        Args:
            state: PipelineState (containing each atom's output_artifact)
            atom_definitions: list of atomic task definitions (from AtomicTaskSplitter)
            merge_strategy: merge strategy — "by_schema" (align by schema) | "concat" (simple concatenation)

        Returns:
            CollectResult
        """
        collected = {}
        missed = []

        for atom_def in atom_definitions:
            atom_id = atom_def.get("atom_id", "")
            output_key = atom_def.get("output_artifact", atom_id)
            output_schema = atom_def.get("output_schema", {})

            # read directly from state (without going through the LLM)
            atom_output = state.get(output_key)

            if atom_output is None:
                # Try alternate keys
                for alt_key in [f"atom_{atom_id}", atom_id, f"output_{atom_id}"]:
                    atom_output = state.get(alt_key)
                    if atom_output is not None:
                        break

            if atom_output is None:
                missed.append(atom_id)
                continue

            # validate and extract by schema
            extracted = self._extract_by_schema(atom_output, output_schema, atom_id)
            if extracted:
                collected[atom_id] = extracted

        # merge all collected results
        merged = self._merge_outputs(collected, atom_definitions, merge_strategy)

        return CollectResult(
            total_atoms=len(atom_definitions),
            collected_atoms=len(collected),
            missed_atoms=missed,
            merged_output=merged,
            merged_summary=f"collected {len(collected)}/{len(atom_definitions)} atoms (missing {len(missed)})",
        )

    def _extract_by_schema(
        self,
        atom_output: Any,
        output_schema: Dict[str, Any],
        atom_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Extract structured data according to the output schema."""
        # if already a dict, extract fields directly per the schema
        if isinstance(atom_output, dict):
            props = output_schema.get("properties", {})
            if not props:
                return {atom_id: atom_output}

            result = {}
            for key in props:
                if key in atom_output:
                    result[key] = atom_output[key]
            return {atom_id: result} if result else {atom_id: atom_output}

        # string type → attempt to parse JSON
        if isinstance(atom_output, str):
            try:
                data = _json.loads(atom_output)
                return self._extract_by_schema(data, output_schema, atom_id)
            except Exception:
                return {atom_id: {"raw_output": atom_output[:500]}}

        return {atom_id: {"output": str(atom_output)[:500]}}

    def _merge_outputs(
        self,
        collected: Dict[str, Dict[str, Any]],
        atom_definitions: List[Dict[str, Any]],
        strategy: str,
    ) -> Dict[str, Any]:
        """Merge the outputs of each atom."""
        if strategy == "concat":
            return {"atoms": collected, "total": len(collected)}

        # By schema: group by atom ID and attempt to align to the same schema
        merged: Dict[str, Any] = {"atoms": {}, "summary": {}}

        for atom_id, data in collected.items():
            merged["atoms"][atom_id] = data

            # extract numeric results for aggregation
            for key, val in data.items():
                if isinstance(val, (int, float)):
                    merged["summary"].setdefault(key, 0)
                    merged["summary"][key] += val
                elif isinstance(val, dict) and "correct_count" in val:
                    merged["summary"].setdefault("correct_count", 0)
                    merged["summary"]["correct_count"] += val["correct_count"]

        merged["summary"]["atoms_collected"] = len(collected)
        return merged

    def detect_loss(
        self,
        atom_outputs: Dict[str, Any],
        final_output: Dict[str, Any],
        atom_definitions: List[Dict[str, Any]],
    ) -> LossReport:
        """Detect information loss during aggregation.

        Compares the correct results in each atomic output vs the correct results in the final aggregate output.

        Args:
            atom_outputs: structured output of each atom {atom_id: {result...}}
            final_output: final aggregate output (possibly summarized by an LLM)
            atom_definitions: atomic task definitions

        Returns:
            LossReport
        """
        total_correct = 0
        correct_items: Set[str] = set()
        loss_details: List[Dict[str, Any]] = []

        # Step 1: count the correct results in each atom
        for atom_id, data in atom_outputs.items():
            if isinstance(data, dict):
                # look for the correctness marker
                for key in ["correct_count", "passed", "success_count"]:
                    if key in data:
                        val = data[key]
                        if isinstance(val, (int, float)) and val > 0:
                            total_correct += int(val)
                            correct_items.add(atom_id)

                # look for the answers dict
                answers = data.get("answers", {})
                if isinstance(answers, dict):
                    for qid, answer in answers.items():
                        correct_items.add(f"{atom_id}:{qid}")

        # Step 2: count the correct results in the final aggregate
        final_correct = 0
        if isinstance(final_output, dict):
            for key in ["correct_count", "passed", "total_correct"]:
                if key in final_output:
                    val = final_output[key]
                    if isinstance(val, (int, float)):
                        final_correct = int(val)
                        break

            # also check answers
            final_answers = final_output.get("answers", {})
            if isinstance(final_answers, dict):
                final_correct = max(final_correct, len(final_answers))

        # Step 3: compare for loss
        loss_count = max(0, total_correct - final_correct)
        loss_rate = (loss_count / max(total_correct, 1)) * 100

        # Step 4: root-cause analysis
        root_causes = []
        if loss_count > 0:
            if final_correct < total_correct and final_output:
                root_causes.append(
                    f"information loss during aggregation: {total_correct} correct at atom stage -> only {final_correct} correct after aggregation"
                )
            if isinstance(final_output, str) and len(str(final_output)) < 200:
                root_causes.append("aggregation output too concise, may have lost details")

            # Check for missing atoms
            missed = [d.get("atom_id", "") for d in atom_definitions
                      if d.get("atom_id", "") not in atom_outputs]
            if missed:
                root_causes.append(f"{len(missed)} atoms produced no result or results were not collected")

        return LossReport(
            total_correct_in_atoms=total_correct,
            total_correct_in_final=final_correct,
            loss_count=loss_count,
            loss_rate=round(loss_rate, 1),
            loss_details=loss_details[:50],
            root_causes=root_causes,
            retention_rate=round(100 - loss_rate, 1),
        )

    def collect_and_detect(
        self,
        state: Dict[str, Any],
        atom_definitions: List[Dict[str, Any]],
        final_output: Optional[Dict[str, Any]] = None,
    ) -> Tuple[CollectResult, Optional[LossReport]]:
        """One-shot execution: collect + loss detection.

        Returns:
            (CollectResult, Optional[LossReport])
        """
        collect_result = self.collect(state, atom_definitions)

        loss_report = None
        if final_output and collect_result.collected_atoms > 0:
            loss_report = self.detect_loss(
                collect_result.merged_output.get("atoms", {}),
                final_output,
                atom_definitions,
            )

        # if there is loss, write it to lineage_decisions
        if loss_report and loss_report.loss_count > 0:
            self._write_loss_to_lineage(state, loss_report)

        return collect_result, loss_report

    def _write_loss_to_lineage(
        self,
        state: Dict[str, Any],
        loss_report: LossReport,
    ) -> None:
        """Write the loss analysis to Decision Lineage (best-effort)."""
        try:
            from core.harness.infrastructure.lineage_store import LineageStore, DecisionRecord

            run_id = state.get("session_id", "") or state.get("_simulation_id", "unknown")
            if not run_id:
                return

            store = LineageStore.get()
            record = DecisionRecord(
                run_id=run_id,
                decision_type="loss_detection",
                chosen_option="structured_collect",
                choice_reasoning=(
                    f"loss analysis: {loss_report.total_correct_in_atoms}->{loss_report.total_correct_in_final} "
                    f"(lost {loss_report.loss_count}, retention {loss_report.retention_rate}%). "
                    f"root cause: {'; '.join(loss_report.root_causes[:3])}"
                ),
                outcome_status="logged",
                outcome_summary=f"Loss rate: {loss_report.loss_rate}%",
            )
            store.insert(record)

        except Exception as e:
            logger.debug("Loss lineage write skipped: %s", e)
