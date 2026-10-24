# 五产品域落地方案（唯一执行真源）

> **文档类型**：落地方案 / Design Plan  
> **状态**：v1.3 · 2026-10-23 基线 · **2026-10-24 首切片落地收口**（见 [`reports/five-products/LANDING_CLOSEOUT.md`](../../../reports/five-products/LANDING_CLOSEOUT.md)）  
> **性质**：指导盘点、契约、首切片、模块化与按需拆部署的**完整执行真源**。  
> **冲突裁决**：本文 > 执行计划摘要 > Decision Brief / PPT / 发言稿。目标边界细节仍引用 [目标架构母稿](./ai-platform-five-products-target-architecture.md)；若与本文路径/门禁冲突，**以本文为准并回写母稿**。  
> **本文不是**：评审会脚本；也**不**表示全面改造已获批或五产品已对外产品化。  
> **当前批准范围**：L1（WP0–WP2）已书面获准；Gate 1 修订已批准本切片完整 WP3–WP4 并合入 main（E3 / 非客户验收）。**Gate 2 / Gate 3 / D13 扩大仍未批**（建议维持：`reports/five-products/GATE2_RECOMMENDATION.md`）。  
> **卫星材料**：Brief / 发言稿 / PPT 大纲 / 执行摘要已于同日按 v1.3 口径回写；收口后抽查以 `LANDING_CLOSEOUT.md` 为准。

---

## 0. 已锁定决策（落地方案基线）

以下不再作为「会上待选项」；变更须走 ADR 修订。

| ID | 决策 | 锁定内容 |
|----|------|----------|
| D1 | 五产品域 | aiPlat / Pi / 本体 / FDE / 诊断；产品独立 ≠ 立刻微服务 |
| D2 | 首切片主路径 | **方案 A（本体非必经）**：见 §3；§3.1 是**目标路径**，不是「现网已贯通」的断言 |
| D3 | 诊断首切片证据 | **仅 Pi + aiPlat**；本体/FDE adapter 后置 |
| D4 | 契约分类 | **六类**为分类全集；**Gate 1 只要求本切片实际使用的契约填实**；未启用类标「本切片未启用」且**不阻塞** Gate 1（见 §5 WP2） |
| D5 | 控制面 | aiPlat 为默认实现；契约可接外部 IAM；目标服务本地鉴权；禁止双重授权含糊并行 |
| D6 | Pi 首切片默认形态 | **Pi Thin**；若做 Enterprise 必须书面列出「本次验证子集」 |
| D6b | Pi Thin「无 aiPlat 闭环」含义 | 指 **已签名 Bundle 落盘后，执行阶段**在 aiPlat 断连时可按离线策略继续；**不是**整条「发布+诊断」链路都不依赖 aiPlat（见 §3.5、§7.2） |
| D7 | 门禁命名 | **L1 准备 ≠ Gate 1**。L1/准备=WP0–WP2；**Gate 1=允许开跑 WP3–WP4**；Gate 2=扩大模块化；Gate 3=独立部署 |
| D8 | 证据等级 | **切片完成**时关键路径 ≥ **E3**、对外承诺 ≥ **E4**（由 WP4 产生，见 §3.6）；Gate 1 **不**要求整条路径已有 E3。静态门禁绿 ≠ 可用 |
| D9 | 共享 identity | `shared/identity` **仅契约与 SDK**；默认实现在 aiPlat |
| D10 | 厂内 Pi 编码实验 | 保持 closed/archive；进主路径须独立 RFC + 生产 caller + E4 |
| D11 | WP0–WP2 时间盒含义 | 上限用于**盘点与形成最小可测契约草案**，**不是**强行交付六套已稳定生产 API |
| D12 | 缺口分类 | 区分 **阻塞项** vs **已知缺口**（§3.6）；禁止把新建路径冒充现状；已知缺口可随 Gate 1 批准进入 WP3–WP4 |
| D13 | 内部场景与 Gate 2 | 内部「非客户验收」可至 Gate 1/切片；**Gate 2 前**须客户场景替换或**书面客户背书**（最低字段见 §6.0.1）。取消须 ADR |
| D14 | 工作包问责 | 每包一名主 A；A′=共同签署。Gate 1/2/3 联签规则**独立于**工作包主 A（§2.2.1）。争议裁决见同节 |

---

## 1. 目标与非目标

### 1.1 目标

形成五个各自有用户、职责、数据 owner 与交付方式的产品域，并通过版本化 API/SDK/事件组合：

| 产品 | 核心职责 | 权威数据 | 明确不负责 |
|------|----------|----------|------------|
| **aiPlat** | 资产生命周期、控制面、编排治理、配额审计、平台运营 | 租户/策略、Agent 等资产版本、平台治理记录 | 本体权威、FDE 项目事实、诊断报告权威库 |
| **Pi** | 安装/配置/升级/运行 Agent；Runtime 实例与执行状态 | Runtime 实例、部署版本、环境配置、执行状态 | 中心 IAM/策略权威；用客户端 gate 替代服务端授权 |
| **本体** | 模型、映射、语义存储、查询/推理、质量与版本 | Ontology、Mapping、语义数据、质量与模型版本 | Agent 生命周期、通用 Runtime |
| **FDE** | 场景→方案→实施→验收证据链 | 项目、需求、计划、任务、验收证据 | 自建 Runtime/本体引擎/诊断引擎；通用项目管理套件 |
| **诊断** | 证据接入、关联、报告；后续评测/测试 | 评测/测试运行、关联索引、诊断报告与证据引用 | 源系统唯一运行事实；默认跨平台修复权 |

### 1.2 终态关系（组合，非强制全连接）

```text
                 FDE（场景 → 验收）
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
        本体 ◄────────► aiPlat ────────► 诊断
          │                 │
          │                 ▼
          └────────────►   Pi
```

### 1.3 非目标（全程禁止当作本方案交付）

