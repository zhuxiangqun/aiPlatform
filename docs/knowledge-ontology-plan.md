# aiPlat 知识库本体模型 — 完整设计方案

> 版本：1.0 | 范围：仅覆盖知识域（KB 文档 + Wiki 页面 + 关系）| 不涉及 Agent/Skill/Tool/Pipeline

---

## 1. 设计依据

本体模型不是凭空设计，而是基于三个支柱：

### 支柱一：自下而上 — 从现有 Schema 提取

```
来源 1: FRONTMATTER_FIELDS (wiki_engine.py:31-36)
  → 类: WikiPage, WikiRelation
  → 属性: title, category, tags, summary, source_articles, contradictions, relationships

来源 2: RELATIONSHIP_TYPES (wiki_engine.py:39-48)  
  → 属性子类: cites, supports, contradicts, example_of, extends, derived_from, parent

来源 3: KBDocument (platform/kb/db.py:24-37)
  → 类: KBDocument
  → 属性: doc_id, source_uri, kind, collection_id

来源 4: KBElement (platform/kb/db.py:73-90)
  → 类: KBElement
  → 属性: type (text/table/image), text, page_idx, doc_id
```

### 支柱二：标准映射 — 对标成熟本体

| 自用名 | 标准映射 | 标准来源 | 为什么选择 |
|--------|---------|---------|-----------|
| `WikiPage`, `ConceptPage` | `skos:Concept` | SKOS | 知识组织系统国际标准(W3C,2009),专门建模概念层级 |
| `parentOf` | `skos:broader` | SKOS | 同标准的概念宽窄关系,附带的传递+非自反+无环约束正是我们需要的 |
| `title`, `summary`, `created_at` | `dc:title/description/created` | Dublin Core | 最基础的元数据标准(ISO 15836), 1995年至今 |
| `cites` | `prov:wasDerivedFrom` | PROV-O | 溯源标准(W3C,2013),精确建模"信息从哪来" |
| `hasSource` | `prov:wasAttributedTo` | PROV-O | 比 wasDerivedFrom 表示更直接的引用链 |
| `KnowledgeAtom` | `crm:E73_Information_Object` | CIDOC-CRM | 文化遗产信息模型(ISO 21127),对不可再分的知识片段有精确定义 |
| `hasAtom` | `crm:P106_is_composed_of` | CIDOC-CRM | 组成关系 |
| `KBDocument` | `foaf:Document` | FOAF | 文档资源 |

### 支柱三：领域定制 — AI 知识库特有语义

```
aiplat:contradicts       — KB 中共有两种矛盾：同文档不同解释、跨文档争议
                           标准本体中无对应 → 自定义
aiplat:is_llm_generated  — LLM 生成 vs 人类编写 → 影响可信度
aiplat:KnowledgeAtom     — 长页面被 LLM 拆分为独立原子 → 非人类创建的知识粒度
aiplat:IngestActivity    — KB ingest 是一个 prov:Activity，有 started_at,ended_at,status
```

---

## 2. T-Box（术语层 — 稳定不变的定义）

### 2.1 类层次 (Class Hierarchy)

```
owl:Thing
└── aiplat:KnowledgeEntity
    ├── aiplat:KnowledgeAtom           — 不可拆分的知识片段
    │   └── property: body (xsd:string)
    │   └── property: extracted_from → KBDocument
    │
    ├── aiplat:CompositeKnowledge      — 由多个原子组成
    │   ├── aiplat:WikiPage            — 标准 Wiki 页面
    │   │   ├── aiplat:ConceptPage     — category="entities"
    │   │   │   └── constraint: ∃hasSource.KBDocument (A1)
    │   │   ├── aiplat:TopicPage       — category="topics"
    │   │   └── aiplat:SourcePage      — 资料摘要页
    │   │       └── constraint: ¬∃cites.WikiPage (A5)
    │   │
    │   └── aiplat:WikiProposal        — 待审批变更提案
    │
    ├── aiplat:KBDocument               — KB 中的原始文档
    │   └── property: doc_id (unique)
    │   └── property: kind (enum: pdf...)
    │   └── property: source_uri (string)
    │   └── property: collection_id (string)
    │
    └── aiplat:WikiRelation             — 页面间关系
        ├── aiplat:CitesRelation        — type="cites"
        ├── aiplat:ContradictsRelation  — type="contradicts"
        ├── aiplat:ParentRelation       — type="parent"
        ├── aiplat:SupportsRelation     — type="supports"
        ├── aiplat:ExtendsRelation      — type="extends"
        └── aiplat:ExampleRelation      — type="example_of"
```

