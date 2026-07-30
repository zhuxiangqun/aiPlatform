"""

PromptAssembler (Phase 4 - minimal).



Phase 4 minimal contract:

- Accepts a prompt input (str or list[message dict])

- Produces a normalized message list and a stable prompt_version



Notes:

- This is intentionally *non-invasive*: by default it preserves the original

  content and only adds versioning metadata.

- Token budgeting / compaction will be handled by ContextAssembler in Phase 4.1+.

"""



from __future__ import annotations

import logging



import hashlib

import json

from dataclasses import dataclass, field

from typing import Any, Dict, List, Optional, Union



from core.harness.kernel.execution_context import get_active_workspace_context

from core.harness.context.engine import DefaultContextEngine





Message = Dict[str, Any]

_DEFAULT_CONTEXT_ENGINE = DefaultContextEngine()





@dataclass

class PromptAssemblyResult:

    messages: List[Message]

    prompt_version: str

    metadata: Dict[str, Any] = field(default_factory=dict)

    # Roadmap-1: stable vs ephemeral split for caching/debugging

    stable_system_prompt: str = ""

    ephemeral_overlay: str = ""

    stable_prompt_version: str = ""

    stable_cache_key: Optional[str] = None

    stable_cache_hit: bool = False

    workspace_context_hash: Optional[str] = None





