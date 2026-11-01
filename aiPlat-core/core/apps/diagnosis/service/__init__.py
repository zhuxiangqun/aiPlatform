"""DIAGNOSIS_V1 C2 service — store / adapters / engine / fixture metrics."""
from core.apps.diagnosis.service.store import (
    DiagnosisStore,
    STORE_SCHEMA_VERSION,
    get_diagnosis_store,
)
from core.apps.diagnosis.service.adapters import (
    collect_evidence,
    read_evaluation_refs,
    read_ontology_refs,
)
from core.apps.diagnosis.service.engine import (
    build_recommendations,
    diagnose_case,
)
from core.apps.diagnosis.service.metrics import fixture_metrics

__all__ = [
    "DiagnosisStore",
    "STORE_SCHEMA_VERSION",
    "get_diagnosis_store",
    "collect_evidence",
    "read_evaluation_refs",
    "read_ontology_refs",
    "diagnose_case",
    "build_recommendations",
    "fixture_metrics",
]