- 五仓库 / 五数据库 / 五微服务一次性拆分  
- 全仓目录搬迁先行  
- 诊断全功能（全量评测编排、自动根因修复、跨平台自动执行）  
- FDE 做成甘特/CRM/全能工单  
- 将 Pi Thin 表述为已完成 Enterprise Runtime  
- 用 CAPABILITIES / 图谱 / architecture_guard 绿代替行为验收  
- 跨产品共享 DB 作为正式集成契约  
- 缺证据时报告 healthy/成功  

### 1.4 四层边界推进顺序

1. 产品边界 → 2. 接口边界 → 3. 代码模块边界 → 4. 部署边界  
未完成前一层，不开下一层的大规模动作。

---

## 2. 组织、RACI 与启动条件

### 2.1 角色（可兼任，关键角色不可空）

| 角色 | 职责 |
|------|------|
| 架构决策 owner | 边界、ADR、依赖方向、Gate/暂停裁决 |
| 业务场景 owner | 场景、价值、验收标准、业务失败成本 |
| 五产品 owner | 各域范围、指标、本域验收 |
| 安全/身份 reviewer | 身份、策略、密钥、副作用 |
| 测试/验收 owner | 可重复环境、证据包、验收表 |
| 运维 owner | 隔离环境、升级回滚、告警 |

**暂停/恢复**：架构决策 owner **与** 业务场景 owner **联合**签署。

### 2.2 RACI

图例：**A** = 主问责（Primary，每包仅一名）· **A′** = 共同签署人（Co-sign，须联签产出物；争议不享最终裁决权）· R/C/I 同常义。

| 工作包 | 架构 | 业务 | 产品 owner | 安全 | 测试 | 运维 | 主 A |
|--------|:----:|:----:|:----------:|:----:|:----:|:----:|:----:|
| WP0 | A | C | R* | C | C | I | 架构 |
| WP1 | A | C | R | C | I | I | 架构 |
| WP2 | A | I | R | R | C | C | 架构 |
| WP3 | A | A′ | R | R | R | C | 架构 |
| WP4 | C | A | R | C | A′ | R | 业务 |
| WP5 | A | C | R | C | C | C | 架构 |
| 模块化（Gate2+） | A | C | R | C | R | C | 架构 |
| 独立部署（Gate3 工作包） | A′ | A′ | R | R | R | A | 运维 |

\*WP0 在正式产品 owner 到位前的 **临时执行** 见 §2.4。  
\*\*Gate 3 行**：运维=工作包主 A；架构与业务均为 **A′**（产出联签）。**Gate 3 门禁本身**仍须架构 × 业务联合签署（下款），与运维主 A 并存。

#### 2.2.1 共同签署与争议裁决

1. **主 A**：对该工作包「完成定义 / 是否达标 / 是否可提交下一门禁」负最终责任，并在产出物上主签。  
2. **A′（共同签署人）**：必须联签；可提出否决异议；**不能**单独宣布工作包完成。  
3. **主 A 与 A′ 意见不一致**时：  
   - 涉及业务价值、验收标准、场景是否成立 → **业务场景 owner** 裁决（书面）。  
   - 涉及边界、契约、依赖方向、安全语义 → **架构决策 owner** 裁决（书面）。  
   - 仍冲突或涉及安全一票否决 → **安全 reviewer** 可阻塞；最终升级由架构 × 业务按暂停规则联合处理。  
4. **Gate 1 / Gate 2 / Gate 3 / 暂停 / 恢复**（门禁层）：一律由架构决策 owner × 业务场景 owner **联合签署**。此规则**独立于**上表工作包主 A——例如 Gate 3 工作包可由运维主责执行，但「是否批准独立部署」仍须架构×业务联签。

### 2.3 进入 L1 / 启动 WP0 的最低条件

须**同时**满足，且有书面「获准进入 L1」记录后，才启动 WP0：

1. 架构决策 owner、业务场景 owner 已指定（可同一人兼任，须书面）。  
2. 场景候选已写明：输入、预期输出、失败条件、是否客户场景；若内部场景须标「**非客户验收**」，并确认知悉 **D13**（Gate 2 前须客户场景替换或书面背书）。  
3. 业务验收人已指定（可与业务 owner 同一人）。  
4. 隔离环境可行性结论（能/不能；不能则 WP0 只出缺口，**不得**进入 Gate 1）。  

**不满足 §2.3 = 不得启动 WP0。** 方案落盘本身不构成开工授权。

**书面获准标准件**（已落盘）：

| 产物 | 路径 |
|------|------|
| L1 批准条 | `reports/five-products/L1_AUTHORIZATION.md` |
| 决策/授权登记 | `reports/five-products/DECISIONS_AND_AUTHORIZATIONS.md` |
| §2.3 核对 | `reports/five-products/SECTION_2_3_CHECKLIST.md` |
| 场景 | `reports/five-products/SCENE.md` |
| 角色 | `reports/five-products/ROLES.md` |
| 日程 | `reports/five-products/SCHEDULE.md` |

确认方式见批准条（签署 / `L1-authorize` commit / 可归档确认）。**生效后**且上表勾齐 → 可启动 WP0。

五产品 owner 全名单：争取 **WP0 第一周内**补齐；未到位时按 §2.4 与 `ROLES.md` 临时覆盖。

过程产物目录：`reports/five-products/`（禁止堆回 `docs/research/`）。

### 2.4 WP0 临时责任人（owner 未到位时）

| 产品域 | 正式 R | owner 未到位时的临时 R | 规则 |
|--------|--------|-------------------------|------|
| aiPlat | aiPlat owner | 架构决策 owner 或指定平台工程师 | 须书面点名 |
| Pi | Pi owner | 架构决策 owner 或指定 Runtime 工程师 | 须书面点名 |
| 本体 | 本体 owner | 架构决策 owner | 若本切片标「未使用本体」，该行可只记「未启用/未知」，**不得**对本体能力下「已具备」结论 |
| FDE | FDE owner | 业务场景 owner 或指定 FDE 工程师 | 须书面点名 |
| 诊断 | 诊断 owner | 架构决策 owner 或指定诊断/观测工程师 | 须书面点名 |

