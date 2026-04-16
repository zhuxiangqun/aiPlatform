"""
Apps Module

Provides application layer: Agents, Skills, Tools implementations.
"""

# IMPORTANT:
# Keep this package initializer lightweight. Importing heavy optional dependencies
# (FastAPI/SSE/MCP servers, etc.) here will make any import under `core.apps.*`
# fail in minimal environments (including unit tests).
#
# Consumers should import from specific submodules, e.g.:
# - core.apps.agents
# - core.apps.skills
# - core.apps.tools
