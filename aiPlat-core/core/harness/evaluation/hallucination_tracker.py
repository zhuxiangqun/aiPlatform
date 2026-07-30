"""
Hallucination Tracker — NLI 事实核查 + Faithfulness 指标 + 幻觉率仪表盘

在 RAG Pipeline 的答案生成后，自动检测:
  1. Faithfulness (忠实度): 答案 vs 检索证据的事实一致性
  2. Answer Relevancy (答案相关性): 答案 vs 原始问题的语义匹配度
  3. Hallucination Score (幻觉风险): 综合评分 [0, 1]

GraphIndex 加持 (aiPlat 独有):
  利用本体知识图谱验证事实声明: claim → GraphIndex 查是否有边支持
"""

from __future__ import annotations
import logging

import re, time, json, hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict


@dataclass
# disposition: internal data type — used by HallucinationTracker.evaluate(); wired to llm.py
class FactualClaim:
    """单个事实声明"""
    text: str                       # 声明原文
    source_evidence: str = ""       # 支持证据
    source_page: str = ""           # 来源页面
    judgment: str = "pending"       # entailment / contradiction / neutral / pending
    confidence: float = 0.0         # 判决置信度


@dataclass
# disposition: internal data type — used by HallucinationTracker.evaluate(); wired to llm.py
class HallucinationReport:
    """单次答案的幻觉检测报告"""
    run_id: str
    question: str
    answer: str
    faithfulness_score: float = 1.0  # [0, 1], 1 = 完全忠实
    relevancy_score: float = 1.0     # 答案与问题相关度
    hallucination_risk: float = 0.0  # [0, 1], 0 = 无幻觉风险
    total_claims: int = 0
    supported_claims: int = 0
    contradicted_claims: int = 0
    neutral_claims: int = 0
    claims: List[FactualClaim] = field(default_factory=list)
    quality_flag: str = "ok"         # ok / needs_review / low_evidence
    timestamp: str = ""