- 临时 R 的产出与正式 owner 同等效力，正式 owner 到位后须复核签字。  
- **负责人（正式或临时）均未指定的产品域**：该域相关边记 **Blocker**（§3.6），不得用猜测填平或伪造成 Known Gap。

---

## 3. 首切片定义（已锁定 · 方案 A）

### 3.0 目标路径 ≠ 现状已通

§3.1 描述的是**目标切片路径**（Gate 1 后要验证的闭环），**不预设**仓库里已存在贯通的生产链路。

WP0 必须对每一条边确认：现有入口、真实 caller、行为证据等级，并按 §3.6 登记为 **As-Is / Known Gap / Blocker**。  
- 边存在且可定位 → **As-Is**。  
- 边缺失但设计与负责人齐全 → **Known Gap**（可进 Gate 1 工作项；不得标「已接线」）。  
- 安全/权威/授权未知或不可控，或无人负责 → **Blocker**（挡在 Gate 1 外）。  
- **禁止**为赶进度：跨库直写、绕过授权、或把新建接口登记为 As-Is。

### 3.1 主路径（目标 · 必经步骤）

```text
FDE：建场景 + 验收标准
  → aiPlat：发布版本化 Agent Bundle（含权限声明与审计）
  → Pi Thin：在目标/隔离环境安装并运行（低风险或只读工具）
  → 诊断：接入 Pi + aiPlat 证据，生成可追溯报告（含 unknown/stale）
  → FDE：按标准验收或开整改任务
  → 故障注入：控制面/证据断连、拒权、过期 → 不得伪报成功
```
### 3.2 本体（非必经）

| 项 | 规则 |
|----|------|
| 何时做 | 场景**明确依赖**语义查询/数据准备度评估时 |
| 如何做 | 只读查询；结果必须带 `ontology_version` / 来源 / 新鲜度 |
| 与诊断 | **不**要求首切片诊断自动接入本体事件 |
| 与 Gate 1 | 路径不依赖本体时，本体维度标「切片未使用」，**不阻塞** |
| 与验收 | 若本切片执行了本体步骤，FDE 证据链须引用该版本；否则验收不强制 Ontology 字段 |

### 3.3 范围清单

| 纳入 | 排除 |
|------|------|
| 1 客户或内部项目/场景 | 多业务域并行 |
| 1 Agent Bundle + 1 Pi 环境 | 高风险副作用工具默认集 |
| 诊断：Pi + aiPlat 事件、run/trace、bundle/runtime 版本关联 | 本体/FDE 诊断 adapter |
| FDE 对象强制：Engagement、Scenario、Requirement、DeliveryPlan、Evidence、Acceptance | 甘特/CRM/财务/全能工单 |
| ≥1 次失联/拒权/过期语义测试 | 自动跨平台修复 |
| 可回滚 Bundle **或** Runtime 版本 | 全仓搬目录 |

### 3.4 端到端验收（硬标准 · 仅 Gate 1 通过后的 WP3–WP4 适用）

**正确性**

1. 可从 FDE 需求定位到：Agent 资产版本 → Bundle → Pi 实例 → 诊断报告（及可选 Ontology 版本）。  
2. Pi 输出符合预定义结果契约。  
3. 诊断报告可回溯证据与规则/评测版本；缺证据为 `unknown`/`stale`，不得默认 `healthy`。  
4. FDE 接受/拒绝有书面证据。

**安全**

5. 目标服务端校验 tenant/actor/scope/资源。  
6. 无授权调用被拒；Pi 客户端 gate 不能绕过服务端拒绝。  
7. 控制面失联时高风险副作用 **fail-closed**（首切片尽量无高风险工具）。  
8. 日志/报告无 token、密钥明文。

**可重复**

9. 干净环境按手册从 Bundle 安装跑到验收可重做。  
10. 保存代码、配置、Bundle、Runtime、（若有）Ontology、诊断规则版本集合。  
11. 失败可归因到产品边界。

### 3.5 Pi Thin 与 aiPlat 的依赖边界（锁定）

整条首切片**发布与诊断**依赖 aiPlat（发 Bundle、出平台侧证据）。  
「Thin 无 aiPlat 完成声明闭环」**仅**指下列执行态：

| 阶段 | 是否依赖 aiPlat 在线 | 说明 |
|------|:--------------------:|------|
| FDE 建档 / 验收编排 | 按实现 | 不在 Thin 定义内 |
| aiPlat **发布** Bundle | **是** | 权威发布与审计在控制面 |
| Pi **安装/加载** 已签名 Bundle | 否（包已在本地） | 完整性校验用本地签名/哈希 |
| Pi **执行**声明内低风险/只读闭环 | **可离线** | 见下方离线策略；高风险副作用仍 fail-closed |
| 诊断关联 **aiPlat** 证据 | **是**（采集/查询时） | 断连则报告记缺口/`stale`，不编造 |
| 诊断关联 **Pi** 本地/已上报事件 | 视缓冲 | 未送达须标记证据缺口 |

**WP2 必须写明的离线策略字段**（写入 `reports/five-products/contracts/pi-thin-offline.md`）：

1. `offline_max_ttl`：自上次成功策略/Bundle 校验起的最长离线执行窗口。  
2. `allowed_ops_offline`：允许的工具/技能集合（首切片默认 ⊆ 只读/低风险）。  
3. `denied_ops_offline`：一律拒绝的副作用类。  
4. `bundle_expiry / policy_expiry`：过期后行为（停止执行 / 仅只读）。  
5. `revocation`：若曾在线拉取撤销列表，离线期满后必须重新校验；无撤销通道时默认缩短 TTL。  
6. `audit_buffer`：离线审计/事件本地缓冲上限与恢复上送失败时的报告语义。

