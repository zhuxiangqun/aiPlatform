---
doc_type: Architecture
title: aiPlat 闭环与演化计算实施方案
status: draft
authority: design-target
language: zh-CN
created: 2026-11-14
doc_id: AIPLAT_EVOLUTION_IMPLEMENTATION_PLAN_6856B3
last_reviewed: 2026-11-25
---
# aiPlat 闭环与演化计算实施方案

> 依据：
> - `docs/architecture/plans/aiplat-closed-loop-maturity.md`
> - `docs/architecture/plans/aiplat-evolutionary-computation-architecture.md`
>
> 本文是实施方案，不是当前实现状态，也不是认证结论。  
> 目标周期：以 2026-12 为 T0，12 个月。  
> 总原则：先补闭环，再做受控演化；不做生产环境无人工门的自主进化。  
> **SSOT**：`Candidate.status` 与状态机以演化计算架构 §6 为准；Phase Gate 以本文 §12 / §15 **同一套 G0–G3** 为准（禁止第二套含义）。  
> **2026-11-25**：G0 底座 **slice-1** 已接线（`core/harness/evo_compute/` + CoreFacade + 基线落盘）；证据 `reports/architecture/evo-compute/phase0-g0-foundation-slice1-evidence.md`。  
> **2026-11-25**：G0 **slice-2** 已接线（三试点 genome + 预算硬上限 + 安全边界契约 + 夹具回放 + `evaluate_g0_exit_readiness`）；证据 `reports/architecture/evo-compute/phase0-g0-pilots-slice2-evidence.md`。  
> **2026-11-25**：G0 **人工签批**（对话「批准」；actor=`zhu-ying`）— 预算上限 + 安全边界已签字；夹具回放齐备后 `evaluate_g0_exit_readiness.phase0_complete=true`；证据 `reports/architecture/evo-compute/phase0-g0-human-signoff-evidence.md`。  
> **未宣称** DE-ES / E2 / 生产流量真实回放认证 / 闭环已测 L4；`certified`/`e2_claimed` 恒 false。

## 0. 结论先行

```text
闭环等级：工作假设整体 ≈ L3（待 KPI 基线；见成熟度模型 §3）
12 个月目标：
  治理 假设L2 → 已测 L3
  知识 假设L2–L3 → 已测 L3+
  评测 假设L3 → 已测 L4
  FDE 假设L3 → 已测 L4
  执行 假设L4 → 已测 L4+
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

| 闭环 | 工作假设（非已测） | 主要缺口 |
|---|:---:|---|
| 执行 | 假设 L4 | 结果回流学习不完整 |
| 评测 | 假设 L3 | 覆盖不足，自动修复最后一跳 |
| FDE | 假设 L3 | 客户数据/跨项目复用靠人工 |
| 知识 | 假设 L2–L3 | 证据覆盖、冲突裁决、错误回滚 |
| 治理 | 假设 L2 | 自动发现→自动修复不完整 |

必须先做基线测量，不能直接拿目标值或工作假设当已测现状。  
等级判定公式见成熟度模型 §3.2（六维度 `min` ∩ KPI 列）。

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
Fitness Service（Pareto → ranked，见架构 §4.3.1）
   ↓
Safety Gate → safety_passed
   ↓
Human Gate → approved | rejected
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

> `status` 枚举与架构文档 §6 **逐字对齐**（SSOT）。禁止使用已废除的 `evaluated`。

```yaml
candidate_id: ...
parent_ids: [...]
genome_id: ...
generation: 3
mutation: ...
created_at: ...
status: draft | registered | evaluating | ranked | safety_passed | human_gate | approved | rejected | canary | production | retired | rolled_back
ranking_profile_id: ...   # §4.3.1 标量化/knee 规则版本
pareto_frontier_ref: ...  # 前沿快照证据
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

与架构 §10.1 对齐并冻结版本：

```text
tune (默认 60%)     — 调参/进化搜索
validate (20%)      — 选型/早停
holdout (15%)       — 最终增益；进化不可见
regression (5%)     — 回归门 + 固定对抗集
真实回放样本        — 可映射进上述分区，须声明
```

### 10.2 统计

```text
预注册 primary metric + 检验族（默认：双侧均值差，Welch t 或 bootstrap CI）
预注册显著性阈值 α（默认 0.05）与最小效应量
至少 2 个独立 batch
报告均值、置信区间、样本量
不只看单次最优
```

#### 10.2.1 多重比较 / 选择偏差（强制）

