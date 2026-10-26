# ADR-09 前置联签 + 停泊（更新 · 第 4 步窄 Accepted）

- **效力**：架构决策 owner × 业务场景 owner（兼任 · 本仓库维护者）  
- **结论**：前置 #3–#5 联签仍有效；**ADR-09 已 Accepted（仅诊断 MVP）** — `ADR09_STEP4_DECISION.md`  
- **仍停泊**：其余四产品全拆；compose 长驻；控制面拆库

## 状态一览

| 选项 | 判定 |
|------|------|
| ADR-09 Accepted · 诊断 MVP 单产品 | ✅ 第 4 步 |
| 五产品一次全拆 | ❌ |
| 对外 E4（窄） | ✅ 第 3 步 |
| compose 长驻 | ❌ |

**默认路径**：ADR-08 Pi Thin + ADR-10 诊断 MVP；诊断独立部署须分 PR 落地（见 STEP4_DECISION 后续）。对外措辞上限见 `ADR09_E4_COPY_DRAFT.md`。

本页保留前置签字指针：`ADR09_ROLES_ONCALL_CONFIRM.md` · `ADR09_E4_*` · `ADR09_STEP3/4_DECISION.md`。
