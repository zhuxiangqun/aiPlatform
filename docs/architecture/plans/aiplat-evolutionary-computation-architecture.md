---
doc_type: Architecture
title: aiPlat 演化计算架构
status: draft
authority: design-target
language: zh-CN
created: 2026-11-14
---

# aiPlat 演化计算架构

> 本文是目标架构与实施框架，不是当前实现状态。  
> 范围：为 aiPlat 的闭环系统增加**受控、可审计、可回滚**的演化计算能力。  
> 非目标：让生产系统无人工门地自改代码。

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
                 └──────────┬───────────┘
                            │ ranked
                 ┌──────────▼───────────┐
                 │    Safety Gate        │
                 │ 策略/类型/测试/预算   │
                 └──────────┬───────────┘
                            │ approved
                 ┌──────────▼───────────┐
                 │ Canary + Human Gate   │
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

选择方式：

```text
Pareto 非支配排序
+ 约束支配
+ 多样性保留
```

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

上线前必须通过：

```text
策略门
类型/语法检查
单元/契约测试
安全扫描
预算检查
人工门（高风险）
```

### 4.6 Canary + 回滚

```text
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

## 6. 演化闭环状态机

```text
DRAFT
  ↓
REGISTERED
  ↓
EVALUATING
  ↓
RANKED
  ↓
APPROVED / REJECTED
  ↓
CANARY
  ↓
PRODUCTION
  ↓
RETIRED / ROLLED_BACK
```

任何状态都必须有：

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
人工批准
可回滚
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
| 进化增益 | 相对基线提升 | 按对象定义 |
| 回归率 | 上线后回归/上线 | ≤5% |

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
