"""
Graph & memory context injection — extracted from loop.py.

Injects: code graph, wiki graph, skill deps, memory reminders into Agent context.
"""
from typing import Any, Dict, List, Optional
import os, re, logging

from ...interfaces.loop import LoopState
from ...kernel.runtime import get_kernel_runtime


async def inject_graph_context(state: LoopState) -> dict:
    """Original: _try_inject_graph_context (loop.py:1769)"""
    """Inject code graph + Wiki knowledge graph context into Agent decision loop.

    Code graph: sys_code_intel_context → related files + dependencies
    Knowledge graph: Wiki page availability → Agent can query sys_wiki_context
    Skill graph: available skill list → Agent planning reference
    """
    hints: Dict[str, Any] = {}
    task = state.context.get("task", "") or state.context.get("_original_query", "")
    skip = state.context.get("_graph_loaded")
    if skip:
        return hints

    # Code graph context
    try:
        from core.harness.syscalls.code_intel_syscall import sys_code_intel_context
        code_ctx = sys_code_intel_context(task)
        if code_ctx and code_ctx.get("related"):
            related_files = code_ctx["related"][:10]
            hints["code_graph"] = {
                "stats": code_ctx.get("stats", {}),
                "related": related_files,
            }
            # Inject into messages
            file_list = "\n".join(
                f"- {f['file']} (imports: {', '.join(f['imports'][:3])})"
                for f in related_files if f.get("file")
            )
            state.context.setdefault("messages", []).insert(0, {
                "role": "user",
                "content": (
                    "[system] Code knowledge graph pre-built. Files related to task:\n"
                    f"{file_list}\n\n"
                    "Use the code graph to locate code — avoid repeated grep/glob."
                ),
            })
    except Exception:
        try:
            from core.harness.syscalls.code_intel_syscall import sys_code_intel_context
            code_ctx = sys_code_intel_context(task)
            if code_ctx and code_ctx.get("related"):
                hints["code_graph"] = code_ctx
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    # Wiki availability
    try:
        from core.harness.knowledge.wiki_engine import search_pages, list_collections
        from core.harness.knowledge.knowledge_ontology import AI as __AI
        kbs = state.context.get("_knowledge_bases", []) or []
        first_cid = kbs[0] if kbs else "default"
        wiki_pages = search_pages(limit=1, collection_id=first_cid)
        if wiki_pages:
            total = 0
            for cid in (kbs or ["default"]):
                total += len(search_pages(limit=1000, collection_id=cid))
            kb_info = ""
            if kbs:
                kb_info = f" (collection: {', '.join(kbs)}, {total} pages)"
            else:
                kb_info = f" ({total} pages)"
            hints["wiki"] = {"pages": total, "collections": kbs}
            state.context.setdefault("messages", []).insert(1, {
                "role": "user",
                "content":                     (
                    f"[system] Wiki KB available{kb_info}.\n\n"
                    f"Search syntax:\n"
                    f"  sys_knowledge_retrieve('question', wiki_collection_ids=['{first_cid}'])\n"
                    f"  sys_wiki_context('question', collection_ids=['{first_cid}'])\n\n"
                    f"[Available ontology class filters - pass target_class param]\n"
                    f"  '{__AI}ConceptPage' → concept entity pages (entities)\n"
                    f"  '{__AI}TopicPage' → topic overview pages (topics)\n"
                    f"  expand_subclasses=True → also search subclass pages\n\n"
                    f"[Examples]\n"
                    f"  sys_knowledge_retrieve('what is memory system', wiki_collection_ids=['{first_cid}'], target_class='{__AI}ConceptPage', expand_subclasses=True)\n"
                    f"  sys_knowledge_retrieve('compare solutions', wiki_collection_ids=['{first_cid}'], target_class='{__AI}TopicPage')\n\n"
                    f"No need to re-reason or guess — just search directly."
                ),
            })
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # Skill graph availability
    try:
        from core.harness.knowledge.skill_deps import build_skill_deps
        deps = build_skill_deps()
        if deps.get("stats", {}).get("total_skills", 0) > 0:
            skills = list(deps["skills"].keys())
            hints["skills"] = {
                "total": deps["stats"]["total_skills"],
                "available": skills[:15],
            }
            state.context.setdefault("messages", []).insert(2, {
                "role": "user",
                "content": (
                    f"[system] {deps['stats']['total_skills']} skills registered."
                    f" Primary: {', '.join(skills[:10])}."
                ),
            })
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # File operations: make agents aware of available file syscalls
    state.context.setdefault("messages", []).insert(3, {
        "role": "user",
        "content": (
            "[system] File syscalls available: sys_file_read, sys_file_write, "
            "sys_file_edit, sys_glob, sys_code_search."
            "Use these instead of bypassing the syscall channel."
        ),
    })

    state.context["_graph_loaded"] = True
    return hints


async def inject_ontology_context(state: LoopState) -> dict:
    """Inject domain ontology context into Agent decision loop (v2.6).

    DomainRouter auto-classify → domain_id + key class list + search hints.
    """
    hints: Dict[str, Any] = {}
    task = state.context.get("task", "") or state.context.get("_original_query", "")
    if not task or state.context.get("_ontology_injected"):
        return hints

    try:
        from core.harness.knowledge.domain_router import DomainRouter
        router = DomainRouter()
        classified = router.classify(task)
        if not classified:
            return hints
        
        # classify can return a str (domain_id) or a dict {domain_id, config, ...}
        if isinstance(classified, str):
            domain_id = classified
            config = {}
        else:
            domain_id = classified.get("domain_id")
            config = classified.get("config", {})
        if not domain_id:
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

        state.context.setdefault("messages", []).insert(3, {
            "role": "user",
            "content": hint_msg,
        })
        state.context["_ontology_injected"] = True
    except Exception as e:
        logging.warning("Ontology context injection failed: %s", e)

    return hints


async def inject_memory_reminders(state: LoopState) -> None:
    """Original: _try_inject_memory_reminders (loop.py:1884)"""
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
            state.context.setdefault("messages", []).insert(0, {
                "role": "user",
                "content": str(reminder_text),
            })
    except Exception as e:
        logging.warning(str(e), exc_info=True)
