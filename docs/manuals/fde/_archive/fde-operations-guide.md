# FDE 系统运维操作指南

> **交付后的持续运营手册——FDE 返回办公室后，如何监控、调整和优化已部署的系统。**

---

## 0. 日常巡检（每天 5 分钟）

### 0.1 快速看板

打开 `GET /fde/dashboard`，关注三个指标：

| 指标 | 正常值 | 异常信号 | 处理 |
|------|:--:|------|------|
| `pipeline_health` | `ok` | `degraded` 或 `error` | 立即跑 `/system/diagnose` |
| `quality_score.overall` | ≥ 60 | < 40 | 跑 `/fde/quality-summary` 定位薄弱子系统 |
| `self_evolution.knowledge_atoms` | 持续增长 | 连续 3 天不增 | 检查 POST_LOOP hook 是否正常 |

### 0.2 健康检查

```bash
curl GET /fde/health
```

返回 6 维组件状态。重点关注 `context_bus.health`（10 层注入是否全正常）和 `model.available`（LLM 是否可用）。

### 0.3 告警扫描

```bash
curl GET /fde/alerts?min_severity=warning
```

返回 5 类告警：blocked（被阻塞行动）、stale（超过 30 天无活动）、zero_evidence（零本体支撑）、high_gaps（超 3 个未匹配概念）、low_quality（质量分 < 40）。

---

## 1. API 端点参考

### 1.1 系统概览类

| 端点 | 方法 | 功能 | 常用场景 |
|------|:--:|------|------|
| `/fde/overview` | GET | 系统自描述 + 架构全景 | 新人了解系统 |
| `/system/overview` | GET | 系统级实时指标 | 监控面板 |
| `/fde/capabilities` | GET | 完整能力清单（30+ 模块） | 能力盘点 |
| `/fde/governance` | GET | 8 项治理能力矩阵 + 行业对标 | 对外展示治理成熟度 |
| `/fde/governance/validate` | GET | 8 项能力自审计 | 系统健康自检 |

### 1.2 诊断与运营类

| 端点 | 方法 | 功能 | 常用场景 |
|------|:--:|------|------|
| `/fde/dashboard` | GET | 10 项关键指标 + 最近活动 + 告警 | 日常巡检首页 |
| `/fde/pipeline-status` | GET | ContextBus 逐层健康 + 数据可用性 | 排查注入问题 |
| `/fde/quality-summary` | GET | 四子系统质量评分（FDE/SECI/Convergence/ContextBus） | 月度质量报告 |
| `/fde/health` | GET | 6 维组件健康检查 | 问题定位 |
| `/fde/validate` | GET | 8 项 E2E 连通测试 | 部署后验收 |
| `/fde/seci-status` | GET | SECI 知识创造引擎状态 | 知识管理 |

### 1.3 诊断会话类

| 端点 | 方法 | 功能 | 常用场景 |
|------|:--:|------|------|
| `/fde/sessions` | GET | 历史诊断列表（按行业/公司/状态过滤） | 查看所有客户诊断 |
| `/fde/sessions/{id}` | GET | 单个会话全视图（证据/行动/时间线/关联） | 客户回访前查看 |
| `/fde/sessions/{id}/timeline` | GET | 状态变迁时间线 | 追溯交付历史 |
| `/fde/sessions/{id}/quality` | GET | 四维加权质量评分（0-100） | 交付质量评估 |
| `/fde/sessions/{id}/ontology-coverage` | GET | 本体覆盖率 + determinism_score | 判断报告可信度 |
| `/fde/sessions/{id}/improve` | GET | 覆盖率改进建议（可执行步骤） | 提升报告质量 |
| `/fde/sessions/compare` | GET | 双会话并排对比 | 同客户前后对比 / 跨客户对比 |

### 1.4 交付跟踪类

| 端点 | 方法 | 功能 | 常用场景 |
|------|:--:|------|------|
| `/fde/delivery/feedback` | POST | 标记交付状态（delivered/completed/blocked） | 客户反馈后更新 |
| `/fde/ask` | POST | 基于诊断上下文追问 | 客户追问"为什么推荐这个方案" |
| `/fde/ingest` | POST | 跨系统数据桥接（ERP/CRM → FDE 输入） | 导入外部数据 |

### 1.5 分析与趋势类

| 端点 | 方法 | 功能 | 常用场景 |
|------|:--:|------|------|
| `/fde/benchmark` | GET | 跨行业聚合统计 + TOP 推荐 | 行业分析 |
| `/fde/trends` | GET | 会话级时间序列趋势 | 月报数据 |
| `/fde/trends/system` | GET | 系统级 12 周趋势 | 季度复盘 |
| `/fde/health/history` | GET | 最近 N 次健康快照对比 | 故障回溯 |
| `/fde/search` | GET | 跨实体全文检索（会话/行动/术语/证据） | 查找特定客户或方案 |

### 1.6 自演进类

