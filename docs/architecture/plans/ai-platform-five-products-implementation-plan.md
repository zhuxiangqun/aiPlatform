# 五产品域完整实施方案（已收敛）

> **已由落地方案取代为日常执行真源。**  
> → 请使用：**[ai-platform-five-products-landing-plan.md](./ai-platform-five-products-landing-plan.md)**  
>  
> 本文保留作历史草稿索引。路径、门禁、WP/DoD 以**落地方案 v1.3**为准（§3.6 Blocker/Known Gap/E3 归属；L1 ≠ Gate 1；仅有条件批 L1）。  

> 母稿：[target-architecture](./ai-platform-five-products-target-architecture.md) · Pi：[pi-thin-runtime](./pi-thin-runtime.md)

---

## 0. 一页纸：要做成什么

### 0.1 目标终态（产品语义）

| # | 产品 | 一句话 | 权威数据 |
|---|------|--------|----------|
| 1 | **aiPlat** | 企业 AI 控制与治理 | 租户/策略、Agent 资产版本、平台治理记录 |
| 2 | **Pi** | 企业部署侧 AI Runtime（Thin / Enterprise / +aiPlat） | Runtime 实例、部署版本、环境配置、执行状态 |
| 3 | **本体平台** | 企业语义数据资产与 AI 数据服务 | Ontology、Mapping、语义数据、质量与模型版本 |
| 4 | **FDE 平台** | FDE 场景实施与交付 | 客户项目、需求、决策、任务、验收证据 |
| 5 | **诊断平台** | 跨产品评估 / 测试 / 监控 / 诊断 | 评测集、测试运行、监控关联、诊断报告与证据引用 |

### 0.2 实施总策略（四句）

1. **产品独立 → 接口独立 → 代码模块化 → 按需部署拆分**；前三步未完成前不做第四步。  
2. **先契约与一条纵向切片，再模块化切片暴露的边**；禁止五产品同步开工。  
3. **证据等级 E0–E5**；静态能力清单 / 图谱 / 架构守卫绿 ≠ 行为可用。  
4. **共享控制面默认在 aiPlat**，契约可接外部 IAM；各产品本地仍须鉴权。

### 0.3 批准范围分层

| 批准级别 | 授权内容 | 不授权 |
|----------|----------|--------|
| **L0 方向批准** | 五产品边界叙事、本实施方案作为操作手册 | 任何生产路径改动 |
| **L1 切片准备**（Brief） | WP0 限时盘点、WP1/WP2 契约最小版、场景提名 | 搬目录、拆服务、诊断全功能 |
| **L2 切片执行**（Gate 1） | WP3–WP4 在隔离环境跑通纵向路径 | 跨库直写「临时方案」上线 |
| **L3 扩大产品化**（Gate 2） | 按切片暴露问题做 facade/守卫/局部迁移 | 无证据的全面重构 |
| **L4 独立部署**（Gate 3） | 单产品拆进程/库/集群 | 无 owner/on-call/成本评估的拆分 |

---

## 1. 原则与硬约束

### 1.1 四层边界（必须分清）

| 层 | 含义 | 本方案优先 |
|----|------|:----------:|
| 产品边界 | 用户、价值、责任、路线图 | ✅ 立即 |
| 接口边界 | 版本化 API / SDK / 事件 | ✅ WP1–WP2 |
| 代码边界 | facade、依赖方向、可测可替 | ✅ Gate 2 后按需 |
| 部署边界 | 进程 / DB / 集群 | ❌ 仅 Gate 3 |

### 1.2 硬禁止（任何阶段）

- 用目录搬迁代替契约。  
- 用客户端 / Pi native tool gate 代替服务端授权。  
- 跨产品共享数据库作为正式集成契约。  
- 缺证据时报告 healthy / 成功。  
- 将 Pi Thin 表述为已完成 Enterprise Runtime。  
- 将 Management 页面等同诊断产品或本体产品。  
- 将能力行数、CAPABILITIES ✅、图谱节点、静态门禁当作生产就绪。  
- 厂内 Pi 编码实验未单独 RFC + caller + 行为验收前进入主路径。

### 1.3 证据等级（贯穿全程）

