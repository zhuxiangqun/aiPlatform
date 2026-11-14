---
doc_type: Architecture
title: 知识系统 v4.3.1 实施方案
status: draft
authority: design-target
language: zh-CN
created: 2026-11-14
---

# 知识系统 v4.3.1 实施方案

> 依据：
> - `docs/standards/knowledge-system/v4.3.1/technical-whitepaper.md`
> - `docs/standards/knowledge-system/v4.3.1/normative-appendix.md`
>
> 本文是把 v4.3.1 标准落到 aiPlat 的实施计划，不是标准正文，也不是当前实现状态声明。  
> 标准生效日：2027-01-01。本文按“先试点域、再平台化、最后规模化”的方式实施。

## 0. 结论先行

```text
v4.3.1 不是一套“知识库功能清单”
而是一套“事实/证据/语义/动作/查询/安全/认证”的完整契约
```

实施顺序必须是：

```text
先事实底座
再对象/证据
再动作/查询
再体验/场景
最后规模化与认证
```

不能反过来：

```text
先做 Wiki/Agent/UI
再补事实与证据
```

否则会形成“读模型先行、事实层缺失”的假闭环。

## 1. 目标与范围

### 1.1 目标

1. 在试点域内实现 v4.3.1 Core 符合性；
2. 扩展到 Extended 能力（对象/动作/函数/接口/对象集/SDK/场景）；
3. 建立 Operational 能力（SLO/备份/恢复/审计/迁移）；
4. 形成可审计的 conformance 证据包；
5. 为全平台推广提供可复制模板。

### 1.2 范围

```text
Raw / Source Registry
Ontology / ObjectType / LinkType
Fact / Claim / Evidence / Review / Revision / Conflict
Object projection / Index / Wiki
Action / Function / Interface
Query / ObjectSet / SDK / Agent Tool
Execution / SQL boundary
Security / multi-tenant / ACL
Scenario / Package
Quality / calibration / conformance
Migration / rollback
```

### 1.3 非目标

```text
一次性替换所有现有系统
让 LLM 自动批准本体/动作
允许任意 SQL 执行
把 Wiki 当事实源
没有证据就宣称符合
把认证当安全认证/合规认证
```

## 2. 实施原则

| # | 原则 |
|---|---|
| 1 | Raw 不可变，事实可追溯 |
| 2 | 先事实账本，后派生视图 |
| 3 | 语义模型版本化，不自动改 |
| 4 | Fact/Claim 必须有 evidence |
| 5 | 动作必须有契约、权限、审批、审计、回滚 |
| 6 | 权限召回前过滤 |
| 7 | 查询不写事实，动作才写事实 |
| 8 | 场景不污染主事实 |
| 9 | 没有证据不得宣称符合 |
| 10 | 先试点域，再复制 |

## 3. 当前基线与差距

> 标准是目标态；当前实现是否符合，必须 Phase 0 用证据测量，不能凭文档推断。

Phase 0 必须产出：

```text
现有资产盘点
现有数据流/权限/动作清单
现有 Wiki/索引/向量库/图/业务库映射
v4.3.1 24 项 conformance 差距表
试点域选择
owner 与验收人
```

差距分类：

| 类型 | 例子 | 处理 |
|---|---|---|
| 有实现无证据 | 有事实表但无 evidence | 补证据/审计 |
| 有数据无契约 | 有对象但无 ObjectType | 补语义契约 |
| 有动作无门禁 | 有 handler 无审批/回滚 | 补 L1 硬门 |
| 有查询无权限 | 召回后才过滤 | 改为召回前过滤 |
| 有 Wiki 无事实源 | Wiki 直接编辑 | 改为读模型 |
| 有场景写主库 | 模拟污染事实 | 隔离场景 |

## 4. 目标架构

```text
Raw Sources
  ↓
Source Registry
  ↓
Ingestion / Extraction
  ↓
Fact Store（Fact/Claim/Evidence/Review/Revision/Conflict）
  ↓
Object Projection / Object Index
  ↓
Query / ObjectSet / SDK / Agent Tool
  ↓
Wiki / Object Browser / Action Console / Review Console
  ↑
Action / Function / Interface
  ↓
Policy / Approval / Audit / Snapshot
```

### 4.1 真相层级

```text
事实源：Raw、Ontology、Fact Store、ActionExecution
派生：ObjectInstance、ObjectIndex、ObjectSet、Wiki、SDK、App
```

### 4.2 建议默认实现栈

标准不绑定数据库；v1 建议：

```text
Raw：对象存储（S3/MinIO）+ 不可变 hash
Fact/Evidence：PostgreSQL + JSONB
图投影：GraphIndex
检索：全文 + 向量索引
Wiki：读模型/编译产物
动作：ActionRegistry + PolicyGate
审计：ActionExecution + audit log
```

