"""
Provenance Engine — 声明级溯源 + 自动过期扫描

功能:
  1. Claim-Level Citation: 答案中每句话绑定来源 (Wiki offset / KB chunk)
  2. ProvenanceScanner: 源文档更新 → 自动标记已生成的答案过期
"""

from __future__ import annotations

import re, time, hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Citation:
    claim: str
    source_type: str = "wiki"
    source_page: str = ""
    source_section: str = ""
    source_offset: int = 0
    source_text: str = ""
    source_version: str = ""
    confidence: float = 0.0
    status: str = "current"


@dataclass
class AnswerProvenance:
    run_id: str
    answer: str
    citations: List[Citation] = field(default_factory=list)
    dataset_version: str = ""
    generated_at: str = ""
    stale_count: int = 0


class ProvenanceTracker:

    def __init__(self):
        self._store: Dict[str, AnswerProvenance] = {}

    def extract_citations(self, answer: str, retrieved_context: List[Dict[str, Any]], *, domain_id: str = "default") -> List[Citation]:
        citations = []
        sentences = re.split(r'(?<=[。！？\n])\s*', answer)
        for sentence in sentences:
            if len(sentence) < 10:
                continue
            best, best_score = None, 0.0
            for ctx in retrieved_context:
                score = self._similarity(sentence, ctx.get("text", ""))
                if score > best_score and score > 0.3:
                    best_score, best = score, ctx
            if best:
                citations.append(Citation(
                    claim=sentence[:200], source_type=best.get("type", "wiki"),
                    source_page=best.get("page", ""), source_section=best.get("section", ""),
                    source_offset=best.get("offset", 0), source_text=best.get("text", "")[:300],
                    source_version=best.get("version", ""), confidence=round(best_score, 2)))
        return citations

    def link_answer_to_sources(self, run_id: str, answer: str, citations: List[Citation], *, dataset_version: str = ""):
        self._store[run_id] = AnswerProvenance(
            run_id=run_id, answer=answer, citations=citations,
            dataset_version=dataset_version,
            generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def get_provenance(self, run_id: str) -> Optional[AnswerProvenance]:
        return self._store.get(run_id)

    def get_stale_answers(self) -> List[AnswerProvenance]:
        return [p for p in self._store.values() if p.stale_count > 0]

    def _similarity(self, a: str, b: str) -> float:
        ta = set(re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', a.lower()))
        tb = set(re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', b.lower()))
        if not ta or not tb: return 0.0
        return len(ta & tb) / max(len(ta | tb), 1)


class ProvenanceScanner:

    def __init__(self, tracker: Optional[ProvenanceTracker] = None):
        self._tracker = tracker or ProvenanceTracker()

    async def on_source_updated(self, page_id: str, new_version: str):
        count = 0
        for run_id, prov in list(self._tracker._store.items()):
            for c in prov.citations:
                if c.source_page == page_id and c.source_version != new_version:
                    c.status = "stale"
                    prov.stale_count = sum(1 for x in prov.citations if x.status == "stale")
                    count += 1
                    break
        if count:
            import logging
            logging.getLogger("aiplat.provenance").info(f"Source '{page_id}' updated: {count} answers stale")

    async def scan_stale_answers(self) -> List[Dict[str, Any]]:
        return [{"run_id": p.run_id, "generated_at": p.generated_at, "stale_count": p.stale_count,
                 "total_citations": len(p.citations)} for p in self._tracker.get_stale_answers()[:50]]

    def get_frontend_badge(self, run_id: str) -> Dict[str, Any]:
        prov = self._tracker.get_provenance(run_id)
        if not prov: return {"status": "unknown"}
        if prov.stale_count == 0: badge = "current ✅"
        elif prov.stale_count < len(prov.citations) * 0.3: badge = "partial ⚠️"
        else: badge = "stale 🔄"
        return {"badge": badge, "citations": len(prov.citations), "stale": prov.stale_count,
                "dataset_version": prov.dataset_version, "generated_at": prov.generated_at}


# ── Global ──────────────────────────────────────────────────────────────────

_provenance_tracker: Optional[ProvenanceTracker] = None

def get_provenance_tracker() -> ProvenanceTracker:
    global _provenance_tracker
    if _provenance_tracker is None: _provenance_tracker = ProvenanceTracker()
    return _provenance_tracker
