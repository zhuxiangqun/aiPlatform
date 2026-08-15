"""Skill Marketplace — skill discovery, installation, and rating.

import logging
H-axis L4→L5 enabler: ecosystem foundation.



Provides:

- Skill discovery from local and remote registries

- One-click skill installation

- Rating/review system

- Popularity and trending metrics

"""

import asyncio, json, os, sqlite3, sys, threading

from datetime import datetime, timezone

from typing import Optional





class SkillMarketplace:

    """Decentralized skill discovery and installation system.



    Discovers skills from:

    1. Local registry (~/.aiplat/skills/)

    2. Remote Git repositories

    3. Community index (configurable URL)

    """



    def __init__(self, db_path: str = "~/.aiplat/marketplace.db"):

        self.db_path = os.path.expanduser(db_path)

        self._lock = threading.Lock()

        self._init_db()



    def _init_db(self):

        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with self._lock:

            conn = sqlite3.connect(self.db_path)

            conn.executescript("""

                CREATE TABLE IF NOT EXISTS skill_registry (

                    skill_id TEXT PRIMARY KEY,

                    name TEXT NOT NULL,

                    version TEXT DEFAULT '1.0.0',

                    description TEXT,

                    category TEXT,

                    source_url TEXT,

                    installed BOOLEAN DEFAULT 0,

                    install_date TEXT,

                    rating REAL DEFAULT 0,

                    rating_count INTEGER DEFAULT 0,

                    downloads INTEGER DEFAULT 0,

                    tags TEXT DEFAULT '[]'

                );

                CREATE TABLE IF NOT EXISTS skill_ratings (

                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    skill_id TEXT NOT NULL,

                    rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),

                    comment TEXT,

                    profile_id TEXT DEFAULT 'default',

                    created_at TEXT NOT NULL,

                    FOREIGN KEY(skill_id) REFERENCES skill_registry(skill_id)

                );

                CREATE INDEX IF NOT EXISTS idx_registry_category ON skill_registry(category);

                CREATE INDEX IF NOT EXISTS idx_registry_rating ON skill_registry(rating DESC);

            """)

            conn.commit()

            conn.close()



    def register(self, skill_id: str, name: str, description: str = "",

                 category: str = "general", source_url: str = "", tags: list[str] | None = None) -> bool:

        with self._lock:

            conn = sqlite3.connect(self.db_path)

            conn.execute("""

                INSERT INTO skill_registry(skill_id, name, description, category, source_url, tags)

                VALUES(?,?,?,?,?,?)

                ON CONFLICT(skill_id) DO UPDATE SET

                    name=?, description=?, category=?, source_url=?, tags=?

            """, (skill_id, name, description, category, source_url, json.dumps(tags or []),

                  name, description, category, source_url, json.dumps(tags or [])))

            conn.commit()

            conn.close()

        return True



    def install(self, skill_id: str, source_url: str = "") -> bool:

        now = datetime.now(timezone.utc).isoformat()

        with self._lock:

            conn = sqlite3.connect(self.db_path)

            conn.execute(

                "UPDATE skill_registry SET installed=1, install_date=?, downloads=downloads+1 WHERE skill_id=?",

                (now, skill_id))

            conn.commit()

            conn.close()



        # Auto-scan and index if installed locally

        if source_url and source_url.startswith("http"):

            try:

                import subprocess

                skills_dir = os.path.expanduser("~/.aiplat/skills")

                target = os.path.join(skills_dir, skill_id)

                subprocess.run(["git", "clone", source_url, target],

                               capture_output=True, timeout=30)

            except Exception:

                logging.getLogger(__name__).debug('install failed', exc_info=True)
        return True



    def rate(self, skill_id: str, rating: int, comment: str = "", profile_id: str = "default"):

        if not 1 <= rating <= 5:

            return False

        with self._lock:

            conn = sqlite3.connect(self.db_path)

            now = datetime.now(timezone.utc).isoformat()

            conn.execute(

                "INSERT INTO skill_ratings(skill_id, rating, comment, profile_id, created_at) VALUES(?,?,?,?,?)",

                (skill_id, rating, comment, profile_id, now))

            avg = conn.execute(

                "SELECT AVG(rating) FROM skill_ratings WHERE skill_id=?", (skill_id,)).fetchone()[0]

            count = conn.execute(

                "SELECT COUNT(*) FROM skill_ratings WHERE skill_id=?", (skill_id,)).fetchone()[0]

            conn.execute(

                "UPDATE skill_registry SET rating=?, rating_count=? WHERE skill_id=?",

                (round(avg, 1), count, skill_id))

            conn.commit()

            conn.close()

        return True



    def discover(self, category: str = "", sort_by: str = "rating",

                 limit: int = 20) -> list[dict]:

        order_map = {"rating": "rating DESC", "downloads": "downloads DESC",

                     "newest": "install_date DESC", "name": "name ASC"}

        order = order_map.get(sort_by, "rating DESC")



        with self._lock:

            conn = sqlite3.connect(self.db_path)

            conn.row_factory = sqlite3.Row

            query = "SELECT * FROM skill_registry"

            params: list = []

            if category:

                query += " WHERE category = ?"

                params.append(category)

            query += f" ORDER BY {order} LIMIT ?"

            params.append(limit)

            rows = conn.execute(query, tuple(params)).fetchall()

            conn.close()

            return [dict(r) for r in rows]



    def get_trending(self, limit: int = 10) -> list[dict]:

        with self._lock:

            conn = sqlite3.connect(self.db_path)

            conn.row_factory = sqlite3.Row

            rows = conn.execute(

                "SELECT * FROM skill_registry WHERE installed=1 ORDER BY rating DESC, downloads DESC LIMIT ?",

                (limit,)).fetchall()

            conn.close()

            return [dict(r) for r in rows]



    def get_stats(self) -> dict:

        with self._lock:

            conn = sqlite3.connect(self.db_path)

            conn.row_factory = sqlite3.Row

            total = conn.execute("SELECT COUNT(*) as c FROM skill_registry").fetchone()["c"]

            installed = conn.execute("SELECT COUNT(*) as c FROM skill_registry WHERE installed=1").fetchone()["c"]

            rated = conn.execute("SELECT COUNT(DISTINCT skill_id) as c FROM skill_ratings").fetchone()["c"]

            conn.close()

            return {"total_skills": total, "installed": installed, "rated": rated}

    # ── P1-A5: agentskills.io 开放标准对接 ──────────────────────────

    EXTERNAL_SOURCES = {
        "agentskills.io": "https://agentskills.io/skills/index.json",
    }

    def supports_external_source(self, source: str) -> bool:
        """Whether an external skill source is supported (agentskills.io)."""
        return source in self.EXTERNAL_SOURCES

    def _frontmatter(self, text: str) -> dict:
        """Parse YAML-ish frontmatter from SKILL.md (safe subset)."""
        result = {}
        if not text.startswith("---"):
            return result
        end = text.find("\n---", 3)
        if end < 0:
            return result
        for line in text[3:end].splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                result[k.strip()] = v.strip().strip("'\"")
        return result

    def export_skill(self, skill_id: str, skill_dir: str = "") -> dict:
        """Serialize an aiPlat skill to agentskills.io-compatible format.

        Maps aiPlat SKILL.md frontmatter → agentskills.io metadata.
        aiPlat extensions (effects/permissions) use safe defaults when absent.
        """
        base = skill_dir or os.path.expanduser("~/.aiplat/skills")
        skill_path = os.path.join(base, skill_id, "SKILL.md")
        if not os.path.exists(skill_path):
            return {"error": f"skill not found: {skill_id}"}
        with open(skill_path, encoding="utf-8") as f:
            text = f.read()
        fm = self._frontmatter(text)
        return {
            "name": fm.get("name", skill_id),
            "description": fm.get("description", ""),
            "version": fm.get("version", "1.0.0"),
            "category": fm.get("category", "general"),
            "tags": fm.get("tags", ""),
            "effects": fm.get("effects", "[]"),      # aiPlat extension → default safe
            "permissions": fm.get("permissions", "[]"),
            "agent": fm.get("agent", ""),
            "metadata_format": "agentskills.io",
            "source": "aiplat",
        }

    def discover_external(self, source: str = "agentskills.io",
                          limit: int = 50) -> list[dict]:
        """Discover skills from an external source index (aggregated view).

        Pulls the remote index (network); on failure returns an empty list
        with the error noted (discover is best-effort, never blocks install).
        """
        if not self.supports_external_source(source):
            return [{"error": f"unsupported source: {source}"}]
        index_url = self.EXTERNAL_SOURCES[source]
        try:
            import urllib.request
            with urllib.request.urlopen(index_url, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return [{"error": f"external source unreachable: {str(e)[:100]}"}]
        items = data.get("skills", data if isinstance(data, list) else [])
        return [
            {"name": s.get("name"), "description": s.get("description", ""),
             "version": s.get("version", "1.0.0"), "source": source}
            for s in items[:limit]
        ]

    def install_external(self, skill_id: str, source: str = "agentskills.io",
                         source_url: str = "") -> bool:
        """Install a skill from an external source (git clone fallback)."""
        if source_url:
            return self.install(skill_id, source_url)
        # No direct URL — fail loud rather than guessing
        raise ValueError(
            f"External install requires source_url for '{skill_id}' "
            f"(agentskills.io index provides repo URLs per skill)")






_marketplace: Optional[SkillMarketplace] = None





def get_marketplace() -> SkillMarketplace:

    global _marketplace

    if _marketplace is None:

        _marketplace = SkillMarketplace()

    return _marketplace

