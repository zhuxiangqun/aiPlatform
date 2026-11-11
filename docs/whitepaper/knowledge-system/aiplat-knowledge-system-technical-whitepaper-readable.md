# aiPlat 知识体系技术白皮书（可读版）

> **版本**：v2.0 · 2026-11-11  
> **性质**：技术白皮书 / 目标架构规范  
> **状态**：Proposed；后续设计与实现以此为准，变更走 ADR  
> **范围**：企业知识体系的模型、架构、摄入、本体、事实、Wiki、索引、检索、安全、评测与治理  
> **说明**：本文是可读版，正文不含 JSON/SQL；字段、API、数据结构见《工程附录》。  
> **诚实边界**：不宣称“通用、无范围、无证据”的 RAG 准确率；允许范围限定、可复现的 benchmark 结论。不把 Wiki 当事实源，不以白皮书代替实现与验证。

---

## 阅读指南

| 读者 | 建议阅读 |
|---|---|
| 决策者 | 摘要、1–4、12–14、结论 |
| 架构师 | 全篇；需要细节时查工程附录 |
| 工程师 | 第 5–11 章 + 工程附录 |
| 安全/合规 | 第 12、14、15 章 |

**一句话：**

> 正文讲“为什么这样设计、各层职责是什么”；工程附录讲“字段怎么定义、接口长什么样”。

---

## 摘要

企业知识系统的核心矛盾不是“文档太多”，而是：

> **知识没有稳定结构、没有可追溯证据、没有可持续维护机制。**

传统 RAG 每次查询都从原始文档重新检索、重新拼接，知识不会积累；纯知识图谱需要大量人工建模，难以覆盖长尾；纯 LLM Wiki 可读、可维护，但容易把合成内容误当事实。

本白皮书提出 **OG-CKS（Ontology-Governed Compiled Knowledge System，本体治理的编译式知识系统）**：

- **Raw sources**：不可变的事实源；
- **Ontology**：概念、关系、公理、约束的 schema；
- **Fact Store**：本体约束下、带证据的规范事实；
- **Wiki**：人类可读的编译视图；
- **Indexes**：FTS/Vector/Graph，可选、可重建；
- **Knowledge Gateway**：统一查询、融合、冲突裁决与引用。

核心主张：

1. 两个真相层：Raw sources + Ontology-typed Fact Store；
2. Wiki 是读模型，不是事实源；
3. 索引是派生，可重建，不是知识；
4. 本体是 schema/约束，不是一堆 YAML；
5. Gateway 是编排器，不是“三选一”；
6. 所有结论必须可引用；无证据则 abstain；
7. 多租户隔离是硬边界；
8. 知识质量必须可评测、可审计、可回滚。

---

## 1. 知识体系要解决什么问题

企业知识通常散落在：

- 网站、文档、PDF、Office 文件；
- Obsidian/笔记库；
- Git 仓库、代码注释；
- Slack、Confluence、Jira、邮件；
- 数据库、数仓、报表；
- 图片、音频、视频；
- 专家访谈、会议纪要。

问题不是“没有资料”，而是：

| 问题 | 后果 |
|---|---|
| 资料不可追溯 | 回答无法引用，无法审计 |
| 每次查询重推 | 知识不积累，重复劳动 |
| 结构与语义缺失 | 只能关键词/相似度，无法多跳 |
| LLM 合成无约束 | Wiki 可读但可能错 |
| 多入口各自实现 | Agent/UI/Pi 答案不一致 |
| 没有评测 | 不知道好坏，无法改进 |

本白皮书的目标不是“再建一个库”，而是建立一条**可审计的知识生产链**。

---

## 2. 核心模型：两个真相层 + 两个视图

| 层 | 角色 | 是否事实源 |
|---|---|---|
| **Raw sources** | 原始资料快照，不可变 | ✅ 事实源 |
| **Ontology + Fact Store** | schema + 规范事实 | ✅ 事实权威 |
| **Wiki** | 人类可读的编译视图 | ❌ 派生 |
| **Indexes** | FTS/Vector/Graph 检索结构 | ❌ 派生 |

