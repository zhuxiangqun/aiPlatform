---
doc_type: Design
authority: plan
scope: docs-reasonable-reduction
language: zh-CN
status: closed
draft_date: 2026-10-23
revised: 2026-10-23-r2
approved_batches: [D0, D1, D2, D3, D4, D5]
closed_at: 2026-10-23
based_on:
  - reports/docs-governance/docs-system-status-analysis-2026-10.md
  - reports/docs-governance/docs-cleanup-plan-2026-10.md
predecessor: docs-cleanup-plan-2026-10（C0–C4 已收口；现位于 reports/docs-governance/）
review_note: >
  r1–r2 评审修订；D0–D5 已全部执行并收口（2026-10-23）
---

# aiPlat 文档合理减量方案（责任导向 · 2026-10）

> **性质**：已收口方案（r2）。**D0–D5 已全部执行**。本文件为落点最终版本（`reports/docs-governance/`）。  
> **前提**：[`docs-cleanup-plan-2026-10.md`](./docs-cleanup-plan-2026-10.md) 的 C0–C4 已收口；过程索引见 [`README.md`](./README.md)。  
> **本方案不追求「为减少而减少」**；不以 `docs/**/*.md` 配额为验收标准。

---

## 0. 问题重述与目标重钉

### 0.1 上一轮达成了什么、没达成什么

| 维度 | C0–C4 结果 | 是否等于「合理」终态 |
|------|------------|----------------------|
| 维护区噪声（收官 research / 过期 plans / 知识 stub） | 明显改善 | **部分**：过程纸与大簇责任混杂仍在 |
| `docs/` 树内 Markdown 总数 | 持平 259 | **无关对错**：该数字不是本阶段主目标 |
| 读者能否分辨现行 vs 历史 vs 过程 | 改善但仍混 | **本方案主战场** |

上一轮若被读成「整个仓库文档变少了」会失望；正确读法是：**有依据地归档与消歧，维护面收缩**。尚未完成的是：按**现行责任**安置剩余文件，并仅在无责任且无义务时删除。

### 0.2 本方案唯一主目标

**让每份文档只承担它仍应承担的责任；责任结束后退出维护区（迁出或删除）；责任仍在则保留——即使 `docs/` 树内总数不变。**

### 0.3 观测指标命名（强制 · 防口径漂移）

| 观测项（正确名称） | 定义 | 会变的操作 | **不是**什么 |
|--------------------|------|------------|--------------|
| **维护区文档数** | C0 §8.3 公式（`docs/` 内扣 archive / `_archive` / whitepaper volumes / 两份生成快照） | 迁出维护区路径、删除 | — |
| **`docs/` 树内 Markdown 总数** | `docs/**/*.md`（排除 `node_modules`） | 仅 **删除** 或 **合并去副本**；迁 `docs/archive/` **通常不变**；迁出 `docs/`（如到根 `reports/`）会 **下降** | **≠ 仓库内全部 Markdown**（不含根 `reports/`、子仓 `*/docs`、`CLAUDE.md` 等） |
| **现行入口可指认性** | 各簇 README / 过程索引是否唯一 | 导航整理 | — |

**根目录 `reports/`**：

- **不计入**上表两项数量指标。  
- 属于处置记录与留存范围（R3/R5 必须检查；见前序方案 §2.1）。  
- 将文件从 `docs/research/` 迁到根 `reports/`：会使 **`docs/` 树内总数**下降，但文件**仍在仓库内**——叙述时禁止写成「仓库文档已物理消失」。

禁止再使用含混的「仓库总数 / 仓库保留文档总数」指代 `find docs … | wc -l` 的结果。

副产物用途：上表数字**可观测、不作硬门槛**。

### 0.4 非目标

- 不设 `docs/` 树内总数 / 维护区数值配额。  
- 不整簇删除 FDE / 对标 / 本体 / contracts。  
- 不把五产品规划、签收包、仍生效的 Charter 伪造成「未发生」。  
- 不在 `docs/research/` 为每一小批再堆复核 Markdown（避免再次「删 N 增 N」）。  
- 不把本方案当作 C0–C4 的无限延期删除授权。  
- 不把根 `reports/README`「删除历史报告不影响完整性」类表述当作批次删除授权（须逐篇 R5）。

