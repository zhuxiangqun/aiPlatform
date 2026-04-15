"""
aiPlat-management 主入口
"""

from management.server import create_app, run_server

__version__ = "0.1.0"

__all__ = [
    "create_app",
    "run_server",
]