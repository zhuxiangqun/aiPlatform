"""

Phase 27: SharedKnowledgePool — cross-instance memory sharing.



Enables multiple Pipeline/Agent executions to share learned facts, patterns,

and strategy effectiveness data across sessions.



Design:

  - File-based JSON append-only log (~/.aiplat/shared_knowledge/pool.json)

  - Max 200 entries, FIFO eviction

  - publish(): append a fact to the shared pool

  - query(): search pool by topic/keyword

  - merge(): resolve conflicts via existing _resolve_semantic_conflict (Phase 23)



Integration:

  - MemoryManager.build_context() — inject top-N shared facts for current query

  - MemoryManager.save_interaction() — auto-publish important learned facts

  - StrategyEffectivenessTracker — share top strategies across instances

"""



from __future__ import annotations



import json

import logging

import os

import time

from dataclasses import dataclass, field, asdict

from typing import Any, Dict, List, Optional



logger = logging.getLogger("aiplat.shared_knowledge")



POOL_ROOT = os.path.expanduser("~/.aiplat/shared_knowledge")

POOL_FILE = os.path.join(POOL_ROOT, "pool.json")

POOL_DB = os.path.join(POOL_ROOT, "pool.db")  # Phase 34: SQLite WAL backend

MAX_POOL_SIZE = 200





@dataclass

class SharedFact:

    """A knowledge fact published to the shared pool."""



    fact_id: str

    session_id: str

    agent_id: str

    topic: str

    content: str

    confidence: float = 1.0

    source: str = "auto"  # "auto" | "manual" | "strategy"

    timestamp: float = field(default_factory=time.time)

    metadata: Dict[str, Any] = field(default_factory=dict)



    def to_dict(self) -> Dict[str, Any]:

        return asdict(self)



    @classmethod

    def from_dict(cls, d: Dict[str, Any]) -> "SharedFact":

        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})





