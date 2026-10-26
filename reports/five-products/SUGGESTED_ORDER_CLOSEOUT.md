# 建议顺序主轨收口（诊断 MVP）

- **状态**：**主轨已收口** · 2026-10-26  
- **效力**：架构 × 业务（兼任）— 对「建议顺序」第 1–4 步 + 诊断 MVP BOUNDARY A–C 作结案  
- **不含**：其余四产品拆分；compose 长驻诊断微服务（见 `ADR09_DEFER_FULL_SPLIT_E4_PROD.md`）

## 已完成（建议顺序）

| 步 | 内容 | 证据 |
|----|------|------|
| 1 | ADR-10 Phase C 单产品加深 | #426 / #429 |
| 2 | 生产默认 D1 + D2 | #431 / #434 |
| 3 | 对外 E4（窄） | #436 |
| 4 | 全拆（单产品=诊断 MVP） | #438 |
| 4+ | BOUNDARY A 清单 / B 独立 home / C one-shot health | #439 / #440 / #441 |

## 生产默认路径（收口后）

- ADR-08 Pi Thin 试点 + ADR-10 诊断 MVP（沙箱 / one-shot compose / SPLIT home / D1·D2 opt-in）  
- 对外措辞上限：`ADR09_E4_COPY_DRAFT.md`  
- 回滚：`ADR10_DIAGNOSIS_MVP_ROLLBACK_DRILL.md`

## 明确未开（须另批）

| 项 | 批准句入口 |
|----|------------|
| 下一单产品全拆（点名产品） | `ADR09_NEXT_PRODUCT_SPLIT_DRAFT.md` |
| compose **长驻**诊断微服务 | 同上草案内可选勾选；默认否 |

未另批前：「继续 / 根据建议实施」**不得**默示开上表两项。