演化会评估大量候选再挑「最好的」，必须校正：

```text
1. 预注册最大候选评估数 N_max（计入预算）
2. 主结论只允许：
   - 预指定单一 primary 对比（baseline vs 预声明 challenger），或
   - 对 holdout 上最终入选者 vs baseline 做一次确认检验
3. 若在 validate 上比较 K 个候选再晋升：
   - 使用 Bonferroni / Holm 按 K 校正，或
   - 预注册门控筛选 + holdout 一次性确认（推荐）
4. 「统计显著提升」= holdout 上 primary 相对 baseline
   在预注册 α（经校正后）下拒绝 H0，且效应 ≥ 预注册最小效应量
5. 探索性分析可报告，但不得单独满足 Phase Gate
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

## 12. 12 个月计划（Phase Gate = G0–G3，与 §15 同一套）

### Phase 0：基线 + 底座（M1–M3）

交付：

- 五条闭环 KPI 基线（成熟度 §7）；
- 治理 L3 方案；
- 知识 owner/证据清单；
- Genome Registry schema；
- Fitness/Replay 原型 + ranking_profile；
- Sandbox 可跑通一次离线评估；
- 预算与 Safety/Human Gate 设计。

**Gate G0**（Phase 0 出口）：

```text
基线有落盘数据（非文档自述）
owner 明确
预算上限批准
安全边界批准
Registry / Fitness / Sandbox 最小可用（可注册 genome、评估 1 个候选、留证据）
试点对象确定
```

> slice-1 进度：Registry/Fitness/Sandbox/状态机/基线 **落盘能力** 已可用。  
> slice-2 进度：三试点已选型登记、预算/安全**契约与硬停**已可用、夹具回放链路已通。  
> 人工签批：预算上限与安全边界已由 `zhu-ying` 批准（2026-11-25）；Gate G0 出口就绪 `phase0_complete=true`（夹具回放）。生产流量真实回放认证仍属加深项，**不得**据此宣称 E2 / certified。

### Phase 1：DE/ES 试点（M4–M6）

交付：

- 3 个低风险对象；
- DE/ES runner；
- 离线回放；
- 多目标排名（§4.3.1）；
- 状态机走通至 human_gate → approved；
- Canary + 回滚演练。

**Gate G1**（Phase 1 出口）：

```text
候选可复现率 ≥95%
血缘完整率 100%
硬约束零回归
至少 1 个对象在 holdout 上按 §10.2.1 定义「统计显著提升」
Canary / 回滚 / Human Gate 演练通过（含状态 HUMAN_GATE）
```

### Phase 2：GA + 评测/FDE（M7–M9）

交付：

- GA 离散组合；
- 评测 L4 关键项；
- FDE L4 关键项；
- 自动回归。

**Gate G2**（Phase 2 出口）：

```text
评测覆盖 ≥90%
FDE 证据覆盖 ≥95%
GA 试点无安全回归
```

### Phase 3：AIS + GP 受限（M10–M12）

交付：

- AIS 异常检测；
- GP 强类型 DSL 沙箱；
- 生产候选评审（100% Human Gate）；
- 闭环 L4 评估报告（按成熟度 §3.2，有基线）。

**Gate G3**（Phase 3 出口）：

```text
AIS 误报在预注册阈值内
GP 只在 DSL 内
生产候选 100% 经 HUMAN_GATE 批准
回滚演练通过
治理/知识/评测/FDE 已测等级达 L4 目标（或差距清单 + owner 签字缓释）
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

## 15. 验收 Gate（与 §12 同一套；禁止并行定义）

| Gate | Phase 出口 | 条件（摘要；细节以 §12 为准） |
|---|---|---|
| G0 | Phase 0 | 基线落盘 + owner + 预算 + 安全边界 + Registry/Fitness/Sandbox 最小可用 + 试点确定 |
| G1 | Phase 1 | DE/ES 可复现/血缘/硬约束 + holdout 统计显著（§10.2.1）+ Canary/回滚/Human Gate 演练 |
| G2 | Phase 2 | 评测/FDE L4 关键覆盖 + GA 无安全回归 |
| G3 | Phase 3 | AIS/GP 边界 + 生产候选 100% Human Gate + 回滚 + 闭环 L4 评估报告 |

已废除：另设「G1=仅底座 / G2=仅 DE/ES / G3=仅 Canary / G4=成熟度」的第二套含义。  
成熟度 L4 并入 **G3** 交付（评估报告），不再使用独立 G4 门号。

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
