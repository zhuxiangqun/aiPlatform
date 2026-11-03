# EVAL 记分卡 v1（相对 [`SCORE_SCOPE_V1.md`](./SCORE_SCOPE_V1.md)）

> Machine: [`scorecard_v1.json`](./scorecard_v1.json) · Gate: `scripts/scorecard_v1_check.sh`  
> Honesty: 分值只相对 **首版声明范围**；`accuracy_claim=false` · ≠ 生产授权

**记录日**：2026-11-03  

| 轴 | 当前分 | 首版 5/5？ | 主要缺口 |
|----|--------|-----------|----------|
| 功能覆盖 | **4.0 / 5** | 否 | 真人 preference κ、G2b 双人；合规/PII 未建；覆盖度矩阵未闭环 |
| 工程架构 | **3.5 / 5** | 否 | package vs Central legacy 双路径；产品根/单 API 未收完 |
| 本地独立（不含 microVM） | **4.2 / 5** | 否 | OIDC 最小企业路径弱；B4-S 本机预演可再固化证据；隔离未认证（范围内可接受但未钉满） |
| 本地独立（含 microVM） | **N/A（Mac）** | 不可 | 需 Linux/KVM — 见 scope §三 |
| 生产独立 | **不计首版** | — | staging + B4-S/B5/B6 |

### 功能 4.0 依据（已具备）

- Agent/Skill/Prompt/KB/Arena/code_review P1 路径  
- session v0+v1、S1 fixture + live_llm、preference **fixture** gate、prod_live 骨架 + `llm_ok_n`  
- closeout v2  

### 功能未满 5（必须）

1. 真人 G2b 双标 + κ 证据（[`G2B_PREP.md`](./G2B_PREP.md)）  
2. 真人 preference A/B（[`PREFERENCE_V0.md`](./PREFERENCE_V0.md)）  
3. 合规/PII v0 schema+测试+报告  
4. 维度矩阵行全部 `evidence_ok=true`（见 JSON `dimensions`）  

### 架构 3.5 → 5 清单

见 scope §二；跟踪项在 `scorecard_v1.json` → `architecture.gaps`。

### 本地 4.2 → 5（不含 microVM）清单

见 scope §三 in-scope；`local_independence_no_microvm.gaps`。

### 禁止误读

| 误读 | 正解 |
|------|------|
| 功能 5 = 评得准 | 否 → 准确另表 |
| 本地 5 = 可 authorize | 否 → `process_split_authorized` 仍 false |
| fixture preference = 人评完成 | 否 |
| 3B smoke = 生产基线 | 否 → 须 prod candidate + `llm_ok_n≥1` |
