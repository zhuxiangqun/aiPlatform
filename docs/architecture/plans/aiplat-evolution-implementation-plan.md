---
doc_type: Architecture
title: aiPlat 闭环与演化计算实施方案
status: draft
authority: design-target
language: zh-CN
created: 2026-11-14
---

# aiPlat 闭环与演化计算实施方案

> 依据：
> - `docs/architecture/plans/aiplat-closed-loop-maturity.md`
> - `docs/architecture/plans/aiplat-evolutionary-computation-architecture.md`
>
> 本文是实施方案，不是当前实现状态，也不是认证结论。  
> 目标周期：以 2026-12 为 T0，12 个月。  
> 总原则：先补闭环，再做受控演化；不做生产环境无人工门的自主进化。

## 0. 结论先行

```text
当前整体约 L3
12 个月目标：
  治理 L2 → L3
  知识 L2–L3 → L3+
  评测 L3 → L4
  FDE L3 → L4
  执行 L4 → L4+
演化能力：
  E0（无） → E2（离线受控演化）
不追求：
  E5（生产自主进化）
```

第一阶段只做：

```text
Genome Registry
Fitness Service
离线回放沙箱
DE / ES 调参
人工批准 + Canary
```

## 1. 目标与非目标

### 1.1 目标

1. 建立五条闭环的可量化基线；
2. 把治理、知识、评测、FDE 补到 L3/L4；
3. 建立演化计算底座；
4. 用 DE/ES 在低风险对象上验证演化增益；
5. 形成可复现、可审计、可回滚的演化流程；
6. 为后续 GA/AIS/GP 扩展留接口。

### 1.2 非目标

```text
不让生产系统自动改核心代码
不用 GP 直接生成 Python
不跳过评测/审批/灰度
不以单一指标做适应度
不修改客户合同与授权边界
不把演化结果直接当对外承诺
```

## 2. 现状基线

| 闭环 | 当前 | 主要缺口 |
|---|:---:|---|
| 执行 | L4 | 结果回流学习不完整 |
| 评测 | L3 | 覆盖不足，自动修复最后一跳 |
| FDE | L3 | 客户数据/跨项目复用靠人工 |
| 知识 | L2–L3 | 证据覆盖、冲突裁决、错误回滚 |
| 治理 | L2 | 自动发现→自动修复不完整 |

必须先做基线测量，不能直接拿目标值当现状。

## 3. 实施原则

| # | 原则 |
|---|---|
| 1 | 先闭环，后演化 |
| 2 | 先离线，后 Canary，最后生产 |
| 3 | 先低风险参数，后结构/代码 |
| 4 | 多目标适应度，硬约束一票否决 |
| 5 | 每个候选有 genome、parent、evidence、version |
| 6 | 每个上线有审批、监控、回滚 |
| 7 | 评估预算有上限 |
| 8 | 失败可复现、可回退、可解释 |

## 4. 总体路线

```text
Phase 0  基线 + 治理补课 + 演化底座
Phase 1  DE/ES 离线调参试点
Phase 2  GA 离散组合 + 评测/FDE 提升
Phase 3  AIS 异常免疫 + GP 受限 DSL
Phase 4  L4 评估 + 规模化
```

每个 Phase 结束必须过 Gate，不通过不进入下一阶段。

## 5. 工作流

### WS0：治理闭环 L2 → L3

目标：

```text
问题自动发现
自动分级
自动派发
人工确认
```

交付：

- 问题分类法；
- 自动分级规则；
- 责任人与 SLA；
- 修复回执；
- 回归验证。

验收：

```text
问题发现覆盖率 ≥70%
自动分级率 ≥60%
MTTR ≤7d
回归率 ≤10%
```

### WS1：知识闭环 L2–L3 → L3+

目标：

```text
来源有 owner
关键断言有证据
冲突可裁决
错误可回滚
```

交付：

- 知识源 owner 清单；
- 证据覆盖检查；
- 冲突裁决流程；
- 知识版本与回滚；
- 反馈修正队列。

验收：

```text
来源 owner 覆盖率 ≥70%
证据覆盖率 ≥60%
冲突裁决率 ≥50%
错误回滚 ≤7d
```

### WS2：评测闭环 L3 → L4

目标：

```text
关键能力有评测
质量门自动执行
失败进入回归
低风险失败可自动修复
```

交付：

- 能力评测覆盖矩阵；
- 评测数据集与 holdout；
- 自动门禁；
- 失败回归；
- 评测证据包。

验收：

```text
能力评测覆盖率 ≥90%
门禁自动化率 ≥90%
失败回归率 ≥80%
证据完整率 ≥95%
```

### WS3：FDE 交付闭环 L3 → L4

目标：

```text
交付材料可自动生成
客户反馈结构化
交付模板可复用
```

交付：

- 交付证据清单；
- 客户反馈表单；
- 模板复用库；
- 项目知识沉淀；
- 签收闭环。

验收：

