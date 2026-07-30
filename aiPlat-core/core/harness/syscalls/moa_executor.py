"""
MoA Executor — standalone Mixture-of-Agents syscall (Phase 42).

Extracted from autoreview skill. Generic: any query can go through
parallel Reference engines + Aggregator LLM synthesis.

Architecture:
  Phase 1: asyncio.gather N reference engines (high temp, return_exceptions=True)
  Phase 2: 1 Aggregator LLM (low temp, stream=True → collected internally)

Safety: cost guard (AIPLAT_MOA_MAX_COST_USD), fault tolerance (failed refs annotated),
        stream type safety (internal collection, returns str).
"""

from __future__ import annotations

import asyncio
import logging
import os as _os
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger("moa_executor")

_MAX_MOA_COST_USD = float(_os.getenv("AIPLAT_MOA_MAX_COST_USD", "0.10"))


@dataclass
class MoaResult:
    query: str
    preset: str
    reference_outputs: List[str] = field(default_factory=list)
    failed_references: List[str] = field(default_factory=list)
    final_answer: str = ""
    duration_ms: float = 0.0
    estimated_cost_usd: float = 0.0


# ── Preset cache ──
_PRESET_CACHE: Optional[Dict] = None


def _load_moa_preset(name: str) -> dict:
    global _PRESET_CACHE
    if _PRESET_CACHE is None:
        import yaml as _yaml
        config_path = _os.path.join(_os.path.dirname(__file__), "moa_presets.yaml")
        with open(config_path) as f:
            _PRESET_CACHE = _yaml.safe_load(f)
    preset = _PRESET_CACHE.get(name)
    if preset is None:
        _log.warning("MoA preset '%s' not found, falling back to 'general'", name)
        return _PRESET_CACHE.get("general", {})
    return preset


def _estimate_cost(models: List[str], agg_model: str, query: str) -> float:
    est_input = max(1, len(query) // 4)
    est_output = est_input * 2
    total_tokens = est_input * (len(models) + 1) + est_output * (len(models) + 1)
    return total_tokens * 2e-6  # ~$2/M tokens


async def _single_model_fallback(query: str, model_purpose: str) -> MoaResult:
    from core.harness.utils.model_injection import best_model_for_purpose
    from core.harness.syscalls.llm import sys_llm_generate
    model = best_model_for_purpose(model_purpose)
    resp = await sys_llm_generate(model=None,
        prompt=[{"role": "user", "content": query}],
        model_name=model, temperature=0.3,
    )
    return MoaResult(
        query=query, preset="fallback",
        reference_outputs=[],
        final_answer=str(resp),
        estimated_cost_usd=0.0,
    )


def _build_aggregator_prompt(
    query: str, ref_outputs: List[str], model_names: List[str],
    failed_refs: List[str], agg_instruction: str,
) -> str:
    lines = [f"Original query: {query}\n"]
    lines.append(f"Available reference analyses ({len(ref_outputs)} total, "
                 f"{len(failed_refs)} failed):\n")
    for i, (name, output) in enumerate(zip(model_names, ref_outputs)):
        status = "OK" if name not in failed_refs else "FAILED"
        lines.append(f"### Reference {i+1}: {name} [{status}]")
        lines.append(output[:2000])
        lines.append("")
    if failed_refs:
        lines.append(f"Note: {len(failed_refs)} engine(s) failed: {', '.join(failed_refs)}. "
                      "Consider this when weighing evidence.")
    if agg_instruction:
        lines.insert(1, f"Instruction: {agg_instruction}\n")
    lines.append("Synthesize the above into one coherent, well-reasoned answer. "
                 "If analyses conflict, explain the disagreement and give your best judgment.")
    return "\n".join(lines)


async def execute(
    query: str,
    preset: str = "general",
    *,
    max_reference_models: int = 4,
    session_id: str = "",
) -> MoaResult:
    t0 = _time.monotonic()
    preset_config = _load_moa_preset(preset)
    ref_models = preset_config["reference_models"][:max_reference_models]
    agg_model = preset_config["aggregator_model"]
    ref_temp = preset_config["temperatures"]["reference"]
    agg_temp = preset_config["temperatures"]["aggregator"]
    agg_instruction = preset_config.get("aggregator_instruction", "")

    # ── Cost guard ──
    estimated_cost = _estimate_cost(ref_models, agg_model, query)
    if estimated_cost > _MAX_MOA_COST_USD:
        _log.warning("MoA cost $%.4f exceeds budget $%.2f, falling back to single model",
                      estimated_cost, _MAX_MOA_COST_USD)
        result = await _single_model_fallback(query, ref_models[0])
        result.duration_ms = (_time.monotonic() - t0) * 1000
        result.estimated_cost_usd = estimated_cost
        return result

    from core.harness.utils.model_injection import best_model_for_purpose
    from core.harness.syscalls.llm import sys_llm_generate

    # ── Phase 1: Parallel reference engines (fault tolerant) ──
    engines = [(best_model_for_purpose(m), role) for m, role in
               zip(ref_models, preset_config["roles"])]

    responses = await asyncio.gather(*(
        sys_llm_generate(model=None,
            prompt=[
                {"role": "system", "content": "You are an expert analyst. Think carefully."},
                {"role": "user", "content": f"{query}\n\n{role_hint}"},
            ],
            model_name=model,
            temperature=ref_temp,
        )
        for model, role_hint in engines
    ), return_exceptions=True)

    ref_outputs = []
    failed_refs = []
    for i, r in enumerate(responses):
        if isinstance(r, Exception):
            failed_refs.append(ref_models[i])
            ref_outputs.append(f"[ERROR] Engine {ref_models[i]} failed: {str(r)[:200]}")
        else:
            ref_outputs.append(str(r))

    # ── Phase 2: Aggregator (stream internally, return str) ──
    agg_model_name = best_model_for_purpose(agg_model)
    agg_prompt = _build_aggregator_prompt(
        query, ref_outputs, ref_models, failed_refs, agg_instruction,
    )

    final_resp = await sys_llm_generate(model=None,
        prompt=[
            {"role": "system", "content": agg_instruction or
                "Synthesize the following analyses into one coherent answer."},
            {"role": "user", "content": agg_prompt},
        ],
        model_name=agg_model_name,
        temperature=agg_temp,
    )
    final = str(final_resp)

    return MoaResult(
        query=query, preset=preset,
        reference_outputs=ref_outputs,
        failed_references=failed_refs,
        final_answer=final,
        duration_ms=(_time.monotonic() - t0) * 1000,
        estimated_cost_usd=estimated_cost,
    )