### 2.1 为什么不是“四库并列”

- 本体不是数据库，是 schema；
- Fact Store 不是 Wiki，是事实；
- KG 不是另一个事实源，是 Fact Store 的图投影；
- Wiki 不是事实源，是读模型；
- 向量/FTS 不是知识，是索引。

### 2.2 为什么不是“Gateway 三选一”

Gateway 应该按查询类型**组合**：

- 事实/关系 → Fact Store / KG；
- 概念/综述 → Wiki；
- 精确词 → FTS；
- 模糊语义 → Vector；
- 复杂问题 → 多路融合 + 冲突裁决。

不是“选一个库”，而是“编排多个视图”。

---

## 3. 一页架构

| 层 | 职责 | 关键产物 |
|---|---|---|
| 7 治理 | owner、版本、审核、评测、审计 | 变更记录、claim 边界 |
| 6 查询 | Gateway：路由、融合、冲突、引用 | 答案 + citations |
| 5 视图 | Wiki + Indexes | 可读页、检索索引 |
| 4 事实 | Fact Store | entity/relation/claim/evidence |
| 3 本体 | TBox | 类、关系、公理、状态、约束 |
| 2 原始 | Raw sources | 不可变 snapshot |
| 1 接入 | API/Connector/Upload/Queue | source registry |

### 3.1 写入路径

1. 登记 Source；
2. 生成不可变 Snapshot；
3. 解析/分块；
4. 本体引导抽取；
5. 候选事实；
6. 校验/实体解析；
7. 人审（低置信/冲突）；
8. 写入 Fact Store；
9. 编译 Wiki；
10. 构建索引。

### 3.2 读取路径

1. Gateway 校验 tenant/collection/ACL；
2. 理解查询；
3. Fact-first（结构化）；
4. Wiki（综述）；
5. FTS/Vector（兜底）；
6. Graph（关系）；
7. 融合/冲突裁决；
8. 引用；
9. 回答或 abstain。

### 3.3 关键不变量

- Raw 不可原地修改；
- 每个 fact/claim 有 evidence；
- Ontology 有版本；
- Wiki/Index 可重建；
- 跨租户查询 0 结果；
- 无 citation 不得 published；
- Gateway 是唯一查询入口；
- 冲突显式；
- 未知必须 abstain。

---

## 4. 六个概念，不要混

| 概念 | 是什么 | 不是什么 |
|---|---|---|
| **Ontology** | schema：类/关系/公理/约束 | 不是事实库，不是 Wiki |
| **Fact Store** | 规范事实：entity/relation/claim + evidence | 不是某个数据库产品 |
| **KG** | Fact Store 的图投影/查询视图 | 不是独立事实源 |
| **Graph DB** | 图存储/查询技术 | 不等于 KG |
| **Wiki** | 可读编译视图 | 不是事实源 |
| **Index** | FTS/Vector/Graph 检索结构 | 不是知识 |

### 4.1 “不承诺完全自动本体学习”

- ABox 抽取可以高度自动化；
- TBox（类/关系/公理/schema）不承诺全自动；
- LLM 可以提议候选，但必须经过语料证据、人审、公理校验、版本冻结；
- “不承诺”不是“不自动化”，而是“不把无人值守 TBox 生成当交付承诺”。

### 4.2 “不把 Wiki 可读当知识正确”

- Wiki 可读、结构清晰、链接完整，不等于事实正确；
- Wiki 可能过时、遗漏、被错误合成；
- 正确性靠 evidence + Fact Store + 校验/评测；
- 可读性是产品体验，不是正确性证明。

---

## 5. Raw Sources：原始资料怎么定义

### 5.1 四个概念

| 概念 | 定义 |
|---|---|
| Connector | 抓取/接收资料的适配器 |
| Source | 一份登记的资料实体 |
| Snapshot | 某一时刻的不可变内容 |
| Revision | 同一 Source 的新快照 |

**原则：进入知识系统的必须是 Snapshot，不是“活链接”。**

### 5.2 典型类型