| 等级 | 证据 | 允许表述 |
|------|------|----------|
| E0 | 文档 / 能力清单 | 「设计存在」 |
| E1 | 源码入口 + 静态路径 | 「代码存在」 |
| E2 | 单测 / 离线 smoke | 「局部逻辑通过」 |
| E3 | 多服务集成 | 「指定组合接线有效」——**切片路径关键能力最低** |
| E4 | 干净环境部署验收 | 「指定版本行为成立」——**对外承诺最低** |
| E5 | 生产运营数据 | 「运行可靠」 |

---

## 2. 组织与 RACI

### 2.1 角色（可兼任，不可空缺）

| 角色 | 职责 | Gate 签署 |
|------|------|----------|
| 架构决策 owner | 边界、ADR、依赖方向、冲突裁决 | Gate 1/2/3、暂停/恢复 |
| 业务场景 owner | 场景、价值、验收人、失败成本 | Gate 1/2、暂停/恢复 |
| aiPlat 产品 owner | 控制面、资产、编排治理 | 本产品相关 WP |
| Pi 产品 owner | Thin/Enterprise 规格与验收 | 本产品相关 WP |
| 本体产品 owner | 模型/映射/查询权威 | 本产品相关 WP |
| FDE 产品 owner | 交付对象与验收链 | 本产品相关 WP |
| 诊断产品 owner | 证据/报告 MVP | 本产品相关 WP |
| 安全/身份 reviewer | 身份透传、策略、密钥、副作用 | Gate 1 安全项 |
| 测试/验收 owner | 可重复环境与证据包 | Gate 2 |
| 运维 owner | 部署、升级、告警、备份 | Gate 3 |

**暂停 / 恢复**：架构决策 owner **与** 业务场景 owner **联合**签署；单一产品 owner 不得单方面推翻。

### 2.2 RACI（工作包级）

| 工作包 | 架构 | 业务 | 五产品 owner | 安全 | 测试 | 运维 |
|--------|:----:|:----:|:------------:|:----:|:----:|:----:|
| WP0 盘点 | A | C | R | C | C | I |
| WP1 边界决策 | A | C | R | C | I | I |
| WP2 契约 | A | I | R | R | C | C |
| WP3 切片设计 | A | A | R | R | R | C |
| WP4 切片执行 | C | A | R | C | A | R |
| WP5 回顾 backlog | A | C | R | C | C | C |
| 模块化（Gate2+） | A | C | R | C | R | C |
| 独立部署（Gate3） | A | C | R | R | R | A |

R=执行 · A=问责 · C=协商 · I=知会

---

## 3. 路线总览与时间盒

```text
L1 批准
  │
  ▼
WP0 盘点（≤2 周，仅切片路径）──► WP1 边界冻结 ──► WP2 契约最小版
  │                                                      │
  └──────────────────────── Gate 1 ──────────────────────┘
                              │
                              ▼
                    WP3 切片设计 ──► WP4 切片执行（隔离环境）
                              │
                         Gate 2？
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
     仅模块化暴露的边                    暂停/缩范围
     （facade / 守卫 / 局部迁移）
              │
         Gate 3？（可选，证据驱动）
              ▼
        单产品独立部署
```

| 阶段 | 时间盒（建议） | 出口 |
|------|----------------|------|
| WP0 | ≤ 10 个工作日 | 切片路径事实清单 + 缺口 + 后置项 |
| WP1 | ≤ 3 个工作日（可与 WP0 尾重叠） | 五产品边界签字表 |
| WP2 | ≤ 5 个工作日 | 六契约最小 schema + 兼容矩阵 + 失联语义 |
| Gate 1 | 评审会 1 次 | Brief 5 项拍板 |
| WP3 | ≤ 5 个工作日 | 测试计划 + 环境清单 + 回滚方案 |
| WP4 | ≤ 10 个工作日 | 证据包 + 验收表 |
| Gate 2 | 评审会 1 次 | 是否扩大 |
| 模块化波次 | 按暴露边排期 | 每波独立 DoD |
| Gate 3 | 按需 | 拆分决策包 |

**日历日期不在缺现状数据时写死**；WP0 结束后由架构 owner 填入实际起止日。

---

## 4. 首个纵向切片（唯一主路径）

### 4.1 路径定义

