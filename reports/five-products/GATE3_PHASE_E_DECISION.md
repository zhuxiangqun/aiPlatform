# Gate3 Phase E 决定（2026-10-24）

**结论：批准 Gate3 Phase E（真实 lock-service 场景 Bundle）。**

## 依据

| 项 | 内容 |
|----|------|
| 授权人 | 架构决策 owner × 业务场景 owner（兼任） |
| 对话授权 | 2026-10-24「批准按照顺序实施」（顺序第 1 项） |
| 前置 | Phase A–D 已合入；场景 `fp-customer-lock-service-bundle-pi-diag-001` |
| 顺序 | ① lock-service Bundle → ② HTTP ⑥b 签收 → ③ E4/全拆仅 ADR（本批不做 ②③） |

## 批准范围（可执行）

| ID | 范围 |
|----|------|
| G3-E1 | 运行时物化 lock-service Bundle 源：从 `fixtures/sample-app` 复制并写入 `domain_id=lock-service` / `scene_id`（避免 inflation 深层目录树） |
| G3-E2 | `GATE3_PI_THIN_PHASE=e`：export → evidence → diagnosis → FDE bind（同 D 链） |
| G3-E3 | 文书：本文件 + pilot DoD；**禁止** harness 硬编码 `if domain == lock-service` |

## 明确不在本批

| 项 |
|----|
| 顺序第 2/3（Phase F / ADR） |
| 五产品全拆 / 对外 E4 落地 |
| 高风险写操作 skill |

## 签署

架构 × 业务（兼任）：**批准 Gate3 Phase E — lock-service Bundle** · 2026-10-24  
