"""
Entity Resolver — Context-aware entity disambiguation and merging.

Three-layer strategy:
  L1: String normalization + edit distance  (weight 0.4)
  L2: Co-occurrence context similarity      (weight 0.3)
  L3: Structural context match              (weight 0.3)

Merge threshold: total_score >= 0.7
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ResolveResult:
    merged: List[Dict[str, Any]] = field(default_factory=list)
    merge_map: Dict[str, str] = field(default_factory=dict)  # {old_name → canonical_name}
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "merged_count": len(self.merged),
            "merge_map": self.merge_map,
            "stats": self.stats,
        }


class EntityResolver:
    """Context-aware entity disambiguation."""

    # Fullwidth → halfwidth mapping
    _FW_MAP = str.maketrans(
        "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    )

    def __init__(self, domain=None):
        self._domain = domain
        self._doc_type = ""

    # ── Public API ──────────────────────────────────────────────────

    def resolve(
        self,
        instances: List[Dict[str, Any]],
        *,
        doc_type: str = "",
        heading_context: Optional[Dict[str, str]] = None,
        mode: str = "strict",
    ) -> ResolveResult:
        """Merge duplicate entities across instances.

        Args:
            instances: list of {class_name, entity_text, properties, chunk_id, ...}
            doc_type: document format (e.g., "md", "pdf")
            heading_context: optional {entity_text → heading_path_str}
            mode: "strict" (3-layer scoring, current) | "lazy" (conservative, SAG-style)

        Lazy mode (SAG-style): only merge if same class + normalized name match +
        same source chunk. Defers hard disambiguation to query time when more
        context is available. This prevents premature merging of distinct entities
        that happen to have similar names.
        """
        if mode == "lazy":
            return self._resolve_lazy(instances, doc_type)
        return self._resolve_strict(instances, doc_type, heading_context)

    def _resolve_strict(
        self,
        instances: List[Dict[str, Any]],
        doc_type: str,
        heading_context: Optional[Dict[str, str]],
    ) -> ResolveResult:
        """3-layer disambiguation: L1 edit distance + L2 co-occurrence + L3 context."""
        self._doc_type = doc_type
        result = ResolveResult()
        total = len(instances)
        merged_out: List[Dict[str, Any]] = []
        used_indices: set = set()

        for i, inst_a in enumerate(instances):
            if i in used_indices:
                continue
            best_match_idx = -1
            best_score = 0.0

            for j, inst_b in enumerate(instances):
                if j <= i or j in used_indices:
                    continue
                if inst_a.get("class_name") != inst_b.get("class_name"):
                    continue  # Only merge same-class entities

                name_a = str(inst_a.get("entity_text", "") or inst_a.get("properties", {}).get("name", ""))
                name_b = str(inst_b.get("entity_text", "") or inst_b.get("properties", {}).get("name", ""))

                score = self._score_pair(name_a, name_b, inst_a, inst_b, heading_context)
                if score > best_score:
                    best_score = score
                    best_match_idx = j

            if best_score >= 0.60 and best_match_idx >= 0:
                inst_b = instances[best_match_idx]
                name_a = str(inst_a.get("entity_text", "") or inst_a.get("properties", {}).get("name", ""))
                name_b = str(inst_b.get("entity_text", "") or inst_b.get("properties", {}).get("name", ""))
                # Pick longer name as canonical
                canonical = name_a if len(name_a) >= len(name_b) else name_b
                merged_inst = dict(inst_a)
                merged_inst["entity_text"] = canonical
                if "properties" in merged_inst:
                    merged_inst["properties"]["name"] = canonical
                # Merge tags, properties, etc.
                for key in ("tags",):
                    vals_a = inst_a.get("frontmatter", {}).get(key, []) or []
                    vals_b = inst_b.get("frontmatter", {}).get(key, []) or []
                    merged_set = list(set(vals_a + vals_b))
                    merged_inst.setdefault("frontmatter", {})[key] = merged_set

                result.merge_map[name_b] = canonical
                result.merge_map[name_a] = canonical
                merged_out.append(merged_inst)
                used_indices.add(i)
                used_indices.add(best_match_idx)
            else:
                merged_out.append(inst_a)
                used_indices.add(i)

        result.merged = merged_out
        result.stats = {
            "total": total,
            "merged": total - len(merged_out),
            "unique": len(merged_out),
            "merge_threshold": 0.6,
        }
        return result

    def _resolve_lazy(
        self,
        instances: List[Dict[str, Any]],
        doc_type: str,
    ) -> ResolveResult:
        """SAG-style conservative dedup: only merge exact-normalized matches in same source.

        At ingest time, keep entities separate even if similar. They can be
        connected later via hyperedges or vector retrieval at query time.
        """
        result = ResolveResult()
        total = len(instances)
        merged_out: List[Dict[str, Any]] = []
        used_indices: set = set()

        for i, inst_a in enumerate(instances):
            if i in used_indices:
                continue
            best_j = -1
            name_a = str(inst_a.get("entity_text", "") or inst_a.get("properties", {}).get("name", ""))
            norm_a = self.normalize(name_a)
            cls_a = inst_a.get("class_name", "")
            chunk_a = str(inst_a.get("chunk_id", ""))

            for j, inst_b in enumerate(instances):
                if j <= i or j in used_indices:
                    continue
                if inst_b.get("class_name") != cls_a:
                    continue
                name_b = str(inst_b.get("entity_text", "") or inst_b.get("properties", {}).get("name", ""))
                norm_b = self.normalize(name_b)
                chunk_b = str(inst_b.get("chunk_id", ""))
                # Lazy: only merge if exact normalized match AND same source chunk
                if norm_a == norm_b and chunk_a and chunk_b and chunk_a == chunk_b:
                    best_j = j
                    break

            if best_j >= 0:
                inst_b = instances[best_j]
                canonical = name_a if len(name_a) >= len(inst_b.get("entity_text", "")) else inst_b.get("entity_text", "")
                merged_inst = dict(inst_a)
                merged_inst["entity_text"] = canonical
                if "properties" in merged_inst:
                    merged_inst["properties"]["name"] = canonical
                result.merge_map[inst_b.get("entity_text", "")] = canonical
                result.merge_map[name_a] = canonical
                merged_out.append(merged_inst)
                used_indices.add(i)
                used_indices.add(best_j)
            else:
                merged_out.append(inst_a)
                used_indices.add(i)

        result.merged = merged_out
        result.stats = {
            "total": total,
            "merged": total - len(merged_out),
            "unique": len(merged_out),
            "merge_threshold": "lazy (exact normalized + same source)",
        }
        return result

    # ── Scoring ─────────────────────────────────────────────────────

    def _score_pair(
        self,
        name_a: str,
        name_b: str,
        inst_a: Dict[str, Any],
        inst_b: Dict[str, Any],
        heading_context: Optional[Dict[str, str]],
    ) -> float:
        score = 0.0

        # L1: String normalization + edit distance (0.4)
        norm_a = self.normalize(name_a)
        norm_b = self.normalize(name_b)
        ed = self._edit_distance(norm_a, norm_b)
        if norm_a == norm_b:
            score += 0.40  # Exact match after normalization
        elif ed <= 1:
            score += 0.38
        elif ed <= 2:
            score += 0.32
        elif ed <= 3:
            score += 0.18

        # L2: Co-occurrence context (0.3)
        chunk_a = str(inst_a.get("chunk_id", ""))
        chunk_b = str(inst_b.get("chunk_id", ""))
        if chunk_a and chunk_b and chunk_a == chunk_b:
            score += 0.30  # Same chunk → likely the same entity

        # L3: Structural context (0.3)
        if heading_context:
            hc_a = heading_context.get(name_a, "")
            hc_b = heading_context.get(name_b, "")
            if hc_a and hc_b and hc_a == hc_b:
                score += 0.15  # Same heading path
        if self._doc_type:
            score += 0.15  # Same document type

        return min(score, 1.0)

    # ── String utilities ────────────────────────────────────────────

    @classmethod
    def normalize(cls, text: str) -> str:
        """Normalize text: fullwidth→halfwidth, strip, lowercase."""
        t = str(text).translate(cls._FW_MAP)
        t = "".join(c for c in t if not c.isspace() or c == " ")
        t = " ".join(t.split())  # Collapse whitespace
        return t.lower()

    @staticmethod
    def _edit_distance(a: str, b: str) -> int:
        """Levenshtein distance."""
        if len(a) < len(b):
            a, b = b, a
        if len(b) == 0:
            return len(a)

        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a):
            curr = [i + 1]
            for j, cb in enumerate(b):
                cost = 0 if ca == cb else 1
                curr.append(min(
                    curr[-1] + 1,          # insertion
                    prev[j + 1] + 1,        # deletion
                    prev[j] + cost,         # substitution
                ))
            prev = curr
        return prev[-1]

    def cross_source_resolve(
        self,
        instances_a: List[Dict[str, Any]],
        instances_b: List[Dict[str, Any]],
        *,
        source_a: str = "",
        source_b: str = "",
    ) -> ResolveResult:
        """P1: Cross-source entity aggregation. Links entities from different data sources.

        Unlike resolve() which merges within the same source, this creates cross-source
        links between entities that refer to the same real-world object.

        Returns a ResolveResult where merge_map maps {source_b_name → source_a_name}
        for entities that should be linked.
        """
        result = ResolveResult()
        merged_out = list(instances_a)
        total = len(instances_a) + len(instances_b)

        for inst_b in instances_b:
            best_score = 0.0
            best_match = -1
            name_b = self.normalize(
                str(inst_b.get("entity_text", "") or inst_b.get("properties", {}).get("name", ""))
            )
            if not name_b:
                merged_out.append(inst_b)
                continue

            for i, inst_a in enumerate(instances_a):
                name_a = self.normalize(
                    str(inst_a.get("entity_text", "") or inst_a.get("properties", {}).get("name", ""))
                )
                if not name_a:
                    continue

                # Cross-source: relaxed class constraint, emphasis on name match
                score = 0.0
                ed = self._edit_distance(name_a, name_b)
                if name_a == name_b:
                    score = 0.85  # Exact normalized match → high confidence cross-link
                elif ed <= 1:
                    score = 0.60
                elif ed <= 2:
                    score = 0.45

                # Boost if same class (cross-domain alignment)
                if inst_a.get("class_name") == inst_b.get("class_name"):
                    score = min(score + 0.10, 0.95)

                if score > best_score:
                    best_score = score
                    best_match = i

            if best_score >= 0.55 and best_match >= 0:
                # Link: record in merge_map, DON'T merge (keep both copies)
                inst_a = instances_a[best_match]
                a_name = str(inst_a.get("entity_text", "") or inst_a.get("properties", {}).get("name", ""))
                b_name = str(inst_b.get("entity_text", "") or inst_b.get("properties", {}).get("name", ""))
                result.merge_map[b_name] = a_name
                # Add cross-source tag
                tags_a = inst_a.get("frontmatter", {}).get("tags", []) or []
                src_tag = f"cross_source:{source_b}" if source_b else "cross_source"
                if src_tag not in tags_a:
                    inst_a.setdefault("frontmatter", {}).setdefault("tags", []).append(src_tag)
            else:
                merged_out.append(inst_b)

        result.merged = merged_out
        result.stats = {
            "total": total,
            "linked": len(result.merge_map),
            "unique": len(merged_out),
            "source_a": source_a,
            "source_b": source_b,
        }
        return result