class SharedKnowledgePool:

    """Cross-instance knowledge pool backed by a JSON append-only log.



    Usage:

        pool = SharedKnowledgePool()

        pool.publish(topic="rate_limit", content="rotate_credential succeeds 85%",

                     source="strategy", confidence=0.85)

        facts = pool.query("rate_limit", limit=5)

        # → [SharedFact(...), ...]

    """



    def __init__(self):

        os.makedirs(POOL_ROOT, exist_ok=True)

        self._facts: List[SharedFact] = []

        self._loaded = False

        self._db_conn = None  # Phase 34: SQLite WAL



    def _init_db(self):

        """Phase 34: Initialize SQLite WAL backend for concurrent access."""

        if self._db_conn is not None:

            return

        import sqlite3

        try:

            self._db_conn = sqlite3.connect(POOL_DB, check_same_thread=False, timeout=10)

            self._db_conn.execute("PRAGMA journal_mode=WAL;")

            self._db_conn.execute("PRAGMA synchronous=NORMAL;")

            self._db_conn.execute("""

                CREATE TABLE IF NOT EXISTS shared_facts (

                    fact_id TEXT PRIMARY KEY,

                    session_id TEXT,

                    agent_id TEXT,

                    topic TEXT,

                    content TEXT,

                    confidence REAL,

                    source TEXT,

                    timestamp REAL,

                    metadata_json TEXT

                )

            """)

            self._db_conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_shared_facts_topic ON shared_facts(topic);"

            )

            self._db_conn.execute(

                "CREATE INDEX IF NOT EXISTS idx_shared_facts_timestamp ON shared_facts(timestamp);"

            )

            self._db_conn.commit()

        except sqlite3.OperationalError:

            # Corrupted DB — recreate

            try:

                self._db_conn.close()

            except Exception:

                logging.getLogger(__name__).debug('_init_db failed', exc_info=True)
            self._db_conn = None

            for _suffix in ("", "-wal", "-shm"):

                try:

                    os.remove(POOL_DB + _suffix)

                except OSError:

                    pass  # noqa: cleanup-best-effort

            self._db_conn = sqlite3.connect(POOL_DB, check_same_thread=False)

            self._db_conn.execute("PRAGMA journal_mode=WAL;")

            self._db_conn.execute("PRAGMA synchronous=NORMAL;")

            self._db_conn.execute("""

                CREATE TABLE IF NOT EXISTS shared_facts (

                    fact_id TEXT PRIMARY KEY,

                    session_id TEXT,

                    agent_id TEXT,

                    topic TEXT,

                    content TEXT,

                    confidence REAL,

                    source TEXT,

                    timestamp REAL,

                    metadata_json TEXT

                )

            """)

            self._db_conn.commit()



    def _load(self) -> None:

        if self._loaded:

            return

        self._init_db()

        # Phase 34: Load from SQLite (supports concurrent reads)

        try:

            rows = self._db_conn.execute(

                "SELECT fact_id, session_id, agent_id, topic, content, confidence, "

                "source, timestamp, metadata_json FROM shared_facts "

                "ORDER BY timestamp DESC LIMIT ?", (MAX_POOL_SIZE,)

            ).fetchall()

            self._facts = []

            for row in rows:

                meta = json.loads(row[8]) if row[8] else {}

                self._facts.append(SharedFact(

                    fact_id=row[0], session_id=row[1], agent_id=row[2],

                    topic=row[3], content=row[4], confidence=row[5],

                    source=row[6], timestamp=row[7], metadata=meta,

                ))

            self._loaded = True

            return

        except Exception as e:

            logger.warning("SharedKnowledgePool: SQLite load failed: %s", e)



        # Fallback: JSON file

        if os.path.exists(POOL_FILE):

            try:

                with open(POOL_FILE, "r", encoding="utf-8") as f:

                    data = json.load(f)

                self._facts = [SharedFact.from_dict(d) for d in data]

            except (json.JSONDecodeError, OSError) as e:

                logger.warning("SharedKnowledgePool: load failed: %s", e)

                self._facts = []

        self._loaded = True



    def _save(self) -> None:

        # Phase 34: Dual-write to SQLite + JSON

        self._init_db()

        try:

            # SQLite: upsert facts

            for f in self._facts:

                self._db_conn.execute(

                    "INSERT OR REPLACE INTO shared_facts "

                    "(fact_id, session_id, agent_id, topic, content, confidence, "

                    "source, timestamp, metadata_json) "

                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",

                    (f.fact_id, f.session_id, f.agent_id, f.topic, f.content,

                     f.confidence, f.source, f.timestamp,

                     json.dumps(f.metadata, ensure_ascii=False) if f.metadata else "{}"),

                )

            # Prune old entries

            self._db_conn.execute(

                "DELETE FROM shared_facts WHERE fact_id NOT IN "

                "(SELECT fact_id FROM shared_facts ORDER BY timestamp DESC LIMIT ?)",

                (MAX_POOL_SIZE,)

            )

            self._db_conn.commit()

        except Exception as e:

            logger.warning("SharedKnowledgePool: SQLite save failed: %s", e)



        # JSON backup

        try:

            with open(POOL_FILE, "w", encoding="utf-8") as f:

                json.dump([f.to_dict() for f in self._facts], f, ensure_ascii=False, indent=2)

        except OSError as e:

            logger.warning("SharedKnowledgePool: JSON save failed: %s", e)



    def sync_from_db(self) -> int:

        """Phase 34: Sync facts from SQLite (cross-instance polling).



        Other instances may have written new facts. Call this periodically.

        Returns number of new facts found.

        """

        self._init_db()

        old_count = len(self._facts)

        # Reload from DB

        try:

            rows = self._db_conn.execute(

                "SELECT fact_id, session_id, agent_id, topic, content, confidence, "

                "source, timestamp, metadata_json FROM shared_facts "

                "ORDER BY timestamp DESC LIMIT ?", (MAX_POOL_SIZE,)

            ).fetchall()

            new_facts = []

            old_ids = {f.fact_id for f in self._facts}

            for row in rows:

                if row[0] not in old_ids:

                    meta = json.loads(row[8]) if row[8] else {}

                    new_facts.append(SharedFact(

                        fact_id=row[0], session_id=row[1], agent_id=row[2],

                        topic=row[3], content=row[4], confidence=row[5],

                        source=row[6], timestamp=row[7], metadata=meta,

                    ))

            if new_facts:

                self._facts.extend(new_facts)

                # Keep sorted and capped

                self._facts.sort(key=lambda f: f.timestamp, reverse=True)

                if len(self._facts) > MAX_POOL_SIZE:

                    self._facts = self._facts[:MAX_POOL_SIZE]

                logger.info("[shared_knowledge] synced %d new facts from other instances", len(new_facts))

            return len(new_facts)

        except Exception as e:

            logger.debug("sync_from_db failed: %s", e)

            return 0



    def query_since(self, timestamp: float, limit: int = 100) -> List[SharedFact]:

        """Phase 36: Return facts newer than timestamp for Gossip sync."""

        self._load()

        newer = [f for f in self._facts if f.timestamp > timestamp]

        newer.sort(key=lambda f: f.timestamp, reverse=True)

        return newer[:limit]



    def publish(

        self,

        topic: str,

        content: str,

        *,

        session_id: str = "",

        agent_id: str = "",

        confidence: float = 1.0,

        source: str = "auto",

        metadata: Optional[Dict[str, Any]] = None,

    ) -> Optional[str]:

        """Publish a fact to the shared pool. Returns fact_id or None."""

        import uuid



        self._load()

        fact_id = f"fact-{uuid.uuid4().hex[:12]}"

        fact = SharedFact(

            fact_id=fact_id,

            session_id=session_id,

            agent_id=agent_id,

            topic=topic,

            content=content,

            confidence=confidence,

            source=source,

            metadata=metadata or {},

        )

        self._facts.append(fact)



        # Evict oldest if over limit

        if len(self._facts) > MAX_POOL_SIZE:

            self._facts = self._facts[-MAX_POOL_SIZE:]



        self._save()

        logger.info(

            "[shared_knowledge] published: topic=%s source=%s confidence=%.2f",

            topic, source, confidence,

        )

        return fact_id



    def query(

        self,

        topic: str = "",

        *,

        limit: int = 10,

        min_confidence: float = 0.5,

        exclude_session_id: str = "",

    ) -> List[SharedFact]:

        """Query shared pool for facts matching a topic.



        Matching: substring match on topic (case-insensitive).

        """

        self._load()

        topic_lower = topic.lower().strip()



        candidates = []

        for fact in self._facts:

            if fact.confidence < min_confidence:

                continue

            if exclude_session_id and fact.session_id == exclude_session_id:

                continue

            if not topic_lower or topic_lower in fact.topic.lower():

                candidates.append(fact)



        # Sort by confidence desc, then recency

        candidates.sort(key=lambda f: (f.confidence, f.timestamp), reverse=True)

        return candidates[:limit]



    def query_all(self, *, limit: int = 20) -> List[SharedFact]:

        """Query all recent facts, highest confidence first."""

        self._load()

        facts = sorted(self._facts, key=lambda f: (f.confidence, f.timestamp), reverse=True)

        return facts[:limit]



    def merge_conflicting(

        self, fact_a_id: str, fact_b_id: str

    ) -> Optional[str]:

        """Resolve conflict between two facts using Jaccard similarity (Phase 23).



        Returns the surviving fact_id, or None if unresolvable.

        """

        self._load()

        fact_a = None

        fact_b = None

        for f in self._facts:

            if f.fact_id == fact_a_id:

                fact_a = f

            elif f.fact_id == fact_b_id:

                fact_b = f



        if not fact_a or not fact_b:

            return None



        # Use Jaccard similarity on content

        try:

            from core.harness.memory.semantic import _cosine_similarity_text

            sim = _cosine_similarity_text(fact_a.content, fact_b.content)

        except Exception:

            # Fallback: simple word overlap

            wa = set(fact_a.content.lower().split())

            wb = set(fact_b.content.lower().split())

            if not wa or not wb:

                sim = 0.0

            else:

                sim = len(wa & wb) / len(wa | wb)



        if sim >= 0.7:

            # Keep the higher confidence one

            if fact_a.confidence >= fact_b.confidence:

                self._facts.remove(fact_b)

                self._save()

                return fact_a_id

            else:

                self._facts.remove(fact_a)

                self._save()

                return fact_b_id

        return None  # both kept, conflict noted



    def stats(self) -> Dict[str, Any]:

        """Pool statistics."""

        self._load()

        topics = {}

        sources = {}

        for f in self._facts:

            topics[f.topic] = topics.get(f.topic, 0) + 1

            sources[f.source] = sources.get(f.source, 0) + 1

        return {

            "total_facts": len(self._facts),

            "max_size": MAX_POOL_SIZE,

            "top_topics": dict(sorted(topics.items(), key=lambda x: -x[1])[:10]),

            "sources": sources,

            "avg_confidence": round(

                sum(f.confidence for f in self._facts) / max(1, len(self._facts)), 3

            ),

        }





# ── Process-wide singleton ──



_pool: Optional[SharedKnowledgePool] = None





def get_shared_knowledge_pool() -> SharedKnowledgePool:

    """Get or create the process-wide shared knowledge pool."""

    global _pool

    if _pool is None:

        _pool = SharedKnowledgePool()

    return _pool


