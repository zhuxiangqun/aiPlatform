"""
Rapid Industry Insight Service — 48h industry cognition core algorithms.

P0: normalize confidence, divergence detection, penetration scoring, blind spot location.
"""
from __future__ import annotations

import json
import logging
import math
import os
import statistics
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RapidSession:
    session_id: str
    industry_name: str
    domain_id: str
    entities_extracted: int = 0
    relations_extracted: int = 0
    aligned_domains: List[str] = field(default_factory=list)
    q1_report: Optional[Dict] = None
    q2_report: Optional[Dict] = None
    q3_questions: List[Dict] = field(default_factory=list)
    answers: Dict[str, Dict] = field(default_factory=dict)
    blind_spots: List[Dict] = field(default_factory=list)
    score: float = 0.0
    round_count: int = 0


# ═══════════════════════════════════════════════════════════
# Q1: Industry Consensus
# ═══════════════════════════════════════════════════════════

def extract_industry_consensus(
    domain_id: str,
    aligned_domains: List[str],
    top_n: int = 5,
) -> Dict[str, Any]:
    """Q1: 提取行业共识 — 从临时域及已对齐域的 inference_rules 中取 Top-N."""
    import yaml

    onto_dir = os.path.expanduser(
        os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))

    all_rules = {}  # domain → [{name, confidence, ...}]
    all_conclusions = []

    for d in [domain_id] + aligned_domains:
        yaml_path = os.path.join(onto_dir, f"{d}.yaml")
        if not os.path.isfile(yaml_path):
            continue
        try:
            with open(yaml_path) as f:
                ont = yaml.safe_load(f)
        except Exception:
            continue
        rules = ont.get("inference_rules", [])
        all_rules[d] = rules
        for r in rules:
            conclusion = r.get("conclusion", {})
            all_conclusions.append({
                "name": r.get("name", ""),
                "description": r.get("description", ""),
                "confidence": conclusion.get("confidence", 0.5),
                "label": conclusion.get("label", ""),
                "relation": conclusion.get("relation", ""),
                "domain": d,
            })

    if not all_conclusions:
        return {
            "consensus": "（暂无推理规则，需从材料中提取更多实体后重新分析）",
            "top_conclusions": [],
            "supporting_entities": [],
            "aligned_domains": aligned_domains,
        }

    # Normalize confidences
    for c in all_conclusions:
        c["normalized"] = _normalize_confidence(
            c["confidence"], c["domain"], all_rules)

    # Sort by normalized confidence descending
    all_conclusions.sort(key=lambda x: x["normalized"], reverse=True)
    top = all_conclusions[:top_n]

    # Get supporting entities from aligned domains
    from core.harness.ontology_engine.graph_index import GraphIndex
    entities = []
    for d in aligned_domains[:3]:
        try:
            g = GraphIndex.load(d)
            classes = g.get_entity_classes()
            entities.extend(classes[:5])
        except Exception:
            pass

    return {
        "consensus": f"Top-{len(top)} 推理结论（归一化置信度）",
        "top_conclusions": top,
        "supporting_entities": list(set(entities))[:10],
        "aligned_domains": aligned_domains,
    }


# ═══════════════════════════════════════════════════════════
# Q2: Route Controversies
# ═══════════════════════════════════════════════════════════

def detect_industry_controversies(
    domain_id: str,
    aligned_domains: List[str],
) -> Dict[str, Any]:
    """Q2: 路线之争 — 图结构分歧检测 + 竞争域数据."""
    from core.harness.ontology_engine.graph_index import GraphIndex

    controversies = []

    for d in [domain_id] + aligned_domains:
        try:
            g = GraphIndex.load(d)
        except Exception:
            continue
        if not g._nodes:
            continue

        # Structural divergence detection
        struct_divs = _detect_graph_divergence(g, g.get_entity_classes()[:10])
        for sd in struct_divs:
            controversies.append({
                "domain": d,
                "type": "structural",
                "entity": sd["entity"],
                "divergent_relations": sd["divergent_relations"],
                "detail": sd["detail"],
            })

    # Also check competition domain for explicit competitor data
    if "bell-competition" in aligned_domains:
        try:
            g_comp = GraphIndex.load("bell-competition")
            competitors = g_comp.get_entities_by_class("Competitor")
            competitor_names = [n.entity_name for n in competitors]
            if competitor_names:
                controversies.append({
                    "domain": "bell-competition",
                    "type": "competitive_landscape",
                    "entity": "行业竞争格局",
                    "positions": [
                        {"side": n, "argument": "（需在材料中补充该竞争对手的差异化优势）"}
                        for n in competitor_names[:3]
                    ],
                })
        except Exception:
            pass

    if not controversies:
        controversies.append({
            "topic": "待补充材料",
            "positions": [],
            "unresolved": "当前材料不足以识别行业分歧，建议补充多来源对比材料",
        })

    return {"controversies": controversies, "aligned_domains": aligned_domains}


