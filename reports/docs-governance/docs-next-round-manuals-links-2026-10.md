---
doc_type: Design
authority: plan
scope: docs-next-round-manuals-links
language: zh-CN
status: closed
draft_date: 2026-10-23
revised: 2026-10-23-e4
approved_batches: [E0, E1, E2, E3, E4]
predecessor: docs-reasonable-reduction-plan-2026-10（D0–D5 已收口）
---

# 下一轮：manuals 责任分型 + 维护区链接门禁扩面（2026-10）

> **性质**：已收口方案（E0–E4）。#379 已合入；exemption 拆除见合入后独立提交。  
> **前提**：责任导向 D0–D5 已收口；过程材料在 `reports/docs-governance/`。  
> **仍不追求配额减量**；删除仅当 Q1=无且 R5=无义务。

---

## 0. 目标

1. **`docs/manuals/`**：按责任分型整理索引（现行操作 / 专题合册 / 过程或过期），避免与 contracts 过程纸混读。  
2. **链接门禁**：把 `verify_doc_links.py` 从「仅 3 个入口文件」扩到 **维护区 README + 入口链一层**（仍非全站；archive 可 WARN）。  
3. **运维债**：PR #379 合并后拆除 `ex-2026-10-docs-cleanup-c0-c4`（见 §4）。

非目标：子仓 `*/docs` 搬迁；`verify_docs.py` 菜单假阳性全清；整簇删 manuals。

---

## 1. 批次（批准后执行）

| 批次 | 内容 | 责任向验收 |
|------|------|------------|
| **E0** | 批准本方案；冻结 manuals 分型表与链接覆盖名单 | `status→approved` |
| **E1** | `manuals/README` 分型（现行 / 专题 / 降权）；逐篇三问仅对「疑似过程/过期」 | 索引可指认三类；默认不迁不删 |
| **E2** | 扩 `verify_doc_links.py`：维护区各簇 `README.md` + `docs/README` 已链到的维护区文件；`archive/**` 默认 WARN | CI Docs Verify 仍绿；broken 维护区链接 = fail |
| **E3** | 修 E2 新暴露的维护区断链（修链优先） | broken maint = 0 |
| **E4** | 收口：更新 `docs/README` 时点；本方案迁入 `reports/docs-governance/` | §0.7 清单对齐 |

复核记录落点：续写本目录短表或 disposition CSV；**禁止**再往 `docs/research/` 堆过程纸。

---

## 2. 链接扩面边界（E2 冻结候选）

**必检（fail）**

- 现有 3 文件：`DOCUMENT_SYSTEM.md`、`docs/README.md`、`manuals/README.md`
- `docs/**/README.md` 且路径**不**含 `archive` / `_archive`
- `reports/docs-governance/README.md`（治理索引）

**可选二期（本方案 E2 不做）**

- 维护区全部 `.md` 正文链接
- archive 内链接升为 fail

**解析规则**：沿用现脚本（相对文件目录 / workspace / 子仓 docs）。

---

## 3. manuals 分型（E1 · 已执行）

以 `docs/manuals/README.md` 为权威索引（三类分区已落地）。复核表：[`e1-manuals-typing-2026-10-23.md`](./e1-manuals-typing-2026-10-23.md)。

| 标签 | 含义 | 默认 |
|------|------|------|
| 现行操作 | 用户/运维仍按步骤执行 | 维护区主列表 |
| 专题合册 | 长手册/合订，仍为权威入口 | 「合册」区 |
| 过程/过期 | 分析快照 / `_archive` / 签收指针 | 降权；本批不迁不删 |

禁止按「FDE / 知识」主题整簇处置。

---

## 3.1 执行记录（2026-10-23）

| 项 | 结果 |
|----|------|
| E0 | 本方案 approved |
| E1 | manuals README 三分型；wiki-fts5 / fde/_archive / M4 指针降权 |
| E2 | `verify_doc_links` fail=26 warn=1；见 `e2-link-gate-expand-2026-10-23.md` |
| E3 | 7 断链全部修链；fail broken=0；见 `e3-maint-link-fixes-2026-10-23.md` |
| 迁/删 | **0 / 0**（E1–E3） |
| E4 | 收口：`docs/README` 时点；本方案 `closed`；见 `e4-closeout-2026-10-23.md` |

---

## 4. physical exemption（与本方案并行 · 合并后）

| 项 | 约定 |
|----|------|
| 现状 | **已拆除**（#379 合入后；`exemptions: []`） |
| 时机 | ✅ #379 合入后执行 |
| 动作 | 从 `physical_merge_gates.yaml` 删除该条；`check_physical_merge_gates.py --base origin/main` 无 exemption 且 OK |
| 若仍 inflation | 不得再加 `paths: ["**"]`；改为证明净增来自合理 docs 或拆更小 PR |

---

## 5. 后续

**E0–E4 已收口；#379 已合入；physical exemption 已拆除（§4）。**

---

*版本: 2026-10-23-e4-postmerge · **closed** · exemption cleared*