"""Multimodal bridge — audio/browser/video → Agent decision loop.

G-axis L2→L3: transforms standalone multimodal modules into Agent-aware context providers.
"""
from core.harness.multimodal.integrator import MultimodalIntegrator, get_multimodal_integrator

__all__ = ["MultimodalIntegrator", "get_multimodal_integrator"]
