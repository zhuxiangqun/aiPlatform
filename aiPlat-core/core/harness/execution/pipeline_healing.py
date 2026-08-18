"""PipelineHealingMixin — self-healing strategy methods for PipelineEngine.

Extracted from pipeline_engine.py (P2-A4 Phase 1, 2026-08-18). Pure structure
move: method bodies unchanged, no API/semantics change. PipelineEngine inherits
this mixin; self._extract_json (a PipelineEngine helper) is resolved via the
MRO at runtime.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from core.harness.execution.phase import PipelinePhase
from core.schemas_builder import PipelineStageConfig

logger = logging.getLogger(__name__)


class PipelineHealingMixin:
    """Self-healing: failure classification -> strategy dispatch -> outcome tracking."""

    def _healing_pre_snapshot(self, state, strategy_name):

        """Phase 25: Snapshot execution context before self-healing attempt."""

        try:

            from core.harness.execution.snapshot import save_execution_snapshot

            pre_id = save_execution_snapshot(

                state, f"pre_{strategy_name}",

                session_id=state.get("session_id", ""),

                stage_id=state.get("_last_error_stage", ""),

            )

            state["_last_snapshot_id"] = pre_id

        except Exception:

            logging.getLogger(__name__).debug('_healing_pre_snapshot failed', exc_info=True)

    def _healing_post_snapshot(self, state, strategy_name):

        """Phase 25: Snapshot execution context after self-healing."""

        try:

            from core.harness.execution.snapshot import snapshot_after_heal

            snapshot_after_heal(

                state, strategy_name,

                session_id=state.get("session_id", ""),

                stage_id=state.get("_last_error_stage", ""),

            )

        except Exception:

            logging.getLogger(__name__).debug('_healing_post_snapshot failed', exc_info=True)
        # Phase 26: Record strategy outcome in effectiveness tracker

        success = state.pop("_meta_optimized", False)

        error_type = state.get("_last_healing_reason", "unknown")

        self._record_strategy_outcome(error_type, strategy_name, success)

    def _resolve_best_strategy(self, error_type, classed=None):

        """Phase 29: UCB1-based strategy selection (replaces Phase 26 greedy lookup)."""

        try:

            from core.harness.optimization.search_engine import get_search_engine

            engine = get_search_engine()

            best = engine.select_best(error_type)

            if best:

                return best

            # Cold start: fallback to Phase 26 tracker exploration

            from core.harness.optimization.strategy_tracker import get_strategy_tracker

            return get_strategy_tracker().explore_strategy(error_type)

        except Exception:

            return None

    async def _dispatch_strategy(self, strategy_name, stage, state, classed=None):

        """Phase 26: Dispatch to strategy by name (replaces if/elif chain)."""

        strategy_map = {

            "rotate_credential": self._strategy_rotate_credential,

            "compress_retry": self._strategy_compress_retry,

            "backoff_retry": self._strategy_backoff_retry,

            "skip_stage": self._strategy_skip_stage,

        }

        handler = strategy_map.get(strategy_name)

        if handler:

            return await handler(stage, state)

        return None

    def _record_strategy_outcome(self, error_type, strategy_name, success):

        """Phase 26: Record strategy effectiveness after execution."""

        try:

            from core.harness.optimization.strategy_tracker import get_strategy_tracker

            tracker = get_strategy_tracker()

            tracker.record(error_type, strategy_name, success=success, tokens_used=0)

        except Exception:

            logging.getLogger(__name__).debug('_record_strategy_outcome failed', exc_info=True)

    async def _strategy_rotate_credential(self, stage, state):

        """rate_limit / auth → rotate API key via infra CredentialPool."""

        self._inc_healing_stat("attempts")

        try:

            from infra.management.model.credential_pool import get_credential_pool

            provider = os.getenv("AIPLAT_LLM_PROVIDER", "deepseek")

            pool = get_credential_pool(provider)

            pool.next()

            if pool.key_count > 1:

                state["_meta_diagnosis"] = f"credential_rotated:{provider}({pool.key_count} keys)"

                state["_meta_optimized"] = True

                self._inc_healing_stat("successes")

                logger.warning("[healing] rotated credential: provider=%s keys=%d", provider, pool.key_count)

                self._healing_post_snapshot(state, "rotate_credential")

                return stage

            else:

                logger.warning("[healing] cannot rotate: only 1 key for %s", provider)

        except Exception as e:

            logger.warning("[healing] credential rotation failed: %s", e)

        self._healing_post_snapshot(state, "rotate_credential")

        return None

    async def _strategy_compress_retry(self, stage, state):

        """context_overflow / payload_too_large → flag compression, retry."""

        self._inc_healing_stat("attempts")

        state["_meta_diagnosis"] = "context_overflow: retry with compression"

        state["_meta_optimized"] = True

        state["_force_context_compression"] = True

        self._inc_healing_stat("successes")

        self._healing_post_snapshot(state, "compress_retry")

        return stage

    async def _strategy_backoff_retry(self, stage, state):

        """timeout / overloaded → exponential backoff + retry."""

        self._inc_healing_stat("attempts")

        retry_count = state.get("_auto_retry_count", 0)

        classed = state.get("_last_classified_error", {})

        retry_after = classed.get("retry_after_seconds", 0) if classed else 0

        wait = max(2 ** retry_count, retry_after) if retry_after > 0 else 2 ** retry_count

        wait = min(wait, 60)

        state["_meta_diagnosis"] = f"backoff:{wait}s(retry_count={retry_count})"

        state["_meta_optimized"] = True

        self._inc_healing_stat("successes")

        await asyncio.sleep(wait)

        self._healing_post_snapshot(state, "backoff_retry")

        return stage

    async def _strategy_skip_stage(self, stage, state):

        """billing / model_not_found / server_error → skip this stage.



        Returns None (not stage!) to signal "done with this stage".

        _retry_loop checks _stage_{id}_skipped before setting error.

        """

        self._inc_healing_stat("attempts")

        failure_strategy = getattr(stage, 'failure_strategy', None) or ''

        if failure_strategy == 'skip_stage':

            state["_meta_diagnosis"] = f"skip_stage:{stage.id}"

            state["_meta_optimized"] = True

            state[f"_stage_{stage.id}_done"] = True

            state[f"_stage_{stage.id}_skipped"] = True

            self._inc_healing_stat("skips")

            logger.warning("[healing] skipping stage %s: %s", stage.id, failure_strategy)

        else:

            self._inc_healing_stat("escalations")

            logger.warning("[healing] cannot skip: stage %s failure_strategy=%s", stage.id, failure_strategy)

        self._healing_post_snapshot(state, "skip_stage")

        return None

    async def _strategy_escalate(self, stage, state):

        """unknown / unresolvable → human approval via PolicyGate."""

        self._inc_healing_stat("attempts")

        try:

            from core.harness.infrastructure.gates.policy_gate import PolicyGate

            gate = PolicyGate()

            result = await gate.check_agent(

                user_id=state.get("user_id", "system"),

                agent_id="pipeline_engine",

                agent_args={

                    "_approval_required": True,

                    "_escalation": True,

                    "_error_stage": stage.id,

                    "_error_reason": state.get("_last_classified_error", {}).get("reason", "unknown"),

                    "_tenant_id": state.get("tenant_id", ""),

                },

            )

            if getattr(result, 'decision', None) and str(result.decision) in ("APPROVAL_REQUIRED",):

                state["_meta_diagnosis"] = f"escalated:approval_id={getattr(result, 'approval_request_id', '')}"

                state["_meta_optimized"] = True

                state["phase"] = PipelinePhase.PAUSED

                state["_paused_for_approval"] = True

                state["_approval_request_id"] = getattr(result, "approval_request_id", "")

                self._inc_healing_stat("escalations")

                self._healing_post_snapshot(state, "escalate")

                return None

        except Exception as e:

            logger.warning("[healing] escalation failed: %s", e)

        self._healing_post_snapshot(state, "escalate")

        return None

    def _inc_healing_stat(key):

        stats = getattr(PipelineEngine, '_healing_stats', None)

        if stats is None:

            PipelineEngine._healing_stats = {}

            stats = PipelineEngine._healing_stats

        stats[key] = stats.get(key, 0) + 1

    async def _meta_optimize(self, stage: PipelineStageConfig, report: Dict, state: PipelineState) -> Optional[PipelineStageConfig]:

        """Invoke lightweight Meta-Agent to diagnose and suggest config changes.



        Called by _retry_loop after 3+ retries still REJECTED.

        Modifies stage in-place; returns None if optimization failed.



        Phase 24: Checks _last_classified_error first — if ErrorTranslator has

        classified the failure, uses a specialized strategy instead of generic

        Meta-Agent LLM call. Unclassified errors fall through to original logic.

        """

        # Phase 24: Read and immediately clear error signature (prevents stale data)

        classed = state.pop("_last_classified_error", None)

        state.pop("_last_error", None)



        if classed:

            reason = classed.get("reason", "unknown")

            state["_last_healing_reason"] = reason  # Phase 26: preserve for outcome recording

            # Phase 25: Snapshot execution context before self-healing attempt

            self._healing_pre_snapshot(state, reason)



            # Phase 26: Strategy effectiveness tracker — data-driven routing

            best = self._resolve_best_strategy(reason, classed)

            if best:

                state["_meta_strategy_source"] = "tracker"

                logger.info("[strategy] tracker-selected: %s for %s", best, reason)

                return await self._dispatch_strategy(best, stage, state, classed)



            # Fallback: hardcoded mapping (backward compat + cold start)

            state["_meta_strategy_source"] = "hardcoded"

            if reason in ("rate_limit", "auth", "auth_permanent"):

                if classed.get("should_rotate_credential"):

                    return await self._strategy_rotate_credential(stage, state)

            if reason in ("context_overflow", "payload_too_large"):

                if classed.get("should_compress"):

                    return await self._strategy_compress_retry(stage, state)

            if reason in ("timeout", "overloaded"):

                if classed.get("retryable"):

                    return await self._strategy_backoff_retry(stage, state)

            if reason in ("billing", "model_not_found", "server_error"):

                return await self._strategy_skip_stage(stage, state)

            if reason == "unknown":

                pass  # fall through to Meta-Agent LLM

            else:

                return await self._strategy_escalate(stage, state)



        score = report.get("score", {})

        issues = report.get("issues", [])[:5]

        history = state.get("_score_history", [])



        # Phase 24: Inject error classification into Meta-Agent prompt (fallback path only)

        error_hint = ""

        if classed:

            error_hint = (

                f"\nKnown failure type: {classed['reason']} "

                f"(retryable={classed['retryable']}, "

                f"compress={classed['should_compress']})"

            )

        else:

            err = state.get("_last_error")

            if err:

                error_hint = f"\nLast error: {type(err).__name__}: {str(err)[:200]}"



        diagnosis_prompt = f"""Stage {stage.id} (agent={stage.agent_id}) REJECTED after multiple retries.

