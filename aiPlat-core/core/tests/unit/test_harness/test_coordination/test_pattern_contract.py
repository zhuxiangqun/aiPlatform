import asyncio

from core.harness.coordination.patterns import CoordinationContext, PipelinePattern


class _BadAgent:
    # execute expects AgentContext-like input; passing str will raise TypeError
    async def execute(self, ctx, extra):  # pragma: no cover
        return "x"


def test_pattern_contract_typeerror_is_explained():
    pattern = PipelinePattern()
    ctx = CoordinationContext(task="t", agents=[_BadAgent()])
    result = asyncio.run(pattern.coordinate(ctx))
    assert result.success is False
    assert result.errors
    assert "execute(task: str)" in result.errors[0]
