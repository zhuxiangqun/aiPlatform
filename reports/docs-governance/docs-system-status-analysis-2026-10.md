---
doc_type: Report
authority: snapshot
scope: workspace-documentation-system
language: zh-CN
snapshot_at: 2026-10-23T10:23:41Z
---

# aiPlat / Pi 文档系统现状分析

> **性质**：现状快照报告。非规约、非方案。与有效规约/契约或代码冲突时，按问题类型分别回到源码行为证据或有效规范文本；本报告不裁决实现对错。  
> **盘点时点**：`2026-10-23T10:23:41Z`（UTC）。下文凡未另注的计数，均为**写入本报告前**的盘点值。  
> **本报告副作用（不计入既有统计）**：落盘后 `docs/research/` Markdown 数 +1；本文件自身带 `doc_type: Report`，不计入「盘点时 doc_type 仅 2 份」的既有统计。

---

## 1. 分析范围与证据口径

本次只读检查了工作区中的 Markdown 文档、主要导航和治理文件、白皮书生成规范与脚本、文档结构/链接检查器，以及 Pi 文档入口。

已核实的范围包括：

| 范围 | 计数（写入本报告前） | 统计命令口径 |
|------|---------------------:|--------------|
| 根级 `docs/` 下 `.md` | **257** | `find docs -name '*.md' ! -path '*/node_modules/*'` |
| 五个子仓 `*/docs/` 下 `.md` | **159** | 见附录 A.1（core 74 + infra 31 + platform 16 + management 25 + app 13） |

根目录和主要产品目录还存在 `CLAUDE.md`、`README.md`、`SECURITY.md`、`AIPLAT_CAPABILITIES.md`、`AIPLAT_ROADMAP.md`、工作区 `reports/`、Pi package 文档等，**不属于**上表两项计数。

文档总量会因是否纳入虚拟环境、隐藏目录、生成目录、package 和 reports 而变化，因此**「全仓文档总数」必须带明确的统计范围，不能只报一个裸数字**。本报告不给出无范围的「全仓总数」。

下文把观察到的文件/脚本状态作为事实；把「为何会造成阅读困难」作为分析。**不包含改造方案或执行阶段。**

---

## 2. 现状事实

### 2.1 文档数量集中在少数大型簇

`docs/` 一级目录的实际 Markdown 数（写入本报告前）：

| 文档簇 | 文件数 |
|--------|-------:|
| contracts | 43 |
| manuals | 39 |
| architecture | 38 |
| research | 37 |
| archive | 29 |
| whitepaper | 16 |
| standards | 10 |
| 其他专题合计 | 其余（合计仍为 257） |

五个子仓文档主要在 `aiPlat-core/docs`，其次是 infra、management、platform 和 app。根 `docs/` 不是全仓唯一文档位置，而是主入口和跨层文档集合。

### 2.2 根文档入口存在实际漂移

`docs/README.md` 当前（盘点时）：

- 标注「最后更新」为 `2026-07-18`。
- 目录计数与文件现状不一致，例如：architecture 标 23、实有 38；research 标 14、实有 37；manuals 标 22、实有 39；archive 标 27、实有 29；standards 标 3、实有 10。
- 「按阅读目的」列出 `api/`、`database/`、`llm/`、`deployment/`、`knowledge/`、`memory/`、`testing/` 等路径；其中若干不是 `docs/` 当前的一级目录，也没有明确指出实际文件位置（例如入门实为 `manuals/getting-started.md`）。
- 没有清楚指向 Pi 当前交付入口。

问题不只是计数过期；读者还可能按入口中的目录去找不存在或未指明的路径。

### 2.3 宪法定义与实际目录不一致

`docs/DOCUMENT_SYSTEM.md` 规定文档目录、类型、权威源和维护流程，但与当前状态有几类落差：

- 文档类型章节标题称「五类」，表格实际列出六类：规约、设计、指南、报告、裁决、骨架（见该文件 §2.1）。
- 当前 `docs/contracts/` 和 `docs/guides/` 未登记在其 §一目录树中。
- `python3 scripts/verify_doc_structure.py` 因这两个目录未登记而失败（exit 1；见附录 A.2）。
- 全站 `docs/` 内带 `doc_type` frontmatter 的 Markdown：**写入本报告前为 2 份**（`docs/DOCUMENT_SYSTEM.md`、`docs/strategy/comparison-vs-vendors.md`）。文档类型治理尚未以一致的文件级元数据落地。本报告落盘后该计数会增加，**不回写为盘点基线**。
- DOCUMENT_SYSTEM 的目录树和权威源表含有过时或不完整条目（例如架构文件路径、`文档目录数` 写 23 而盘点时顶层子目录为 26）。