### 2.2 对象属性 (Object Properties)

```
Property: hasSource （prov:wasAttributedTo）
  domain:  aiplat:WikiPage
  range:   aiplat:KBDocument
  语义:    WikiPage 的知识来源于 KB 文档
  约束:    每个 ConceptPage 至少 ∃1 hasSource.KBDocument (A1)

Property: cites （prov:wasDerivedFrom）
  domain:  aiplat:WikiPage
  range:   aiplat:WikiPage
  语义:    当前页面引用目标页面的知识
  特性:    Asymmetric（不对称）

Property: contradicts （aiplat:contradicts）
  domain:  aiplat:WikiPage
  range:   aiplat:WikiPage
  语义:    两页对同一事实给出不可调和的不同描述
  特性:    Symmetric（A contradicts B ⇒ B contradicts A）(A3)

Property: parentOf （skos:broader）
  domain:  aiplat:WikiPage
  range:   aiplat:WikiPage
  语义:    目标页面是源页面的父概念
  特性:    Irreflexive + Asymmetric + Transitive
  基数:    ≤1 parentOf per WikiPage

Property: extends （skos:narrower）
  domain:  aiplat:WikiPage
  range:   aiplat:WikiPage
  语义:    当前页面细化/扩展目标页面的内容
  特性:    是 skos:narrower 的子属性

Property: supports
  domain:  aiplat:WikiPage
  range:   aiplat:WikiPage
  语义:    当前页面为目标页面提供证据支撑

Property: example_of
  domain:  aiplat:WikiPage
  range:   aiplat:WikiPage
  语义:    当前页面是目标概念的具体案例

Property: hasAtom （crm:P106_is_composed_of）
  domain:  aiplat:WikiPage
  range:   aiplat:KnowledgeAtom

Property: transitivelyTouches （推理属性）
  ≡ (cites ∪ parentOf ∪ extends ∪ supports ∪ contradicts)*
  语义:    所有可间接抵达的知识范围
  特性:    Transitive（推理器自动计算，无需手动声明）
```

### 2.3 数据属性 (Data Properties)

```
WikiPage:
  title:        xsd:string  [Functional, 1..1]  — 全局唯一
  summary:      xsd:string  [1..1]             — 200 字内
  body:         xsd:string  [0..1]             — Markdown
  category:     {"entities","topics","contradictions"} [1..1]
  tags:         xsd:string  [0..*]
  version:      xsd:string  [1..1]
  created_at:   xsd:dateTime [1..1]
  updated_at:   xsd:dateTime [1..1]
  is_llm_generated: xsd:boolean [0..1]

KBDocument:
  doc_id:       xsd:string  [Functional, 1..1]
  kind:         {"pdf","pptx","docx","xlsx","csv","md","txt",
                 "json","mp3","mp4","jpg","png"} [1..1]
  source_uri:   xsd:string  [1..1]
  collection_id: xsd:string [0..1]

KnowledgeAtom:
  title:        xsd:string  [1..1]
  body:         xsd:string  [1..1]
  extracted_at: xsd:dateTime [1..1]
```

### 2.4 公理 (Axioms)