| 类型 | 示例 | 快照形态 |
|---|---|---|
| Web | 官网、文档站、博客 | HTML/文本 + URL + 抓取时间 + hash |
| 文件 | PDF/DOCX/PPTX/XLSX/MD | 原始 bytes + 文件名 + hash |
| Obsidian | 个人/团队 Markdown 库 | 每个 `.md` + frontmatter + 链接 |
| Git | 代码仓库/docs | commit SHA + 文件树 |
| SaaS/API | Slack、Confluence、Jira、邮件 | API 响应 + 时间戳/游标 |
| 数据库 | 业务表、指标 | 查询结果 + schema 版本 + 时点 |
| 多模态 | 图片、音频、视频 | 原始文件 + OCR/转写 + 时间码 |
| 人工 | 访谈、纪要、专家笔记 | 原始记录 + 作者 + 日期 |
| 数据集 | 公开数据、评测集 | 原始包 + 版本 + license |

### 5.3 更新不是覆盖

- 内容变化 → 新 Revision；
- 旧 Snapshot 保留；
- 删除用 tombstone；
- 同名文件不同内容要区分；
- 同一 URL 变化不能覆盖旧页面。

### 5.4 Obsidian 与网站

**Obsidian：**

- 不把正在编辑的 Vault 直接当 raw；
- 每次同步扫描文件、算 hash、变更生成新 Snapshot；
- 保留 frontmatter、双链、附件；
- `[[link]]` 是 Source 内部关系，不直接当事实；
- 手写内容标 `human_authored`，注明作者/时间/审核。

**网站：**

- 抓 HTML + 文本 + 元数据；
- 记录 URL、最终 URL、抓取时间、HTTP 状态、ETag、hash；
- 动态页面保存渲染后快照；
- 不把搜索摘要当原始页面；
- 记录许可/robots/版权。

---

## 6. 本体：知识体系的 schema

### 6.1 TBox 与 ABox

| 层 | 内容 |
|---|---|
| TBox | 类、属性、关系、公理、状态、约束 |
| ABox | 本体约束下的实体/关系/claim 实例 |

本体不是知识库；它是“知识怎么组织”的 schema。

### 6.2 本体怎么构建

1. 标准/专家种子；
2. 代表性语料；
3. LLM/统计提议候选概念/关系；
4. 聚类/归一；
5. 人审；
6. 公理/约束校验；
7. 冻结 v1；
8. 抽取 ABox；
9. 监控漂移；
10. 新版本。

**MUST NOT：**

- 凭空定义无证据；
- 全自动发布；
- 用 Wiki 反哺本体；
- 无版本变更。

### 6.3 校验

- 类型合法性；
- 关系域/值域；
- 基数约束；
- 状态迁移；
- 矛盾检测；
- 孤立实体；
- 来源缺失。

### 6.4 演化

- 版本化；
- 迁移脚本；
- 向后兼容；
- 旧数据标记；
- 重建视图/索引；
- 变更审计。

---

## 7. Fact Store：规范事实层

### 7.1 定义

> **Fact Store 不是某个数据库产品，而是“本体约束下、带证据的规范事实层”。**

可以用关系表、三元组、图数据库、文档库实现；实现方式不是规范，职责才是规范。

### 7.2 存什么

| 记录 | 内容 |
|---|---|
| Entity | id、class、properties、source_refs、confidence、review |
| Relation | from、type、to、valid_from/to、source_refs |
| Claim | subject/predicate/object 或 text、evidence |
| Evidence | source_id、locator、quote、hash |
| Review | reviewer、status、time、notes |
| Revision | before/after、actor、time、reason |
| Conflict | 多值、来源、时间、裁决状态 |

### 7.3 不是什么

- 不是 Ontology（那是 schema）；
- 不是 Wiki（那是读模型）；
- 不是 Vector/FTS（那是索引）；
- 不是 Graph DB（那只是可能实现）；
- 不是日志/事件流（那是变更记录）。

### 7.4 与 KG 的关系

- Fact Store 是规范事实层；
- KG 是 Fact Store 的图投影/查询视图；
- 图数据库可以实现 Fact Store；
- 关系表也可以构建 KG 视图；
- 不要为了“有图”复制一套事实。

### 7.5 强制规则

