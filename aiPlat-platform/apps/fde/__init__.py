"""
FDE module — Field Deployment Engineer application.

Per app-module-layout.md:
- api/     — REST endpoints (platform/apps/fde/api/)
- service/ — business logic (core/apps/fde/)
- prompts/ — LLM templates (core/apps/fde/prompts.py)
"""

# Domain prompts registration (P1-1 migration — triggers from core)
from core.apps.fde.prompts import register_fde_prompts
register_fde_prompts()

# Router registration: decouples server startup from platform import
from core.api.router_registry import register
from apps.fde.api.fde import router as fde_router
register("/api/core", fde_router)

# Handler registration: platform pushes capabilities to CoreFacade
# Direction: platform → core (correct per architecture contract §2.1)
from core.api.core_facade import register_handler
from apps.fde.api.fde import _get_pipeline_health, _clarify, fde_health
register_handler("fde_pipeline_health", _get_pipeline_health)
register_handler("fde_health", fde_health)
register_handler("fde_clarify", _clarify)

# TenantStore injection (P0-A3): platform owns tenant quota/policy/usage tables.
# Direction: platform → core via CoreFacade (set_tenant_store). Same DB file as
# ExecutionStore → zero data migration. Core consumers resolve via protocol.
from core.api.core_facade import set_tenant_store
from tenants.tenant_store import TenantStore

_tenant_store = TenantStore()
set_tenant_store(_tenant_store)
