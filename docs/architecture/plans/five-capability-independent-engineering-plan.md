# 五能力独立化工程方案（V2.2 · 模块自治 + 三类部署）

> **文档类型**：工程规划 / Design Plan  
> **状态**：工程基线 · **V2.2 @ 2026-11-01**（G0 通过；D1/D2 冻结；**显式解冻** D3 本地验收 + 跨能力 E2E；预发仍 defer）  
> **基线**：`main` @ `b46e286`（week-34）→ G0 锚点 **19** 提交（见 [`G0_CLOSEOUT.md`](../../../reports/five-products/G0_CLOSEOUT.md)）；其后继续工程推进；CI 242 行、nightly unit 硬门  
> **V2.1 打包共用面**：`templates/module/PACKAGING_BASE.md` · `scripts/check_five_products_packaging_surface.sh` · `scripts/lib/aiplat_security_baseline.py`  
> **V2.2**：`ops_d3_local_acceptance_all.sh` · `ops_five_products_e2e_local.sh`（local only；硬门仍 false；不 authorize） · [`ENGINEERING_UNFREEZE_D3_E2E.md`](../../../reports/five-products/ops/ENGINEERING_UNFREEZE_D3_E2E.md)  

> **范围**：仅工程侧（架构、代码、测试、打包、文档、验证、模板化）；不含销售、定价、合同、SLA 运营、24×7  
> **批准边界**：本文**不改变** ADR-09 / ADR-08 / Gate3 的已批范围。Pi 之外的进程/DB 拆分，逐产品另走 ADR。  
> **关联**：  
> - [五产品落地方案](./ai-platform-five-products-landing-plan.md)（E0–E5 证据级定义）  
> - [Pi Thin Runtime](./pi-thin-runtime.md)  
> - [`reports/five-products/LANDING_CLOSEOUT.md`](../../../reports/five-products/LANDING_CLOSEOUT.md)  
> - [`reports/five-products/ADR09_DEFER_FULL_SPLIT_E4_PROD.md`](../../../reports/five-products/ADR09_DEFER_FULL_SPLIT_E4_PROD.md)  
> **本文不是**：新 ADR；不是“五产品已全拆”的批准；不是对外产品化承诺。

---

## 0. 决策摘要

| # | 决策 | 状态 |
|---|---|---|
| 1 | 五个**能力边界**保留：Pi / FDE / 本体 / 评测 / aiPlat | 锁定 |
| 2 | 不做五个平级产品/五个进程；做 **5 个自治模块 + 3 类部署位置** | 锁定 |
| 3 | 独立维护优先：代码/API/数据/测试/构建/版本自治；运行时按需拆分 | 锁定 |
| 4 | 顺序：Pi → FDE → 评测 → 本体 → aiPlat 企业运行时 | 锁定 |
| 5 | Pi 真独立；FDE 现场可部署；本体/评测先独立服务/模块；aiPlat 是中心宿主 | 锁定 |
| 6 | monorepo + 每模块独立包/构建/版本；暂不拆仓 | 锁定 |
| 7 | 生产标准：Postgres + S3；SQLite 仅本地/测试；D1 前允许双轨 | 锁定 |
| 8 | 身份：standalone + OIDC 联邦；唯一权威 | 锁定 |
| 9 | 级别命名：**A1–A3（自治）+ D1–D3（交付）**，不复用 E0–E5 | 锁定 |
| 10 | 目标：20 个月五能力 A2/D2，Pi/FDE/评测 D3；全五进程拆分是 stretch | 锁定 |

---

## 1. 目标、非目标与定义

### 1.1 目标

- 五个能力**可独立维护**：改一个不牵动其他；各自可深做。
- 三种部署形态可落地：**中心 / 现场 / 边缘**。
- 每个能力有清晰契约、数据归属、测试、文档、版本。
- 20 个月内：五能力 **A2 + D2**；Pi / FDE / 评测 **D3**（验收就绪，不等于客户签字）。

### 1.2 非目标

- 不做五个独立销售品 / P&L。
- 不做五个微服务同时上线。
- 不做销售、定价、合同、SLA 运营、24×7。
- 不做“零耦合”；目标只是“契约耦合”。
- 不在 G0 未绿时加产品功能。

### 1.3 级别定义

**自治级别**

