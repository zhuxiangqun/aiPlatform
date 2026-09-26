# S 波 Charter — 商业短板补齐（不是 M4，不是放权）

| 字段 | 值 |
|------|-----|
| 文档 ID | `ORG-S-WAVE-CHARTER-2026-09` |
| 版本 | **v1.0** |
| 日期 | 2026-09-19 |
| 状态 | ☑ **宣布** · S1–S4 |
| 关联 | [`ORG_H_WAVE_CHARTER.md`](./ORG_H_WAVE_CHARTER.md) · [`ORG_M4_SIGNOFF_PACK.md`](./ORG_M4_SIGNOFF_PACK.md) · [`ORG_L5_DECISION_RECORD.md`](./ORG_L5_DECISION_RECORD.md) |
| 决策 | D-S1–D-S4 见 Decision Record §10 |

**纪律**：只补吞吐、基线 ROI、模板开域、签收准备可填。`m4_claim_allowed` 恒 false。H4 仍不写活本体。不自动上架技能。不宣称 L5。

---

## 0. 一句话

把「人批堆死、看不见人时、第二域从零写 YAML、签字栏永远空白」做成可操作的产品能力；真客户签字另宣布。

---

## 1. 范围

| 阶段 | 内容 | 非目标 |
|------|------|--------|
| S1 | OrgPilot 扫队列 + `approval_rules` seed | live 扫；后台强制 cron（可选） |
| S2 | `PUT/GET …/value/baseline` + 试点表单 | 编造基线；跨租户读 |
| S3 | `domain_packs` 安装（alert_triage / data_catalog / work_order）；动作脚手架只写 `org/action_drafts` | harness 硬编码域名；写入 `actions/` 并登记；删旧 ensure_* |
| S4 | `signoff_progress` 值班/双签可填；证据包带入 | 打开 `m4_claim_allowed` |

---

## 2. 宣布用语

> S 波于 2026-09-19 宣布并落地：沙箱可扫 H4 队列、客户可填价值基线、领域模板可安装、签收进度可记录。不是 M4，不是 L5。