- 每个 fact/claim 有 evidence；
- evidence 能回到 Raw Snapshot；
- 有 confidence + review_status；
- 支持 temporal validity；
- 支持 conflict，不强行合并；
- 支持 tenant/collection ACL；
- 支持 revision/rollback；
- 支持按 entity/relation/claim/time/source 查询。

---

## 8. Wiki：人类可读的编译视图

### 8.1 定位

Wiki 是 Fact Store 的读模型，不是事实源。

职责：

- 让人读懂；
- 让人审；
- 让人引用；
- 让人发现矛盾；
- 让答案可沉淀。

### 8.2 页面类型

- entity：实体页；
- concept：概念页；
- comparison：对比页；
- overview：综述；
- contradiction：矛盾页；
- answer：人审后归档的答案。

### 8.3 index 与 log

- index：内容目录；
- log：append-only 账本；
- 可 grep、可审计、可版本化。

### 8.4 编译与审核

1. 从 Fact Store 选页面；
2. 生成/更新正文；
3. 插入 citations；
4. 标记冲突/过期；
5. 人审；
6. published。

规则：

- 每个关键断言有 citation；
- 无 citation 不 published；
- Wiki 不写回 Fact Store；
- Wiki 可重建。

---

## 9. 索引：FTS / Vector / Graph

| 索引 | 擅长 | 不擅长 |
|---|---|---|
| FTS | 精确关键词、编号、合同号 | 同义、模糊语义、中文分词 |
| Vector | 语义召回、同义表达 | 精确 ID、可解释性、相似≠正确 |
| Graph | 关系、多跳、影响分析 | 长文本、叙事、歧义 |

原则：

- 索引可重建；
- 索引不是事实源；
- 记录模型/版本；
- 租户隔离；
- 允许最终一致，但可检测滞后。

---

## 10. Gateway：统一查询编排

### 10.1 职责

- 租户/集合/权限；
- 查询理解；
- 路由；
- 多源融合；
- 冲突裁决；
- 引用；
- 降级披露。

### 10.2 查询模式

| 模式 | 用途 |
|---|---|
| structured | 本体/事实查询 |
| wiki | 概念/综述 |
| fts | 精确关键词 |
| vector | 模糊召回 |
| hybrid | 默认组合 |
| graph | 多跳 |
| auto | 路由 |

### 10.3 冲突裁决

> **冲突裁决优先级：raw > fact > wiki > index similarity**

- 冲突显式返回；
- 不静默选一个；
- 无证据 abstain。

---

## 11. Raw 更新时，知识怎么更新

**Raw 不可变，不等于资料不更新。更新 = 新 Snapshot/Revision。**

### 11.1 流程

1. 检测变化；
2. 生成新 Snapshot；
3. diff / 影响分析；
4. 重抽取受影响 facts；
5. 校验 / 冲突 / 人审；
6. 更新 Fact Store；
7. 重编译受影响 Wiki；
8. 重建受影响索引；
9. 失效缓存；
10. 审计。

### 11.2 变更检测

| Source | 方式 |
|---|---|
| Web | 定时抓取 + ETag/Last-Modified + hash |
| 文件/Obsidian | 文件监听/扫描 + hash |
| Git | webhook + commit SHA |
| SaaS/API | webhook/游标 |
| 数据库 | 时点快照/增量查询 |
| 人工 | 新版本/审核 |

### 11.3 删除与矛盾

- 删除 Source → tombstone；
- 受影响 fact 标 retired；
- Wiki 标 stale/deprecated；
- 索引移除或标失效；
- 新资料与旧事实冲突 → 建 Conflict，不自动选边。

### 11.4 自动化等级

| 级别 | 行为 |
|---|---|
| L0 | 只检测，人工处理 |
| L1 | 自动检测 + 影响报告 |
| L2 | 自动重抽取 + 人审后发布 |
| L3 | 低风险自动发布，高风险人审 |
| L4 | 全自动发布（不承诺） |

白皮书要求至少 L1，推荐 L2；L3 仅限低风险域。

---

## 12. 安全与多租户

### 12.1 隔离

