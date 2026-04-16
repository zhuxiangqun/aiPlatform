import asyncio

from core.harness.coordination.patterns import CoordinationContext, HierarchicalDelegationPattern


class _Agent:
    def __init__(self, name: str, outputs):
        self.name = name
        self._outputs = list(outputs)

    async def execute(self, task: str):
        class _R:
            def __init__(self, out):
                self.output = out

        if self._outputs:
            return _R(self._outputs.pop(0))
        return _R(f"{self.name}:{task}")


def test_hierarchical_delegation_runs_depth_limited():
    # root emits two subtasks
    root = _Agent("root", ["- sub1\n- sub2"])
    w1 = _Agent("w1", ["done1"])
    w2 = _Agent("w2", ["done2"])

    pattern = HierarchicalDelegationPattern(depth_limit=2, max_nodes=10)
    ctx = CoordinationContext(task="top", agents=[root, w1, w2], metadata={"depth_limit": 2})

    result = asyncio.run(pattern.coordinate(ctx))
    assert result.success is True
    # outputs: root + 2 workers
    assert len(result.outputs) >= 3
    assert "sub1" in str(result.outputs[0]) or "- sub1" in str(result.outputs[0])