```text
FDE 建场景/验收标准
  →（可选）本体评估数据准备度
  → aiPlat 发布版本化 Agent Bundle
  → Pi 在目标环境部署并运行（首切片建议 Thin 或声明子集的 Enterprise）
  → 诊断接入 Pi + aiPlat 证据 → 可追溯报告
  → FDE 验收 / 整改任务
  → 故障注入：断连 / 拒权 / 过期 → 无伪成功
```

### 4.2 首切片强制范围

| 纳入 | 排除（暂缓） |
|------|----------------|
| 1 客户/项目/场景 | 多域并行 |
| 1 本体域 + 1 受控查询（若路径需要） | 全量 ingestion 重建 |
| 1 Agent Bundle + 1 Pi 环境 | 高风险副作用工具 |
| 诊断：**仅 Pi + aiPlat** 证据流 | 本体/FDE 诊断 adapter（后置） |
| FDE：Engagement、Scenario、Requirement、DeliveryPlan、Evidence、Acceptance | 甘特/CRM/全能工单 |
| 1 次失联/拒权/过期语义测试 | 自动跨平台修复 |

### 4.3 场景准入（Gate 1 前）

业务侧会前 **3 个工作日**提交：

1. 场景名称与业务用户  
2. 可重复输入 / 预期输出 / 失败条件  
3. 业务验收签署人  
4. 失败成本说明（为何值得做）  
5. 数据敏感级别与是否可用隔离环境  

无真实客户时：允许**内部可复现场景**，必须标注「非客户验收」；Gate 2 扩大前须客户场景替换或背书。

---

## 5. 工作包详解

### WP0 — 现状盘点（切片路径限定）

#### 目标

回答：这条路径上**现在实际跑什么、谁调谁、谁写权威数据、身份在哪校验、副作用在哪发生**。

#### 范围纪律

- **必做**：切片将经过的入口、caller、数据 owner、身份流、副作用、版本字段、运行证据。  
- **后置**：全仓依赖图、全能力条目证据升级、切片未使用产品的深挖。  
- 切片未使用的产品维度标「切片未使用」，**不阻塞 Gate 1**。

#### 建议调查命令与落点（示例，按仓库现状调整）

```bash
# FDE 触达 knowledge/ontology 的生产调用面
rg -n 'from core\.harness\.(knowledge|ontology)' aiPlat-core/core/apps/fde --glob '*.py'

# Platform FDE API 面
rg -n '@router\.' aiPlat-platform/apps/fde/api --glob '*.py' | head

# Pi 包与工厂导出
ls packages/aiplat-pi-runtime
rg -n 'export_pi_bundle|aiplat-pi-runtime' scripts packages --glob '*.{py,ts,md,sh}' | head

# 控制面 / 身份
rg -n 'require_auth|PolicyGate|_resolve_identity' aiPlat-platform/auth aiPlat-platform/api --glob '*.py' | head
```

产物写入：`reports/five-products/wp0-slice-inventory-YYYY-MM-DD.md`（过程材料；**不要**堆进 `docs/research/`）。

#### 必填表模板

**表 A — 能力与入口**

| 能力 | 产品 owner | 入口路径 | 实际 caller | 证据等级 | 备注 |
|------|------------|----------|-------------|----------|------|
| | | | | E? | |

**表 B — 依赖边**

| 边类型 | 源 | 目标 | 机制（import/HTTP/DB/事件） | 是否公开契约 | 风险 |
|--------|----|------|------------------------------|:------------:|------|
| | | | | 是/否 | |

**表 C — 数据 owner**

| 实体 | 权威 owner | 主存储 | 写入方 | 只读方 | 缓存？版本/新鲜度字段？ |
|------|------------|--------|--------|--------|-------------------------|
| | | | | | |

**表 D — 身份与副作用**

| 操作 | 签发方 | 校验方 | 允许的 scopes | 副作用 | 失联默认 |
|------|--------|--------|---------------|--------|----------|
| | | | | | fail-closed / … |

**表 E — 关闭/归档实验**

| 路径 | 状态 | 是否有生产 caller | 是否出现在能力声明 | 处置 |
|------|------|:-----------------:|:------------------:|------|
| 厂内 Pi 编码旁路等 | closed/archive | | | 保持关闭 |

#### DoD