| 级别 | 含义 |
|---|---|
| **A1** | 代码/API/schema/测试自治：独立目录、公共 API、自有数据、独立测试；禁止跨模块 internal import |
| **A2** | 构建/版本自治：独立 build、制品、版本、CHANGELOG；可单独 CI |
| **A3** | 部署自治：独立进程/DB/升级/回滚；**需 ADR** |

**交付级别**

| 级别 | 含义 |
|---|---|
| **D1** | 可部署：干净环境安装/升级/回滚/备份；不依赖其他模块内部 |
| **D2** | 可交付：文档、契约、安全包草稿、兼容矩阵、性能基线 |
| **D3** | 验收就绪：UAT harness、证据包、验收标准、dry run（非客户签字） |

> 与仓库 E0–E5 的关系：本文 A/D 级**不是**证据等级；E0–E5 仍按落地方案 §3.6 使用。

### 1.4 部署形态

```text
中心 Central：aiPlat + Ontology + Evaluation（默认）
现场 Field：FDE（本地优先；可选本地只读 Ontology/Eval 缓存）
边缘 Edge：Pi（POC / 离线）
```

**默认 3 个部署单元，不是 5 个。**

---

## 2. 现状基线（week-34）

### 2.1 已核实

- CI 从 1,011 行降到 **242 行**；`CORE_TARGETS` 单数组；PR 执行 `core/tests/unit` 全量。
- nightly：collect 硬门 + **unit 硬门**（无 `continue-on-error`）+ 其余 informational。
- 21 条 `~/.aiplat` 红已在 week-34 修（commit 声称；**P0 需只读复核**）。
- 五能力目前仍共进程、共享 core / identity / DB；Pi 是独立包；FDE/本体/评测是平台/内核的一部分。

### 2.2 P0 必须复核（不得当既成事实）

- **P0-3′（正式例外，2026-11-01）**：不以「字面 chmod-555 / 只读 HOME」为硬条件；判据改为 **假 HOME 可写 + hermetic `AIPLAT_HOME`** 下 `pytest core/tests` collect 0 error，`core/tests/unit` 绿（与 conftest 同路径）。字面只读 HOME 下 git 红 = 已知例外，**非**逃逸。证据见 [`G0_REPORT.md`](../../../reports/five-products/G0_REPORT.md)。
- Tier A 逃逸是否为 0（`paths.py` SSOT fallback 除外）。
- CI 242 行 job / nightly unit 硬门是否真绿（**defect-gate receipt ≠ CI**；须有完整 CI run 证据）。

### 2.3 主要耦合点

- `core/harness` 约 48 万行；跨模块 import、全局单例、共享 SQLite、`~/.aiplat` 逃逸。
- FDE 依赖 platform；本体依赖 DomainRouter；评测仅切片 MVP；aiPlat 单进程 / SQLite。
- 无模块 charter、无契约测试、无每模块构建。

---

## 3. 目标架构

### 3.1 五个能力边界

| 能力 | 职责 | 不负责 |
|---|---|---|
| **Pi Runtime** | 边缘/POC 执行；加载 Artifact Bundle；本地模型 | 企业治理、多租户 |
| **FDE Workbench** | 客户现场交付/实施/证据/验收 | 自建 Runtime/本体/评测引擎 |
| **Ontology Service** | 数字资产盘点、图谱、LLM Wiki、查询 | Agent 生命周期、通用 Runtime |
| **Evaluation Service** | 评测协议、沙箱、轨迹、指标、报告 | 源系统运行事实 |
| **aiPlat Platform** | Agent/Skill/Workflow 工厂；企业运行时；身份/租户/治理 | 本体权威、FDE 项目事实 |

### 3.2 共享内核（只放横向）

- 契约模型：Artifact Bundle / Evidence / Eval Protocol / Ontology API。
- Identity/Tenant 客户端（OIDC、tenant claims）。
- Telemetry（OTel）、配置规范、测试工具。

**不放**：业务规则、领域数据、内部实现、全局单例。

### 3.3 数据归属

| 数据 | 归属 |
|---|---|
| 租户/用户/策略/Artifact/Run | aiPlat |
| 项目/需求/实施/验收证据 | FDE |
| 实体/关系/资产/Wiki | Ontology |
| 评测任务/轨迹/分数/报告 | Evaluation |
| 本地运行态/配置/日志 | Pi |

**禁止跨模块读表；只走 API / 事件。**

### 3.4 契约

