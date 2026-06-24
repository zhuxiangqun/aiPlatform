"""
A2A Protocol — Google Agent-to-Agent protocol implementation.

Backed by aiPlat infrastructure (ExecutionStore, ReActLoop, SkillRegistry).
Zero new dependencies.

Usage:
    from core.apps.a2a.server import a2a_router
    app.include_router(a2a_router)
"""

from .server import a2a_router
from .agent_card import AgentCard

__all__ = ["a2a_router", "AgentCard"]
