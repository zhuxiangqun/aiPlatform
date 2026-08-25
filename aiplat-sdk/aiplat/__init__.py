"""
aiPlat Agent SDK — 3 行代码创建并执行 AI Agent。

Usage:
    from aiplat import Agent

    agent = Agent(name="my-analyst", model="qwen2.5-coder:7b")
    agent.bind_skill("data_analysis")
    result = agent.execute("分析上周销售数据")

    # 流式模式
    async for chunk in agent.stream("生成报告"):
        print(chunk, end="")

    # 自定义 Pipeline
    from aiplat import Pipeline
    pipeline = Pipeline()
    pipeline.add_stage("retrieve", skill="knowledge_retrieval")
    pipeline.add_stage("analyze", agent=agent)
    result = await pipeline.run(input_data)

    # stdio 持久内核（P0-a 对接）
    from aiplat import StdioKernelClient
    async with StdioKernelClient() as kernel:
        thread = await kernel.thread_start("p1", "build auth")
        async for event in kernel.stream_events(thread["thread_id"]):
            print(event)
"""

from .agent import Agent
from .pipeline import Pipeline
from .harness import ReActLoop
from .config import Config
from .stdio import StdioKernelClient, StdioKernelError
from .exec import exec_script, exec_pipeline, main as exec_main

__version__ = "0.2.0"
__all__ = ["Agent", "Pipeline", "ReActLoop", "Config", "StdioKernelClient", "StdioKernelError",
           "exec_script", "exec_pipeline", "exec_main"]
