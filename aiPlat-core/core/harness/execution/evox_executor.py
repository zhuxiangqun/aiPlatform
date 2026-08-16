"""
EvoXExecutor — EvoX swarm executor (Wire AtomicTaskSplitter → PipelineEngine → Collector)

Chains three EvoX stages into a complete swarm execution pipeline:

  1. AtomicTaskSplitter.split() → list of atomic tasks
  2. PipelineEngine FanOut → N independent StageRunners executed in parallel
  3. ProgrammaticCollector.collect_and_detect() → structured merge + loss detection

Callers: REST API /evo/execute / FDE workbench
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.harness.execution.atomic_splitter import AtomicTaskSplitter, SplitResult, AtomicTaskDefinition
from core.harness.execution.programmatic_collector import ProgrammaticCollector, CollectResult, LossReport

logger = logging.getLogger(__name__)


# ── Data Models ──────────────────────────────────────────────────────────

@dataclass
class EvoXResult:
    """EvoX swarm execution result."""
    task: str
    atom_count: int
    coverage_verified: bool

    # execution stage
    atoms_executed: int = 0
    atoms_failed: int = 0

    # merge stage
    collected_count: int = 0
    missed_count: int = 0

    # loss analysis
    total_correct_in_atoms: int = 0
    total_correct_in_final: int = 0
    loss_count: int = 0
    loss_rate: float = 0.0
    retention_rate: float = 100.0
    loss_root_causes: List[str] = field(default_factory=list)

    # summary
    summary: str = ""
    total_time_ms: float = 0.0
    total_tokens: int = 0


# ── EvoXExecutor ──────────────────────────────────────────────────────────

class EvoXExecutor:
    """EvoX swarm executor.

    Usage:
        executor = EvoXExecutor()
        result = await executor.run(
            task="Analyze 563 questions and output all answers",
            max_atoms=50,
            parallel_limit=10,
        )
    """

    def __init__(self, *, max_atoms_default: int = 50, parallel_limit: int = 10):
        self._splitter = AtomicTaskSplitter(max_atoms=max_atoms_default)
        self._collector = ProgrammaticCollector()
        self._parallel_limit = parallel_limit

    async def run(
        self,
        task: str,
        *,
        max_atoms: int = 0,
        domain_hint: str = "",
        existing_state: Optional[Dict[str, Any]] = None,
    ) -> EvoXResult:
        """Complete EvoX swarm pipeline.

        Steps:
          1. atomic split
          2. parallel execution (FanOut)
          3. programmatic merge
          4. loss detection

        Args:
            task: original task description
            max_atoms: maximum number of atoms (0 = use the default)
            domain_hint: domain hint
            existing_state: existing PipelineState (if any)

        Returns:
            EvoXResult
        """
        start_time = _time.time()

        # Step 1: atomic split
        logger.info("EvoX Step 1: Splitting task into atoms...")
        split_result = await self._splitter.split(
            task, max_atoms=max_atoms or self._splitter._max_atoms,
            domain_hint=domain_hint,
        )

        if not split_result.atoms:
            return EvoXResult(
                task=task,
                atom_count=0,
                coverage_verified=False,
                summary="split failed: no atomic tasks generated",
            )

        # Step 2: parallel execution (via PipelineEngine FanOut)
        logger.info("EvoX Step 2: Executing %d atoms in parallel (limit=%d)...",
                     split_result.atom_count, self._parallel_limit)

        state = await self._execute_atoms_in_parallel(
            split_result.atoms,
            existing_state or {},
        )

        # Step 3+4: collect + loss detection
        logger.info("EvoX Step 3+4: Collecting and detecting loss...")
        collect_result, loss_report = self._collector.collect_and_detect(
            state,
            [a.to_dict() for a in split_result.atoms],
            state.get("_final_output"),
        )

        # Step 3.5: Template rendering (if output_template specified)
        template_output = None
        output_template = state.get("_output_template", "")
        if output_template:
            try:
                from core.harness.document.template_engine import TemplateRenderer
                renderer = TemplateRenderer()
                template_output = renderer.render(
                    output_template,
                    collect_result.merged_output if collect_result else {},
                )
                logger.info("Template rendered: %s", template_output.get("path", ""))
            except Exception as e:
                logger.debug("Template rendering skipped: %s", e)

        elapsed = (_time.time() - start_time) * 1000

        return EvoXResult(
            task=task,
            atom_count=split_result.atom_count,
            coverage_verified=split_result.coverage_verified,
            atoms_executed=collect_result.collected_atoms,
            atoms_failed=len(collect_result.missed_atoms),
            collected_count=collect_result.collected_atoms,
            missed_count=len(collect_result.missed_atoms),
            total_correct_in_atoms=loss_report.total_correct_in_atoms if loss_report else 0,
            total_correct_in_final=loss_report.total_correct_in_final if loss_report else 0,
            loss_count=loss_report.loss_count if loss_report else 0,
            loss_rate=loss_report.loss_rate if loss_report else 0.0,
            retention_rate=loss_report.retention_rate if loss_report else 100.0,
            loss_root_causes=loss_report.root_causes if loss_report else [],
            summary=(
                f"split {split_result.atom_count} atoms, collected {collect_result.collected_atoms}, "
                f"loss {loss_report.loss_rate if loss_report else 0}%"
            ),
            total_time_ms=elapsed,
            total_tokens=state.get("tokens_used", 0),
        )

    async def _execute_atoms_in_parallel(
        self,
        atoms: List[AtomicTaskDefinition],
        base_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute atomic tasks in parallel.

        Creates an independent PipelineStage for each atom and limits concurrency via a Semaphore.
        """
        semaphore = asyncio.Semaphore(self._parallel_limit)
        state = dict(base_state)
        state.setdefault("_atom_executions", {})
        total_tokens = state.get("tokens_used", 0)

        async def _run_atom(atom: AtomicTaskDefinition) -> Dict[str, Any]:
            async with semaphore:
                try:
                    from core.harness.utils.model_injection import best_model_for_purpose
                    from core.harness.syscalls.llm import sys_llm_generate

                    # build an independent prompt for each atom
                    prompt = self._build_atom_prompt(atom, base_state)

                    result = await sys_llm_generate(
                        messages=[{"role": "user", "content": prompt}],
                        model=best_model_for_purpose("code_gen"),
                        temperature=0.2,
                        max_tokens=atom.estimated_tokens or 2000,
                    )
                    content = result.get("content", "") if isinstance(result, dict) else str(result)

                    # attempt to parse structured output
                    output = self._parse_atom_output(content, atom)
                    return {atom.atom_id: output}

                except Exception as e:
                    logger.warning("Atom %s failed: %s", atom.atom_id, e)
                    return {atom.atom_id: {"error": str(e)[:200]}}

        # execute all atoms in parallel
        tasks = [_run_atom(atom) for atom in atoms]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # merge results into state
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                atom_id = atoms[i].atom_id if i < len(atoms) else f"atom_{i}"
                state["_atom_executions"][atom_id] = {"error": str(result)}
            elif isinstance(result, dict):
                for key, val in result.items():
                    state[key] = val
                    state["_atom_executions"][key] = val

        # calculate total tokens (best-effort)
        for r in results:
            if isinstance(r, dict):
                for val in r.values():
                    if isinstance(val, dict) and "tokens" in val:
                        total_tokens += val.get("tokens", 0)

        state["tokens_used"] = total_tokens
        return state

    def _build_atom_prompt(
        self,
        atom: AtomicTaskDefinition,
        base_state: Dict[str, Any],
    ) -> str:
        """Build an independent execution prompt for an atomic task."""
        schema_str = _json.dumps(atom.output_schema, ensure_ascii=False) if atom.output_schema else ""
        input_str = _json.dumps(atom.input_schema, ensure_ascii=False) if atom.input_schema else ""

        return f"""Execute the following atomic task.

Task boundary:
{atom.boundary}

Input structure:
{input_str or "no specific input"}

Output requirements:
Output the result strictly following this JSON Schema:
{schema_str or '{{"result": "string"}}'}

Notes:
- Only handle tasks within your boundary
- Output must be valid JSON, no extra text
- If the task is outside your boundary, return {{"skipped": true, "reason": "out of boundary"}}
"""

    def _parse_atom_output(self, content: str, atom: AtomicTaskDefinition) -> Dict[str, Any]:
        """Parse the atomic output into structured data."""
        # extract JSON
        try:
            # handle markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                parts = content.split("```")
                for p in parts:
                    p = p.strip()
                    if p.startswith("{") or p.startswith("["):
                        content = p
                        break

            start = content.find("{")
            if start >= 0:
                end = content.rfind("}")
                if end > start:
                    return _json.loads(content[start:end + 1])

        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        return {"raw_output": content[:1000]}
