# Gate3 Phase F 决定（2026-10-24）

**结论：批准 Gate3 Phase F（生产 HTTP 验收签收 · ⑥b preflight）。**

## 依据

| 项 | 内容 |
|----|------|
| 授权人 | 架构决策 owner × 业务场景 owner（兼任） |
| 对话授权 | 2026-10-24「批准按照顺序实施」（顺序第 2 项） |
| 前置 | Phase D 沙箱绑定已合入；`POST .../acceptance/signoff` + `fde_preflight_signoff_gate` 已存在 |
| 顺序 | ① lock-service Bundle（Phase E / #404）→ **② 本批** → ③ E4/全拆仅 ADR |

## 批准范围（可执行）

| ID | 范围 |
|----|------|
| G3-F1 | 经生产路径 `POST /api/platform/apps/fde/acceptance/signoff`（ASGI TestClient，非沙箱直写） |
| G3-F2 | 硬门：无 ⑥b → 409 `preflight_gate_blocked`；有 ⑥b 无 report → 409 slice；双齐 → `signed_off` |
| G3-F3 | `GATE3_PI_THIN_PHASE=f`：Phase C → 上述 HTTP 断言；⑥b 用 `save_preflight_run` 写入（同 HTTP `/security-preflight/run` 落盘契约） |
| G3-F4 | 文书：本文件 + pilot DoD；**禁止**绕过或废除 ⑥b；**禁止**新建平行 signoff API |

## 明确不在本批

| 项 |
|----|
| 五产品全拆 / 对外 E4 落地（顺序第 3 仅 ADR） |
| 启动完整 platform 多进程控制面 |
| 废除 Phase D 沙箱落盘路径 |

## 签署

架构 × 业务（兼任）：**批准 Gate3 Phase F — HTTP ⑥b 验收签收** · 2026-10-24  
