# EVAL_V1 G2a — 单人复核锁 v0（工程校准）

- **目标**：≥30 条金标 + 你一人 adjudicate → `lock-v0` → local `gate_claim`  
- **禁止**：宣称 accuracy / κ / 外部 gate（D5）  
- **现状**：种子已 ≥40 可跑；标签默认 `pending_review`

## 建议节奏（D11）

每周三 19:00–21:00 复核；约 30×20 分钟 ≈ 10 小时总量。

## API（canonical `/api/platform/apps/eval`）

```bash
# 1) 确保金标已导入
curl -X POST .../store/bootstrap-e3 -d '{"tenant_id":"eval-v1"}'

# 2) AI 只做预标注（不 adjudicate）
curl -X POST .../store/review-queue/preannotate -d '{"tenant_id":"eval-v1"}'

# 3) 拉待审队列
curl '.../store/review-queue?tenant_id=eval-v1&limit=30'

# 4) 你逐条确认（pass 以你为准，可参考 ai_preannotate）
curl -X POST .../store/labels/{label_id}/adjudicate \
  -d '{"pass":true,"notes":"...","tenant_id":"eval-v1"}'

# 5) ≥30 adjudicated 后锁 v0
curl -X POST .../store/lock-v0 -d '{"tenant_id":"eval-v1"}'

# 6) 本地 gate claim（仍非 accuracy）
curl -X POST .../store/gate-g2a -d '{"mode":"nightly","tenant_id":"eval-v1"}'

# 状态
curl '.../store/g2a-status?tenant_id=eval-v1'
```

## 出口

| 条件 | 结果 |
|---|---|
| `v0_locked=true` + engineering gate pass | local `gate_claim=true`；可另批解冻 UI `/eval` preview |
| 未满 30 adjudicated | 不可 lock；E0–E5 仍可用 |
| accuracy / κ / 外部 gate | **G2b 后置** |

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_eval_v1_g2a.py -q
```
