---
doc_type: Architecture
title: aiPlat 演化计算架构
status: draft
authority: design-target
language: zh-CN
created: 2026-11-14
doc_id: AIPLAT_EVOLUTIONARY_COMPUTATION_ARCHITECTURE_2D5403
last_reviewed: 2026-11-25
---
# aiPlat 演化计算架构

> 本文是目标架构与实施框架，不是当前实现状态。  
> 范围：为 aiPlat 的闭环系统增加**受控、可审计、可回滚**的演化计算能力。  
> 非目标：让生产系统无人工门地自改代码。  
> 状态机与 `Candidate.status` 枚举以本文 §6 为 SSOT；实施方案必须对齐，禁止另起一套。

## 1. 目标与非目标

### 1.1 目标

```text
让可度量、可回放的系统组件
在沙箱中产生候选变体
用多目标适应度选择
经安全门和人工批准后灰度上线
并保留完整血缘和回滚能力
```

### 1.2 非目标

```text
不让生产环境直接遗传规划生成核心代码
不跳过评测、审批、灰度
不用单一指标代替质量/安全/成本
不修改客户合同/授权边界
```

## 2. 设计原则

| # | 原则 | 说明 |
|---|---|---|
| 1 | 基因组有边界 | 只允许声明过的字段/结构变异 |
| 2 | 评估先于选择 | 没有可复现评估，不进入种群 |
| 3 | 沙箱先于生产 | 候选先离线/回放，不直接改生产 |
| 4 | 多目标选择 | 质量、成本、延迟、安全、合规同时约束 |
| 5 | 血缘可追溯 | 每个候选有 parent、mutation、fitness、证据 |
| 6 | 人工门不可绕过 | 高风险变体必须人工批准 |
| 7 | 失败可回滚 | 任何上线变体必须可一键回退 |
| 8 | 预算有上限 | 评估调用数、token、时间、并发均受限 |

## 3. 总体架构

```text
                 ┌──────────────────────┐
                 │   Genome Registry    │
                 │ 可进化对象/边界/版本  │
                 └──────────┬───────────┘
                            │
                 ┌──────────▼───────────┐
                 │ Evolution Orchestrator│
                 │ GA/ES/DE/PSO/GP/AIS  │
                 │ 种群/代数/约束/预算   │
                 └──────────┬───────────┘
                            │ candidates
                 ┌──────────▼───────────┐
                 │  Evolution Sandbox    │
                 │ 离线回放/隔离执行     │
                 └──────────┬───────────┘
                            │ evidence
                 ┌──────────▼───────────┐
                 │   Fitness Service     │
                 │ 多目标/约束/置信度    │
                 │ Pareto → ranked 决策  │
                 └──────────┬───────────┘
                            │ ranked
                 ┌──────────▼───────────┐
                 │    Safety Gate        │
                 │ 策略/类型/测试/预算   │
                 └──────────┬───────────┘
                            │ safety_passed
                 ┌──────────▼───────────┐
                 │     Human Gate        │
                 │ 高风险 MUST；低风险可  │
                 │ 记录 policy 豁免证据  │
                 └──────────┬───────────┘
                            │ approved
                 ┌──────────▼───────────┐
                 │       Canary          │
                 └──────────┬───────────┘
                            │ deploy
                 ┌──────────▼───────────┐
                 │ Production + Monitor  │
                 └──────────┬───────────┘
                            │ feedback
                            └────→ Registry/Fitness
```

## 4. 核心组件

### 4.1 Genome Registry

管理“什么可以被进化”。

```yaml
genome:
  genome_id: routing.weights.v3
  target: execution.routing
  representation: continuous_vector
  fields:
    - name: semantic_weight
      type: float
      min: 0.0
      max: 1.0
    - name: cost_weight
      type: float
      min: 0.0
      max: 1.0
  constraints:
    - sum(semantic_weight, cost_weight) == 1.0
  mutable: true
  owner: platform-oncall
  evaluation_profile: routing_replay_v1
  rollback: versioned_config
```

要求：

```text
字段白名单
类型/范围/约束
owner
评估集
回滚方式
```

### 4.2 Evolution Orchestrator

负责算法插件和种群生命周期。

```text
init population
→ evaluate
→ select
→ reproduce
→ evaluate
→ ... 
→ produce ranked candidates
```

必须支持：

```text
随机种子固定
种群快照
代数/预算上限
早停
约束修复
Pareto 前沿
```

### 4.3 Fitness Service

适应度不是单一分数，而是向量：

