"""
Infrastructure Management API Module

This module provides the REST API server for aiPlat-infra layer.
"""

from .main import create_app

__all__ = ["create_app"]