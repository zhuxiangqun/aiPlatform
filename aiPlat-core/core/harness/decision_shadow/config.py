"""Decision-shadow config (Ollaya Phase 1 skeleton).

Defaults keep the feature fully off. Opening sample traffic / DomainRouter
hooks still requires a written Go (or narrower waiver) — this module alone
does not authorize live shadowing or T3 replacement.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class DecisionShadowConfig:
    enabled: bool = False
    sample_rate: float = 0.01
    trigger: str = "t3_or_t2_boundary"
    queue_size: int = 64
    timeout_ms: int = 200
    endpoint: str = ""
    model: str = ""
    audit_ttl_hours: int = 72
    store_raw_text: bool = False

    def to_public_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["honesty"] = (
            "skeleton only; default off; ≠ DomainRouter hook; "
            "≠ Ollaya accuracy; ≠ token savings; ≠ Go Phase 1b"
        )
        return d


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _load_yaml_overlay() -> Dict[str, Any]:
    """Optional ~/.aiplat/decision_shadow.yaml (behavior config, not secrets)."""
    home = os.getenv("AIPLAT_HOME") or str(Path.home() / ".aiplat")
    path = Path(home) / "decision_shadow.yaml"
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_decision_shadow_config(
    *,
    overlay: Optional[Dict[str, Any]] = None,
) -> DecisionShadowConfig:
    """Resolve config: defaults ← YAML ← env (env wins). Always defaults to off."""
    y = overlay if overlay is not None else _load_yaml_overlay()
    base = DecisionShadowConfig(
        enabled=bool(y.get("enabled", False)),
        sample_rate=float(y.get("sample_rate", 0.01)),
        trigger=str(y.get("trigger", "t3_or_t2_boundary")),
        queue_size=int(y.get("queue_size", 64)),
        timeout_ms=int(y.get("timeout_ms", 200)),
        endpoint=str(y.get("endpoint", "") or ""),
        model=str(y.get("model", "") or ""),
        audit_ttl_hours=int(y.get("audit_ttl_hours", 72)),
        store_raw_text=bool(y.get("store_raw_text", False)),
    )
    return DecisionShadowConfig(
        enabled=_env_bool("AIPLAT_DECISION_SHADOW_ENABLED", base.enabled),
        sample_rate=_env_float("AIPLAT_DECISION_SHADOW_SAMPLE_RATE", base.sample_rate),
        trigger=os.getenv("AIPLAT_DECISION_SHADOW_TRIGGER", base.trigger)
        or base.trigger,
        queue_size=_env_int("AIPLAT_DECISION_SHADOW_QUEUE_SIZE", base.queue_size),
        timeout_ms=_env_int("AIPLAT_DECISION_SHADOW_TIMEOUT_MS", base.timeout_ms),
        endpoint=os.getenv("AIPLAT_DECISION_SHADOW_ENDPOINT", base.endpoint)
        or base.endpoint,
        model=os.getenv("AIPLAT_DECISION_SHADOW_MODEL", base.model) or base.model,
        audit_ttl_hours=_env_int(
            "AIPLAT_DECISION_SHADOW_AUDIT_TTL_HOURS", base.audit_ttl_hours
        ),
        store_raw_text=_env_bool(
            "AIPLAT_DECISION_SHADOW_STORE_RAW_TEXT", base.store_raw_text
        ),
    )