### 3.6 阻塞项 · 已知缺口 · E3/E4 阶段归属（防 Gate 1 循环）

> 目的：允许「批准去建设并验收切片」，而**不要求**「切片已跑通才能获准去跑」。

#### 3.6.1 三类登记（WP0 表 B/F 必用）

| 类型 | 定义 | Gate 1 含义 |
|------|------|-------------|
| **阻塞项（Blocker）** | 安全边界、数据权威、授权方式仍**未知或不可控**；或没有可执行设计与负责人；或隔离环境「不能」 | **挡在 Gate 1 外**；须先澄清/缩场景/补负责人，不得带病开工 |
| **已知缺口（Known Gap）** | 当前尚无实现或未接线，但已书面定义：拟建接口/步骤、责任人（正式或临时 R）、范围、测试点、回滚；**不**把缺口写成「现状已接线」 | **可随 Gate 1 批准**进入 WP3–WP4，作为明确工作项；WP4 结束须关闭或归因 |
| **已具备（As-Is）** | 有入口 + caller + 证据等级；可复用 | 记入事实清单；可被切片调用 |

禁止：跨库直写「补洞」；把 Known Gap 标成 As-Is；把必须靠本次 WP4 才产生的 E3 当作 Gate 1 前置绿灯。

#### 3.6.2 E3 / E4 证据归属

| 证据 | Gate 1 **之前**（WP0–WP2）要求 | **切片完成时**（WP4，§3.4）要求 |
|------|-------------------------------|----------------------------------|
| 局部已有能力的 E1/E2（源码、单测） | 尽量登记；缺失则多为 Known Gap 或 Blocker（视安全） | — |
| **本切片端到端路径的 E3**（多服务集成行为） | **不要求已取得**。Gate 1 批准的是「去取得」 | **必须达到**（或失败归因且不降标） |
| **对外承诺用的 E4** | 不要求 | 若对外宣称该切片能力可用则必须达到；否则保持「非对外承诺」 |
| 安全/授权/租户校验的负向设计 | 须在 WP2/WP3 设计层可指认 | WP4 须跑通负向用例 |

**一句话**：Gate 1 审的是「能否安全、有责地开工建设与验收」；WP4 审的是「目标路径是否真的跑通」。二者不得颠倒。

#### 3.6.3 Known Gap 提交 Gate 1 的最低字段

每条 Known Gap 须含：`gap_id`、描述、拟建面（API/步骤）、owner、依赖、测试点、回滚、是否触及安全副作用（是则安全 reviewer 预签）。

Gate 1 审查时：字段齐全仍不够——若实质是安全边界、数据权威或授权「未知/不可控」，**改标 Blocker**，不得以 Known Gap 过门。

---

## 4. 总路线与时间盒

```text
WP0 盘点（≤10 工作日）
  → WP1 边界冻结（≤3 日，可与 WP0 尾重叠）
  → WP2 六契约最小版 + 兼容矩阵 + 失联语义（≤5 日）
  → Gate 1（切片开工门）
  → WP3 切片设计（≤5 日）
  → WP4 切片执行与证据包（≤10 日）
  → WP5 回顾与 backlog
  → Gate 2？ → 仅模块化暴露的边（M 波次）
  → Gate 3？ → 单产品独立部署（证据+成本）
```

| 阶段 | 时间盒 | 出口产物 |
|------|--------|----------|
| WP0 | ≤10 工作日 | 切片路径事实清单、依赖边、owner、身份流、差距、关闭实验表 |
| WP1 | ≤3 工作日 | 边界签字表（切片范围） |
| WP2 | ≤5 工作日 | **本切片启用的**契约最小草案 + 兼容矩阵填实行 + 失联/离线策略；非生产 API 全集 |
| Gate 1 | 1 次检查 | 通过/附条件/驳回（**单独决定**是否开 WP3–WP4） |
| WP3–WP4 | 有条件 | 仅 Gate 1 通过后；窗口紧，缺 caller/环境则暂停或缩切片，**不降验收** |
| WP5 | ≤3 工作日 | ADR 更新、GAPS backlog、Gate2 建议 |
| Gate 2–3 / M 波次 | 无承诺日期 | 框架就位；工期与拆分承诺须另批 |

**当前获准执行**：仅 WP0–WP2（在 L1 授权后）。WP3+ 日程表仅为预留，**不写入对外承诺日期**。

日历起止由架构 owner 在获准 L1 后写入 `reports/five-products/SCHEDULE.md`（只排到 WP2 / Gate 1）。

---

## 5. 工作包详解

### WP0 — 切片路径现状盘点

#### 目标

弄清主路径（§3.1）上：**实际入口、caller、数据权威、身份校验点、副作用点、版本字段、现有证据等级**。

#### 范围纪律

- **必盘**：§3.1 **目标路径**上的边——逐边找现状，不是默认已通（§3.0）。  
- **按需**：若场景启用本体，加盘查询入口与版本字段。  
- **禁止**：全仓目录考古、全量 CAPABILITIES 证据升级作为 WP0 完成条件。  
- **禁止**：跨库直写「补洞」、把 WP3 才计划新建的接口写成「现状已接线」。  
- 未使用产品维度写「切片未使用」。  
- 执行人：正式产品 owner，或 §2.4 临时 R。  

#### 建议调查锚点（按现状）

```bash
# FDE → knowledge/ontology 直连面
rg -n 'from core\.harness\.(knowledge|ontology)' aiPlat-core/core/apps/fde --glob '*.py'

# FDE API
rg -n '@router\.' aiPlat-platform/apps/fde/api --glob '*.py' | head -40

# Pi 与导出
ls packages/aiplat-pi-runtime
rg -n 'export_pi_bundle|aiplat-pi-runtime' scripts packages --glob '*.{py,ts,md,sh}' | head -40

# 控制面
rg -n 'require_auth|PolicyGate|_resolve_identity' aiPlat-platform --glob '*.py' | head -40
```

