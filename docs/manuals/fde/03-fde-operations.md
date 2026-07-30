# FDE 运维与自演进

> ← [文档导航](README.md)

> **目标角色**：负责已交付客户项目后续维护的 FDE / 运维工程师  
> **前置**：项目已完成⑦ 验收移交

---

## 一、日常巡检（每天 5 分钟）

### 1.1 快速看板

打开 `GET /fde/dashboard`，关注三个指标：

| 指标 | 正常值 | 异常处理 |
|------|:--:|------|
| `pipeline_health` | `ok` | `degraded`/`error` → 跑 `/system/diagnose` |
| `quality_score.overall` | ≥ 60 | < 40 → 跑 `/fde/quality-summary` 定位薄弱子系统 |
| `self_evolution.knowledge_atoms` | 持续增长 | 连续 3 天不增 → 检查 POST_LOOP hook |

### 1.2 健康检查

```bash
curl http://localhost:8003/api/platform/apps/fde/health
```
返回 6 维组件状态。重点关注 `context_bus.health`（10 层注入是否正常）和 `model.available`。

### 1.3 告警扫描

```bash
curl "http://localhost:8003/api/platform/apps/fde/alerts?min_severity=warning"
```
5 类告警：blocked（被阻塞）、stale（超 30 天无活动）、zero_evidence（零本体支撑）、high_gaps（超 3 个未匹配概念）、low_quality（质量分 < 40）。

---

## 二、API 端点速查

### 系统概览

| 端点 | 用途 |
|------|------|
| `GET /fde/dashboard` | 10 项关键指标 + 最近活动 + 告警 |
| `GET /fde/health` | 6 维组件健康检查 |
| `GET /fde/validate` | 8 项 E2E 连通测试 |
| `GET /fde/quality-summary` | 四子系统质量评分（FDE/SECI/Convergence/ContextBus） |

### 诊断会话管理

| 端点 | 用途 |
|------|------|
| `GET /fde/sessions?company=X` | 按客户过滤诊断历史 |
| `GET /fde/sessions/{id}/timeline` | 状态变迁时间线 |
| `GET /fde/sessions/{id}/quality` | 四维质量评分（0-100） |
| `GET /fde/sessions/compare?id=X&id2=Y` | 双会话并排对比 |

### 趋势与分析

| 端点 | 用途 |
|------|------|
| `GET /fde/trends` | 会话级时间序列趋势 |
| `GET /fde/trends/system` | 系统级 12 周趋势 |
| `GET /fde/search?q=关键词` | 跨实体全文检索 |

### 交付跟踪

| 端点 | 用途 |
|------|------|
| `POST /fde/delivery/feedback` | 标记交付状态 |
| `POST /fde/ask` | 基于诊断上下文追问 |
| `POST /fde/ingest` | 跨系统数据桥接（ERP/CRM → FDE） |

---

## 三、自演进系统

### 3.1 七层自动运转

| 层 | 功能 | 触发方式 | 零 Token 成本 |
|:--:|------|------|:---:|
| **观察层** | 每次健康检查自动记快照 | `/fde/health` 调用后 | ✅ |
| **诊断层** | 5 条规则跨子系统分析 | 每 10 次 Agent 对话 + 后台每小时 | ✅ |
| **修复层** | 对已知模式自动修复（confidence ≥ 0.9） | 诊断发现可修复问题后自动 | ✅ |
| **演化层** | 从知识缺口发现新术语、新方案 | 后台每小时 | ✅ |
| **目标分解层** | LLM+Ontology 拆解模糊目标→子Goal→依赖规划→分层执行 | WakeScheduler 检测到 `~/.aiplat/goals/pending/` 新文件时 | ❌ (LLM) |
| **自主部署层** | ToolBootstrap生成Skill→沙箱→灰度→push→构建→部署→验证→回滚 | GoalExecutor 检测到 tool_gap 时自动触发 | ❌ (LLM+构建) |
| **外部发现层** | socket扫描→服务指纹→DataSourceConfig→监听注册 | AIPLAT_DISCOVERY_ENABLED=true 时后台扫描 | ✅ |

### 3.2 数据积累预期

自演进需要数据积累，初期返回"数据不足"是正常的：

| 功能 | 多久生效 |
|------|:--:|
| 系统趋势分析 | ≥ 5 小时运行 |
| SECI 停滞检测 | 2 周 |
| 证据退化检测 | ≥ 3 次诊断 |
| 术语自动发布 | 同一概念 ≥ 3 次出现在知识缺口 |
| 目标分解 | 首次提交模糊目标后即时生效 |
| 自主部署 | ≥ 1 次成功 ToolBootstrap 后 |
| 外部发现 | ≥ 1 次端口扫描后 |

**不需要手动干预。** 系统自动积累，你只需确保服务在运行。

