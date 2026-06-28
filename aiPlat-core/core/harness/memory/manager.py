"""
Memory Manager — Four-Layer Memory System

Layer 1: Working  Memory (Hot)   — 当前对话上下文 (deque, 30K tokens)
Layer 2: Episodic Memory (Warm)  — 会话摘要与关键决策
Layer 3: Semantic Memory (Cold)  — 长期知识 / 用户偏好 (vector + FTS5)
Layer 4: Task Skills   (External)— 可复用执行模式 (流水线晶体化, pass_rate ≥85% 自动注册)

Design reference: Hermes Agent 四层记忆诊断框架.
"""

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


class MemoryManager:
    """Unified memory manager with three-layer architecture.

    Supports namespace-based isolation: each agent can use its own namespace
    to keep memories separate (e.g., 'agent_a', 'agent_b', 'agent_c').
    """

    def __init__(self, config: Optional[MemoryConfig] = None, namespace: str = "default",
                 *, tenant_id: Optional[str] = None, session_id: Optional[str] = None):
        self._config = config or MemoryConfig()
        self.namespace = namespace
        # §5.12 isolation scope: when set, semantic retrieve/capture are tenant+session
        # scoped (build_context auto-applies the S1 filter; capture stamps metadata).
        self._tenant_id = tenant_id
        self._session_id = session_id
        self._persist_callback = None  # injected by service layer for SQLite persistence  # noqa: pending-wire

        # Initialize layers
        self._working = WorkingMemory(
            max_tokens=self._config.working_tokens,
            max_messages=self._config.max_messages
        )
        self._episodic = EpisodicMemory(
            update_interval=self._config.episodic_update_interval
        )
        self._semantic = SemanticMemory(
            store_type=self._config.vector_store_type
        )
        self._compression = ContextCompression()
        self._reminders = get_system_reminders() if self._config.enable_reminders else None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval = int(os.getenv("AIPLAT_MEMORY_CLEANUP_INTERVAL", str(86400)))

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
                logging.debug(str(e), exc_info=True)

    async def shutdown(self) -> None:
        """Gracefully stop background tasks."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
    
    async def build_context(
        self,
        current_query: str,
        system_prompt: str,
        *,
        skip_system_messages: bool = False,
    ) -> BuildContextResult:
        """Build complete context from all memory layers.

        When skip_system_messages=True, the caller handles system-level injection
        (CLAUDE.md, project context) separately — only memory-layer context
        (working/episodic/semantic) is assembled here.
        """
        
        # 1. Retrieve relevant semantic memories
        relevant_memories = await self._semantic.retrieve(
            current_query, tenant_id=self._tenant_id, session_id=self._session_id)
        
        # 2. Get episodic summary
        episodic_summary = self._episodic.get_summary()
        
        # 3. Get working memory context
        working_context = self._working.get_context()
        
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
        try:
            profiles = await self._semantic.retrieve("user_profile preferences constraints", k=1)
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
            logging.debug(str(e), exc_info=True)
        
        # Add working memory
        messages.extend(working_context)
        
        # Add current query
        messages.append({"role": "user", "content": current_query})
        
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
        
        # 7. Apply compression if needed
        if self._config.enable_compression and self._compression.should_trigger_compression(state):
            messages = await self._compression.compress(messages, state)
        
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
        )

    async def get_reminders(self, token_usage_ratio: float = 0.0, consecutive_reads: int = 0,
                            tool_failed: bool = False) -> List[str]:
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
        }
        reminder = await self._reminders.check_and_inject(exec_state)
        return [reminder] if reminder else []
    
    async def save_interaction(
        self,
        user_message: str,
        assistant_message: str,
        tool_calls: Optional[List[Dict]] = None,
        stability: str = "medium",
        is_critical: bool = False,
    ):
        """Save an interaction to memory.

        Args:
            stability: "high" (stable fact/decision → SQLite), "medium" (normal),
                       "low" (transient tool output → Working only, skip Episodic).
            is_critical: If True, the interaction is preserved through all
                         compression levels (e.g. HITL approvals, pipeline decisions).
        """
        # Save to working memory (all stability levels)
        self._working.add("user", user_message)
        self._working.add("assistant", assistant_message)

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
                logging.getLogger("manager").debug("best-effort skipped", exc_info=True)

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
                logging.debug(str(e), exc_info=True)

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
        try:
            from core.harness.integration import get_skill_registry
            from core.apps.skills.metadata import SkillMetadata
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
            logging.debug(str(e), exc_info=True)

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
                logging.getLogger("manager").debug("best-effort skipped", exc_info=True)

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
                        logging.getLogger("manager").debug("best-effort skipped", exc_info=True)

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
            result["semantic"]["items"].append({"key": key, "content": item.content[:200], "metadata": item.metadata})
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
                        logging.getLogger("manager").debug("best-effort skipped", exc_info=True)
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
        """Get a reusable LLM callable for episodic summarization and scoring."""
        if not self._config.use_llm_summary:
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
    async def _persist(interaction: dict) -> None:
        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            user_id = str(interaction.get("user_id", "system"))
            key = str(interaction.get("session_id", "default"))
            content = str(interaction.get("summary", ""))[:5000]
            import uuid, time as _time
            now = _time.time()
            await store._execute(
                "INSERT INTO long_term_memories(id,user_id,key,content,metadata_json,created_at,updated_at,relevance_decay) VALUES(?,?,?,?,?,?,?,?);",
                (str(uuid.uuid4()), user_id, key, content,
                 str(interaction.get("metadata", "{}"))[:2000],
                 interaction.get("timestamp", now), now, 1.0))
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    mgr._persist_callback = _persist


__all__ = [
    "MemoryConfig",
    "BuildContextResult",
    "TaskSkill",
    "MemoryManager",
    "get_memory_manager"
]