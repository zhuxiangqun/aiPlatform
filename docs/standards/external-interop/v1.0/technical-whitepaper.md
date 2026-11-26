---
doc_type: Standard
status: active
authority: canonical
doc_id: EXT_INTEROP_V10_WHITEPAPER
purpose: 定义 aiPlat 外援互通 v1.0 目标架构与强制要求
scope_in: 外部资产类型、兼容层级、导入/适配/认证、安全边界、符合性（附录 N）
scope_out: 具体供应商 SLA、业务域内容、把「能 import」当成「已互通」
owner: 朱向群
version: 1.0.0
last_reviewed: 2026-11-26
review_cycle: 90d
---
# aiPlat 外援互通技术白皮书 v1.0

> **版本**：v1.0.0 · 2026-11-26  
> **状态**：已批准；**2026-12-01 生效**  
> **性质**：技术标准（`authority: canonical`）  
> **构成**：正文 + 规范性附录 + `schemas/`  
> **批准**：`ADR-EXT-INTEROP-v1.0-2026-11-26.md`  
> **诚实边界**：标准批准 ≠ 实现 certified；禁止无证据跨层宣称。

---

## 标准声明

效力 / 构成 / 冲突裁决同评测系统白皮书（草案 → 批准 → 符合性单独认证）。

---

## 文档地图

| 正文 | 内容 | 附录 |
|---|---|---|
| 0–2 | 概览、痛点、原则 | — |
| 3 | 架构与资产类型 | A/B |
| 4 | 兼容层级 L0–L2 | C |
| 5 | 导入与适配流水线 | D |
| 6 | 契约与 Schema | E |
| 7 | 安全 / 权限 / 沙箱 | F |
| 8 | 观测与审计 | G |
| 9 | 与评测 / FDE / 知识关系 | H |
| 10 | 路线图 | — |
| 11 | 迁移 | — |
| 12 | 符合性认证 | N |
| 13 | 实施参考 | — |
| 14 | 结论 | — |

---

## 0. 先看一页

外援互通要解决的不是「能把包解压进来」，而是：

> **外部 Agent / Skill / Tool / MCP / Prompt 包，在明确兼容层上可导入、可适配、可审计、可门禁。**

失败模式：

- **能 import 就宣称已互通**；
- **跳过 L0 直接谈语义对齐**；
- **绕过 PolicyGate 直调外部工具**；
- **把供应商 demo 当成生产授权**。

目标链路：

> **资产声明 → 兼容层判定 → 适配 → 权限沙箱 → 观测 →（评测门禁）→ 可选生产 authorize。**

---

## 1. 痛点（摘要）

1. 格式碎片（多源包无统一 manifest）；  
2. 兼容层口头约定、无机器判定；  
3. 导入成功但运行时权限/租户丢失；  
4. MCP/Tool 与内部 Skill 边界模糊；  
5. 无审计轨迹仍对外「已对接」。

---

## 2. 原则

| # | 原则 |
|---|---|
| 1 | **分层诚实**：L0 语法 → L1 运行 → L2 语义；禁止跳级宣称 |
| 2 | **权限不降级**：外援调用 MUST 经 PolicyGate / 既有 syscall |
| 3 | **导入 ≠ 认证**：compat_tier 与 certified 分字段 |

---

## 3. 架构与资产类型

### 3.1 逻辑分层

```text
Catalog        外援资产目录 / 版本 / 来源
Adapter        格式适配 / 字段映射
Runtime Bridge Tool/MCP/Skill 桥接到平台 syscall
Policy         沙箱 / 配额 / 租户
Evidence       导入报告 / 兼容判定 / 审计
```

### 3.2 资产类型（v1.0）

MUST 定义契约：`agent_pack`、`skill_pack`、`tool_spec`、`mcp_server`、`prompt_pack`。  
未知类型 MUST 拒绝或标 `compat=unknown`（禁止静默当 L2）。

---

## 4. 兼容层级 L0–L2

| 层 | 含义 | 可宣称 |
|---|---|---|
| L0 | 清单/Schema 可解析 | 可导入（语法） |
| L1 | 在平台沙箱可调用 | 可运行（运行） |
| L2 | 语义字段/协议对齐 + 评测探针可选通过 | 可互通（语义） |

升级规则：MUST 先满足下层；评测通过不自动升 L2（须显式判定记录）。

---

## 5. 导入与适配

- Manifest MUST 含 `source`、`version`、`compat_claim`、`checksum`；
- 适配失败 MUST fail closed（禁止半导入）；
- 适配器 MUST NOT 硬编码业务 Agent 名做分支（配置驱动）。

---

## 6. 契约与 Schema

字段权威见附录 E；`schemas/` 定稿后与附录同步。

---

## 7. 安全

- 外援默认最小权限；
- 网络/文件/密钥能力 MUST 显式声明；
- admin 级外援操作遵循平台 MFA 等既有治理。

---

## 8. 观测与审计

- 每次导入/升级 MUST 写审计事件；
- 运行时调用 MUST 可追溯到 `asset_id` + `compat_tier`。

---

## 9. 与其他系统

| 系统 | 关系 |
|---|---|
| 评测 | L1+ 资产可进 Tool/MCP subject；评测通过 ≠ L2 自动授予 |
| FDE | 客户外援交付走 FDE 签收；工程互通走本标准 |
| 知识 | 外援文档可 ingest，但 Wiki 不是外援权威源 |

---

## 10–11. 路线图与迁移

```text
Draft → Core（L0/L1 + 审计 + Policy）
     → Extended（L2 判定 + 目录 UX）
     → Operational（生产 authorize / 供应商 SLA）
```

旧 ad-hoc 导入脚本 → Adapter 注册表；并行第二套导入 API MUST NOT 新增。

---

## 12. 符合性认证

附录 N；`exists` ≠ `certified`。

---

## 13. 实施参考

`docs/architecture/plans/external-interop-v1.0-implementation-plan.md`。

---

## 14. 结论

外援互通标准把「能装进来」与「能安全、分层、可证地互通」拆开；跳级宣称一律不合规。
