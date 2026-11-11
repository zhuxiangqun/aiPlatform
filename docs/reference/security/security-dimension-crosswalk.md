# 安全质量维度 Crosswalk：26 维 ↔ v3 20 维

> 机器可读 SoT：[`reports/security/security_quality_dimensions.yaml`](../../../reports/security/security_quality_dimensions.yaml)
> v3 证据矩阵：[`reports/security/aiplat-security-quality-report-2026-11-09-v3.md`](../../../reports/security/aiplat-security-quality-report-2026-11-09-v3.md) §4
> **唯一真相源是 YAML**；本表仅对账。≠ 认证。
> `dimension_set_version=1.1`：追加 **D26**（成果物 authz）；**未重排** D07–D25。v3#6 拆为 D06（平台）+ D26（成果物）。

| 26 维 ID | 名称 | v3 20 维 ID | 关系 |
|---|---|---|---|
| D01 | 安全治理与威胁建模 | 1 | equal |
| D02 | 安全需求与验收标准 | 2 | equal |
| D03 | 独立验证与红队 | 3 | equal |
| D04 | 认证与合规映射 | 4 | equal |
| D05 | 身份认证 | 5 | equal |
| D06 | 平台授权与最小权限 | 6 | split_platform |
| D26 | 成果物 authz / IDOR / SSRF | 6 | split_artifact |
| D07 | 租户/数据隔离 | 7 | equal |
| D08 | 隐私与数据生命周期 | 8 | equal |
| D09 | 密钥与凭据 | 9 | equal |
| D10 | 审计与不可否认 | 10 | equal |
| D11 | 输入信任 / Prompt Injection | 11 | equal |
| D12 | 输出处理 / 下游注入 | 12 | equal |
| D13 | 模型与系统提示安全 | 13 | equal |
| D14 | 工具 / Agent 过度代理 | 14 | equal |
| D15 | 记忆 / RAG / 上下文投毒 | 15 | equal |
| D16 | 多 Agent 信任 | 16 | equal |
| D17 | 安全评测与红队（分威胁族） | — | **new**（评测仪器；扩展而非替代 v3#3） |
| D18 | 沙箱 / 隔离 / 网络出口 | 17 | equal |
| D19 | 供应链 / 制品完整性 | 18 | equal |
| D20 | 安全编码 / 成果物质量 | 19 | equal |
| D21 | 可用性 / 资源滥用 | — | **new** |
| D22 | 人因 / 审批 UX / 透明度 | — | **new** |
| D23 | 事件响应 / 回滚 | 20 | equal |
| D24 | 配置安全 / fail-closed | — | **new**（从授权/配置运营拆出） |
| D25 | 数据驻留 / 法务 | — | **new** |

## 对账规则

- v3 的 1–5、7–16、17–20 必须在上表有且仅有一条 `equal` 映射。
- v3#6 由 `split_platform`（D06）+ `split_artifact`（D26）共同覆盖；禁止把 D26 当成 D07 重排。
- `new` 行 `v3_id: null`；不得把 new 维假装成已在 v3 验收。
- 状态以 YAML `status` / 证据 `level` 为准，不以本 Markdown 为准。
