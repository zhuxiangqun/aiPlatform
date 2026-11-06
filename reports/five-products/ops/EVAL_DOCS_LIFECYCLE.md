# Evaluation 文档生命周期（收口）

> **生效**：2026-11-06  
> **导航入口**：[`modules/evaluation/README.md`](../modules/evaluation/README.md)  
> **原则**：现行定义少而稳；收口凭证进 archive；不解冻/过程纸不再当产品说明。

## 状态标签

| 标签 | 含义 | 读者动作 |
|------|------|----------|
| **living** | 现行产品/模块定义或仍约束行为 | 作为入口与决策依据 |
| **frozen-gate** | 已执行解冻/范围决策，保留效力但不扩写 | 查「当时开了什么」；勿当教程 |
| **evidence** | 收口/签收/阻塞凭证 | 审计追溯；已迁 `_archive/eval-receipts/` |
| **prep** | A3/基准预备稿与门禁说明 | 跑脚本/对照 scope；非对外白皮书 |

## living（维护）

| 文档 | 角色 |
|------|------|
| [`modules/evaluation/README.md`](../modules/evaluation/README.md) | **唯一导航入口** |
| [`modules/evaluation/MODULE.md`](../modules/evaluation/MODULE.md) | 模块边界 |
| [`modules/evaluation/EVAL_PROTOCOL.md`](../modules/evaluation/EVAL_PROTOCOL.md) | 协议 |
| [`EVALUATION_PRODUCT_REVIEW_2026-11-04.md`](./EVALUATION_PRODUCT_REVIEW_2026-11-04.md) | 产品评审基线 |
| [`EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md`](./EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md) | 改进轨道计划 |
| [`EVAL_LOCAL_FIRST_PRIORITY_2026-11-06.md`](./EVAL_LOCAL_FIRST_PRIORITY_2026-11-06.md) | 本机优先策略 |
| [`EVAL_A1_SCOPE_DECISION_LOCAL_SUFFICIENT_2026-11-06.md`](./EVAL_A1_SCOPE_DECISION_LOCAL_SUFFICIENT_2026-11-06.md) | A1 范围裁决 |
| [`EVAL_ARENA_LOCAL_PRODUCT_DECISION_2026-11-06.md`](./EVAL_ARENA_LOCAL_PRODUCT_DECISION_2026-11-06.md) | Arena 产品裁决 |
| [`EVAL_G2B100_PROTOCOL_SIGNED_2026-11-05.md`](./EVAL_G2B100_PROTOCOL_SIGNED_2026-11-05.md) | G2b-100 已签 protocol 指针 |
| [`EVAL_V1_G2A_RUNBOOK.md`](./EVAL_V1_G2A_RUNBOOK.md) | G2a 操作 runbook |
| [`EVAL_OBJECT_CARDS_OWNER_VERIFY.md`](./EVAL_OBJECT_CARDS_OWNER_VERIFY.md) | 对象卡 owner 核对 |
| [`EVAL_P2_CHARTER_2026-11-06.md`](./EVAL_P2_CHARTER_2026-11-06.md) | P2 章程 |
| `packages/aiplat-evaluation/docs/a3/PRODUCT_ROOT_V1.md` | 产品根 |
| `packages/aiplat-evaluation/docs/a3/SCORE_SCOPE_V1.md` | 记分范围 |
| `packages/aiplat-evaluation/docs/a3/SCORECARD_V1.md` | 记分卡 |
| `AIPLAT_CAPABILITIES.md` | 能力事实 |

## frozen-gate（本批已迁 archive；勿扩写）

目录：[`_archive/eval-gates/`](./_archive/eval-gates/)  

含 `ENGINEERING_UNFREEZE_EVAL_*.md`（16 份）。原路径留 **stub**；`ops_engineering_freeze_check.sh` 仍按原路径做存在性检查。

仍留 `ops/` 原位（盘点 / handoff，本批未迁）：`EVAL_V1_E1_INVENTORY.md`、`EVAL_V1_E3_GOLD_SOURCES.md`、`EVAL_P1B_AGENT_HANDOFF.md`。新工作写新 living 决策，不回填这些文件当说明书。

## evidence（已迁 archive）

目录：[`_archive/eval-receipts/`](./_archive/eval-receipts/)  

含 CLOSEOUT / SIGNOFF / PARTIAL / BLOCKED / ACCEPT / EXPAND_READY 等评测收口凭证。原路径留 **stub** 指到 archive，避免断链。

## prep（A3 目录）

`packages/aiplat-evaluation/docs/a3/`：门禁、基准协议、证据清单。入口横幅已标明「非白皮书」。对外叙事仍走平台 `docs/whitepaper/volumes/01|02`。

## 明确不存在

- 仓库内**没有**「评测产品技术白皮书」「评测产品产品白皮书」成对专册。
- 勿把 ops 收口稿或 a3 预备稿误称为白皮书。

## 后续批次（未做）

- a3 内已收官单点协议降权为索引-only（保留脚本引用路径）
- 可选：迁 `EVAL_V1_E1_INVENTORY` / `E3_GOLD_SOURCES` / `P1B_AGENT_HANDOFF`（先做入链普查）
