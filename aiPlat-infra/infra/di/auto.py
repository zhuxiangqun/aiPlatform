"""
Auto registration utilities for infra.di.

Provides:
- @injectable decorator to mark services for auto-registration
- list_injectables() for DI container bootstrap

Design goal: keep it lightweight and config-driven (scan_packages imports modules,
modules register injectables during import).
"""

from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Type

from .schemas import Lifetime


@dataclass(frozen=True)
class InjectableSpec:
    service: Type
    implementation: Type
    lifetime: Lifetime = Lifetime.SINGLETON


_INJECTABLES: List[InjectableSpec] = []


def injectable(
    cls: Optional[Type] = None,
    *,
    service: Optional[Type] = None,
    lifetime: Lifetime = Lifetime.SINGLETON,
) -> Callable[[Type], Type]:
    """
    Decorator to register a class as injectable.

    Usage:
        @injectable
        class Foo: ...

        @injectable(service=IFoo, lifetime=Lifetime.SINGLETON)
        class FooImpl(IFoo): ...
    """

    def _wrap(target: Type) -> Type:
        spec = InjectableSpec(service=service or target, implementation=target, lifetime=lifetime)
        _INJECTABLES.append(spec)
        return target

    if cls is None:
        return _wrap
    return _wrap(cls)


def list_injectables() -> List[InjectableSpec]:
    return list(_INJECTABLES)

