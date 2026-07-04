# P3-17: Effect-TS Layer DI Research

## Context

OpenCode (anomalyco/opencode) uses **Effect-TS** for dependency injection:
- `Context.Service<Service, Interface>()` — defines typed service contracts
- `Layer.effect(Service, ...)` — creates concrete implementations with dependencies
- `Effect.gen(function* ...)` — generator-based effectful programming
- `InstanceState.make()` — lazy per-instance state management

aiPlat currently uses **Service Locator** pattern:
- Global singletons: `get_skill_registry()`, `get_tool_registry()`, `get_model_registry()`
- `CoreFacade` as the boundary between platform and core
- `_resolve_or_import()` for late-bound dependency resolution
- Explicit `try/except ImportError` for optional dependencies

## Comparison

| Dimension | Effect-TS Layer | aiPlat Service Locator |
|-----------|----------------|----------------------|
| **Type safety** | Compile-time via Schema.Struct | Runtime only (Python typing, no compile-time DI) |
| **Testability** | Layer substitution for complete mock isolation | Monkey-patch global singletons |
| **Lifecycle** | Layer provides scoped lifecycle (per-request, per-test) | Singletons live for process lifetime |
| **Discoverability** | `.pipe(Layer.provide(Config))` chains visible at use site | Implicit via `get_*_registry()` calls scattered |
| **Cross-process** | Not applicable (JS runtimes) | Two-process (core + platform) — singletons must be seeded in both |

## Recommendation: Gradual Migration Path

### Phase 1: Introduce `dependency-injector` (Python library)
- Replace `get_skill_registry()` global calls with `container.skill_registry()`
- Centralize all singleton access through declarative `providers.Singleton`
- This gives visible wiring without needing TypeScript-level type safety

### Phase 2: Extract `WiringContainer`
- One `Container` per process (core, platform)
- Declares all providers explicitly
- Platform can override specific providers for testing

### Phase 3: Scoped lifetimes
- Add `RequestScoped` providers for per-request state (trace_id, tenant)
- Clean up manual trace_id threading through function args

### Expected Benefits
- Visible dependency graph (no more hidden implicit imports)
- Test isolation without monkey-patching
- Platform can supply mock `ModelRouter` for E2E tests

### Risk Assessment
- Low: Service Locator → DI Container is a well-understood migration
- Medium: Need to convert ~30 `get_*_registry()` call sites
- Tool: `dependency-injector` is mature, ~3K GitHub stars, maintained since 2019

## Status

- **Decision**: Adopt `dependency-injector` for Phase 1, defer Layer-style DI
- **Reason**: Python lacks TypeScript's structural typing; benefit/cost of full Effect-TS port is unclear
- **Implementation**: Separate project, not part of current optimization cycle