- tenant/collection 硬边界；
- 所有表/索引/对象带 tenant_id；
- 跨租户查询 0 结果；
- 共享 ontology 只共享 schema，不共享事实；
- 跨租户负向测试。

### 12.2 数据安全

- 加密 at rest/in transit；
- PII/secret 扫描；
- path allowlist；
- 上传限制；
- 审计；
- 保留/删除/法务 hold。

### 12.3 访问控制

- 角色/属性/对象级；
- Wiki 页面权限；
- Fact/Claim 权限；
- 导出权限；
- 审计所有访问。

---

## 13. 质量、评测与准确率声明

### 13.1 指标

| 层 | 指标 |
|---|---|
| 本体 | 类/关系覆盖、实体解析 P/R、矛盾率 |
| 事实 | 证据覆盖、置信度校准、过期率 |
| Wiki | citation 覆盖、stale 率、孤儿页 |
| 检索 | Recall@k、MRR、context precision |
| 回答 | faithfulness、citation accuracy、abstain 正确率 |
| 隔离 | 跨租户 0 泄漏 |
| 运维 | ingest 成功率、p95、重建耗时 |

### 13.2 准确率不是单一数字

RAG 至少分四层：

- 检索：找没找到；
- 回答：答得对不对、是否被证据支持；
- 引用：引用是否指向正确来源；
- 行为：不知道时是否敢说不知道。

### 13.3 允许的声明

必须同时满足：

1. 绑定 Subject；
2. 绑定数据集与版本；
3. 绑定配置/模型/索引版本；
4. 给出样本量 n；
5. 给出 95% CI；
6. 给出评测日期；
7. 说明适用/不适用范围。

### 13.4 禁止的声明

- “我们的 RAG 准确率 95%”（无数据集/CI/范围）；
- “所有领域都准确”；
- “通过安全/合规认证”；
- 用 Wiki 可读性代替事实正确性；
- 用 Recall 代替 answer correctness；
- 用单次 demo 代替 benchmark。

**结论：不吹“通用准确率”，但要建立“范围限定、可复现、可审计”的评测体系。**

---

## 14. 运维与治理

### 14.1 SLO

- ingest 成功率/延迟；
- query p95；
- citation 命中率；
- freshness；
- 重建耗时；
- 隔离测试通过率。

### 14.2 存储选择

- 小规模：SQLite/FTS/Markdown；
- 大规模：PostgreSQL + PGVector/FAISS + 对象存储；
- 图存储可选：关系表/三元组/图数据库；
- 所有索引可重建。

### 14.3 版本

- ontology version；
- fact schema version；
- embedding model version；
- index version；
- Wiki revision；
- 兼容/迁移。

### 14.4 治理

- 域 owner；
- 数据 owner；
- Wiki reviewer；
- security owner；
- platform owner；
- RFC/ADR；
- 变更/回滚/审计；
- claim 边界。

---

## 15. 采用路线

### Phase 0：基础

- Raw immutable；
- Source registry；
- 持久摄入；
- ontology v0；
- Fact Store；
- Wiki/Index 可重建；
- 单一 Gateway；
- 租户隔离。

### Phase 1：Wiki-first

- 直接 source-to-wiki；
- index/log/lint；
- 引用；
- 人审；
- 答案归档。

### Phase 2：本体/图谱

- TBox 版本化；
- ABox 抽取；
- 实体解析；
- GraphRAG；
- 冲突/时序。

### Phase 3：规模化

- PG/PGVector；
- 多 worker；
- SLO；
- 多模态；
- 联邦知识；
- 认证/审计。

---

## 16. 结论

**本白皮书的核心不是“再建一个知识库”，而是建立一条可审计的知识生产链：**

> Raw → Ontology → Fact → Wiki → Index → Gateway → Citation → Answer

**一句话：**

> 本体定义“怎么理解”，事实库保存“什么是真的”，Wiki 负责“怎么读”，索引负责“怎么找”，Gateway 负责“怎么答且不越界”。

**边界：**

> 不承诺完全自动本体学习；不把 Wiki 可读当知识正确；不宣称通用准确率；不把白皮书当认证。
