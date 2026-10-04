import asyncio
import time
from typing import Any, Dict, List, Optional

import pytest


class FakeStore:
    def __init__(self):
        self.nodes = [
            {
                "node_id": "span-gen-1",
                "parent_id": "step:1",
                "kind": "llm",
                "name": "generate",
                "label": "generate",
                "role": "work",
                "status": "running",
                "start_time": time.time() - 100,
                "end_time": None,
                "duration_ms": 0,
                "args": {},
            }
        ]
        self.syscalls = [
            {
                "id": "run1:llm:generate:start:1",
                "kind": "llm",
                "name": "generate",
                "status": "success",
                "start_time": time.time() - 100,
                "end_time": time.time() - 10,
                "duration_ms": 90000,
            }
        ]

    async def init(self):
        return None

    def _connect(self):
        class C:
            def execute(self, *a, **k):
                class R:
                    rowcount = 0  # already success → UPDATE matches 0
                return R()
            def commit(self):
                pass
            def close(self):
                pass
        return C()

    async def list_run_graph_nodes(self, run_id):
        return list(self.nodes)

    async def upsert_run_graph_node(self, node):
        for i, n in enumerate(self.nodes):
            if n["node_id"] == node["node_id"]:
                self.nodes[i] = {**n, **node}
                return self.nodes[i]
        self.nodes.append(node)
        return node

    async def list_syscall_events(self, run_id=None, limit=50):
        return {"items": self.syscalls}


@pytest.mark.asyncio
async def test_close_running_seals_graph_even_when_syscall_already_success():
    from core.services.execution_store.syscall_mixin import SyscallMixin

    class S(FakeStore, SyscallMixin):
        pass

    store = S()
    n = await store.close_running_syscall_events(
        "run1", status="success", kind="llm", name="generate"
    )
    assert n == 0  # UPDATE matched nothing
    node = store.nodes[0]
    assert node["status"] == "ok"
    assert node["end_time"] is not None


@pytest.mark.asyncio
async def test_close_running_seals_pre_llm_prep_graph_card():
    from core.services.execution_store.syscall_mixin import SyscallMixin

    class S(FakeStore, SyscallMixin):
        pass

    store = S()
    store.nodes = [
        {
            "node_id": "ctx:pre_llm_prep",
            "parent_id": "step:qa_agent:2",
            "kind": "context",
            "name": "pre_llm_prep",
            "label": "准备 · LLM 前置",
            "role": "work",
            "status": "running",
            "start_time": time.time() - 50,
            "end_time": None,
            "duration_ms": 0,
            "args": {},
        }
    ]
    n = await store.close_running_syscall_events(
        "run-qa", status="ok", kind="context", name="pre_llm_prep"
    )
    assert n == 0
    node = store.nodes[0]
    assert node["status"] == "ok"
    assert node["end_time"] is not None