这说明文档治理规则存在，但其维护结果没有持续反映真实文件系统。

### 2.4 分类和入口同时承担多种含义

当前目录和导航同时承载以下信息：

- 内容类型：规范、设计、手册、研究、报告、ADR。
- 维护状态：当前、已完成、生成快照、历史归档。
- 受众：开发、运维、FDE、产品、管理层。
- 生成方式：手写、脚本生成、suite 生成、运行快照。

这些维度没有稳定分开。例如：

- `research/` 同时有现行主报告、调研底稿、已完成方案和历史核实报告（其 README 索引中多处标注「已收官 / 已完成 / 已核实 / 已闭环」与现行主报告并列）。
- `architecture/plans/` 同时有仍在使用的 living 文档、提案和过期规划；architecture README 将五产品三份放在「规划与路线图（非现状）」下，但未列出 `pi-thin-runtime.md`（盘点时 `architecture/README.md` 无 `pi-thin` 字样）。
- `whitepaper/` 同时包含生成卷、体系规则、商业材料与案例材料。

因此，目录名本身无法可靠回答一份文件是否现行、谁负责维护、改动应该去改哪个源文件。

### 2.5 contracts 已有索引，但索引维护负担较重

`docs/contracts/README.md` **已经存在**，且按 FDE 与 Org L5 等主题提供阅读顺序和状态说明。因此，「缺少 contracts README」不符合当前仓库事实。

该索引同时包含大量阶段状态、开工/签收状态和跨仓路径，容易变成需要频繁更新的状态页。问题是**已有索引是否持续准确、是否职责过重**，不是缺少索引文件。

### 2.6 research 与 archive 的状态边界不清

`docs/research/` 有 37 份 Markdown（写入本报告前）。其 README 把多个标明「已收官」「已完成」「已核实」「已闭环」的文件与现行主报告、底稿和活跃方案放在同一索引中。

`docs/archive/` 已有 29 份 Markdown 和归档说明。因此，归档机制并非不存在；当前可观察到的缺口是：文件级「是否仍属活跃 research」的判断与「若移动则影响哪些链接/suite/脚本」在导航层不可见——本报告只陈述该现象，不描述应如何迁移。

### 2.7 白皮书生成链路有效，但只保证新鲜度

白皮书体系有 `docs/whitepaper/WHITEPAPER_SYSTEM.md`、docs/whitepaper 下的 suite 配置（文件名 whitepaper-suite.yaml）和生成脚本。本次运行结果（附录 A.3）：

- `python3 scripts/generate_platform_whitepaper.py --check` → **PASS**（相对 `AIPLAT_CAPABILITIES.md` 新鲜）。
- `python3 scripts/generate_whitepaper_volumes.py --check` → **PASS**（五卷相对 suite + CAPABILITIES + assessment-scores 新鲜）。

这只证明**生成文件与指定输入源同步**，不证明卷内没有重复正文，也不证明摘要适合目标受众。白皮书可以既新鲜又冗长。

### 2.8 Pi 文档已有相对清楚的包内分工，根导航缺失

Pi 相关资料当前分布在（package 侧 `.md`，排除 `node_modules`，盘点时共 11 份路径级文件，含 fixtures）：

- `packages/aiplat-pi-runtime/README.md`：包入口、Pi-only 和企业回连使用方式。
- `packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md`：企业回连配置和技术能力。
- `packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE_DELIVERY.md`：交付、SKU 和验收。
- `packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE_KB_HEALTH.md`：KB health 细节。
- `docs/architecture/plans/pi-thin-runtime.md`：Pi 产品定位和轴 A/B 的 living 摘要。
- `packages/aiplat-pi-runtime/PHASE0.md`、`PHASE0_RESULTS.md`：阶段验证记录。
- `packages/aiplat-pi-runtime/docs/FACTORY_IN_EXPERIMENT.md`：厂内 Pi 实验和关闭状态。

包内已有分工，但根 `docs/README.md` 没有 Pi 主路径；`docs/architecture/README.md` 列出五产品规划，**未**链到 `pi-thin-runtime.md`。阅读分流（「当前已交付 Thin Runtime」vs「非现状目标规划」）在根架构导航上不明显。

