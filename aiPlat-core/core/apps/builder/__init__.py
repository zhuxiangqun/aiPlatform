"""
builder application module — service layer.

Per app-module-layout.md:
- api/     → aiPlat-platform/apps/builder/api/ (REST endpoints)
- service/ → aiPlat-core/core/apps/builder/ (this directory)
"""

# v2.5 scaffold — business logic goes here

# Domain prompts registration (P1-1 migration)
from . import prompts; prompts.register_builder_prompts()
