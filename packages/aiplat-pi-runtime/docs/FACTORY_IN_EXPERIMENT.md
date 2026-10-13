# 厂内轴（A）实验备忘 — 非主路径

> 状态：**方式四 CLI + Workspace Execute 旁路 flag 已接线**；**默认关闭**（`AIPLAT_PI_CODING_EXECUTOR`）。  
> **未**接入 PipelineEngine / harness；**不得**标 CAPABILITIES「厂内已接线」。  
> 主产品轴仍是厂外薄 Runtime（本包 + 导出/ZIP）。  

> 权威战略：`docs/architecture/plans/pi-thin-runtime.md` §战略。

## 目标

补 aiPlat **编码场景执行闭环**空白（文件/ bash 类副作用），**不**替代 PipelineEngine / ReActLoop / PolicyGate。

## 方式四骨架（本包）

```bash
# 无 --allow-host → 拒绝（强制提醒沙箱/隔离）
python3 packages/aiplat-pi-runtime/scripts/coding_exec.py \
  --cwd /path/in/sandbox --prompt "…" --model ollama/qwen2.5:3b

# 本地实验（显式放行 host cwd）
AIPLAT_PI_MODEL=ollama/qwen2.5:3b \
  bash packages/aiplat-pi-runtime/scripts/coding_exec_smoke.sh

python3 packages/aiplat-pi-runtime/scripts/test_coding_exec_unit.py
```

调用方责任：在外层跑 PolicyGate / done_verify / review_gate；生产默认须 Docker（或等价）隔离后再 `--allow-host` 指向容器内 cwd。

## 允许尝试的顺序

1. **方式四**：`coding_closed_loop` 可选执行器 → 沙箱内 `pi --mode rpc` / print（外层仍 done_verify / review_gate）← **CLI 骨架**

2. **方式二**：`handler.py` 经 Pi RPC 做文件类副作用（syscall/PolicyGate 在启动 Pi 之前或经工具桥回闸）
3. **方式三**：MCP 执行宿主（aiPlat 保留 `check_cost_ladder` + 审计）
4. **方式一**：`createAgentSession` 旁路 `react_tools` — **最后**；禁止默认换 StageRunner→ReActLoop

## 方式四探针（本包）

| 文件 | 作用 |
|------|------|
| `python/pi_rpc_client.py` | JSONL RPC 客户端 + 沙箱 cwd 门禁 |
| `scripts/coding_exec.py` | print-mode 编码执行 CLI |
| `python/workspace_coding_bridge.py` | Workspace Execute 旁路桥（flag 默认 OFF） |
| `scripts/coding_rpc_probe.py` | `--dry-run` / `--live` 冒烟 |

```bash
# 无 LLM：起 pi RPC → get_state → 退出（cwd 自动用临时沙箱）
python3 packages/aiplat-pi-runtime/scripts/coding_rpc_probe.py --dry-run

# 有模型（例 Ollama）
AIPLAT_PI_MODEL=ollama/qwen2.5:3b \
  python3 packages/aiplat-pi-runtime/scripts/coding_rpc_probe.py --live
```

环境变量：`AIPLAT_PI_BIN` · `AIPLAT_PI_MODEL` · `AIPLAT_PI_CODING_SANDBOX_ROOT` · `AIPLAT_PI_CODING_ALLOW_HOST=1`（仅开发） · `AIPLAT_PI_CODING_EXECUTOR=1`（Workspace Execute 旁路，**默认关闭**）。

**flag 接线（实验，默认 OFF）**：`core_facade._execute_workspace_agent_background` 在 `runner.run` 之前，当 `AIPLAT_PI_CODING_EXECUTOR` 开启且 `state["_workspace_coding_defaults"]` 时，经 `workspace_coding_bridge.run_workspace_coding_via_pi` 可选走 Pi；失败/未启用则回落 ReActLoop。**不**改 CAPABILITIES「厂内已接线」。

**下一步（仍属实验）**：沙箱/PolicyGate 证据齐全后再考虑 CAPABILITIES 登记；PipelineEngine 仍禁止直接塞 Pi。

## 硬约束

- PolicyGate / done_verify / review_gate **始终在 Pi 外**
- 必须选沙箱（Docker / 等价隔离）；禁止裸跑用户工作区当生产默认
- 工具语义非 drop-in：Pi `read/bash/...` ≠ `sys_tool_call`；厂外混合已用 `enterprise_tool_gate` 拦截原生副作用；厂内仍须显式工具桥 + 外层 PolicyGate
- 不把本实验写进 CAPABILITIES「已接线」或主推荐路径，直至有生产 caller + 门禁证据

## 非目标

- 用 Pi 解决「厂外交付不够厚」（那是厚运行时 / 混合回连产品决策）
- 把 Memory / SECI 塞进 Pi
- 默认替换 `coding_closed_loop` 的原生工具路径