- [ ] 切片每条调用边有代码入口 + caller（或明确「缺失 → 阻塞 Gate1」）  
- [ ] 切片每类数据有唯一 owner；缓存单独标注  
- [ ] Pi Thin 已实现 vs Enterprise 缺口清单  
- [ ] 诊断现状 vs MVP 差距清单  
- [ ] 所有「已接线」声明带证据等级；关键能力 ≥ E3 或降级表述  
- [ ] 时间盒到期：未完成项标「未知/后置」，附恢复条件  

---

### WP1 — 产品边界与决策冻结

#### 目标

把母稿中的职责表变成**已签字的切片范围边界**，消灭双重 owner。

#### 活动

1. 对照母稿 §3 产品表，填写「本切片使用 / 不使用 / 后置」。  
2. 裁决 Knowledge 三分归属（仅切片涉及部分）：  
   - 语义事实 / 模型版本 → 本体  
   - Agent 检索编排 / 降级 → aiPlat  
   - 跨产品证据索引 → 诊断  
3. 裁决编排引擎归属表述：  
   - **控制面与资产发布** ∈ aiPlat  
   - **厂外执行宿主** ∈ Pi  
   - **Harness 内核** 仍属共享执行底座，产品化时经公开接口暴露，不把 FDE 业务写回 harness  
4. 确认 `shared/identity` **仅契约/SDK**；默认实现在 aiPlat。

#### 产物

- `reports/five-products/wp1-boundary-signoff-YYYY-MM-DD.md`  
- ADR-01 草稿（可先一页）

#### DoD

- [ ] 五产品 owner 姓名 + 替补人  
- [ ] 无「双权威」实体残留在切片路径  
- [ ] 非目标清单已贴到切片看板（防范围膨胀）  

---

### WP2 — 契约最小版与兼容矩阵

#### 六类契约（最小字段集）

以下为**首切片必须可测**的最小集；完整字段见母稿 §8。

**1) Identity / Policy**

```text
tenant_id, actor_id|service_id, scopes[], audience,
request_id, trace_id, product_id, environment_id,
authn_source (aiplat|external_iam), expires_at
```

验收：目标服务拒绝伪造 tenant/actor；客户端 gate 不能放行服务端已拒操作。

**2) Agent Bundle**

```text
bundle_id, schema_version, source_asset_ids[], asset_versions[],
runtime_compat_range, permission_claims[], model_requirements,
build_info, integrity (hash|sig), rollback_hint
```

验收：不兼容 / 损坏包在安装前拒绝；permission_claims **不能**单独授权。

**3) Runtime Control**

```text
instance_id, deploy_version, config_version, health,
heartbeat_at, event_types[], offline_until, command_authz
```

验收：控制面断开时副作用 fail-closed（按 WP2 表决策）。

**4) Semantic Query**

```text
ontology_version, mapping_version, query_id,
provenance[], freshness (as_of|lag), permission_decision
```

验收：无版本/来源则不可进入 FDE 验收「通过」。

**5) Evidence / Diagnosis**

```text
event_schema_version, source_product, source_instance, environment,
asset_versions{}, run_id, trace_id, severity, status,
evidence_refs[], report_rule_version, generated_at
```

验收：报告可回溯；缺证据 → `unknown`/`stale`，禁止默认 `healthy`。

**6) Delivery**

```text
engagement_id, scenario_id, requirement_ids[],
refs {agent_bundle, runtime, ontology, diagnosis_report},
acceptance_status, evidence_ids[], decided_by, decided_at
```

验收：FDE 不写对方 DB；只持稳定引用。

#### 兼容矩阵（必须填实，禁空模板）

| 对象 | 生产者 | 消费者 | 当前版本 | 支持窗口 | 不兼容行为 | owner |
|------|--------|--------|----------|----------|------------|--------|
| Bundle schema | aiPlat | Pi | | | 安装前拒绝 | |
| Runtime API | Pi | 控制面 | | | | |
| Ontology query | 本体 | aiPlat/Pi/FDE | | | | |
| Evidence event | Pi/aiPlat | 诊断 | | | 忽略未知可选字段 | |
| Delivery | FDE | adapters | | | 状态幂等 | |
| Identity | aiPlat/IAM | 全服务 | | | | |

#### 控制面不可用语义（逐行决策）

沿用执行计划 §4.4 表；WP2 结束时每行必须是「可继续有限 / fail-closed / stale 展示」之一，并有负责人。

