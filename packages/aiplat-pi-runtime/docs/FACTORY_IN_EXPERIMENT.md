# 厂内轴（A）实验备忘 — 非主路径

> 状态：**未接线**。主产品轴是厂外薄 Runtime（本包 + 导出/ZIP）。  
> 权威战略：`docs/architecture/plans/pi-thin-runtime.md` §战略。

## 目标

补 aiPlat **编码场景执行闭环**空白（文件/ bash 类副作用），**不**替代 PipelineEngine / ReActLoop / PolicyGate。

## 允许尝试的顺序

1. **方式四**：`coding_closed_loop` 可选执行器 → 沙箱内 `pi --mode rpc` / print（外层仍 done_verify / review_gate）
2. **方式二**：`handler.py` 经 Pi RPC 做文件类副作用（syscall/PolicyGate 在启动 Pi 之前或经工具桥回闸）
3. **方式三**：MCP 执行宿主（aiPlat 保留 `check_cost_ladder` + 审计）
4. **方式一**：`createAgentSession` 旁路 `react_tools` — **最后**；禁止默认换 StageRunner→ReActLoop

## 硬约束

- PolicyGate / done_verify / review_gate **始终在 Pi 外**
- 必须选沙箱（Docker / 等价隔离）；禁止裸跑用户工作区当生产默认
- 工具语义非 drop-in：Pi `read/bash/...` ≠ `sys_tool_call`；若要门禁每次工具调用，须显式工具桥
- 不把本实验写进 CAPABILITIES「已接线」或主推荐路径，直至有生产 caller + 门禁证据

## 非目标

- 用 Pi 解决「厂外交付不够厚」（那是厚运行时 / 混合回连产品决策）
- 把 Memory / SECI 塞进 Pi