```yaml
fitness:
  quality: 0.0-1.0
  cost: usd
  latency_p95_ms: number
  safety_violations: number
  policy_violations: number
  evidence_coverage: 0.0-1.0
  confidence: 0.0-1.0
```

约束：

```text
hard_constraints: 安全/合规/策略一票否决
soft_objectives: 质量/成本/延迟
```

选择方式（种群内）：

```text
1. 硬约束过滤（违规 → 淘汰，不计前沿）
2. 约束支配 + Pareto 非支配排序
3. 前沿内多样性保留（拥挤距离 / 网格）
```

#### 4.3.1 Pareto 前沿 → ranked 列表（强制决策规则）

Pareto 前沿上的解互相非支配，**天然不可全序**。要产出 `ranked candidates`，必须按下列固定管线（可复现、可审计）：

```text
A. 硬约束已通过的前沿成员
B. 预注册标量化偏好（默认）：
     score = w_q·quality − w_c·normalize(cost)
             − w_l·normalize(latency_p95)
             − w_s·safety_violations   # 应已为 0
   权重在 evaluation_profile 中预注册并版本化；禁止事后改权抬名次
C. 并列时：先更高 evidence_coverage，再更高 confidence，再更小 genome 字典序
D. 可选 knee-point：仅当 profile 声明 use_knee=true 时，
   在标量化之前用归一化前沿的最大边缘收益点插入 top；
   仍须留下完整前沿快照
E. 高风险 genome：排名仅供参考，最终上线人选由 HUMAN_GATE 人工挑选；
   机器序不得绕过人工挑选
```

输出必须同时保留：

```text
pareto_frontier[]     # 未标量化的前沿成员
ranked_candidates[]   # 按 A–E 得到的有序列表
ranking_profile_id    # 权重/规则版本
seed                  # 可复现
```

禁止：只用单一事后分数重排、不落盘前沿、改权重不升版本。

### 4.4 Evolution Sandbox

候选必须先在沙箱评估：

```text
离线回放
固定数据集
固定模型/索引快照
隔离网络
资源限额
无生产写权限
```

要求：

```text
可复现
可重放
可比较
可丢弃
```

### 4.5 Safety Gate

自动化门（**不是**人工批准）：

```text
策略门
类型/语法检查
单元/契约测试
安全扫描
预算检查
```

通过后状态为 `SAFETY_PASSED`。人工批准见 §4.6 / §6 的 `HUMAN_GATE`。

### 4.6 Human Gate

```text
高风险变体：MUST 人工批准（状态 HUMAN_GATE → APPROVED|REJECTED）
低风险变体：允许 policy 记录的自动通过，但仍写入 approver=system_policy
             + 豁免证据；可随时收回
禁止：把 Safety Gate 通过等同于 APPROVED
```

### 4.7 Canary + 回滚

```text
仅 APPROVED 之后进入 CANARY
小流量
指标对比
自动回滚阈值
版本化配置
血缘记录
```

## 5. 算法组合

| 算法 | 表示 | 适合 | 不适合 |
|---|---|---|---|
| GA | 离散编码 | 配置组合、Pipeline 结构、规则集 | 高维连续、昂贵评估 |
| ES | 连续向量 | 阈值、权重、步长自适应 | 离散结构 |
| DE | 连续向量 | 连续黑盒、参数调优 | 离散/树结构 |
| PSO | 连续向量 | 低维快速基线 | 多峰、噪声、强约束 |
| GP | 树/图/DSL | 规则树、Workflow、表达式 | 直接生成核心代码 |
| AIS | 抗体/签名 | 异常检测、攻击/故障签名 | 生成复杂策略 |

### 5.1 选择矩阵

```text
连续参数        → DE / ES
离散组合        → GA
规则/DSL        → GP（受限）
异常/免疫       → AIS
低维快速基线    → PSO
```

### 5.2 推荐优先级

```text
1. DE / ES  （低风险连续参数）
2. GA       （离散配置）
3. AIS      （异常免疫）
4. GP       （受限 DSL）
5. PSO      （仅基线/对照）
```

## 6. 演化闭环状态机（Candidate.status SSOT）

```text
DRAFT
  ↓
REGISTERED
  ↓
EVALUATING
  ↓
RANKED                 # 已按 §4.3.1 产出 ranked + 前沿快照
  ↓
SAFETY_PASSED / REJECTED   # 仅自动化 Safety Gate
  ↓
HUMAN_GATE             # 显式人工门（高风险不可跳过）
  ↓
APPROVED / REJECTED    # 仅人工（或低风险 policy 豁免证据）可进入 APPROVED
  ↓
CANARY
  ↓
PRODUCTION
  ↓
RETIRED / ROLLED_BACK
```

