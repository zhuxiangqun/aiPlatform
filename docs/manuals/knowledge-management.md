# aiPlatform 知识管理 — 完整指南

> 版本: 1.1 · 2026-07-19  
> 适用: aiPlatform v2.6+  
> 入口: 管理端 → 知识中心 → 管线总览（`/knowledge/overview`）  
> 🆕 v2.6: 本体编辑器 + 角色视图 + 流程编排 + SLA 监控 + 术语消歧

---

## 目录

1. [知识管线概览](#一知识管线概览)
2. [原始资料层](#二原始资料层)
3. [本体模型](#三本体模型)
4. [向量知识库](#四向量知识库)
5. [LLM Wiki](#五llm-wiki)
6. [RAG 检索](#六rag-检索)
7. [质量反馈闭环](#七质量反馈闭环)
8. [快速上手](#八快速上手)
9. [运维与诊断](#九运维与诊断)
10. [常见问题](#十常见问题)

---

## 一、知识管线概览

aiPlatform 的知识系统是一个 6 阶段管线，从原始资料进入，经过本体模型的结构化处理，最终服务于 RAG 检索，并通过质量反馈形成自演进闭环。

```
原始资料 → 本体模型 → 向量知识库 + LLM Wiki → RAG 检索 → 质量反馈
   ↑                                                    │
   └──────────── ① 摄入          ② 结构化              │
                                                       │
   ┌───────────────────────────────────────────────────┘
   └───────── ③ 索引   ④ 合成   ⑤ 检索   ⑥ 闭环
```

### 各阶段职责

| 阶段 | 组件 | 输入 | 输出 | LLM 调用？ |
|:---:|------|------|------|:---:|
| ① 原始资料 | DocumentParser | PDF/Word/HTML/MD | StructuredChunk[] | 否 |
| ② 本体模型 | OntologyEngine (3 Phase) | StructuredChunk[] + 域 YAML | 实体/关系 → GraphIndex + Wiki 分类 | Phase 2 (PropertyExtractor, LLM) |
| ③ 向量知识库 | InfraEmbeddingAdapter + FTS5 | 分类后的 Wiki 页面 | 语义向量 + 全文索引 | 否 |
| ④ LLM Wiki | KnowledgeSynthesizer + WikiEngine | GraphIndex 实体/关系 | 推理链/事实卡/跨文档结论 → Wiki 页面 | ActiveSynthesis 可选 |
| ⑤ RAG 检索 | DomainRouter + CRAG + WikiPageRetriever | 用户查询 | 带来源的答案 | HyDE level 3 |
| ⑥ 质量反馈 | HallucinationTracker + CandidatePool + ActiveSynthesis | ⑤的输出 + 用户信号 | 知识缺口 → 自动补充 | ActiveSynthesis |

### 核心原则

1. **本体驱动（异步最终一致性）**：逻辑上所有原始资料必须经过 OntologyEngine 的结构化处理。引擎管线作为异步后台任务运行，采用最终一致性模型：
   - ClassMapper（零 LLM）打粗粒度标签后，**先行落地基础向量索引保证检索可用**
   - PropertyExtractor（LLM）+ GraphBuild 作为**增强管线异步运行**
   - 管线崩溃/超时时：**基础索引仍可服务**，RAG 不会完全不可用
   - 增强完成后：覆盖更新向量 + 更新 Wiki 页面
2. **配置驱动**：所有行为分叉来自 YAML 配置（类/关系/状态机/推理规则），零硬编码业务逻辑。
3. **多路检索**：RAG 同时走 Wiki(语义)、FTS5(关键词)、GraphIndex(实体边验证)三条路径，CRAG 3 级退回。
4. **自动闭环**：HallucinationTracker 检测不忠实回答 → FeedbackRadar 检测用户隐式信号 → CandidatePool 积累 → N≥3 触发 ActiveSynthesis 自动补知识。

---

## 二、原始资料层

### 2.1 支持格式

| 格式 | 解析器 | 说明 |
|------|--------|------|
| PDF | DocumentParser (MinerU / Tesseract) | 表格保留为 StructuredTable，不展平 |
| DOCX/PPTX | DocumentParser (python-docx / python-pptx) | 保留标题层级 |
| HTML | DocumentParser (BeautifulSoup) | 保留结构 |
| Markdown | DocumentParser (内置) | 保留 heading 路径 |
| TXT | DocumentParser (内置) | 纯文本 |
| 图片 (png/jpg) | DocumentParser (OCR 软依赖) | 图像 OCR 提取文本 |
| 视频 (mp4/avi/mov) | DocumentParser (faster-whisper) | 转写+帧提取 |

外部数据源（通过 DataSource 抽象层连接，不移动数据）：

| 类型 | 连接器 | 端点 |
|------|--------|------|
| SQL | SQLDataSource (PostgreSQL/MySQL/SQLite) | `POST /api/core/ontology/datasources` |
| API | APIDataSource (REST) | `POST /api/core/ontology/datasources` |
| File | FileDataSource (CSV/JSON/Excel) | `POST /api/core/ontology/datasources` |

### 2.2 上传方式

| 方式 | 入口 | 端点 |
|------|------|------|
| 页面上传 | 知识中心 → 原始资料 | `POST /api/platform/apps/fde/ingest` |
| Vault 文件浏览器 | 知识中心 → 原始资料 | VaultBrowser 组件 |
| API 上传 | 外部系统 | `POST /api/core/kb/ingest` |
| URL 导入 | 知识中心 | `POST /api/core/kb/ingest-url` |
| 数据源连接 | 知识中心 → 本体模型 → 外部数据源 | `POST /api/core/ontology/datasources` |

### 2.3 DocumentParser 输出

```python
@dataclass
class StructuredChunk:
    id: str              # "chunk-0"
    text: str            # chunk 文本
    heading_path: list   # ["第一章", "1.1 概述"]
    page_num: int        # 页码
    entities: list       # NER 实体候选
    metadata: dict       # 含 tables (StructuredTable[])
```

---

## 三、本体模型

### 3.1 位置

**管理入口**：知识中心 → 本体模型（`/infra/ontology`）  
📗 详细的 CRUD 操作指南 → [本体模型管理使用手册](ontology.md)

### 3.2 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| ClassMapper | `ontology_engine/class_mapper.py` | 关键词倒排索引 → T-Box 类标签（零 LLM） |
| PropertyExtractor | `ontology_engine/property_extractor.py` | LLM 并行提取结构化属性 |
| EntityResolver | `ontology_engine/entity_resolver.py` | 编辑距离 + 共现 + 结构上下文 → 消歧合并 |
| StateMachine | `ontology_engine/state_machine.py` | YAML 配置驱动的状态评估（v2.6: 动态阈值 + 时序触发器） |
| GraphIndex | `ontology_engine/graph_index.py` | SQLite 实体-关系图存储 |
| KnowledgeSynthesizer | `ontology_engine/knowledge_synthesis.py` | 图 → Wiki 页面合成 |
| **Ontology Editor** 🆕 | `platform/apps/ontology_editor/` | 可视化本体 CRUD，低代码建模，NL→YAML 生成 |
| **Role View** 🆕 | `harness/knowledge/role_view.py` | 职责维度：角色视角术语定义 + 字段/类可见性过滤 |
| **Process Orchestrator** 🆕 | `harness/knowledge/process_orchestrator.py` | 跨实体业务流程编排 (Order→Picking→Shipment) |
| **SLA Monitor** 🆕 | `harness/knowledge/sla_monitor.py` | 时序触发器后台监控，超时自动升级 |
| **Term Resolver** 🆕 | `harness/knowledge/term_resolver.py` | 跨域术语消歧：同名异义 + 同义异名检测 |

### 3.3 本体建模流程

1. **创建域** — 定义 `domain_id`、名称、描述
2. **定义类 (T-Box)** — 每个类有 `required_fields`、`optional_fields`、枚举值
3. **定义关系** — `domain` 类 ← `relation` → `range` 类，支持传递/对称
4. **定义状态机**（可选）— `from → to` 转换规则 + trigger 条件 + side_effects
5. **上传文档** — 触发 OntologyEngine 管线
6. **验证** — 查看验证报告的覆盖率

### 3.4 OntologyEngine 管线（3 个 Phase）

引擎实际按 3 个 Phase 组织，其中 Phase 3 包含 16 个串行子步骤：

```
Phase 1 (并行, 无LLM):  Classify → Table Context
Phase 2 (并行, LLM):     Extract (asyncio.gather — 唯一 LLM 调用的阶段)
Phase 3 (串行, 确定性):  Validate → Dedup → Build → SourceTrace
    → EntityResolve → Indicators → StateMachine → Reviews
    → RelationDetect → GraphBuild → Inference → CaseNodes
    → KnowledgeSynthesis (图→Wiki页面)
```

### 3.5 外部数据源桥接

可将 SQL 数据库表直接映射为本体实例（无需移动数据）：

```yaml
classes:
  Supplier:
    sql_mapping:
      source: erp_db
      table: suppliers
      key_column: supplier_id
      column_map:
        name: company_name
        category: supplier_type
```

支持 SQL (PostgreSQL/MySQL/SQLite)、REST API、CSV/JSON/Excel 三种连接器。

### 3.6 域 YAML 示例

```yaml
name: "智能锁安装维保"
namespace: "http://aiplat.local/ontology/lock-service/"
version: "1.0.0"

classes:
  InstallOrder:
    label: 安装工单
    required_fields: [order_id, customer_name, device_model, status]
    optional_fields: [address, scheduled_date, technician, notes]
    states:
      default: pending
      enum:
        - name: pending
          label: 待派单
        - name: assigned
          label: 已派单
        - name: completed
          label: 已完成
      transitions:
        - from: pending
          to: assigned
          trigger:
            type: relation_exists
            relation: assigned_to

object_properties:
  - name: assigned_to
    label: 派单给
    domain: [InstallOrder]
    range: [Technician]
```

### 3.7 Ontology Editor 可视化编辑 (v2.6 新增)

管理端新增**本体编辑器**（`/ontology-editor`），支持：

| 功能 | 说明 |
|------|------|
| 域 CRUD | 创建/编辑/删除域，写回 `~/.aiplat/ontologies/{id}.yaml` |
| 类 CRUD | 可视化管理 classes、states、transitions、side_effects |
| NL→YAML | 自然语言描述业务概念 → LLM 自动生成 class 定义草案 |
| 角色视图 | 为不同岗位（计划员/仓管员）定义术语含义和字段可见性 |
| 流程编排 | 跨实体业务流程定义（Order→Picking→Shipment→Invoice） |
| 即时发布 | publish → YAML 写回 + 缓存失效 + 规则版本快照 |
| 监控面板 | 状态分布、瓶颈分析、SLA 违约列表 |

**对比手写 YAML**：
- 手写：修改 `~/.aiplat/ontologies/{domain}.yaml` → 手动重启
- 🆕 编辑器：UI 表单 → publish → 自动写回 + 热加载

---

## 四、向量知识库

### 4.1 位置

**查看入口**：知识中心 → 向量知识库（`/platform/kb?tab=documents`）

### 4.2 组件

| 组件 | 职责 |
|------|------|
| InfraEmbeddingAdapter | 将 Wiki 页面文本向量化（sentence-transformers） |
| FTS5 全文索引 | SQLite FTS5 全文搜索索引 |
| KB Store | 文档/Spec/知识原子持久化 |

### 4.3 索引流程

1. OntologyEngine 处理完毕 → Wiki 页面已分类（带有类标签）
2. InfraEmbeddingAdapter.embed(page_text) → 768 维向量
3. `vectors.json` 缓存 + FTS5 全文索引更新
4. 检索时：余弦相似度 + FTS5 关键词双路 → RRF 融合排序

### 4.4 检索权重配置

每个域可通过 `GovernorConfig.composite_weights` 独立配置复合评分权重：

| 权重项 | 默认值 | 说明 |
|--------|:---:|------|
| raw_score | 0.55 | 原始检索相关性权重 |
| freshness | 0.15 | 文档时间衰减权重 |
| credibility | 0.15 | 来源可信度权重（基于文献等级） |
| density | 0.15 | 信息密度权重 |

配置示例（在域 YAML 或 registry.json 中覆盖）：

```json
{
  "composite_weights": {
    "raw_score": 0.40,
    "freshness": 0.30,
    "credibility": 0.10,
    "density": 0.20
  }
}
```

检索路由本身还有 `AIPLAT_WIKI_BOOST` 环境变量（默认 1.1，Wiki 路径提权系数）。

---

## 五、LLM Wiki

### 5.1 位置

**编辑入口**：知识中心 → LLM Wiki（`/platform/kb?tab=wiki`）

### 5.2 Wiki 页面生成方式

| 方式 | 触发 | 说明 |
|------|------|------|
| **知识合成** | OntologyEngine Phase 8 | GraphIndex 实体 → 推理链/事实卡/跨文档结论 |
| **手动创建** | Wiki 编辑器 | FDE 或知识管理员手动编写 |
| **ActiveSynthesis** | CandidatePool N≥3 | LLM 驱动的 STORM 式知识生成（需 enable） |
| **自动策展** | wiki_auto_update | KB 文档变更时自动增量更新 Wiki |

### 5.3 Wiki 页面结构

每个 Wiki 页面以 Markdown 格式存储，包含 `frontmatter`：

```yaml
---
title: "智能锁安装流程"
source_instances: [entity1, entity2]
synthesis_type: "reasoning_chain"
domain_id: "lock-service"
class: "InstallOrder"
---
# 智能锁安装流程
...
```

`source_instances` 是知识合成版本锁的关键——当源实体更新时，合成页面自动标记为待复查。

### 5.4 Wiki 健康检查

Wiki 引擎提供健康报告：

| 指标 | 说明 |
|------|------|
| total_pages | 页面总数 |
| dead_links | 死链数 |
| orphan_pages | 孤立页面（无入链/出链） |
| contradictions | 矛盾声明数 |
| health_score | 综合健康分 (0-100) |

---

## 六、RAG 检索

### 6.1 位置

**质量查看入口**：知识中心 → RAG 检索（`/platform/kb?tab=eval`）

### 6.2 检索路由

```
用户查询
  ↓
DomainRouter.classify(query)   ← 3 层级联：标签倒排 → 向量余弦 → LLM 二分类
  ↓
  ├─ WikiPageRetriever (语义检索, collection_id 路由)
  ├─ GraphIndex 遍历 (实体边验证)
  └─ FTS5 关键词检索
  ↓
CRAG 3 级退回:
  Level 1: 本体优先检索 (target_class 过滤)
    ↓ <100 字
  Level 2: FTS5 关键词
    ↓ <50 字
  Level 3: HyDE 假设答案 → 重检
  ↓
HallucinationTracker (Jaccard + GraphIndex 验证)
  ↓
回答 + 来源标注
```

### 6.3 RAG 质量指标

| 指标 | 计算方式 | 阈值 |
|------|---------|:---:|
| 忠实度 (faithfulness) | 支持声明 / 总声明 | ≥0.7 |
| 回答相关度 (relevancy) | 基于 HallucinationTracker 质量分布 | ≥0.7 |
| 检索精度 (retrieval_precision) | 质量门通过率 | ≥0.8 |
| 用户放弃率 (abandon_rate) | FeedbackRadar 检测 | ≤0.1 |
| 重试率 (repeat_query_rate) | 同 query 重复次数 | ≤0.15 |

---

## 七、质量反馈闭环

### 7.1 闭环流程

```
RAG 回答
  ↓
HallucinationTracker 自动检测不忠实回答
  ↓
FeedbackRadar 检测用户隐式信号（放弃/重复/负面）
  ↓
知识缺口检测 (knowledge_gap_detector)
  ↓
CandidatePool.submit(gap) → 去重 + 冲突检测
  ↓
N ≥ 3 独立来源 + 无冲突 + GraphIndex 验证
  ↓
ActiveSynthesis → LLM 生成 Wiki 草稿
  ↓
FDE 审核确认 → 写回知识库
  ↓
本体模型增量更新 → 向量重新索引 → 检索质量提升
```

### 7.2 关键组件

| 组件 | 文件 | 职责 |
|------|------|------|
| HallucinationTracker | `evaluation/hallucination_tracker.py` | 声明提取 → Jaccard 相似度 + GraphIndex 边验证 → faithfulness 0-1 |
| FeedbackRadar | `learning/feedback_radar.py` | 5 种隐式信号检测（边界缺失/方向错误/信息过载/目标漂移/信号冷却） |
| RAGDiagnosticsCollector | `evaluation/rag_diagnostics_collector.py` | 3 数据源聚合 (Hallucination + Feedback + Retrieval) + 异常检测 |
| CandidateKnowledgePool | `knowledge/candidate_pool.py` | FDE 反馈 → normalize + dedup + 语义冲突检测(>100°, embedding; 关键词 fallback) → N≥3 触发 |
| ActiveSynthesis | `knowledge/active_synthesis.py` | LLM 驱动的知识合成（需 `AIPLAT_ACTIVE_SYNTHESIS_ENABLED=true`） |
| EvolutionEngine | `evolution_engine.py` | 夜间 6 步进化管线（模式分析→Skill 审批→裁剪→回归检测→淘汰→微调触发） |

### 7.3 FDE 反馈 → 候选池

FDE 在现场澄清对话中发现的知识缺口自动进入候选池。详细流程和运维操作参见 **[FDE 运维手册](./fde/03-fde-operations.md#四fde--知识库反馈闭环)**。

**简要流程**：FDE 对话 → 检测缺失概念 → CandidatePool 标准化去重 → N≥3 触发自动合成 → 审核 → 发布。

---

## 八、快速上手

### 8.1 创建第一个知识域（5 分钟）

1. 打开知识中心 → 本体模型 → 点击 **🤖 智能生成**
2. 填写域名和关键词描述（如：`lock-service` + "智能锁 安装工单 设备型号 故障类型"）
3. AI 自动生成 YAML（类 + 关系 + 状态机）
4. 点击 **💾 保存并注册**
5. 回到原始资料页，上传 1-2 份相关文档
6. 回到本体模型，运行引擎管线（classify-all → build-instances）
7. 打开 RAG 检索页，尝试提问

### 8.2 常用操作速查

| 操作 | 入口 |
|------|------|
| 上传文档 | 原始资料 → 点击上传 |
| 创建本体类 | 本体模型 → 选中域 → + 类 |
| 定义状态机 | 本体模型 → 类定义下 → 状态机编辑 |
| 查看知识图谱 | 本体模型 → 🕸️ 图 Tab |
| 编辑 Wiki | LLM Wiki → 选择 collection → 编辑 |
| 查看 RAG 质量 | RAG 检索 → 查看健康分 |
| 查看知识缺口 | 质量反馈 → 缺口面板 |
| 触发知识合成 | 本体模型 → 🧬 合成 |

---

## 九、运维与诊断

### 9.1 相关诊断检查

| 检查项 | 位置 | 监控什么 |
|--------|------|---------|
| wiki_health | 知识中心 Wiki 健康概览 | 死链/孤立/矛盾 |
| wiki_content_quality | 知识中心 Wiki 健康概览 | 低质量页面数 |
| rag_quality | RAG 检索页 + 诊断中心卡片 | 忠实度/精度/放弃率 |
| doc_sync | 诊断中心 (doc_sync) | CAPABILITIES.md 同步 |

### 9.2 性能指标

| 指标 | 目标 | 检测 |
|------|:---:|------|
| 引擎管道延迟 P95 | <60s | `benchmark_ontology.py` |
| 图遍历 P95 | <500ms | `benchmark_traversal.py` |
| 检索召回 Recall@10 | >85% | `eval_retrieval.py` |
| 置信度校准 ECE | <0.10 | `eval_calibration.py` |

---

## 十、常见问题

### 10.1 "0 个节点 · 0 个实例"

**原因**：未上传文档，或上传后未运行引擎管线。

**解决**：
1. 确认已上传文档到对应域
2. 运行 `classify-all → build-instances → build-edges`
3. 检查验证报告

### 10.2 "检索不到期望的结果"

**原因**：检索阈值过高，或实体消歧错误。

**解决**：
1. 调低域卡片的**检索阈值**（0.25 → 0.15）
2. 打开**子类展开**开关
3. 增加**跨域降级**数量

### 10.3 "RAG 忠实度一直为 0"

**原因**：没有进行过知识库问答（没有数据）。

**解决**：在知识库问答入口（MaterialsChat）进行几次对话后，24h 内会生成质量数据。

### 10.4 "状态机没有触发"

**原因**：实体不满足 trigger 条件。

**解决**：
1. 使用传播模拟手动验证 trigger 条件
2. 检查关系是否存在于图数据中

### 10.5 "知识缺口面板为空"

**原因**：`AIPLAT_ACTIVE_SYNTHESIS_ENABLED` 未开启。

**解决**：设置 `AIPLAT_ACTIVE_SYNTHESIS_ENABLED=true`，然后在 FDE 对话中进行几次澄清。

---

*最后更新: 2026-07-18 · 版本: 1.0*
