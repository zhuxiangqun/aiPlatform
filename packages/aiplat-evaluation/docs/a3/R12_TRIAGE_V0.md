---
doc_type: Reference
---

# R12 · 对账差异分诊（v0）

> 源：[`R12_CAPABILITY_RECONCILIATION.md`](./R12_CAPABILITY_RECONCILIATION.md) · JSON evidence  
> 范围：tranche-1 `evaluation-system`（667 条差异，多为 open）  
> Honesty：分诊 ≠ 已清零；清零前禁止宣称「全平台覆盖完成」

---

## 1. 数量快照

| 类型 | 数量 |
|---|---:|
| registry 有、CAPABILITIES 无 | 611 |
| CAPABILITIES eval 样词有、本域 registry 无 | 56 |
| 合计 | 667 |

registry_only 主要落在：

| 桶 | 约数 | 含义 |
|---|---:|---|
| `aiPlat-core/core/apps/eval/**` | ~408 | 评测服务实现面（含 Error 类型/内部 helper） |
| `core/api/core_facade.py` re-export | ~177 | 门面透传符号，非独立能力 |
| `core/harness/evaluation/**` | ~12 | harness 评测组件 |
| 其他 | 少数 | 脚本/前端/杂项 |

---

## 2. 分诊规则（执行）

| 类别 ID | 判定 | 默认处置 | 阻断 Tier A？ |
|---|---|---|---|
| **H1** | 对外宣称 / 发布门禁 / 安全相关 public API | 补 `AIPLAT_CAPABILITIES.md` 行 + 保持 registry | 是（缺则不得升 A） |
| **H2** | CoreFacade 纯 re-export / `*Error` / 私有 helper | 豁免：`human_view_exempt` + 到期日（默认 +90d） | 否 |
| **H3** | 文档/ADR/面板文件名误进 join（cap_only） | 降为非能力叙述；从对账分子剔除 | 否 |
| **H4** | 包内脚本 / 一次性工具 | 豁免或移出 provides | 否 |
| **H5** | 真实缺口：人类视图有、registry 无的可调用能力 | 补 registry `provides` 或删夸大文档 | 视宣称 |

---

## 3. 本轮建议动作（不改 registry  bulk）

1. **冻结 join 口径**：下一版 r12 脚本对 `*Error`、纯 re-export、`.md`/`.tsx` 文件名默认进 H2/H3，减少噪声。  
2. **H1 候选白名单**：从 `in_both`（27）+ 显式对外 API 起步建 Tier 矩阵，不从 611 全量开干。  
3. **cap_only 56**：批量标 H3（ADR/面板/文档），不进 registry。  
4. **到期**：H2/H4 豁免统一到期 **2027-02-14**；到期未复核 → 重新 open。

---

## 4. Owner

| 角色 | 职责 |
|---|---|
| 评测 owner | 批 H1 白名单；签豁免到期 |
| 平台文档 | H3 文档降级措辞 |
| 工程 | r12 脚本噪声过滤（下一 commit） |

---

## 5. 退出标准（tranche-1 清零）

```text
H1：0 open
H2/H4：全部有豁免+到期日或已登记人类视图
H3/H5：已处置
报表：按 H1–H5 分列，禁止只报一个覆盖%
```
