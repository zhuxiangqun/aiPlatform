# aiPlat Agent SDK

**3 行代码创建并执行 AI Agent**

```python
from aiplat import Agent
agent = Agent(name="my-analyst", model="qwen2.5-coder:7b")
result = agent.execute("分析销售数据")
```

---

## Quick Start

### 1. 基础执行 (同步)

```python
from aiplat import Agent

agent = Agent(name="contract-reviewer", model="qwen2.5-coder:7b")
agent.bind_skill("document_analysis")

result = agent.execute("请审核这份合同的合规性")
print(result.output)
```

### 2. 流式执行 (异步)

```python
from aiplat import Agent
import asyncio

async def main():
    agent = Agent(name="report-generator", model="qwen2.5-coder:7b")
    async for chunk in agent.stream("生成Q3销售分析报告"):
        print(chunk, end="")

asyncio.run(main())
```

### 3. 多轮对话

```python
from aiplat import Agent

agent = Agent(name="assistant", model="qwen2.5-coder:7b")
agent.chat("帮我查一下上周的订单数据")
reply = agent.chat("其中哪笔订单金额最高？")
print(reply)
```

### 4. 自定义 Pipeline

```python
from aiplat import Pipeline, Agent
import asyncio

pipeline = Pipeline()
pipeline.add_stage("retrieve", skill="knowledge_retrieval")
pipeline.add_stage("analyze", agent=Agent(name="analyst", model="qwen2.5-coder:7b"))
pipeline.add_stage("format", skill="format_output")

result = await pipeline.run({"query": "分析竞品定价策略"})
```

### 5. 直接使用 ReActLoop (底层控制)

```python
from aiplat import ReActLoop, Config
import asyncio

config = Config(model="qwen2.5-coder:7b", max_steps=10)
loop = ReActLoop(config)

async def main():
    result = await loop.execute("编写一个 Python 脚本来分析日志文件")
    print(result.output)

asyncio.run(main())
```

---

## Installation

```bash
pip install aiplat-sdk
# 或开发模式
pip install -e .
```

## API Reference

| Class | Method | Description |
|-------|--------|-------------|
| `Agent` | `execute(task)` | Sync execution, returns result |
| `Agent` | `stream(task)` | Async streaming execution |
| `Agent` | `chat(message)` | Multi-turn conversation |
| `Agent` | `bind_skill(name)` | Bind a skill to this agent |
| `Agent` | `bind_tool(name)` | Bind a tool to this agent |
| `Pipeline` | `add_stage(name, **kw)` | Add a pipeline stage |
| `Pipeline` | `run(input)` | Execute the pipeline |
| `ReActLoop` | `execute(task)` | Direct harness control |
| `Config` | — | Agent configuration (model, max_steps, etc.) |

## stdio 持久内核（P1，对接 P0-a）

`StdioKernelClient` 封装 `python -m core.acp.stdio_server` 的 JSON-RPC over stdio 协议，
程序化启停 Thread（会话）+ 流式监听事件：

```python
import asyncio
from aiplat import StdioKernelClient

async def main():
    async with StdioKernelClient() as kernel:
        # 启动会话（Thread）
        thread = await kernel.thread_start("p1", "build auth module")
        # 流式监听 run_events（item.event）
        async for event in kernel.stream_events(thread["thread_id"]):
            print(event["event_type"])
        # HITL 审批
        await kernel.thread_approve(thread["thread_id"], thread["state"], feedback="ok")
        # 或拒绝并带反馈
        # await kernel.thread_reject(thread["thread_id"], thread["state"], feedback="redo")
        await kernel.thread_cancel(thread["thread_id"])

asyncio.run(main())
```

| Class | Method | Description |
|-------|--------|-------------|
| `StdioKernelClient` | `thread_start(project, requirement)` | 启动 Thread → {thread_id, state, run_id} |
| `StdioKernelClient` | `thread_events(thread_id, after_seq)` | 拉取 run_events 事件流 |
| `StdioKernelClient` | `stream_events(thread_id)` | 轮询式流式监听（异步生成器） |
| `StdioKernelClient` | `thread_approve/reject/rollback/resume/cancel` | HITL 审批 + 生命周期控制 |
| `StdioKernelClient` | `start()/close()` | spawn/终止内核进程（支持 async with） |

> 依赖：需可导入 `core.acp.stdio_server`（内核模块位于 aiPlat-core）。`AIPLAT_STDIO_PYTHON` 可指定解释器。