#### 产物落点

- `shared/contracts/` 逻辑归属（**先文档 + schema 草案**，不强制新建包）  
- 建议路径：`docs/architecture/contracts/five-products/`（若创建，须登记 DOCUMENT_SYSTEM；本阶段也可先放 `reports/five-products/contracts/`）

#### DoD

- [ ] 六契约均有生产者、消费者、版本、错误语义  
- [ ] 兼容矩阵无「待指定」空单元格（切片用到的行）  
- [ ] 失联语义表签字  
- [ ] 至少 1 组契约负向用例清单（伪造身份、坏 bundle、过期策略）  

---

### Gate 1 — 进入切片执行

对照 [Decision Brief](./ai-platform-five-products-decision-brief.md) 五项 + 下列清单：

- [ ] 场景与验收人确认  
- [ ] Pi 形态（Thin / Enterprise 子集）确认  
- [ ] 控制面：aiPlat 默认 **或** 外部 IAM（禁止双重授权）  
- [ ] WP0 切片路径无「阻塞级未知」  
- [ ] WP2 最小契约可用  
- [ ] 隔离环境、密钥、数据脱敏方案就绪  
- [ ] 回滚：可回滚 Agent bundle 版本 **或** Runtime 版本  
- [ ] 安全 reviewer 对副作用范围签字（首切片应为低风险/只读）  

**未过 Gate 1：禁止改生产默认路径、禁止宣称五产品已产品化。**

---

### WP3 — 切片设计

#### 交付物

1. **序列图**：身份签发 → 各产品调用 → 证据回流 → 验收  
2. **环境清单**：模型、密钥、网络、是否允许出网  
3. **数据夹具**：最小 ontology / 项目 / bundle 样例（可合成）  
4. **测试计划**：正确性 + 安全负向 + 失联 + 可重复性  
5. **运维手册草稿**：安装 Pi、导出 bundle、查看报告、回滚  
6. **风险与暂停触发**：映射执行计划 §5.6  

#### DoD

- [ ] 每步有责任产品与证据文件名约定  
- [ ] 失败注入用例 ≥ 3（断连、拒权、过期/缺失证据）  
- [ ] 回滚演练步骤可在 30 分钟内执行（设计层）  

---

### WP4 — 切片执行与证据包

#### 执行顺序（建议日计划）

| 日 | 活动 |
|----|------|
| D1 | 环境拉起；导出/安装 bundle smoke |
| D2 | FDE 建档 + 验收标准入库 |
| D3 | 本体查询（若纳入）带版本结果 |
| D4 | aiPlat 发布 + 审计记录核对 |
| D5–D6 | Pi 运行主路径；采集 run/trace |
| D7 | 诊断报告生成与关联校验 |
| D8 | FDE 验收签字；整改任务演练 |
| D9 | 故障注入三连 |
| D10 | 证据包归档 + 缺陷归因会 |

#### 证据包目录（建议）

```text
reports/five-products/slice-<id>/
  VERSIONS.md          # 代码/配置/bundle/runtime/ontology/规则版本
  RUNLOG/              # 关键运行日志（脱敏）
  DIAGNOSIS_REPORT.md
  ACCEPTANCE.md        # 业务签署
  FAILURE_INJECTION.md
  GAPS.md              # 暴露的边界问题 → WP5 backlog
```

#### 验收表（必须全部勾选或明确「失败归因产品」）

**正确性**

- [ ] FDE 需求 → Agent → Bundle → Pi 实例 →（Ontology 版本）→ 诊断报告 可追溯  
- [ ] Pi 输出符合预定义结果契约  
- [ ] 本体结果含来源/版本（若路径使用）  
- [ ] FDE 接受/拒绝有证据  

**安全**

- [ ] 服务端校验 tenant/actor/scope/资源  
- [ ] 无授权工具调用被拒；客户端不能绕过  
- [ ] 失联时高风险副作用 fail-closed  
- [ ] 无证据不标 healthy  
- [ ] 日志/报告无 token/密钥明文  

**可重复与运维**

- [ ] 干净环境按手册重跑成功  
- [ ] 版本集合完整保存  
- [ ] 失败可定位到产品边界  
- [ ] 可回滚 bundle 或 Runtime  

#### DoD

