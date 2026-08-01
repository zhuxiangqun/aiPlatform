"""

Memory Manager — Four-Layer Memory System



Layer 1: Working  Memory (Hot)   — 当前对话上下文 (deque, 30K tokens)

Layer 2: Episodic Memory (Warm)  — 会话摘要与关键决策

Layer 3: Semantic Memory (Cold)  — 长期知识 / 用户偏好 (vector + FTS5)

Layer 4: Task Skills   (External)— 可复用执行模式 (流水线晶体化, pass_rate ≥85% 自动注册)



Design reference: Hermes Agent 四层记忆诊断框架.

"""

# === capability_dependencies (Phase 43: auto-verified) ===

# depends_on:

#   - memory-subsystem:

#       symbols: [WorkingMemory, EpisodicMemory, SemanticMemory, MemoryEntry]

#   - memory-white-boxing:

#       symbols: [LongTermMemoryMixin, memory rules JSON]

#   - memory-runtime-filtering:

#       symbols: [load_memory_rules, save_memory_rules]

#   - context-compression:

#       symbols: [normalize_roles]

#   - ai-knowledge-layer:

#       symbols: [brand_rules.yaml]

#   - extension-and-learning:

#       symbols: [SharedKnowledgePool]

#   - knowledge-infrastructure:

#       symbols: [ContextBus, RunContext]

# === end ===



import asyncio

import logging

import os

from typing import List, Optional, Dict, Any

from dataclasses import dataclass, field



from .working import WorkingMemory

from .episodic import EpisodicMemory

from .semantic import SemanticMemory

from .compression import ContextCompression, ContextState

from .reminders import SystemReminders, get_system_reminders



logger = logging.getLogger(__name__)





@dataclass

class TaskSkill:

    """Layer 4: External Memory — reusable execution patterns (procedural memory).



    Completed pipeline executions crystallize into TaskSkills stored at

    ~/.aiplat/task_skills/. Hot skills (pass_rate >= 85%) auto-register

    in SkillRegistry for agent discovery.



    Corresponds to Hermes "External Memory" — the skill-layer that answers

    "how to execute" rather than "what to know."

    """

    skill_id: str

    name: str

    pipeline_id: str

    agent_sequence: List[str]

    artifacts: List[str]

    pass_rate: float

    keywords: List[str]

    artifacts_keys: Dict[str, Any] = field(default_factory=dict)

    rollback_count: int = 0

    plan_id: str = ""

    created_at: str = ""

    last_used_at: str = ""



    @property

    def is_hot(self) -> bool:

        return self.pass_rate >= 0.85





@dataclass

class MemoryConfig:

    """Memory system configuration"""

    working_tokens: int = 30000

    episodic_update_interval: int = 5

    max_messages: int = 20

    vector_store_type: str = "sqlite"

    enable_compression: bool = True

    enable_reminders: bool = True

    use_llm_summary: bool = True

    model: Any = None  # injected by caller for episodic LLM summarization





@dataclass

class BuildContextResult:

    """Result of building context"""

    messages: List[Dict]

    token_count: int

    reminder: Optional[str] = None

    working_context: str = ""

    episodic_summary: str = ""

    relevant_memories: str = ""
    version_context: Dict[str, str] = field(default_factory=dict)





# ── P0-4: Cross-layer re-rank helper ──



def _re_rank_messages(messages: list, query: str) -> list:

    """跨层重排：系统消息固定顺序，非系统消息按语义相关度排序。

    

    最近 3 条非系统消息保持原位（时效性保护），

    其余按与当前 query 的语义相关度降序排列。

    """

    from core.harness.memory.compression import get_cached_embedding, score_semantic_relevance



    system_msgs = [m for m in messages if m.get("role") == "system"]

    non_system = [m for m in messages if m.get("role") != "system"]



    if len(non_system) <= 3:

        return messages  # 太少，不重排



    # 时效性保护：最近 3 条保持原位

    recent = non_system[-3:]

    older = non_system[:-3]



    relevance = score_semantic_relevance(older, query)

    sorted_older = [m for _, m in sorted(zip(relevance, older), key=lambda x: -x[0])]



    return system_msgs + sorted_older + recent