现状语义（文档表述层面）：**当前仓库已交付形态是 Pi-only 默认运行、企业能力可选回连；这不等同于五产品目标方案中的完整 Enterprise Runtime。**（见 `pi-thin-runtime.md` 与五产品 plans 各自正文；本条为文档间语义对照，非运行时验收。）

此外，「hybrid」在企业回连、Skill 执行类型和 Builder 工厂模式中可能指不同概念。当前根导航没有提供全局消歧。

### 2.9 现有文档校验覆盖有限

| 脚本 | 实际覆盖（盘点时） | 本次结果 |
|------|-------------------|----------|
| `scripts/verify_doc_structure.py` | 仅检查 `docs/` **一级目录**是否写入 `DOCUMENT_SYSTEM.md` §一；不检查 README 文件数，也不验证全站文件清单 | **失败**（未登记 `contracts/`、`guides/`） |
| `scripts/verify_doc_links.py` | **仅**检查 3 个文件：`docs/DOCUMENT_SYSTEM.md`、`docs/README.md`、`docs/manuals/README.md` 中的 Markdown 链接 | **指定 3 个文件范围内通过**（exit 0） |
| 白皮书 `--check` | 生成物相对指定权威源的新鲜度 | 总白书与五卷均 **PASS** |

因此：

- 不能把「指定 3 个文件链接检查通过」简称成「文档链接检查通过」或「全站无断链」。
- 「结构检查失败」与「白皮书新鲜度通过」可同时成立；二者回答不同问题。

---

## 3. 基于事实的系统性诊断

文档系统的主要问题不是单纯「文件数量太多」，而是**权威、生命周期、生成责任和导航规则没有在同一套治理机制中闭环**：

1. **入口陈旧**：目录、计数和路径未随文件系统同步（§2.2）。
2. **维护状态弱化**：完成、活跃、目标态和历史状态主要靠正文措辞表达，入口未统一呈现（§2.4、§2.6）。
3. **事实源与叙述副本并存**：生成器和白皮书机制存在，但新鲜度门禁不负责控制重复内容（§2.7）。
4. **目录不等于分类**：同一目录收纳不同维护状态、受众和生成方式的文件（§2.4）。
5. **治理检查与治理承诺不匹配**：宪法覆盖面大，结构/链接脚本检查面小；结构检查未与「目录已登记」承诺保持一致（§2.3、§2.9）。
6. **跨仓分布没有形成统一导航层**：文档实际分布在根 docs、子仓、包目录和根级文件中（§1、§2.1、§2.8）。
7. **状态声明缺少证据等级**：有些文档声明「已完成/已接线」，但导航没有始终链接到实现或行为验证证据（§2.5、§2.6；contracts / research 索引中的完成措辞即此类现象）。

上述机制同时解释了：文档很多但难找、入口很多但不敢确信、生成物新鲜却仍可能冗长重复等阅读现象。

---

## 4. 权威判断需要分成两类

文档系统不能用一条「代码 > CAPABILITIES > 契约」的线性顺序处理所有冲突，因为它们回答的问题不同：

- **现状事实**：源码和可重复行为证据说明现在实际实现了什么。`AIPLAT_CAPABILITIES.md` 是能力声明/接线索引，不能单独证明行为可用。
- **规范要求**：有效的规约、契约和已批准 ADR 说明系统应该如何工作。若实现违反契约，应记录为实现偏差，不能因为代码如此就把规范自动判为失效。

规划、研究和白皮书可以解释背景或目标，但不能覆盖上述两类权威。

> 本节是**分析框架**：说明文档冲突至少对应两类问题。它**不**新增全局优先级规则，也不改写工作区既有规约文本中的裁决表述。

---

## 5. 统一结论

先前分析正确指出了主要结构问题：入口失配、现状与非现状混排、生成物可能重复叙述、Pi 根导航缺失。仓库核验支持这些判断。

同时，实际现状要求补上以下事实：`contracts/README.md` 已存在；白皮书新鲜度检查当前通过；结构检查当前失败；链接检查覆盖很窄（指定 3 个文件）；文档类型本身尚未稳定应用到文件级（盘点时 `docs/` 内 `doc_type` 仅 2 份，不含本报告）。忽略这些事实会让后续讨论从错误基线开始。

**统一的现状基线：**

文档系统已有成熟的部分治理和生成设施，但目录、入口、元数据和校验覆盖未同步演进，导致实际维护状态不可从导航可靠判断。

本文件为后续讨论提供**单一现状基线**。改造方案不在本报告范围内。

---

## 附录 A. 命令证据（可复现）