```
A1: 概念完整性 (Conceptual Integrity)
    ConceptPage ⊑ (≥1 hasSource.KBDocument)
    
    含义: 每个概念页必须至少关联一个 KB 文档作为来源
    违反: 概念页没有引用任何 KB 文档 → 可能是 LLM 幻觉或缺少资料
    查询: SELECT ?p WHERE { ?p rdf:type aiplat:ConceptPage .
                             FILTER NOT EXISTS { ?p aiplat:hasSource ?d } }

A2: 来源传递 (Source Transitivity)  
    hasAtom(p, a) ∧ derivesFrom(a, d) ⇒ hasSource(p, d)
    
    含义: Wiki 页面的来源继承自其知识原子的来源
    违反: 知识原子的来源未向上传递到页面
    推理: 推理器自动补全 hasSource 边

A3: 矛盾对称性 (Contradiction Symmetry)
    contradicts(p1, p2) ⇔ contradicts(p2, p1)
    
    含义: 矛盾声明必须双向可见
    违反: A 说与 B 矛盾，但 B 没有声明与 A 矛盾
    实现: SymmetricProperty — 推理器自动保证

A4: 层级无环 (Hierarchy Acyclicity)
    ¬∃p1,...,pn: parentOf(p1,p2) ∧ ... ∧ parentOf(pn,p1)
    
    含义: 概念层级不能形成循环
    违反: A 的父概念是 B，B 的父概念是 A → 死循环
    实现: IrreflexiveProperty + AsymmetricProperty — 推理器自动拒绝环

A5: 源页面独立 (Source Page Independence)
    SourcePage ⊑ ¬∃cites.WikiPage
    
    含义: 资料摘要页只摘要原始资料，不引用其他 Wiki 概念
    违反: SourcePage 写了 cites 到其他 Wiki → 分类错误
```

---

## 3. A-Box 构建器（实例层 — 随数据自动重建）

### 3.1 输入数据源

| 序号 | 来源 | 提供什么 |
|:---:|------|---------|
| 1 | `~/.aiplat/wiki/**/*.md` | WikiPage 实例（frontmatter + body） |
| 2 | `~/.aiplat/wiki/index.json` | 全局索引，补充元数据 |
| 3 | `~/.aiplat/kb/tenants/*/kb.sqlite3` | KBDocument 实例（doc_id, kind, source_uri） |
| 4 | `~/.aiplat/wiki/changelog.json` | 增量重建的时间窗口 |

### 3.2 构建流程

```
┌─ Step 1: 扫描 Wiki 目录 ───────────────────────────────────┐
│  for each .md file:                                        │
│    解析 frontmatter → title, category, tags, summary       │
│    解析 body → relations ([[links]]), source_refs          │
│    → 创建 aiplat:WikiPage 实例                             │
│      ├── category="entities" → ConceptPage                 │
│      ├── category="topics" → TopicPage                     │
│      └── 无 cites 出边       → SourcePage (如果符合)       │
│  边构建:                                                   │
│    related[] → cites; contradictions[] → contradicts       │
│    relationships[] → 类型化关系边                           │
│    parentOf → parentOf (验证: ≤1, 无环)                    │
└───────────────────────────────────────────────────────────┘
                           │
┌─ Step 2: 扫描 KB 数据库 ───────────────────────────────────┐
│  SELECT doc_id, source_uri, kind FROM documents            │
│  → 创建 aiplat:KBDocument 实例                             │
│                                                           │
│  交叉验证:                                                 │
│    hasSource 的目标 KBDocument 存在? → ✓                  │
│    hasSource 的目标 KBDocument 不存在? → 标记 invalid_ref │
└───────────────────────────────────────────────────────────┘
                           │
┌─ Step 3: 推理封装 ────────────────────────────────────────┐
│  sync_reasoner_pellet()                                    │
│    → A3: 自动补全对称的 contradicts 边                     │
│    → A4: 自动拒绝 parentOf 环路                            │
│    → A2: 自动推导来源传递                                  │
│    → 传递闭包自动计算                                      │
└───────────────────────────────────────────────────────────┘
```

### 3.3 重建策略

| 触发器 | 范围 | 方法 | 耗时 |
|--------|------|------|:---:|
| `wiki_auto_update()` 完成 | 增量 | `_rebuild_for_doc(doc_id)` — 只重建该 KB 文档相关的 A-Box 片段 | 秒级 |
| `write_page()` 调用 | 增量 | `_rebuild_for_page(title)` — 重建该页 + 所有关联页 | 秒级 |
| `delete_page()` 调用 | 全量 | 删除影响传递闭包 → 必须全部重建 | 分钟级 |
| `POST /ontology/rebuild` | 全量 | 手动触发 | 分钟级 |

---

## 4. 标准本体映射表（完整版）