# ═══════════════════════════════════════════════════════════
# Q3: Penetrating Questions
# ═══════════════════════════════════════════════════════════

def generate_penetrating_questions(
    domain_id: str,
    aligned_domains: List[str],
    count: int = 10,
) -> Dict[str, Any]:
    """Q3: 穿透性试题生成 + 穿透力过滤."""
    from core.harness.ontology_engine.graph_index import GraphIndex

    # Collect graph context for LLM
    all_entities = []
    all_relations = []

    for d in [domain_id] + aligned_domains:
        try:
            g = GraphIndex.load(d)
        except Exception:
            continue
        for nid, node in g._nodes.items():
            all_entities.append({
                "name": node.entity_name,
                "class": node.class_name,
                "domain": d,
            })
            for edge in node.out_edges:
                all_relations.append({
                    "source": node.entity_name,
                    "relation": edge.relation_name,
                    "target": edge.target_id,
                    "label": edge.relation_label,
                })

    if not all_entities:
        return {"questions": [], "filtered_count": 0,
                "message": "暂无实体数据，请先上传材料"}

    # Build graph context for LLM
    graph_context = json.dumps({
        "entities": all_entities[:30],
        "relations": all_relations[:20],
    }, ensure_ascii=False)

    # Generate questions via LLM
    questions = _llm_generate_questions(graph_context, count)

    # Penetration filtering
    g_first = None
    for d in [domain_id] + aligned_domains:
        try:
            g_first = GraphIndex.load(d)
            if g_first._nodes:
                break
        except Exception:
            pass

    filtered = []
    dropped = 0
    for q in questions:
        if g_first:
            score = _test_penetration(q, g_first)
        else:
            score = 0.8  # no graph to test against, optimistic
        q["penetration_score"] = round(score, 2)
        if score >= 0.5:
            filtered.append(q)
        else:
            dropped += 1

    return {
        "questions": filtered,
        "filtered_count": dropped,
        "total_generated": len(questions),
    }


# ═══════════════════════════════════════════════════════════
# Blind Spot Location
# ═══════════════════════════════════════════════════════════

def locate_blind_spot_source(
    entity_name: str,
    graph: Any,
) -> Dict[str, Any]:
    """盲区实体 → 反查原始文档 chunk 定位."""
    node = graph.get_node(entity_name)
    if not node:
        return {
            "entity": entity_name,
            "located": False,
            "message": "实体不在图中，需从材料补充",
        }

    source_doc = getattr(node, "source_doc_id", "") or (
        node.metadata.get("source_doc_id", "") if node.metadata else "")
    source_chunk = (node.metadata.get("source_chunk_id", "")
                    if node.metadata else "")

    if source_doc:
        preview = _get_chunk_preview(source_doc, source_chunk)
        return {
            "entity": entity_name,
            "located": True,
            "source_doc": source_doc,
            "source_chunk": source_chunk,
            "source_text_preview": preview,
        }

    return {
        "entity": entity_name,
        "located": False,
        "message": "无溯源信息（source_doc_id 为空），建议回补含此实体的原始材料",
    }


# ═══════════════════════════════════════════════════════════
# Private helpers
# ═══════════════════════════════════════════════════════════

def _normalize_confidence(
    conf: float,
    domain_id: str,
    all_domain_rules: Dict[str, List[Dict]],
) -> float:
    """z-score normalize confidence across domains → [0,1]."""
    domain_confs = [
        r.get("conclusion", {}).get("confidence", 0.5)
        for r in all_domain_rules.get(domain_id, [])
    ]
    if len(domain_confs) < 2:
        return conf

    mu = statistics.mean(domain_confs)
    sigma = statistics.stdev(domain_confs) if len(domain_confs) > 1 else 0.1
    if sigma == 0:
        return conf

    z = (conf - mu) / sigma
    return 1.0 / (1.0 + math.exp(-z))


