"""
Feedback Loops Module
"""

from .local import (
    FeedbackLevel,
    FeedbackType,
    FeedbackData,
    LocalFeedbackLoop,
    FeedbackAggregator,
    get_local_feedback,
    create_local_feedback,
)
from .push import (
    PushDestination,
    PushStatus,
    PushTarget,
    PushMessage,
    PushManager,
    PushFeedbackHandler,
    create_push_manager,
    get_push_manager,
)
from .prod import (
    ProdEnvironment,
    StorageBackend,
    FeedbackStorageType,
    ProdFeedbackConfig,
    StoredFeedback,
    ProdFeedbackStore,
    ProdFeedbackAnalytics,
    ProductionFeedbackLoop,
    create_production_feedback,
    get_production_feedback,
)

# evolution_trigger removed (dead duplicate of apps/skills/evolution/engine.py)

# EvolutionEngine + get_evolution_engine re-exported from canonical location
from core.apps.skills.evolution.engine import EvolutionEngine, get_evolution_engine  # noqa: data type (class) — allowed exception
EvolutionTriggerType = None
EvolutionAction = None  
EvolutionTrigger = None
EvolutionEvent = None
EvolutionTriggerManager = EvolutionEngine  # for backward compat

__all__ = [
    "FeedbackLevel",
    "FeedbackType",
    "FeedbackData",
    "LocalFeedbackLoop",
    "FeedbackAggregator",
    "get_local_feedback",
    "create_local_feedback",
    "PushDestination",
    "PushStatus",
    "PushTarget",
    "PushMessage",
    "PushManager",
    "PushFeedbackHandler",
    "create_push_manager",
    "get_push_manager",
    "ProdEnvironment",
    "StorageBackend",
    "FeedbackStorageType",
    "ProdFeedbackConfig",
    "StoredFeedback",
    "ProdFeedbackStore",
    "ProdFeedbackAnalytics",
    "ProductionFeedbackLoop",
    "create_production_feedback",
    "get_production_feedback",
]