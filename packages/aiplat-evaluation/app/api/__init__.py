"""Canonical eval API routers for standalone host (A3 / B1-L)."""

from app.api.execution_stubs import register_execution_stubs
from app.api.store_routes import register_store_routes

__all__ = ["register_store_routes", "register_execution_stubs"]