def _detect_graph_divergence(
    graph: Any,
    target_classes: List[str],
) -> List[Dict]:
    """结构性分歧：同一实体有冲突方向的关系."""
    divergences = []

    divergent_patterns = [
        ("supports", "competes_with"),
        ("instantiates", "replaces"),
        ("governed_by", "violates"),
        ("owns", "equity_method"),
    ]

    for node_id, node in graph._nodes.items():
        if node.class_name not in target_classes and target_classes:
            continue
        in_edges = defaultdict(list)
        for nid, n in graph._nodes.items():
            for edge in n.out_edges:
                if edge.target_id == node_id:
                    in_edges[edge.relation_name].append({
                        "source": n.entity_name,
                        "source_class": n.class_name,
                    })

        for rel_a, rel_b in divergent_patterns:
            if rel_a in in_edges and rel_b in in_edges:
                divergences.append({
                    "entity": node.entity_name,
                    "divergent_relations": [rel_a, rel_b],
                    "detail": {
                        rel_a: [e["source"] for e in in_edges[rel_a]],
                        rel_b: [e["source"] for e in in_edges[rel_b]],
                    },
                })

    return divergences


def _bfs_reachable(graph: Any, start_id: str) -> Set[str]:
    """BFS from start_id, return all reachable entity IDs."""
    visited = set()
    queue = [start_id]
    while queue:
        cur = queue.pop(0)
        if cur in visited:
            continue
        visited.add(cur)
        node = graph._nodes.get(cur)
        if node:
            for edge in node.out_edges:
                if edge.target_id not in visited:
                    queue.append(edge.target_id)
    return visited


def _test_penetration(question: Dict, graph: Any) -> float:
    """Evaluate question penetration score (0-1).

    High = removing key relations makes answer entities unreachable.
    Low = answer entities still reachable via alternative paths.
    """
    involve_entities = question.get("involves_entities", [])
    involve_relations = question.get("involves_relations", [])
    expected = set(question.get("expected_answer_entities", []))

    if not involve_entities or not expected:
        return 0.5

    # Create cloned graph with key relations removed
    graph_clone = deepcopy(graph)
    for node_id, node in graph_clone._nodes.items():
        node.out_edges = [
            e for e in node.out_edges
            if e.relation_name not in involve_relations
        ]

    # BFS from start entity
    start = involve_entities[0]
    reachable = _bfs_reachable(graph_clone, start)

    still_reachable = len(expected & reachable)
    if len(expected) == 0:
        return 0.5
    return 1.0 - (still_reachable / len(expected))


def _get_chunk_preview(doc_id: str, chunk_id: str) -> str:
    """Read chunk text preview from source document."""
    if not chunk_id:
        return "（chunk_id 为空，无法定位具体段落）"
    # Try reading from parsed chunks
    chunk_dir = os.path.expanduser(
        os.getenv("AIPLAT_CHUNKS_DIR", "~/.aiplat/chunks"))
    chunk_path = os.path.join(chunk_dir, f"{chunk_id}.txt")
    if os.path.isfile(chunk_path):
        try:
            with open(chunk_path) as f:
                return f.read()[:500]
        except Exception:
            pass
    return f"文档: {doc_id}, Chunk: {chunk_id}（chunk 文件未缓存）"


def _llm_generate_questions(
    graph_context: str,
    count: int = 10,
) -> List[Dict]:
    """Generate penetrating questions via LLM with graph context."""
    # Try using sys_llm_generate if running in server context
    try:
        from core.harness.syscalls.llm import sys_llm_generate

        prompt = f"""基于以下行业知识图谱的实体和关系，生成 {count} 道"穿透性试题"。
每道题必须：① 包含一个"结构钩子"——必须理解至少 2 个实体之间的 1 条关系链才能答对，
② JSON 格式输出。

图谱上下文：
{graph_context}

输出格式（严格 JSON 数组）：
[
  {{
    "id": "Q1",
    "text": "问题正文",
    "involves_entities": ["实体名1", "实体名2"],
    "involves_relations": ["关系名"],
    "expected_answer_entities": ["标准答案涉及的关键实体"]
  }}
]
"""
        # Try async context, fall back to simple approach
        try:
            import asyncio
            result = asyncio.get_event_loop().run_until_complete(
                sys_llm_generate(prompt, purpose="reasoning"))
        except RuntimeError:
            return _generate_structural_questions(graph_context, count)
        return _parse_llm_questions(result)
    except Exception:
        return _generate_structural_questions(graph_context, count)