合法 `Candidate.status` 枚举（实现与实施方案必须全集对齐）：

```text
draft | registered | evaluating | ranked
| safety_passed | human_gate
| approved | rejected | canary | production
| retired | rolled_back
```

说明：

```text
evaluated 不是合法终态；评估中用 evaluating，评估完成进入 ranked 或 rejected
APPROVED ≠ SAFETY_PASSED
高风险：RANKED → SAFETY_PASSED → HUMAN_GATE → APPROVED → CANARY
低风险：HUMAN_GATE 可记录 policy 自动批准，但状态仍须经过 human_gate 节点
```

任何状态变迁都必须有：

```text
actor
timestamp
evidence
version
```

## 7. 评估预算

LLM/Agent 评估昂贵，必须限制：

```text
max_candidates
max_generations
max_llm_calls
max_tokens
max_wall_time
max_cost_usd
```

建议：

```text
先小种群粗筛
再大种群精评
使用缓存/回放
使用代理模型
```

没有预算控制的演化 = 成本失控。

## 8. 安全与合规

### 8.1 禁止

```text
生产环境直接自改代码
GP 生成核心 Python 代码
无沙箱执行候选
无人工门部署高风险变体
无血缘覆盖旧版本
```

### 8.2 必须

```text
PolicyGate 检查
租户隔离
审计日志
Human Gate 批准（高风险不可跳过；见 §4.6 / §6）
可回滚
Safety Gate 通过 ≠ 人工批准
```

## 9. 分阶段路线

### Phase 0：登记与基线（0–3 个月）

```text
Genome Registry
评估集/回放
fitness 基线
预算与血缘
```

### Phase 1：DE / ES 离线调参（3–6 个月）

对象：

```text
路由权重
检索参数
超时/重试阈值
模型选择权重
```

产出：

```text
候选排名
Pareto 前沿
人工审批
Canary
```

### Phase 2：GA 离散组合（6–9 个月）

对象：

```text
Pipeline 结构
Skill/Tool 组合
规则集
```

### Phase 3：AIS 异常免疫（6–12 个月）

对象：

```text
异常执行
提示注入
跨租户异常
知识冲突
```

先检测，不自动修复。

### Phase 4：GP 受限进化（12 个月+）

只允许：

```text
强类型 DSL
规则树
受限 Workflow
```

禁止直接生成核心代码。

## 10. KPI

| KPI | 含义 | 目标 |
|---|---|---|
| 候选可复现率 | 可重放候选/全部候选 | ≥95% |
| 血缘完整率 | 有 parent/evidence/version | 100% |
| 安全门拦截率 | 被拦截高风险候选/高风险候选 | 100% |
| Canary 回滚率 | 回滚/上线 | ≤5% |
| 评估成本/候选 | 平均 token/费用 | 有上限 |
| 进化增益 | 相对基线提升 | 按对象预注册（见 §10.1） |
| 回归率 | 上线后回归/上线 | ≤5%（相对冻结回归集） |

### 10.1 数据集隔离与冻结（强制）

每个 `evaluation_profile` 必须在 Registry 中声明并**冻结版本**：

| 分区 | 用途 | 默认比例（可按对象覆盖，须预注册） |
|---|---|---|
| tune | 调参 / 进化搜索 | 60% |
| validate | 选择与早停 | 20% |
| holdout | 最终增益报告（进化过程不可见） | 15% |
| regression | 上线前/后回归门 | 5% + 固定对抗集 |

规则：

```text
进化循环禁止读取 holdout / regression 标签或分数
增益只在 holdout 上报告；validate 只用于选型
regression 集变更必须升版本；旧 Canary 对比绑定旧版本
随机划分 seed 写入 lineage；禁止静默重划
进化增益 = holdout(primary_metric_candidate) − holdout(primary_metric_baseline)
  须带 CI；对象级 primary_metric 在 profile 预注册
```

## 11. 反模式

```text
用单一分数做适应度
在训练集上进化
没有 holdout
没有随机种子
没有预算
没有血缘
直接改生产
GP 生成核心代码
用进化绕过审批
```

## 12. 结论

```text
aiPlat 可以先做受控演化计算
不能做无人工门的生产自主进化
```

第一阶段最稳的组合：

```text
DE / ES 调连续参数
GA 调离散组合
AIS 做异常免疫
PSO 只做基线
GP 最后、受限、沙箱化
```

真正决定成败的不是算法，而是：

```text
基因组边界
评估质量
预算控制
安全门
血缘与回滚
```
