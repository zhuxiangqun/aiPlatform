"""Learning module — skill evolution & release management."""

# Handler registration: platform pushes learning capabilities to CoreFacade
# Direction: platform → core (correct per architecture contract §2.1)
from core.api.core_facade import register_handler
from apps.learning.api.learning_releases import (
    publish_release_candidate,
    rollback_release_candidate,
)
register_handler("publish_release_candidate", publish_release_candidate)
register_handler("rollback_release_candidate", rollback_release_candidate)