| 端点 | 方法 | 功能 | 常用场景 |
|------|:--:|------|------|
| `/system/diagnose` | GET | 主动系统诊断（5 条规则 + 关联分析） | 排查异常 |
| `/system/heal` | POST | 自动修复（confidence ≥ 0.9 安全门） | 快速恢复 |
| `/system/evolve` | GET | 演化循环（模式检测 → 术语发布 / 草稿审批） | 知识库自动增长 |
| `/system/self-check` | POST | 一键 diagnose→heal→evolve 全周期 | 定期维护 |

### 1.7 数据播种类

| 端点 | 方法 | 功能 | 参数 |
|------|:--:|------|------|
| `/fde/bootstrap-test-data` | POST | 播种单个行业演示数据 | `?industry=政务` |
| `/fde/bootstrap-all` | POST | 一键播种 4 行业演示数据 | 无 |

---

## 2. 常见操作场景

### 2.1 客户追问"为什么推荐这个方案？"

```bash
curl -X POST /fde/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "为什么推荐RAG而不是传统关键词搜索？",
    "session_id": "session_某省政务服务中心_1720...",
    "industry": "政务"
  }'
```

系统会基于该会话的域图谱、历史案例、方案原型、跨域类比，给出有据可依的回答。

### 2.2 客户反馈"方案落地了"

```bash
curl -X POST /fde/delivery/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_某省政务服务中心_1720...",
    "status": "completed"
  }'
```

反馈后，系统自动：更新交付率统计 → 触发 ROI 重新计算 → 下次诊断时参考最新数据。

### 2.3 怀疑系统出了问题的排查流程

```bash
# 第一步：诊断
curl GET /system/diagnose

# 第二步：管道健康
curl GET /fde/pipeline-status

# 第三步：全局健康
curl GET /fde/health

# 第四步：自动修复
curl -X POST /system/heal
```

### 2.4 查看某个客户的交付进展

```bash
# 查看详情
curl GET /fde/sessions/{session_id}

# 查看状态时间线
curl GET /fde/sessions/{session_id}/timeline

# 查看质量评分
curl GET /fde/sessions/{session_id}/quality

# 查看本体覆盖率
curl GET /fde/sessions/{session_id}/ontology-coverage
```

### 2.5 一次性创建所有行业演示数据

```bash
curl -X POST /fde/bootstrap-all
```

创建后可通过 `/fde/dashboard`、`/fde/benchmark` 查看效果。

---

## 3. 配置管理

### 3.1 方案原型管理

**文件**：`~/.aiplat/ontologies/ai-solution.yaml` → `solution_archetypes` 块

```yaml
solution_archetypes:
  - name: 智能风控引擎          # 方案显示名
    category: anomaly_detection # 类别
    data_maturity_min: 3        # 最低数据成熟度要求
    cost_level: medium          # 成本等级: low/medium/high
    estimated_cycle_months: 3-5 # 预期周期(月)
    deployment_modes: [on_premise, cloud]  # 部署模式
    xinchuang_compatible: true  # 信创兼容: true/false
```

**操作**：编辑 YAML → 保存 → mtime 检测 → 下次诊断自动热加载（零重启）。

### 3.2 数字员工角色管理

**文件**：`~/.aiplat/ontologies/ai-solution.yaml` → `digital_employee_roles` 块

```yaml
digital_employee_roles:
  - keywords: 关联挖掘/图谱/关系网络    # LLM 匹配关键词
    role_name: 关系挖掘助手            # 角色显示名
    role_ability: 发现隐藏关联、构建关联网络  # 角色能力描述
    skills: [knowledge_retrieval, document_analysis]  # 绑定 Skill
```

**操作**：新增角色 → 编辑 YAML → 下一次诊断时 §6 自动显示新角色。

### 3.3 收敛阈值管理

**文件**：`~/.aiplat/ontologies/knowledge-atom.yaml` → `convergence` 块

```yaml
convergence:
  triggers:
    skill_weight:
      min_similar_atoms: 3    # 需要几个相似原子才触发调整
      similarity_threshold: 0.65
      damping: 0.3            # 调整阻尼
    agent_prompt:
      min_confidence: 0.9     # 多高置信度才注入 Agent
```

**操作**：当系统提示"收敛失效"时，降低 `min_similar_atoms` 让触发更容易。

### 3.4 权限边界管理

**文件**：`~/.aiplat/ontologies/fde-delivery.yaml` → `classes.{ClassName}.permissions`

```yaml
permissions:
  - role: admin
    actions: [view, edit, execute]
    scope: all
  - role: viewer
    actions: [view]
    scope: own
```

**操作**：新增角色或调整权限后，`graph.check_permission()` 立即生效。

---

## 4. 交付跟踪全流程

```
客户诊断 → /fde/sessions/{id} (查看)
    ↓
客户确认 → POST /fde/delivery/feedback (status=delivered)
    ↓
实施中   → /fde/sessions/{id}/timeline (监控状态变化)
    ↓
阶段完成 → POST /fde/delivery/feedback (status=completed)
    ↓
效果评估 → /fde/sessions/{id}/quality + /ontology-coverage
    ↓
优化迭代 → /fde/sessions/{id}/improve (生成改进建议)
    ↓
新一轮诊断 → 自动参考历史交付率 → ROIP 更准
```
