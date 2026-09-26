"""Live ontology YAML write gate.

Direct writers (editor save, wiki dump, importer) are denied.
VersionedOntologyStore.apply_proposal / rollback_proposal set the allow token
around their own file writes.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_ALLOW: ContextVar[bool] = ContextVar("ontology_live_yaml_write", default=False)


class LiveYamlDirectWriteDenied(PermissionError):
    """Raised when code tries to overwrite live ontology YAML outside apply/rollback."""

    def __init__(self) -> None:
        super().__init__(
            "live ontology YAML write denied; approve a proposal then "
            "VersionedOntologyStore.apply_proposal. Direct save/import is not a write path."
        )


def live_yaml_write_allowed() -> bool:
    return bool(_ALLOW.get())


def assert_live_yaml_write() -> None:
    if not live_yaml_write_allowed():
        raise LiveYamlDirectWriteDenied()


@contextmanager
def allow_live_yaml_write() -> Iterator[None]:
    token = _ALLOW.set(True)
    try:
        yield
    finally:
        _ALLOW.reset(token)
