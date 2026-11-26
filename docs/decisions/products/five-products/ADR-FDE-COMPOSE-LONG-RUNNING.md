---
doc_type: Decision
doc_id: ADR-FDE-COMPOSE-LONG-RUNNING
status: accepted
authority: decision
created: 2026-11-26
last_reviewed: 2026-11-26
accepted_at: 2026-11-26
language: zh-CN
purpose: FDE 可选 compose 长驻专项决定（F11 adr_ref）；不扩大 ADR-09 E4
---

# ADR — FDE compose 长驻（可选运维 profile）

- **状态**：**Accepted（窄）** · 2026-11-26  
- **关联**：`ADR09_NEXT_FDE_DECISION.md`（FDE 批立时 **不含** compose 长驻；本 ADR 覆盖该「不含」）；`ADR09_COMPOSE_LONG_RUNNING_DECISION.md`（通用长驻轨已含，本 ADR 补 FDE 产品行）；FDE 系统标准 v1.0 附录 N **F11**  
- **目标**：允许 F11 批准记录引用本文件路径作为 `adr_ref`，使 `evaluate_fde_compose_long_running_authorize` 可 `authorized=true`（须非作者批准 JSON）

## 批准句（Accepted）

> 批准 **FDE compose 长驻**（可选 profile）。范围：仅 FDE 交付面可选长驻 compose；**不含**强制生产默认、超边界 E4、第二 Identity/PolicyGate、一次五产品长驻。

## 授权 / 禁止

| 项 | |
|----|--|
| ✅ | 为 FDE 提供**正式可选** compose 长驻 profile（显式 `up -d` + 文档化停机） |
| ✅ | 回滚默认：`docker compose … down -v`；切回共部署 / one-shot health |
| ✅ | 与 `scripts/adr09_fde_optional_health_*` one-shot 路径并存，不覆盖 |
| ❌ | 强制全环境生产默认从共部署/one-shot 改为长驻 |
| ❌ | 超边界 E4 / SLA 生产承诺 |
| ❌ | 借机拆第二套签收系统或改 ADR-02 Identity |

## 与既有关系

| 既有 | 关系 |
|------|------|
| `ADR09_NEXT_FDE_DECISION` | 当时 **不含** 长驻；本 ADR 为后续专项，**Accepted 后覆盖**该「不含」 |
| `ADR09_COMPOSE_LONG_RUNNING_*` | 通用轨已落地 **Pi Thin**；本 ADR 补 **FDE** 产品行，不一次写满五套 |
| `ADR-FDE-SYS-v1.0` | 标准包批准 ≠ 本部署授权 |
| F10 | 生产独立进程 authorize 独立；本 ADR 不替代 F10 |

## 落地序

1. BOUNDARY：FDE 长驻 compose + 启停/回滚 README → **已完成**（`compose.fde-long-running.yml`；`ADR09_*_BOUNDARY` 序 D）  
2. 烟测：`up -d` → health → `down -v` → **已完成**（`scripts/adr09_compose_fde_long_running_smoke.sh`）  
3. 非作者批准记录：`gate_ids` 含 `F11`，`adr_ref` = 本文件 → **已完成**  
4. 刷新 `reports/products/fde-system/v1.0/operational-gap-evidence.md` → **已完成**

## 签署

| 角色 | 姓名 | 状态 |
|------|------|------|
| 架构 / 业务 | 对话「批准 F11」· 2026-11-26 | **Accepted** |
| Data Governance（非作者） | 朱莹 | **Confirmed**（批准 JSON） |
| Security（建议） | 朱鸿林 | 可选复核；不阻断 F11 authorize |

**诚实锁**：Accepted + 非作者批准 JSON + `adr_ref` → `F11 authorized` 可 true；仍 ≠ `certified`；≠ 强制生产默认；≠ E4。
