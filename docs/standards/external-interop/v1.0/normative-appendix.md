---
doc_type: Standard
status: active
authority: canonical
doc_id: EXT_INTEROP_V10_APPENDIX
purpose: 外援互通 v1.0 规范性附录
scope_in: 附录 A–H、N；兼容层与错误码
scope_out: 实现状态声明
owner: 朱向群
version: 1.0.0
last_reviewed: 2026-11-26
review_cycle: 90d
---
# aiPlat 外援互通规范性附录 v1.0

> 配套白皮书；与正文同等效力（2026-12-01 起）。用语 MUST / MUST NOT / SHOULD / MAY。  
> 机读：`schemas/external-interop.v1.0.schema.json` + `conformance-checklist.yaml`。

## 附录地图

| 小节 | 内容 |
|---|---|
| 0 | 约定 |
| A | 架构对象 |
| B | 资产类型 |
| C | 兼容层 L0–L2 |
| D | 导入流水线 |
| E | Manifest / Schema 字段 |
| F | 安全 |
| G | 审计 |
| H | 与评测/FDE |
| N | Conformance Checklist |

---

## 0. 约定

同评测附录 0（大小写、扩展 `x-`、RFC3339、SemVer 兼容）。

---

## A. 架构对象

| 对象 | MUST |
|---|---|
| ExternalAsset | 带 id/version/source/checksum |
| CompatVerdict | 显式 L0/L1/L2/unknown |
| Adapter | 注册表可发现 |
| ImportReport | fail closed 可复现 |

---

## B. 资产类型

```text
asset_kind: agent_pack | skill_pack | tool_spec | mcp_server | prompt_pack
```

未知 kind：MUST `compat=unknown` 或拒绝；MUST NOT 静默按 L2 处理。

---

## C. 兼容层

| 字段 | 规则 |
|---|---|
| `compat_tier` | `L0` \| `L1` \| `L2` \| `unknown` |
| `compat_evidence_refs[]` | L1+ MUST 非空 |
| `claimed_tier` vs `verified_tier` | 分离；宣称 > 验证 MUST 拒升 |

升级：L0→L1→L2 单向；降级须写审计原因。

### C.1 实现 tier ↔ 标准层映射（机读权威：`asset_compat._IMPL_TIER_TO_LEVEL`）

| 实现 `tier` | 标准 `verified_tier` | 说明 |
|---|---|---|
| `blocked` | `unknown` | 不可用 |
| `needs_handler` / `needs_binding` / `needs_impl` / `schema_only` / `connectable` | `L0` | 可解析/清单级，不可默认可调度 |
| `prompt_ready` / `handler_ready` / `tool_mapped` / `persona_ready` / `bound_ready` / `mapped` / `connected` / `gated` | `L1` | 可运行（须 `schedulable`） |
| （仅当 `semantic_probe_passed=true` 且 L1+schedulable） | `L2` | 禁止自动升 L2 |

`compat_tier` 对外权威 = `verified_tier`；`claimed_tier` > `verified_tier` → `interop.tier_claim_illegal`。

---

## D. 导入流水线

步骤（顺序 MUST）：

1. 校验 checksum / 签名（若声明）；  
2. 解析 manifest（L0）；  
3. 适配映射；  
4. 沙箱试调用（L1，若目标 ≥L1）；  
5. 可选语义探针（L2）；  
6. 写 ImportReport + 审计。

任一步失败：MUST NOT 标记为更高 tier。

### 错误码（最小集）

| code | 含义 |
|---|---|
| `interop.manifest_invalid` | Manifest 不合规 |
| `interop.checksum_mismatch` | 校验失败 |
| `interop.adapter_missing` | 无适配器 |
| `interop.tier_claim_illegal` | 跳级宣称 |
| `interop.policy_denied` | PolicyGate 拒绝 |
| `interop.half_import_forbidden` | 半导入禁止 |

---

## E. Manifest 最小字段

| 字段 | MUST |
|---|---|
| `asset_id` | 是 |
| `asset_kind` | 是 |
| `version` | 是 |
| `source` | 是 |
| `checksum` | 是 |
| `compat_claim` | 是（可低于 verified） |
| `capabilities[]` | L1+ 是 |
| `tenant_scope` | 是（或显式 global+授权） |

---

## F. 安全

- 能力未声明 MUST 视为无该能力；
- 外援 MUST NOT 绕过 `sys_tool_call` / `sys_skill_call` PolicyGate；
- 密钥 MUST NOT 写入资产包明文（引用密钥库）。

---

## G. 审计

ImportReport MUST 含：`asset_id`、`verified_tier`、`actor`、`tenant_id`、`timestamp`、`evidence_refs`。

---

## H. 与评测 / FDE

- 评测 subject 引用外援时 MUST 带 `verified_tier`；
- FDE 交付外援 MUST 另有签收记录；不得用 ImportReport 代替客户签收。

---

## N. Conformance Checklist

| ID | 等级 | 项 | Core |
|---|---|---|---|
| X01 | Core | Manifest + checksum 校验 | MUST |
| X02 | Core | L0 解析 fail closed | MUST |
| X03 | Core | claimed/verified tier 分离 | MUST |
| X04 | Core | PolicyGate 不绕过 | MUST |
| X05 | Core | ImportReport + 审计 | MUST |
| X06 | Core | 半导入禁止 | MUST |
| X07 | Extended | L1 沙箱试调用 | SHOULD |
| X08 | Extended | L2 语义探针 + 显式判定 | SHOULD |
| X09 | Extended | 资产目录 UX | SHOULD |
| X10 | Operational | 生产 authorize | MAY |
| X11 | Operational | 供应商 SLA 绑定 | MAY |

`core_ready` = X01–X06；`certified` 须非作者批准 + 证据。

### N.1 代码证据快照（2026-11-26 · 测量，非认证）

权威测量报告：`reports/products/external-interop/v1.0/core-gap-evidence.md`。

| ID | 测量状态 | 一句话 |
|---|---|---|
| X01 | exists | `compute_asset_tree_checksum` + finalize 写 manifest.checksum |
| X02 | exists | `_read_skill_manifest` fail-closed → `interop.manifest_invalid` |
| X03 | exists | claimed/verified 分离；跳级 → tier_claim_illegal |
| X04 | exists | sys_skill_call / sys_tool_call 经 PolicyGate + COMPAT 门 |
| X05 | exists | `wrap_install_report` + install_report schema |
| X06 | exists | half_import / 跳级宣称 → import_failed |
| X07 | exists | `run_l1_sandbox_trial` 静态试跑 + `compat_evidence_refs` |
| X08 | exists | `set_semantic_probe_result` 显式探针；禁自动升 L2 |
| X09 | exists | `build_interop_asset_catalog` + Workspace 四列表 claimed/verified tip |
| X10 | exists | `evaluate_interop_production_authorize`；**authorized=true**（朱莹 pilot） |
| X11 | exists | `bind_supplier_sla`；**bound=true**（须批准 + `sla_ref`/`vendor_id`） |

**测量：Core/Extended/Operational 项均为 exists。**  
**徽章（2026-11-26 clause-sync）**：conditional `core_ready`（朱鸿林）+ `extended_ready`（朱莹）；X10–X11 → `operational_ready`。`certified`：**否**（≠ L2 auto-grant）。  
§C.1 映射表已补；L2 仅 `semantic_probe_passed`。  
证据：`core|extended|operational-gap-evidence.md` + `*-approval-record.approved.json`。
