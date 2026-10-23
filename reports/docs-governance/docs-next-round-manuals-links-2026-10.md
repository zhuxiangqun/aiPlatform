---
doc_type: Design
authority: plan
scope: docs-next-round-manuals-links
language: zh-CN
status: draft
draft_date: 2026-10-23
predecessor: docs-reasonable-reduction-plan-2026-10（D0–D5 已收口）
---

# 下一轮：manuals 责任分型 + 维护区链接门禁扩面（2026-10）

> **性质**：方案草案；**未批准执行**。  
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

## 3. manuals 分型（E1 输入 · 未复核）

以 `docs/manuals/README.md` 现有清单为起点，执行时对每条标：

| 标签 | 含义 | 默认 |
|------|------|------|
| 现行操作 | 用户/运维仍按步骤执行 | 维护区主列表 |
| 专题合册 | 长手册/合订，仍为权威入口 | 主列表或「合册」区 |
| 过程/过期 | 已接替或一次性 | 降权；有义务→留路径；无义务→可迁 archive |

禁止按「FDE / 知识」主题整簇处置。

---

## 4. physical exemption（与本方案并行 · 合并后）

| 项 | 约定 |
|----|------|
| 现状 | `ex-2026-10-docs-cleanup-c0-c4`，`expires: 2026-11-06`，`paths: ["**"]` |
| 时机 | **#379 合入 main 之后**再拆（合入前拆除会导致相对 `origin/main` 的 inflation 误伤本 PR） |
| 动作 | 从 `physical_merge_gates.yaml` 删除该条；跑 `check_physical_merge_gates.py --base origin/main` 须无 exemption 且 OK |
| 若仍 inflation | 不得再加 `paths: ["**"]`；改为证明净增来自合理 docs 或拆更小 PR |

---

## 5. 建议首批批准

推荐 **E0 + E1**（manuals 索引分型，低风险），随后 **E2+E3**（链接扩面 + 修链）。  
exemption 拆除作为合并后独立小提交，不阻塞 E0。

---

*版本: 2026-10-23-r0 · **未批准执行***