盘点时点：`2026-10-23T10:23:41Z`（UTC）。工作区根：`/Users/apple/workdata/person/zy/aiPlatform`。

### A.1 规模计数

**根 `docs/` Markdown**

```text
范围: docs/**/*.md
排除: 路径含 node_modules
命令: find docs -name '*.md' ! -path '*/node_modules/*' | wc -l
结果: 257
```

**一级簇分布**（同范围；Python 按 `docs/` 下第一级路径聚合）摘要：contracts 43、manuals 39、architecture 38、research 37、archive 29、whitepaper 16、standards 10；合计 257。

**五子仓 `*/docs`**

```text
范围: {aiPlat-core,aiPlat-infra,aiPlat-platform,aiPlat-management,aiPlat-app}/docs/**/*.md
结果: 74 + 31 + 16 + 25 + 13 = 159
```

**`doc_type` frontmatter（写入本报告前）**

```text
范围: docs/**/*.md，行首匹配 ^doc_type:
命令: rg -l '^doc_type:' --glob '*.md' docs
结果: 2 个文件
  - docs/DOCUMENT_SYSTEM.md
  - docs/strategy/comparison-vs-vendors.md
说明: 不含本报告文件。
```

### A.2 结构检查

```text
命令: python3 scripts/verify_doc_structure.py
退出码: 1
摘要:
  未登记目录: contracts/、guides/
```

### A.3 白皮书新鲜度

```text
命令: python3 scripts/generate_platform_whitepaper.py --check
退出码: 0
摘要: PASS: whitepaper fresh vs AIPLAT_CAPABILITIES.md

命令: python3 scripts/generate_whitepaper_volumes.py --check
退出码: 0
摘要: PASS: all five whitepaper volumes fresh vs suite + CAPABILITIES + assessment-scores
```

### A.4 链接检查（指定文件）

```text
命令: python3 scripts/verify_doc_links.py
检查文件（脚本 FILES_TO_CHECK，共 3 个）:
  - docs/DOCUMENT_SYSTEM.md
  - docs/README.md
  - docs/manuals/README.md
退出码: 0
摘要: All links valid across 3 files
表述约束: 仅能写「指定 3 个文件范围内通过」，不能写「全站文档链接检查通过」。
```

### A.5 入口与 Pi 相关路径存在性（抽样）

```text
docs/contracts/README.md → 存在
docs/architecture/plans/pi-thin-runtime.md → 存在（architecture/README.md 未引用 pi-thin）
packages/aiplat-pi-runtime/README.md → 存在
docs/README.md「最后更新」行 → 2026-07-18
```

---

## 附录 B. 与 2026-08 目录结构审计的对照（事实）

| 2026-08-19 审计表述 | 2026-10-23 盘点 |
|--------------------|-----------------|
| 根 docs 约 167 md / 25 子目录 | 257 md / 26 顶层子目录 |
| 「蓝图 == 实际顶层目录」已闭环 | `contracts/`、`guides/` 仍未入 DOCUMENT_SYSTEM §一；`verify_doc_structure` 失败 |
| README 计数轻微残留（standards 3、research 14） | 漂移扩大（standards 实 10、research 实 37 等） |
| 未强调 contracts 簇规模 | contracts 为最大簇（43），且已有 README |

对照仅说明时间切片差异，不评价对错，不提出修复步骤。

---

## 附录 C. 盘点之后的仓库变化（事后事实，不改写 §2）

§2 仍以「写入本报告前」为盘点基线。其后同日工作区发生过文档治理改动（不改变 §2 时点语义）：

| 项 | 事后状态（约 2026-10-23 晚） |
|----|------------------------------|
| `DOCUMENT_SYSTEM` 登记 `contracts/`、`guides/` | 已登记；本地 `verify_doc_structure.py` 绿 |
| `docs-verify.yml` 与 structure | 已增加 `verify_doc_structure.py` 步骤 |
| `docs/README` / `architecture/README` | 计数现算 + Pi Thin 入口；五产品仍标非现状 |
| 白书 vol02/04 Pi 粘贴 | 生成器改为摘要+链接后已再生成；`--check` 绿 |
| research→archive | 已迁 3 份收官专项（pipeline / tenant / CI 核实） |
| 根 `README.md` 入门/API 链 | 已改为 `docs/manuals/getting-started.md`、`docs/API/api-reference.md` |
| by-role / contract 中 `core-layer1` 路径 | 已改为 `architecture/core/core-layer1-latest.md` |

本附录只记录变化，不构成新的改造方案。

---

*报告结束。*
