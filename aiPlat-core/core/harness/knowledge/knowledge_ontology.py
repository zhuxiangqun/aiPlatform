"""
Knowledge Ontology — T-Box (Term Box) for the aiPlat knowledge domain.

Defines classes, object properties, data properties, and axioms for
the knowledge base domain: Wiki pages, KB documents, relationships.

Design foundations:
  1. Bottom-up: Extracted from existing FRONTMATTER_FIELDS, KBDocument schema,
     RELATIONSHIP_TYPES found in wiki_engine.py and platform/kb/db.py
  2. Standard mapping: Dublin Core (dc:), SKOS (skos:), PROV-O (prov:),
     CIDOC-CRM (crm:), FOAF (foaf:) — per docs/knowledge-ontology-plan.md
  3. Domain-specific: aiplat: namespace for AI knowledge base semantics
     (contradictions, LLM generation, knowledge atoms)

Usage:
    from core.harness.knowledge.knowledge_ontology import get_ontology
    onto = get_ontology()
    # Load A-Box
    from core.harness.knowledge.knowledge_abox_builder import build_abox
    build_abox(onto)

from pathlib import Path
    # Reason
    onto.sync_reasoner_pellet()
    # Query
    results = list(onto.world.sparql("SELECT ..."))
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
import logging

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# Namespace
# ══════════════════════════════════════════════════════════════

AI = "http://aiplat.local/knowledge#"
NS = {
    "aiplat": AI,
    "dc": "http://purl.org/dc/elements/1.1/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "prov": "http://www.w3.org/ns/prov#",
    "crm": "http://www.cidoc-crm.org/cidoc-crm/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}

# ══════════════════════════════════════════════════════════════
# T-Box: Class Hierarchy (dataclass representation)
# ══════════════════════════════════════════════════════════════

@dataclass
class OntologyClass:
    """Represents a named class in the T-Box."""
    uri: str                           # Full URI
    label: str                         # Human-readable label
    parent: Optional[str] = None       # URI of parent class
    equivalent_to: List[str] = field(default_factory=list)  # OWL equivalentClass expressions
    disjoint_with: List[str] = field(default_factory=list)  # Disjoint with these classes
    standard_mapping: Optional[str] = None  # Standard ontology URI
    # ── Schema-level field constraints ──
    required_fields: List[str] = field(default_factory=list)
    """该类的实例必须包含的 data property key (title, summary, body 等)"""
    optional_fields: List[str] = field(default_factory=list)
    """该类的实例可选包含的 data property key (tags, related, source_articles 等)"""
    allowed_categories: List[str] = field(default_factory=list)
    """该类对应的 Wiki category 目录名 (entities, topics, contradictions, atoms)"""
    template_markdown: str = ""
    """该类 Wiki 页面的 SOP 模板（含必填槽位占位符）"""
    extraction_prompt: str = ""
    """KB 文档抽取该类实例的 LLM 指令片段"""
    fields: List[Dict[str, Any]] = field(default_factory=list)
    """每字段的 type/enum/description 等元数据（来自 YAML fields 段）"""
    description: str = ""
    """该类的描述文本"""
    states: Dict[str, Any] = field(default_factory=dict)
    """状态机定义：{description, default, enum: [{name, label, description}, ...]}"""
    implements: List[str] = field(default_factory=list)
    """该类实现的 Interface 名称列表（P1: Interface 原语）"""
    transitions: List[Dict[str, Any]] = field(default_factory=list)
    """状态转换规则：[{from, to, description, trigger: {type, ...}}, ...]"""
    side_effects: List[Dict[str, Any]] = field(default_factory=list)
    """状态转换联动：[{when, actions: [{type, ...}]}, ...]"""
    synonyms: List[str] = field(default_factory=list)
    """同义词列表，用于域路由器T1 label匹配扩展 (e.g. ["k8s", "kubernetes"])"""
    confidence_threshold: float = 0.7
    """本体映射置信度阈值，低于此值不启用 target_class 过滤 (domain router T2 使用)"""


@dataclass
class OntologyObjectProperty:
    """Represents a typed object property."""
    uri: str
    label: str
    domain: List[str]                  # Class URIs
    range: List[str]                   # Class URIs
    standard_mapping: Optional[str] = None
    # OWL characteristics
    is_symmetric: bool = False
    is_transitive: bool = False
    is_irreflexive: bool = False
    is_asymmetric: bool = False
    is_functional: bool = False
    max_cardinality: Optional[int] = None
    min_cardinality: Optional[int] = None
    inverse_of: Optional[str] = None
    inverse_label: str = ""  # human-readable inverse label


@dataclass  
class OntologyDataProperty:
    """Represents a typed data property."""
    uri: str
    label: str
    domain: List[str]
    range: str                        # XSD type
    is_functional: bool = False
    min_cardinality: int = 0
    max_cardinality: Optional[int] = None
    standard_mapping: Optional[str] = None


@dataclass
class OntologyAxiom:
    """Represents a logical axiom / constraint."""
    id: str
    description: str
    sparql_violation_query: str       # SPARQL to find violations
    severity: str = "error"           # error | warning | info


@dataclass
class OntologyTriple:
    """Single SPO triple for the A-Box."""
    subject: str       # URI of the subject (e.g., aiplat:RAG概述)
    predicate: str     # URI of the property (e.g., aiplat:cites)
    object: str        # URI or literal value


# ══════════════════════════════════════════════════════════════
# T-Box: Class Definitions
# ══════════════════════════════════════════════════════════════

CLASSES: List[OntologyClass] = [
    # ── Root ──
    OntologyClass(f"{AI}KnowledgeEntity", "知识实体", standard_mapping="http://www.w3.org/2002/07/owl#Thing"),
    
    # ── Atomic Knowledge ──
    OntologyClass(f"{AI}KnowledgeAtom", "知识原子",
        parent=f"{AI}KnowledgeEntity",
        required_fields=["title", "body"],
        optional_fields=["tags", "source_doc_id", "evidence_start", "evidence_end",
                          "evidence_text", "confidence", "category"],
        allowed_categories=["atoms"],
        extraction_prompt="从文档中提取可独立成句的知识断言。每条断言是一个 KnowledgeAtom。",
        standard_mapping=f"{NS['crm']}E73_Information_Object"),
    
    # ── Composite Knowledge ──
    OntologyClass(f"{AI}CompositeKnowledge", "组合知识",
        parent=f"{AI}KnowledgeEntity"),
    
    OntologyClass(f"{AI}WikiPage", "Wiki 页面",
        parent=f"{AI}CompositeKnowledge",
        required_fields=["title", "body"],
        optional_fields=["summary", "tags", "related", "source_articles",
                          "contradictions", "relationships"],
         allowed_categories=["entities", "topics", "contradictions", "atoms",
                              "ai-concepts", "ai-systems", "ai-techniques",
                              "business-problems", "references", "synthesis"],
        equivalent_to=[f"rdfs:subClassOf {NS['skos']}Concept"]),

    OntologyClass(f"{AI}ConceptPage", "概念页",
        parent=f"{AI}WikiPage",
        required_fields=["title", "summary", "body"],
        optional_fields=["tags", "related", "source_articles", "relationships", "contradictions"],
        allowed_categories=["entities"],
        template_markdown="# {{title}}\n\n## 摘要\n{{summary}}\n\n## 核心内容\n...\n\n## 来源\n{{source_articles}}\n",
        extraction_prompt="从文档中提取独立的概念/实体。名称中文优先5-15字；定义/描述核心2-3句；关键词3-8个；来源标注引用kb:doc_id。",
        equivalent_to=[f"{AI}WikiPage AND ({AI}category == 'entities')"],
        standard_mapping=f"{NS['skos']}Concept"),

    OntologyClass(f"{AI}TopicPage", "专题页",
        parent=f"{AI}WikiPage",
        required_fields=["title", "summary", "body"],
        optional_fields=["tags", "related", "relationships", "contradictions"],
        allowed_categories=["topics"],
        template_markdown="# {{title}}\n\n## 概述\n{{summary}}\n\n## 讨论\n...\n\n## 关联概念\n{{related}}\n",
        extraction_prompt="提取跨实体的专题讨论。需要明确的论点、支撑证据、与相关概念页的交叉引用。",
        equivalent_to=[f"{AI}WikiPage AND ({AI}category == 'topics')"],
        standard_mapping=f"{NS['skos']}Collection"),
    
    OntologyClass(f"{AI}SourcePage", "资料摘要页",
        parent=f"{AI}WikiPage",
        required_fields=["title", "body", "source_articles"],
        optional_fields=["summary", "tags"],
        allowed_categories=["entities"],
        equivalent_to=[f"{AI}WikiPage AND NOT EXISTS({AI}cites)"],
        disjoint_with=[f"{AI}ConceptPage"]),

    OntologyClass(f"{AI}WikiProposal", "Wiki 提案",
        parent=f"{AI}CompositeKnowledge",
        required_fields=["title", "body"],
        optional_fields=["target_pages", "reason", "proposal_type"],
        allowed_categories=[],
        standard_mapping=f"{NS['prov']}Activity"),

    OntologyClass(f"{AI}ContradictionPage", "矛盾声明页",
        parent=f"{AI}WikiPage",
        required_fields=["title", "body", "contradictions"],
        optional_fields=["summary", "tags", "source_articles"],
        allowed_categories=["contradictions"],
        extraction_prompt="识别相互冲突的断言对：claim_a vs claim_b，说明冲突原因。"),

    # ── Claim-level entities ──
    OntologyClass(f"{AI}Claim", "断言",
        parent=f"{AI}KnowledgeAtom",
        required_fields=["title", "body"],
        optional_fields=["source_doc_id", "evidence_start", "evidence_end",
                          "evidence_text", "confidence", "status", "tags",
                          "source_articles"],
        allowed_categories=["atoms"],
        extraction_prompt="从知识原子中提取可独立验证的断言。每条断言有精确 evidence 位置和置信度。"),

    OntologyClass(f"{AI}Resolution", "解决记录",
        parent=f"{AI}WikiProposal",
        required_fields=["title", "body", "resolves_claim"],
        optional_fields=["resolution_type", "evidence", "status"],
        allowed_categories=["contradictions"],
        extraction_prompt="记录矛盾的解决过程：解决类型、证据、结论。"),

    # ── External Resources ──
    OntologyClass(f"{AI}KBDocument", "KB 文档",
        parent=f"{AI}KnowledgeEntity",
        required_fields=["doc_id", "source_uri"],
        optional_fields=["kind", "title", "meta_json", "collection_id"],
        allowed_categories=[],
        standard_mapping=f"{NS['foaf']}Document"),
    
    # ── Relationships ──
    OntologyClass(f"{AI}WikiRelation", "Wiki 关系",
        parent=f"{AI}KnowledgeEntity"),
    
    OntologyClass(f"{AI}CitesRelation", "引用关系",
        parent=f"{AI}WikiRelation",
        equivalent_to=[f"{AI}WikiRelation AND ({AI}relation_type == 'cites')"]),
    
    OntologyClass(f"{AI}ContradictsRelation", "矛盾关系",
        parent=f"{AI}WikiRelation",
        equivalent_to=[f"{AI}WikiRelation AND ({AI}relation_type == 'contradicts')"]),
    
    OntologyClass(f"{AI}ParentRelation", "父概念关系",
        parent=f"{AI}WikiRelation",
        equivalent_to=[f"{AI}WikiRelation AND ({AI}relation_type == 'parent')"]),
    
    OntologyClass(f"{AI}SupportsRelation", "支撑关系",
        parent=f"{AI}WikiRelation",
        equivalent_to=[f"{AI}WikiRelation AND ({AI}relation_type == 'supports')"]),
    
    OntologyClass(f"{AI}ExtendsRelation", "扩展关系",
        parent=f"{AI}WikiRelation",
        equivalent_to=[f"{AI}WikiRelation AND ({AI}relation_type == 'extends')"]),
    
    OntologyClass(f"{AI}ExampleRelation", "案例关系",
        parent=f"{AI}WikiRelation",
        equivalent_to=[f"{AI}WikiRelation AND ({AI}relation_type == 'example_of')"]),

    # Phase 4 — Cross-domain: TaskSkill ↔ Knowledge bridge
    OntologyClass(f"{AI}TaskSkill", "任务技能",
        parent=f"{AI}KnowledgeEntity",
        optional_fields=["skill_id", "name", "pipeline_id", "agent_sequence",
                          "artifacts", "pass_rate", "keywords", "created_at"]),

    # Learning domain (L1 — AI Learning Coach T-Box)
    OntologyClass(f"{AI}LearningPath", "学习路径",
        parent=f"{AI}KnowledgeEntity",
        optional_fields=["description", "target_role", "chapter_count", "tags"]),
    OntologyClass(f"{AI}Chapter", "学习章节",
        parent=f"{AI}KnowledgeEntity",
        optional_fields=["title", "path_id", "order", "estimated_minutes",
                          "concepts", "status", "mastery_score"]),
    OntologyClass(f"{AI}Material", "学习材料",
        parent=f"{AI}KnowledgeEntity",
        optional_fields=["type", "title", "content", "source_url"]),
    OntologyClass(f"{AI}Exercise", "练习题",
        parent=f"{AI}KnowledgeEntity",
        optional_fields=["exercise_type", "question", "options_json", "rubric"]),
    OntologyClass(f"{AI}Assessment", "评估结果",
        parent=f"{AI}KnowledgeEntity",
        optional_fields=["learner_id", "score", "passed", "feedback",
                          "weak_points_json", "submitted_at"]),
]

# ══════════════════════════════════════════════════════════════
# T-Box: Object Property Definitions
# ══════════════════════════════════════════════════════════════

OBJECT_PROPERTIES: List[OntologyObjectProperty] = [
    OntologyObjectProperty(f"{AI}hasSource", "来源文档",
        domain=[f"{AI}WikiPage"], range=[f"{AI}KBDocument"],
        standard_mapping=f"{NS['prov']}wasAttributedTo"),
    
    OntologyObjectProperty(f"{AI}cites", "引用",
        domain=[f"{AI}WikiPage"], range=[f"{AI}WikiPage"],
        standard_mapping=f"{NS['prov']}wasDerivedFrom",
        is_asymmetric=True, inverse_of=f"{AI}isCitedBy"),
    
    OntologyObjectProperty(f"{AI}isCitedBy", "被引用",
        domain=[f"{AI}WikiPage"], range=[f"{AI}WikiPage"],
        inverse_of=f"{AI}cites"),
    
    OntologyObjectProperty(f"{AI}contradicts", "矛盾",
        domain=[f"{AI}WikiPage"], range=[f"{AI}WikiPage"],
        is_symmetric=True),
    
    OntologyObjectProperty(f"{AI}parentOf", "父概念",
        domain=[f"{AI}WikiPage"], range=[f"{AI}WikiPage"],
        standard_mapping=f"{NS['skos']}broader",
        is_transitive=True, is_irreflexive=True, is_asymmetric=True,
        max_cardinality=1, inverse_of=f"{AI}childOf"),
    
    OntologyObjectProperty(f"{AI}childOf", "子概念",
        domain=[f"{AI}WikiPage"], range=[f"{AI}WikiPage"],
        inverse_of=f"{AI}parentOf"),
    
    OntologyObjectProperty(f"{AI}extends", "扩展",
        domain=[f"{AI}WikiPage"], range=[f"{AI}WikiPage"],
        standard_mapping=f"{NS['skos']}narrower"),
    
    OntologyObjectProperty(f"{AI}supports", "支撑",
        domain=[f"{AI}WikiPage"], range=[f"{AI}WikiPage"],
        is_asymmetric=True),
    
    OntologyObjectProperty(f"{AI}example_of", "案例",
        domain=[f"{AI}WikiPage"], range=[f"{AI}WikiPage"],
        is_asymmetric=True),
    
    OntologyObjectProperty(f"{AI}hasAtom", "包含原子",
        domain=[f"{AI}WikiPage"], range=[f"{AI}KnowledgeAtom"],
        standard_mapping=f"{NS['crm']}P106_is_composed_of"),
    
    OntologyObjectProperty(f"{AI}derivesFrom", "提取自",
        domain=[f"{AI}KnowledgeAtom"], range=[f"{AI}KBDocument"],
        standard_mapping=f"{NS['prov']}wasDerivedFrom"),
    
    OntologyObjectProperty(f"{AI}transitivelyTouches", "传递触达",
        domain=[f"{AI}WikiPage"], range=[f"{AI}KnowledgeEntity"],
        is_transitive=True),

    # ── Claim/Evidence properties ──
    OntologyObjectProperty(f"{AI}resolves", "解决断言",
        domain=[f"{AI}Resolution"], range=[f"{AI}Claim"],
        standard_mapping=f"{NS['prov']}wasInfluencedBy"),
    OntologyObjectProperty(f"{AI}contradictsClaim", "矛盾断言",
        domain=[f"{AI}Claim"], range=[f"{AI}Claim"],
        is_symmetric=True),
    OntologyObjectProperty(f"{AI}supportsClaim", "支撑断言",
        domain=[f"{AI}Claim"], range=[f"{AI}Claim"],
        is_asymmetric=True),

    # Phase 4 — TaskSkill↔WikiPage cross-domain links
    OntologyObjectProperty(f"{AI}usesKnowledge", "使用知识",
        domain=[f"{AI}TaskSkill"], range=[f"{AI}WikiPage"]),
    OntologyObjectProperty(f"{AI}producesKnowledge", "产出知识",
        domain=[f"{AI}TaskSkill"], range=[f"{AI}WikiPage"]),
    OntologyObjectProperty(f"{AI}producedBy", "由谁产出",
        domain=[f"{AI}WikiPage"], range=[f"{AI}TaskSkill"]),

    # Learning domain relations (L1)
    OntologyObjectProperty(f"{AI}prerequisiteOf", "前置依赖",
        domain=[f"{AI}Chapter"], range=[f"{AI}Chapter"],
        is_asymmetric=True),
    OntologyObjectProperty(f"{AI}containsChapter", "包含章节",
        domain=[f"{AI}LearningPath"], range=[f"{AI}Chapter"]),
    OntologyObjectProperty(f"{AI}assesses", "评估关联",
        domain=[f"{AI}Assessment"], range=[f"{AI}Exercise"],
        is_asymmetric=True),

    # Cross-modal relations (Phase CM — document structure preservation)
    OntologyObjectProperty(f"{AI}explains", "文字解释",
        domain=[f"{AI}WikiPage", f"{AI}KBDocument"], range=[f"{AI}KBDocument"],
        is_asymmetric=True),
    OntologyObjectProperty(f"{AI}belongsToSection", "属于章节",
        domain=[f"{AI}KBDocument"], range=[f"{AI}WikiPage"],
        is_asymmetric=True),
    OntologyObjectProperty(f"{AI}refersToImage", "引用图片",
        domain=[f"{AI}WikiPage"], range=[f"{AI}KBDocument"],
        is_asymmetric=True),
    OntologyObjectProperty(f"{AI}refersToTable", "引用表格",
        domain=[f"{AI}WikiPage"], range=[f"{AI}KBDocument"],
        is_asymmetric=True),
]

# ══════════════════════════════════════════════════════════════
# T-Box: Data Property Definitions
# ══════════════════════════════════════════════════════════════

DATA_PROPERTIES: List[OntologyDataProperty] = [
    OntologyDataProperty(f"{AI}title", "标题",
        domain=[f"{AI}WikiPage"], range="xsd:string",
        is_functional=True, min_cardinality=1,
        standard_mapping=f"{NS['dc']}title"),
    
    OntologyDataProperty(f"{AI}summary", "摘要",
        domain=[f"{AI}WikiPage"], range="xsd:string",
        min_cardinality=1,
        standard_mapping=f"{NS['dc']}description"),
    
    OntologyDataProperty(f"{AI}body", "正文",
        domain=[f"{AI}WikiPage"], range="xsd:string",
        standard_mapping=f"{NS['crm']}P190_has_symbolic_content"),
    
    OntologyDataProperty(f"{AI}category", "分类",
        domain=[f"{AI}WikiPage"], range="xsd:string",
        is_functional=True, min_cardinality=1),
    
    OntologyDataProperty(f"{AI}tags", "标签",
        domain=[f"{AI}WikiPage"], range="xsd:string",
        standard_mapping=f"{NS['skos']}related"),
    
    OntologyDataProperty(f"{AI}created_at", "创建时间",
        domain=[f"{AI}KnowledgeEntity"], range="xsd:dateTime",
        standard_mapping=f"{NS['dc']}created"),
    
    OntologyDataProperty(f"{AI}updated_at", "更新时间",
        domain=[f"{AI}KnowledgeEntity"], range="xsd:dateTime",
        standard_mapping=f"{NS['dc']}modified"),
    
    OntologyDataProperty(f"{AI}is_llm_generated", "LLM 生成",
        domain=[f"{AI}WikiPage"], range="xsd:boolean"),
    
    OntologyDataProperty(f"{AI}doc_id", "文档 ID",
        domain=[f"{AI}KBDocument"], range="xsd:string",
        is_functional=True),
    
    OntologyDataProperty(f"{AI}kind", "文档类型",
        domain=[f"{AI}KBDocument"], range="xsd:string"),
    
    OntologyDataProperty(f"{AI}relation_type", "关系类型",
        domain=[f"{AI}WikiRelation"], range="xsd:string",
        is_functional=True, min_cardinality=1),

    # ── Evidence / Claim tracking ──
    OntologyDataProperty(f"{AI}evidence_start", "证据起始位置",
        domain=[f"{AI}KnowledgeAtom"], range="xsd:integer", min_cardinality=0),
    OntologyDataProperty(f"{AI}evidence_end", "证据结束位置",
        domain=[f"{AI}KnowledgeAtom"], range="xsd:integer"),
    OntologyDataProperty(f"{AI}evidence_text", "证据原文",
        domain=[f"{AI}KnowledgeAtom"], range="xsd:string"),
    OntologyDataProperty(f"{AI}confidence", "置信度",
        domain=[f"{AI}KnowledgeAtom"], range="xsd:float"),
    OntologyDataProperty(f"{AI}status", "状态",
        domain=[f"{AI}Claim", f"{AI}WikiProposal", f"{AI}ContradictsRelation"],
        range="xsd:string"),
    OntologyDataProperty(f"{AI}resolution_type", "解决类型",
        domain=[f"{AI}Resolution"], range="xsd:string"),
    OntologyDataProperty(f"{AI}source_doc_id", "来源文档ID",
        domain=[f"{AI}KnowledgeAtom"], range="xsd:string"),
    # Lifecycle state management (Phase 1 — entity lifecycle state machine)
    OntologyDataProperty(f"{AI}lifecycleState", "生命周期状态",
        domain=[f"{AI}KnowledgeEntity"], range="xsd:string",
        is_functional=True, min_cardinality=0),
    OntologyDataProperty(f"{AI}generatedBy", "生成溯源",
        domain=[f"{AI}KnowledgeEntity"], range="xsd:string"),
    OntologyDataProperty(f"{AI}qualityScore", "质量评分",
        domain=[f"{AI}KnowledgeEntity"], range="xsd:integer",
        is_functional=True, min_cardinality=0),
    OntologyDataProperty(f"{AI}fieldLevelPermission", "字段级权限",
        domain=[f"{AI}KnowledgeEntity"], range="xsd:string"),
    # Learning domain (L1)
    OntologyDataProperty(f"{AI}estimatedMinutes", "预估学习时间",
        domain=[f"{AI}Chapter"], range="xsd:integer"),
    OntologyDataProperty(f"{AI}masteryScore", "掌握度评分",
        domain=[f"{AI}Chapter", f"{AI}Assessment"], range="xsd:float",
        is_functional=True),
    OntologyDataProperty(f"{AI}exerciseType", "习题类型",
        domain=[f"{AI}Exercise"], range="xsd:string"),
    OntologyDataProperty(f"{AI}chapterStatus", "章节状态",
        domain=[f"{AI}Chapter"], range="xsd:string"),
]

# ══════════════════════════════════════════════════════════════
# T-Box: Axioms (Consistency Constraints)
# ══════════════════════════════════════════════════════════════

AXIOMS: List[OntologyAxiom] = [
    OntologyAxiom(
        id="A1",
        description="概念完整性: 每个 ConceptPage 必须至少关联一个 KBDocument 作为来源",
        severity="error",
        sparql_violation_query="""
            SELECT ?page WHERE {
                ?page rdf:type <{AI}ConceptPage> .
                FILTER NOT EXISTS { ?page <{AI}hasSource> ?doc }
            }
        """.replace("{AI}", AI),
    ),
    OntologyAxiom(
        id="A2",
        description="来源传递: hasAtom(p,a) AND derivesFrom(a,d) ⇒ hasSource(p,d)",
        severity="info",
        sparql_violation_query="""
            SELECT ?page ?kb WHERE {
                ?page <{AI}hasAtom> ?atom .
                ?atom <{AI}derivesFrom> ?kb .
                FILTER NOT EXISTS { ?page <{AI}hasSource> ?kb }
            }
        """.replace("{AI}", AI),
    ),
    OntologyAxiom(
        id="A3",
        description="矛盾对称性: contradicts(A,B) ⇒ contradicts(B,A)",
        severity="warning",
        sparql_violation_query="""
            SELECT ?a ?b WHERE {
                ?a <{AI}contradicts> ?b .
                FILTER NOT EXISTS { ?b <{AI}contradicts> ?a }
            }
        """.replace("{AI}", AI),
    ),
    OntologyAxiom(
        id="A4",
        description="层级无环: parentOf 关系不能形成环",
        severity="error",
        sparql_violation_query="""
            SELECT ?page WHERE {
                ?page <{AI}parentOf>+ ?page
            }
        """.replace("{AI}", AI),
    ),
    OntologyAxiom(
        id="A5",
        description="源页面独立: SourcePage 不能 cites 其他 WikiPage",
        severity="warning",
        sparql_violation_query="""
            SELECT ?page WHERE {
                ?page rdf:type <{AI}SourcePage> .
                ?page <{AI}cites> ?target .
                ?target rdf:type <{AI}WikiPage>
            }
        """.replace("{AI}", AI),
    ),
    OntologyAxiom(
        id="A6",
        description="引用完整性: 每个 hasSource 的 object 必须是一个已注册的 KBDocument",
        severity="error",
        sparql_violation_query="""
            SELECT ?page ?kb WHERE {
                ?page <{AI}hasSource> ?kb .
                FILTER NOT EXISTS { ?kb rdf:type <{AI}KBDocument> }
            }
        """.replace("{AI}", AI),
    ),
    OntologyAxiom(
        id="A7",
        description="关联双向性: 每个 cites 关系必须在两方的 related 字段中都有反映",
        severity="info",
        sparql_violation_query="""
            SELECT ?a ?b WHERE {
                ?a <{AI}cites> ?b .
                FILTER NOT EXISTS { ?b <{AI}cites> ?a }
                FILTER NOT EXISTS { ?b <{AI}isCitedBy> ?a }
            }
        """.replace("{AI}", AI),
    ),
    OntologyAxiom(
        id="A8",
        description="键区分度: 新增 WikiPage/KnowledgeAtom 的 title+summary 与已有实体余弦相似度必须 < 0.85，除非声明为同义词",
        severity="warning",
        sparql_violation_query="""
            (checked at write time via check_key_discrimination)
        """,
    ),
]


# ══════════════════════════════════════════════════════════════
# Schema Validation Engine
# ══════════════════════════════════════════════════════════════

@dataclass
class SchemaValidationResult:
    is_valid: bool
    class_uri: str
    class_label: str
    category: str
    missing_required: List[str] = field(default_factory=list)
    unknown_fields: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestion: str = ""


def get_class_by_category(category: str) -> Optional[OntologyClass]:
    """Map Wiki category string → most specific OntologyClass with that category.

    Prefers the class with more constraints (required_fields count) and
    fewer categories (more specific).
    """
    candidates = [cls for cls in CLASSES if category in cls.allowed_categories]
    
    # Also search YAML domain classes (e.g., ai-knowledge, ship-design, it-ops)
    if not candidates:
        try:
            from core.harness.knowledge.ontology_loader import load_all_domains
            for dom in load_all_domains().values():
                for cls in dom.classes:
                    if category in (cls.allowed_categories or []):
                        candidates.append(cls)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    if not candidates:
        return None
    # Sort by specificity: more required_fields → fewer categories → deeper parent chain
    def specificity(cls: OntologyClass) -> tuple:
        req = len(cls.required_fields)
        cats = -len(cls.allowed_categories)  # fewer = more specific (negated for sort)
        depth = _class_depth(cls)
        return (-req, -cats, -depth)  # sort ascending → most specific first (all negated)
    candidates.sort(key=specificity)
    return candidates[0]


def _class_depth(cls: OntologyClass) -> int:
    """Count parent chain depth."""
    d = 0
    current = cls
    visited = set()
    while current.parent and current.uri not in visited:
        visited.add(current.uri)
        d += 1
        parent = next((c for c in CLASSES if c.uri == current.parent), None)
        if parent is None:
            break
        current = parent
    return d


def get_classes_with_templates() -> List[OntologyClass]:
    """Return all classes that have a Wiki page template defined."""
    return [cls for cls in CLASSES if cls.allowed_categories and cls.template_markdown]


# ── Per-Collection Ontology Extension ──────────────────────────

def _extension_path(collection_id: str):
    from pathlib import Path
    import os as _oss
    home = _oss.getenv("AIPLAT_HOME", _oss.path.expanduser("~/.aiplat"))
    return Path(home) / "wiki" / "collections" / collection_id / "ontology_extension.yaml"


def load_collection_extension(collection_id: str) -> Optional[Dict]:
    """Load per-collection T-Box extension YAML. Returns None if not found.

    Cached in memory after first load (invalidate on file change via mtime check).
    collection_id="default" always returns None (no extension for default).
    """
    if collection_id == "default":
        return None

    path = _extension_path(collection_id)
    if not path.exists():
        return None

    cache_key = f"_ext_cache_{collection_id}"
    if hasattr(load_collection_extension, cache_key):
        cached_time, cached_data = getattr(load_collection_extension, cache_key)
        if path.stat().st_mtime <= cached_time:
            return cached_data

    import yaml
    import time as _time
    try:
        extension = yaml.safe_load(open(path)) or {}
        setattr(load_collection_extension, cache_key, (_time.time(), extension))
        return extension
    except Exception:
        return None


def get_extended_class(category: str, collection_id: str = "default") -> Optional[OntologyClass]:
    """Get the T-Box class for a category, merged with collection extension.

    Returns a NEW OntologyClass instance with merged required/optional fields.
    Original CLASSES list is never modified.
    """
    base = get_class_by_category(category)
    if base is None:
        return None

    extension = load_collection_extension(collection_id)
    if extension is None:
        return base  # No extension — use base class as-is

    extends = extension.get("extends", {})
    for class_key, ext_fields in extends.items():
        if class_key == base.label or class_key == base.uri.replace(AI, ""):
            return OntologyClass(
                uri=base.uri,
                label=ext_fields.get("label_override", base.label),
                parent=base.parent,
                required_fields=base.required_fields + ext_fields.get("additional_required", []),
                optional_fields=base.optional_fields + ext_fields.get("additional_optional", []),
                allowed_categories=base.allowed_categories,
                template_markdown=base.template_markdown,
                extraction_prompt=base.extraction_prompt,
                standard_mapping=base.standard_mapping,
            )
    return base


def validate_page_against_schema(
    page_data: Dict[str, Any],
    *,
    mode: str = "warning",
    collection_id: str = "default",
) -> SchemaValidationResult:
    """Validate a Wiki page against T-Box class schema constraints.

    Validation rules (derived from T-Box):
    1. category must map to at least one OntologyClass.allowed_categories
    2. All required_fields must be non-empty
    3. Unknown fields are non-fatal but logged
    4. Cross-domain: parentOf max_cardinality=1 (from OBJECT_PROPERTIES)

    Args:
        page_data: Dict with title, category, body, summary, tags, related etc.
        mode: "warning" = don't block, return warnings; "error" = block on missing required.
        collection_id: Wiki collection context.

    Returns:
        SchemaValidationResult
    """
    category = page_data.get("category", "entities")
    cls = get_extended_class(category, collection_id)

    if cls is None:
        all_cats = sorted(set(c for ccls in CLASSES for c in ccls.allowed_categories))
        return SchemaValidationResult(
            is_valid=(mode != "error"),
            class_uri="", class_label=f"unknown:{category}",
            category=category,
            warnings=[f"Category '{category}' does not map to any T-Box class"] if mode == "warning" else [],
            missing_required=["category"] if mode == "error" else [],
            suggestion=f"Supported categories: {all_cats}",
        )

    # Check required fields
    missing = []
    for f in cls.required_fields:
        val = page_data.get(f)
        if val is None or (isinstance(val, str) and not val.strip()) or \
           (isinstance(val, list) and len(val) == 0):
            missing.append(f)

    # Known fields set — include parent class fields for completeness
    base_known = set(["category", "relationships", "stale_references", "version",
                       "last_updated", "_body", "_category", "_path", "body",
                       "source_articles", "summary", "tags", "related",
                       "contradictions", "source_doc_id", "evidence_start",
                       "evidence_end", "evidence_text", "confidence",
                       "contradicts_atom_index", "supports_atom_index",
                       "lifecycle_state", "_generated_by", "quality_score",
                       "field_level_permission", "title", "marking", "status", "images"])
    known = set(cls.required_fields + cls.optional_fields) | base_known
    # Also inherit parent class fields
    parent = cls.parent
    while parent:
        pc = next((c for c in CLASSES if c.uri == parent), None)
        if pc:
            known.update(pc.required_fields)
            known.update(pc.optional_fields)
            parent = pc.parent
        else:
            break
    unknown = [k for k in page_data if k not in known and not k.startswith("_")]

    # Cross-domain: parentOf cardinality check
    relationships = page_data.get("relationships") or []
    parent_count = sum(1 for r in relationships if isinstance(r, dict) and r.get("type") == "parent")
    if parent_count > 1:
        return SchemaValidationResult(
            is_valid=False,
            class_uri=cls.uri, class_label=cls.label, category=category,
            missing_required=missing,
            unknown_fields=unknown,
            suggestion="parentOf relation max_cardinality=1. Remove extra parent relationships.",
        )

    if mode == "error" and missing:
        return SchemaValidationResult(
            is_valid=False,
            class_uri=cls.uri, class_label=cls.label, category=category,
            missing_required=missing, unknown_fields=unknown,
            suggestion=f"Please complete required fields: {', '.join(missing)}",
        )

    return SchemaValidationResult(
        is_valid=True,
        class_uri=cls.uri, class_label=cls.label, category=category,
        warnings=([
            f"Schema mode=warning: missing required fields {missing}" if missing else "",
            f"Unknown T-Box fields: {unknown}" if unknown else "",
        ] if mode == "warning" else []),
        missing_required=missing,
        unknown_fields=unknown,
    )


def build_atom_extraction_prompt(doc_text: str, doc_id: str, *,
                                  max_atoms: int = 20,
                                  max_length: int = 12000) -> str:
    """Build KnowledgeAtom-level extraction prompt for LLM-driven KB→Wiki conversion.

    Returns a structured prompt instructing the LLM to extract atoms with
    precise evidence positions, confidence scores, and contradiction markers.
    """
    atom_cls = get_class_by_category("atoms")
    if not atom_cls:
        atom_cls = next((c for c in CLASSES if c.label == "知识原子"), None)
    required = atom_cls.required_fields if atom_cls else ["title", "body", "source_doc_id"]
    optional = atom_cls.optional_fields if atom_cls else ["tags", "evidence_start", "evidence_text"]

    return f"""You are a knowledge atom extraction expert. Extract all independently understandable knowledge claims from the document below.

