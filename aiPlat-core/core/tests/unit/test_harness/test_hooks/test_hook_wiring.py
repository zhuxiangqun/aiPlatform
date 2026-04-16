import asyncio

from core.harness.execution.loop import BaseLoop, ReActLoop
from core.harness.interfaces.loop import LoopState, LoopStateEnum, LoopConfig
from core.harness.infrastructure.hooks import HookManager, HookPhase, create_hook, HookContext


class _OneStepLoop(BaseLoop):
    async def step(self, state: LoopState) -> LoopState:
        await super().step(state)
        state.current = LoopStateEnum.FINISHED
        state.context["output"] = "ok"
        return state


def test_contract_hook_can_block_execution():
    hm = HookManager()

    async def deny_contract(ctx: HookContext):
        return {"allow": False, "reason": "contract denied"}

    hm.register(create_hook("deny", deny_contract, HookPhase.PRE_CONTRACT_CHECK, priority=999))

    loop = _OneStepLoop(hook_manager=hm)
    res = asyncio.run(loop.run(LoopState(), LoopConfig(max_steps=2)))
    assert res.success is False
    assert "contract denied" in (res.error or "")


class _DummyModel:
    async def generate(self, messages):
        class _R:
            def __init__(self, c):
                self.content = c

        # Trigger SecurityScanHook via PRE_APPROVAL_CHECK (Write/Edit content scan)
        return _R('ACTION: WRITE: {"path":"a.txt","content":"sk-abcdefghijklmnopqrstuvwxyz"}')


class _DummyTool:
    name = "WRITE"
    description = "dummy write"

    async def execute(self, params):
        class _R:
            def __init__(self, out):
                self.output = out

        return _R("should not run")


def test_pre_approval_hook_can_deny_tool_use():
    loop = ReActLoop(model=_DummyModel(), tools=[_DummyTool()])
    state = LoopState(
        context={
            "task": "t",
            "messages": [{"role": "user", "content": "t"}],
            "session_id": "s",
            "user_id": "u",
        }
    )
    res = asyncio.run(loop.run(state, LoopConfig(max_steps=1)))
    assert res.success is False or res.success is True  # loop may finish but should deny
    obs = res.final_state.context.get("observation", "")
    assert "Denied:" in obs

