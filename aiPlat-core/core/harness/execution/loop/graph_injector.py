"""
Graph & memory context injection — extracted from loop.py.

Injects: code graph, wiki graph, skill deps, memory reminders into Agent context.

IMPORTANT (hang fix): code-graph / wiki full-scan / skill-deps / ontology classify
are sync-heavy (monorepo walk, SentenceTransformer load, ModelManager Ollama scan).
Workspace agents set ``_coding_policy_profile=off`` — skip both code-graph AND
ontology inject there. When coding is on, offload to ``asyncio.to_thread`` with a
hard timeout so ReAct can still reach ``sys_llm_generate`` (otherwise Ollama stays
idle with only step_1/context_snapshot).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict, Optional

from ...interfaces.loop import LoopState


def _env_flag(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name) or default)
    except Exception:
        return default


def wants_code_graph(state: LoopState) -> bool:
    """Whether this ReAct run should pay for monorepo code-graph inject."""
    if _env_flag("AIPLAT_SKIP_CODE_GRAPH_INJECT"):
        return False
    if _env_flag("AIPLAT_FORCE_CODE_GRAPH_INJECT"):
        return True
    prof = str(state.context.get("_coding_policy_profile") or "").strip().lower()
    if prof in ("off", "none", "0", "false"):
        return False
    if prof and prof not in ("", "auto"):
        # karpathy_v1 / custom coding profiles → enable
        return True
    # Profile unset: only enable for explicit code-ish tasks (avoid architect oral hangs)
    task = str(
        state.context.get("task")
        or state.context.get("_original_query")
        or state.context.get("_user_task")
        or ""
    )
    return bool(
        re.search(
            r"(refactor|implement|bugfix|pull request|\bPR\b|codebase"
            r"|\u6e90\u7801|\u91cd\u6784|\u51fd\u6570|\u6a21\u5757|\u4ed3\u5e93)",
            task,
            re.I,
        )
    )


def _safe_code_intel(task: str) -> Optional[Dict[str, Any]]:
    try:
        from core.harness.syscalls.code_intel_syscall import sys_code_intel_context

        return sys_code_intel_context(task)
    except Exception:
        logging.getLogger(__name__).debug("sys_code_intel_context failed", exc_info=True)
        return None


def _light_wiki_hint(kbs: list) -> Dict[str, Any]:
    """Cheap wiki availability probe — never scan limit=1000 on the hot path."""
    from core.harness.knowledge.wiki_engine import search_pages

    first_cid = kbs[0] if kbs else "default"
    sample = search_pages(limit=1, collection_id=first_cid) or []
    if not sample:
        return {}
    return {"pages_sample": 1, "collections": list(kbs or ["default"]), "first_cid": first_cid}


def _skill_deps_hint() -> Dict[str, Any]:
    from core.harness.knowledge.skill_deps import build_skill_deps

    deps = build_skill_deps()
    total = int((deps.get("stats") or {}).get("total_skills", 0) or 0)
    if total <= 0:
        return {}
    skills = list((deps.get("skills") or {}).keys())
    return {"total": total, "available": skills[:15]}


async def inject_graph_context(state: LoopState) -> dict:
    """Inject code graph + Wiki + skill deps into Agent decision loop.

    Heavy work is skipped for non-coding agents and otherwise run in a worker
    thread with timeouts so the first LLM syscall is never starved.
    """
    hints: Dict[str, Any] = {}
    task = state.context.get("task", "") or state.context.get("_original_query", "")
    if state.context.get("_graph_loaded"):
        return hints

    coding_on = wants_code_graph(state)
    # Allow sub-second timeouts in tests; production default remains 8s / 3s.
    graph_timeout = max(0.05, _float_env("AIPLAT_CODE_GRAPH_INJECT_TIMEOUT", 8.0))
    light_timeout = max(0.05, _float_env("AIPLAT_GRAPH_LIGHT_INJECT_TIMEOUT", 3.0))

    # Code graph (monorepo walk) — only when coding
    if coding_on:
        try:
            code_ctx = await asyncio.wait_for(
                asyncio.to_thread(_safe_code_intel, str(task or "")),
                timeout=graph_timeout,
            )
            if code_ctx and code_ctx.get("related"):
                related_files = code_ctx["related"][:10]
                hints["code_graph"] = {
                    "stats": code_ctx.get("stats", {}),
                    "related": related_files,
                }
                file_list = "\n".join(
                    f"- {f['file']} (imports: {', '.join(f['imports'][:3])})"
                    for f in related_files
                    if f.get("file")
                )
                state.context.setdefault("messages", []).insert(
                    0,
                    {
                        "role": "user",
                        "content": (
                            "[system] Code knowledge graph pre-built. Files related to task:\n"
                            f"{file_list}\n\n"
                            "Use the code graph to locate code — avoid repeated grep/glob."
                        ),
                    },
                )
        except asyncio.TimeoutError:
            logging.warning(
                "code_graph inject timed out after %.1fs — continuing to LLM",
                graph_timeout,
            )
            hints["code_graph_timeout"] = True
        except Exception:
            logging.warning("code_graph inject failed", exc_info=True)
    else:
        hints["code_graph_skipped"] = True

    # Wiki availability (light probe only)
    kbs = state.context.get("_knowledge_bases", []) or []
    if coding_on or kbs:
        try:
            wiki = await asyncio.wait_for(
                asyncio.to_thread(_light_wiki_hint, list(kbs)),
                timeout=light_timeout,
            )
            if wiki:
                from core.harness.knowledge.knowledge_ontology import AI as __AI

                first_cid = wiki.get("first_cid") or "default"
                hints["wiki"] = {
                    "pages": wiki.get("pages_sample", 1),
                    "collections": wiki.get("collections") or [],
                }
                state.context.setdefault("messages", []).insert(
                    1,
                    {
                        "role": "user",
                        "content": (
                            f"[system] Wiki KB available (collection: {first_cid}).\n\n"
                            f"Search syntax:\n"
                            f"  sys_knowledge_retrieve('question', wiki_collection_ids=['{first_cid}'])\n"
                            f"  sys_wiki_context('question', collection_ids=['{first_cid}'])\n\n"
                            f"[Available ontology class filters - pass target_class param]\n"
                            f"  '{__AI}ConceptPage' → concept entity pages (entities)\n"
                            f"  '{__AI}TopicPage' → topic overview pages (topics)\n"
                            f"  expand_subclasses=True → also search subclass pages\n\n"
                            f"No need to re-reason or guess — just search directly."
                        ),
                    },
                )
        except asyncio.TimeoutError:
            logging.warning("wiki light inject timed out after %.1fs", light_timeout)
        except Exception:
            logging.warning("wiki inject failed", exc_info=True)

    # Skill graph — off-thread; skip when non-coding to keep step_1 → LLM fast
    if coding_on:
        try:
            sk = await asyncio.wait_for(
                asyncio.to_thread(_skill_deps_hint),
                timeout=light_timeout,
            )
            if sk:
                hints["skills"] = sk
                state.context.setdefault("messages", []).insert(
                    2,
                    {
                        "role": "user",
                        "content": (
                            f"[system] {sk['total']} skills registered."
                            f" Primary: {', '.join(sk.get('available') or [])}."
                        ),
                    },
                )
        except asyncio.TimeoutError:
            logging.warning("skill_deps inject timed out after %.1fs", light_timeout)
        except Exception:
            logging.warning("skill_deps inject failed", exc_info=True)

    if coding_on:
        state.context.setdefault("messages", []).insert(
            3,
            {
                "role": "user",
                "content": (
                    "[system] File syscalls available: sys_file_read, sys_file_write, "
                    "sys_file_edit, sys_glob, sys_code_search."
                    "Use these instead of bypassing the syscall channel."
                ),
            },
        )

    state.context["_graph_loaded"] = True
    return hints


def wants_ontology_inject(state: LoopState) -> bool:
    """Whether this ReAct run should pay for DomainRouter classify + embed build.

    Same policy as code-graph: workspace/oral agents set coding_policy=off and
    must not stall step_1 on SentenceTransformer / ModelManager cold start.
    """
    if _env_flag("AIPLAT_SKIP_ONTOLOGY_INJECT"):
        return False
    if _env_flag("AIPLAT_FORCE_ONTOLOGY_INJECT"):
        return True
    prof = str(state.context.get("_coding_policy_profile") or "").strip().lower()
    if prof in ("off", "none", "0", "false"):
        return False
    return True


async def inject_ontology_context(state: LoopState) -> dict:
    """Inject domain ontology context into Agent decision loop (v2.6).

    DomainRouter.classify is sync (embed all domains + possible T3 LLM). Skip for
    coding_policy=off (workspace agents). Otherwise run in a worker thread with
    timeout. Abandoned threads can still burn GIL — prefer skip over long waits.
    """
    hints: Dict[str, Any] = {}
    task = state.context.get("task", "") or state.context.get("_original_query", "")
    if not task or state.context.get("_ontology_injected"):
        return hints

    if not wants_ontology_inject(state):
        state.context["_ontology_injected"] = True
        hints["ontology_skipped"] = True
        return hints

    # Keep short: wait_for abandons the await but the worker may keep loading ST.
    classify_timeout = max(0.05, _float_env("AIPLAT_ONTOLOGY_CLASSIFY_TIMEOUT", 3.0))

    try:
        from core.harness.knowledge.domain_router import DomainRouter

        router = DomainRouter()

        def _classify() -> Any:
            return router.classify(str(task))

        try:
            classified = await asyncio.wait_for(
                asyncio.to_thread(_classify),
                timeout=classify_timeout,
            )
        except asyncio.TimeoutError:
            logging.warning(
                "ontology classify timed out after %.1fs — continuing without domain hint",
                classify_timeout,
            )
            state.context["_ontology_injected"] = True
            hints["ontology_timeout"] = True
            return hints

        if not classified:
            state.context["_ontology_injected"] = True
            return hints

        # classify can return a str (domain_id) or a dict {domain_id, config, ...}
        if isinstance(classified, str):
            domain_id = classified
            config = {}
        else:
            domain_id = classified.get("domain_id")
            config = classified.get("config", {})
        if not domain_id:
            state.context["_ontology_injected"] = True
            return hints
        domain_name = config.get("name", domain_id)
        domain_desc = config.get("description", "")

        onto_dir = os.path.expanduser(
            os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies")
        )
        yaml_path = os.path.join(onto_dir, f"{domain_id}.yaml")
        class_list = ""
        if os.path.exists(yaml_path):
            import yaml

            with open(yaml_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            classes = raw.get("classes", {})
            if classes:
                top = list(classes.items())[:8]
                class_list = "\n".join(
                    f"    - {name}: {cls.get('label', name)}"
                    for name, cls in top
                )

        hint_msg = (
            f"[system] Domain ontology context injected:\n"
            f"  domain: {domain_name} ({domain_id})"
        )
        if domain_desc:
            hint_msg += f" — {domain_desc[:120]}"
        if class_list:
            hint_msg += f"\n  key ontology classes:\n{class_list}"
        hint_msg += f"\n  use domain_id='{domain_id}' to narrow search scope."

        hints["ontology"] = {
            "domain_id": domain_id,
            "domain_name": domain_name,
            "class_count": len(class_list.split("\n")) if class_list else 0,
        }

        state.context.setdefault("messages", []).insert(
            3,
            {
                "role": "user",
                "content": hint_msg,
            },
        )
        state.context["_ontology_injected"] = True
    except Exception as e:
        logging.warning("Ontology context injection failed: %s", e)
        state.context["_ontology_injected"] = True

    return hints


async def inject_memory_reminders(state: LoopState) -> None:
    """Bridge: inject MemoryManager reminders into the message loop.

    When MemoryManager is available (wired at server startup), its
    SystemReminders are injected as user-role messages for the agent.
    """
    try:
        from core.harness.memory.manager import get_memory_manager

        ns = state.context.get("_agent_namespace", "default")
        mgr = get_memory_manager(namespace=ns)
        if mgr is None:
            return
        reminders = await mgr.get_reminders(
            token_usage_ratio=float(state.context.get("_token_usage_ratio", 0) or 0),
            consecutive_reads=int(state.context.get("_consecutive_reads", 0) or 0),
            tool_failed=bool(state.context.get("_tool_failed", False)),
            calling_tool=str(state.context.get("_last_tool_called", "") or ""),
            pending_todos=int(state.context.get("_pending_todos", 0) or 0),
        )
        if not reminders:
            return
        for reminder_text in reminders:
            state.context.setdefault("messages", []).insert(
                0,
                {
                    "role": "user",
                    "content": str(reminder_text),
                },
            )
    except Exception as e:
        logging.warning(str(e), exc_info=True)