#### 必填表（文件：`reports/five-products/wp0-inventory.md`）

**A 能力入口**｜**B 依赖边**｜**C 数据 owner**｜**D 身份与副作用**｜**E 关闭实验**｜**F 差距分级**（安全/正确性/边界/运维）

证据等级：E0 文档 · E1 源码 · E2 单测 · E3 集成 · E4 干净部署 · E5 生产。

#### DoD

- [ ] 摘要首句写明：「§3.1 为目标路径；下列为 WP0 核实后的 As-Is / Known Gap / Blocker」  
- [ ] 主路径每条边已分类（§3.6.1）；Known Gap 含 §3.6.3 最低字段；Blocker 单列  
- [ ] **无**「因整路径尚无 E3 而一律阻塞 Gate 1」——端到端 E3 归属 WP4（§3.6.2）  
- [ ] 无跨库直写或临时旁路被登记为 As-Is  
- [ ] 切片数据唯一 owner；缓存单独标版本/新鲜度字段有无  
- [ ] Pi Thin 已实现 vs Enterprise 缺口表；并区分「执行离线」vs「发布/诊断依赖 aiPlat」  
- [ ] 诊断现状 vs MVP（Pi+aiPlat 证据+报告）差距表  
- [ ] 各产品域均有正式或临时 R 署名；无负责人的主路径边 → Blocker  
- [ ] As-Is 边带证据等级；声称 As-Is 但仅有 E0 → 降为 Known Gap 或 Blocker  
- [ ] 时间盒到期：未完成标后置；**不**虚构完备性或虚报 E3  

---

### WP1 — 边界冻结（切片范围）

#### 动作

1. 确认本切片使用的产品步骤（主路径全用；本体用/不用）。  
2. 冻结 Knowledge 三分（仅切片触及部分）：语义事实→本体；检索编排→aiPlat；跨产品证据索引→诊断。  
3. 冻结编排表述：**资产发布与治理**∈aiPlat；**厂外执行宿主**∈Pi；Harness=共享执行底座，经公开接口暴露，禁止把 FDE 业务写回 harness。  
4. 确认 D9（shared/identity 仅契约）。

#### 产物

`reports/five-products/wp1-boundary-signoff.md` + ADR-01 一页草稿。

#### DoD

- [ ] 无双重权威实体  
- [ ] 非目标贴在看板  
- [ ] 五产品 owner 名单齐（最迟本 WP 结束）  

---

### WP2 — 契约分类与「本切片启用集」

#### 适用规则（D4 · 纠正「六类全填才过门」）

| 规则 | 说明 |
|------|------|
| 六类是**分类全集** | Identity、Bundle、Runtime、Semantic、Evidence/Diagnosis、Delivery |
| Gate 1 只卡 **本切片启用集** | 实际路径用到的契约必须：最小字段、生产者/消费者、版本或草案号、错误/失联语义、owner |
| 未启用契约 | 矩阵行状态填 **`本切片未启用`**，owner 可空或填「n/a」；**不阻塞 Gate 1** |
| Semantic 特例 | 首切片默认未启用本体时：Semantic = `本切片未启用`；**一旦** WP1 决定启用本体，Semantic 升入启用集并强制测 |
| 交付物级别 | WP2 产出的是**可测的最小契约草案 + 矩阵**，不是六套已上线生产 API（D11） |

首切片默认启用集（本体关闭时）：Identity、Bundle、Runtime、Evidence/Diagnosis、Delivery。  
Semantic：默认 `本切片未启用`。

#### 启用契约的最小字段

**Identity / Policy**：`tenant_id, actor_id|service_id, scopes[], audience, request_id, trace_id, product_id, environment_id, authn_source, expires_at`  
验收：伪造身份失败；客户端不能放行服务端已拒操作。

**Agent Bundle**：`bundle_id, schema_version, source_asset_ids[], asset_versions[], runtime_compat_range, permission_claims[], model_requirements, build_info, integrity, rollback_hint`  
验收：坏包/不兼容包安装前拒绝；`permission_claims` 不能单独授权。

**Runtime Control**：`instance_id, deploy_version, config_version, health, heartbeat_at, event_types[], offline_until, command_authz`  
验收：符合失联表 + §3.5 离线策略文件。

**Semantic**（仅启用时）：`ontology_version, mapping_version, query_id, provenance[], freshness, permission_decision`  
验收：无版本/来源不得「验收通过」。

**Evidence / Diagnosis**：`event_schema_version, source_product, source_instance, environment, asset_versions{}, run_id, trace_id, severity, status, evidence_refs[], report_rule_version, generated_at`  
验收：可回溯；缺证据→`unknown`/`stale`。

**Delivery**：`engagement_id, scenario_id, requirement_ids[], refs{agent_bundle,runtime,ontology?,diagnosis_report}, acceptance_status, evidence_ids[], decided_by, decided_at`  
验收：FDE 不写对方权威库；只持稳定引用。

#### 兼容矩阵

| 对象 | 本切片状态 | 生产者 | 消费者 | 版本/草案 | 不兼容行为 | owner |
|------|------------|--------|--------|-----------|------------|--------|
| Identity | 启用 / 未启用 | | | | | |
| Bundle schema | 启用 | aiPlat | Pi | | 安装前拒绝 | |
| Runtime API | 启用 | Pi | 控制面 | | | |
| Ontology/Semantic | **默认未启用** | | | | | n/a |
| Evidence event | 启用 | Pi/aiPlat | 诊断 | | 忽略未知可选字段 | |
| Delivery | 启用 | FDE | adapters | | 状态幂等 | |

「启用」行：禁止空 owner、空版本/草案号。  
「本切片未启用」行：不阻塞 Gate 1。

#### 失联语义（锁定默认）+ Pi Thin 离线

