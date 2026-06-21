"""
Fine-tune provider shared types and package exports.

All providers implement the same implicit interface (no ABC required).
FineTuneJobResult is the shared return type for create_job() and get_job().
"""


class FineTuneJobResult:
    """Fine-tuning job result — shared across all providers."""
    provider_job_id: str = ""
    result_model: str = ""
    status: str = ""
    error: str = ""
    training_tokens: int = 0
    estimated_cost_usd: float = 0.0


# Lazy imports to avoid MLX dependency at import time
from .deepseek import DeepSeekFineTuneProvider  # noqa: E402

__all__ = ["DeepSeekFineTuneProvider", "FineTuneJobResult"]
