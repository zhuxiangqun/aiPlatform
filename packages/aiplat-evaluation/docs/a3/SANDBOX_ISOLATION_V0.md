# Sandbox isolation v0（首版本地 · 不含 microVM）

> Honesty: **`sandbox_real_isolation=false`** · Docker `network=none` ≠ 隔离认证 · ≠ authorize

## In-scope（SCORE_SCOPE §三）

| 条件 | 代码事实 |
|------|----------|
| Docker CLI 沙箱 | `app/sandbox/docker_exec.py` 固定 `--network=none`（+ read-only / memory / pids） |
| 策略门 | `app/sandbox/policy.py`：`off` / `local_stub` / `docker`；`microvm` prep 不 admit |
| 技能工具 | fixture-only；live skill tools 仍 deny |
| 诚实字段 | closeout / health 携带 `sandbox_real_isolation=false` |

## Gate

```bash
bash packages/aiplat-evaluation/scripts/sandbox_isolation_v0_gate.sh
```

## Explicit non-claims

- 非 microVM / KVM / Firecracker 真隔离  
- 非 SOC 沙箱认证  
- 非 `process_split_authorized`  
- Darwin 本机不得把本文件写成「含 microVM 本地 5」