| 操作 | 默认 |
|------|------|
| Pi 读仍有效已签名 Bundle 并在 TTL 内执行允许集 | 可有限运行，记 offline（§3.5） |
| Pi 高风险副作用 / 超出 `allowed_ops_offline` | fail-closed |
| 本体只读（若启用） | 带版本新鲜缓存或 unavailable |
| FDE 读已有项目 | 可展示并标 stale |
| 诊断拉 aiPlat 证据中断 | 记缺口，不编造健康 |

须同时交付 `reports/five-products/contracts/pi-thin-offline.md`（§3.5 六字段）。

#### 产物落点

`reports/five-products/contracts/`（启用集 schema 草案 + 矩阵 + 离线策略）。稳定后再迁文档树。

#### DoD

- [ ] 矩阵每行有状态：`启用` 或 `本切片未启用`  
- [ ] **所有启用行**有生产者/消费者/版本或草案号/错误语义/owner  
- [ ] Semantic 在未用本体时为 `本切片未启用`（不阻塞）  
- [ ] `pi-thin-offline.md` 六字段齐全并签字  
- [ ] 失联表签字  
- [ ] ≥3 条负向用例（启用集内）：伪造身份、坏 Bundle、过期/缺失证据  
- [ ] 明确声明：本 WP **未**声称交付六套生产级稳定 API  

---

### Gate 1 — 切片开工门（单独批准 WP3–WP4）

**审什么**：能否安全、有责地**开工建设并验收**目标路径。  
**不审什么**：整条路径是否**已经**具备端到端 E3（那是 WP4 的事，§3.6.2）。

**全部满足**才进入 WP3；本门**不是** L1 自动延续：

- [ ] 场景、验收人、失败条件明确  
- [ ] Pi 形态=Thin 或 Enterprise 子集清单；`pi-thin-offline.md` 已定  
- [ ] 控制面路径明确（aiPlat 默认或具名外部 IAM）  
- [ ] WP0 **无未关闭的 Blocker**（§3.6.1）；安全/权威/授权/无负责人等不得带病过门  
- [ ] 所有 Known Gap 已附 §3.6.3 字段，并纳入 WP3–WP4 工作项清单  
- [ ] **Known Gap 抽查**：每条确有可执行设计、责任人、测试点、回滚；**无一**把安全边界 / 数据权威 / 授权方式的「仍未知或不可控」包装成普通缺口（此类一律升为 Blocker）  
- [ ] **未**将「路径尚无端到端 E3」误列为 Blocker  
- [ ] WP2 **启用集**契约可用于本路径；未启用行已标记  
- [ ] 隔离环境、密钥、脱敏方案就绪（WP0 已确认「能」）  
- [ ] Bundle 发布与诊断证据：**As-Is 可指认**，或 **Known Gap 设计可执行**（否则缩场景/驳回）  
- [ ] 回滚：Bundle 或 Runtime 可回滚（设计层）  
- [ ] 安全 reviewer：副作用范围 + 触及安全的 Known Gap 预签  
- [ ] 架构 × 业务联合签署 **「批准进入 WP3–WP4」**（联签独立于工作包主 A）  

未过 Gate 1：**禁止** WP3–WP4、**禁止**改生产默认路径、禁止对外宣称五产品已产品化。  
仅有 Blocker、或 Known Gap 无设计/无人负责、或安全/权威/授权被伪装成 Known Gap：**暂停或缩切片**。  
**禁止**为过 Gate 1 而降低 §3.4 / WP4 的 E3–E4 完成标准。  
**禁止**将「已获准 L1」解释为「切片已获准开跑」或「全面改造已获批」。

---

### WP3 — 切片设计

产物：序列图、环境清单、数据夹具、测试计划（含正确性/安全/失联）、回滚步骤、运维手册草稿。  
文件：`reports/five-products/slice-<id>/DESIGN.md`

#### DoD

- [ ] 每步有责任产品与证据文件名约定  
- [ ] 故障注入用例 ≥3  
- [ ] 回滚步骤可在 30 分钟内演练（设计层可执行）  

---

### WP4 — 切片执行

#### 建议日程

| 日 | 内容 |
|----|------|
| D1 | 环境；Bundle 导出/安装 smoke |
| D2 | FDE 建档与验收标准 |
| D3 | （可选）本体只读查询 |
| D4 | aiPlat 发布与审计核对 |
| D5–D6 | Pi 主路径；采集 run/trace |
| D7 | 诊断报告与关联 |
| D8 | FDE 验收/整改 |
| D9 | 故障注入三连 |
| D10 | 证据包归档；缺陷归因 |

#### 证据包

```text
reports/five-products/slice-<id>/
  VERSIONS.md
  RUNLOG/                 # 脱敏
  DIAGNOSIS_REPORT.md
  ACCEPTANCE.md
  FAILURE_INJECTION.md
  GAPS.md                 # → 模块化 backlog
```

#### DoD

- [ ] §3.4 验收表全部通过，或失败已归因到产品并记入 GAPS  
- [ ] 测试/验收 owner 签署  
- [ ] GAPS 每条含严重度与建议（契约/facade/后置）  

---

### WP5 — 回顾

1. 更新 ADR-01～03（至少）；其余按需。  
2. 仅基于 GAPS 生成模块化 backlog（禁「因目录好看而搬迁」）。  
3. 给出 Gate 2 建议：扩大 / 维持 / 暂停；若场景为「非客户验收」，须在建议中单列 **D13 客户背书缺口**。  

---

## 6. Gate 2 — 扩大产品化门禁与其后模块化

### 6.0 Gate 2 通过条件（在 WP4/WP5 之后单独批准）

**全部满足**方可批准「按 GAPS 扩大模块化 / 产品化」：

- [ ] WP4 端到端行为与安全/失败模式通过（或失败已归因且不依赖降标）  
- [ ] 失败状态可观察；数据与权限边界成立  
- [ ] 五产品 owner（或已复核的临时 R 转正）到位  
- [ ] **D13**：场景为真实客户路径，**或**已取得符合 §6.0.1 的书面客户背书 / 客户场景替换；仅有「非客户验收」→ **不得**过 Gate 2  
- [ ] 架构 × 业务联合签署「批准进入 Gate 2 模块化」  