### 0.5 与上一方案的继承关系

| 继承 | 废弃/收紧 |
|------|-----------|
| 双指标口径（观测用；本方案改名见 §0.3） | 「次优先降总数」不再写成驱动目标 |
| 主题相同≠重复；候选≠删除清单；已完成≠可自动迁档 | 继续强制 |
| R1–R7 + 删除双路径 A/B | **原样沿用** |
| C0 维护区公式 §8.3 | 复测命令沿用；收口时现算 |

### 0.6 D0 预冻结：过程材料唯一入口与落点（r1 · 执行 D1 前生效）

评审已要求 D1 不得把过程纸分散到未索引位置。**D0 批准本方案时，同时冻结下表**（若改分流规则须升方案补丁版）：

| 规则 | 冻结内容 |
|------|----------|
| **唯一查找入口** | 仓库根 [`reports/docs-governance/README.md`](./README.md)（D1 执行时创建；文内清单 = 过程材料权威索引） |
| **物理落点** | 文档治理过程材料（现状快照、已收口清理方案、C1–C4 复核表、以及本方案在 D5 **收口后的最终版本**）→ **`reports/docs-governance/`** |
| **移动语义** | 一律 **`git mv`（或等价：写入新路径并删除旧路径）**；是**移动**不是复制。落点上的文件即该材料的唯一正文，不存在「docs 一份 + reports 一份」 |
| **research 指针** | `docs/research/README.md` **只保留一条**链到上述 README（不再逐条罗列 c1–c4） |
| **禁止双份** | 同一过程材料不得同时存在于 `docs/research/`（或 `docs/archive/`）与 `reports/docs-governance/`；移动完成后 `docs/` 侧路径必须消失 |
| **禁止默认进 archive** | 文档治理过程纸**不**迁 `docs/archive/`（archive 留给产品/架构历史正文；过程治理轨迹统一走根 `reports/docs-governance/`） |
| **本方案文件** | 批准执行期间可留 `docs/research/`；D5 收口后**移动**到 `reports/docs-governance/`（最终版本），research 仅留入口链 |
| **新复核记录** | 续写 `reports/document-disposition-*.csv` 或 `reports/docs-governance/` 下短附录；**禁止**新增 `docs/research/cN-*-review-*.md` |

根 `reports/` 目录内其它历史审计 JSON/changelog **不属于**本索引范围，勿混入 `docs-governance/` 清单冒充同一责任。

### 0.7 `reports/docs-governance/` 与文档 CI（r2）

| 项 | 约定 |
|----|------|
| **工作流触发** | `.github/workflows/docs-verify.yml` 的 `paths` **包含** `reports/docs-governance/**`（与 `docs/**` 并列）。仅改治理索引/过程材料时也会拉起 Docs Verify。 |
| **自动检查覆盖面** | 现有 `verify_docs.py` / `verify_doc_structure.py` 仍以 **`docs/`** 为主；**不会**因本目录落盘就自动变成全站链接门禁，也不把根 `reports/` 其它文件纳入同一套扫描。 |
| **本目录最低校验（D1/D5 与后续改动必做）** | （1）`reports/docs-governance/README.md` 清单与目录内 `.md` **一一对应、无孤儿**；（2）`docs/research/`（及 `docs/archive/`）无已移动材料的残留路径；（3）`docs/research/README.md` 指向该 README 的相对链接可解析。可用本地：`test -f reports/docs-governance/README.md` + 对照 `ls reports/docs-governance/*.md`。 |
| **明确不做** | 本方案不扩展 `verify_doc_links.py` 覆盖面到全站或整个 `reports/`。 |

---

## 1. 责任终态（目录应长什么样）

执行任何批次前，以本表为「合理」的定义；偏离须在复核记录写明理由。