- Artifact Bundle：manifest + AGENT.md/SKILL.md + skills/handler + 版本/签名。
- Evidence：Pi/FDE 证据事件 schema；供 Evaluation/aiPlat 消费。
- Eval Protocol：任务、轨迹、指标、报告、判定。
- Ontology API：entity/relation/graph/wiki/asset。
- Identity：OIDC + tenant claims + service token。

### 3.5 依赖规则

- 只允许依赖共享内核；禁止模块间 internal import。
- 依赖图必须无环；由 architecture guard 强制。
- 模块可禁用；宿主降级而非崩溃。

---

## 4. 五个能力专项

### 4.1 Pi（边缘 / POC）

| 项 | 内容 |
|---|---|
| 范围 | 加载 Bundle；本地模型；离线执行；POC 模板；企业回连可选 |
| 接口 | Bundle、本地配置、事件/证据输出 |
| 数据 | 本地目录；默认不上传 |
| 目标 | A3 / D3；独立包/容器；更新/回滚 |
| 平台 | Linux/macOS 先，Windows 后 |
| 依赖 | 无中心依赖 |
| 风险 | 跨平台打包、SDK 版本、本地数据安全 |

### 4.2 FDE（现场）

| 项 | 内容 |
|---|---|
| 范围 | 项目/需求/实施/任务/证据/验收；本地优先；Bundle 导入；证据导出；可选同步 |
| 接口 | Bundle、Evidence、Identity（可选） |
| 数据 | 现场本地 DB；验收证据可导出 |
| 目标 | A2 + 现场 D1；逐步 D2/D3 |
| 依赖 | 不依赖 aiPlat 进程；只依赖契约 |
| 风险 | 离线/同步/多用户/升级；现场数据合规 |

### 4.3 评测（独立服务）

| 项 | 内容 |
|---|---|
| 范围 | 评测协议、沙箱、轨迹、指标、报告；先评 Agent/Skill/Workflow，再扩 HTTP/CLI 程序 |
| 接口 | Eval Protocol、Evidence、Report |
| 数据 | 评测任务/轨迹/分数/报告；保留期 |
| 目标 | A2/A3；D2/D3 |
| 依赖 | 可读 Bundle/Evidence；不依赖 aiPlat 内部 |
| 风险 | 范围蔓延、沙箱安全、指标可信度 |
| 首版边界 | **不承诺“所有程序”**；先 aiPlat 产物，再外部程序 |

### 4.4 本体（独立知识服务）

| 项 | 内容 |
|---|---|
| 范围 | 资产连接器（文档/库/代码/Wiki）、实体/关系抽取、图谱、LLM Wiki、权限；首版只读盘点 |
| 接口 | Ontology API、Asset schema |
| 数据 | 自有图/索引/资产元数据 |
| 目标 | A2/A3；可中心/可现场；D2 |
| 依赖 | 不依赖 FDE/评测内部 |
| 风险 | 抽取难、连接器多、权限/合规 |
| 首版边界 | **不承诺“所有资产类型”**；先文档 + 只读 |

### 4.5 aiPlat（中心宿主）

| 项 | 内容 |
|---|---|
| 范围 | Agent/Skill/Workflow 工厂；企业运行时（多租户、配额、审计、治理）；身份/租户 |
| 接口 | Bundle、Identity、Tenant、Policy |
| 数据 | 租户/用户/策略/Artifact/Run |
| 目标 | A2 + D1/D2；PG/HA/多租户需 ADR |
| 依赖 | 可托管 Ontology/Evaluation，但不依赖其内部 |
| 风险 | SQLite→PG、HA、多租户、体量 |

---

## 5. 模块治理（保证“单独维护”）

每个能力必须有：

1. `MODULE.md` charter：范围、非目标、API、数据、依赖、SLO、owner。
2. `module.yaml`：版本、构建入口、测试入口、契约、迁移。
3. `CODEOWNERS`。
4. 公共 API 目录；内部实现禁止跨模块 import。
5. 自有 schema + 迁移；禁止跨模块表。
6. 契约测试（API/事件）；N-1 兼容。
7. 独立 build/test 命令；CI 可单模块跑。
8. 独立 CHANGELOG / 版本 / 弃用策略。
9. 可禁用：模块关闭，宿主降级。

**依赖规则**：只允许依赖共享内核；禁止模块间 internal import；依赖图无环。

---

## 6. 工作分解与估算