Gate 2 **不**批准：无证据的全仓搬迁、诊断全功能、拆微服务（仍属 Gate 3）。  
取消 D13 须另立 ADR，纪要默示不算数。

#### 6.0.1 书面客户背书最低内容（D13）

附件须可核验，至少包含：

1. 客户组织名称  
2. 客户联系人姓名与角色（有权同意扩大依据者）  
3. 对应场景标识/简述（与切片或后续扩大场景可追溯）  
4. 验收目标或成功标准摘要  
5. 明确同意：该场景/结论可作为 **Gate 2 扩大产品化** 的业务依据（范围边界一句话）  
6. 日期与签字（或等价书面确认）  

缺任一项 = 背书不成立。内部场景技术通过 ≠ 客户背书。

**原件留存**：须归档背书**原始证据**（邮件/函件/会议纪要签字页/等价原件路径），记入 `reports/five-products/` 或评审附件索引。仅有纪要结论句「客户已同意」、无原件可追溯 → **背书不成立**。

### 6.1 模块化范围

只做 Gate 2 批准且 GAPS 列出的边。

### 6.2 手法优先级

1. 公开 API/facade + 改 caller  
2. 版本化 DTO/事件  
3. 依赖守卫（防回潮）  
4. DB 直连 → API（双读窗口）  
5. 目录搬迁（最后；单子域 + 回归 + 回滚）  

### 6.3 单波次 DoD

- [ ] 范围=批准的边  
- [ ] 契约或集成测试覆盖  
- [ ] 无新的跨域私有 import  
- [ ] 回滚说明  
- [ ] 能力声明变更不虚抬证据等级  

### 6.4 预设波次（示例，以 GAPS 裁剪）

| 波次 | 主题 | 现况锚点 |
|------|------|----------|
| M1 | FDE 去直连 knowledge/ontology | `core/apps/fde/service/*` |
| M2 | Bundle 契约硬化 | `export_pi_bundle` ↔ `aiplat-pi-runtime` |
| M3 | 诊断事件 schema 落地 | Pi/aiPlat → 诊断 |
| M4 | Knowledge 按 owner 切面 | `harness/knowledge` |
| M5 | 关闭实验隔离复核 | 厂内 Pi 路径 |

---

## 7. 各产品中长期落地规格（Gate 2+ 按批准启动）

### 7.1 aiPlat

- 控制面稳定 API；禁私有身份模块被跨产品 import  
- 资产生命周期与 Bundle 字段对齐  
- 编排=治理/发布；执行不在厂外重复造控制面  
- FDE/诊断业务逻辑迁出 harness  

### 7.2 Pi

| 形态 | 落地要求 |
|------|----------|
| Thin | **执行态**可在 aiPlat 断连时按 §3.5 离线策略跑已签名 Bundle 的声明闭环；**发布与诊断仍依赖 aiPlat**；E4 干净环境验证执行态 |
| Enterprise | 安装/升级/回滚/健康/事件/离线语义；与 Thin 兼容矩阵 |
| +aiPlat | 服务端最终授权；native gate 仅防旁路 |

参考：[pi-thin-runtime.md](./pi-thin-runtime.md)。措辞「无 aiPlat」禁止解读为「整条切片不需要 aiPlat」。

### 7.3 本体

- Model/Mapping/Query API：版本、来源、新鲜度  
- RAG/向量=派生视图，非权威  
- 消除跨产品 DB 直连  

### 7.4 FDE

- 强制六对象状态机；其余对象按流程需要引入  
- Adapter：aiPlat/Pi/本体/诊断/客户系统  
- 客户隔离与串租负向测试  

### 7.5 诊断

- MVP=证据接入+关联+报告+unknown/stale（本落地方案首切片已定义）  
- Evaluation/Testing=二期单独批准  
- Remediation=只建议/建任务；执行走目标产品授权 API  
- Management=入口，非唯一业务模型  

---

## 8. 数据 owner（落地权威表）

| 数据 | 权威 owner | 他方允许 |
|------|------------|----------|
| Tenant/Actor/平台策略 | aiPlat 或配置的外部 IAM | 有期限授权上下文 |
| Agent/Skill/Workflow/Tool 版本 | aiPlat | Pi 快照、诊断/FDE 引用 |
| Runtime/Deployment/Instance | Pi | 控制面投影、诊断索引 |
| Ontology/Mapping/Semantic | 本体 | 带版本新鲜度的缓存 |
| 项目/需求/验收 | FDE | 关联 ID |
| Eval/Test/Diagnostic Report | 诊断 | 链接与摘要 |
| 源运行日志/业务事实 | 各源产品 | 诊断受控引用 |

---

## 9. 目标逻辑结构（迁移地图 · 非立即搬迁）

```text
products/
  aiplat/{control_plane,agent_lifecycle,governance,api}/
  pi/{runtime/thin,runtime/enterprise,adapters,packaging,docs}/
  ontology/{model,ingestion,mapping,semantic_store,query,governance,api}/
  fde/{projects,discovery,delivery,acceptance,integrations,api}/
  diagnostics/{evaluation,testing,telemetry,correlation,diagnosis,remediation,adapters}/
shared/{contracts,sdk,identity,observability,security,connectors}/
```

| 现有区域 | 归属方向 |
|----------|----------|
| `harness/ontology_engine/` | 本体核心，经 API 隔离 |
| `harness/knowledge/` | 三分：本体事实 / aiPlat 检索编排 / 诊断证据 |
| `core/apps/fde` + `platform/apps/fde` | FDE 产品域 |
| `packages/aiplat-pi-runtime/` | Pi Thin |
| `scripts/export_pi_bundle.py` | aiPlat 工厂打包 |
| 各层 diagnostics + Management | 事实提供器 vs 诊断分析 |

每次目录移动：行为回归 + import 兼容 + 回滚方案。

