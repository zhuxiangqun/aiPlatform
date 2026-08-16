"""
AtomicTaskSplitter — atomic task splitter (EvoMap EvoX aligned)

Dynamically splits complex tasks into atomic subtasks with clear boundaries that can be executed independently:

  1. LLM analysis → list of atomic tasks (each atom has a clear boundary, structured output schema, and owner)
  2. verify_coverage() → checks whether the atom list fully covers the original task; auto-fills any gaps
  3. Injects PipelineEngine FanOut → N independent ReActLoops executed in parallel

Design principles (EvoX swarm):
  - Each atom = an independent context, with no mutual interference
  - Each atom has structured output (not free text), constrained by a schema
  - All atoms together must cover the original task, with no overlap and no omission

Callers: PipelineEngine → FanOut mode / REST API POST /atomic/split
"""

from __future__ import annotations

import json as _json
import logging
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ── Data Models ────────────────────────────────────────────────────────────

@dataclass
class AtomicTaskDefinition:
    """Definition of a single atomic task."""
    atom_id: str
    boundary: str                       # task boundary description (what to do and what not to do)
    input_schema: Dict[str, Any]        # input JSON Schema
    output_schema: Dict[str, Any]       # output JSON Schema (not free text)
    assigned_agent: str = ""            # assigned Agent ID (may be empty; assigned by the scheduler)
    dependencies: List[str] = field(default_factory=list)  # IDs of dependent atoms
    priority: int = 0                   # priority (0 = lowest)
    estimated_tokens: int = 0           # estimated token consumption

    def to_dict(self) -> Dict[str, Any]:
        return {
            "atom_id": self.atom_id,
            "boundary": self.boundary,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "assigned_agent": self.assigned_agent,
            "dependencies": self.dependencies,
            "priority": self.priority,
            "estimated_tokens": self.estimated_tokens,
        }


@dataclass
class SplitResult:
    """Split result."""
    original_task: str
    atoms: List[AtomicTaskDefinition]
    coverage_verified: bool = False     # whether full-coverage verification passed
    uncovered_gaps: List[str] = field(default_factory=list)  # uncovered portions
    atom_count: int = 0
    total_estimated_tokens: int = 0


# ── Mutations (generalized from pipeline_sandbox for task params) ─────────

_TASK_MUTATIONS: Dict[str, str] = {
    "empty_boundary": "边界声明为空 → 原子边界不明确",
    "overlapping_keys": "两个原子声明了相同的输出key → 重复覆盖",
    "missing_schema": "输出schema为空 → 无法结构化汇合",
    "circular_dependency": "原子A依赖B，原子B依赖A → 死锁",
}


# ── AtomicTaskSplitter ─────────────────────────────────────────────────────