def _generate_structural_questions(
    graph_context: str,
    count: int = 10,
) -> List[Dict]:
    """Generate questions purely from graph structure (no LLM, zero cost)."""
    try:
        data = json.loads(graph_context)
    except Exception:
        return []

    entities = data.get("entities", [])
    relations = data.get("relations", [])

    questions = []
    for i, rel in enumerate(relations[:count]):
        src = next((e["name"] for e in entities if e["name"] == rel["source"]), rel["source"])
        tgt = rel["target"]
        questions.append({
            "id": f"Q{i + 1}",
            "text": f"在 '{src}' 与 '{tgt}' 之间，'{rel['relation']}' ({rel.get('label', '')}) 关系说明了什么业务逻辑？为什么这个关系是关键的？",
            "involves_entities": [rel["source"], rel["target"]],
            "involves_relations": [rel["relation"]],
            "expected_answer_entities": [rel["source"], rel["target"]],
        })

    return questions


def _parse_llm_questions(llm_output: Any) -> List[Dict]:
    """Parse LLM output into structured question list."""
    if not llm_output:
        return []
    try:
        text = str(llm_output)
        # Extract JSON array from LLM output
        import re
        match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    # Fallback: try to parse the whole thing
    try:
        return json.loads(str(llm_output))
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════
# P1: Reuse Rate Dashboard
# ═══════════════════════════════════════════════════════════

SHARED_DOMAIN_PREFIXES = [
    "bell-", "lock-", "supply-", "gov-", "finance-",
    "it-", "ship-", "fde-", "service-", "procurement-",
    "ai-", "enterprise-", "knowledge-", "system_",
]


def calculate_reuse_rate(graph: Any) -> Dict[str, Any]:
    """Calculate what fraction of entities reuse shared ontology vs custom.

    Returns {rate, shared, custom, total, details}.
    custom > 40% triggers overspill warning.
    """
    entities = list(graph._nodes.values())
    total = len(entities)
    if total == 0:
        return {"rate": 1.0, "shared": 0, "custom": 0, "total": 0,
                "details": [], "warning": False}

    shared = 0
    custom = 0
    details = []

    for node in entities:
        xd = (node.metadata or {}).get("_cross_domain", {})
        aligned_to = xd.get("aligned_to", "")

        is_shared = False
        reason = "new"
        if aligned_to:
            if any(aligned_to.startswith(p) for p in SHARED_DOMAIN_PREFIXES):
                is_shared = True
                reason = f"aligned→{aligned_to}"
        elif node.source_doc_id and not node.source_doc_id.startswith("rapid:"):
            is_shared = True
            reason = f"doc:{node.source_doc_id[:30]}"

        if is_shared:
            shared += 1
        else:
            custom += 1

        details.append({
            "entity": node.entity_name,
            "class": node.class_name,
            "shared": is_shared,
            "reason": reason,
        })

    rate = round(shared / total, 2)
    return {
        "rate": rate,
        "shared": shared,
        "custom": custom,
        "total": total,
        "details": details,
        "warning": custom > total * 0.4,
        "customization_pct": round(custom / total * 100, 1) if total else 0,
    }


# ═══════════════════════════════════════════════════════════
# P2: Auto Domain Suggestion + Icebreaker Questions
# ═══════════════════════════════════════════════════════════