| ID | 工作包 | 交付 | 工程周 |
|---|---|---|---:|
| G0 | 质量基线复核 + 残留逃逸清扫 + SBOM/签名 + 契约脚手架 + 模块模板 | G0 报告 | 4–6 |
| M1 | 五模块 charter/API/schema/契约/CODEOWNERS/依赖守卫 | A1 | 6–8 |
| M2 | 每模块独立 build/test/版本/CI | A2 | 4–6 |
| P1 | Pi 打包/更新/回滚/文档/UAT | A3/D3 | 8–10 |
| P2 | FDE 现场包/本地 DB/证据/验收 | A2/D2 | 12–16 |
| P3 | 评测协议/沙箱/适配器/报告 | A2/D2 | 12–16 |
| P4 | 本体连接器/图谱/Wiki/只读盘点 | A2/D2 | 16–20 |
| P5 | aiPlat PG/HA/多租户/治理 | A2/D2 | 20–26 |
| T1 | `templates/module/` + 复制到第二、第三模块 | 模板 | 4–6 |

**合计 86–114 工程周**；加 30% 缓冲约 **110–145 周**；按每周 1–2 个可合并 PR，日历 **20–24 个月**。

---

## 7. 路线图与 Gate

| 阶段 | 时间 | 目标 | Gate |
|---|---|---|---|
| P0 | M0–M1 | G0 复核、模块 charter、契约、模板 | G0 |
| P1 | M1–M4 | Pi A3/D1；Bundle 契约 | G-Pi |
| P2 | M4–M7 | FDE 现场 D1；评测协议 | G-FDE |
| P3 | M7–M10 | 评测 D2；本体 A1 | G-Eval |
| P4 | M10–M14 | 本体 D2；aiPlat PG/HA D1 | G-Onto |
| P5 | M14–M18 | aiPlat D2；五模块 A2 | G-A2 |
| P6 | M18–M20 | Pi/FDE/评测 D3 dry run；五能力 D2 | G-D2 |
| Stretch | M20–M30 | 本体/评测/FDE 进程拆分（逐产品 ADR） | G-A3 |

---

## 8. ADR 阶梯

| 事项 | 可否现在做 | 依据 |
|---|---|---|
| P0：质量 / 模板 / 契约 | ✅ | 工程内部 |
| Pi → A3/D1 | ✅ | Gate3 / ADR-08 / Pi BOUNDARY；若加安装器/更新通道，先确认是否需 ADR-08 修订 |
| 诊断 / FDE / 本体 / 评测的 **A1/A2** | ✅ | 模块/构建自治，不拆进程 |
| FDE 现场部署 | ❌ 需 ADR | 现场/离线边界超出既有 FDE BOUNDARY |
| 本体独立服务 | ❌ 需 ADR | ADR-03 data owner + 进程/DB |
| 评测独立服务 | ❌ 需 ADR | 新服务边界 |
| aiPlat PG/HA/多租户 | ❌ 需 ADR | 控制面产品化 |
| 五个进程全拆 | ❌ 逐产品 ADR | ADR-09 只批 Pi Thin |

**未批前只到 A2 / D1c**：此处 **D1c = `delivery_mode: cohost`**（契约/healthz 独立，进程仍共宿中心；≠ 独立部署）。旧「D0」叙事作废；勿与「旧 D1c 天花板」混读。见 `capabilities.manifest.yaml` `delivery_alias_cohost: D1c`。

---

## 9. 质量、测试、发布

### 9.1 G0 通过条件

1. **P0-3′**：假 HOME 可写 + hermetic `AIPLAT_HOME` 下 `pytest core/tests` collect 0 error，`core/tests/unit` 绿。字面只读 HOME **不是**硬门（正式例外；见 G0 报告）。
2. PR CI 242 行 job 绿；nightly unit 硬门绿（须有可引用的 Actions run；receipt 不能替代）。
3. 生产代码中 Tier A `~/.aiplat` / `expanduser` 逃逸扫描为 0。
4. 干净环境可复现构建 + SBOM + 签名。
5. 契约测试脚手架可跑（至少 1 个样例）。
6. 每模块 Chart/manifest 骨架存在。
7. flake 隔离策略落地（owner + 过期）。
8. G0 报告一页，含命令与输出；若有正式例外须在报告与本计划同步声明。

### 9.2 测试

- unit + contract + integration + 每部署形态 e2e + 升级/回滚 + 备份恢复 + 性能基线 + 安全扫描。
- PR < 15 分钟；nightly 全量；release gate。
- flake 隔离区 + owner + 过期；无 ticket 不得 skip/xfail。

### 9.3 发布