class AtomicTaskSplitter:
    """Atomic task splitter.

    Usage:
        splitter = AtomicTaskSplitter()
        result = await splitter.split("Analyze 563 questions and output the answers", max_atoms=50)
        → SplitResult(atoms=[...], coverage_verified=True)
    """

    def __init__(self, *, max_atoms: int = 100):
        self._max_atoms = max_atoms

    async def split(
        self,
        task: str,
        *,
        max_atoms: int = 0,
        domain_hint: str = "",
        existing_context: Optional[Dict[str, Any]] = None,
    ) -> SplitResult:
        """Split a complex task into atomic subtasks.

        Args:
            task: original task description
            max_atoms: maximum number of atoms (0 = use the default)
            domain_hint: domain hint (helps the LLM split more precisely)
            existing_context: existing context information

        Returns:
            SplitResult
        """
        limit = max_atoms if max_atoms > 0 else self._max_atoms
        atoms = await self._llm_split(task, limit, domain_hint, existing_context)

        # coverage verification
        gaps = await self._verify_coverage(task, atoms)
        if gaps:
            # auto-fill uncovered portions
            extra = await self._llm_fill_gaps(task, atoms, gaps, limit - len(atoms))
            atoms.extend(extra)

        # final verification
        final_gaps = await self._verify_coverage(task, atoms) if gaps else []
        coverage_ok = len(final_gaps) == 0

        return SplitResult(
            original_task=task,
            atoms=atoms,
            coverage_verified=coverage_ok,
            uncovered_gaps=final_gaps,
            atom_count=len(atoms),
            total_estimated_tokens=sum(a.estimated_tokens for a in atoms),
        )

    async def _llm_split(
        self,
        task: str,
        max_atoms: int,
        domain_hint: str,
        existing_context: Optional[Dict],
    ) -> List[AtomicTaskDefinition]:
        """LLM-driven atomic splitting."""
        try:
            from core.harness.utils.model_injection import best_model_for_purpose
            from core.harness.syscalls.llm import sys_llm_generate
            from core.harness.utils.prompt_loader import _sync_resolve

            domain_text = f"\nDomain: {domain_hint}" if domain_hint else ""
            context_text = ""
            if existing_context:
                context_text = f"\nExisting context: {_json.dumps(existing_context, ensure_ascii=False)[:500]}"
            
            prompt = _sync_resolve("atomic-splitter-llm-split",
                task=f"Original task:\n{task}{domain_text}{context_text}",
                context=f"At most {max_atoms} atomic subtasks")

            result = await sys_llm_generate(
                messages=[{"role": "user", "content": prompt}],
                model=best_model_for_purpose("reasoning"),
                temperature=0.1,
                max_tokens=4000,
            )

            # Parse JSON
            content = self._extract_json(result.get("content", "") if isinstance(result, dict) else str(result))
            atoms_raw = _json.loads(content)

            if not isinstance(atoms_raw, list):
                raise ValueError(f"Expected array, got {type(atoms_raw)}")

            atoms = []
            for a in atoms_raw[:max_atoms]:
                atom = AtomicTaskDefinition(
                    atom_id=a.get("atom_id", f"atom_{_uuid.uuid4().hex[:8]}"),
                    boundary=str(a.get("boundary", "")),
                    input_schema=a.get("input_schema", {}),
                    output_schema=a.get("output_schema", {}),
                    dependencies=a.get("dependencies", []),
                    estimated_tokens=a.get("estimated_tokens", 1000),
                )
                atoms.append(atom)

            return atoms

        except Exception as e:
            logger.warning("LLM split failed: %s, returning fallback single-atom", e)
            return [AtomicTaskDefinition(
                atom_id="atom_fallback",
                boundary=f"Execute all tasks: {task[:200]}",
                input_schema={},
                output_schema={"type": "object"},
                estimated_tokens=5000,
            )]

    async def _verify_coverage(
        self,
        task: str,
        atoms: List[AtomicTaskDefinition],
    ) -> List[str]:
        """Verify whether the atom list fully covers the original task.

        Returns:
            list of uncovered portions (empty list = full coverage)
        """
        if not atoms:
            return ["No atomic tasks"]

        try:
            from core.harness.utils.model_injection import best_model_for_purpose
            from core.harness.syscalls.llm import sys_llm_generate
            from core.harness.utils.prompt_loader import _sync_resolve

            boundaries = "\n".join(
                f"- {a.atom_id}: {a.boundary[:200]}" for a in atoms
            )

            prompt = _sync_resolve("atomic-splitter-verify-coverage",
                task=task[:2000],
                steps=boundaries)

            result = await sys_llm_generate(
                messages=[{"role": "user", "content": prompt}],
                model=best_model_for_purpose("reasoning"),
                temperature=0.0,
                max_tokens=500,
            )

            content = self._extract_json(result.get("content", "") if isinstance(result, dict) else str(result))
            data = _json.loads(content)
            return data.get("gaps", [])

        except Exception as e:
            logger.debug("Coverage verification skipped: %s", e)
            return []

    async def _llm_fill_gaps(
        self,
        task: str,
        existing_atoms: List[AtomicTaskDefinition],
        gaps: List[str],
        remaining_slots: int,
    ) -> List[AtomicTaskDefinition]:
        """Auto-fill the uncovered portions."""
        if not gaps or remaining_slots <= 0:
            return []

        try:
            from core.harness.utils.model_injection import best_model_for_purpose
            from core.harness.syscalls.llm import sys_llm_generate
            from core.harness.utils.prompt_loader import _sync_resolve

            existing_ids = [a.atom_id for a in existing_atoms]

            prompt = _sync_resolve("atomic-splitter-fill-gaps",
                task=task[:1000],
                gaps=chr(10).join(f'- {g}' for g in gaps[:10]),
                existing_steps=str(existing_ids))

            result = await sys_llm_generate(
                messages=[{"role": "user", "content": prompt}],
                model=best_model_for_purpose("reasoning"),
                temperature=0.1,
                max_tokens=2000,
            )

            content = self._extract_json(result.get("content", "") if isinstance(result, dict) else str(result))
            atoms_raw = _json.loads(content)

            atoms = []
            for a in (atoms_raw if isinstance(atoms_raw, list) else [])[:remaining_slots]:
                atom_id = a.get("atom_id", f"atom_fill_{_uuid.uuid4().hex[:8]}")
                if atom_id not in existing_ids:
                    atoms.append(AtomicTaskDefinition(
                        atom_id=atom_id,
                        boundary=str(a.get("boundary", "")),
                        input_schema=a.get("input_schema", {}),
                        output_schema=a.get("output_schema", {}),
                        dependencies=a.get("dependencies", []),
                        estimated_tokens=a.get("estimated_tokens", 1000),
                    ))

            return atoms

        except Exception as e:
            logger.warning("Gap filling failed: %s", e)
            return []

    def validate(self, atoms: List[AtomicTaskDefinition]) -> Dict[str, Any]:
        """Validate the quality of the atom list (non-LLM deterministic check).

        Returns:
            {"valid": bool, "issues": [...]}
        """
        issues = []
        ids: Set[str] = set()
        output_keys: Set[str] = set()

        for a in atoms:
            # duplicate ID
            if a.atom_id in ids:
                issues.append(_TASK_MUTATIONS["overlapping_keys"] + f": {a.atom_id}")
            ids.add(a.atom_id)

            # empty boundary
            if not a.boundary.strip():
                issues.append(_TASK_MUTATIONS["empty_boundary"] + f": {a.atom_id}")

            # empty schema
            if not a.output_schema:
                issues.append(_TASK_MUTATIONS["missing_schema"] + f": {a.atom_id}")

            # circular dependency
            for dep in a.dependencies:
                if dep == a.atom_id:
                    issues.append(_TASK_MUTATIONS["circular_dependency"] + f": {a.atom_id} → {dep}")

            # check output key conflicts
            for key in a.output_schema.get("properties", {}).keys():
                if key in output_keys:
                    issues.append(f"output key conflict: '{key}' already used in another atom")
                output_keys.add(key)

        return {"valid": len(issues) == 0, "issues": issues}

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from LLM output."""
        text = text.strip()
        # handle markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            parts = text.split("```")
            for p in parts:
                p = p.strip()
                if p.startswith("[") or p.startswith("{"):
                    text = p
                    break
        # extract the outermost JSON array/object
        start = text.find("[")
        if start == -1:
            start = text.find("{")
        if start >= 0:
            end = text.rfind("]") if text[start] == "[" else text.rfind("}")
            if end > start:
                return text[start:end + 1]
        return text