选择理由：

```text
关系约束 + JSONB 灵活字段
容易做事务/审计/迁移
图/向量作为投影，不成为第二事实源
```

## 5. 工作流

### W0：项目与符合性基线

交付：

- 试点域（建议一个中等复杂度域）；
- 资产/owner 清单；
- v4.3.1 24 项 checklist 差距表；
- 目标等级（Core/Extended/Operational）；
- 验收人与评审节奏。

验收：

```text
差距表有证据
每项有 owner
试点域边界明确
```

### W1：Raw 与 Source Registry

任务：

- Raw 不可变快照；
- source_id / locator / hash / 抓取时间；
- 来源策略（权威/时效/适用范围）；
- 来源 owner；
- 删除/撤回策略。

验收：

```text
Raw 可追溯
来源有 owner
来源策略可执行
```

### W2：语义模型

任务：

- ObjectType / LinkType；
- 属性、主键、数据绑定；
- 版本化；
- 漂移检测 → 提案 → 人审 → 新版本；
- 禁止自动改本体。

验收：

```text
类型有版本
变更有人审
对象映射可追溯
```

### W3：Fact / Claim / Evidence

任务：

- Fact/Claim/Evidence/Review/Revision/Conflict 记录；
- 必填字段：tenant_id、evidence、source_policy、extractor_version、review_status、status、confidence、valid_from/to、revision；
- 审核状态与生命周期状态分离；
- 冲突裁决；
- 推断标记 `inferred=true`。

验收：

```text
无 evidence 不 published
状态转换有 actor/time/reason
冲突未裁决不发布
```

### W4：对象投影、索引、Wiki

任务：

- Fact Store → ObjectInstance；
- ObjectIndex 重建；
- Wiki 编译；
- 血缘/健康；
- 有条件重建；
- 区分精确重放/语义重建/不可重建。

验收：

```text
派生视图可重建
重建条件有记录
不复制第二套事实
```

### W5：Action / Function / Interface

任务：

- ActionContract；
- FunctionContract；
- Interface；
- 管理画面 draft → review → publish；
- dry-run；
- 权限/审批/回滚/自主度；
- 禁止 LLM 自动发布。

验收：

```text
动作有契约/权限/审计/回滚
函数默认无副作用
接口兼容性校验
```

### W6：查询 / ObjectSet / SDK / Agent Tool

任务：

- 统一查询入口；
- 租户/权限前置；
- 对象/事实优先；
- ObjectSet；
- SDK 生成；
- Agent 工具只调用查询/动作，不直写；
- 防假绿/abstain。

验收：

```text
召回前过滤
引用可定位
无证据 abstain
查询不写事实
```

### W7：执行边界

任务：

- L1 硬门：ActionContract/PolicyGate/ACL/状态机；
- 审批；
- 实体锁；
- ActionExecution；
- before/after snapshot；
- idempotency；
- kill switch；
- Lv4 误报率门。

验收：

```text
无 L1 高风险动作不上生产
动作记录可审计
失败可回滚
```

### W8：安全与多租户

任务：

- 租户隔离；
- 实例/字段级 ACL；
- 权限透传；
- 跨租户负向测试；
- 审计留存。

验收：

```text
跨租户 0 泄漏
权限不扩大
字段级策略生效
```

### W9：场景 / Package

任务：

- Scenario 隔离；
- 分支 owner/过期；
- 合并人审；
- Package 版本/签名/兼容。

验收：

```text
模拟不写主事实
包可验证
版本兼容
```

### W10：质量 / 校准 / 认证 / 迁移

任务：

- 指标定义；
- confidence 校准；
- OCS；
- conformance 24 项；
- 迁移/双写/对账/回滚；
- 认证证据包。

验收：

```text
指标有数据集/版本/门槛
conformance 有证据
迁移不丢数据
```

## 6. 分阶段计划

### Phase 0：基线与试点（M1）

交付：

- 试点域；
- 资产/owner 清单；
- 差距表；
- 目标等级；
- 迁移策略。

Gate G0：

```text
差距有证据
owner 明确
试点边界批准
```

### Phase 1：事实底座（M2–M4）

交付：

- Raw/Source Registry；
- Fact/Claim/Evidence；
- ObjectType/LinkType；
- 统一查询最小闭环；
- 租户隔离。

Gate G1：

```text
Raw 不可变
Fact 有 evidence
查询前置权限
跨租户测试通过
```

### Phase 2：对象/动作/查询（M5–M7）

交付：

- Object projection/index/Wiki；
- Action/Function/Interface；
- Policy/Approval/Audit；
- ObjectSet/SDK/Agent tool；
- 管理画面。

Gate G2：

```text
动作有 L1 硬门
对象/索引可重建
查询/动作不越权
```