```
┌──────────────┬──────────────────────┬───────────┬──────────────────────┐
│  aiplat 术语  │ 标准映射              │ 标准来源   │ 标准定义              │
├──────────────┼──────────────────────┼───────────┼──────────────────────┤
│ ConceptPage  │ skos:Concept          │ SKOS      │ 知识组织系统中的概念   │
│ TopicPage    │ skos:Collection        │ SKOS      │ 概念的集合            │
│ parentOf     │ skos:broader           │ SKOS      │ 更宽泛的概念          │
│ extends      │ skos:narrower          │ SKOS      │ 更窄化的概念          │
│ tags         │ skos:related           │ SKOS      │ 语义关联              │
│ title        │ dc:title              │ Dublin Core│ 资源名称             │
│ summary      │ dc:description        │ Dublin Core│ 资源描述             │
│ created_at   │ dc:created            │ Dublin Core│ 创建时间              │
│ updated_at   │ dc:modified           │ Dublin Core│ 修改时间              │
│ body         │ crm:P190_has_symbolic_ │ CIDOC-CRM │ 符号内容              │
│              │     content            │           │                      │
│ KnowledgeAtom│ crm:E73_Information_   │ CIDOC-CRM │ 信息对象              │
│              │     Object             │           │                      │
│ hasAtom      │ crm:P106_is_composed_of│ CIDOC-CRM │ 组成关系              │
│ cites        │ prov:wasDerivedFrom    │ PROV-O    │ 来源推导              │
│ hasSource    │ prov:wasAttributedTo   │ PROV-O    │ 归因                  │
│ KBDocument   │ foaf:Document          │ FOAF      │ 文档资源              │
│ IngestActivity│ prov:Activity        │ PROV-O    │ 活动                  │
│ contradicts  │ aiplat:contradicts     │ 自定义     │ 知识矛盾              │
│ is_llm_gen   │ aiplat:llmGenerated    │ 自定义     │ AI 生成标记            │
└──────────────┴──────────────────────┴───────────┴──────────────────────┘
```

---

## 5. 验证查询

所有查询由推理器在最新 A-Box 上执行，返回结构化结果：

```
Q1: 概念完整性违反 (A1)
    "哪些概念页缺少 KB 来源？"

Q2: 矛盾对称性违反 (A3)
    "哪些矛盾声明只在单方面出现？"

Q3: 层级环路违反 (A4)
    "哪些 parentOf 关系构成了死循环？"

Q4: 分类一致性违反
    "哪些页面在 entities/ 目录但 frontmatter 写 category='topics'？"

Q5: 传递知识网络
    "从页面 X 出发，通过所有关系类型可达哪些页面？"

Q6: 来源影响力
    "哪些 KB 文档被最多的 Wiki 页面引用？"

Q7: 知识缺口
    "KB 中有哪些文档还没被转化为任何 Wiki 页面？"
```

---

## 6. 实施文件清单

| 文件 | 内容 | 行数 |
|------|------|:---:|
| `core/harness/knowledge/knowledge_ontology.py` | T-Box 类/属性/公理定义 | ~120 |
| `core/harness/knowledge/knowledge_abox_builder.py` | 从 Wiki+KB 构建 A-Box | ~150 |
| `core/harness/knowledge/knowledge_validator.py` | 推理器封装 + 7 个验证查询 | ~80 |
| `wiki_engine.py` (修改) | write/delete_page 加增量重建钩子 | +8 |
| `core_facade.py` (修改) | wiki_auto_update 后触发增量重建 | +3 |
| `wiki_health_rules.py` (修改) | OntologyValidationRule | +40 |
| `wiki.py` (修改) | GET /ontology/query + POST /ontology/rebuild | +25 |

总计：~430 行新代码，0 处破坏性修改。

---

## 7. 预期效果

| 维度 | 现在的 Wiki | 实施后 |
|------|:---:|------|
| 创建概念页不填来源 | ✅ 允许 | ❌ 拒绝 (A1) |
| 矛盾只标一边 | ✅ 允许 | ⚠️ 告警 (A3) |
| 父概念形成环 | ✅ 允许 | ❌ 拒绝 (A4) |
| "和 X 相关的所有知识" | related 字段 | 传递闭包全展开 |
| KB 文档已删但 Wiki 还在引用 | 无法发现 | 自动检测 invalid_ref |
| 导出为标准 RDF | ❌ | ✅ owlready2 自带 |
| 被外部知识图谱查询 | ❌ | ✅ SPARQL |