| 目录 / 材料类 | 应保留在维护区的 | 应退出维护区的 | 默认可删的（须 R5=无义务，且非「未核实」） |
|---------------|------------------|----------------|---------------------------------------------|
| `research/` | 现行对标主报告、仍被引用的设计/元审计依据、未收官 `plan-*`、现行底稿 | 已收官审计快照、**文档治理过程纸**（→ §0.6） | 无入链且 R5 已确认无义务的一次性冒烟纸 |
| `architecture/plans/` | living、仍指导实现的稿、明示「非现状」的五产品目标稿 | 无入链过程稿、已被 SoT 取代的对比（C3 已做一批） | 同左且 R5=无义务 |
| `architecture/` 核心参考 | overview、边界、矩阵、知识入口等 | — | 默认不删 |
| `contracts/` | 约束正文、仍生效 Charter/Runbook、有留存义务的签收包 | 无脚本引用的纯过程纸可迁 archive；已降权扫描纸可路径保留 | 仅路径 B |
| `manuals/` | 现行操作步骤 | 责任已接替的 stub（C4 已处理一批） | 同左 |
| `archive/` | （只读）有留存价值的产品/架构历史 | — | 见 §3.3：断链≠自动可删 |
| 同名消歧对（C2） | 文首已标明异职的两份 | — | 禁止仅因同名合并 |
| 文档治理过程材料 | 仅 §0.6 索引 + 目录内正文 | 退出 `research/` 主列表 | **默认不删**；见 §3.1.1 |

---

## 2. 责任三问（每篇强制，先于处置）

```text
Q1 现行责任？  操作 / 约束正文 / 验收复现 / 现行设计或 ADR 效力 / 无
Q2 留存义务？  合规签收 / 事故审计 / 外部副本要求 / 无 / 未核实·待确认
Q3 接替文件？  有（写路径）/ 无（则不得在仍有 Q1 时迁删）
```

| Q1 | Q2 | 默认 R6 |
|----|----|---------|
| 有 | 任意 | **保留维护区**（可消歧、合并正文到接替文件后删副本） |
| 无 | 有或**未核实·待确认** | **迁出**（过程纸→§0.6；其它→archive 等）；**禁止删除** |
| 无 | 无（R5 已确认） | **移动**到约定落点保留可读最终版本，或 **删除**（路径 A/B） |

「未核实·待确认」不得默当成「无义务」。

**Git 历史不足以单独满足「可删」**：能 `git show` 到旧 blob ≠ 已履行业务审计/签收留存。R5 必须显式结论；对批次复核表见 §3.1.1。

---

## 3. 候选队列（冻结名单 · 全部未复核 · 非授权）

下列仅为**待逐篇三问 + R1–R7** 的输入；任一批执行须**另开批准**（D0 批准本方案 ≠ 批准 D2–D4）。

### 3.1 队列 D1 — research 文档治理过程材料

| # | 文件 | 初步归类（未复核） | D1 默认处置（落点已冻结） |
|---|------|-------------------|---------------------------|
| 1 | `docs-system-status-analysis-2026-10.md` | 现状快照 | 迁 `reports/docs-governance/` |
| 2 | `docs-cleanup-plan-2026-10.md` | 已收口方案 | 迁 `reports/docs-governance/` |
| 3–6 | `c1`…`c4-*-review-2026-10-23.md` | 批次复核表 | 迁 `reports/docs-governance/`（**默认迁、不删**；删见 §3.1.1） |
| — | **本文件** | 现行方案 | 执行期留 research；D5 收口后**移动**到同目录（最终版本，非复制） |

**验收（责任向）**：

1. `research/README` 维护区表不再与对标主报告并列过程纸；  
2. 过程材料**唯一**经 `reports/docs-governance/README.md` 可找全；  
3. `docs/research/` 与 `docs/archive/` 中无 D1 清单的双份残留。

#### 3.1.1 C1–C4 复核表：删除额外门槛（r1）

| 条件 | 要求 |
|------|------|
| 默认 | **移动**到 `reports/docs-governance/`，保持可读全文（唯一正文） |
| 允许删除落点上的最终版本 | 仅当 R5 **明确**「无留存义务」，且 Q2 ≠「未核实·待确认」 |
| 禁止 | 仅以「Git 历史可找回」作为 R5=可删的唯一依据 |
| 外部/业务审计义务 | 与 C4 相同：**未核实·待确认** 时只迁不删 |

### 3.2 队列 D2 — research 规划 / 审计残留