---

## 10. Gate 3 — 独立部署门槛

须至少一项真实驱动 **且** 完成成本/运维评估：

- 客户隔离/数据驻留/独立密钥  
- 独立扩缩容负载  
- 独立 SLA 与发布节奏 + 责任团队  
- ≥2 个真实消费者证明多平台复用  
- 共享部署已造成可量化故障或升级冲突  

另需：迁移回滚、API 兼容、故障隔离、授权审计、SLO、备份恢复。无 owner/on-call 不拆。

---

## 11. ADR 落地顺序

| ADR | 最晚完成时机 |
|-----|----------------|
| ADR-01 边界与非目标 | WP1 |
| ADR-02 控制面与外部 IAM | WP2 / Gate1 前 |
| ADR-03 数据 owner | WP1–WP2 |
| ADR-04 Pi 形态与 Bundle 兼容 | Gate1 前 |
| ADR-05 本体 vs Knowledge/RAG | 启用本体步骤或 M4 前 |
| ADR-06 FDE 对象与适配 | WP3 |
| ADR-07 诊断证据与修复权 | WP2–WP4 |
| ADR-08 部署拆分门槛 | Gate3 前 |
| ADR-09 关闭实验与能力声明 | WP0/WP5 |

每份含：上下文、决策、备选、影响、迁移、回滚、重评触发。

---

## 12. 测试与现有门禁关系

| 机制 | 角色 |
|------|------|
| architecture_guard / constitution | 静态必要非充分 |
| CAPABILITIES / capability truth | 声明层；单独不够 E4 |
| defect-gate | 合并纪律；不替代切片验收 |
| 契约测试 + 切片 E2E | 本方案行为真源 |

Gate 2+ 建议守卫：禁止 `apps/fde` 直 import `harness.knowledge` 内部模块（仅 facade）。

---

## 13. 风险与控制

| 风险 | 控制 |
|------|------|
| 范围膨胀 | 只准 §3 主路径；变更 ADR |
| 隐性单体 | 契约测试 + 依赖守卫 |
| Pi 过度承诺 | Thin/子集清单 + 证据等级 |
| 双权威 | WP1 冻结；缓存打标 |
| 权限旁路 | 服务端负向测试 |
| 伪健康 | unknown/stale 硬验收 |
| Owner 空缺 | §2.3 最低启动条件 |
| 业务挤占 | 正式暂停；重启重过 Gate1 |

---

## 14. 指标（先基线后目标）

| 产品 | 首轮指标 |
|------|----------|
| aiPlat | 发布成功率、策略正确率、审计完整率 |
| Pi | 安装成功率、任务成功率、断连降级正确率 |
| 本体 | 查询可追溯率、映射覆盖、新鲜度 |
| FDE | 场景→验收周期、证据完整率、返工率 |
| 诊断 | 关联成功率、报告可复现率、unknown/stale 识别率 |

须定义分母与采集源；无历史时只建基线。

---

## 15. 成功定义

| 阶段 | 成功 | 当前是否在批准范围内 |
|------|------|:--------------------:|
| L1 准备（WP0–WP2） | As-Is/Known Gap/Blocker 分类清楚；启用集契约可测；可提交 Gate1 | **是（书面获准 L1 后）** |
| Gate 1 | 无 Blocker；Known Gap 可执行；**不要求**路径已有端到端 E3 | 另批；≠ L1 |
| 切片（WP3–WP4） | §3.4 全过；路径 E3（及对外时 E4）；失败可归因 | Gate1 前否 |
| Gate 2 扩大 | §6.0 + D13 背书（§6.0.1） | 另批 |
| Gate 3 拆分 | 门槛+成本；架构×业务联签 | 另批；无日期承诺 |

---

## 16. 启动清单（满足 §2.3 并获准进入 L1 之后）

> 下列步骤**仅在**书面「获准进入 L1」之后执行；本文落盘 ≠ 自动开工。

1. 确认架构 owner、业务 owner、验收人、§2.4 临时 R（如需要）已书面点名  
2. 场景写入 `reports/five-products/SCENE.md`  
3. 开目录 `reports/five-products/`  
4. 启动 **WP0**（表 A–F + §3.0 纪律），时间盒 ≤10 工作日  
5. WP0 尾并行 **WP1**；紧接 **WP2**（启用集契约 + `pi-thin-offline.md`，非六套生产 API）  
6. 提交 **Gate 1**；**仅通过后**才排 WP3–WP4  
7. Gate 2 须另批且满足 **D13**；Gate 3 另批；**均不预估完成日**  

---

## 17. 文档集关系（防再漂移）

| 文件 | 地位 |
|------|------|
| **本文 landing-plan** | **落地方案唯一执行真源** |
| target-architecture | 目标边界与长期原则（路径/门禁以本文为准） |
| execution-plan | 历史首切片稿；与本文冲突时作废冲突句 |
| decision-brief / review-* | 会务材料；不指导日常执行 |

---

## 18. 变更记录

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0 | 2026-10-23 | 首版：路径 A、六契约、门禁命名、WP/Gate/模块化 |
| 1.1 | 2026-10-23 | 有条件评审：L1/WP0–WP2；Semantic 启用集；Pi Thin 离线；目标≠现状；临时 R；Gate1 另批切片 |
| 1.2 | 2026-10-23 | D13 Gate2 客户背书；RACI 主 A + A′；§6.0 Gate2 检查单 |
| 1.3 | 2026-10-23 | §3.6 阻塞/已知缺口/E3 阶段归属；Gate3 业务 A′；D13 最低字段+原件留存；Gate1 Known Gap 抽查（防伪装 Blocker）；定为有条件 L1 执行基线；卫星文档同步 |

---

**一句话**：书面获准 L1 后只做 WP0–WP2；Gate 1 批准「去建设并验收」（Known Gap 可带，Blocker 不可），端到端 E3 在 WP4 交付且不降标；Gate 2 须客户背书。  
