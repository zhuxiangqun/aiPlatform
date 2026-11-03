# EVAL 记分卡 v1（相对 [`SCORE_SCOPE_V1.md`](./SCORE_SCOPE_V1.md)）

> Machine: [`scorecard_v1.json`](./scorecard_v1.json) · Gate: `scripts/scorecard_v1_check.sh`  
> Evidence audit: [`EVIDENCE_AUDIT_V1.md`](./EVIDENCE_AUDIT_V1.md) + [`evidence/evidence_manifest.v1.json`](./evidence/evidence_manifest.v1.json)  
> Honesty: 分值只相对 **首版声明范围**；`accuracy_claim=false` · ≠ 生产授权 · **功能 5 需可审计证据 + 双人真实性确认**

**记录日**：2026-11-04  

| 轴 | 当前分 | 首版 5/5？ | 主要缺口 |
|----|--------|-----------|----------|
| 功能覆盖 | **5.0 / 5** | 是（首版范围 + 证据审计） | manifest SHA256 + 聚合入仓；**双人 attestation=confirmed**；`accuracy_claim=false` |
| 工程架构 | **5.0 / 5** | 是（首版范围） | 单挂+308；薄路由；contracts SSOT；产品根声明；legacy_7dim 永久 report-only |
| 本地独立（不含 microVM） | **5.0 / 5** | 是（首版范围） | SANDBOX_ISOLATION_V0 + OIDC_MINIMAL_V0 + B4S refresh；`sandbox_real_isolation=false`；≠ authorize |
| 本地独立（含 microVM） | **N/A（Mac）** | 不可 | Linux track 策略已落地（见 [`MICROVM_LINUX_TRACK.md`](./MICROVM_LINUX_TRACK.md)）；仍需 Linux/KVM 主机证据；`guest_boot` 延后 |
| 生产独立 | **不计首版** | — | staging + B4-S/B5/B6 |

### 功能 5.0（可审计）

G2b κ≈0.63、preference agreement=0.75/κ≈0.47；聚合见 `docs/a3/evidence/*_aggregate.v1.json`；  
`dual_human_attestation.status=confirmed`（2026-11-04 操作员确认两名真人独立盲填）。  
审计门禁见 [`EVIDENCE_AUDIT_V1.md`](./EVIDENCE_AUDIT_V1.md)。

**仍禁止误读**：功能分 ≠ 准确率；`accuracy_claim=false`；κ/agreement ≠ G2b accuracy 认证。

### 架构 5.0（首版范围）

见 [`ARCH_CONSOLIDATION_V1.md`](./ARCH_CONSOLIDATION_V1.md) + [`PRODUCT_ROOT_V1.md`](./PRODUCT_ROOT_V1.md) + scope §二。  
Central `legacy_7dim` = 永久诚实终态（`deprecated_for_engineering`），**≠** 未完成迁移。

### 本地 5.0（不含 microVM）

见 [`SANDBOX_ISOLATION_V0.md`](./SANDBOX_ISOLATION_V0.md) · [`OIDC_MINIMAL_V0.md`](./OIDC_MINIMAL_V0.md) · [`B4S_LOCAL_REHEARSAL.md`](./B4S_LOCAL_REHEARSAL.md)。  
**≠** `process_split_authorized` · **≠** 隔离认证 · **≠** staging。

### 禁止误读

| 误读 | 正解 |
|------|------|
| JSON 写 5 = 可审计 5 | 否 → 须 manifest + 哈希 + 双人确认 |
| 功能 5 = 评得准 | 否 → 准确另表；κ/agreement ≠ accuracy |
| 本地 5 = 可 authorize | 否 → `process_split_authorized` 仍 false |
| 人评 κ = 可开 accuracy_claim | 否 → 仍须 G2b closeout / 准确率轨 |
| 首版三项 5 = 生产独立 | 否 → 需 staging + B4-S/B5/B6 |