| # | 文件 | 初步归类（未复核） |
|---|------|-------------------|
| 1–6 | `plan-app-factory-l2-*.md` … `l5-cicd.md`、`l45-db-migration.md` | 应用工厂分层规划；判是否仍未收官 |
| 7 | `plan-g6-hooks-bridge.md` | 专项规划 |
| 8 | `plan-tier-ontology-layering.md` | 设计规划 |
| 9 | `记忆系统审计报告.md` | 审计快照（未进 C1 冻结表） |
| 10 | `LLM自动选择策略审计报告.md` | 审计；可能仍有运维参考价值 |
| 11 | `Hermes调研底稿.md` | 原始材料；与根目录 hermes 分析关系待判 |

**C1 已裁定保留、本队列默认不动**（除非出现新接替文件）：

- `aiPlat核心能力对标报告.md`、`对标底稿-2026-10-五家.md`
- `aiPlat治理体系元审计报告.md`、`企业级AI可信落地全景图-aiPlat对照.md`、`应用工厂分析报告.md`

### 3.3 队列 D3 — archive 过期 / 断链快照（修链与删除分判）

原则：处理的是**误导或已确认零留存价值**，不是「archive 太大不好看」。

**断链本身 ≠ 可删。** 断链只证明链接目标不存在；留存价值仍走 Q2/R5。

| 处置类型 | 何时选用 | 验收记录必须写明 |
|----------|----------|------------------|
| **修链** | 报告仍有留存/阅读价值，仅目标路径漂移或应指向现行 SoT | 旧链 → 新链（或「目标已不存在，改为说明句」） |
| **标注失效** | 整份快照过期但仍需留档备查 | 文首失效声明 + 现行替代入口（若有） |
| **删除（路径 B）** | Q1=无且 R5=无义务（非未核实），且无必要保留误导正文 | R3 入链已处理 + R5 结论 |

首批探针（仍须分判，不得「见断链即删」）：

| 文件 | 已知问题 | 允许的下一步（未裁定） |
|------|----------|------------------------|
| `docs/archive/doc_full_scan_report.md` | 指向不存在的 `./ARCHITECTURE_STATUS.md`；文首已自标过期 | 修链 / 标注失效 / 路径 B 删除——**三选一，分别记 R6** |

**D3 批次验收（责任向）**：探针文件的 R6 必须属于上表三类之一且有记录；禁止用「已处理断链」含混带过而未写明类型。

完整 D3 名单在批准该批时生成（输出≠删除清单）：

```bash
find docs/archive -name '*.md' | sort
```

### 3.4 队列 D4 — contracts 过程材料（责任分型，禁止整主题合并）

文件名启发式命中（**候选**）：Kickoff / Smoke / Checklist / Wave Charter / Pilot / M4 Signoff 等。

| 子类 | 默认 |
|------|------|
| 仍被脚本/CI/`test -f` 引用的过程纸 | **路径保留** + 索引降权（延续 C3） |
| 约束正文 / 仍生效 Charter | **维护区保留** |
| 有留存义务的签收包 | 维护区或 archive，**不删** |
| 无引用、R5=无义务的一次性清单 | 迁 archive 或路径 B 删除 |

### 3.5 队列 D5 — 同名消歧对（默认冻结）

| 对 | 本方案默认 |
|----|------------|
| guides ↔ manuals `PR_ARCHITECTURE_CHECKLIST` | **不动**（除非可证重复正文且 CI 路径已迁移） |
| articles ↔ architecture `private-control-plane` | **不动** |
| framework ↔ whitepaper `verification-protocol` | **不动** |

### 3.6 明确不在本方案范围

- 子仓 `aiPlat-*/docs` 大规模搬迁  
- `doc_type` 全站补齐；全站链接门禁扩面；`verify_docs` 菜单假阳性治理（均可另立项）  
- physical exemption `ex-2026-10-docs-cleanup-c0-c4`（**运维债**：2026-11-06 前收窄/拆除，不写入减量验收）

---

## 4. 批次设计（责任向 · 无配额）

