# ADR-09 前置联签 + 停泊（2026-10-26；第 3 步 E4 已另批）

- **效力**：架构决策 owner × 业务场景 owner（兼任 · 本仓库维护者）书面选择  
- **结论**：**ADR-09 本体仍停泊 Proposed** — **不** Accepted；**不**全拆落地  
- **第 3 步例外**：对外 E4（窄）已批 — `ADR09_E4_STEP3_DECISION.md`（翻宣传拒签；边界内文案）

## 为何选这条（相对其它选项）

| 选项 | 判定 |
|------|------|
| 直接 ADR-09 Accepted / 五产品全拆 | ❌ 仍过早：无独立 7×24；扩缩容仍 ⬜ |
| 对外 E4（窄） | ✅ **第 3 步已批** — 见 STEP3_DECISION |
| compose 长驻诊断微服务 | ❌ 仍不批 |
| 换线做其它仓务 | 全拆停泊后允许 |

**默认生产路径继续**：ADR-08 Pi Thin 试点 + ADR-10 诊断 MVP；对外措辞上限见 `ADR09_E4_COPY_DRAFT.md`。

## 联签范围（更新）

| # | 签什么 | 不签什么 |
|---|--------|----------|
| 3 | 知情接受「无独立 7×24、维持兼任 on-call」；宣传 E4 已翻签 | 不因此批准全拆 |
| 4 | 确认「可说/禁止说」边界；**批准边界内对外发布** | 不批准超边界承诺 / 交付日 SLA |
| 5 | CLEAN_ENV PASS 可作**对外验收证据引用**（非 SLA） | 不作 7×24 / 全量产品化证明 |

签字落点：`ADR09_ROLES_ONCALL_CONFIRM.md` · `ADR09_E4_COPY_DRAFT.md` · `ADR09_E4_CLEAN_ENV_NOTE.md` · `ADR09_E4_STEP3_DECISION.md`。

## 再开条件（全拆 · 须另批）

详见 `ADR09_DEFER_FULL_SPLIT_E4_PROD.md`。本页本身 **不是** ADR-09 Accepted。
