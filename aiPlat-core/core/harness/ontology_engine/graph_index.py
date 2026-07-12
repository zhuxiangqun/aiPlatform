"""
Graph Index — bidirectional graph with SQLite persistence + incremental writes.

Architecture:
  - In-memory _nodes dict for fast queries (populated from SQL on load)
  - SQLite backend for incremental INSERT/UPDATE/DELETE
  - JSON export for backward compatibility
  - Primary key: (domain_id, entity_id) for nodes

Persists to ~/.aiplat/graph/{domain_id}.db (SQLite)
Exports to ~/.aiplat/graph/{domain_id}.json (optional, backward compat)
"""

from __future__ import annotations
import logging

import json as _json
import os as _os
import sqlite3 as _sqlite3
import time as _time
from dataclasses import dataclass, field
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional


@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    relation_name: str
    relation_label: str = ""
    confidence: float = 1.0
    inferred: bool = False
    rule_name: str = ""
    inferred_confidence: float = 1.0
    context_description: str = ""  # Natural language description of this relationship
    embedding: Optional[List[float]] = None  # Per-relation embedding vector


@dataclass
class GraphNode:
    entity_id: str
    entity_name: str
    class_name: str
    source_doc_id: str = ""           # KB document ID this entity was extracted from
    out_edges: List[GraphEdge] = field(default_factory=list)
    in_edges: List[GraphEdge] = field(default_factory=list)


@dataclass
class HyperEdge:
    """An N-ary relationship connecting one event to multiple entities.

    SAG-style hyperedge: a complete event description that binds together
    all related entities, preserving full context instead of splitting
    into fragmented triples.

    Example:
      event: "RAGChat is an enterprise Q&A system handling 5000+ queries/day"
      entity_ids: ["RAG", "RAGChat", "客服自动化"]
    """
    event_id: str                          # unique event identifier
    entity_ids: List[str] = field(default_factory=list)  # connected entities
    context_description: str = ""          # full event description (SAG event card)
    embedding: Optional[List[float]] = None  # per-hyperedge embedding
    confidence: float = 1.0
    source_chunk_id: str = ""              # originating chunk (for traceability)