| 批次 | 队列 | 允许动作 | 责任向验收 | 观测（可选 · 用 §0.3 名称） |
|------|------|----------|------------|------------------------------|
| **D0** | — | 通过本方案 r2+；冻结 §0.6 / §0.7 / §3 | `status`→approved；过程落点与 CI 约定生效 | — |
| **D1** | §3.1 | 按 §0.6 **移动**到 `reports/docs-governance/`；更新 research README；做 §0.7 最低校验 | §3.1 三条验收；C1–C4 **默认只移不删**；§0.7 清单无孤儿 | 维护区可能 ↓；`docs/` 树内总数因移出 docs 可能 ↓（文件仍在仓库根 reports） |
| **D2** | §3.2 | 未收官保留；收官迁 archive | 每份有 Q1–Q3 | 同上 |
| **D3** | §3.3 | 修链 / 标注失效 / 删除分判 | §3.3 验收：每份写明处置类型 | 仅删除时 `docs/` 树内总数 ↓ |
| **D4** | §3.4 | 分型后降权/迁档/极少删除 | contracts 能指认约束 vs 过程 vs 签收 | `docs/` 树内总数通常不变 |
| **D5** | — | 收口：复测、更新 `docs/README` 时点、本方案**移动**为 docs-governance 最终版本 | §1 终态无未解释偏离；§0.7 最低校验 | 记录数字，**不判成败** |

批次可合并批准（如 D0+D1），但**不可**跳过逐篇三问。

---

## 5. 复核记录落点（与 §0.6 一致）

| 允许 | 禁止 |
|------|------|
| `reports/docs-governance/` 正文 + 其 README 清单 | 在 `docs/research/` 新增 `cN-*-review-*.md` |
| `reports/document-disposition-*.csv` 续写 | 过程纸同时留在 research 与 docs-governance（双份） |
| PR checklist | 用「Git 可找回」跳过 R5 直接删 C1–C4 |
| 本方案短附录 | 无批准执行 §3 队列 |

---

## 6. 复测命令（观测用 · 与 C0 同口径）

```bash
# docs/ 树内 Markdown 总数（≠ 仓库全部 Markdown）
find docs -name '*.md' ! -path '*/node_modules/*' | wc -l

# 维护区（同 docs-cleanup-plan §8.3）
python3 - <<'PY'
from pathlib import Path
GEN = {
    "docs/reports/AIPLAT_ARCHITECTURE_REPORT.md",
    "docs/reports/AIPLAT_DIAGNOSTIC_REPORT.md",
}
n_total = n_maint = 0
for p in Path("docs").rglob("*.md"):
    if "node_modules" in p.parts:
        continue
    n_total += 1
    rel = p.as_posix()
    if rel.startswith("docs/archive/") or "_archive" in p.parts:
        continue
    if rel.startswith("docs/whitepaper/volumes/") or rel in GEN:
        continue
    n_maint += 1
print("docs_tree_total", n_total)
print("maint", n_maint)
PY
```

收口叙述模板：

```text
责任验收：§1 终态对照 = …（通过/有例外: …）
观测：docs_tree_total=… maint=…（相对 C0–C4 收口 259/187）
说明：移动到根 reports/ 会使 docs_tree_total↓，文件仍在仓库
删除 N=… 迁出维护区 M=…（迁 archive / 移动到 reports/docs-governance 分列）
D3 分判：修链=… / 标注失效=… / 删除=…
```

---

## 7. 批准与禁止

| 允许 | 禁止 |
|------|------|
| 用 §6 复测并引用本方案 | 将「方案已写 / r2 已吸收评审」视为 D1–D4 已批准 |
| 按 §3 缩小某批执行范围 | 设 `docs/` 树内总数配额并倒推删除 |
| 修正启发式名单（升补丁版） | 未做三问即迁/删；断链即删 |
| D3 在 R5=无义务时真删 | 因「archive 最大」整目录删 |
| D1 按 §0.6 统一落点 | 过程纸分散到 archive + reports 且无唯一索引 |

---

## 8. 建议的首批批准范围（供拍板）

**D0–D5 已全部执行并收口（2026-10-23）** — 见 §10–§14。

---

## 9. 评审意见吸收对照

| 轮次 | 评审点 | 落点 |
|------|--------|------|
| r1 | 「仓库总数」易误解 | §0.3 **`docs/` 树内 Markdown 总数** |
| r1 | D1 唯一入口与落点 | §0.6 |
| r1 | C1–C4 不能仅凭 Git 删除 | §3.1.1；§2 |
| r1 | D3 修链 vs 删除分判 | §3.3 |
| r2 | 「收口后副本」与禁止双份冲突 | §0.6：**移动** / **收口后的最终版本**；禁止复制双留 |
| r2 | 新落点可能不触发文档 CI | §0.7 + `docs-verify.yml` 增加 `reports/docs-governance/**`；最低校验三条（非全站门禁） |

