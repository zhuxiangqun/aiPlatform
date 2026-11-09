"""Load mock tool catalog seeds (JSON or YAML)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from core.apps.eval.service.capability_case_bank import default_seed_dir
from core.apps.eval.service.mock_tools.schema import (
    assert_mock_tool_catalog_valid,
    validate_mock_tool_catalog,
)


class MockToolCatalogError(ValueError):
    """Catalog load / parse failure (fail closed)."""


def default_mock_tools_dir() -> Path:
    return default_seed_dir() / "fixtures" / "mock_tools"


def load_mock_tool_catalog(
    *,
    path: Optional[Path] = None,
    seed_dir: Optional[Path] = None,
    validate: bool = True,
) -> Dict[str, Any]:
    """Load catalog.sample.json (default) or explicit path.

    Prefer JSON; ``.yaml``/``.yml`` requires PyYAML.
    """
    if path is None:
        root = Path(seed_dir) if seed_dir else default_mock_tools_dir()
        path = root / "catalog.sample.json"
    path = Path(path)
    if not path.is_file():
        raise MockToolCatalogError(f"mock catalog missing: {path}")
    raw = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    try:
        if suffix in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore
            except ImportError as exc:
                raise MockToolCatalogError("PyYAML required for .yaml catalog") from exc
            doc = yaml.safe_load(raw)
        else:
            doc = json.loads(raw)
    except (json.JSONDecodeError, Exception) as exc:
        if isinstance(exc, MockToolCatalogError):
            raise
        raise MockToolCatalogError(f"mock catalog parse failed: {path}: {exc}") from exc
    if not isinstance(doc, Mapping):
        raise MockToolCatalogError("mock catalog must be an object")
    out = dict(doc)
    if validate:
        errs = validate_mock_tool_catalog(out)
        if errs:
            raise MockToolCatalogError(
                "mock_tool_catalog_invalid:" + ",".join(errs)
            )
        assert_mock_tool_catalog_valid(out)
    return out
