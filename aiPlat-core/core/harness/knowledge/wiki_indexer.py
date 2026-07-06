"""WikiIndexer — auto-index generated SKILL.md into knowledge base.
F-axis L4→L5 enabler: WIKI_PATH indexing + Execution→GraphIndex feedback.

Auto-indexes generated artifacts (SKILL.md, learning outputs) into the
knowledge graph and Wiki knowledge base for cross-Agent discoverability.
"""
import asyncio, json, os, sys, sqlite3, threading, hashlib
from datetime import datetime, timezone
from typing import Optional


WIKI_PATH = os.path.expanduser(os.environ.get("AIPLAT_WIKI_PATH", "~/.aiplat/wiki"))


class WikiIndexer:
    """Auto-indexes generated artifacts into knowledge base.

    Watches for new artifacts (SKILL.md, learning outputs) and automatically
    registers them in WIKI_PATH and GraphIndex for cross-Agent discovery.
    """

    def __init__(self, wiki_path: str = WIKI_PATH):
        self.wiki_path = os.path.expanduser(wiki_path)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        os.makedirs(self.wiki_path, exist_ok=True)
        db_path = os.path.join(self.wiki_path, "index.db")
        with self._lock:
            conn = sqlite3.connect(db_path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS indexed_artifacts (
                    artifact_path TEXT PRIMARY KEY,
                    artifact_type TEXT NOT NULL,
                    title TEXT,
                    checksum TEXT NOT NULL,
                    indexed_at TEXT NOT NULL,
                    source_agent TEXT,
                    tags TEXT DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS graph_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL,
                    node_type TEXT,
                    node_value TEXT,
                    relation TEXT,
                    confidence REAL DEFAULT 0.5,
                    created_at TEXT NOT NULL,
                    applied BOOLEAN DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_artifacts_type ON indexed_artifacts(artifact_type);
                CREATE INDEX IF NOT EXISTS idx_graph_feedback_exec ON graph_feedback(execution_id);
            """)
            conn.commit()
            conn.close()

    def index_artifact(self, artifact_path: str, artifact_type: str = "skill",
                       title: str = "", source_agent: str = "",
                       tags: list[str] | None = None) -> bool:
        """Index a generated artifact into WIKI_PATH."""
        if not os.path.isfile(artifact_path):
            return False

        with open(artifact_path, "rb") as f:
            checksum = hashlib.md5(f.read()).hexdigest()

        now = datetime.now(timezone.utc).isoformat()
        wiki_target = os.path.join(self.wiki_path, os.path.basename(artifact_path))

        with self._lock:
            db_path = os.path.join(self.wiki_path, "index.db")
            conn = sqlite3.connect(db_path)
            existing = conn.execute(
                "SELECT checksum FROM indexed_artifacts WHERE artifact_path=?",
                (artifact_path,)).fetchone()
            if existing and existing[0] == checksum:
                conn.close()
                return False

            conn.execute("""
                INSERT INTO indexed_artifacts(artifact_path, artifact_type, title,
                    checksum, indexed_at, source_agent, tags)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(artifact_path) DO UPDATE SET
                    checksum=?, indexed_at=?, tags=?
            """, (artifact_path, artifact_type, title, checksum, now,
                  source_agent, json.dumps(tags or []),
                  checksum, now, json.dumps(tags or [])))
            conn.commit()
            conn.close()

        # Copy to WIKI_PATH
        try:
            with open(artifact_path, "rb") as src:
                with open(wiki_target, "wb") as dst:
                    dst.write(src.read())
        except Exception:
            pass

        return True

    def auto_index_skills(self, skills_dir: str = "~/.aiplat/skills") -> list[str]:
        """Auto-scan and index all SKILL.md files."""
        skills_dir = os.path.expanduser(skills_dir)
        indexed = []
        if not os.path.isdir(skills_dir):
            return indexed

        for name in os.listdir(skills_dir):
            md_path = os.path.join(skills_dir, name, "SKILL.md")
            if os.path.isfile(md_path):
                if self.index_artifact(md_path, "skill", title=name):
                    indexed.append(name)
        return indexed

    async def feed_execution_to_graph(self, execution_id: str, node_type: str,
                                       node_value: str, relation: str = "related_to",
                                       confidence: float = 0.5) -> bool:
        """Feed execution output into GraphIndex as feedback edge.

        Bridges the gap between Agent execution traces and the knowledge graph.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            db_path = os.path.join(self.wiki_path, "index.db")
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO graph_feedback(execution_id, node_type, node_value, relation, confidence, created_at) VALUES(?,?,?,?,?,?)",
                (execution_id, node_type, node_value, relation, confidence, now))
            conn.commit()
            conn.close()

        # Try to register in GraphIndex if available
        try:
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
            core_path = os.path.join(repo_root, 'aiPlat-core')
            if core_path not in sys.path:
                sys.path.insert(0, core_path)
            from core.harness.ontology_engine.graph_index import GraphIndex
            graph = GraphIndex(domain_id=node_type)
            await graph.add_entity(node_value, {"source": "execution_feedback", "execution_id": execution_id})
        except Exception:
            pass

        return True

    def get_indexed_count(self) -> dict:
        db_path = os.path.join(self.wiki_path, "index.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        artifacts = conn.execute("SELECT COUNT(*) as c FROM indexed_artifacts").fetchone()["c"]
        feedback = conn.execute("SELECT COUNT(*) as c FROM graph_feedback WHERE applied=0").fetchone()["c"]
        conn.close()
        return {"indexed_artifacts": artifacts, "pending_feedback": feedback}


_indexer: Optional[WikiIndexer] = None


def get_wiki_indexer() -> WikiIndexer:
    global _indexer
    if _indexer is None:
        _indexer = WikiIndexer()
    return _indexer