class GraphIndex:
    """Bidirectional graph with SQLite persistence and incremental writes."""

    def __init__(self, domain_id: str):
        self.domain_id = domain_id
        self._nodes: Dict[str, GraphNode] = {}
        self._hyperedges: Dict[str, HyperEdge] = {}
        home = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat"))
        db_dir = home / "graph"
        db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = db_dir / f"{domain_id}.db"
        self._json_path = db_dir / f"{domain_id}.json"
        self._conn: Optional[_sqlite3.Connection] = None

    def _get_conn(self) -> _sqlite3.Connection:
        if self._conn is None:
            self._conn = _sqlite3.connect(str(self._db_path))
            self._ensure_schema()
        return self._conn

    def _ensure_schema(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                domain_id TEXT NOT NULL DEFAULT '',
                entity_id TEXT NOT NULL,
                entity_name TEXT NOT NULL DEFAULT '',
                class_name TEXT NOT NULL DEFAULT '',
                source_doc_id TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (domain_id, entity_id)
            )
        """)
        # Phase E1: migration — add source_doc_id to existing tables
        try:
            conn.execute("ALTER TABLE graph_nodes ADD COLUMN source_doc_id TEXT NOT NULL DEFAULT ''")
        except _sqlite3.OperationalError:
            pass  # Column already exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain_id TEXT NOT NULL DEFAULT '',
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation_name TEXT NOT NULL DEFAULT '',
                relation_label TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 1.0,
                inferred INTEGER NOT NULL DEFAULT 0,
                rule_name TEXT NOT NULL DEFAULT '',
                inferred_confidence REAL NOT NULL DEFAULT 1.0,
                context_desc TEXT NOT NULL DEFAULT '',
                embedding TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_src ON graph_edges(domain_id, source_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_tgt ON graph_edges(domain_id, target_id)")
        # Migrate: add new columns if missing
        try:
            conn.execute("ALTER TABLE graph_edges ADD COLUMN context_desc TEXT NOT NULL DEFAULT ''")
        except _sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE graph_edges ADD COLUMN embedding TEXT NOT NULL DEFAULT ''")
        except _sqlite3.OperationalError:
            pass
        conn.commit()

    # ── Mutators ──────────────────────────────────────────────────

    def add_entity(self, entity_id: str, entity_name: str, class_name: str, *, source_doc_id: str = "") -> GraphNode:
        """Register a node (idempotent — returns existing if present).

        Q: Validates class_name against domain YAML — unknown classes log a warning.
        
        Args:
            source_doc_id: KB document ID for traceability (Phase E1)
        """
        if entity_id not in self._nodes:
            # Q: Schema validation — check class exists in domain YAML
            known = self._load_class_labels()
            if known and class_name and class_name not in known:
                logging.warning(
                    "GraphIndex[%s]: entity '%s' uses unknown class '%s'. "
                    "Known classes: %s. Add this class to %s.yaml or correct the class_name.",
                    self.domain_id, entity_name[:60], class_name,
                    ", ".join(sorted(list(known))[:10]),
                    self.domain_id,
                )

            self._nodes[entity_id] = GraphNode(
                entity_id=entity_id,
                entity_name=entity_name,
                class_name=class_name,
                source_doc_id=source_doc_id,
            )
            conn = self._get_conn()
            conn.execute(
                "INSERT OR REPLACE INTO graph_nodes(domain_id, entity_id, entity_name, class_name, source_doc_id) VALUES (?,?,?,?,?)",
                (self.domain_id, entity_id, entity_name, class_name, source_doc_id),
            )
            conn.commit()
            self._invalidate_cache()
        return self._nodes[entity_id]

    def add_relation(
        self,
        source_id: str,
        target_id: str,
        relation_name: str,
        *,
        relation_label: str = "",
        confidence: float = 1.0,
        inverse_name: str = "",
        inverse_label: str = "",
        inferred: bool = False,
        rule_name: str = "",
    ) -> None:
        """Add a directed edge. Creates out_edge on source and in_edge on target.
        Writes to SQLite incrementally.

        Validates domain/range constraints from the domain YAML's object_properties.
        Relations violating constraints get confidence reduced to 0.3.
        """
        if source_id not in self._nodes or target_id not in self._nodes:
            return

        src_class = self._nodes[source_id].class_name
        tgt_class = self._nodes[target_id].class_name

        # N: Relation domain/range constraint validation
        if src_class and tgt_class:
            constraints = self._load_property_constraints()
            if relation_name in constraints:
                allowed_src = constraints[relation_name]["domain"]
                allowed_tgt = constraints[relation_name]["range"]
                src_ok = not allowed_src or src_class in allowed_src
                tgt_ok = not allowed_tgt or tgt_class in allowed_tgt
                if not (src_ok and tgt_ok):
                    logging.warning(
                        "Relation constraint violation: %s(%s→%s) not in domain[%s]×range[%s]. "
                        "Confidence reduced to 0.3.",
                        relation_name, src_class, tgt_class,
                        ",".join(allowed_src or []), ",".join(allowed_tgt or []),
                    )
                    confidence = min(confidence, 0.3)

        self._add_edge_internal(
            source_id, target_id, relation_name,
            relation_label=relation_label, confidence=confidence,
            inferred=inferred, rule_name=rule_name,
        )
        if inverse_name:
            self._add_edge_internal(
                target_id, source_id, inverse_name,
                relation_label=inverse_label or inverse_name, confidence=confidence,
                inferred=inferred, rule_name=rule_name,
            )
        self._invalidate_cache()

    def _add_edge_internal(
        self, src: str, tgt: str, rname: str, *,
        relation_label: str = "", confidence: float = 1.0,
        inferred: bool = False, rule_name: str = "",
    ):
        edge = GraphEdge(
            source_id=src, target_id=tgt,
            relation_name=rname, relation_label=relation_label or rname,
            confidence=confidence, inferred=inferred,
            rule_name=rule_name, inferred_confidence=confidence,
        )
        self._nodes[src].out_edges.append(edge)
        self._nodes[tgt].in_edges.append(edge)
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO graph_edges(domain_id, source_id, target_id, relation_name,
               relation_label, confidence, inferred, rule_name, inferred_confidence, context_desc, embedding)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (self.domain_id, src, tgt, rname, relation_label or rname,
             confidence, int(inferred), rule_name, confidence,
             getattr(edge, 'context_description', ''),
             _json.dumps(getattr(edge, 'embedding', None) or [])),
        )
        conn.commit()
        self._invalidate_cache()

    def add_inferred_edge(
        self, source_id: str, target_id: str, relation_name: str, *,
        relation_label: str = "", confidence: float = 1.0, rule_name: str = "",
    ) -> bool:
        """Add an inferred edge. Skips if duplicate exists. Returns True if added."""
        if source_id not in self._nodes or target_id not in self._nodes:
            return False
        src = self._nodes[source_id]
        exists = any(
            e.relation_name == relation_name and e.target_id == target_id
            and getattr(e, "inferred", False)
            for e in src.out_edges
        )
        if exists:
            return False
        self._add_edge_internal(
            source_id, target_id, relation_name,
            relation_label=relation_label, confidence=confidence,
            inferred=True, rule_name=rule_name,
        )
        return True

    def remove_inferred_edges(self) -> int:
        """Remove all inferred edges. Returns count removed."""
        removed = 0
        for node in self._nodes.values():
            out_before = len(node.out_edges)
            in_before = len(node.in_edges)
            node.out_edges = [e for e in node.out_edges if not getattr(e, "inferred", False)]
            node.in_edges = [e for e in node.in_edges if not getattr(e, "inferred", False)]
            removed += (out_before - len(node.out_edges)) + (in_before - len(node.in_edges))
        conn = self._get_conn()
        conn.execute("DELETE FROM graph_edges WHERE domain_id=? AND inferred=1", (self.domain_id,))
        conn.commit()
        return removed

    def set_edge_context(self, source_id: str, target_id: str, relation_name: str, *,
                         context_description: str = "") -> bool:
        """Set a human-readable context description for an edge.

        Example: "RAG implements RAGChat as an enterprise Q&A system handling 5000+ queries/day"
        """
        node = self._nodes.get(source_id)
        if not node:
            return False
        for e in node.out_edges:
            if e.target_id == target_id and e.relation_name == relation_name:
                e.context_description = context_description
                conn = self._get_conn()
                conn.execute(
                    "UPDATE graph_edges SET context_desc=? WHERE domain_id=? AND source_id=? AND target_id=? AND relation_name=?",
                    (context_description, self.domain_id, source_id, target_id, relation_name),
                )
                conn.commit()
                return True
        return False

    def set_edge_embedding(self, source_id: str, target_id: str, relation_name: str, *,
                           embedding: List[float]) -> bool:
        """Set a per-relation embedding vector. Stored as JSON in SQLite."""
        node = self._nodes.get(source_id)
        if not node:
            return False
        for e in node.out_edges:
            if e.target_id == target_id and e.relation_name == relation_name:
                e.embedding = list(embedding)
                conn = self._get_conn()
                conn.execute(
                    "UPDATE graph_edges SET embedding=? WHERE domain_id=? AND source_id=? AND target_id=? AND relation_name=?",
                    (_json.dumps(list(embedding)), self.domain_id, source_id, target_id, relation_name),
                )
                conn.commit()
                return True
        return False

    def remove_entity(self, entity_id: str) -> bool:
        """Remove a node and all its edges. Incremental DELETE."""
        if entity_id not in self._nodes:
            return False
        del self._nodes[entity_id]
        conn = self._get_conn()
        conn.execute("DELETE FROM graph_edges WHERE domain_id=? AND (source_id=? OR target_id=?)",
                     (self.domain_id, entity_id, entity_id))
        conn.execute("DELETE FROM graph_nodes WHERE domain_id=? AND entity_id=?",
                     (self.domain_id, entity_id))
        conn.commit()
        self._invalidate_cache()
        return True

    # ── HyperEdge Operations ──────────────────────────────────────

    def add_hyperedge(
        self,
        event_id: str,
        entity_ids: List[str],
        *,
        context_description: str = "",
        confidence: float = 1.0,
        source_chunk_id: str = "",
    ) -> HyperEdge:
        """Create a SAG-style hyperedge: one event connecting multiple entities.

        The hyperedge preserves full context — unlike triples which fragment an
        event into many small pieces. All connected entities can reach each other
        via get_hyperedge_neighbors().

        Args:
            event_id: unique identifier for this event (e.g. chunk_id)
            entity_ids: list of entity IDs connected by this event
            context_description: full event description (SAG event card)
            confidence: extraction confidence
            source_chunk_id: originating document chunk
        """
        if event_id in self._hyperedges:
            return self._hyperedges[event_id]

        he = HyperEdge(
            event_id=event_id,
            entity_ids=list(entity_ids),
            context_description=context_description,
            confidence=confidence,
            source_chunk_id=source_chunk_id,
        )
        self._hyperedges[event_id] = he

        # Persist to SQL
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_hyperedges (
                event_id TEXT NOT NULL,
                domain_id TEXT NOT NULL DEFAULT '',
                entity_ids TEXT NOT NULL DEFAULT '[]',
                context_description TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 1.0,
                source_chunk_id TEXT NOT NULL DEFAULT '',
                embedding TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (domain_id, event_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_he_domain ON graph_hyperedges(domain_id)")
        conn.execute(
            """INSERT OR REPLACE INTO graph_hyperedges
               (event_id, domain_id, entity_ids, context_description, confidence, source_chunk_id)
               VALUES (?,?,?,?,?,?)""",
            (event_id, self.domain_id, _json.dumps(entity_ids),
             context_description, confidence, source_chunk_id),
        )
        conn.commit()
        self._invalidate_cache()
        return he

    def get_hyperedge(self, event_id: str) -> Optional[HyperEdge]:
        return self._hyperedges.get(event_id)

    def get_hyperedge_neighbors(
        self,
        entity_id: str,
        *,
        direction: str = "all",
    ) -> List[GraphNode]:
        """Get entities reachable via hyperedges from a given entity.

        All entities in the same hyperedge are fully connected to each other.
        This is the SAG-style "local hyperedge expansion" — no global traversal.

        Args:
            entity_id: starting entity
            direction: "all" (default) — all entities in shared hyperedges
        """
        neighbors: Dict[str, GraphNode] = {}
        for he in self._hyperedges.values():
            if entity_id in he.entity_ids:
                for eid in he.entity_ids:
                    if eid != entity_id and eid in self._nodes:
                        neighbors[eid] = self._nodes[eid]
        return list(neighbors.values())

    def get_hyperedges_for_entity(self, entity_id: str) -> List[HyperEdge]:
        """Get all hyperedges that contain the given entity."""
        return [he for he in self._hyperedges.values() if entity_id in he.entity_ids]

    def remove_hyperedge(self, event_id: str) -> bool:
        if event_id not in self._hyperedges:
            return False
        del self._hyperedges[event_id]
        conn = self._get_conn()
        conn.execute("DELETE FROM graph_hyperedges WHERE domain_id=? AND event_id=?",
                     (self.domain_id, event_id))
        conn.commit()
        self._invalidate_cache()
        return True

    # ── Edge Operations (binary) ──────────────────────────────────

    def add_relations_batch(
        self, relations: List[Dict[str, Any]], *, domain,
    ) -> int:
        """Batch-add relations from RelationMapper output."""
        added = 0
        prop_map = {getattr(p, "name", ""): p for p in getattr(domain, "object_properties", [])}
        for p in getattr(domain, "object_properties", []):
            short = getattr(p, "uri", "").rsplit("#", 1)[-1].rsplit("/", 1)[-1]
            if short:
                prop_map[short] = p
        for rel in relations:
            src = str(rel.get("source", "") or rel.get("source_id", ""))
            tgt = str(rel.get("target", "") or rel.get("target_id", ""))
            rname = str(rel.get("relation", "") or rel.get("relation_name", ""))
            conf = float(rel.get("confidence", 1.0))
            if not src or not tgt or not rname:
                continue
            prop = prop_map.get(rname)
            label = getattr(prop, "label", "") if prop else rname
            inv_name = getattr(prop, "inverse_label", "") if prop else ""
            inv_label = getattr(prop, "label", "") if prop and inv_name else ""
            if src not in self._nodes:
                self.add_entity(src, src, "")
            if tgt not in self._nodes:
                self.add_entity(tgt, tgt, "")
            self.add_relation(
                source_id=src, target_id=tgt, relation_name=rname,
                relation_label=label, confidence=conf,
                inverse_name=inv_name, inverse_label=inv_label,
            )
            added += 1
        return added

    # ── Queries ────────────────────────────────────────────────────

    def get_node(self, entity_id: str) -> Optional[GraphNode]:
        return self._nodes.get(entity_id)

    def find_by_name(self, name: str) -> Optional[GraphNode]:
        nl = name.lower()
        for node in self._nodes.values():
            if node.entity_name.lower() == nl:
                return node
        return None

    def get_neighbors(
        self, entity_id: str, *,
        direction: str = "outgoing",
        relation_filter: Optional[List[str]] = None,
    ) -> List[GraphNode]:
        node = self._nodes.get(entity_id)
        if not node:
            return []
        neighbors: Dict[str, GraphNode] = {}
        def _collect(edges):
            for e in edges:
                if relation_filter and e.relation_name not in relation_filter:
                    continue
                nid = e.target_id if direction != "incoming" else e.source_id
                if nid == entity_id:
                    nid = e.source_id if direction == "incoming" else e.target_id
                if nid in self._nodes:
                    neighbors[nid] = self._nodes[nid]
        if direction in ("outgoing", "both"):
            _collect(node.out_edges)
        if direction in ("incoming", "both"):
            _collect(node.in_edges)
        return list(neighbors.values())

    def get_inverse_relations(self, entity_id: str) -> List[GraphEdge]:
        node = self._nodes.get(entity_id)
        return list(node.in_edges) if node else []

    # ── Persistence ────────────────────────────────────────────────

    def save(self, *, export_json: bool = True) -> str:
        """Sync in-memory to SQLite (commit). Optionally export JSON."""
        if self._conn:
            self._conn.commit()
        if export_json:
            self._export_json()
        return str(self._db_path)

    def _export_json(self) -> str:
        """Export current graph to JSON (backward compat)."""
        data = {
            "domain_id": self.domain_id,
            "saved_at": _time.time(),
            "nodes": {},
        }
        for nid, node in self._nodes.items():
            data["nodes"][nid] = {
                "entity_id": node.entity_id,
                "entity_name": node.entity_name,
                "class_name": node.class_name,
                "out_edges": [{
                    "source_id": e.source_id, "target_id": e.target_id,
                    "relation_name": e.relation_name, "relation_label": e.relation_label,
                    "confidence": e.confidence, "inferred": getattr(e, "inferred", False),
                    "rule_name": getattr(e, "rule_name", ""),
                    "inferred_confidence": getattr(e, "inferred_confidence", 1.0),
                } for e in node.out_edges],
            }
        self._json_path.write_text(_json.dumps(data, ensure_ascii=False, indent=2))
        return str(self._json_path)

    @classmethod
    def load(cls, domain_id: str) -> GraphIndex:
        """Load graph from SQLite first, fall back to JSON."""
        graph = cls(domain_id)

        # Try SQLite first
        conn = graph._get_conn()
        rows = conn.execute(
            "SELECT entity_id, entity_name, class_name FROM graph_nodes WHERE domain_id=?",
            (domain_id,),
        ).fetchall()

        if rows:
            # Load nodes from SQL
            for entity_id, entity_name, class_name in rows:
                graph._nodes[entity_id] = GraphNode(
                    entity_id=entity_id, entity_name=entity_name, class_name=class_name,
                )
            # Load edges from SQL
            edge_rows = conn.execute(
                """SELECT source_id, target_id, relation_name, relation_label,
                          confidence, inferred, rule_name, inferred_confidence,
                          context_desc, embedding
                   FROM graph_edges WHERE domain_id=?""",
                (domain_id,),
            ).fetchall()
            for src, tgt, rn, rl, conf, inf, rule, inf_conf, ctx_desc, emb_json in edge_rows:
                if src in graph._nodes and tgt in graph._nodes:
                    edge = GraphEdge(
                        source_id=src, target_id=tgt,
                        relation_name=rn, relation_label=rl,
                        confidence=conf, inferred=bool(inf),
                        rule_name=rule, inferred_confidence=inf_conf,
                        context_description=ctx_desc or "",
                    )
                    if emb_json:
                        try:
                            edge.embedding = _json.loads(emb_json)
                        except Exception as e:
                            logging.debug(str(e), exc_info=True)
                    graph._nodes[src].out_edges.append(edge)
                    graph._nodes[tgt].in_edges.append(edge)
            # Load hyperedges from SQL
            try:
                he_rows = conn.execute(
                    """SELECT event_id, entity_ids, context_description, confidence,
                              source_chunk_id, embedding
                       FROM graph_hyperedges WHERE domain_id=?""",
                    (domain_id,),
                ).fetchall()
                for ev_id, ent_json, ctx_desc, conf, chunk_id, emb_json in he_rows:
                    try:
                        entity_ids = _json.loads(ent_json)
                    except Exception:
                        entity_ids = []
                    he = HyperEdge(
                        event_id=ev_id, entity_ids=entity_ids,
                        context_description=ctx_desc or "",
                        confidence=conf, source_chunk_id=chunk_id or "",
                    )
                    if emb_json:
                        try:
                            he.embedding = _json.loads(emb_json)
                        except Exception as e:
                            logging.debug(str(e), exc_info=True)
                    graph._hyperedges[ev_id] = he
            except _sqlite3.OperationalError:
                pass  # Table doesn't exist yet (pre-migration)
            return graph

        # Fallback to JSON
        if graph._json_path.exists():
            try:
                data = _json.loads(graph._json_path.read_text())
            except Exception:
                return graph
            raw_nodes = data.get("nodes", {})
            for nid, nd in raw_nodes.items():
                graph._nodes[nid] = GraphNode(
                    entity_id=nd.get("entity_id", nid),
                    entity_name=nd.get("entity_name", ""),
                    class_name=nd.get("class_name", ""),
                )
            for nid, nd in raw_nodes.items():
                for ed in nd.get("out_edges", []):
                    src, tgt = ed.get("source_id", ""), ed.get("target_id", "")
                    if src and tgt and src in graph._nodes and tgt in graph._nodes:
                        edge = GraphEdge(
                            source_id=src, target_id=tgt,
                            relation_name=ed.get("relation_name", ""),
                            relation_label=ed.get("relation_label", ""),
                            confidence=ed.get("confidence", 1.0),
                        )
                        edge.inferred = ed.get("inferred", False)
                        edge.rule_name = ed.get("rule_name", "")
                        edge.inferred_confidence = ed.get("inferred_confidence", 1.0)
                        graph._nodes[src].out_edges.append(edge)
                        graph._nodes[tgt].in_edges.append(edge)
            # Migrate to SQL
            graph.save(export_json=False)
        return graph

    # ── Stats ──────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        node_count = len(self._nodes)
        edge_count = sum(len(n.out_edges) for n in self._nodes.values())
        return {
            "domain_id": self.domain_id,
            "node_count": node_count,
            "edge_count": edge_count,
            "avg_degree": round(edge_count / node_count, 2) if node_count else 0,
        }

    # ── N: Relation domain/range constraint loader ──────────────────

    def _load_property_constraints(self) -> Dict[str, Dict[str, List[str]]]:
        """Load domain/range constraints from the domain YAML's object_properties.

        Returns: {relation_name: {"domain": [...], "range": [...]}}
        Cached per instance for performance.
        """
        if hasattr(self, '_prop_constraints_cache'):
            return getattr(self, '_prop_constraints_cache')

        constraints = {}
        try:
            import os
            path = os.path.expanduser(f"~/.aiplat/ontologies/{self.domain_id}.yaml")
            if os.path.exists(path):
                from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
                dom = load_ontology_from_yaml(path)
                for prop in dom.object_properties:
                    uri = getattr(prop, 'uri', '') or ''
                    name = uri.rsplit('/', 1)[-1] if '/' in uri else uri
                    domain = list(getattr(prop, 'domain', []) or [])
                    # Resolve domain/range URIs to short class names
                    domain_short = [d.rsplit('/', 1)[-1] for d in domain if '/' in d]
                    range_uri = list(getattr(prop, 'range', []) or [])
                    range_short = [r.rsplit('/', 1)[-1] for r in range_uri if '/' in r]
                    if name and (domain_short or range_short):
                        constraints[name] = {"domain": domain_short, "range": range_short}
        except Exception:
            pass

        setattr(self, '_prop_constraints_cache', constraints)
        return constraints

    def _load_class_labels(self) -> set:
        """Load known class labels from the domain YAML for schema validation. (Q)

        Returns: set of class label strings or empty set if YAML unavailable.
        Cached per instance.
        """
        if hasattr(self, '_class_labels_cache'):
            return getattr(self, '_class_labels_cache')

        labels = set()
        try:
            import os
            path = os.path.expanduser(f"~/.aiplat/ontologies/{self.domain_id}.yaml")
            if os.path.exists(path):
                from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
                dom = load_ontology_from_yaml(path)
                for cls in dom.classes:
                    labels.add(cls.label)
        except Exception:
            pass

        setattr(self, '_class_labels_cache', labels)
        return labels

    def _invalidate_cache(self):
        """Invalidate traversal cache on graph mutation."""
        try:
            from core.harness.ontology_engine.traversal_cache import get_traversal_cache
            get_traversal_cache(self.domain_id).invalidate()
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    # ── Graph Snapshots (versioning + rollback) ────────────────────

    def snapshot(self, label: str = "") -> Dict[str, Any]:
        """Save a versioned snapshot of current graph state."""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain_id TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                timestamp REAL NOT NULL,
                data TEXT NOT NULL
            )
        """)
        conn.commit()
        ts = _time.time()
        data = _json.dumps({
            "nodes": {nid: {"entity_id": n.entity_id, "entity_name": n.entity_name, "class_name": n.class_name}
                      for nid, n in self._nodes.items()},
            "edges": [
                {"source": e.source_id, "target": e.target_id, "relation": e.relation_name,
                 "label": e.relation_label, "confidence": e.confidence, "inferred": getattr(e,"inferred",False)}
                for n in self._nodes.values() for e in n.out_edges
            ],
            "hyperedges": {
                hid: {"event_id": he.event_id, "entity_ids": he.entity_ids,
                      "context_description": he.context_description}
                for hid, he in self._hyperedges.items()
            },
        }, ensure_ascii=False)
        conn.execute(
            "INSERT INTO graph_snapshots(domain_id, label, timestamp, data) VALUES (?,?,?,?)",
            (self.domain_id, label or f"snap_{_time.strftime('%m%d_%H%M%S')}", ts, data),
        )
        conn.commit()
        return {"id": conn.execute("SELECT last_insert_rowid()").fetchone()[0], "label": label, "timestamp": ts}

    def list_snapshots(self, limit: int = 20) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, label, timestamp FROM graph_snapshots WHERE domain_id=? ORDER BY timestamp DESC LIMIT ?",
            (self.domain_id, limit),
        ).fetchall()
        return [{"id": r[0], "label": r[1], "timestamp": r[2]} for r in rows]

    def restore_snapshot(self, snapshot_id: int) -> Dict[str, Any]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT data, label, timestamp FROM graph_snapshots WHERE id=? AND domain_id=?",
            (snapshot_id, self.domain_id),
        ).fetchone()
        if not row:
            raise ValueError(f"Snapshot {snapshot_id} not found")
        data = _json.loads(row[0])
        self._nodes.clear()
        self._hyperedges.clear()
        for nid, nd in data.get("nodes", {}).items():
            self._nodes[nid] = GraphNode(entity_id=nd["entity_id"], entity_name=nd["entity_name"], class_name=nd["class_name"])
        for ed in data.get("edges", []):
            if ed["source"] in self._nodes and ed["target"] in self._nodes:
                edge = GraphEdge(source_id=ed["source"], target_id=ed["target"], relation_name=ed["relation"], relation_label=ed.get("label",""), confidence=ed.get("confidence",1.0))
                edge.inferred = ed.get("inferred", False)
                self._nodes[ed["source"]].out_edges.append(edge)
                self._nodes[ed["target"]].in_edges.append(edge)
        from core.harness.ontology_engine.graph_index import HyperEdge
        for hid, hd in data.get("hyperedges", {}).items():
            self._hyperedges[hid] = HyperEdge(event_id=hd["event_id"], entity_ids=hd["entity_ids"], context_description=hd.get("context_description",""))
        self.save(export_json=False)
        self._invalidate_cache()
        return {"restored_snapshot_id": snapshot_id, "label": row[1], "timestamp": row[2],
                "nodes": len(self._nodes), "edges": sum(len(n.out_edges) for n in self._nodes.values())}

    def compare_snapshots(self, id_a: int, id_b: int) -> Dict[str, Any]:
        conn = self._get_conn()
        a_row = conn.execute("SELECT data FROM graph_snapshots WHERE id=?", (id_a,)).fetchone()
        b_row = conn.execute("SELECT data FROM graph_snapshots WHERE id=?", (id_b,)).fetchone()
        if not a_row or not b_row:
            return {"error": "snapshot not found"}
        a = _json.loads(a_row[0])
        b = _json.loads(b_row[0])
        a_nodes = set(a.get("nodes", {}).keys())
        b_nodes = set(b.get("nodes", {}).keys())
        a_edges = {(e["source"], e["target"], e["relation"]) for e in a.get("edges", [])}
        b_edges = {(e["source"], e["target"], e["relation"]) for e in b.get("edges", [])}
        return {
            "nodes_added": list(b_nodes - a_nodes),
            "nodes_removed": list(a_nodes - b_nodes),
            "edges_added": len(b_edges - a_edges),
            "edges_removed": len(a_edges - b_edges),
        }

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, entity_id: str) -> bool:
        return entity_id in self._nodes