```text
交付证据覆盖率 ≥95%
客户反馈结构化率 ≥80%
模板复用率 ≥80%
签收闭环率 ≥95%
```

### WS4：演化计算底座

组件：

```text
Genome Registry
Evolution Orchestrator
Fitness Service
Evolution Sandbox
Safety Gate
Canary / Rollback
Lineage & Evidence
```

交付顺序：

```text
1. Registry schema
2. Fitness/Replay
3. Sandbox
4. DE/ES runner
5. Safety Gate
6. Canary/approval
7. GA/AIS/GP 扩展点
```

### WS5：安全、观测与审计

必须与 WS4 同步：

- 威胁模型；
- 沙箱隔离；
- 预算与限流；
- 审计日志；
- 血缘；
- 回滚演练；
- 人工门。

## 6. 参考架构

```text
Genome Registry
   ↓
Evolution Orchestrator
   ├── DE / ES
   ├── GA
   ├── PSO（基线）
   ├── GP（受限）
   └── AIS（检测）
   ↓
Evolution Sandbox
   ↓
Fitness Service
   ↓
Safety Gate
   ↓
Human Approval
   ↓
Canary → Production
   ↓
Monitor → Registry
```

### 6.1 逻辑模块

| 模块 | 职责 | 建议归属 |
|---|---|---|
| Genome Registry | 可进化对象、边界、版本 | Core 通用服务 |
| Evolution Orchestrator | 种群、代数、算法插件 | Core 通用服务 |
| Fitness Service | 多目标评估、回放 | Core + 评测 |
| Evolution Sandbox | 隔离执行、复现 | Infra/Core |
| Safety Gate | 策略、类型、测试、预算 | Platform + Core |
| Canary/Approval | 灰度、人工门 | Platform |
| Lineage Store | 血缘、证据、回滚 | Core/存储 |

> 模块名为逻辑名，实际目录在实现阶段按仓库边界确定，不在本方案中预设代码路径。

## 7. 数据契约

### 7.1 Genome

```yaml
genome_id: routing.weights.v1
target: execution.routing
representation: continuous_vector
fields:
  - name: semantic_weight
    type: float
    min: 0.0
    max: 1.0
constraints:
  - sum(weights) == 1.0
evaluation_profile: routing_replay_v1
owner: platform-oncall
mutable: true
rollback: versioned_config
```

### 7.2 Candidate

```yaml
candidate_id: ...
parent_ids: [...]
genome_id: ...
generation: 3
mutation: ...
created_at: ...
status: evaluated | ranked | approved | rejected | canary | production | rolled_back
```

### 7.3 Evaluation

```yaml
evaluation_id: ...
candidate_id: ...
dataset_version: ...
model_snapshot: ...
index_snapshot: ...
metrics: {...}
hard_constraints: {...}
evidence_ref: ...
```

### 7.4 Fitness

```yaml
quality: 0.0-1.0
cost_usd: ...
latency_p95_ms: ...
safety_violations: 0
policy_violations: 0
evidence_coverage: 0.0-1.0
confidence: 0.0-1.0
```

### 7.5 Approval

```yaml
candidate_id: ...
approver: ...
decision: approved | rejected
scope: ...
expires_at: ...
rollback_plan: ...
```

## 8. 算法策略

| 阶段 | 算法 | 对象 | 风险 |
|---|---|---|---|
| Phase 1 | DE / ES | 连续参数 | 低 |
| Phase 1 | PSO | 基线对照 | 低 |
| Phase 2 | GA | 离散配置 | 中 |
| Phase 3 | AIS | 异常/攻击签名 | 中 |
| Phase 3+ | GP | 受限 DSL/规则树 | 高 |

规则：

```text
连续参数优先 DE/ES
PSO 只做基线，不做主算法
GA 只做离散组合
AIS 先检测不生成
GP 只允许强类型 DSL
```

## 9. 首批试点对象

只选低风险、可回放、可回滚：

### 9.1 路由权重

```text
semantic_weight
cost_weight
latency_weight
```

评估：

```text
离线 query replay
质量/成本/延迟
```

### 9.2 检索参数

```text
top_k
score_threshold
rrf_weight
```

评估：

```text
Recall@k
citation 命中
回答质量
```

### 9.3 超时/重试

```text
timeout_ms
max_retries
backoff
```

评估：

```text
成功率
p95
成本
```

明确排除：

```text
Prompt 全文
PolicyGate 规则
核心 Python 代码
客户合同参数
```

## 10. 评估设计

### 10.1 数据集

```text
训练/调参集
验证集
holdout
对抗集
真实回放样本
```

### 10.2 统计

```text
预注册 primary metric
至少 2 个独立 batch
报告均值、置信区间、样本量
不只看单次最优
```

### 10.3 预算

```text
max_candidates
max_generations
max_llm_calls
max_tokens
max_wall_time
max_cost
```

预算在 G0 基线后设定，不能无限搜索。

## 11. 安全与合规