class HallucinationTracker:
    """幻觉检测跟踪器。

    Usage:
        tracker = HallucinationTracker()
        report = await tracker.evaluate(
            question="Python 3.13 有什么新特性?",
            answer="Python 3.13 引入了 free-threaded 模式...",
            retrieved_context=[{"page": "Python3.13", "text": "..."}],
        )
        print(f"Faithfulness: {report.faithfulness_score:.2%}")
        print(f"Hallucination Risk: {report.hallucination_risk:.2%}")
        print(f"Flag: {report.quality_flag}")
    """

    def __init__(self):
        self._history: List[HallucinationReport] = []
        self._stats: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

    async def evaluate(
        self,
        *,
        question: str,
        answer: str,
        retrieved_context: List[Dict[str, Any]],
        run_id: str = "",
        domain_id: str = "default",
    ) -> HallucinationReport:
        """评估答案的幻觉风险。

        Args:
            question: 原始问题
            answer: LLM 生成的答案
            retrieved_context: 检索到的上下文
            run_id: 执行 ID
            domain_id: 域 ID

        Returns:
            幻觉检测报告
        """
        # Step 1: Extract claims from answer
        claims = self._extract_claims(answer)
        total = len(claims)

        # Step 2: Verify each claim against retrieved context
        supported = 0
        contradicted = 0
        neutral = 0

        for claim in claims:
            judgment, evidence, confidence = self._verify_claim(
                claim.text, retrieved_context
            )
            claim.judgment = judgment
            claim.source_evidence = evidence[:200] if evidence else ""
            claim.source_page = evidence.get("page", "") if isinstance(evidence, dict) else ""
            claim.confidence = confidence

            if judgment == "entailment":
                supported += 1
            elif judgment == "contradiction":
                contradicted += 1
            else:
                neutral += 1

        # Step 3: Calculate scores
        faithfulness = supported / max(total, 1)
        relevancy = self._calculate_relevancy(question, answer)
        hallucination_risk = contradicted / max(total, 1) + (1 - faithfulness) * 0.5
        hallucination_risk = min(1.0, hallucination_risk)

        # Step 4: Determine quality flag
        if hallucination_risk > 0.3 or faithfulness < 0.5:
            flag = "low_evidence"
        elif hallucination_risk > 0.1 or faithfulness < 0.7:
            flag = "needs_review"
        else:
            flag = "ok"

        report = HallucinationReport(
            run_id=run_id,
            question=question,
            answer=answer,
            faithfulness_score=round(faithfulness, 3),
            relevancy_score=round(relevancy, 3),
            hallucination_risk=round(hallucination_risk, 3),
            total_claims=total,
            supported_claims=supported,
            contradicted_claims=contradicted,
            neutral_claims=neutral,
            claims=claims,
            quality_flag=flag,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

        # Store for dashboard
        self._history.append(report)
        self._update_stats(report, domain_id)

        return report

    def get_dashboard(self, domain_id: str = "") -> Dict[str, Any]:
        """获取幻觉率仪表盘数据。"""
        stats = self._stats.get(domain_id, self._stats.get("default", {}))
        return {
            "total_evaluations": len(self._history),
            "avg_faithfulness": self._avg(stats.get("faithfulness", [])),
            "avg_relevancy": self._avg(stats.get("relevancy", [])),
            "avg_hallucination_risk": self._avg(stats.get("hallucination_risk", [])),
            "quality_distribution": {
                "ok": stats.get("ok_count", 0),
                "needs_review": stats.get("needs_review_count", 0),
                "low_evidence": stats.get("low_evidence_count", 0),
            },
            "graph_verified": stats.get("graph_verified", 0),
            "graph_contradicted": stats.get("graph_contradicted", 0),
        }

    def get_recent_reports(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的幻觉报告。"""
        return [
            {
                "run_id": r.run_id,
                "question": r.question[:80],
                "faithfulness": r.faithfulness_score,
                "hallucination_risk": r.hallucination_risk,
                "quality_flag": r.quality_flag,
                "claims": f"{r.supported_claims}/{r.total_claims} supported",
                "timestamp": r.timestamp,
            }
            for r in self._history[-limit:]
        ]

    # ── Internal: Claim Extraction ─────────────────────────────────────────

    def _extract_claims(self, answer: str) -> List[FactualClaim]:
        """从答案中提取事实声明。"""
        claims = []
        # Split by sentence
        sentences = re.split(r'(?<=[。！？.!\?\n])\s*', answer)
        for s in sentences:
            s = s.strip()
            # Filter: must contain factual indicators
            if len(s) > 10 and self._is_factual(s):
                claims.append(FactualClaim(text=s[:300]))
        return claims[:20]  # Cap at 20 claims

    def _is_factual(self, text: str) -> bool:
        """判断是否为事实性声明（非 questions/opinions）。"""
        factual_indicators = [
            '是', '有', '在', '包含', '支持', '提供', '引入', '使用',
            'is', 'has', 'was', 'supports', 'provides', 'includes', 'uses',
            'can', 'will', 'does', 'allows',
        ]
        return any(w in text.lower()[:30] for w in factual_indicators)

    def _verify_claim(
        self,
        claim: str,
        context: List[Dict[str, Any]],
    ) -> Tuple[str, Any, float]:
        """验证声明 vs 检索上下文。

        Returns:
            (judgment, evidence, confidence)
            judgment: entailment / contradiction / neutral
        """
        best_match = None
        best_score = 0.0

        for ctx in context:
            ctx_text = ctx.get("text", "")
            score = self._text_similarity(claim, ctx_text)
            if score > best_score:
                best_score = score
                best_match = ctx

        # Also try GraphIndex verification
        graph_result = self._verify_with_graph(claim)

        if graph_result["conflict"]:
            return "contradiction", graph_result, max(0.7, best_score)
        elif graph_result["support"]:
            return "entailment", graph_result, max(0.6, best_score)
        elif best_score > 0.5:
            return "entailment", best_match, best_score
        elif best_score > 0.2:
            return "neutral", best_match, best_score
        else:
            return "neutral", None, 0.0

    def _verify_with_graph(self, claim: str) -> Dict[str, Any]:
        """使用知识图谱验证声明 (aiPlat 独有)。

        检查 claim 中的实体对是否在 GraphIndex 中存在关系边。
        """
        try:
            from core.harness.knowledge.graph_index import GraphIndex
            # Extract entity pairs from claim
            entities = self._extract_entities(claim)
            if len(entities) < 2:
                return {"support": False, "conflict": False, "reason": "insufficient_entities"}

            # Check if relation exists in graph
            for i in range(len(entities)):
                for j in range(i + 1, len(entities)):
                    a, b = entities[i], entities[j]
                    # This is a simplified check — full implementation needs NER + relation extraction
                    if self._has_graph_edge(a, b):
                        return {"support": True, "conflict": False, "entities": [a, b]}

            return {"support": False, "conflict": False, "entities": entities[:3]}
        except Exception:
            return {"support": False, "conflict": False, "reason": "graph_unavailable"}

    def _extract_entities(self, text: str) -> List[str]:
        """从文本中提取实体 (简化版 NER)。"""
        entities = []
        # Chinese entities: 2-8 char groups
        zh = re.findall(r'[\u4e00-\u9fff]{2,8}', text)
        # English capitalized words
        en = re.findall(r'[A-Z][a-z]+(?:\s[A-Z][a-z]+)?', text)
        entities.extend(zh[:5])
        entities.extend(en[:5])
        return entities

    def _has_graph_edge(self, entity_a: str, entity_b: str) -> bool:
        """检查图中是否存在实体间的关系边。"""
        try:
            from core.harness.knowledge.graph_index import GraphIndex
            # Search for nodes by name
            graph = GraphIndex("ai-knowledge")
            node_a = graph.find_by_name(entity_a)
            node_b = graph.find_by_name(entity_b)
            if node_a and node_b:
                # Check for edges between them
                edges = graph.get_edges_between(node_a.get("id"), node_b.get("id"))
                return len(edges) > 0
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        return False

    def _text_similarity(self, a: str, b: str) -> float:
        """文本相似度 (Jaccard + 关键词)。"""
        if not a or not b:
            return 0.0
        ta = set(re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', a.lower()))
        tb = set(re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', b.lower()))
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / max(len(ta | tb), 1)

    def _calculate_relevancy(self, question: str, answer: str) -> float:
        """计算答案与问题的相关性。"""
        q_tokens = set(re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', question.lower()))
        a_tokens = set(re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', answer.lower()))
        if not q_tokens:
            return 1.0
        overlap = len(q_tokens & a_tokens)
        return min(1.0, overlap / len(q_tokens))

    def _update_stats(self, report: HallucinationReport, domain_id: str):
        """更新仪表盘统计数据。"""
        s = self._stats[domain_id]
        s["faithfulness"].append(report.faithfulness_score)
        s["hallucination_risk"].append(report.hallucination_risk)
        s["relevancy"].append(report.relevancy_score)
        if report.quality_flag == "ok":
            s["ok_count"] = s.get("ok_count", 0) + 1
        elif report.quality_flag == "needs_review":
            s["needs_review_count"] = s.get("needs_review_count", 0) + 1
        else:
            s["low_evidence_count"] = s.get("low_evidence_count", 0) + 1

    def _avg(self, values: List[float]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 3)

    # ── v2.10: evaluate_text for non-dialog context (sys_file_write) ──

    async def evaluate_text(self, text: str, source: str = "unknown",
                            doc_id: str = "") -> Dict[str, Any]:
        """Evaluate standalone text for hallucination. Used by sys_file_write."""
        if not text or len(text) < 50:
            return {"risk": "low", "detail": "Text too short"}
        try:
            from core.harness.evaluation.nli_engine import NLIEngine
            engine = NLIEngine()
            result = await engine.evaluate_claims(text[:2000])
            risk = "high" if result.get("contradiction_score", 0) > 0.7 else \
                   "medium" if result.get("contradiction_score", 0) > 0.4 else "low"
            return {"risk": risk, "detail": str(result.get("summary", ""))[:100],
                    "score": result.get("contradiction_score", 0)}
        except Exception:
            import re
            patterns = [
                r"(?i)\b(据不完全统计|权威人士透露|研究表明|数据表明)\b",
                r"(?i)\b(all|every|always|never|none)\b.*\b(are|is|were)\b",
            ]
            matches = sum(1 for p in patterns if re.search(p, text))
            if matches >= 2:
                return {"risk": "medium", "detail": f"{matches} suspect patterns"}
            return {"risk": "low", "detail": "Heuristic pass"}


# ── Global singleton ─────────────────────────────────────────────────────────

_tracker: Optional[HallucinationTracker] = None

def get_hallucination_tracker() -> HallucinationTracker:
    global _tracker
    if _tracker is None:
        _tracker = HallucinationTracker()
    return _tracker
