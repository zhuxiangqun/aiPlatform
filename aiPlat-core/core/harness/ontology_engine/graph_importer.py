"""
GraphFileImporter — Import external graph data into GraphIndex.

Supported formats:
  - CSV: rows of (source, target, relation) or (source, target, relation, weight)
  - GraphML: basic node/edge import (XML-based)
  - Edge list: plain text, one edge per line: source -> target [relation]

Usage:
    importer = GraphFileImporter()
    count = importer.import_file("/path/to/graph.csv", domain_id="my-data",
                                  format="csv", source_col=0, target_col=1, relation_col=2)
"""
from __future__ import annotations

import csv
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

logger = logging.getLogger("aiplat.graph_import")


class GraphFileImporter:
    """Import external graph data files into the GraphIndex."""

    def import_file(
        self,
        file_path: str,
        *,
        domain_id: str = "default",
        format: str = "auto",
        source_col: int = 0,
        target_col: int = 1,
        relation_col: Optional[int] = 2,
        delimiter: str = ",",
    ) -> Dict[str, Any]:
        """
        Import a graph file into the knowledge graph.

        Args:
            file_path: Path to the graph data file
            domain_id: Target knowledge domain
            format: "csv" | "graphml" | "edgelist" | "auto" (detect from extension)
            source_col/target_col/relation_col: Column indices for CSV/edge list
            delimiter: Field delimiter for CSV

        Returns:
            { "imported_nodes": int, "imported_edges": int, "errors": [...] }
        """
        if format == "auto":
            format = _detect_format(file_path)

        if not os.path.exists(file_path):
            return {"imported_nodes": 0, "imported_edges": 0, "errors": [f"File not found: {file_path}"]}

        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            graph = GraphIndex(domain_id)

            if format == "csv":
                return self._import_csv(file_path, graph, source_col, target_col, relation_col, delimiter)
            elif format == "graphml":
                return self._import_graphml(file_path, graph)
            elif format == "edgelist":
                return self._import_edgelist(file_path, graph)
            else:
                return {"imported_nodes": 0, "imported_edges": 0, "errors": [f"Unsupported format: {format}"]}
        except Exception as e:
            logger.warning("Graph import failed: %s", e, exc_info=True)
            return {"imported_nodes": 0, "imported_edges": 0, "errors": [str(e)]}

    def _import_csv(
        self, file_path: str, graph,
        source_col: int, target_col: int, relation_col: Optional[int], delimiter: str,
    ) -> Dict[str, Any]:
        """Import from CSV: source,target[,relation]"""
        nodes_added = 0
        edges_added = 0
        errors = []

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f, delimiter=delimiter)
            header = next(reader, None)  # skip header row
            for row_num, row in enumerate(reader, start=2):
                if len(row) < 2:
                    continue
                try:
                    source = row[source_col].strip()
                    target = row[target_col].strip()
                    if not source or not target:
                        continue

                    relation = row[relation_col].strip() if relation_col is not None and len(row) > relation_col else "related_to"

                    # Add nodes if they don't exist
                    sid = graph.add_entity(entity_name=source, class_name="Imported")
                    tid = graph.add_entity(entity_name=target, class_name="Imported")
                    graph.add_relation(sid, tid, relation_name=relation)

                    nodes_added += 2 if sid and tid else 0
                    edges_added += 1
                except Exception as e:
                    errors.append(f"Row {row_num}: {e}")

        graph.save()
        return {"imported_nodes": nodes_added, "imported_edges": edges_added, "errors": errors}

    def _import_graphml(self, file_path: str, graph) -> Dict[str, Any]:
        """Import basic GraphML format."""
        tree = ET.parse(file_path)
        root = tree.getroot()

        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        # Handle default namespace
        if root.tag == "{http://graphml.graphdrawing.org/xmlns}graphml":
            ns = {"g": "http://graphml.graphdrawing.org/xmlns"}

        nodes_added = 0
        edges_added = 0
        node_id_map: Dict[str, str] = {}

        for node_elem in root.findall(".//node") or root.findall(".//g:node", ns):
            nid = node_elem.get("id", "")
            name = nid
            for data_elem in node_elem.findall("data") or node_elem.findall("g:data", ns):
                if data_elem.get("key") in ("label", "name", "d0"):
                    name = (data_elem.text or "").strip() or name
            if name:
                node_id_map[nid] = graph.add_entity(entity_name=name, class_name="Imported")
                nodes_added += 1

        for edge_elem in root.findall(".//edge") or root.findall(".//g:edge", ns):
            src = edge_elem.get("source", "")
            tgt = edge_elem.get("target", "")
            label = edge_elem.get("label", "related_to")
            if src in node_id_map and tgt in node_id_map:
                graph.add_relation(node_id_map[src], node_id_map[tgt], relation_name=label)
                edges_added += 1

        graph.save()
        return {"imported_nodes": nodes_added, "imported_edges": edges_added, "errors": []}

    def _import_edgelist(self, file_path: str, graph) -> Dict[str, Any]:
        """Import from edge list: one line = source -> target [relation]"""
        nodes_added = 0
        edges_added = 0
        pattern = re.compile(r'(.+?)\s*[-=]>+\s*(.+?)(?:\s+\[(.+?)\])?\s*$')

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = pattern.match(line)
                if not m:
                    continue
                source = m.group(1).strip()
                target = m.group(2).strip()
                relation = m.group(3).strip() if m.group(3) else "related_to"

                sid = graph.add_entity(entity_name=source, class_name="Imported")
                tid = graph.add_entity(entity_name=target, class_name="Imported")
                graph.add_relation(sid, tid, relation_name=relation)
                nodes_added += 2
                edges_added += 1

        graph.save()
        return {"imported_nodes": nodes_added, "imported_edges": edges_added, "errors": []}


def _detect_format(file_path: str) -> str:
    """Detect graph file format from extension."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in (".csv", ".tsv"):
        return "csv"
    if ext in (".graphml", ".xml"):
        return "graphml"
    if ext in (".txt", ".edges", ".edgelist"):
        return "edgelist"
    # Check file content for GraphML header
    try:
        with open(file_path, "r") as f:
            head = f.read(200)
        if "<graphml" in head:
            return "graphml"
        if "->" in head or "→" in head:
            return "edgelist"
    except Exception:
        pass
    return "csv"  # default