### 必须

```text
沙箱无生产写权限
PolicyGate 检查
租户隔离
人工批准
Canary
回滚演练
审计留痕
```

### 禁止

```text
生产自改代码
GP 生成核心代码
无 holdout 进化
无血缘覆盖
绕过审批
```

## 12. 12 个月计划

### Phase 0：基线 + 底座（M1–M3）

交付：

- 五条闭环 KPI 基线；
- 治理 L3 方案；
- 知识 owner/证据清单；
- Genome Registry schema；
- Fitness/Replay 原型；
- 预算与安全门设计。

Gate G0：

```text
基线有数据
owner 明确
试点对象确定
安全边界批准
```

### Phase 1：DE/ES 试点（M4–M6）

交付：

- 3 个低风险对象；
- DE/ES runner；
- 离线回放；
- 多目标排名；
- 人工审批；
- Canary 演练。

Gate G1：

```text
候选可复现率 ≥95%
血缘完整率 100%
硬约束零回归
至少 1 个对象有统计显著提升
```

### Phase 2：GA + 评测/FDE（M7–M9）

交付：

- GA 离散组合；
- 评测 L4 关键项；
- FDE L4 关键项；
- 自动回归。

Gate G2：

```text
评测覆盖 ≥90%
FDE 证据覆盖 ≥95%
GA 试点无安全回归
```

### Phase 3：AIS + GP 受限（M10–M12）

交付：

- AIS 异常检测；
- GP 强类型 DSL 沙箱；
- 生产候选评审；
- L4 评估报告。

Gate G3：

```text
AIS 误报可接受
GP 只在 DSL 内
生产候选 100% 人工批准
回滚演练通过
```

## 13. 前 90 天

| 周 | 任务 | 产出 |
|---|---|---|
| 1–2 | 基线测量 | KPI 基线表 |
| 3–4 | 试点对象选择 | 3 个 genome |
| 5–6 | Registry/Fitness schema | 数据契约 |
| 7–8 | 离线回放 | replay 结果 |
| 9–10 | DE/ES 原型 | 候选排名 |
| 11–12 | 安全门/审批演练 | Canary + 回滚报告 |

## 14. RACI

| 角色 | 职责 |
|---|---|
| 架构 owner | 方案、边界、Gate |
| Core/Platform 工程 | Registry/Orchestrator/Sandbox |
| 评测 owner | 数据集、fitness、统计 |
| SRE/Security | 沙箱、审计、回滚 |
| FDE/产品 | 试点对象、人工门 |
| 数据治理 | 知识 owner/证据 |

## 15. 验收 Gate

| Gate | 条件 |
|---|---|
| G0 | 基线、owner、预算、安全边界 |
| G1 | Registry/Fitness/Sandbox 可用 |
| G2 | DE/ES 试点有效且无硬约束回归 |
| G3 | Canary/回滚/人工门通过 |
| G4 | 治理/知识/评测/FDE 达到 L4 目标 |

## 16. KPI

沿用成熟度模型 KPI，并新增：

| KPI | 目标 |
|---|---|
| 候选可复现率 | ≥95% |
| 血缘完整率 | 100% |
| 安全门拦截率 | 100% |
| Canary 回滚率 | ≤5% |
| 评估预算超支 | 0 |
| 进化增益 | 按对象预注册 |
| 上线后回归率 | ≤5% |

## 17. 风险

| 风险 | 缓解 |
|---|---|
| Goodhart | 多目标 + holdout + 人工评审 |
| 评测噪声 | 重复 batch + 置信区间 |
| 成本失控 | 预算上限 + 小种群粗筛 |
| 安全退化 | 硬约束 + Safety Gate |
| 灾难性遗忘 | 回归集 + 回滚 |
| 不可复现 | seed + snapshot + lineage |
| GP 生成风险 | 强类型 DSL + 沙箱 + 人工门 |

## 18. 资源估算

建议最小团队：

```text
Core/Platform 工程 2
评测工程 1
SRE/Security 0.5
FDE/产品 0.5
架构 owner 0.25
```

预算：

```text
以 G0 基线为准
试点评估预算设硬上限
超过上限自动停止
```

## 19. Definition of Done

```text
五个闭环 KPI 有基线
Genome/Fitness/Sandbox 可用
DE/ES 试点完成
GA/AIS/GP 有扩展点
安全门/审批/回滚演练通过
L4 评估报告完成
```

## 20. 明确不做

```text
不做生产自主进化
不做无人工门部署
不做 GP 生成核心代码
不做单指标优化
不做无 holdout 的进化
不做绕过评测的发布
```

## 21. 结论

```text
第一步不是上算法，是补闭环和评估
第二步是 DE/ES 离线试点
第三步才是 GA/AIS/GP
```

如果只能做一件事：

```text
先把 Genome Registry + Fitness + Sandbox + Safety Gate 建起来
```

否则任何演化算法都只会变成不可控的自动调参。