- [ ] 证据包完整  
- [ ] 测试/验收 owner 签署  
- [ ] `GAPS.md` 每条有严重度与建议处置（契约 / facade / 后置）  

---

### WP5 — 架构回顾与 Backlog

#### 产出

1. 更新 ADR-01～03（至少）；其余 ADR 按需开立  
2. **仅针对 GAPS** 的模块化 backlog（每项：收益、成本、依赖、证据）  
3. Gate 2 建议：扩大 / 维持切片运维 / 暂停  
4. 明确**不做清单**再冻结一轮  

#### DoD

- [ ] 无「因为目录好看而搬迁」项进入 backlog  
- [ ] 每项后续改造有切片证据链接  

---

## 6. Gate 2 之后：模块化实施规范

仅处理 WP4 暴露且 Gate 2 批准的边。

### 6.1 标准手法（按优先级）

| 优先级 | 手法 | 适用 |
|:------:|------|------|
| 1 | 公开 API / facade + 改 caller | 跨产品 import 私有模块 |
| 2 | 版本化 DTO / 事件 | 共享可变结构体 |
| 3 | 依赖守卫（arch_guard / import-linter） | 防止回潮 |
| 4 | DB 直连 → API（双读窗口） | 跨域写权威库 |
| 5 | 目录搬迁 | **最后**；单子域 + 行为回归 + 回滚 |

### 6.2 单波次 DoD

- [ ] 变更限定在批准的边  
- [ ] 契约测试或集成测试覆盖该边  
- [ ] 无新的跨域私有 import（守卫或评审证明）  
- [ ] 回滚说明  
- [ ] 能力声明若变更：同步 CAPABILITIES **且**不升证据等级至超过实测  

### 6.3 建议模块化波次（示例，以 GAPS 为准裁剪）

| 波次 | 主题 | 典型现况锚点 |
|------|------|----------------|
| M1 | FDE → 本体/知识：去直连，经 facade | `core/apps/fde/service/*` 对 `harness.knowledge` / ontology |
| M2 | aiPlat 工厂 → Pi：bundle 契约硬化 | `scripts/export_pi_bundle.py` ↔ `packages/aiplat-pi-runtime` |
| M3 | 诊断证据：Pi/aiPlat 事件 schema 落地 | 各层 diagnostics API vs Management 页 |
| M4 | Knowledge 拆分（仅已证明边界） | `harness/knowledge` 按 owner 切读写面 |
| M5 | 关闭实验隔离检查 | 厂内 Pi 路径无生产 caller |

---

## 7. 各产品实施规格（中长期，Gate 2+ 按需）

> 以下不是首切片并行任务；是 Gate 2 后产品化清单。每条启动需单独批准与 owner。

### 7.1 aiPlat

| 主题 | 工作项 | 验收 |
|------|--------|------|
| 控制面契约 | Identity/Policy 稳定 API；禁私有 import | 契约测试 + 外部 adapter 桩 |
| 资产生命周期 | 发布/撤回/版本/审计 | 与 Bundle 字段对齐 |
| 编排治理 | 平台侧运行治理与配额 | 与 Pi 执行职责不重叠说明 |
| 去业务化 | FDE/诊断业务逻辑迁出 harness | 守卫拦截回归 |

### 7.2 Pi

| 主题 | 工作项 | 验收 |
|------|--------|------|
| Thin 规格锁定 | 无 aiPlat 时可完成声明闭环 | 干净环境 E4 |
| Enterprise 规格 | 安装/升级/回滚/健康/事件/离线 | 与 Thin 兼容矩阵 |
| +aiPlat | 服务端授权；native gate 仅防旁路 | 负向测试 |
| 实验隔离 | 厂内编码路径保持 closed | 无生产能力声明 |

参考：[pi-thin-runtime.md](./pi-thin-runtime.md)

### 7.3 本体

| 主题 | 工作项 | 验收 |
|------|--------|------|
| Model/Mapping/Query API | 版本、来源、新鲜度 | 同版本可复现 |
| 与 RAG 边界 | 派生索引打标 | 非权威 |
| 去 DB 直连 | FDE/aiPlat 改走 API | 双读窗口后切断 |

### 7.4 FDE

