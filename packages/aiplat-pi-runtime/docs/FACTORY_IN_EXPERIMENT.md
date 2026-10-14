# 厂内轴（A）实验备忘 — 非主路径

> 状态：**方式四 CLI + Workspace Execute 旁路 flag 已接线**；**默认关闭**（`AIPLAT_PI_CODING_EXECUTOR`）。  
> **未**接入 PipelineEngine / harness；**不得**标 CAPABILITIES「厂内已接线」。  
> 主产品轴仍是厂外薄 Runtime（本包 + 导出/ZIP）。  
> 退出条件见下文 **§退出条件**（决策树，非完成度清单）。

> 权威战略：`docs/architecture/plans/pi-thin-runtime.md` §战略。

## 目标

历史上宣称：补 aiPlat **编码场景执行闭环**空白（文件 / bash 类副作用），**不**替代 PipelineEngine / ReActLoop / PolicyGate。  
**不为补上下文**：aiPlat 已有 Memory/CRAG/ContextBus；厂内接 Pi 的价值若成立，应是**可选执行引擎 + 本地工具循环**（见 `pi-thin-runtime.md` §双模式内涵），而非再造门禁。

> **① 空白验证（2026-10-14）**：宣称的「文件/bash 副作用空白」**未被证明**。  
> 证据见 §退出条件 → ①；当前处置：**保持默认 OFF**，进入合并/放弃评估窗口，**禁止**标 CAPABILITIES 已接线。

## 与「三种集成」的对应

| 形态 | 本实验落点 |
|------|------------|
| RPC 子进程 | `pi_rpc_client` / `coding_exec` / RPC probe |
| SDK 嵌入 | **不做默认**（Node 绑定） |
| 可选执行后端 | `AIPLAT_PI_CODING_EXECUTOR` → Workspace Execute 旁路（默认 OFF） |

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

## 退出条件（决策树 — 强制）

冗余实验最常见的死法不是「做不完」，而是「做完了才发现问题不存在」。  
**第一刀问空白是否真实，不问实验完成度。**

```
              ① 空白验证（前置门槛）
              coding_closed_loop 是否真的无法
              执行文件 / bash 类副作用？
                    │
            ┌───────┴───────┐
           YES              NO / 未证明
            │                │
     ② 独占性评估      ⓪ 合并或放弃
     能否用合理成本        （空白不存在或未被证明；
     扩展 coding_closed_    实验无独立存在必要）
     loop 填补空白？
            │
     ┌──────┴──────┐
    YES           NO
     │             │
  ⓪ 合并关闭   ③ 升级评估
  （吸收有用部分， （仅当主路径无法填补时）
   关闭实验）         │
              ┌───────┴───────┐
             全满足          任一不满足
              │                │
         升级到主路径     保留实验 + 时间窗口
```

### ⓪ 立即放弃 / 合并关闭

| 条件（任一） | 动作 |
|--------------|------|
| ① 判定空白不存在或**未被证明** | 保持 `AIPLAT_PI_CODING_EXECUTOR` 默认 OFF；进入合并评估（吸收有用脚本进文档/探针）或计划删除 |
| 能用 <2 周工作量扩展 `coding_closed_loop` / 原生 syscall 填补真实缺口 | **合并关闭**：吸收有用部分，关闭厂内旁路 |
| 总生命周期满 12 个月仍未决议 | **自动放弃**，删除实验接线（可基于当时主路径重开，不复活旧旁路） |

### ① 空白验证（前置门槛）

**问题真实** = 至少 1 个**有真实 caller**（issue/PR/客户）的场景，且 `coding_closed_loop` **做不了**（不是「做不好」）。  
没有真实 caller 的空白 = 想象，不算空白。

#### ① 静态证据包（2026-10-14）

