"""Runtime Facade — kernel runtime access (no core_facade dependency)."""
from __future__ import annotations

from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.integration import KernelRuntime, get_harness
from core.harness.kernel.types import ExecutionRequest
from core.harness.memory.manager import get_memory_manager
from core.harness.execution.pipeline_engine import get_event_bus