[Output Format] JSON array:
[
  {{
    "title": "Claim title (5-15 chars, concise)",
    "body": "Knowledge content (2-8 sentences, self-contained)",
    "source_doc_id": "{doc_id}",
    "evidence_start": 1234,
    "evidence_end": 1567,
    "evidence_text": "Direct quote from source (50-200 chars)",
    "confidence": 0.85,
    "category": "entities" | "topics",
    "tags": ["keyword1", "keyword2"],
    "contradicts_atom_index": null,
    "supports_atom_index": null
  }}
]

[Core Constraints]
1. Each atom must be independently understandable without context
2. evidence_start/end are 0-based character positions in the source document
3. evidence_text must be a direct quote, not paraphrased
4. Mutually exclusive claims: mark contradicts_atom_index (array index number)
5. Supporting claims: mark supports_atom_index
6. Skip atoms with confidence < 0.5

[Source Document] (doc_id={doc_id})
{doc_text[:max_length]}
"""


# ══════════════════════════════════════════════════════════════
# Ontology Registry
# ══════════════════════════════════════════════════════════════

@dataclass
class KnowledgeOntology:
    """Holds the complete T-Box and A-Box for the knowledge domain."""
    classes: List[OntologyClass] = field(default_factory=lambda: CLASSES)
    object_properties: List[OntologyObjectProperty] = field(default_factory=lambda: OBJECT_PROPERTIES)
    data_properties: List[OntologyDataProperty] = field(default_factory=lambda: DATA_PROPERTIES)
    axioms: List[OntologyAxiom] = field(default_factory=lambda: AXIOMS)
    # A-Box (population)
    triples: List[OntologyTriple] = field(default_factory=list)

    def get_class(self, uri: str) -> Optional[OntologyClass]:
        for c in self.classes:
            if c.uri == uri:
                return c
        return None

    def get_property(self, uri: str):
        for p in self.object_properties + self.data_properties:
            if p.uri == uri:
                return p
        return None

    def get_axiom(self, axiom_id: str) -> Optional[OntologyAxiom]:
        for a in self.axioms:
            if a.id == axiom_id:
                return a
        return None

    def get_class_by_label(self, label: str) -> Optional[OntologyClass]:
        for c in self.classes:
            if c.label == label:
                return c
        return None

    def to_sparql_rules(self) -> str:
        """Generate SPARQL validation queries for all axioms."""
        queries = []
        for ax in self.axioms:
            queries.append(f"# {ax.id}: {ax.description}")
            queries.append(ax.sparql_violation_query.strip())
            queries.append("")
        return "\n".join(queries)

    def validate_tbox(self) -> List[str]:
        """Validate T-Box internal consistency."""
        issues = []
        # Check that all property domains/ranges reference existing classes
        class_uris = {c.uri for c in self.classes}
        for prop in self.object_properties:
            for d in prop.domain:
                if d not in class_uris:
                    issues.append(f"Property '{prop.label}' domain '{d}' is not a defined class")
            for r in prop.range:
                if r not in class_uris:
                    issues.append(f"Property '{prop.label}' range '{r}' is not a defined class")
        # Check that parent references are valid
        for c in self.classes:
            if c.parent and c.parent not in class_uris:
                issues.append(f"Class '{c.label}' parent '{c.parent}' is not a defined class")
            for d in c.disjoint_with:
                if d not in class_uris:
                    issues.append(f"Class '{c.label}' disjoint_with '{d}' is not a defined class")
        return issues


# ══════════════════════════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════════════════════════

_onto: Optional[KnowledgeOntology] = None


def get_ontology() -> KnowledgeOntology:
    """Get or create the singleton KnowledgeOntology instance."""
    global _onto
    if _onto is None:
        _onto = KnowledgeOntology()
        issues = _onto.validate_tbox()
        if issues:
            for i in issues:
                logger.warning(f"Ontology T-Box issue: {i}")
    return _onto


def reset_ontology() -> None:
    """Reset the ontology (e.g., for testing or rebuild)."""
    global _onto
    _onto = None


def export_to_owl_rdf(format: str = "turtle") -> str:
    """Export T-Box + A-Box as standard OWL/RDF serialization.

    Args:
        format: "turtle" (default), "rdfxml", or "ntriples"

    Returns:
        RDF serialization string compatible with Protégé, GraphDB, Stardog.
    """
    onto = get_ontology()
    lines = []

    if format == "turtle":
        lines.append("@prefix aiplat: <http://aiplat.local/knowledge#> .")
        lines.append("@prefix owl: <http://www.w3.org/2002/07/owl#> .")
        lines.append("@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .")
        lines.append("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .")
        lines.append("@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .")
        lines.append("@prefix dc: <http://purl.org/dc/elements/1.1/> .")
        lines.append("@prefix skos: <http://www.w3.org/2004/02/skos/core#> .")
        lines.append("@prefix prov: <http://www.w3.org/ns/prov#> .")
        lines.append("@prefix crm: <http://www.cidoc-crm.org/cidoc-crm/> .")
        lines.append("@prefix foaf: <http://xmlns.com/foaf/0.1/> .")
        lines.append("")

        # T-Box: Classes
        for cls in onto.classes:
            s = _turtle_id(cls.uri)
            lines.append(f"{s} rdf:type owl:Class ;")
            lines.append(f"    rdfs:label \"{cls.label}\" .")
            if cls.parent:
                lines.append(f"{s} rdfs:subClassOf <{cls.parent}> .")
            if cls.standard_mapping:
                lines.append(f"{s} owl:equivalentClass {cls.standard_mapping} .")
            for d in cls.disjoint_with:
                lines.append(f"{s} owl:disjointWith <{d}> .")
            lines.append("")

        # T-Box: Object Properties
        for op in onto.object_properties:
            s = _turtle_id(op.uri)
            lines.append(f"{s} rdf:type owl:ObjectProperty ;")
            lines.append(f"    rdfs:label \"{op.label}\" ;")
            for d in op.domain:
                lines.append(f"    rdfs:domain <{d}> ;")
            for r in op.range:
                lines.append(f"    rdfs:range <{r}> .")
            if op.is_transitive:
                lines.append(f"{s} rdf:type owl:TransitiveProperty .")
            if op.is_symmetric:
                lines.append(f"{s} rdf:type owl:SymmetricProperty .")
            if op.is_asymmetric:
                lines.append(f"{s} owl:AsymmetricProperty {s} ." if format != "turtle" else f"{s} rdf:type owl:AsymmetricProperty .")
            if op.inverse_of:
                lines.append(f"{s} owl:inverseOf <{op.inverse_of}> .")
            if op.max_cardinality is not None:
                lines.append(f"{s} owl:maxCardinality {op.max_cardinality} .")
            lines.append("")

        # T-Box: Data Properties
        for dp in onto.data_properties:
            s = _turtle_id(dp.uri)
            lines.append(f"{s} rdf:type owl:DatatypeProperty ;")
            lines.append(f"    rdfs:label \"{dp.label}\" ;")
            lines.append(f"    rdfs:range {dp.range} ;")
            for d in dp.domain:
                lines.append(f"    rdfs:domain <{d}> ;")
            if dp.is_functional:
                lines.append(f"    rdf:type owl:FunctionalProperty .")
            else:
                # remove trailing semicolon
                lines[-1] = lines[-1].rstrip(" ;") + " ."
            lines.append("")

        # A-Box: Triples
        for t in onto.triples:
            s = _turtle_id(t.subject)
            p = _turtle_id(t.predicate)
            o = _turtle_id(t.object) if not t.object.startswith('"') else t.object
            lines.append(f"{s} {p} {o} .")

    elif format == "ntriples":
        for t in onto.triples:
            s = _turtle_id(t.subject)
            p = _turtle_id(t.predicate)
            o = _turtle_id(t.object) if not t.object.startswith('"') else t.object
            lines.append(f"{s} {p} {o} .")

    else:
        lines.append(f"# RDF export in {format} format not yet implemented.")
        lines.append(f"# Triples available: {len(onto.triples)}")
        lines.append(f"# Classes: {len(onto.classes)}")
        lines.append(f"# Use format=turtle or format=ntriples")

    return "\n".join(lines)


def _turtle_id(uri: str) -> str:
    """Convert URI to safe Turtle identifier."""
    if uri.startswith("http://"):
        return f"<{uri}>"
    if ":" in uri and not uri.startswith('"'):
        return uri
    return f"<{uri}>"


def _safe_uri(name: str) -> str:
    """Convert a name to a URI-safe string, stripping unsafe characters."""
    import re
    safe = re.sub(r'[<>:"/\\|?*#]', '_', str(name))
    return safe[:120]


# ══════════════════════════════════════════════════════════════
# Ontology Evolution — Suggestions Storage (Layer 3)
# ══════════════════════════════════════════════════════════════

import os as _os
import json as _json
import time as _time


def _suggestions_path(collection_id: str = "default") -> str:
    home = _os.path.expanduser(_os.getenv("AIPLAT_HOME", "~/.aiplat"))
    return _os.path.join(home, "wiki", "collections", collection_id, "ontology_suggestions.json")


def load_pending_suggestions(collection_id: str = "default") -> List[Dict[str, Any]]:
    """Load all suggestions from the tracking file."""
    path = _suggestions_path(collection_id)
    if not _os.path.exists(path):
        return []
    try:
        data = _json.load(open(path))
        if isinstance(data, list):
            return data
        return data.get("suggestions", [])
    except Exception:
        return []


def save_suggestions(suggestions: List[Dict[str, Any]], collection_id: str = "default") -> None:
    """Write suggestions to the tracking file."""
    path = _suggestions_path(collection_id)
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        _json.dump({
            "version": "v1.2",
            "updated_at": _time.time(),
            "suggestions": suggestions,
        }, f, indent=2, ensure_ascii=False)


def accept_suggestion(suggestion_id: str, reviewer: str = "", *, collection_id: str = "default") -> Optional[Dict]:
    """Mark a suggestion as accepted. Does NOT modify any code."""
    suggestions = load_pending_suggestions(collection_id)
    for s in suggestions:
        if s.get("id") == suggestion_id:
            s["status"] = "accepted"
            s["reviewed_by"] = reviewer or "human"
            s["reviewed_at"] = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())
            save_suggestions(suggestions, collection_id)
            return s
    return None


def reject_suggestion(suggestion_id: str, reason: str = "", reviewer: str = "", *, collection_id: str = "default") -> Optional[Dict]:
    """Mark a suggestion as rejected with optional reason."""
    suggestions = load_pending_suggestions(collection_id)
    for s in suggestions:
        if s.get("id") == suggestion_id:
            s["status"] = "rejected"
            s["rejected_reason"] = reason
            s["reviewed_by"] = reviewer or "human"
            s["reviewed_at"] = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())
            save_suggestions(suggestions, collection_id)
            return s
    return None


def generate_code_for_suggestion(suggestion_id: str, *, collection_id: str = "default") -> Dict[str, Any]:
    """Generate Python code block for implementing an accepted suggestion.

    Uses template-based code generation (NOT LLM). Each suggestion type maps
    to a deterministic code template. The generated code is for human review
    only — it never writes to disk.
    """
    suggestions = load_pending_suggestions(collection_id)
    suggestion = next((s for s in suggestions if s.get("id") == suggestion_id), None)
    if not suggestion:
        return {"error": f"Suggestion '{suggestion_id}' not found"}

    stype = suggestion.get("type", "")
    desc = suggestion.get("description", "")

    if stype == "new_class":
        name = desc.replace(" ", "").replace("高频概念:", "").split("(")[0].strip()
        class_name = ''.join(c for c in name if c.isalnum() or c == '_') or "NewClass"
        code = (
            f'    OntologyClass(f"{{AI}}{class_name}", "{desc}",\n'
            f'        parent=f"{{AI}}ConceptPage",\n'
            f'        required_fields=["title", "body"],\n'
            f'        optional_fields=["summary", "tags", "related"],\n'
            f'        allowed_categories=["entities"],\n'
            f'        extraction_prompt="从文档中提取{class_name}相关概念。",\n'
            f'    ),'
        )
        return {
            "suggestion_id": suggestion_id,
            "type": stype,
            "code_diff": code,
            "affected_file": "aiPlat-core/core/harness/knowledge/knowledge_ontology.py",
            "insert_after_class": "ConceptPage",
            "risk": "low",
            "instructions": (
                "1. Copy the code block above\n"
                "2. Insert into CLASSES list in knowledge_ontology.py\n"
                "3. Run: python3 -m py_compile aiPlat-core/core/harness/knowledge/knowledge_ontology.py\n"
                "4. Once verified, mark suggestion as 'implemented' via API"
            ),
        }

    elif stype == "new_property":
        code = (
            f'    OntologyObjectProperty(f"{{AI}}{desc}", "{desc}",\n'
            f'        domain=[f"{{AI}}WikiPage"], range=[f"{{AI}}WikiPage"]),\n'
        )
        return {
            "suggestion_id": suggestion_id,
            "type": stype,
            "code_diff": code,
            "affected_file": "aiPlat-core/core/harness/knowledge/knowledge_ontology.py",
            "insert_into_list": "OBJECT_PROPERTIES",
            "risk": "low",
            "instructions": "Copy code block, insert into OBJECT_PROPERTIES list, verify compile.",
        }

    elif stype == "add_required_field":
        return {
            "suggestion_id": suggestion_id,
            "type": stype,
            "code_diff": f"# Add to required_fields of target class:\n# {desc}",
            "affected_file": "aiPlat-core/core/harness/knowledge/knowledge_ontology.py",
            "risk": "medium",
            "instructions": "Manually add the field to the target class's required_fields list. Existing pages may need migration.",
        }

    elif stype == "merge_classes":
        return {
            "suggestion_id": suggestion_id,
            "type": stype,
            "code_diff": f"# Merge action: {desc}\n# 1. Remove the merged class definition\n# 2. Merge its fields into the target class\n# 3. Update existing pages' category if needed",
            "affected_file": "aiPlat-core/core/harness/knowledge/knowledge_ontology.py",
            "risk": "high",
            "instructions": "Review carefully. Merging classes may require page migration.",
        }

    else:
        return {
            "suggestion_id": suggestion_id,
            "type": stype,
            "code_diff": f"# Custom implementation for: {desc}",
            "affected_file": "aiPlat-core/core/harness/knowledge/knowledge_ontology.py",
            "risk": "medium",
            "instructions": "Manual implementation required for this suggestion type.",
        }


def add_suggestions_from_patterns(
    collection_id: str = "default",
    *,
    include_llm: bool = False,
    max_llm_suggestions: int = 5,
) -> List[Dict[str, Any]]:
    """Generate ontology suggestions from detected patterns.

    Tier 1: Rule-based analysis of OntologyPatterns (always).
    Tier 2: LLM-driven semantic suggestions (opt-in via include_llm=True).

    For LLM-powered suggestions standalone, call:
      POST /ontology/suggestions/semantic  (uses knowledge_evolution_llm.generate_semantic_suggestions)
    """
    from core.harness.knowledge.knowledge_validator import detect_ontology_patterns
    patterns = detect_ontology_patterns(collection_id)

    new_suggestions = []
    sid_counter = int(_time.time() * 1000)

    # Tag clusters → new_class suggestions
    for tc in patterns.tag_clusters[:10]:
        if tc["count"] >= 3:
            sid_counter += 1
            new_suggestions.append({
                "id": f"sug_{sid_counter}",
                "type": "new_class",
                "status": "pending",
                "description": f"高频概念: {tc['root_tag']} ({tc['count']}次)",
                "rationale": f"Tag '{tc['root_tag']}' appears {tc['count']} times across pages. May warrant a dedicated ontology class.",
                "implementation": f"Add new class for '{tc['root_tag']}' to CLASSES list",
                "confidence": min(0.9, 0.5 + tc["count"] * 0.05),
                "impact": {"affected_classes": [], "affected_pages": tc["count"]},
                "risk": "low",
                "generated_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            })

    # Category gaps → deprecate_class suggestions
    for cg in patterns.category_gaps:
        sid_counter += 1
        new_suggestions.append({
            "id": f"sug_{sid_counter}",
            "type": "deprecate_class",
            "status": "pending",
            "description": f"空壳类: {cg['label']} (categories: {cg['categories']})",
            "rationale": cg["reason"],
            "implementation": f"Consider removing or reclassifying '{cg['label']}' since no wiki pages use its categories",
            "confidence": 0.7,
            "impact": {"affected_classes": [cg["class_uri"]], "affected_pages": 0},
            "risk": "low",
            "generated_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        })

    # Dangling references → rename_field suggestions
    for dr in patterns.dangling_references[:5]:
        if dr["variant_exists"]:
            sid_counter += 1
            new_suggestions.append({
                "id": f"sug_{sid_counter}",
                "type": "rename_field",
                "status": "pending",
                "description": f"引用变体: '{dr['references']}' → '{dr['variant_suggestion']}'",
                "rationale": f"Page '{dr['page'][:40]}' references '{dr['references'][:40]}' but the canonical title is '{dr['variant_suggestion'][:40]}'",
                "implementation": f"Update related/contradictions field on affected pages to use canonical title",
                "confidence": 0.85,
                "impact": {"affected_classes": [], "affected_pages": 1},
                "risk": "low",
                "generated_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            })

    # Merge existing suggestions with new ones (dedup by id AND by description+type for resolved ones)
    existing = load_pending_suggestions(collection_id)
    existing_ids = {s.get("id") for s in existing}
    # Skip new suggestions whose description+type already has a resolved (accepted/rejected) entry
    resolved_descriptions = {
        (s.get("description"), s.get("type"))
        for s in existing if s.get("status") in ("accepted", "rejected")
    }
    # Also track ALL seen descriptions (to dedup within this generation)
    all_descriptions = {(s.get("description"), s.get("type")) for s in existing}
    new_unique = []
    for s in new_suggestions:
        if s["id"] in existing_ids:
            continue
        desc_key = (s.get("description"), s.get("type"))
        if desc_key in resolved_descriptions or desc_key in all_descriptions:
            continue
        all_descriptions.add(desc_key)
        new_unique.append(s)
    merged = existing + new_unique

    if merged != existing:
        save_suggestions(merged, collection_id)

    # Tier 2: LLM-driven semantic suggestions (opt-in)
    if include_llm:
        try:
            import asyncio as _asyncio
            from core.harness.knowledge.knowledge_evolution_llm import generate_semantic_suggestions
            llm = _asyncio.run(
                generate_semantic_suggestions(
                    collection_id,
                    max_suggestions=max_llm_suggestions,
                )
            )
            merged_ids = {s.get("id") for s in merged}
            for s in llm:
                sid = s.get("id", "")
                if sid and sid not in merged_ids:
                    merged.append(s)
        except Exception:
            logger.warning("LLM-driven suggestions generation failed for %s", collection_id, exc_info=True)

    return merged


def check_key_discrimination(
    title: str, summary: str = "", *, collection_id: str = "default"
) -> Tuple[bool, List[str]]:
    u"""A8: Check that a new entity's key has sufficient discrimination from existing ones.

    Uses cosine similarity of hash embeddings (zero-dependency, deterministic).
    Returns (ok, warnings) — ok=False means similarity > 0.85 with an existing entity.

    From Neuron 2025 KV-memory paper: hippocampus enforces 'repulsion' to maximize
    key distinctness. This is the computational equivalent.
    """
    from core.harness.knowledge.embedder import hash_embed, cosine_similarity
    from core.harness.knowledge.knowledge_abox_builder import _scan_wiki_pages

    warnings = []
    text = f"{title}: {summary}" if summary else title
    new_vec = hash_embed(text, dim=128)

    existing = _scan_wiki_pages(collection_id=collection_id)
    for page in existing:
        existing_title = str(page.get("title", ""))
        if existing_title == title:
            continue  # same title → replacement, not duplication
        existing_text = f"{existing_title}: {str(page.get('summary', ''))[:200]}"
        existing_vec = hash_embed(existing_text, dim=128)
        sim = cosine_similarity(new_vec, existing_vec)
        if sim > 0.85:
            warnings.append(
                f"A8: '{title}' similarity {sim:.2f} with existing '{existing_title}'. "
                f"Consider using existing page or merging."
            )

    return len(warnings) == 0, warnings


def check_schema_readiness(collection_id: str = "default"):
    """Scan all wiki pages and report ERROR-mode schema compliance.

    Returns a readiness report showing which pages would be rejected
    if AIPLAT_WIKI_SCHEMA_MODE=error were enabled.
    """
    from core.harness.knowledge.wiki_engine import search_pages, read_page
    all_pages = search_pages(limit=10000, collection_id=collection_id)

    passing = []
    failing = []
    missing_fields: Dict[str, int] = {}

    for p in all_pages:
        # Read full page to get body
        full = read_page(p["title"], collection_id=collection_id) or {}
        page_data = {
            "title": full.get("title", p.get("title", "")),
            "category": full.get("category", p.get("category", "entities")),
            "summary": full.get("summary", p.get("summary", "")),
            "body": full.get("body", ""),
            "tags": full.get("tags", p.get("tags", [])),
            "related": full.get("related", p.get("related", [])),
            "contradictions": full.get("contradictions", p.get("contradictions", [])),
            "source_articles": full.get("source_articles", p.get("source_articles", [])),
            "relationships": full.get("relationships", p.get("relationships", [])),
        }
        result = validate_page_against_schema(page_data, mode="error")

        if result.is_valid:
            passing.append({
                "title": p["title"],
                "category": p.get("category", ""),
                "class": result.class_label,
            })
        else:
            failing.append({
                "title": p["title"],
                "category": p.get("category", ""),
                "class": result.class_label,
                "missing": result.missing_required,
                "suggestion": result.suggestion,
            })
            for f in result.missing_required:
                missing_fields[f] = missing_fields.get(f, 0) + 1

    readiness = len(passing) / max(1, len(passing) + len(failing)) * 100

    return {
        "collection_id": collection_id,
        "total_pages": len(all_pages),
        "passing": len(passing),
        "failing": len(failing),
        "readiness_pct": round(readiness, 1),
        "ready_for_error_mode": len(failing) == 0,
        "top_missing_fields": sorted(missing_fields.items(), key=lambda x: -x[1])[:10],
        "failing_pages": failing[:20],  # first 20 failures
        "passing_pages": passing if len(passing) <= 20 else passing[:20],
    }


# ══════════════════════════════════════════════════════════════
# K3 Synonym Governance — SynonymMap (术语治理)
# ══════════════════════════════════════════════════════════════

_SYNONYM_MAP = None  # Optional[Dict[str, str]] — {synonym → canonical_term}


def load_synonyms(path: str = "") -> Dict[str, str]:
    """Load synonym groups from YAML. Returns {synonym → canonical_term}.

    Loads from ~/.aiplat/synonyms.yaml by default.
    Each group's first term is the canonical/preferred label.
    """
    global _SYNONYM_MAP
    if _SYNONYM_MAP is not None:
        return _SYNONYM_MAP

    import os as _os
    import yaml as _yaml
    from pathlib import Path as _P

    file_path = path or str(_P(_os.getenv("AIPLAT_HOME", _P("~").expanduser() / ".aiplat")) / "synonyms.yaml")
    if not _P(file_path).exists():
        _SYNONYM_MAP = {}
        return {}

    with open(file_path, "r", encoding="utf-8") as f:
        data = _yaml.safe_load(f)

    _SYNONYM_MAP = {}
    for group in (data or {}).get("groups", []):
        terms = group.get("terms", [])
        if len(terms) >= 2:
            canonical = terms[0]
            for syn in terms[1:]:
                _SYNONYM_MAP[syn.lower()] = canonical
            _SYNONYM_MAP[canonical.lower()] = canonical  # self-map

    return _SYNONYM_MAP


def expand_query_with_synonyms(query: str) -> List[str]:
    """Expand a search query with synonym variants (bidirectional).

    Both synonyms → canonical AND canonical → synonyms expansions.
    Returns list of [original_query, expansions, ...] for OR-matching.
    """
    synonyms = load_synonyms()
    if not synonyms:
        return [query]

    variants = [query]
    # Build reverse map: canonical → [synonyms]
    canonical_groups: dict = {}
    for syn, canonical in synonyms.items():
        canonical_groups.setdefault(canonical, []).append(syn)

    # Check each word in query
    words = query.split()
    for word in words:
        wl = word.lower()
        # If this word is a canonical term, add queries with each synonym
        if wl in canonical_groups:
            for syn in canonical_groups[wl]:
                variants.append(query.replace(word, syn[:20]))
        # If this matches a synonym, add query with canonical
        if wl in synonyms and synonyms[wl] != wl:
            variants.append(query.replace(word, synonyms[wl][:20]))

    return list(set(variants))  # dedup


def reset_synonyms() -> None:
    global _SYNONYM_MAP
    _SYNONYM_MAP = None
