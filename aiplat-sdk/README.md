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
