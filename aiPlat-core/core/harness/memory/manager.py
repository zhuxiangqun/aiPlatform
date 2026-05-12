"""
Memory Manager

Integrates Working, Episodic, and Semantic memory layers.
"""

import logging
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
    """L3 skill-layer memory: how to execute a task, not what to know.

    Completed pipeline execution paths are crystallized into reusable TaskSkills.
    This is the GenericAgent L3 equivalent — procedural memory distinct from
    knowledge-layer memory (L1 Working, L2 Episodic/Semantic).
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
    to keep memories separate (e.g., 'architect', 'programmer', 'qa').
    """

    def __init__(self, config: Optional[MemoryConfig] = None, namespace: str = "default"):
        self._config = config or MemoryConfig()
        self.namespace = namespace
        self._persist_callback = None  # injected by service layer for SQLite persistence

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
    
    async def build_context(
        self,
        current_query: str,
        system_prompt: str
    ) -> BuildContextResult:
        """Build complete context from all memory layers"""
        
        # 1. Retrieve relevant semantic memories
        relevant_memories = await self._semantic.retrieve(current_query)
        
        # 2. Get episodic summary
        episodic_summary = self._episodic.get_summary()
        
        # 3. Get working memory context
        working_context = self._working.get_context()
        
        # 4. Build messages list
        messages = [{"role": "system", "content": system_prompt}]
        
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
        
        # Add working memory
        messages.extend(working_context)
        
        # Add current query
        messages.append({"role": "user", "content": current_query})
        
        # 5. Check compression
        total_tokens = sum(len(m.get("content", "").split()) * 1.3 for m in messages)
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
            working_context=working_context[-3] if isinstance(working_context, list) and working_context else "",
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
    ):
        """Save an interaction to memory.

        Args:
            stability: "high" (stable fact/decision → SQLite), "medium" (normal),
                       "low" (transient tool output → Working only, skip Episodic).
        """
        # Save to working memory (all stability levels)
        self._working.add("user", user_message)
        self._working.add("assistant", assistant_message)

        # Episodic: skip low-stability (transient tool output, debug traces)
        if stability != "low":
            await self._episodic.add_interaction(user_message, assistant_message, tool_calls)

        # Update episodic summary if needed
        if stability != "low" and await self._episodic.should_update():
            llm_callable = None
            if self._config.use_llm_summary:
                async def _call_llm(prompt: str):
                    from ..syscalls.llm import sys_llm_generate
                    try:
                        from ..execution.loop import _default_model
                        model = _default_model() if callable(_default_model) else None
                    except Exception:
                        model = None
                    if model is None:
                        raise RuntimeError("No model available for episodic summary")
                    resp = await sys_llm_generate(model, prompt)
                    return getattr(resp, "content", str(resp))
                llm_callable = _call_llm
            summary = await self._episodic.update_summary(llm_callable=llm_callable)
            logger.info(f"Updated episodic summary: {summary.summary[:100]}")

        # Bridge to SQLite: only high-stability (stable facts, decisions)
        if self._persist_callback and stability == "high":
            try:
                await self._persist_callback(
                    namespace=self.namespace,
                    user_message=user_message,
                    assistant_message=assistant_message,
                )
            except Exception:
                pass
    
    async def capture_to_semantic(
        self,
        key: str,
        content: str,
        metadata: Optional[Dict] = None
    ):
        """Capture important info to semantic memory"""
        await self._semantic.store(key, content, metadata)

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
        """Find task skills matching given keywords (primary) or semantic similarity (fallback).

        Hot skills (pass_rate >= 85%) are prioritized and returned first.
        Cold skills (pass_rate < 70%) are indexed only — not loaded by default.

        When query_text is provided and keyword overlap is insufficient,
        falls back to embedding-based semantic similarity via EmbeddingProvider.
        """
        import os as _os
        import json as _json
        skills_dir = _os.path.expanduser("~/.aiplat/task_skills")
        if not _os.path.isdir(skills_dir):
            return []
        results: List[TaskSkill] = []
        kw_lower = {k.lower() for k in keywords}
        for fname in _os.listdir(skills_dir):
            if not fname.endswith(".json"):
                continue
            fpath = _os.path.join(skills_dir, fname)
            try:
                with open(fpath) as f:
                    data = _json.load(f)
                skill_kws = {k.lower() for k in data.get("keywords", [])}
                overlap = len(kw_lower & skill_kws)
                if overlap == 0:
                    continue
                pr = data.get("pass_rate", 0) or 0
                if pr < min_pass_rate:
                    continue
                results.append(self._build_task_skill(data))
            except Exception:
                continue

        # Embedding fallback: if keyword match returned too few, try semantic similarity
        if len(results) < limit and query_text and len(query_text.strip()) > 10:
            try:
                from core.harness.memory.embedding import get_embedding_provider
                provider = get_embedding_provider()
                query_vec = await provider.embed_single(query_text)
                if query_vec:
                    scored: List[tuple] = []
                    for fname in _os.listdir(skills_dir):
                        if not fname.endswith(".json"):
                            continue
                        fpath = _os.path.join(skills_dir, fname)
                        try:
                            with open(fpath) as f:
                                data = _json.load(f)
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
                pass

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
                        pass

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
                        pass
        result["task_skills"]["total"] = len(result["task_skills"]["skills"])
        return result
    
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
_memory_managers: Dict[str, MemoryManager] = {}
_default_manager: Optional[MemoryManager] = None


def get_memory_manager(config: Optional[MemoryConfig] = None, namespace: str = "default") -> MemoryManager:
    """Get memory manager for a namespace.

    When namespace='default', returns the legacy singleton (backward compat).
    Other namespaces get their own isolated MemoryManager instance.
    """
    global _default_manager, _memory_managers
    if namespace == "default" or not namespace:
        if _default_manager is None:
            _default_manager = MemoryManager(config, namespace="default")
        return _default_manager
    if namespace not in _memory_managers:
        _memory_managers[namespace] = MemoryManager(config, namespace=namespace)
    return _memory_managers[namespace]


__all__ = [
    "MemoryConfig",
    "BuildContextResult",
    "TaskSkill",
    "MemoryManager",
    "get_memory_manager"
]