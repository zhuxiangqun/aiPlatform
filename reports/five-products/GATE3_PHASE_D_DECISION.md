# Gate3 Phase D 决定（2026-10-24）

**结论：批准 Gate3 Phase D（FDE 验收绑定 Phase C `report_id`）。**

## 依据

| 项 | 内容 |
|----|------|
| 授权人 | 架构决策 owner × 业务场景 owner（兼任） |
| 对话授权 | 2026-10-24「批准 Phase D」 |
| 前置 | Phase C 已合入；`validate_slice_signoff_reports` 已存在 |
| 场景 | `fp-customer-lock-service-bundle-pi-diag-001`（SCENE F1） |

## 批准范围（可执行）

| ID | 范围 |
|----|------|
| G3-D1 | `fp-*` / `for_slice` 验收**必须**带有效 `evidence_report_ids`（既有 gate，不改语义） |
| G3-D2 | `GATE3_PI_THIN_PHASE=d`：Phase C → 负向（无 report 拒签）→ 正向（绑 report 通过） |
| G3-D3 | 沙箱落盘验收绑定记录（`$AIPLAT_HOME/.../acceptance/`），不强制走生产 HTTP ⑥b preflight |
| G3-D4 | 文书：本文件 + pilot DoD；**禁止**新建平行 signoff API / 拆 FDE 服务 |

## 明确不在本次批准内

| 项 |
|----|
| 五产品全拆 / 对外 E4 |
| 绕过或废除 ⑥b 安全 preflight 生产门禁 |
| 诊断二期 / 自动修复 |

## 签署

架构 × 业务（兼任）：**批准 Gate3 Phase D — FDE 验收绑定诊断 report_id** · 2026-10-24  
