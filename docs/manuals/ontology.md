# 本体模型管理 — 使用手册

> 版本: 1.2 · 2026-07-19  
> 适用: aiPlatform v2.6+  
> 入口: 打开 /infra/ontology（本体模型） (`/infra/ontology`) | 🆕 编辑器入口: `/ontology-editor`  
> 📘 知识管线总览 → [knowledge-management.md](knowledge-management.md)  
> 🆕 v2.6 新增: 本体编辑器 UI、角色视图、跨实体流程编排、时序 SLA 监控、动态阈值触发器、术语消歧

---

## 本文档范围

本文档聚焦**本体模型的 CRUD 操作**：域管理、类/关系/状态机编辑、引擎运行、验证修复、缺口合成。

知识管线的整体架构（原始资料→本体→向量→Wiki→RAG→反馈闭环）参见 [知识管理完整指南](knowledge-management.md)。

## 目录

- [一、概念与架构](#一概念与架构)
- [二、5 分钟快速上手](#二5-分钟快速上手)
- [三、界面总览](#三界面总览)
- [四、域管理](#四域管理)
- [五、类定义](#五类定义)
- [六、关系定义](#六关系定义)
- [七、状态机](#七状态机)
- [八、文档注入与引擎管线](#八文档注入与引擎管线)
- [九、图可视化与操作](#九图可视化与操作)
- [十、验证与修复](#十验证与修复)
- [十一、知识缺口与主动合成](#十一知识缺口与主动合成)
- [十二、高级功能](#十二高级功能)
- [十三、与 FDE 交付体系的集成](#十三与-fde-交付体系的集成)
- [十四、常见问题排查](#十四常见问题排查)
- [附录 A：API 端点速查](#附录-aapi-端点速查)
- [附录 B：域 YAML 模板](#附录-b域-yaml-模板)

---

## 一、概念与架构

### 1.1 什么是本体模型

本体模型（Ontology）是对某个**知识领域**的规范化描述。它包括：

| 概念 | 含义 | 类比 |
|------|------|------|
| **T-Box**（类定义） | 领域里有哪些**类型**的东西 | 数据库的 schema（表结构） |
| **A-Box**（实例） | 类定义下的**具体实体** | 数据库的行（具体数据） |
| **关系** | 类和类之间如何**连接** | 数据库的外键 |
| **状态机** | 实体在生命周期中的**状态流转** | 工作流的状态转换 |
| **推理规则** | 从已知事实**推导**新知识 | `if A→B and B→C then A→C` |

### 1.2 为什么需要本体模型

在 aiPlatform 中，本体模型不是学术概念，而是**工程基础设施**：

| 场景 | 没有本体 | 有本体 |
|------|---------|--------|
| FDE 交付 | 每次手动梳理客户业务概念 | 引擎自动分类文档 → 自动提取属性 |
| 知识检索 | 关键词匹配，查不准 | 基于类的语义检索 + 子类展开 |
| 诊断 | 不知道哪个域缺了什么 | 知识缺口自动检测 + 主动合成 |
| 对话 | 不懂行业术语 | DomainRouter 自动路由到对应域 |

### 1.3 系统架构

```
用户界面 (OntologyManager UI)
  ↓
API 层 (70+ REST endpoints)
  ↓
OntologyEngine (8 阶段管线)
  ├── ClassMapper      — 关键词倒排索引 → T-Box 类标签（确定性）
  ├── PropertyExtractor — LLM 并行提取结构化属性（LLM）
  ├── Validator        — Schema 校验必填字段（确定性）
  ├── EntityResolver   — 编辑距离 + 共现 + 结构 → 消歧合并（确定性）
  ├── StateMachine     — YAML 配置驱动的状态评估（确定性）
  ├── RelationDetect   — 共现关系发现（确定性）
  ├── GraphBuild       — 实体 + 关系写入 SQLite 图（确定性）
  └── KnowledgeSynthesizer — 图 → Wiki 页面合成（模板驱动）
  ↓
GraphIndex (SQLite 存储) + Wiki 页面
```

---

## 二、5 分钟快速上手

### 2.1 用智能生成创建第一个域

1. 打开管理端 → 知识工厂 → **本体模型**
2. 点击右上角 **🤖 智能生成** 按钮
3. 填写：

| 字段 | 说明 | 示例 |
|------|------|------|
| 域名 ID | 唯一标识，1-50 字符，英文 | `lock-service` |
| 显示名 | 中文名称 | `智能锁安装维保` |
| 描述关键词 | 用自然语言描述这个领域包含什么 | `智能锁 安装工单 设备型号 安装师傅 故障类型 维修记录 客户现场` |
| 子目录 | Vault 中文档的子目录（可选） | 留空扫描全部 |
| 样本数 | 扫描多少份文档来分析 | 默认 20 |

4. 点击 **开始生成**，AI 将依次：
   - 扫描 Vault 中的文档提取关键词
   - 识别领域实体（方法/系统/概念/问题/参考资料）
   - 聚类为 4-8 个本体类
   - 提取类之间的关系
   - 若有生命周期相关实体，自动定义状态机
   - 组装成完整 YAML 文件

5. 预览生成的 YAML，确认无误后点击 **💾 保存并注册**。

6. 新域即刻出现在域列表中，已热加载到 DomainRouter。

### 2.2 手动创建域

如果智能生成不满足需求，可以手动创建：

1. 点击 **新建域**
2. 填写 `域名 ID` 和 `显示名`
3. 系统自动生成空 YAML 模板
4. 手动添加类、关系、状态机（见后续章节）

---

## 三、界面总览

进入 `/infra/ontology` 后，页面分为以下区域：

```
┌──────────────────────────────────────────────────────────────┐
│  本体模型管理                     [新建域] [🤖 智能生成] [刷新] │
├──────────────────────────────────────────────────────────────┤
│  域列表（左侧卡片或表格）                                      │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ AI知识 v2.0 · 6 类 · 19 关系 · 检索:0.25               │ │
│  │ 船舶设计 v1.0 · 9 类 · 17 关系 · 检索:0.3              │ │
│  │ ...更多域...                                            │ │
│  └─────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────┤
│  选中域的详细信息（右侧面板）                                   │
│  [类定义] [关系] [🕸️ 图] [状态机] [🧠 推理] [🧬 合成]          │
│  [🔍 缺口] [📢 推荐] [📋 复查] [📜 历史] [数据源]            │
├──────────────────────────────────────────────────────────────┤
│  🤖 AIP Assist — 智能辅助面板                                  │
│  复查: 0条 · 缺口: 3个 · 建议: 上传文档开始构建知识图谱         │
└──────────────────────────────────────────────────────────────┘
```

### 3.1 各面板功能速查

| 面板 | 功能 | 何时使用 |
|------|------|---------|
| **类定义** | 查看/新建/编辑/删除本体类 | 定义"这个领域有哪些东西" |
| **关系** | 定义类之间的连接方式 | 定义"这些东西之间的关系" |
| **🕸️ 图** | 可视化类+关系的交互图 | 理解本体结构 |
| **状态机** | 定义实体的状态转换规则 | 实体有生命周期时 |
| **🧠 推理** | 基于规则推导隐含知识 | 高级用法 |
| **🧬 合成** | 从图数据生成 Wiki 页面 | 引擎跑完后 |
| **🔍 缺口** | 检测知识覆盖空白 | 诊断知识完整度 |
| **📢 推荐** | 主动生成知识补充建议 | 持续维护 |
| **📋 复查** | 待 FDE 确认的关联审查 | 状态变更后 |
| **📜 历史** | 状态变更的时间线 | 追踪实体演变 |

### 3.9 本体编辑器 (v2.6) vs 手写 YAML

| 操作 | 手写 YAML | 🆕 编辑器 |
|------|------|------|
| 创建域 | 建文件 → `~/.aiplat/ontologies/{id}.yaml` | 管理端 → 本体编辑器 → "+" → 填写表单 |
| 编辑 class | 编辑 YAML 文本 | UI 表单：类名、标签、字段、枚举值 |
| 添加状态机 | 手写 states/transitions | 状态机可视化表单：states 列表 → transitions 连线 |
| 副作用配置 | 手写 YAML | 表单选择：add_tag / call_webhook / mark_related_for_review / inject_case_study |
| 角色视图 🆕 | 不存在 | views YAML：术语定义 + 字段可见性 + 类过滤 |
| 流程编排 🆕 | 不存在 | processes YAML：跨实体步骤 + auto_create + SLA |
| NL→YAML 🆕 | 不可用 | 输入业务描述 → LLM 生成 class 定义草案 |
| 发布与版本 🆕 | 手动替换文件 | publish → 写回 YAML + graph snapshot + 缓存失效 |
| 监控 🆕 | 不可用 | Monitor tab：状态分布 + 瓶颈分析 + SLA 违约 |

**入口**：管理端 → 打开 /ontology-editor（本体编辑器） (`/ontology-editor`)

---

## 四、域管理

### 4.1 创建域

**手动创建**（`POST /ontology/domains`）：

```json
{
  "id": "my-domain",
  "name": "我的领域",
  "description": "领域用途描述",
  "version": "1.0.0"
}
```

系统自动生成 `~/.aiplat/ontologies/my-domain.yaml`。

**智能生成**（`POST /ontology/domains/generate`）：

见 [5 分钟快速上手](#二5-分钟快速上手)。

### 4.2 域配置项

在域卡片上可配置的参数：

| 参数 | 默认值 | 说明 |
|------|:---:|------|
| 检索阈值 | 0.25 | 本体映射的最低置信度阈值 |
| 子类展开 | ✓ | 检索时是否自动包含子类 |
| 跨域降级 | 3 | 主域结果不足时降级到多少个 fallback 域 |
| Prompt | `domain-prompt-{id}` | 该域的回答风格 prompt 模板 |
| Collection | 同 id | 对应的 Wiki collection |

### 4.3 编辑域

直接在域的 YAML 文件中修改类/关系/状态机（或通过 UI）。修改后无需重启，`DomainRouter` 下次 `classify()` 时自动重建索引。

### 4.4 删除域

删除域会**级联清理**：
- 对应 GraphIndex 的 SQLite 数据库
- 对应 Wiki collection 的所有页面
- 对应状态变更历史

> ⚠️ 删除前建议先创建快照：`POST /api/core/ontology/engine/snapshot/{domain_id}``。

---

## 五、类定义

### 5.1 类是什么

类是本体模型的核心——它定义了**这个领域里有哪些类型的东西**。每个类有：

| 组成部分 | 说明 | 示例（lock-service 域） |
|---------|------|------------------------|
| **名称** | 英文标识名 | `InstallOrder` |
| **标签** | 中文显示名 | `安装工单` |
| **必填字段** | 引擎必须提取的字段 | `order_id, customer_name, device_model, status` |
| **可选字段** | 引擎尽量提取的字段 | `address, scheduled_date, technician, notes` |
| **分类** | Wiki 类别标签（用于 ClassMapper 分类） | `lock-service` |

### 5.2 添加类

1. 进入域的 **类定义** Tab
2. 点击 **+ 类**
3. 填写类名、标签、必填/可选字段
4. 可选：定义**枚举字段**（如 `lock_type: [指纹锁, 密码锁, 人脸锁]`）
5. 保存

### 5.3 编辑/删除类

- **编辑**：修改字段、标签、分类等
- **删除**：需要 `?force=true` 参数。首次调用返回受影响的实例数量供确认。

### 5.4 类的实例

每个类下可以查看已构建的实例（来自文档解析结果）：

```
安装工单
  必填: order_id, customer_name, device_model, status
  可选: address, scheduled_date, technician, notes, urgency
  📂 查看实例 → (12 个实例)
```

---

## 六、关系定义

### 6.1 关系是什么

关系（Object Property）定义了**类和类之间的连接方式**。它是有向的：

```
InstallOrder ──派单给──▶ Technician    （一个工单派给一个师傅）
RepairRecord ──故障原因──▶ FaultType    （维修记录的故障类型）
```

### 6.2 关系的属性

| 属性 | 说明 |
|------|------|
| **domain** | 关系的**出发点**是哪些类（可多选） |
| **range** | 关系的**到达点**是哪些类（可多选） |
| **transitive** | 是否传递（A→B and B→C ⇒ A→C） |
| **symmetric** | 是否对称（A→B ⇒ B→A） |

### 6.3 添加关系

1. 进入域的 **关系** Tab
2. 点击 **+ 关系**
3. 填写关系名（snake_case）、中文标签
4. 选择 domain 类（出发点）和 range 类（到达点）
5. 可选：勾选 `传递`、`对称`

---

## 七、状态机

### 7.1 什么时候需要状态机

当某个类的实例有**明确的生命周期**时，定义状态机可以让引擎**自动推导实体状态变化**。例如：

```
安装工单:
  pending ──(派单)──▶ assigned ──(到场)──▶ in_progress ──(完成)──▶ completed
                                                                       └── cancelled
```

### 7.2 状态机三要素

| 要素 | 说明 | 示例 |
|------|------|------|
| **状态** | 实体可能处于的阶段 | `pending, assigned, in_progress, completed, cancelled` |
| **转换** | 从 A 状态到 B 状态的规则 | `pending → assigned` |
| **触发器** | 什么条件下触发转换 | `relation_count(assigned_to) >= 1` |
| **副作用** | 转换后自动执行的动作 | `mark_related_for_review` |

### 7.3 定义状态机

在 YAML 中：

```yaml
classes:
  InstallOrder:
    states:
      default: pending
      enum:
        - name: pending
          label: 待派单
        - name: assigned
          label: 已派单
        - name: in_progress
          label: 安装中
        - name: completed
          label: 已完成
      transitions:
        - from: pending
          to: assigned
          trigger:
            type: relation_exists
            relation: assigned_to
        - from: assigned
          to: in_progress
          trigger:
            type: property_condition
            field: visited_at
            operator: ">="
            value: 1
        - from: in_progress
          to: completed
          trigger:
            type: relation_exists
            relation: installed_by
          side_effects:
            - type: mark_related_for_review
              relation: uses_device
```

### 7.4 传播模拟

UI 中的 **🔁 传播模拟** 功能：选择一个类 → 模拟新实例创建后，状态机会如何连锁触发其他类的状态变化。

---

## 八、文档注入与引擎管线

### 8.1 支持的上传方式

| 方式 | 路径 | 适用场景 |
|------|------|---------|
| **平台文档上传** | `POST /api/platform/apps/fde/ingest` | PDF/DOCX/PPTX/HTML/MD/TXT |
| **引擎直接处理** | `POST /api/core/ontology/engine/parse-and-process` | 已有文本，直接跑引擎 |
| **KB 批量导入** | `POST /api/core/wiki/ingest` | 从 URL 拉取文档 |
| **数据源连接** | `GET /api/core/ontology/datasources` | SQL/API 数据源 |

### 8.2 引擎管线流程

上传文档后，引擎自动跑 8 个阶段：

```
┌────────────────────────────────────────────────────────────────────┐
│ Phase 1: Classify（分类）                                          │
│   DocumentParser → StructuredChunk[] → ClassMapper                 │
│   → 每个 chunk 被打上 T-Box 类标签（零 LLM，关键词倒排索引）         │
│                                                                     │
│ Phase 2: Extract（提取）                                           │
│   PropertyExtractor → 并行 asyncio.gather → LLM 提取结构化属性      │
│   → 按 required_fields 校验                                        │
│                                                                     │
│ Phase 3: Validate + Dedup + Build + SourceTrace                    │
│   → Schema 校验 → 标题去重 → 构建实体 → 记录来源文档                 │
│                                                                     │
│ Phase 4: EntityResolve（消歧）                                      │
│   → 编辑距离 0.4 + 共现 0.3 + 结构上下文 0.3 → 合并重复实体          │
│                                                                     │
│ Phase 5: StateMachine（状态机）                                     │
│   → YAML 配置驱动 → evaluate_chain → 自动状态迁移                   │
│   → 写入 state_changes.db                                           │
│                                                                     │
│ Phase 6: RelationDetect（关系发现）                                  │
│   → 同 chunk 内的实体自动建立关系                                    │
│                                                                     │
│ Phase 7: GraphBuild（图构建）                                       │
│   → 实体 + 关系 → 写入 GraphIndex (SQLite)                          │
│   → 表 → HyperEdge（表格结构化数据保留）                             │
│                                                                     │
│ Phase 8: KnowledgeSynthesis（知识合成）                              │
│   → 推理链 + 事实卡 + 跨文档结论 → 生成 Wiki 页面                   │
│   → 页面携带 source_instances + synthesis_type frontmatter          │
└────────────────────────────────────────────────────────────────────┘
```

### 8.3 大批量处理

对于已有大量 Wiki 页面的域，使用批量流程：

1. `POST /domains/{id}/classify-all` — LLM 给所有未分类页面打类标签
2. `POST /domains/{id}/build-instances` — 并行引擎处理（2 并发）
3. `POST /domains/{id}/build-edges` — 构建跨页面图边
4. `POST /api/core/ontology/domains/{domain_id}/verify` — 验证分类覆盖率和数据完整性

---

## 九、图可视化与操作

### 9.1 查看图

在 **🕸️ 图** Tab 中，可以看到：
- **节点**：类和实例的交互式可视化
- **边**：关系连线，标注关系名
- **点击节点**：查看类详情或实例详情
- **切换图/表视图**：右上角按钮

### 9.2 图操作

| 操作 | 端点 | 说明 |
|------|------|------|
| 查看统计 | `GET /api/core/ontology/engine/graph-stats/{domain_id}` | 节点数、边数、推断边数 |
| 快照 | `POST /api/core/ontology/engine/snapshot/{domain_id}`` | 保存当前图状态 |
| 恢复 | `POST /engine/snapshot/{id}/restore` | 恢复到指定快照 |
| 遍历 | `POST /engine/traverse` | 多跳路径查询 |
| 推理 | `POST /engine/infer` | 运行推理规则生成新边 |

---

## 十、验证与修复

### 10.1 验证报告

打开域的 **📊 验证报告** Tab 可以看到：

| 指标 | 含义 | 预期值 |
|------|------|:---:|
| 页面总数 | Wiki collection 中的页面数 | >0 |
| 已分类 | 被 ClassMapper 打上标签的页面数 | 接近总数 |
| 未分类 | 未被分类的页面数 | 越少越好 |
| 图节点 | GraphIndex 中的实体数 | 随文档量增长 |
| 图边 | 实体之间的关系数 | >0 |
| 异常 | Schema 冲突、字段缺失等 | 0 |

### 10.2 自动修复

点击 **🔧 修复** 按钮（`POST /domains/{id}/repair`）：

- 删除孤立节点
- 修复损坏的关系引用
- 补充缺失的默认字段值
- 清理重复实体

### 10.3 进化建议

点击 **🔄 进化** 按钮（`POST /domains/{id}/evolve`）：

- 基于现有实例检测新的类候选
- 检测高频共现实体对建议新关系
- 检测类下实例数过少建议合并

---

## 十一、知识缺口与主动合成

### 11.1 检测缺口

**🔍 缺口** Tab（`POST /engine/detect-gaps`）：

- 基于近期查询日志分析
- 识别 `no_instance`（类存在但无实例）和 `no_entity`（实体已知但无 Wiki 页面）两种缺口
- 按频率排序，优先处理高频缺口

### 11.2 CandidatePool → ActiveSynthesis

FDE 现场反馈的知识缺口自动进入候选池：

```
FDE 澄清对话 → 检测到缺失概念
  → CandidatePool.submit(gap)
    → normalize + dedup
    → N ≥ 3 次独立来源
    → 冲突检测（关键词反义）
    → GraphIndex 验证
    → ActiveSynthesis（LLM 生成 Wiki 草稿）
    → FDE 审核确认
```

### 11.3 主动推荐

**📢 推荐** Tab（`GET /api/core/ontology/engine/recommend/{domain_id}`）：

- 基于知识缺口自动生成补充建议
- 优先级排序（高频缺口优先）
- 一键触发生成

---

## 十二、高级功能

### 12.1 SQL 本体桥接

将外部数据库（PostgreSQL/MySQL/SQLite）映射为本体实例：

```yaml
# sql_ontology_example.yaml
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

1. 上传 YAML 配置文件
2. `POST /api/core/ontology/sql/query` — 将 SPARQL-like 查询翻译为 SQL 执行
3. 结果自动映射为本体实例

### 12.2 数据源连接器

支持三种外部数据源：

| 类型 | 配置 | 说明 |
|------|------|------|
| SQL | `~/.aiplat/datasources/{name}.yaml` | 直接连接数据库 |
| API | REST endpoint | 通过 HTTP 拉取数据 |
| File | CSV/JSON/Excel | 批量文件导入 |

运行：`POST /engine/process-from-datasource`

### 12.3 SDK 导出

`GET /api/core/ontology/sdk/{domain_id}` — 自动生成 Python/TypeScript 客户端代码，包含该域所有类的类型定义和 CRUD 方法。

### 12.4 OWL/RDF 导出

`GET /export?format=turtle` — 导出为 W3C 标准语义 Web 格式，与其他本体系统互操作。

---

## 十三、与 FDE 交付体系的集成

FDE 现场交付工程师通过 8 步流程使用本体引擎：建域 → 注入文档 → 跑引擎 → 客户 QA → 发现缺口 → 追踪效果 → 持续迭代。

完整操作指南和 API 参考详见 **[FDE 运维与自演进手册](./fde/03-fde-operations.md#五fde-与本体引擎集成)**。

诊断中心的以下检查项反映了本体健康度：

| 检查项 | 含义 | 打开 /infra/ontology（本体模型） 中的对应操作 |
|--------|------|---------------------|
| `wiki_health` | Wiki 页面健康度（死链/孤立/矛盾） | 点击验证报告 |
| `wiki_content_quality` | Wiki 内容质量评分 | 点击修复 |
| `rag_quality` | RAG 检索质量（忠实度/精度） | 补充知识缺口 |
| `assessment` | 成熟度评估 | 域配置完善度 |

---

## 十四、常见问题排查

### 14.1 "0 个节点 · 0 个实例 · 0 页已分类"

**原因**：尚未上传文档，或上传后未运行引擎。

**解决**：
1. 确认 Vault 中有文档（`~/.aiplat/vault/`）
2. 运行 `classify-all` → `build-instances` → `build-edges`
3. 检查验证报告中的覆盖情况

### 14.2 "LLM 提取的属性质量差"

**原因**：类的描述不够精确，或文档格式复杂。

**解决**：
1. 确保 `required_fields` 和 `optional_fields` 有清晰的中文描述
2. 尝试 `POST /engine/parse-and-process` 直接处理，查看中间输出
3. 调整 ClassMapper 的 `class_threshold` 参数

### 14.3 "智能生成了空 YAML"

**原因**：Vault 中没有相关文档，或描述关键词太宽泛。

**解决**：
1. 减少生成样本数，或用更窄的关键词
2. 先手动上传几份相关文档到 Vault
3. 手动创建域 + 少量类，然后通过 `evolve` 扩展

### 14.4 "检索不到期望的结果"

**原因**：检索阈值过高，或实体消歧错误。

**解决**：
1. 调低域卡片上的**检索阈值**（从 0.25 降到 0.15）
2. 检查 EntityResolver 是否误合并了不应该合并的实体
3. 打开**子类展开**开关
4. 增加**跨域降级**数量

### 14.5 "状态机没有触发"

**原因**：实体不满足 trigger 条件。

**解决**：
1. 检查 `_persist_reviews()` 文件（`~/.aiplat/ontology_reviews/{domain}.json`）中的 pending 条目
2. 使用**传播模拟**手动验证 trigger 条件
3. 检查关系是否真的存在于图数据中（`GET /api/core/ontology/engine/graph-stats/{domain_id}`）

---

## 附录 A：API 端点速查

### 域管理

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/domains` | 列出所有域 |
| POST | `/domains` | 新建域 |
| POST | `/domains/generate` | AI 智能生成 |
| GET | `/domains/{id}` | 获取域详情 |
| PUT | `/domains/{id}` | 更新域 |
| DELETE | `/domains/{id}` | 删除域 |
| POST | `/domains/{id}/evolve` | 进化分析 |
| POST | `/domains/{id}/repair` | 自动修复 |

### 类管理

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/domains/{id}/classes` | 添加类 |
| PUT | `/domains/{id}/classes/{name}` | 编辑类 |
| DELETE | `/domains/{id}/classes/{name}` | 删除类 |
| GET | `/domains/{id}/instances` | 按类标签查看实例 |

### 关系管理

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/domains/{id}/properties` | 添加关系 |
| PUT | `/domains/{id}/properties/{name}` | 编辑关系 |
| DELETE | `/domains/{id}/properties/{name}` | 删除关系 |

### 引擎操作

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/engine/process` | 单文本处理 |
| POST | `/engine/parse-and-process` | 解析+处理+写入 |
| POST | `/domains/{id}/build-instances` | 批量构建实例 |
| POST | `/domains/{id}/build-edges` | 构建跨页面边 |
| POST | `/domains/{id}/classify-all` | LLM 分类全部页面 |
| POST | `/engine/synthesize` | 知识合成 |
| POST | `/engine/infer` | 推理新边 |

### 验证与模拟

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/domains/{id}/validation-report` | 验证报告 |
| POST | `/domains/{id}/verify` | 统一验证 |
| POST | `/engine/simulate-state` | 状态模拟 |
| POST | `/engine/simulate-scenarios` | 多方案推演 |
| GET | `/engine/reviews/{id}` | 复查队列 |
| POST | `/engine/reviews/{id}/resolve` | 解决复查 |

---

## 附录 B：域 YAML 模板

### 完整模板（含状态机 + 推理规则）

```yaml
name: "我的领域"
namespace: "http://aiplat.local/ontology/my-domain/"
description: "领域用途描述"
version: "1.0.0"

classes:
  MyEntity:
    label: 我的实体
    required_fields: [name, description, category]
    optional_fields: [tags, source_doc]
    categories: [my-domain]
    fields:
      - name: category
        type: enum
        values: [type_a, type_b, type_c]
    states:
      default: created
      enum:
        - name: created
          label: 已创建
        - name: active
          label: 活跃中
        - name: archived
          label: 已归档
      transitions:
        - from: created
          to: active
          trigger:
            type: property_condition
            field: validated
            operator: ">="
            value: 1
        - from: active
          to: archived
          trigger:
            type: property_condition
            field: days_since_last_update
            operator: ">"
            value: 90
          side_effects:
            - type: mark_related_for_review
              relation: references

  AnotherEntity:
    label: 另一个实体
    required_fields: [name]
    optional_fields: [notes]

object_properties:
  - name: references
    label: 引用
    domain: [MyEntity]
    range: [AnotherEntity]
    inverse: referenced_by

  - name: depends_on
    label: 依赖
    domain: [MyEntity]
    range: [MyEntity]
    transitive: true

data_properties:
  - name: priority
    label: 优先级
    domain: [MyEntity]
    range: integer

inference_rules:
  - name: dependency_chain
    description: 传递依赖链：如果 A 依赖 B 且 B 依赖 C，则 A 也依赖 C
    premises:
      - relation: depends_on
        direction: outgoing
      - relation: depends_on
        direction: outgoing
    conclusion:
      relation: depends_on
      label: 间接依赖
      confidence: 0.8
```

---

*最后更新: 2026-07-17 · 版本: 1.0*