| 主题 | 工作项 | 验收 |
|------|--------|------|
| 六类核心对象 | 见执行计划 §8 | 状态机测试 |
| Adapters | aiPlat/Pi/本体/诊断/客户系统 | 至少 1 个非 aiPlat 组件参与 |
| 权限与客户隔离 | 项目边界 | 串租负向测试 |

### 7.5 诊断

| 主题 | 工作项 | 验收 |
|------|--------|------|
| MVP | Pi+aiPlat 证据、关联、报告、unknown/stale | 首切片已验可扩展 |
| Evaluation/Testing | 第二阶段 | 单独 RFC |
| Remediation | 只建议/建任务；执行走目标产品 API | 无超级权限 |
| Management | 可作入口，非唯一模型 | 规则不进纯前端 |

---

## 8. ADR 实施顺序

| ADR | 最早时机 | 阻塞关系 |
|-----|----------|----------|
| ADR-01 五产品边界与非目标 | WP1 | Gate 1 |
| ADR-02 控制面与外部 IAM | WP2 | 含身份的切片步骤 |
| ADR-03 数据 owner | WP1–WP2 | 任何跨产品写 |
| ADR-04 Pi 形态与兼容 | Gate 1 前 | Pi 步骤 |
| ADR-05 本体 vs Knowledge/RAG | 本体纳入切片或 M4 前 | 语义查询验收 |
| ADR-06 FDE 对象与适配 | WP3 | FDE 验收对象 |
| ADR-07 诊断证据与修复权 | WP2–WP4 | 诊断报告 |
| ADR-08 部署拆分门槛 | Gate 3 前 | 拆服务 |
| ADR-09 关闭实验与能力声明 | WP0/WP5 | 能力对外表述 |

模板要求：上下文、决策、备选、影响、迁移、回滚、重评触发条件。

---

## 9. 质量、测试与 CI 挂钩

### 9.1 测试分层

| 层 | 内容 | 所有者 |
|----|------|--------|
| 契约测试 | schema、兼容、负向授权 | 契约 owner |
| 单产品 | 母稿 §13 各产品重点 | 产品 owner |
| 切片 E2E | 路径 §4 + 故障注入 | 测试 owner |
| 回归守卫 | 禁止私有跨域 import 回潮 | 架构 |

### 9.2 与现有门禁关系

| 现有机制 | 在本方案中的角色 |
|----------|------------------|
| `architecture_guard` / constitution | **必要非充分**；管静态边界 |
| capability truth / CAPABILITIES | 声明层；**不得**单独当 E4 |
| defect-gate | 合并/推送纪律；不替代切片验收 |
| Docs verify / link gate | 文档完整性；不证明运行 |

新增守卫建议（Gate 2+）：`import-linter` 或 arch_guard 规则——`apps/fde` 禁止直 import `harness.knowledge` 内部模块（仅允许 facade）。

---

## 10. 风险登记与应对（实施版）

| ID | 风险 | 信号 | 应对 | 升级 |
|----|------|------|------|------|
| R1 | 范围膨胀 | 五 API 并行新建 | 冻结非目标；变更走 ADR | 架构+业务暂停 |
| R2 | 隐性单体 | 私有 import 回潮 | 守卫+契约测试 | Gate 2 拒绝扩大 |
| R3 | Pi 过度承诺 | 对外称 Enterprise 已完成 | 形态矩阵+证据等级 | 产品 owner 更正文案 |
| R4 | 双权威数据 | 两边都「可写」 | WP1 裁决；缓存打标 | 阻塞验收 |
| R5 | 权限旁路 | 只测 UI gate | 强制服务端负向测 | 安全一票否决 |
| R6 | 伪健康 | 缺数据仍绿 | unknown/stale 硬验收 | 诊断报告作废 |
| R7 | Owner 空缺 | 决策无人签 | 替补人；否则停 Gate1 | 评审主席 |
| R8 | 业务挤占 | 验收无限延期 | 正式暂停，保留 WP0/1 | 联合恢复签署 |

---

## 11. 目标逻辑结构（迁移地图，非立即执行）

```text
products/
  aiplat/{control_plane,agent_lifecycle,governance,api}/
  pi/{runtime/thin,runtime/enterprise,adapters,packaging,docs}/
  ontology/{model,ingestion,mapping,semantic_store,query,governance,api}/
  fde/{projects,discovery,delivery,acceptance,integrations,api}/
  diagnostics/{evaluation,testing,telemetry,correlation,diagnosis,remediation,adapters}/
shared/{contracts,sdk,identity,observability,security,connectors}/
```