- semver；签名镜像；SBOM；air-gap；CHANGELOG；N-1 兼容。
- 每模块独立版本；产品/模块兼容矩阵。

---

## 10. 文档与模板

每模块固定文档：README、install、upgrade、admin、API、security、troubleshooting、backup/restore、compatibility、CHANGELOG、UAT。

`templates/module/` 含：charter、`module.yaml`、Dockerfile、Chart、CI、contract tests、docs 骨架、runbook、UAT；**V2.1** 另含 `PACKAGING_BASE.md`、D1/D2 stub（`scripts/d1_lib.sh`、`d2_admin_check.sh`、`security/baseline.yaml`）。门禁：`bash scripts/check_five_products_packaging_surface.sh`。

---

## 11. 角色与协作

| 事项 | 我 | 你 |
|---|---|---|
| 架构/代码/测试/打包/文档/验证/模板 | 负责 | review / 批准 |
| 优先级/范围/验收 | 提议 | 最终决定（已授权我决定） |
| ADR 签字 / 客户 / 合同 | 不签 | 你 / 未来团队 |
| 生产环境 | 不接触 | 提供测试环境 |

**节奏**：每周 1–2 个可合并 PR；每阶段一次 Gate review；每模块完成后写 charter/测试/文档再切换。

---

## 12. 风险与止损

| 风险 | 触发 | 止损 |
|---|---|---|
| 范围蔓延（“所有程序/所有资产/所有现场”） | 单模块需求无边界 | 回到首版范围：Agent/Skill/Workflow；只读盘点；本地优先 |
| 过早拆进程 | 无 ADR 就拆 DB/进程 | 停在 A2 / D1c |
| 分布式单体 | 跨模块仍共享表 | 先修数据归属 |
| 单人 context switch | 5 模块并行 | 同一时间只深做 1 个 |
| G0 未绿 | 复核失败 | 冻结功能，先修 |
| 评审瓶颈 | PR 堆积 > 1 周 | 缩小 PR / 批量评审 |
| ADR 延迟 | 关键拆分等批 | 先做 A2 / D1c，不等 |

---

## 13. 度量

- **自治**：跨模块 internal import = 0；共享表 = 0；契约测试覆盖；模块 build/test 时间；变更耦合。
- **交付**：D1 安装成功率/耗时；D2 文档/扫描/兼容；D3 UAT 通过率/证据完整率。
- **工程**：CI 时长、flake 率、覆盖率、MTTR。

---

## 14. 前 90 天

| 周 | 交付 |
|---|---|
| W1–2 | G0 只读复核；五模块 charter 草案；契约清单 |
| W3–6 | 残留逃逸清扫；SBOM/签名；模块模板；Pi 打包 |
| W7–10 | Pi D1；FDE 现场范围；评测协议草案 |
| W11–12 | G0/Pi Gate review；决定是否进入 FDE |

---

## 15. 明确不做

- 不做五个销售品 / P&L。
- 不做五个微服务同时上线。
- 不做销售/定价/合同/SLA/24×7。
- 不做“零耦合”。
- 不在 G0 未绿时加功能。
- 不做无 ADR 的进程/DB 拆分。

---

## 16. 假设与待确认

1. 接受 **A1–A3 / D1–D3** 命名，不再用 E1–E3。
2. 接受 **5 能力 + 3 部署单元**，不是 5 个平级进程。
3. 接受 **20 个月五能力 D2、Pi/FDE/评测 D3**；全五进程拆分是 stretch。
4. 接受 **FDE/本体/评测/aiPlat 的进程/DB 拆分逐产品 ADR**。
5. 接受每周 1–2 个 PR 的 review 节奏。

---

## 17. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-01 | **V2.2** | 显式解冻 D3 本地验收 + 跨能力 E2E（仍不解冻 authorize）；入口 `ops_d3_local_acceptance_all.sh` / `ops_five_products_e2e_local.sh` |
| 2026-11-01 | **V2.1** | G0 通过（P0-3′）；D1c=cohost；Pi D3 / FDE·Onto·Eval D2 / Central D2 Thin 本地收口；共享 packaging base + baseline checker；五包 `PERF_BASELINE.md` + `check_five_products_perf_baseline.sh`（非生产 SLA）；`staging_ready=false`、硬门 false；复审 2026-11-08 |
| 2026-10-29 | V2 | 从“五产品 E1–E3”改为“五能力 A/D 级 + 三类部署”；对齐 week-34 基线、ADR-09 边界、E0–E5 命名 |