Current: agent_type={getattr(stage, 'agent_type', 'react')}, prompt_extra={json.dumps(str(getattr(stage, 'prompt_extra', ''))[:300])}

Evaluation: overall={score.get('overall', '?')}, pass_rate={report.get('pass_rate', '?')}

Dimension scores: {json.dumps({k: v for k, v in score.items() if k != 'overall'})}

Issues: {json.dumps(issues, ensure_ascii=False)}

Score history: {json.dumps([h.get('overall', 0) for h in history[-5:]]) if history else 'none'}

{error_hint}

Output ONLY this JSON (no preamble): {{"diagnosis":"<1 sentence>","suggested_prompt_extra":"<additional content>","suggested_agent_type":"react|plan|reflection","enable_test_plan":false}}"""



        try:

            result_text = await self._stage_runner.run(diagnosis_prompt, state)

            json_str = self._extract_json(result_text)

            if not json_str:

                return stage

            changes = json.loads(json_str)

            if not isinstance(changes, dict):

                return stage



            if changes.get("suggested_prompt_extra") and isinstance(changes["suggested_prompt_extra"], str):

                extra = changes["suggested_prompt_extra"].strip()

                current = getattr(stage, 'prompt_extra', '') or ''

                if extra and extra not in current:

                    stage.prompt_extra = current + "\n" + extra

            if changes.get("suggested_agent_type") in ("plan", "reflection"):

                stage.agent_type = changes["suggested_agent_type"]

            if changes.get("enable_test_plan"):

                stage.generate_test_plan = True



            state["_meta_optimized"] = True

            state["_meta_diagnosis"] = str(changes.get("diagnosis", ""))[:200]

            return stage

        except Exception:

            return stage

    def _extract_keywords(text: str) -> List[str]:

        """Extract technical framework keywords from requirement text.



        Only includes technology-agnostic framework/tool names, NOT business domain terms.

        Business keywords (e-commerce, healthcare, finance, etc.) must be declared

        by the Skill author in its SKILL.md frontmatter, not inferred by the engine.

        """

        import re

        import os as _os

        tech_patterns = [

            r"(?:fastapi|flask|django|express|spring|rails|laravel)",

            r"(?:react|vue|angular|next\.?js|nuxt|svelte)",

            r"(?:postgres|mysql|mongodb|redis|sqlite|mariadb)",

            r"(?:docker|kubernetes|k8s|terraform)",

            r"(?:python|typescript|javascript|go|rust|java|kotlin|swift)",

            r"(?:rest|graphql|grpc|websocket|soap)",

        ]

        extra = _os.getenv("AIPLAT_TECH_KEYWORD_PATTERNS", "")

        if extra:

            tech_patterns.extend([p.strip() for p in extra.split("||") if p.strip()])

        kw = set()

        text_lower = text.lower()

        for p in tech_patterns:

            m = re.findall(p, text_lower)

            for x in m:

                kw.add(x.lower().replace("-", "").replace(".", ""))

        return sorted(kw)[:10]