### Phase 3：体验/场景（M8–M10）

交付：

- Wiki 规模化；
- 对象浏览器；
- 动作台/审核台；
- 场景/分支；
- Package。

Gate G3：

```text
场景不污染事实
审核台可闭环
包可验证
```

### Phase 4：规模化/认证（M11–M12）

交付：

- SLO/容量/恢复；
- 迁移/回滚演练；
- conformance 证据包；
- 复制模板。

Gate G4：

```text
24 项 checklist 有证据
SLO 达标
迁移/回滚通过
```

> 12 个月是“单试点域 + 核心平台”的目标；全平台推广建议 18–24 个月。

## 7. 前 90 天

| 周 | 任务 | 产出 |
|---|---|---|
| 1–2 | 资产盘点/试点域 | 资产清单 |
| 3–4 | 差距表 | 24 项 checklist |
| 5–6 | Raw/Source Registry 设计 | 数据契约 |
| 7–8 | Fact/Evidence 最小表 | schema/迁移 |
| 9–10 | 查询最小闭环 | 租户/权限 |
| 11–12 | 证据/验收 | G1 预演 |

## 8. 迁移方案

### 8.1 映射

```text
现有 Wiki → 读模型
GraphIndex → 对象投影
向量 KB → Raw/检索索引
TripleStore → 关系/语义
业务库 → Source/ObjectType 绑定
```

### 8.2 步骤

```text
盘点
映射
双写/影子写
回填
对账
灰度读
切换写
回滚演练
旧系统只读/退役
```

### 8.3 验收

```text
数据不丢
证据可追溯
权限不扩大
查询可对账
动作可回滚
旧系统退役有记录
```

## 9. 符合性测试

### 9.1 结构

```text
JSON Schema
23 defs
22 示例
```

命令：

```bash
python3 schemas/validate_examples_v4.3.1.py
```

### 9.2 语义

```text
22 示例
30 用例
```

命令：

```bash
python3 schemas/validate_semantics_v4.3.1.py
```

### 9.3 负向

```text
缺 evidence
越权
冲突未裁决
状态非法转换
跨租户
```

### 9.4 认证

按 N 的 24 项 checklist 逐项提供证据：

```text
架构说明
数据契约
权限矩阵
测试/评测报告
迁移/回滚记录
SLO
例外 ADR
```

## 10. CI 门禁

```text
schema 校验
语义校验
24 项 conformance
权限/跨租户负向测试
迁移/回滚演练
文档/链接
```

没有证据不得标记通过。

## 11. KPI

| KPI | 目标 |
|---|---|
| Raw 可追溯率 | 100% |
| Fact/Claim evidence 覆盖率 | 100% published |
| 跨租户泄漏 | 0 |
| 动作 L1 硬门覆盖率 | 100% 高风险动作 |
| 24 项 conformance | 24/24 |
| 证据包完整率 | 100% |
| 查询 p95 | ≤2s |
| 动作成功率 | ≥99.5% 生产 SLO |

## 12. RACI

| 角色 | 职责 |
|---|---|
| 知识系统 owner | 标准、范围、Gate |
| 本体工程师 | ObjectType/LinkType/Interface |
| 数据工程 | Raw/Source/Fact/Evidence |
| 平台工程 | Query/Action/SDK/Admin |
| 安全 | Policy/ACL/审计 |
| 评测 | 指标/校准/OCS |
| FDE/业务 | 试点域、语义、验收 |

## 13. 风险

| 风险 | 缓解 |
|---|---|
| 先做 UI 后补事实 | Gate 强制事实底座优先 |
| 无 evidence 发布 | Schema/语义门 |
| 权限召回后过滤 | 召回前过滤测试 |
| 本体漂移 | 版本化 + 人审 |
| 迁移丢数据 | 双写/对账/回滚 |
| 场景污染事实 | 隔离 + 合并人审 |
| 假绿 | 证据包 + 负向测试 |
| 范围过大 | 单试点域先行 |

## 14. Definition of Done

```text
试点域 Core 符合
Extended 关键能力可用
Operational 证据完整
24 项 conformance 有证据
迁移/回滚演练通过
KPI 达标
```

## 15. 明确不做

```text
不做一次性全平台替换
不让 LLM 自动发布本体/动作
不做无证据的“符合”
不做查询层写事实
不做场景写主库
不做任意 SQL
```

## 16. 结论

```text
v4.3.1 的实施不是“建一个知识库”
而是“建立事实/证据/语义/动作/查询/安全/认证的完整契约”
```

最小正确起点：

```text
Raw 不可变
+ Source Registry
+ Fact/Claim/Evidence
+ ObjectType
+ 查询前置权限
```

这四件事不做，后面的 Wiki、Agent、SDK 都会变成空中楼阁。