| 证据 | 命令 / 位置 | 结果 |
|------|-------------|------|
| 编码闭环默认注入 sandbox + done_verify（**不依赖 Pi**） | `inject_workspace_coding_defaults(..., coding_closed_loop=True)` → `_sandbox` / `_done_verify` | ✅ 见 `aiPlat-core/core/tests/unit/test_harness/test_workspace_coding_defaults.py` |
| 文件副作用 syscall 已存在 | `sys_file_read` / `sys_file_write` / `sys_file_edit` | ✅ `aiPlat-core/core/harness/syscalls/file.py` |
| bash 类工具有沙箱门禁认知 | `SandboxGate` 含 `tool:bash` | ✅ `harness/infrastructure/gates/sandbox_gate.py` |
| Workspace Execute 默认走 ReActLoop | `AIPLAT_PI_CODING_EXECUTOR` 未设时 `if not _used_pi_coding: runner.run(...)` | ✅ `core_facade._execute_workspace_agent_background` |
| Pi 旁路默认 OFF | `os.getenv("AIPLAT_PI_CODING_EXECUTOR")` 空 | ✅ |

**判据**：`blank_not_proven` — 宣称的「无法执行文件/bash 类副作用」与主路径事实冲突。  
Pi 若还有独占价值，须改写成**可证伪**命题（例：「离线无平台时的 Pi 本地工具循环优于 coding_closed_loop」），并附真实 caller；否则走 ⓪。

复跑静态检查：

```bash
PYTHONPATH=aiPlat-core python3 - <<'PY'
from core.schemas_builder import inject_workspace_coding_defaults
import os
os.environ["AIPLAT_CODING_STAGE_SANDBOX"] = "true"
state = {}
inject_workspace_coding_defaults(state, agent_meta={"coding_closed_loop": True})
assert state.get("_sandbox") is True
assert isinstance(state.get("_done_verify"), dict)
assert not (os.getenv("AIPLAT_PI_CODING_EXECUTOR") or "").strip()
print("① ok: native coding_closed_loop injects sandbox+done_verify; Pi flag default OFF")
PY
```

> Docker 沙箱端到端（读→改→bash）可作为**加强证据**，不阻塞上述静态判据。若将来有人主张「原生路径沙箱内跑不通」，须先提交失败复现再重开 ①。

### ② 独占性评估

空白若被证明真实：评估能否用合理成本（<2 周）扩展主路径填补。

- **YES** → ⓪ 合并关闭（最优结局：不增加平行执行路径）
- **NO** → ③ 升级评估

### ③ 升级到主路径（三条件**全**满足）

| 条件 | 判据 |
|------|------|
| 安全证据完整 | Docker（或等价）隔离验证通过 + 沙箱逃逸测通过 + PolicyGate / done_verify / review_gate **在 Pi 外**的证据链 + 架构/安全签字 |
| 生产 caller 存在 | 非 smoke/demo；PR/issue 明确依赖此旁路 |
| 不要求改核心 | 零修改 PipelineEngine / ReActLoop / PolicyGate 核心逻辑（否则是换心，违反硬约束） |

全满足 → 可标 CAPABILITIES「厂内已接线」并讨论是否接入引擎（仍须单独 RFC）。  
任一不满足 → 保留实验 + 下表时间窗口。

### 时间窗口

| 阶段 | 时限（自 2026-10-14 ① 起算） | 超期动作 |
|------|------------------------------|----------|
| ① 空白验证 | 已执行 → `blank_not_proven` | 进入 ⓪ |
| ②/③ 或合并决议 | **2027-01-14**（+3 个月） | 无真实独占 caller → 合并关闭或删除接线 |
| 升级窗口 | **2027-04-14**（+6 个月） | 未全满足 ③ → 合并/放弃 |
| 总生命周期 | **2027-10-14**（+12 个月） | 未决议 → **自动放弃** |

## 硬约束

- PolicyGate / done_verify / review_gate **始终在 Pi 外**
- 必须选沙箱（Docker / 等价隔离）；禁止裸跑用户工作区当生产默认
- 工具语义非 drop-in：Pi `read/bash/...` ≠ `sys_tool_call`；厂外混合已用 `enterprise_tool_gate` 拦截原生副作用；厂内仍须显式工具桥 + 外层 PolicyGate
- 不把本实验写进 CAPABILITIES「已接线」或主推荐路径，直至 ③ 三条件全满足
- **实验代码不得标 CAPABILITIES 已接线**（防泄漏到产品路径）

## 非目标

- 用 Pi 解决「厂外交付不够厚」（那是厚运行时 / 混合回连产品决策）
- 把 Memory / SECI 塞进 Pi
- 默认替换 `coding_closed_loop` 的原生工具路径
- 在空白未证明时继续加方式一/二/三实现
