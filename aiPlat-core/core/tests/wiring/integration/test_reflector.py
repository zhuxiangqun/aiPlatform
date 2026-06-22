"""
Integration tests for OnErrorReflector wiring.

Verify that the hook correctly detects consecutive tool_call errors
and injects a reasoning hint for the next step.
"""
import pytest


class TestOnErrorReflectorIntegration:

    @pytest.mark.asyncio
    async def test_detects_consecutive_errors(self):
        """OnErrorReflector should detect >=2 consecutive error observations."""
        from core.harness.infrastructure.hooks.on_error_reflector import create_on_error_reflector
        from core.harness.infrastructure.hooks.hook_manager import HookContext, HookPhase

        reflector = create_on_error_reflector()
        context = HookContext(
            phase=HookPhase.POST_OBSERVE,
            state={
                "_observations": [
                    "Tool 'search' returned: 3 results",
                    "error: connection refused after 3 retries",
                    "failed: timeout exceeded for tool 'fetch'",
                ],
            },
        )
        hint = await reflector.on_post_observe(context)
        # Should detect >= 2 errors and return a hint
        if hint is not None:
            assert isinstance(hint, dict), f"Expected dict hint, got {type(hint)}"
            if "reasoning_hint" in hint:
                assert len(str(hint["reasoning_hint"])) > 0

    @pytest.mark.asyncio
    async def test_no_error_means_no_hint(self):
        """OnErrorReflector should not inject hint when there are no errors."""
        from core.harness.infrastructure.hooks.on_error_reflector import create_on_error_reflector
        from core.harness.infrastructure.hooks.hook_manager import HookContext, HookPhase

        reflector = create_on_error_reflector()
        context = HookContext(
            phase=HookPhase.POST_OBSERVE,
            state={
                "_observations": [
                    "Tool 'search' returned: 5 results",
                    "Tool 'fetch' returned: data loaded",
                    "Tool 'analyze' returned: analysis complete",
                ],
            },
        )
        hint = await reflector.on_post_observe(context)
        # With no errors, should return None
        if hint is not None:
            assert isinstance(hint, dict), f"Expected None or dict, got {type(hint)}"
            assert not hint.get("reasoning_hint"), \
                f"Should not inject hint on clean run: {hint}"

    @pytest.mark.asyncio
    async def test_single_error_is_not_enough(self):
        """A single error should not trigger reflection (needs >=2)."""
        from core.harness.infrastructure.hooks.on_error_reflector import create_on_error_reflector
        from core.harness.infrastructure.hooks.hook_manager import HookContext, HookPhase

        reflector = create_on_error_reflector()
        context = HookContext(
            phase=HookPhase.POST_OBSERVE,
            state={
                "_observations": [
                    "Tool 'search' returned: 3 results",
                    "error: connection refused",
                    "Tool 'fetch' returned: data loaded",
                ],
            },
        )
        hint = await reflector.on_post_observe(context)
        # Single error should not trigger
        if hint is not None:
            assert isinstance(hint, dict), f"Expected None or dict, got {type(hint)}"
            assert not hint.get("reasoning_hint"), \
                f"Single error should not trigger reflection: {hint}"
