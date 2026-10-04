"""
eval application module — service layer.

Per app-module-layout.md:
- api/     → routers (entropy thin proxy) + platform apps/eval
- service/ → aiPlat-core/core/apps/eval/ (this directory)

Unique writer for Agent scoring_dimensions + eval_metric/eval_runner:
``generate_agent_eval`` / ``inspect_agent_eval`` / ``enqueue_listed_agent_eval``.
"""
from core.apps.eval.agent_eval import (
    enqueue_listed_agent_eval,
    generate_agent_eval,
    inspect_agent_eval,
)

__all__ = [
    "generate_agent_eval",
    "inspect_agent_eval",
    "enqueue_listed_agent_eval",
]