| 现有区域 | 方向 | 触发迁移的证据 |
|----------|------|----------------|
| `harness/ontology_engine/` | 本体核心，经 API 隔离 | M 波次证明直连有害 |
| `harness/knowledge/` | 三分 owner | ADR-05 + 切片/GAPS |
| `core/apps/fde` + `platform/apps/fde` | FDE 域收敛 | M1 |
| `packages/aiplat-pi-runtime/` | Pi Thin + 分类 | ADR-04 |
| `scripts/export_pi_bundle.py` | aiPlat 工厂打包 | M2 |
| 各层 diagnostics + Management | 事实提供器 vs 诊断分析 | 诊断 MVP |

**`shared/identity`**：只放契约与 SDK；**实现默认在 aiPlat**。

---

## 12. 沟通与文档落点纪律

| 材料 | 落点 |
|------|------|
| 目标架构 / ADR / 本实施方案 | `docs/architecture/plans/`（及后续 ADR 目录） |
| WP0–WP5 过程清单、证据包 | `reports/five-products/` |
| 禁止 | 把过程盘点堆回 `docs/research/` |
| 对外承诺 | 仅 E4+ 且文案经产品 owner |

---

## 13. 启动检查清单（评审会当天）

**会前（业务，≥3 个工作日）**

- [ ] 候选场景 + 验收人 + 失败成本  

**会上拍板（Brief 五项）**

- [ ] 场景  
- [ ] 业务验收人  
- [ ] Pi 形态  
- [ ] 控制面/IAM  
- [ ] Gate1/暂停签署人  

**会后立即**

- [ ] 指定五产品 owner + 替补  
- [ ] 开 `reports/five-products/` 目录与 WP0 时间盒截止日期  
- [ ] 架构 owner 发布本实施方案的「L1 已批准」变更记录（日期/范围）  

---

## 14. 成功定义

### 14.1 L1（准备）成功

WP0 在时间盒内交付切片路径事实；WP2 契约可测；Gate 1 可开。

### 14.2 L2（切片）成功

隔离环境端到端可重复；安全与失联用例通过；证据包完整；失败可归因到产品边界。

### 14.3 L3（扩大）成功

仅模块化有证据的边；守卫防回潮；对外表述证据等级不虚高。

### 14.4 L4（拆分）成功

满足母稿独立部署门槛 + 成本/运维评估 + 迁移回滚演练。

---

## 15. 明确不实施清单（再次冻结）

- 不一次性拆五个仓库 / 五个数据库 / 五个微服务。  
- 不把所有身份与业务数据集中进 aiPlat DB。  
- 不把 Pi Thin 写成完整企业 Runtime。  
- 不把本体等同图库或 RAG。  
- 不把 FDE 做成通用项目管理套件。  
- 不把诊断做成超级权限或默认自动修复。  
- 不在 Gate 1 前做全仓目录搬迁。  
- **不在本文件批准前实施产品代码改造**（除非另有明确工程任务授权）。

---

## 16. 与既有三份文档的关系

| 文档 | 角色 |
|------|------|
| `ai-platform-five-products-target-architecture.md` | **规范**：目标边界、契约、owner、ADR 母稿 |
| `ai-platform-five-products-decision-brief.md` | **决策请求**：批准什么 / 不批准什么 |
| `ai-platform-five-products-execution-plan.md` | **首切片执行计划**：WP0–WP5 与 Gate |
| **本文** | **完整实施方案**：RACI、时间盒、模板、DoD、模块化规范、产品规格与启动清单 |

冲突裁决：评审纪要 > 更新后的母稿 > 执行计划 > 本文操作细节。

---

## 17. 变更记录

| 版本 | 日期 | 说明 |
|------|------|------|
| 0.1 | 2026-10-23 | 首版完整实施方案；衔接既有三稿与五产品改造提案；明确不自动授权编码 |

---

**批准含义**：批准进入 **L1 切片准备（WP0–WP2）** 的操作手册与治理方式。  
**下一步**：开评审会完成 Decision Brief 五项拍板 → 启动 WP0 时间盒。
