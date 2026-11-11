---
doc_type: Architecture
---

# Ollaya decision_shadow · 一键关闭演练（C6 工程附页）

> **状态**：工程草稿 · **≠ 0.6 正式会签 · ≠ 采样 Go · ≠ 挂 classify**  
> **依据**：实施方案 §5.1 C6 / §5.2；证据包 §0.6.1 C6  
> **日期**：2026-11-08  
> **适用代码**：`core/harness/decision_shadow/`（#616 默关骨架已合入）

## 1. 目的

在影子采样将来打开后，运维能在分钟级把旁路关掉，且主路径 `DomainRouter.classify` 语义不变。当前骨架默认已关；本页约定**关闭键、是否需重启、回滚验证**。

## 2. 关闭优先级（谁改哪键）

| 优先级 | 操作 | 是否需重启 | 备注 |
|:--:|------|:--:|------|
| 1 | env：`AIPLAT_DECISION_SHADOW_ENABLED=0`（或 `false`/`off`） | **是**（当前 loader 在进程启动/配置加载时解析；gunicorn 需 SIGHUP 或重启） | env 覆盖 YAML |
| 2 | `~/.aiplat/decision_shadow.yaml` → `enabled: false` | **是**（同上） | 行为配置；密钥勿写入此文件 |
| 3 | 代码默认 | 已为 `false` | PR 不得把默认改成 `true`（合并门禁） |

相关 env（实现已接线，默认可不设）：

- `AIPLAT_DECISION_SHADOW_ENABLED`
- `AIPLAT_DECISION_SHADOW_SAMPLE_RATE`
- `AIPLAT_DECISION_SHADOW_TRIGGER`
- `AIPLAT_DECISION_SHADOW_QUEUE_SIZE`
- `AIPLAT_DECISION_SHADOW_TIMEOUT_MS`
- `AIPLAT_DECISION_SHADOW_ENDPOINT` / `…_MODEL`（凭据类仍走密钥 env，勿进 YAML）
- `AIPLAT_DECISION_SHADOW_STORE_RAW_TEXT`（默认 false）

## 3. 演练步骤（dev 已跑通骨架探测）

```bash
# 1) 确认现状（应 enabled=false / classify_hook_wired=false）
curl -sS "${CORE_BASE:-http://127.0.0.1:8002}/api/core/diagnostics/decision-shadow/status" \
  | python3 -m json.tool

# 2) 强制关闭（即使有人误开 YAML）
export AIPLAT_DECISION_SHADOW_ENABLED=0
# 向 gunicorn master 发 SIGHUP（或完整重启 core）
kill -HUP "$(pgrep -f 'gunicorn.*server:app' | head -1)"

# 3) 再确认 + 探测投递被拒
curl -sS "${CORE_BASE:-http://127.0.0.1:8002}/api/core/diagnostics/decision-shadow/status"
curl -sS -X POST "${CORE_BASE:-http://127.0.0.1:8002}/api/core/diagnostics/decision-shadow/try-enqueue" \
  -H 'Content-Type: application/json' \
  -d '{"trace_id":"kill-switch-drill","tier":"t3","query_raw":"drill"}'
# 期望：accepted=false；drops.disabled 递增
```

**本机实证（2026-11-08 · #616 合入后 SIGHUP）**：`enabled=false`；`POST try-enqueue` → `accepted=false`，`drops.disabled=1`。JSONL：`.aiplat/ollaya_phase0/decision_shadow_status.jsonl`。

## 4. 回滚验证（打开后再关）

仅在**书面采样 Go**之后才允许把 `enabled` 设为 true。回滚时：

1. 按 §2 置 `enabled=false` 并 SIGHUP/重启。  
2. `GET …/decision-shadow/status` → `enabled=false`。  
3. 主路径：对照 `GET …/domain-router/route-stats` 与业务 classify 调用，确认无异常冒泡（契约 C1/C3）。  
4. 若曾挂 `DomainRouter.classify` 钩子：关闭后 `classify_hook_wired` 仍可能为 true（钩子代码在），但 `try_enqueue` 因 `enabled=false` 必须立刻 drop——**钩子存在 ≠ 流量开启**。

## 5. 诚实边界

- 本页 **≠** 0.6 会签签字。  
- 本页 **≠** 授权开采样 / 挂 classify / 进 1b。  
- 热更新：当前实现为进程加载配置；**不要假设**不重启即可翻转开关，除非后续实现显式热读并在此页更新。
