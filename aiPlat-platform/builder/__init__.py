"""aiPlat-platform package."""

# Handler registration: platform pushes builder service to CoreFacade
# Direction: platform → core (correct per architecture contract §2.1)
from core.api.core_facade import register_handler
from builder.builder_project_service import _get_project_service
register_handler("builder_project_service", _get_project_service)
