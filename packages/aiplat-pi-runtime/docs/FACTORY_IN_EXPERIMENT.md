# 厂内轴（A）— ⓪ 合并关闭（归档）

> **处置（2026-10-14）**：① 空白验证结论 `blank_not_proven` → 走 **§⓪ 合并关闭**。  
> **Workspace Execute Pi 旁路已从 `core_facade` 拆除**；`AIPLAT_PI_CODING_EXECUTOR` **不再影响**生产 Execute。  
> 离线 CLI / RPC 探针保留在本包 `scripts/` · `python/`，供手工复现与文档引用，**不是**产品主路径。  
> **不得**标 CAPABILITIES「厂内已接线」。主产品轴仍是厂外薄 Runtime（本包导出/ZIP + hybrid）。

> 权威战略：`docs/architecture/plans/pi-thin-runtime.md` §战略。

## 为什么关闭

历史上宣称：补 aiPlat **编码场景执行闭环**空白（文件 / bash 类副作用）。  
静态证据表明主路径已具备：

| 证据 | 位置 |
|------|------|
| `coding_closed_loop` 注入 sandbox + done_verify | `inject_workspace_coding_defaults` |
| 文件副作用 syscall | `sys_file_read` / `sys_file_write` / `sys_file_edit` |
| bash 沙箱门禁认知 | `SandboxGate`（`tool:bash`） |
| Workspace Execute 默认 ReActLoop | `core_facade._execute_workspace_agent_background` |

**判据**：宣称的「无法执行文件/bash 类副作用」与主路径事实冲突（`blank_not_proven`）。  
无真实独占 caller → 不维持平行执行旁路。

## 合并关闭做了什么

| 项 | 动作 |
|----|------|
| `core_facade` Pi 旁路 | **删除**（flag 开启也不再劫持 Execute） |
| `workspace_coding_bridge` / `coding_exec` / RPC probe | **保留为离线工具**（归档；不经 Workspace Execute） |
| CAPABILITIES | 仍不标「厂内已接线」 |
| 方式一/二/三 | **不实现**（空白未证明时禁止加平行路径） |

验收：

```bash
# facade 不得再引用 Workspace Execute Pi 桥
! grep -n 'run_workspace_coding_via_pi\|workspace_coding_bridge' \
  aiPlat-core/core/api/core_facade.py

# 归档探针（可选）
python3 packages/aiplat-pi-runtime/scripts/factory_in_evidence_smoke.py
```

## 若将来重开

须先提交**可证伪**命题 + **真实 caller**（issue/PR/客户），并重做 ① 空白验证。  
禁止直接复活已拆除的 `core_facade` 旁路；若确需可选执行核，走单独 RFC（安全证据 + 不改 PipelineEngine/ReActLoop/PolicyGate 核心）。

## 归档：离线探针（非产品路径）

```bash
# 无 --allow-host → 拒绝（强制提醒沙箱）
python3 packages/aiplat-pi-runtime/scripts/coding_exec.py \
  --cwd /path/in/sandbox --prompt "…" --model ollama/qwen2.5:3b

python3 packages/aiplat-pi-runtime/scripts/coding_rpc_probe.py --dry-run
python3 packages/aiplat-pi-runtime/scripts/test_coding_exec_unit.py
python3 packages/aiplat-pi-runtime/scripts/factory_in_evidence_smoke.py
```

环境变量（仅离线工具）：`AIPLAT_PI_BIN` · `AIPLAT_PI_MODEL` · `AIPLAT_PI_CODING_SANDBOX_ROOT` · `AIPLAT_PI_CODING_ALLOW_HOST=1`（仅开发）。  
`AIPLAT_PI_CODING_EXECUTOR` **已无生产效果**（历史 flag；设置无效）。

## 硬约束（仍适用任何未来 RFC）

- PolicyGate / done_verify / review_gate **始终在 Pi 外**
- 生产默认须 Docker（或等价）隔离；禁止裸跑用户工作区
- 工具语义非 drop-in：Pi `read/bash/...` ≠ `sys_tool_call`
- 不把厂内 Pi 执行核写进 CAPABILITIES「已接线」或主推荐路径，除非 RFC 三条件全满足

## 非目标

- 用 Pi 解决「厂外交付不够厚」（混合回连 / DELIVERY SKU 已另立）
- 把 Memory / SECI 塞进 Pi
- 默认替换 `coding_closed_loop` 的原生工具路径
- 在空白未证明时继续加方式一/二/三实现
