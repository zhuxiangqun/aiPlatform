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