def auto_suggest_domains(
    entities: List[Dict],
    threshold: float = 0.75,
) -> List[Dict]:
    """Suggest shared domain alignment using embedding cosine similarity.

    Uses existing entity index page vectors from vectors.json for comparison.
    LLM only used for final natural-language suggestion reason.
    """
    suggestions = []
    try:
        from core.harness.knowledge.embedder import embed_text_semantic
    except ImportError:
        return suggestions

    # Load existing class embeddings from vector cache
    import os as _os
    vec_path = _os.path.expanduser("~/.aiplat/wiki/collections/default/vectors.json")
    class_embeddings = {}
    if _os.path.isfile(vec_path):
        try:
            class_embeddings = json.loads(open(vec_path).read())
        except Exception:
            pass

    if not class_embeddings:
        return suggestions

    # Only consider shared domain class pages
    shared_embeddings = {
        k: v for k, v in class_embeddings.items()
        if any(k.startswith(p.replace("-", "").title()) or
               any(p in k.lower() for p in ["bell", "supply", "lock", "finance",
                                            "gov", "it-ops", "ship", "fde",
                                            "service", "procurement", "knowledge"])
               for _p in [p])
        # simplified: check if any shared domain prefix appears in key
    }
    # More precise: check domain prefix explicitly
    shared_embeddings = {}
    for k, v in class_embeddings.items():
        for p in SHARED_DOMAIN_PREFIXES:
            prefix_clean = p.replace("-", " ").replace("_", " ").title().replace(" ", "")
            if k.startswith(prefix_clean) or p.replace("-", "") in k.lower().replace(" ", ""):
                shared_embeddings[k] = v
                break

    if not shared_embeddings:
        return suggestions

    for entity in entities:
        name = entity.get("name", "")
        text = f"{name} {entity.get('description', '')}"[:500]
        if not text.strip():
            continue
        try:
            vec = embed_text_semantic(text[:2000])
        except Exception:
            continue
        if not vec:
            continue

        # Cosine similarity with all shared class embeddings
        similarities = []
        for class_key, class_vec in shared_embeddings.items():
            if not class_vec:
                continue
            sim = _cosine_similarity(vec, class_vec)
            if sim >= threshold:
                similarities.append((class_key, sim))

        similarities.sort(key=lambda x: x[1], reverse=True)
        if similarities:
            suggestions.append({
                "entity_name": name,
                "matches": [
                    {"domain_class": ck, "similarity": round(sc, 2)}
                    for ck, sc in similarities[:3]
                ],
            })

    return suggestions


def generate_icebreaker_questions(aligned_domains: List[str]) -> List[str]:
    """Generate industry-specific icebreaker questions based on aligned domains."""
    icebreaker_map = {
        "bell-competition": [
            "这个行业的头部公司是谁？他们各自押注的技术路线有何不同？",
            "目前的竞争格局中，哪类公司的利润率最高？为什么？",
            "行业里有没有还没达成共识的关键问题？",
        ],
        "supply-chain": [
            "目前供应链中哪个环节的库存周转最慢？",
            "供应商评级是根据什么标准？多久更新一次？",
            "物流配送是否支持多仓库调拨？",
        ],
        "bell-healthcare": [
            "临床试验数据管理是按 ICH-GCP 标准还是内部规范？",
            "患者招募目前最大的瓶颈是什么？",
            "CRO 服务的切换成本有多大？",
        ],
        "bell-consulting": [
            "目前有哪些业务流程是靠人工经验而非系统规则驱动的？",
            "团队里有多少人具备 BPR 项目经验？",
            "最近一次流程优化带来了多少效率提升？",
        ],
        "bell-contact-center": [
            "目前的呼叫中心是自建还是外包？坐席规模多大？",
            "客服对话数据是否已经在做分析和知识沉淀？",
            "高峰期和低谷期的坐席利用率差多少？",
        ],
        "bell-data-cloud": [
            "目前用的 CRM 系统是什么？有没有做过定制开发？",
            "AI 能力（如自动回复）是自研还是采购的第三方方案？",
        ],
        "lock-service": [
            "目前设备故障率最高的型号是哪个？",
            "安装师傅的调度系统是手动分配还是自动派单？",
            "客户现场的门类型分布是怎样的？",
        ],
        "procurement-mvo": [
            "采购流程中哪个环节最耗时？审批还是比价？",
            "供应商的历史履约率是多少？",
            "有没有遇到过围标的情况？",
        ],
        "finance": [
            "核心财务指标中哪个波动最大？为什么？",
            "交易对手的信用评估是怎么做的？",
        ],
        "gov-service": [
            "政务服务中审批时限最长的环节是哪一步？",
            "公民办事的一次通过率大概是多少？",
        ],
    }

    questions = []
    for domain in aligned_domains:
        qs = icebreaker_map.get(domain, [])
        questions.extend(qs)

    # Deduplicate
    seen = set()
    unique = []
    for q in questions:
        if q not in seen:
            seen.add(q)
            unique.append(q)

    return unique[:8]


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
