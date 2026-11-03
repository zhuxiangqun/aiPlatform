# EVAL 记分卡 v1（相对 [`SCORE_SCOPE_V1.md`](./SCORE_SCOPE_V1.md)）

> Machine: [`scorecard_v1.json`](./scorecard_v1.json) · Gate: `scripts/scorecard_v1_check.sh`  
> Honesty: 分值只相对 **首版声明范围**；`accuracy_claim=false` · ≠ 生产授权

**记录日**：2026-11-03  

| 轴 | 当前分 | 首版 5/5？ | 主要缺口 |
|----|--------|-----------|----------|
| 功能覆盖 | **4.3 / 5** | 否 | 真人 preference κ、G2b 双人；覆盖度矩阵未闭环（compliance_pii 已建） |
| 工程架构 | **5.0 / 5** | 是（首版范围） | 单挂+308；薄路由；contracts SSOT；产品根声明；legacy_7dim 永久 report-only |
| 本地独立（不含 microVM） | **5.0 / 5** | 是（首版范围） | SANDBOX_ISOLATION_V0 + OIDC_MINIMAL_V0 + B4S refresh；`sandbox_real_isolation=false`；≠ authorize |
| 本地独立（含 microVM） | **N/A（Mac）** | 不可 | 需 Linux/KVM — 见 scope §三 |
| 生产独立 | **不计首版** | — | staging + B4-S/B5/B6 |

### 功能 4.3 依据（已具备）

- Agent/Skill/Prompt/KB/Arena/code_review P1 路径  
- session v0+v1、S1 fixture + live_llm、preference **fixture** gate、prod_live 骨架 + `llm_ok_n`  
- closeout v2  
- 合规/PII v0（[`COMPLIANCE_PII_V0.md`](./COMPLIANCE_PII_V0.md)；启发式；`certified=false`）  

### 功能未满 5（必须）

1. 真人 G2b 双标 + κ 证据（[`G2B_PREP.md`](./G2B_PREP.md)）  
2. 真人 preference A/B（[`PREFERENCE_V0.md`](./PREFERENCE_V0.md)）  
3. 维度矩阵行全部 `evidence_ok=true`（见 JSON `dimensions`；人评两行仍 false）  

### 架构 5.0（首版范围）

见 [`ARCH_CONSOLIDATION_V1.md`](./ARCH_CONSOLIDATION_V1.md) + [`PRODUCT_ROOT_V1.md`](./PRODUCT_ROOT_V1.md) + scope §二。  
完成：单挂、308、薄路由、contracts SSOT、CODEOWNERS、`release:check`、产品根声明。  
Central `legacy_7dim` = 永久诚实终态（`deprecated_for_engineering`），**≠** 未完成迁移。

### 本地 5.0（不含 microVM）

见 [`SANDBOX_ISOLATION_V0.md`](./SANDBOX_ISOLATION_V0.md) · [`OIDC_MINIMAL_V0.md`](./OIDC_MINIMAL_V0.md) · [`B4S_LOCAL_REHEARSAL.md`](./B4S_LOCAL_REHEARSAL.md)。  
**≠** `process_split_authorized` · **≠** 隔离认证 · **≠** staging。

### 禁止误读

| 误读 | 正解 |
|------|------|
| 功能 5 = 评得准 | 否 → 准确另表 |
| 本地 5 = 可 authorize | 否 → `process_split_authorized` 仍 false |
| fixture preference = 人评完成 | 否 |
| 3B smoke = 生产基线 | 否 → 须 prod candidate + `llm_ok_n≥1` |