class MemoryManager:

    """Unified memory manager with three-layer architecture.



    Supports namespace-based isolation: each agent can use its own namespace

    to keep memories separate (e.g., 'agent_a', 'agent_b', 'agent_c').

    """



    def __init__(self, config: Optional[MemoryConfig] = None, namespace: str = "default",

                 *, tenant_id: Optional[str] = None, session_id: Optional[str] = None):

        self._config = config or MemoryConfig()

        self._current_ontology_version: str = ""
        self._current_collection_version: str = ""

        # Auto-inject model for episodic LLM summarization if not provided by caller

        if self._config.use_llm_summary and self._config.model is None:

            try:

                from core.harness.utils.model_injection import best_model_for_purpose

                purpose = "doc_llm"

                model_name = best_model_for_purpose(purpose)

                if model_name:

                    from core.harness.utils.model_injection import create_selected_adapter

                    self._config.model = create_selected_adapter(model_name=model_name)

                    logger.info("Episodic LLM summarization: auto-injected model '%s'", model_name)

                else:

                    logger.warning("Episodic LLM summarization: no model available, using rule-based fallback")

            except Exception as e:

                logger.warning("Episodic LLM summarization: auto-injection failed: %s", e)

        self.namespace = namespace

        # §5.12 isolation scope: when set, semantic retrieve/capture are tenant+session

        # scoped (build_context auto-applies the S1 filter; capture stamps metadata).

        self._tenant_id = tenant_id

        self._session_id = session_id

        self._persist_callback = None  # wiring: active — wired by get_memory_manager() → _wire_persist_callback()



        # Initialize layers

        self._working = WorkingMemory(

            max_tokens=self._config.working_tokens,

            max_messages=self._config.max_messages

        )

        self._episodic = EpisodicMemory(

            update_interval=self._config.episodic_update_interval

        )

        self._semantic = SemanticMemory(

            store_type=self._config.vector_store_type,

            tenant_id=self._tenant_id or "default",

        )

        self._compression = ContextCompression()

        self._reminders = get_system_reminders() if self._config.enable_reminders else None

        self._episodic_cleanup_counter = 0  # Phase 23.2 G1

        self._cleanup_task: Optional[asyncio.Task] = None

        self._cleanup_interval = int(os.getenv("AIPLAT_MEMORY_CLEANUP_INTERVAL", str(86400)))



        # P2-25: Pluggable memory provider backend

        try:

            from core.harness.memory.providers import get_memory_provider

            self._memory_provider = get_memory_provider()

        except Exception:

            self._memory_provider = None



    async def start_background_tasks(self) -> None:

        """Start periodic background maintenance tasks."""

        if self._cleanup_task is None:

            self._cleanup_task = asyncio.create_task(self._cleanup_loop())



    async def _cleanup_loop(self) -> None:

        """Periodically soft-delete expired low-access semantic memories."""

        while True:

            try:

                await asyncio.sleep(self._cleanup_interval)

                count = await self.cleanup_semantic_expired()

                if count:

                    logger.debug(f"Semantic cleanup: soft-deleted {count} expired items")

            except asyncio.CancelledError:

                break

            except Exception as e:

                logging.warning(str(e), exc_info=True)



    async def shutdown(self) -> None:

        """Gracefully stop background tasks."""

        if self._cleanup_task:

            self._cleanup_task.cancel()

            try:

                await self._cleanup_task

            except asyncio.CancelledError:

                pass  # noqa: normal-cancellation

            self._cleanup_task = None

    

    async def build_context(

        self,

        current_query: str,

        system_prompt: str,

        *,

        session_id: Optional[str] = None,

        skip_system_messages: bool = False,

        retrieval_budget: str = "full",

    ) -> BuildContextResult:

        """Build complete context from all memory layers.

        When session_id is provided, scopes Working memory and semantic retrieval
        to that session (prevents cross-project contamination in Builder PM chats).

        When skip_system_messages=True, the caller handles system-level injection
        (CLAUDE.md, project context) separately — only memory-layer context
        (working/episodic/semantic) is assembled here.

        retrieval_budget: "full" | "minimal" | "working_only"

          - full:       full semantic + episodic + working

          - minimal:    semantic top_k=1 + working (skip episodic)

          - working_only: working memory only (skip all retrieval)

        """

        # Scope to caller's session if provided
        if session_id:
            self._session_id = session_id
        import logging as _bcl; _bcl.getLogger('MEMORY_DEBUG').warning('build_context: session=%s working_msgs=%d', session_id, self._working.message_count)

        # P0-1: 检测审计模式——autoreview 审查时只保留 Working Memory

        audit_mode = False

        try:

            from core.harness.kernel.execution_context import get_active_workspace_context

            exec_ctx = get_active_workspace_context()

            if exec_ctx:

                audit_mode = exec_ctx.variables.get("_active_skill", "") == "autoreview"

        except Exception:

            logging.getLogger(__name__).debug('build_context failed', exc_info=True)


        # Phase 38: AdaptiveContextRouter — self-learning source selection (B-axis L5)

        adaptive_sources = None

        if not audit_mode:

            try:

                from core.harness.knowledge.adaptive_context import AdaptiveContextRouter

                _router = AdaptiveContextRouter()

                task_type = self._session_id or "general"

                _source_cfg = await _router.select_sources(task_type, "memory_build")

                adaptive_sources = _source_cfg.get("sources", [])

                # Adaptive compression based on token pressure

                _compression = _source_cfg.get("compression", "balanced")

                if _compression == "aggressive":

                    retrieval_budget = "minimal"

                logger.debug("AdaptiveContext: sources=%s compression=%s", adaptive_sources, _compression)

            except Exception:

                logging.getLogger(__name__).debug('build_context failed', exc_info=True)


        # PR #2: 从 ControlProfile 读取记忆注入策略

        skip_episodic = audit_mode

        skip_semantic = audit_mode

        if not audit_mode:

            try:

                from core.harness.meta.profile_registry import get_active_profile

                profile = get_active_profile()

                if not profile.episodic_injection:

                    skip_episodic = True

                if not profile.semantic_injection:

                    skip_semantic = True

            except Exception:

                logging.getLogger(__name__).debug('build_context failed', exc_info=True)


        # 1. Retrieve relevant semantic memories (Phase 18.1: budget-gated)

        relevant_memories = []

        if not skip_semantic and retrieval_budget != "working_only":

            if retrieval_budget == "minimal":

                relevant_memories = await self._semantic.retrieve(

                    current_query, tenant_id=self._tenant_id, session_id=self._session_id, top_k=1)

            else:

                relevant_memories = await self._semantic.retrieve(

                    current_query, tenant_id=self._tenant_id, session_id=self._session_id)

        
        # Phase 52: Inject ConversationIngestor wiki pages (best-effort)
        if retrieval_budget != "working_only":
            try:
                import os as _parseos, time as _parsetime
                wiki_root = _parseos.path.expanduser(_parseos.getenv("AIPLAT_HOME", "~/.aiplat")) + "/wiki/collections"
                if _parseos.path.isdir(wiki_root):
                    cutoff = _parsetime.time() - 7 * 86400
                    for col in _parseos.listdir(wiki_root)[:3]:
                        col_dir = _parseos.path.join(wiki_root, col)
                        if _parseos.path.isdir(col_dir):
                            for f in sorted(_parseos.listdir(col_dir), key=lambda x: _parseos.path.getmtime(_parseos.path.join(col_dir, x)), reverse=True)[:3]:
                                fpath = _parseos.path.join(col_dir, f)
                                if _parseos.path.isfile(fpath) and _parseos.path.getmtime(fpath) > cutoff:
                                    with open(fpath, encoding="utf-8", errors="ignore") as fh:
                                        body = fh.read()[:500]
                                    relevant_memories.append(type("_IngestorMem", (), {"content": body, "metadata": {"source": "ingestor", "title": f.replace(".md","")}, "importance": 0.7})())
            except Exception:
                pass
        

        # 2. Get episodic summary (Phase 18.1: budget-gated)

        episodic_summary = ""

        if not skip_episodic and retrieval_budget == "full":

            episodic_summary = self._episodic.get_summary()



        # Phase 18.1: Budget log — track token savings

        if retrieval_budget != "full":

            try:

                saved_episodic = self._estimate_tokens(episodic_summary) if episodic_summary else 0

                logging.getLogger("aiplat.memory").info(

                    "[BUDGET] %s bypass, saved ~%d tokens, query=%s",

                    retrieval_budget, saved_episodic, current_query[:80]

                )

            except Exception:

                logging.getLogger(__name__).debug('code failed', exc_info=True)
        

        # 3. Get working memory context

        working_context = (

            self._working.get_audit_context() if audit_mode 

            else self._working.get_context(session_id=self._session_id)

        )

        

        # 4. Build messages list

        messages: list = []

        if not skip_system_messages:

            messages.append({"role": "system", "content": system_prompt})

        

        # Add semantic memories as context

        if relevant_memories:

            memory_context = "## Relevant Past Context\n"

            for mem in relevant_memories[:3]:

                memory_context += f"- {mem.content[:200]}...\n"

            messages.append({"role": "system", "content": memory_context})

        

        # Add episodic summary

        if episodic_summary:

            messages.append({

                "role": "system",

                "content": f"## Session Summary\n{episodic_summary}"

            })



        # Add critical episodes (importance_score > 0.8) — never compressed

        if not audit_mode:

            critical = self._episodic.get_critical_episodes(limit=5)

            if critical:

                lines = []

                for ep in critical:

                    ts = ep.get("timestamp", "")[:19]

                    u = str(ep.get("user", ""))[:120]

                    a = str(ep.get("assistant", ""))[:120]

                    lines.append(f"[{ts}] User: {u}\n[{ts}] Assistant: {a}")

                messages.append({

                    "role": "system",

                    "content": "## Critical Decisions (Preserved)\n" + "\n---\n".join(lines),

                    "meta": {"role": "system_arch"},

                })



        # Inject user profile from semantic memory (auto-extracted via ProfileBuilder)

        if not audit_mode:

            try:

                profiles = await self._semantic.retrieve("user_profile preferences constraints", top_k=1)

                for p in profiles:

                    if hasattr(p, 'metadata') and isinstance(p.metadata, dict):

                        if p.metadata.get("tag") == "user_profile":

                            import json as _json

                            data = _json.loads(p.content) if isinstance(p.content, str) else p.content

                            prefs = data.get("preferences", []) if isinstance(data, dict) else []

                            constraints = data.get("constraints", []) if isinstance(data, dict) else []

                            if prefs or constraints:

                                from core.harness.memory.profile_builder import UserProfile

                                profile = UserProfile.from_dict(data)

                                msg = profile.to_system_message()

                                if msg:

                                    messages.append({"role": "system", "content": msg})

                            break

            except Exception as e:

                logging.warning(str(e), exc_info=True)



        # Phase 42: Inject brand foundation rules (voice/tone/forbidden words)

        if retrieval_budget in ("full", "minimal") and not audit_mode:

            try:

                import os as _os_br, yaml as _yaml_br

                rules_path = _os_br.path.expanduser("~/.aiplat/brand_rules.yaml")

                # Also check the module-local fallback

                if not _os_br.path.exists(rules_path):

                    rules_path = _os_br.path.join(_os_br.path.dirname(__file__), "brand_rules.yaml")

                if _os_br.path.exists(rules_path) and _os_br.getenv("AIPLAT_BRAND_RULES_ENABLED", "false").lower() in ("1", "true", "yes"):

                    with open(rules_path, "r") as f:

                        rules = _yaml_br.safe_load(f) or {}

                    voice = rules.get("voice", {})

                    forbidden = rules.get("forbidden_words", [])

                    fmt = rules.get("format_rules", {})

                    if voice or forbidden or fmt:

                        lines = ["\n[Brand Foundation] Style & voice rules:"]

                        if voice:

                            lines.append(f"- Voice: {voice.get('style','professional')}, "

                                         f"tone: {voice.get('tone','confident')}")

                        if forbidden:

                            lines.append(f"- Forbidden words: {', '.join(forbidden[:10])}")

                        if fmt:

                            lang = fmt.get("response_language", "")

                            if lang:

                                lines.append(f"- Language: {lang}")

                        messages.append({

                            "role": "system",

                            "content": "\n".join(lines),

                            "meta": {"role": "brand_rules"},

                        })

            except Exception:

                logging.getLogger(__name__).debug('code failed', exc_info=True)


        # Phase 40: Inject crystallized Task Skills (Procedural Memory)

        if retrieval_budget in ("full", "minimal") and not audit_mode:

            try:

                from core.apps.skills.registry import get_skill_registry

                reg = get_skill_registry()

                names = reg.list_skills(enabled_only=True)

                hot = []

                for name in names[:30]:

                    stub = reg.get_stub(name)

                    stats = reg._binding_stats.get(name) if hasattr(reg, '_binding_stats') else None

                    pr = stats.pass_rate if stats and hasattr(stats, 'pass_rate') and stats.total_executions > 0 else 1.0

                    tc = stats.total_executions if stats and hasattr(stats, 'total_executions') else 0

                    if pr >= 0.85:

                        hot.append((name, stub or name, pr, tc))

                if hot:

                    hot.sort(key=lambda x: (x[2], x[3]), reverse=True)

                    lines = ["\n[Procedural Memory] High-confidence reuse patterns:"]

                    for name, stub, pr, _tc in hot[:5]:

                        lines.append(f"- {name} (pass_rate={pr:.0%}): {stub[:120]}")

                    lines.append("→ Use sys_skill_call to load full SOP when needed.")

                    messages.append({

                        "role": "system",

                        "content": "\n".join(lines),

                        "meta": {"role": "procedural_memory"},

                    })

            except Exception:

                logging.getLogger(__name__).debug('code failed', exc_info=True)
        

        # Add working memory

        messages.extend(working_context)



        # P0-4: 跨层统一重排——非系统消息按语义相关度排序（审计模式跳过）

        if not audit_mode and current_query and len(messages) > 3:

            try:

                messages = _re_rank_messages(messages, current_query)

            except Exception:

                logging.getLogger(__name__).debug('code failed', exc_info=True)
        

        # Add current query

        messages.append({"role": "user", "content": current_query})

        

        # Phase 23.2 G1: Episodic TTL cleanup (every 10 calls)

        self._episodic_cleanup_counter += 1

        if self._episodic_cleanup_counter % 10 == 0:

            removed = self._episodic.cleanup_expired()

            if removed:

                logging.debug("[TTL] Cleaned %d expired episodic entries", removed)



        # 5. Check compression

        total_tokens = sum(self._estimate_tokens(str(m.get("content", ""))) for m in messages)

        state = ContextState(

            token_usage=int(total_tokens),

            token_limit=self._config.working_tokens,

            message_count=len(messages)

        )

        

        # 6. Check for system reminders

        reminder = None

        if self._reminders:

            exec_state = {

                "token_usage_ratio": total_tokens / self._config.working_tokens,

                "consecutive_reads": self._count_consecutive_reads(working_context),

                "tool_failed": self._check_last_tool_failed(working_context)

            }

            reminder = await self._reminders.check_and_inject(exec_state)

            if reminder and isinstance(reminder, dict):

                # Phase 42: Inject reminder as message object with role support

                messages.append(reminder)

                reminder = str(reminder.get("content", ""))



        # 7. Apply compression if needed

        if self._config.enable_compression and self._compression.should_trigger_compression(state):

            messages = await self._compression.compress(messages, state)

        

        # 8. Phase 27: Inject cross-instance shared knowledge

        if not audit_mode and current_query:

            try:

                from core.harness.memory.shared_pool import get_shared_knowledge_pool

                pool = get_shared_knowledge_pool()

                shared = pool.query(current_query, limit=3, min_confidence=0.6)

                if shared:

                    facts_text = "\n".join(

                        f"- [{f.topic}] {f.content[:200]} (confidence={f.confidence:.2f})"

                        for f in shared

                    )

                    messages.append({

                        "role": "system",

                        "content": (

                            "## Shared Knowledge (Cross-Session)\n"

                            "The following facts were learned from other sessions. "

                            "Treat them as medium-confidence collaborative knowledge:\n"

                            f"{facts_text}"

                        ),

                        "meta": {"role": "shared_knowledge"},

                    })

                    total_tokens += len(facts_text.split()) * 1.3

            except Exception:

                logging.getLogger(__name__).debug('code failed', exc_info=True)


        # Phase 42: Normalize message roles before sending to LLM

        try:

            from core.harness.memory.transcript_guard import normalize_roles

            messages = normalize_roles(messages)

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)


        return BuildContextResult(

            messages=messages,

            token_count=int(total_tokens),

            reminder=reminder,

            working_context=(

                working_context[-3]

                if isinstance(working_context, list) and len(working_context) >= 3

                else working_context[-1] if isinstance(working_context, list) and working_context

                else ""

            ),

            episodic_summary=episodic_summary,

            relevant_memories="\n".join([m.content[:200] for m in relevant_memories[:3]]) if relevant_memories else "",
            version_context={
                "ontology_version": self._current_ontology_version or self._resolve_ontology_version() or "",
                "kb_collection_version": self._current_collection_version or "",
            },
        )

    def set_domain_context(self, domain_id: str, collection_id: str = "") -> None:
        """设置当前域上下文，使 build_context 返回的 version_context 携带正确的版本信息."""
        if domain_id:
            self._current_ontology_version = self._resolve_ontology_version_for(domain_id)
        if collection_id:
            self._current_collection_version = collection_id

    def _resolve_ontology_version(self) -> str:
        """Best-effort: resolve current ontology version (deprecated: use set_domain_context)."""
        try:
            from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore
            # Try default domain — caller should use set_domain_context for accuracy
            store = VersionedOntologyStore(domain_id="ai-knowledge")
            ver = store.get_current_version()
            return str(ver) if ver else ""
        except Exception:
            return ""

    def _resolve_ontology_version_for(self, domain_id: str) -> str:
        """Resolve ontology version for a specific domain."""
        try:
            from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore
            store = VersionedOntologyStore(domain_id=domain_id)
            ver = store.get_current_version()
            return str(ver) if ver else ""
        except Exception:
            return ""



    async def get_reminders(self, token_usage_ratio: float = 0.0, consecutive_reads: int = 0,

                             tool_failed: bool = False, calling_tool: str = "",

                             pending_todos: int = 0) -> List[str]:

        """Lightweight reminder check without full context assembly.



        Used by the agent execution loop as a bridge hook.

        Returns a list of reminder strings (empty if no reminders triggered).

        """

        if not self._reminders:

            return []

        exec_state = {

            "token_usage_ratio": token_usage_ratio,

            "consecutive_reads": consecutive_reads,

            "tool_failed": tool_failed,

            "calling_tool": calling_tool,

            "pending_todos": pending_todos,

        }

        reminder = await self._reminders.check_and_inject(exec_state)

        return [reminder] if reminder else []



    async def get_nudge(self, turn_number: int = 0) -> str:

        """Periodic memory nudge — returns a summary every ~10 turns.



        Hermes-aligned: memory_manager.py provides periodic reminders to

        the agent so it doesn't forget long-term context.  Returns empty

        string when not due.

        """

        if turn_number > 0 and turn_number % 10 == 0:

            try:

                recent = self._semantic.recent_entries(limit=3)

                if recent:

                    items = [f"- {e.content[:120]}" for e in recent if e.content]

                    return (

                        f"[Memory Nudge — turn #{turn_number}] "

                        f"Key memories from your past sessions:\n"

                        + "\n".join(items) + "\n"

                        f"(Use memory:search to recall more if needed.)"

                    )

            except Exception:

                logging.getLogger(__name__).debug('get_nudge failed', exc_info=True)
        return ""

    

    async def save_interaction(

        self,

        user_message: str,

        assistant_message: str,

        tool_calls: Optional[List[Dict]] = None,

        stability: str = "medium",

        is_critical: bool = False,

        session_id: Optional[str] = None,

        metadata: Optional[Dict[str, Any]] = None,

    ):

        """Save an interaction to memory.



        Args:

            stability: "high" (stable fact/decision → SQLite), "medium" (normal),

                       "low" (transient tool output → Working only, skip Episodic).

            is_critical: If True, the interaction is preserved through all

                         compression levels (e.g. HITL approvals, pipeline decisions).

        """

        # Phase 40: Apply user-configurable memory rules

        rules = self.load_memory_rules()

        ignore_greetings = rules.get("ignore_greetings", True)

        capture_errors = rules.get("capture_errors", True)

        ignore_patterns = [p.lower() for p in rules.get("ignore_patterns", [])]

        capture_patterns = [p.lower() for p in rules.get("capture_patterns", ["error", "failed", "timeout", "exception"])]



        user_lower = (user_message or "").lower().strip()

        asst_lower = (assistant_message or "").lower().strip()



        # Check capture patterns on both user and assistant messages

        for pattern in capture_patterns:

            if pattern and (pattern in user_lower or pattern in asst_lower):

                is_critical = True

                stability = "high"

                break



        # Check ignore patterns on user message only (don't ignore assistant output)

        if ignore_greetings:

            greet_words = ["hello", "hi", "hey", "thanks", "thank you", "bye", "good morning", "good afternoon", "ok", "好的", "你好", "谢谢", "再见", "收到"]

            for g in greet_words:

                if user_lower == g or user_lower.startswith(g):

                    stability = "low"

                    break

        for pattern in ignore_patterns:

            if pattern and pattern in user_lower:

                stability = "low"

                break



        # Save to working memory (all stability levels)

        _wm_meta = {"session_id": session_id} if session_id else {}

        self._working.add("user", user_message, metadata=_wm_meta)

        self._working.add("assistant", assistant_message, metadata=_wm_meta)
        import logging as _sl; _sl.getLogger('MEMORY_DEBUG').warning('save_interaction: session=%s messages=%d', session_id, self._working.message_count)



        # Lazy-start background cleanup on first interaction

        if self._cleanup_task is None:

            await self.start_background_tasks()



        # Episodic: skip low-stability (transient tool output, debug traces)

        if stability != "low":

            await self._episodic.add_interaction(

                user_message, assistant_message, tool_calls,

                is_critical=is_critical,

            )

            # Fire background importance scoring (never blocks main loop)

            if self._episodic._scoring_enabled:

                llm = self._get_llm_callable()

                if llm:

                    asyncio.create_task(self._episodic._score_interactions(llm))



        # Update episodic summary if needed

        if stability != "low" and await self._episodic.should_update():

            llm_callable = self._get_llm_callable()

            if self._config.use_llm_summary and llm_callable:

                summary = await self._episodic.update_summary(llm_callable=llm_callable)

                logger.info(f"Updated episodic summary: {summary.summary[:100]}")

            else:

                summary = await self._episodic.update_summary()



        # Bridge to SQLite: only high-stability (stable facts, decisions)

        if self._persist_callback and stability == "high":

            try:

                await self._persist_callback(

                    namespace=self.namespace,

                    user_message=user_message,

                    assistant_message=assistant_message,

                )

            except Exception:

                logging.getLogger("memory").warning("best-effort skipped", exc_info=True)



        # Auto Memory (P6): detect patterns and auto-save learnings to file

        try:

            self._interaction_count = getattr(self, "_interaction_count", 0) + 1

            corrections = sum(1 for tc in (tool_calls or []) if isinstance(tc, dict) and tc.get("name") == "correct_agent")

            from core.harness.memory.file_store import auto_save_learning, should_auto_learn

            if should_auto_learn(self._interaction_count, corrections):

                if corrections >= 2:

                    auto_save_learning("correction",

                        f"Agent corrected {corrections} times in session",

                        source="auto")

                if self._interaction_count % 10 == 0:

                    auto_save_learning("pattern",

                        f"Checkpoint: {self._interaction_count} interactions",

                        source="auto")

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)


            # Wiki auto-extraction: high-stability insights → knowledge atoms

            try:

                import re as _re

                assistant = str(assistant_message or "").strip()

                if len(assistant) > 80:

                    from core.harness.knowledge.wiki_engine import write_page, search_pages

                    existing = search_pages(limit=100)

                    existing_titles = [p["title"] for p in existing]

                    title_match = _re.match(r'^(.{5,60}?)[.!?。！？\n]', assistant)

                    title = (title_match.group(1) if title_match else assistant[:60]).strip()

                    if title and len(title) >= 10:

                        safe_title = _re.sub(r'[<>:"/\\|?*]', '_', title)[:80]

                        if safe_title not in existing_titles:

                            write_page(safe_title, assistant[:5000],

                                       category="topics",

                                       tags=["memory", "auto-extracted"],

                                       summary=assistant[:300].replace('\n', ' '),

                                       source_articles=["memory:episodic"])

            except Exception as e:

                logging.warning(str(e), exc_info=True)



    def export_episodic_state(self) -> Dict[str, Any]:

        """Export episodic memory for persistence (survives restart)."""

        return {

            "summary": self._episodic._summary,

            "message_count": self._episodic._message_count,

            "full_messages": self._episodic._full_messages[-500:],  # cap at 500

        }



    def import_episodic_state(self, state: Dict[str, Any]) -> None:

        """Restore episodic memory from persisted state."""

        if not state or not isinstance(state, dict):

            return

        self._episodic._summary = str(state.get("summary", "") or "")

        self._episodic._message_count = int(state.get("message_count", 0) or 0)

        messages = state.get("full_messages")

        if isinstance(messages, list):

            self._episodic._full_messages = messages

    

    async def capture_to_semantic(

        self,

        key: str,

        content: str,

        metadata: Optional[Dict] = None,

        expires_at: Optional[Any] = None,

    ):

        """Capture important info to semantic memory.



        Args:

            expires_at: Optional datetime for TTL-based expiration.

                        stability="low" → 7 days, "medium" → 30 days, "high" → None (permanent).

        """

        # Stamp tenant/session so semantic retrieve can enforce isolation (§5.12).

        if self._tenant_id is not None or self._session_id is not None:

            metadata = dict(metadata or {})

            if self._tenant_id is not None:

                metadata.setdefault("tenant_id", self._tenant_id)

            if self._session_id is not None:

                metadata.setdefault("session_id", self._session_id)

        await self._semantic.store(key, content, metadata, expires_at=expires_at)



    async def cleanup_semantic_expired(self) -> int:

        """Soft-delete expired low-access semantic memories. Returns count cleaned."""

        return await self._semantic.cleanup_expired()



    async def forget_semantic(self, key: str) -> bool:

        """Phase 40: Soft-delete a semantic memory entry. Returns True if deleted."""

        return await self._semantic.delete(key)



    async def recover_semantic(self, key: str) -> bool:

        """Phase 40: Recover a soft-deleted semantic memory entry."""

        return self._semantic.recover_deleted(key)



    async def increment_semantic_access(self, keys: list) -> None:

        """Phase 46: Batch increment access_count for semantic memory keys."""

        await self._semantic.increment_access_count(keys)



    async def search_semantic(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:

        """Phase 40: Search semantic memories and return with provenance fields."""

        items = await self._semantic.retrieve(query, top_k=top_k, threshold=0.0)

        out: List[Dict[str, Any]] = []

        for item in items:

            out.append({

                "key": item.id,

                "content": item.content,

                "metadata": item.metadata,

                "access_count": item.access_count,

                "is_deleted": item.is_deleted,

                "source_tag": item.source_tag,

                "trust_weight": item.trust_weight,

                "provenance": item.provenance,

                "created_at": item.created_at.isoformat() if item.created_at else None,

            })

        return out



    # ── Phase 40: Memory Rules (user-configurable meta-cognition) ──



    _RULES_PATH = os.path.expanduser("~/.aiplat/memory_rules.json")

    _DEFAULT_RULES = {

        "ignore_greetings": True,

        "capture_errors": True,

        "ignore_patterns": [],

        "capture_patterns": ["error", "failed", "timeout", "exception"],

    }



    @classmethod

    def load_memory_rules(cls) -> Dict[str, Any]:

        """Load user-configurable memory rules from disk."""

        import json as _json

        if os.path.exists(cls._RULES_PATH):

            try:

                with open(cls._RULES_PATH, "r") as f:

                    return _json.load(f)

            except Exception:

                logging.getLogger(__name__).debug('load_memory_rules failed', exc_info=True)
        return dict(cls._DEFAULT_RULES)



    @classmethod

    def save_memory_rules(cls, rules: Dict[str, Any]) -> None:

        """Save user memory rules to disk."""

        import json as _json

        os.makedirs(os.path.dirname(cls._RULES_PATH), exist_ok=True)

        current = cls.load_memory_rules()

        current.update(rules)

        with open(cls._RULES_PATH, "w") as f:

            _json.dump(current, f, indent=2)



    async def save_task_skill(self, skill: TaskSkill) -> str:

        """Persist a L3 task skill to disk and index.



        Returns the skill file path.

        """

        import json as _json

        import os as _os

        skills_dir = _os.path.expanduser("~/.aiplat/task_skills")

        _os.makedirs(skills_dir, exist_ok=True)

        skill_path = _os.path.join(skills_dir, f"{skill.skill_id}.json")

        data = {

            "skill_id": skill.skill_id,

            "name": skill.name,

            "pipeline_id": skill.pipeline_id,

            "agent_sequence": skill.agent_sequence,

            "artifacts": skill.artifacts,

            "pass_rate": skill.pass_rate,

            "keywords": skill.keywords,

            "artifacts_keys": skill.artifacts_keys,

            "rollback_count": skill.rollback_count,

            "plan_id": skill.plan_id,

            "created_at": skill.created_at,

            "last_used_at": skill.last_used_at,

        }

        with open(skill_path, "w") as f:

            _json.dump(data, f, indent=2)

        logger.info(f"TaskSkill saved: {skill.skill_id} → {skill_path}")



        # Auto-register in SkillRegistry so agents can discover it
        # Only register hot skills (pass_rate ≥ 85%) to avoid low-quality contamination

        try:

            from core.harness.integration import get_skill_registry

            from core.apps.skills.metadata import SkillMetadata

            if not getattr(skill, 'is_hot', False):
                logger.info(f"TaskSkill {skill.skill_id} pass_rate={skill.pass_rate:.2f} < 0.85, skipping registry")
                return skill_path

            registry = get_skill_registry()

            if registry:

                meta = SkillMetadata(

                    id=skill.skill_id,

                    name=skill.name or skill.skill_id,

                    description=f"Learned task skill (pipeline={skill.pipeline_id})",

                    tags=skill.keywords or [],

                    status="enabled",

                )

                registry.register(meta)

                logger.info(f"TaskSkill registered in SkillRegistry: {skill.skill_id}")

        except Exception as e:

            logging.warning(str(e), exc_info=True)



        return skill_path



    async def load_task_skill(self, skill_id: str) -> Optional[TaskSkill]:

        """Load a L3 task skill from disk."""

        import json as _json

        import os as _os

        skill_path = _os.path.expanduser(f"~/.aiplat/task_skills/{skill_id}.json")

        if not _os.path.exists(skill_path):

            return None

        with open(skill_path) as f:

            data = _json.load(f)

        return TaskSkill(

            skill_id=data["skill_id"],

            name=data.get("name", ""),

            pipeline_id=data.get("pipeline_id", ""),

            agent_sequence=data.get("agent_sequence", []),

            artifacts=data.get("artifacts", []),

            pass_rate=data.get("pass_rate", 0.0),

            keywords=data.get("keywords", []),

            artifacts_keys=data.get("artifacts_keys", {}),

            rollback_count=data.get("rollback_count", 0),

            plan_id=data.get("plan_id", ""),

            created_at=data.get("created_at", ""),

            last_used_at=data.get("last_used_at", ""),

        )



    async def find_similar_task_skills(

        self, keywords: List[str], min_pass_rate: float = 0.7, limit: int = 5,

        query_text: str = "",

    ) -> List[TaskSkill]:

        import os as _os

        import json as _json

        skills_dir = _os.path.expanduser("~/.aiplat/task_skills")

        if not _os.path.isdir(skills_dir):

            return []



        # Load skill files via asyncio.to_thread to avoid blocking event loop

        import asyncio as _asyncio

        def _load_skills() -> List[Dict]:

            results: List[Dict] = []

            for fname in _os.listdir(skills_dir):

                if not fname.endswith(".json"):

                    continue

                fpath = _os.path.join(skills_dir, fname)

                try:

                    with open(fpath) as f:

                        results.append(_json.load(f))

                except Exception:

                    continue

            return results

        all_data = await _asyncio.to_thread(_load_skills)



        results: List[TaskSkill] = []

        kw_lower = {k.lower() for k in keywords}

        for data in all_data:

            skill_kws = {k.lower() for k in data.get("keywords", [])}

            overlap = len(kw_lower & skill_kws)

            if overlap == 0:

                continue

            pr = data.get("pass_rate", 0) or 0

            if pr < min_pass_rate:

                continue

            results.append(self._build_task_skill(data))



        # Embedding fallback: if keyword match returned too few, try semantic similarity

        if len(results) < limit and query_text and len(query_text.strip()) > 10:

            try:

                from core.harness.memory.embedding import get_embedding_provider

                provider = get_embedding_provider()

                query_vec = await provider.embed_single(query_text)

                if query_vec:

                    scored: List[tuple] = []

                    for data in all_data:

                        try:

                            pr = data.get("pass_rate", 0) or 0

                            if pr < min_pass_rate:

                                continue

                            text = " ".join([

                                data.get("name", ""),

                                " ".join(data.get("agent_sequence", [])),

                                " ".join(data.get("keywords", [])),

                            ])

                            cached_key = f"{text[:200]}"

                            if provider._cache.get(f"all-MiniLM-L6-v2:{cached_key}"):

                                text_vec = provider._cache.get(f"all-MiniLM-L6-v2:{cached_key}")

                            else:

                                text_vec = await provider.embed_single(text)

                            if text_vec:

                                sim = provider.cosine_similarity(query_vec, text_vec)

                                if sim > 0.3:

                                    skill = self._build_task_skill(data)

                                    scored.append((skill, sim))

                        except Exception:

                            continue

                    scored.sort(key=lambda x: -x[1])

                    existing_ids = {s.skill_id for s in results}

                    for skill, sim in scored:

                        if skill.skill_id not in existing_ids:

                            results.append(skill)

                            existing_ids.add(skill.skill_id)

                            if len(results) >= limit:

                                break

            except Exception:

                logging.getLogger("manager").warning("best-effort skipped", exc_info=True)



        results.sort(key=lambda s: (-s.pass_rate, -len(s.keywords)))

        return results[:limit]



    @staticmethod

    def _build_task_skill(data: Dict) -> TaskSkill:

        return TaskSkill(

            skill_id=data["skill_id"],

            name=data.get("name", ""),

            pipeline_id=data.get("pipeline_id", ""),

            agent_sequence=data.get("agent_sequence", []),

            artifacts=data.get("artifacts", []),

            pass_rate=data.get("pass_rate", 0) or 0,

            keywords=data.get("keywords", []),

            artifacts_keys=data.get("artifacts_keys", {}),

            rollback_count=data.get("rollback_count", 0),

            plan_id=data.get("plan_id", ""),

            created_at=data.get("created_at", ""),

            last_used_at=data.get("last_used_at", ""),

        )



    async def list_hot_task_skills(self) -> List[TaskSkill]:

        """Return only hot task skills (pass_rate >= 85%)."""

        import os as _os

        import json as _json

        skills_dir = _os.path.expanduser("~/.aiplat/task_skills")

        if not _os.path.isdir(skills_dir):

            return []

        hot: List[TaskSkill] = []

        for fname in _os.listdir(skills_dir):

            if not fname.endswith(".json"):

                continue

            fpath = _os.path.join(skills_dir, fname)

            try:

                with open(fpath) as f:

                    data = _json.load(f)

                pr = data.get("pass_rate", 0) or 0

                if pr < 0.85:

                    continue

                hot.append(TaskSkill(

                    skill_id=data["skill_id"],

                    name=data.get("name", ""),

                    pipeline_id=data.get("pipeline_id", ""),

                    agent_sequence=data.get("agent_sequence", []),

                    artifacts=data.get("artifacts", []),

                    pass_rate=pr,

                    keywords=data.get("keywords", []),

                    artifacts_keys=data.get("artifacts_keys", {}),

                    rollback_count=data.get("rollback_count", 0),

                    plan_id=data.get("plan_id", ""),

                    created_at=data.get("created_at", ""),

                    last_used_at=data.get("last_used_at", ""),

                ))

            except Exception:

                continue

        hot.sort(key=lambda s: -s.pass_rate)

        return hot



    async def export_all(self, namespace_filter: str = "") -> Dict[str, Any]:

        """Serialize all memory layers into a portable JSON structure.



        Returns a complete snapshot of Working, Episodic, Semantic, and

        TaskSkill memories. Used for instance migration and backup.

        """

        import os as _os

        import json as _json

        import time as _time



        result = {

            "version": "1.0",

            "exported_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),

            "system": "aiplat-core",

            "memory": {

                "episodic": {"summary": self._episodic.get_summary()},

                "semantic": [],

                "task_skills": [],

                "sessions": [],

            },

        }



        for key, item in self._semantic._items.items():

            entry = {"key": key, "content": item.content, "metadata": item.metadata}

            if namespace_filter and namespace_filter not in str(item.metadata.get("namespace", "")):

                continue

            result["memory"]["semantic"].append(entry)



        skills_dir = _os.path.expanduser("~/.aiplat/task_skills")

        if _os.path.isdir(skills_dir):

            for fname in _os.listdir(skills_dir):

                if fname.endswith(".json"):

                    try:

                        with open(_os.path.join(skills_dir, fname)) as f:

                            result["memory"]["task_skills"].append(_json.load(f))

                    except Exception:

                        logging.getLogger("manager").warning("best-effort skipped", exc_info=True)



        return result



    async def import_from(self, data: Dict[str, Any], merge: bool = False) -> Dict[str, Any]:

        """Restore memory from a JSON export. merge=True: add to existing; merge=False: replace.



        Returns summary of what was restored.

        """

        summary = {"semantic_restored": 0, "task_skills_restored": 0, "errors": []}

        memory = data.get("memory", {})



        if not merge:

            self._episodic._full_messages = []

            self._episodic._summary = ""

            self._semantic._items.clear()



        if memory.get("episodic", {}).get("summary"):

            self._episodic._summary = str(memory["episodic"]["summary"])



        for entry in memory.get("semantic", []):

            try:

                key = entry.get("key", "")

                if key and key not in self._semantic._items:

                    await self._semantic.store(

                        key=key,

                        content=entry.get("content", ""),

                        metadata=entry.get("metadata"),

                    )

                    summary["semantic_restored"] += 1

            except Exception as e:

                summary["errors"].append(f"semantic:{key}:{e}")



        import os as _os

        skills_dir = _os.path.expanduser("~/.aiplat/task_skills")

        for skill_data in memory.get("task_skills", []):

            sid = skill_data.get("skill_id", "")

            if not sid:

                continue

            try:

                _os.makedirs(skills_dir, exist_ok=True)

                skill_path = _os.path.join(skills_dir, f"{sid}.json")

                if not merge or not _os.path.exists(skill_path):

                    import json as _json

                    with open(skill_path, "w") as f:

                        _json.dump(skill_data, f, indent=2)

                    summary["task_skills_restored"] += 1

            except Exception as e:

                summary["errors"].append(f"task_skill:{sid}:{e}")



        return summary



    async def inspect(self, namespace: str = "") -> Dict[str, Any]:

        """Return human-readable snapshot of all memory layers for diagnostics.



        When namespace is provided, return only memories tagged with that namespace.

        """

        result = {

            "working": {"token_count": self._working.token_count, "message_count": self._working.message_count},

            "episodic": {"summary": self._episodic.get_summary()},

            "semantic": {"total_items": len(self._semantic._items), "items": []},

            "task_skills": {"total": 0, "skills": []},

        }

        for key, item in self._semantic._items.items():

            if namespace and namespace not in str(item.metadata.get("namespace", key)):

                continue

            result["semantic"]["items"].append({

                "key": key,

                "content": item.content[:200],

                "metadata": item.metadata,

                "source_tag": item.source_tag or "",

                "trust_weight": item.trust_weight,

                "provenance": item.provenance or "",

                "access_count": item.access_count,

                "is_deleted": item.is_deleted,

            })

        import os as _os

        import json as _json

        skills_dir = _os.path.expanduser("~/.aiplat/task_skills")

        if _os.path.isdir(skills_dir):

            for fname in _os.listdir(skills_dir):

                if fname.endswith(".json"):

                    try:

                        with open(_os.path.join(skills_dir, fname)) as f:

                            sk = _json.load(f)

                            result["task_skills"]["skills"].append({"skill_id": sk.get("skill_id"), "pass_rate": sk.get("pass_rate"), "name": sk.get("name")})

                    except Exception:

                        logging.getLogger("manager").warning("best-effort skipped", exc_info=True)

        result["task_skills"]["total"] = len(result["task_skills"]["skills"])

        return result

    

    @staticmethod

    def _estimate_tokens(text: str) -> int:

        try:

            import tiktoken

            enc = tiktoken.get_encoding("cl100k_base")

            return len(enc.encode(text))

        except Exception:

            return max(1, int(len(text) / 3.5))



    def _get_llm_callable(self):

        """Get a reusable LLM callable for episodic summarization and scoring.

        If model wasn't injected at init time (env vars not yet available),
        attempts lazy injection on first use.
        """

        if not self._config.use_llm_summary:

            return None

        # Lazy injection: retry if init-time injection failed
        if self._config.model is None:
            try:
                from core.harness.utils.model_injection import best_model_for_purpose, create_selected_adapter
                model_name = best_model_for_purpose("doc_llm")
                if model_name:
                    self._config.model = create_selected_adapter(model_name=model_name)
                    logger.info("Episodic LLM summarization: lazy-injected model '%s'", model_name)
            except Exception as e:
                logger.warning("Episodic LLM: lazy injection failed: %s", e)
                return None

        if self._config.model is None:
            return None

        try:

            async def _call_llm(prompt: str):

                from ..syscalls.llm import sys_llm_generate

                model = self._config.model if hasattr(self._config, 'model') and self._config.model else None

                if model is None:

                    raise RuntimeError("No model available — set MemoryConfig.model")

                resp = await sys_llm_generate(model, prompt)

                return getattr(resp, "content", str(resp))

            return _call_llm

        except Exception:

            return None



    def _count_consecutive_reads(self, context: List[Dict]) -> int:

        """Count consecutive read operations"""

        reads = 0

        for msg in reversed(context[-10:]):

            tool = msg.get("metadata", {}).get("tool", "")

            if tool in ["Read", "Grep", "Glob"]:

                reads += 1

            else:

                break

        return reads

    

    def _check_last_tool_failed(self, context: List[Dict]) -> bool:

        """Check if last tool call failed"""

        if context:

            last = context[-1]

            return last.get("metadata", {}).get("tool_failed", False)

        return False

    

    def get_stats(self) -> Dict:

        """Get memory system statistics"""

        return {

            "working": {

                "tokens": self._working.token_count,

                "messages": self._working.message_count

            },

            "semantic": self._semantic.get_stats(),

            "compression": "enabled" if self._config.enable_compression else "disabled",

            "reminders": "enabled" if self._config.enable_reminders else "disabled"

        }





# Per-namespace memory managers

_memory_managers: Dict[tuple, MemoryManager] = {}

_default_manager: Optional[MemoryManager] = None





def get_memory_manager(config: Optional[MemoryConfig] = None, namespace: str = "default",

                       *, tenant_id: Optional[str] = None,

                       session_id: Optional[str] = None) -> MemoryManager:

    """Get memory manager for a namespace.



    When namespace='default' (and no tenant/session scope), returns the legacy

    singleton (backward compat). Other namespaces / tenant-scoped managers get their

    own isolated MemoryManager instance, cached by (namespace, tenant_id, session_id)

    so a tenant-scoped manager is never reused across tenants.

    """

    global _default_manager, _memory_managers

    if (namespace == "default" or not namespace) and tenant_id is None and session_id is None:

        if _default_manager is None:

            _default_manager = MemoryManager(config, namespace="default")

            _wire_persist_callback(_default_manager)

        return _default_manager

    key = (namespace or "default", tenant_id, session_id)

    if key not in _memory_managers:

        _memory_managers[key] = MemoryManager(

            config, namespace=namespace or "default",

            tenant_id=tenant_id, session_id=session_id)

        _wire_persist_callback(_memory_managers[key])

    return _memory_managers[key]





def _wire_persist_callback(mgr: MemoryManager) -> None:

    """Wire the MemoryManager's persistence callback to execution_store's long_term_memories."""

    async def _persist(**kwargs) -> None:
        # Accept both legacy dict-style and new kwarg-style calling conventions
        interaction = kwargs.get("interaction") or kwargs
        if isinstance(interaction, dict) and "namespace" in interaction:
            interaction = interaction
        else:
            # New-style: namespace, user_message, assistant_message
            interaction = {
                "user_id": str(kwargs.get("user_id", "system")),
                "session_id": str(kwargs.get("namespace", "default")),
                "summary": str(kwargs.get("assistant_message", ""))[:5000],
                "metadata": str(kwargs.get("user_message", ""))[:2000],
                "timestamp": kwargs.get("timestamp", None),
            }

        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            await store.add_long_term_memory(
                user_id=str(interaction.get("user_id", "system")),
                content=str(interaction.get("summary", ""))[:5000],
                key=str(interaction.get("session_id", "default")),
                metadata={"raw_user_message": str(interaction.get("metadata", ""))[:2000]},
            )
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    mgr._persist_callback = _persist





__all__ = [

    "MemoryConfig",

    "BuildContextResult",

    "TaskSkill",

    "MemoryManager",

    "get_memory_manager"

]