**数据不足时的 UI 表现**（避免误告警）：
- 当某一指标累计数据未达到生效阈值（如趋势分析 <5 小时）时，Dashboard 相关卡片显示为 **灰色状态**，并标注文字：`⏳ 数据收集中（已积累 X/5 小时）`
- 该状态不触发任何告警（severity 为空），不阻断 FDE 的 Tab 切换和操作
- 一旦阈值达成，卡片自动切换为正常监控状态（绿色/黄色/红色）

### 3.3 日常检查（每周一次）

```bash
# 看后台调度器是否在跑
curl http://localhost:8002/api/core/system/overview | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('scheduler',{}))"
# 预期：{"active": true, "interval_seconds": 3600}
```

### 3.4 手动全周期自检

```bash
curl -X POST http://localhost:8002/api/core/system/self-check
```
返回 diagnose → heal → evolve 三阶段结果。

### 3.5 手动触发诊断

```bash
curl http://localhost:8002/api/core/system/diagnose
# → 返回 5 条规则评估结果 + 置信度
curl -X POST http://localhost:8002/api/core/system/heal
# → 返回自动修复结果（仅 confidence ≥ 0.9）
```

---

## 四、FDE → 知识库反馈闭环

日常 FDE 操作自动驱动知识库优化，不需要运维手动操作：

```
客户现场提问 → FDE 澄清对话 → 知识缺口记录
  → CandidateKnowledgePool.add_gap()
  → 后台评估（重要性 + 紧迫性 + 可操作度）
  → 高分缺口 → 生成维基草案 → 审核人审核
  → 审核通过 → 正式发布到知识库
```

FDE 在 ③ 问题重构 → 澄清对话中产生的知识缺口会自动入库。在 ⑧ 运营监控 → 知识管理面板可查看候选池。

---

## 五、FDE 与本体引擎集成

### 完整工作流

```
构建域本体 → 注入 Wiki 文档 → 运行引擎管线 → 客户 QA
  → 发现知识缺口 → 标记关联实体待复审 → 跟踪效果 → 持续迭代
```

### 运维中的本体操作

| 你想… | 方式 |
|------|------|
| 可视化编辑域本体 | 管理端 → 知识工厂 → **本体编辑器** (`/ontology-editor`) |
| 查看域健康 | `GET /wiki/health-trend` |
| 验证域 YAML | `POST /ontology-editor/domains/{id}/publish`（含自动验证+快照） |
| 查看本体覆盖 | `GET /fde/sessions/{id}/ontology-coverage` |
| 查看状态分布 | `GET /ontology-editor/domains/{id}/monitor/state-distribution` |
| 查看流程瓶颈 | `GET /ontology-editor/domains/{id}/monitor/bottlenecks` |
| 规则版本管理 | `GET /api/platform/apps/ontology-editor/domains/{id}/rule-versions` |

> 本体编辑器 + 角色视图 + 流程编排 + 流程监控详见 [知识管理手册](../knowledge-management.md) §3.7。

更多详情参见 [本体引擎手册](../ontology.md)。

---

## 五、能力增强与 FDE 工作流映射

以下新增能力间接提升 FDE 工作流效率。映射到 8 步交付生命周期：

| 新增能力 | 增强的步骤 | 效果 |
|---------|:---:|------|
| **抽象目标分解** (Phase 39) | ① 业务认知 → ③ 问题重构 | 模糊需求自动拆解为结构化子目标，预先暴露知识缺口 |
| **自主部署流水线** (Phase 40) | ⑤ 快速构建 + ⑥ 评测护栏 | 沙箱→灰度5%→25%→100%→git push→部署→健康检查→回滚全自动 |
| **外部系统发现** (Phase 41) | ② 评估域 | 自动扫描客户网络→发现SQL/API数据源→生成DataSourceConfig→人工点一次确认 |
| **MoA 多模型推理** (Phase 42) | ③ 问题重构 | N参考引擎并行(高温)+1聚合器合成(低温), 诊断报告多视角交叉验证 |
| **记忆规则引擎** | ⑧ 运营监控 | 寒暄不存 + 报错必记, 自动过滤低价值对话, 保留关键决策 |
| **长期记忆CRUD** | ⑧ 运营监控 | 用户可直接查看/编辑/删除长期记忆, 白盒化冷存储 |
| **品牌基础层注入** | 全流程 | voice/tone/forbidden_words规则自动注入Agent, 确保输出统一 |
| **Wiki全局索引** | ② 评估域 | 一键生成 index.md, 按分类分组, 每条目含摘要+置信度 |
| **上下文压缩增强** | 全流程 | 微压缩(micro_compress) + Transcript Guard角色归一化, 减少长会话token消耗 |

当前能力总数见 [`AIPLAT_CAPABILITIES.md`](../../../AIPLAT_CAPABILITIES.md)。各能力启用方式见对应环境变量配置。