class MessageFormatter:

    """

    Kernel-side prompt assembler.



    Versioning:

    - prompt_version is a sha256 of canonical JSON serialization of messages.

    - This is deterministic and suitable for replay/debugging.

    """



    def assemble(

        self,

        prompt: Union[str, List[Message]],

        *,

        metadata: Optional[Dict[str, Any]] = None,

    ) -> PromptAssemblyResult:

        msgs = self._normalize(prompt)

        meta = dict(metadata or {})



        # Prompt Mode (OpenClaw-like): full/minimal/none

        # - full: default, allow all context injections

        # - minimal: keep only stable context (e.g., project context), skip heavy overlays

        # - none: disable context injection (for tightly-scoped subagents/jobs)

        try:

            if "prompt_mode" not in meta:

                from core.harness.kernel.execution_context import get_active_request_context



                rctx = get_active_request_context()

                ep = (getattr(rctx, "entrypoint", None) or "").lower() if rctx else ""

                if ep in {"subagent", "cron", "scheduler", "job"}:

                    meta["prompt_mode"] = "minimal"

                else:

                    meta["prompt_mode"] = "full"

        except Exception:

            meta.setdefault("prompt_mode", "full")



        # Roadmap-1 (Phase 1): ContextEngine handles project context injection.

        try:

            ctx = get_active_workspace_context()

            if ctx and getattr(ctx, "claude_md_files", None):

                meta.setdefault("claude_md_files", list(getattr(ctx, "claude_md_files", None) or []))



            # PR #2: 从 ControlProfile 读取上下文层数上限

            try:

                from core.harness.meta.profile_registry import get_active_profile

                profile = get_active_profile()

                meta.setdefault("context_layers", profile.context_layers)

                meta.setdefault("context_max_sources", profile.context_max_sources)

            except Exception:

                logging.getLogger(__name__).debug('assemble failed', exc_info=True)


            res = _DEFAULT_CONTEXT_ENGINE.apply(

                messages=msgs, metadata=meta, repo_root=str(ctx.repo_root) if ctx and ctx.repo_root else None

            )

            msgs, meta = res.messages, res.metadata

            if getattr(res, "workspace_context_hash", None):

                meta.setdefault("workspace_context_hash", getattr(res, "workspace_context_hash", None))

            if getattr(res, "status", None) and isinstance(getattr(res, "status", None), dict):

                meta.setdefault("context_status", getattr(res, "status", None))

        except Exception as e:

            logging.debug(str(e), exc_info=True)



        # ── Architecture Contract Injection ──

        # For code-generation skills, inject architecture constraints

        # BEFORE code is written (not just checked in CI).

        try:

            skill_name = (meta.get("skill_name") or "").lower()

            coding_skills = {

                "code_generation", "code-hygiene", "code_review",

                "code_generator", "code_generate", "generate_code",

                "refactor", "fix_bug", "implement",

            }

            if skill_name in coding_skills or meta.get("inject_arch_contract"):

                from core.harness.utils.prompt_loader import _sync_resolve

                contract = _sync_resolve("coding-contract")

                if isinstance(prompt, str):

                    prompt = prompt + "\n" + contract

                elif isinstance(prompt, list) and prompt:

                    sys_idx = next((i for i, m in enumerate(prompt)

                                    if m.get("role") == "system"), None)

                    if sys_idx is not None:

                        prompt[sys_idx]["content"] = str(prompt[sys_idx].get("content", "")) + "\n" + contract

                    else:

                        prompt.insert(0, {"role": "system", "content": contract})

        except Exception as e:

            logging.debug(str(e), exc_info=True)



        # Roadmap-1 (Phase 1): lightweight prompt stats (no behavior change).

        try:

            meta.setdefault("context_engine", "default_v1")

            meta.setdefault("prompt_message_count", len(msgs))

            meta.setdefault("prompt_estimated_tokens", self._estimate_tokens(msgs))

        except Exception as e:

            logging.debug(str(e), exc_info=True)



        version = self._hash_messages(msgs)

        meta.setdefault("versioning", "sha256(messages)")



        stable_system, overlay = self._split_system_layers(msgs)

        stable_prompt_version = hashlib.sha256(stable_system.encode("utf-8")).hexdigest() if stable_system else ""

        w_hash = meta.get("workspace_context_hash")

        stable_cache_key = self._build_stable_cache_key(

            meta=meta, stable_prompt_version=stable_prompt_version, workspace_context_hash=w_hash

        )

        # B: Three-layer cache markers for prompt caching

        meta.setdefault("cache_layers", {

            "stable": bool(stable_system),      # identity + tools + skills

            "context": bool(w_hash),             # workspace + project

            "volatile": True,                    # memory + time + recent

        })

        stable_cache_hit = False

        if stable_cache_key:

            stable_cache_hit = _STABLE_PROMPT_CACHE.get(stable_cache_key) == stable_system

            _STABLE_PROMPT_CACHE[stable_cache_key] = stable_system

            # trim cache

            if len(_STABLE_PROMPT_CACHE) > 256:

                try:

                    for k in list(_STABLE_PROMPT_CACHE.keys())[:64]:

                        _STABLE_PROMPT_CACHE.pop(k, None)

                except Exception:

                    _STABLE_PROMPT_CACHE.clear()



        # PR #3: CacheAwareRouter — 若 D1/D2 未变更,复用 stable_system 前缀

        try:

            from core.harness.meta.profile_registry import get_active_profile

            from core.harness.meta.cache_aware_router import get_cache_router

            cache_router = get_cache_router()

            cache_action = cache_router.evaluate(get_active_profile())

            if "D1" in cache_action.get("freeze", []):

                meta.setdefault("cache_frozen_dims", cache_action["freeze"])

                # 保留 stable_system 不变，D3-D6 通过 overlay 追加

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)


        meta.setdefault("stable_prompt_version", stable_prompt_version)

        if stable_cache_key:

            meta.setdefault("stable_cache_key", stable_cache_key)

            meta.setdefault("stable_cache_hit", bool(stable_cache_hit))

        meta.setdefault("stable_system_prompt_chars", len(stable_system))

        meta.setdefault("ephemeral_overlay_chars", len(overlay))



        # Roadmap-1: enrich context_status with cache + token-ish metrics (best-effort).

        try:

            cs = meta.get("context_status") if isinstance(meta.get("context_status"), dict) else None

            if cs is not None:

                cs.setdefault("stable_cache", {})

                if isinstance(cs.get("stable_cache"), dict):

                    cs["stable_cache"]["key"] = stable_cache_key

                    cs["stable_cache"]["hit"] = bool(stable_cache_hit)

                    cs["stable_cache"]["stable_prompt_version"] = stable_prompt_version

                cs.setdefault("workspace_context_hash", w_hash)

                cs.setdefault("system_layers", {})

                if isinstance(cs.get("system_layers"), dict):

                    cs["system_layers"]["stable_system_prompt_chars"] = len(stable_system)

                    cs["system_layers"]["ephemeral_overlay_chars"] = len(overlay)

                    cs["system_layers"]["stable_system_prompt_token_estimate"] = int(len(stable_system) // 4) if stable_system else 0

                    cs["system_layers"]["ephemeral_overlay_token_estimate"] = int(len(overlay) // 4) if overlay else 0

                cs.setdefault("prompt", {})

                if isinstance(cs.get("prompt"), dict):

                    cs["prompt"]["message_count"] = len(msgs)

                    cs["prompt"]["estimated_tokens"] = meta.get("prompt_estimated_tokens")

        except Exception as e:

            logging.debug(str(e), exc_info=True)



        return PromptAssemblyResult(

            messages=msgs,

            prompt_version=version,

            metadata=meta,

            stable_system_prompt=stable_system,

            ephemeral_overlay=overlay,

            stable_prompt_version=stable_prompt_version,

            stable_cache_key=stable_cache_key,

            stable_cache_hit=stable_cache_hit,

            workspace_context_hash=str(w_hash) if w_hash is not None else None,

        )



    # -----------------------------

    # Phase 4: centralized templates

    # -----------------------------



    def build_react_reasoning_messages(

        self,

        *,

        task: str,

        history: str,

        tools_desc: str,

        skills_desc: str = "",

        observation: str,

    ) -> List[Message]:

        msgs: List[Message] = []

        has_tools = tools_desc and tools_desc != "No tools available"

        if has_tools:

            from core.harness.utils.prompt_loader import _sync_resolve

            msgs.append({"role": "system", "content": _sync_resolve("browser-assistant")})



        from core.harness.utils.prompt_loader import _sync_resolve

        prompt = _sync_resolve("react-reasoning",

            task=task, history=history, tools_desc=tools_desc,

            skills_desc=skills_desc or "", observation=observation,

            mem_hints="", bus_hints="",

        )

        msgs.append({"role": "user", "content": prompt})

        return msgs



    def build_plan_execute_plan_messages(self, *, task: str) -> List[Message]:

        from core.harness.utils.prompt_loader import _sync_resolve

        prompt = _sync_resolve("plan-execute-plan", task=task, context="")

        return [{"role": "user", "content": prompt}]



    def build_plan_execute_step_messages(self, *, action: str, task: str) -> List[Message]:

        prompt = f"Execute this step: {action}\nContext: {task}"

        return [{"role": "user", "content": prompt}]



    def build_langgraph_reason_messages(

        self,

        *,

        history: str,

        reasoning: str,

        action: str,

        observation: str,

    ) -> List[Message]:

        from core.harness.utils.prompt_loader import _sync_resolve

        prompt = _sync_resolve("langgraph-reason",

            history=history, reasoning=reasoning, action=action, observation=observation,

        )

        return [{"role": "user", "content": prompt}]



    def build_langgraph_observe_messages(self, *, observation: str) -> List[Message]:

        from core.harness.utils.prompt_loader import _sync_resolve

        prompt = _sync_resolve("langgraph-observe", observation=observation)

        return [{"role": "user", "content": prompt}]



    def _normalize(self, prompt: Union[str, List[Message]]) -> List[Message]:

        if isinstance(prompt, str):

            return [{"role": "user", "content": prompt}]

        if isinstance(prompt, list):

            out: List[Message] = []

            for m in prompt:

                if not isinstance(m, dict):

                    continue

                role = m.get("role", "user")

                content = m.get("content", "")

                out.append({**m, "role": role, "content": content})

            return out

        # Fallback: coerce

        return [{"role": "user", "content": str(prompt)}]



    def _hash_messages(self, messages: List[Message]) -> str:

        canonical = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()



    def _split_system_layers(self, messages: List[Message]) -> tuple[str, str]:

        """

        Split messages into:

        - stable_system_prompt: leading system messages (before first non-system)

        - ephemeral_overlay: any later system messages (rare; but used by session search injection etc.)

        """

        stable_parts: List[str] = []

        overlay_parts: List[str] = []

        saw_non_system = False

        for m in messages or []:

            if not isinstance(m, dict):

                continue

            if m.get("role") == "system":

                c = str(m.get("content") or "")

                layer = None

                try:

                    layer = (m.get("metadata") or {}).get("layer") if isinstance(m.get("metadata"), dict) else None

                except Exception:

                    layer = None

                if layer == "ephemeral":

                    overlay_parts.append(c)

                elif not saw_non_system:

                    stable_parts.append(c)

                else:

                    overlay_parts.append(c)

            else:

                saw_non_system = True

        return "\n\n".join([p for p in stable_parts if p]), "\n\n".join([p for p in overlay_parts if p])



    def _build_stable_cache_key(

        self, *, meta: Dict[str, Any], stable_prompt_version: str, workspace_context_hash: Any

    ) -> Optional[str]:

        try:

            target_type = str(meta.get("target_type") or meta.get("release_target_type") or "").strip() or "unknown"

            target_id = str(meta.get("target_id") or meta.get("release_target_id") or "").strip() or "unknown"

            w = str(workspace_context_hash or "")

            # Important: stable cache key must *not* depend on per-turn prompt_version,

            # otherwise it will miss whenever user/assistant messages change.

            raw = f"{target_type}:{target_id}:{stable_prompt_version}:{w}"

            return hashlib.sha256(raw.encode("utf-8")).hexdigest()

        except Exception:

            return None



    # Project context logic moved to ContextEngine (core.harness.context.engine)



    def _estimate_tokens(self, messages: List[Message]) -> int:

        """

        Best-effort token estimator.

        We intentionally avoid model-specific tokenizers at this phase.

        """

        total_chars = 0

        for m in messages or []:

            try:

                c = m.get("content", "")

                if c is None:

                    continue

                total_chars += len(str(c))

            except Exception:

                continue

        # heuristic: ~4 chars per token

        return int(total_chars / 4) + 1





# Small in-process cache for stable system prompts (Roadmap-1).

_STABLE_PROMPT_CACHE: Dict[str, str] = {}

