# P0 开工清单（勘误后 · 2026-10-29）

> **状态**：W1 复核已跑；**SSOT 切换为 V2**  
> **时间盒**：W1–W2（约 10 个工作日）  
> **纪律**：**不改业务代码**（逃逸清扫属 G0 W3–6，另批）  
> **真源（最新）**：[`docs/architecture/plans/five-capability-independent-engineering-plan.md`](../../docs/architecture/plans/five-capability-independent-engineering-plan.md)（V2 · 五能力 + 三类部署 · A1–A3/D1–D3）  
> **旧口径作废**：五平级产品 / 仅 D1c 叙事 — 以 V2 §0 为准  
> **HEAD 基线**：`b46e286`（week-34）— 结论须用命令复核，不以 commit message 自证

---

## 0. 锁定口径（本阶段口头禁止误用）

| 术语 | 本阶段含义 |
|------|------------|
| **D0** | 共进程现状能力 |
| **D1c** | 契约/schema 独立，**进程仍共部署**（≠ 独立部署） |
| **D1** | 独立进程/DB/升级回滚 — **仅 Pi 在 Gate3 内可冲；其余产品需单独 ADR** |
| **E0–E5** | 落地方案证据等级（文档→生产），**禁止**与 D* 混称 |

**冻结**：产品边界外新能力、新五产品叙事、非 D1 使能重构。  
**不冻结**：expand-green / hermetic / CI / 安全 / 逃逸债 / 契约修补 / 文档 / Bug。

---

## 1. W1 — 只读复核（D0 基线取证）

| ID | 项 | 命令 / 做法 | 通过标准 | 产出 |
|----|----|-------------|---------|------|
| P0-1 | collect | `cd aiPlat-core && python -m pytest core/tests --collect-only -q` | **0 error** | 写入 G0 报告 |
| P0-2 | full unit | `cd aiPlat-core && python -m pytest core/tests/unit -q --tb=line` | **0 failed**（记录 passed/skipped） | 同上 |
| P0-3 | HOME 隔离 | **推荐 P0-3′**：假 `HOME` **可写** + `$HOME/.aiplat`→`AIPLAT_HOME`（同 conftest）；可选压力测：`HOME` chmod 555（已知会打挂 git 依赖测） | P0-3′：0 failed。字面只读 HOME 见 `G0_REPORT`（16 git 红，非逃逸回归） | 同上 |
| P0-4 | CI 形态 | `wc -l .github/workflows/ci.yml`；确认 `CORE_TARGETS` 单数组 | **≈242 行**；无 300+ 重复路径列表 | 同上 |
| P0-5 | nightly 形态 | 读 `.github/workflows/core-tests-nightly.yml` | `core-tests-unit` **无** `continue-on-error` | 同上 |
| P0-6 | 逃逸扫描 | 生产代码（排除 tests）`expanduser("~/.aiplat")` / 硬编码 `~/.aiplat` | 出**清单**（路径:行）；0 为理想，非 0 → 进修复计划（业务修复进 W3+，本周只列） | `reports/five-products/P0_ESCAPE_SCAN.md` |

**W1 不做**：修业务逻辑、开 Pi 安装器实现、拆服务。

---

## 2. W2 — 骨架与草案（仍零业务代码）