---

## 10. D0+D1 执行记录（2026-10-23）

| 项 | 结果 |
|----|------|
| D0 | 方案 `status: approved`；§0.6 / §0.7 / §3 冻结生效 |
| D1 移动（6） | `docs-system-status-analysis`、`docs-cleanup-plan`、`c1`…`c4` → `reports/docs-governance/`（`git mv`；未删） |
| 唯一入口 | [`reports/docs-governance/README.md`](./README.md) 已建；`docs/research/README` 单指针 |
| §0.7 | 清单↔目录一致；research 残留 0；指针可解析 |
| 本文件 | **仍在** `docs/research/`（D5 再移动） |
| 责任验收 | research 主列表不再并列过程纸；过程材料可经唯一入口找全 |
| 观测 | `docs_tree_total` **254**（原 259）；`maint` **182**（原 187）；文件仍在仓库根 `reports/` |

---

## 11. D2 执行记录（2026-10-23）

| 项 | 结果 |
|----|------|
| 批准 | 用户「继续」 |
| 保留维护区（8） | 全部 `plan-app-factory-l2*`…`l5`（验收 MUST）+ `plan-g6-hooks-bridge` + `plan-tier-ontology-layering`（代码设计依据） |
| 迁 archive（3） | `Hermes调研底稿` / `LLM自动选择策略审计报告` / `记忆系统审计报告` |
| 删除 | **0** |
| 复核落点 | [`reports/docs-governance/d2-research-residual-2026-10-23.md`](./d2-research-residual-2026-10-23.md) |
| 观测 | `docs_tree_total` 不变（仍在 docs/archive）；`maint` ↓3 |

---

## 12. D3 执行记录（2026-10-23）

| 项 | 结果 |
|----|------|
| 批准 | 用户「继续」 |
| archive 相对链扫描 | broken **1** → 修后 **0** |
| `doc_full_scan_report.md` | R6=**修链**（兼强化失效说明）；目标 `aiPlat-core/docs/ARCHITECTURE_STATUS.md` |
| 删除 / 标注失效（单独成类） | 删除 **0**；未另开「仅标注、不修链」条目 |
| 复核 | [`reports/docs-governance/d3-archive-links-2026-10-23.md`](./d3-archive-links-2026-10-23.md) |
| 观测 | `docs_tree_total` / `maint` **不变**（未删未迁出 docs） |

---

## 13. D4 执行记录（2026-10-23）

| 项 | 结果 |
|----|------|
| 批准 | 用户「继续」 |
| 动作 | `docs/contracts/README` 责任分型：§3.0 约束/操作 · §3.1 过程降权 · §3.2 签收 |
| 迁 archive / 删除 | **0 / 0**（候选均有入链或留存义务） |
| 复核 | [`d4-contracts-typing-2026-10-23.md`](./d4-contracts-typing-2026-10-23.md) |
| 观测 | `docs_tree_total` / `maint` **不变** |

---

## 14. D5 收口（2026-10-23）

| 项 | 结果 |
|----|------|
| 本方案 | **移动**至 `reports/docs-governance/`（最终版本；非复制） |
| research | 仅保留指向本目录 README 的**单指针** |
| §0.7 | 清单↔目录对齐；research 无过程纸残留 |
| §1 终态 | research 无治理过程纸并列；contracts 可指认四类责任；archive 相对链 broken 0 |
| 观测（收口现算） | 见下表 |

| 观测项 | C0–C4 收口 | D5 收口 |
|--------|----------:|--------:|
| `docs/` 树内 Markdown 总数 | 259 | **253**（−6 过程材料出 docs） |
| 维护区（C0 公式） | 187 | **178** |
| `research/` | 23 | **14** |
| `archive/` | 57 | **60** |

说明：D2 迁 archive 不减树内总数；D1/D5 移出 `docs/` 才降 `docs_tree_total`；文件仍在仓库根 `reports/docs-governance/`。

---

*方案版本: 2026-10-23-r2 · 责任导向 · **D0–D5 已收口** · 前序 C0–C4 见同目录 `docs-cleanup-plan-2026-10.md`*