| ID | 项 | 交付物路径（建议） | 通过标准 |
|----|----|-------------------|---------|
| P0-7 | 产品清单 | `product.manifest.yaml`（仓根或 `reports/five-products/`） | 五产品各一行：id / owner / 当前级(D0) / 下一级(D1 或 D1c) / ADR 引用 |
| P0-8 | 产品模板 | `templates/product/` | 含：Dockerfile 占位、Chart 骨架、docs 目录清单、contract-tests 占位、runbook/UAT 空模板、README |
| P0-9 | 契约脚手架 | `templates/product/contracts/` + 至少 **1** 个样例（优先 Pi Thin 已有契约引用） | 可 `pytest` 或脚本跑通「样例 schema 校验」；N-1 规则写进 README（可先文档） |
| P0-10 | Pi Chart 骨架 | `templates/product/charts/pi/` 或 `packages/aiplat-pi-runtime/chart/` | Helm 3 可 `helm lint`（空 values 允许） |
| P0-11 | SBOM/签名骨架 | `scripts/release/` 或模板内：syft/cosign **调用说明 + stub 脚本** | 文档写清输入/输出路径；本周可不接 CI required |
| P0-12 | 升级/回滚/备份骨架 | 每产品 runbook 三节空模板 + Pi 一节填「现状 Gate3 脚本指针」 | 指向已有 `gate3_pi_thin_*` / rollback drill，不新造并行流程 |
| P0-13 | flake 策略 | `docs/` 或 `reports/five-products/FLAKE_POLICY.md` | owner + 过期日；**禁止无 ticket 的 skip/xfail**；隔离目录约定 |
| P0-14 | ADR 草案×4 | `reports/five-products/ADR-DRAFT-{diagnosis,fde,ontology,control-plane}-d1.md` | 各 1 页：动机 / 非目标 / D1c→D1 门槛 / 回滚；**不实施、不 Accepted** |
| P0-15 | G0 报告 | `reports/five-products/G0_REPORT.md` | 见 §3 |

---

## 3. G0 通过条件（八项全勾才出 P0）

- [ ] P0-1 collect 0 error（附命令输出摘要）
- [ ] P0-2 unit 0 failed（附 passed/skipped 计数）
- [ ] P0-3 只读 HOME 下 unit 绿（附 HOME/AIPLAT_HOME 路径）
- [ ] P0-4/5 CI≈242 + nightly unit 硬门已确认
- [ ] P0-6 逃逸扫描清单已落盘（0 或带修复计划）
- [ ] P0-8/9/10 模板 + 契约样例 + Pi Chart 骨架存在
- [ ] P0-11/12/13 SBOM·签名说明 + 升级/回滚模板 + flake 策略
- [ ] P0-14 四份 ADR 草案 + P0-15 G0 报告一页

**明确不进 G0 主债**：「21 红」仅作 P0-2/3 复核项，不再单列清债工作包。

---

## 4. 两周节奏

| 周 | 焦点 | 出口 |
|----|------|------|
| **W1** | P0-1…P0-6 | 复核通过/失败表；逃逸清单 |
| **W2** | P0-7…P0-15 | 骨架 PR（仅 docs/templates/scripts/reports）+ G0 报告 |
| **Gate** | 你 review G0 报告 | **通过 → 开 Pi D1**；失败 → 只修复核缺口，仍不扩产品范围 |

**PR 纪律**：每周 ≤2 个；本阶段 PR 只含 `reports/`、`templates/`、`docs/`、`scripts/` 骨架、workflow **只读确认**（不改业务）。

---

## 5. Pi D1 入场条件（P0 之后，不在本两周做）

须同时满足：

1. G0 八项勾完；  
2. 仍在 Gate3 / ADR-08 / Pi BOUNDARY 内；  
3. 若安装器/更新通道超出 ADR-08 原文 → **先 ADR-08 修订草案**，再写代码；  
4. 第一刀建议：干净环境一条命令安装 + `/healthz` + 升级/回滚演练（复用 Gate3 脚本，不平行发明）。

---

## 6. 明确不做（P0）

- 不改 `aiPlat-core/core/harness/**` 业务逻辑（逃逸**修复**放到 G0 通过后的专项，清单可先出）  
- 不拆诊断/FDE/本体/控制面进程或 DB  
- 不宣称五产品 D1 / 对外 E4  
- 不做销售/定价/合同/SLA/24×7  
- 不以 week-34 commit 文案代替 P0-1…3 命令输出  

---

## 7. 角色

| 事项 | 执行 | 批准 |
|------|------|------|
| 跑复核命令、写报告/骨架/ADR 草案 | Agent | 你 |
| G0 是否通过、是否开 Pi D1 | — | 你 |
| 进程/DB 拆分 ADR Accepted | — | 架构×业务联签（现行 Gate 规则） |

---

## 8. 下一句口令

你说 **「按 P0 开工」** → 从 **P0-1** 只读复核开始（先出命令输出，再写 `G0_REPORT` 草稿）。  
你说 **「先改清单」** → 指出要改的 ID。
