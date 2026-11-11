---
doc_type: Architecture
---

# Workspace Isolation Contract — Local Workspaces and Remote Profiles

> **Status**: Phase 1 local + Phase 2 remote Core proxy are implementable under this contract.  
> **Scope**: Phase 1 local named workspaces; Phase 2 remote Core profiles (allowlisted proxy).  
> **Decision**: the workspace selector first appears on Eval Center Agent pages.  
> **Principle**: an ID on a request does not prove that the whole read/write chain is isolated.

## 1. Terms

| Term | Meaning |
|---|---|
| workspace | A local data partition for selected data such as agents and evaluation results. It is not a tenant or a Git repository. |
| tenant | Identity, authorization, and quota boundary. Tenant remains independent of workspace. |
| profile | Phase 2 remote Core connection record (`kind: remote`, `base_url`); selecting one changes the API target. |
| `default` | Compatibility local workspace mapped to the existing `$AIPLAT_HOME/agents` and `$AIPLAT_HOME/eval_results`. |
| `WorkspaceContext` | Validated request/execution value carrying workspace identity, resolved root/paths, kind, and authorization context. |

## 2. Request resolution and defaults

Resolution precedence is `X-Aiplat-Workspace-Id` header, then `workspace_id` query parameter. If both are present, the header wins. The resolved ID must be syntactically valid, registered, local for Phase 1, and authorized before any workspace data is accessed.

| Request | Missing ID | Unknown ID |
|---|---|---|
| `GET` / `HEAD` | Resolve to `default` for legacy read compatibility | `404 workspace_not_found` |
| `POST` / `PUT` / `PATCH` / `DELETE` | `400 workspace_required` | `404 workspace_not_found` |
| Explicit `workspace_id=default` | Allowed | — |

Writes must never silently land in `default`. If a temporary legacy-write compatibility flag is required, it must be opt-in, time-bounded, and emit an audit log for every affected write. It must not be enabled by default.

## 3. Path resolution

`AIPLAT_HOME` remains the process-level home and is never changed per request. The registry is `$AIPLAT_HOME/workspaces/registry.yaml`. The `default` workspace maps to existing paths without migration. Other local IDs map to `$AIPLAT_HOME/workspaces/{id}/agents` and `$AIPLAT_HOME/workspaces/{id}/eval_results`.

Registry roots may be relative to `AIPLAT_HOME` or absolute, but resolution must normalize to an absolute real path and enforce the configured allowed prefix. Reject `..`, symlink escape, non-local roots in Phase 1, and paths that resolve outside the allowed root. Workspace IDs must be validated as single safe path components; callers cannot supply arbitrary roots through request data.

Path APIs should accept an explicit `WorkspaceContext` or resolved root. ContextVar lookup is convenience fallback only; a write path must not use a missing context to silently choose `default`.

## 4. Authorization (workspace is not tenant)

`tenant_id` remains independent. Every resolution checks the authenticated actor/tenant against workspace ACL; the workspace header is a selector, not a credential. Phase 1 ACL policy must be explicit in the registry or an equivalent server-side policy. The initial policy may restrict non-default workspaces to configured actors/tenants; `default` compatibility must not bypass existing authentication or tenant checks.

Unauthorized access returns `403 workspace_forbidden` (the Phase 1 decision; a later security review may choose concealment semantics). Authorization is required for list, read, write, job enqueue, and job execution. ACL changes must take effect without relying on stale authorization cache entries.

## 5. Async propagation and explicit context

HTTP middleware resolves and authorizes the workspace, creates `WorkspaceContext`, and may install it in a ContextVar for synchronous call-site convenience. Middleware must reset the ContextVar in `finally` using its token.

Service and worker APIs must receive `workspace: WorkspaceContext` explicitly. Queue jobs persist `workspace_id` (and enough validated identity metadata to re-resolve ACL at execution); workers resolve the ID against the registry and reauthorize before accessing data. Child processes receive explicit validated arguments/environment. Thread pools, background tasks, queues, and subprocesses must not treat the ambient ContextVar as the sole source of truth. A missing or invalid workspace in a write job fails closed.

## 6. Phase 1 data boundary

| Data | Isolated in Phase 1? | Boundary |
|---|---:|---|
| `agents/` | Yes | Workspace-specific root |
| `eval_results/` | Yes | Workspace-specific root |
| Eval Center reports/history backed by eval result files | Yes | Stored beneath the workspace `eval_results/` boundary |
| Traces | No | Shared globally in Phase 1 |
| Cache | No | Shared globally; any path/result cache key must include `workspace_id` where its value depends on workspace data |
| Temporary files / attachments | No | Shared globally in Phase 1 |
| Non-evaluation indexes / databases | No | Shared globally in Phase 1 |
| Global model configuration / credentials | No | Deployment-level shared configuration, not workspace data |

The Eval Center must display: **“本工作区一期只隔离 Agent 与评测结果；traces/缓存/附件/其它 DB 仍共享。”** A report or trace stored outside the isolated boundary must not be presented as workspace-private.

## 7. Registry, concurrency, and cache invalidation

Registry schema includes `schema_version`; malformed, unsupported, or partially written registry state fails closed and must not silently synthesize a replacement that changes workspace mapping. First-run initialization may create a `default`-only registry atomically.

Registry writes use an inter-process file lock, a same-directory temporary file, flush/fsync as supported, and atomic rename. Workspace creation is idempotent by ID and must reject conflicting definitions. Set registry permissions to `0600` and workspace directories to `0700` where supported; document platform limitations.

Any resolved-path cache is keyed by workspace ID and registry version (or invalidated on registry mutation). On workspace switch, the UI aborts in-flight requests, clears selected Agent/report/history state, then reloads. Server-side AgentManager and path caches that can retain workspace-scoped values must be workspace-keyed or explicitly invalidated.

## 8. API and error contract

Workspace management is exposed through the CoreFacade boundary. `GET /core/workspaces` returns only workspaces visible to the caller; reads without a selector use the `default` request context but may return the caller's full authorized workspace list. `POST /core/workspaces` is a write and requires an explicit workspace context or an explicitly defined bootstrap/admin rule; it creates a local empty workspace only.

| Error | HTTP | Meaning |
|---|---:|---|
| `workspace_required` | 400 | A write request omitted the workspace selector |
| `workspace_not_found` | 404 | The selected workspace is not registered or available in this phase |
| `workspace_forbidden` | 403 | Authenticated actor/tenant lacks access |

Capability documentation and `capability_registry.yaml` are updated with the implementation, not as a substitute for enforcing this contract.

## 9. Phase 1 UI contract

The selector first appears in Eval Center Agent list/exam flows. Persist the selected local ID in localStorage. All related list, exam, score, history, and attributable-report requests carry the same `X-Aiplat-Workspace-Id`; writes require an explicit selection and send the header. Shared apiClient support should be used where practical so calls cannot omit it accidentally.

On switch: abort old requests, clear Agent/report/history selections, then reload. Late responses from the prior workspace must be ignored. Explain that workspace is a local Agent/evaluation-result partition, not a tenant or Git repository, and show the shared-data notice from §6.

## 10. Phase 2 remote profile contract

Remote profiles use `kind: remote` with server-managed `id`, `label`, `base_url`, and optional `auth_secret_env` (env var name for Bearer/token; never stored in plaintext in the registry beyond the env key). Optional `allowed_routes` may **tighten** the built-in Eval allowlist; it must not expand beyond the built-in set.

### 10.1 Semantics

- Selecting a remote profile changes the **API target** (which aiPlat Core host), not a local disk partition.
- A local `X-Aiplat-Workspace-Id` is **never** forwarded to the remote Core.
- The remote Core uses its own default data context. Nested remote named-workspace semantics are out of scope.
- Orthogonal to external-agent pull eval (`http_chat_pull`): that calls third-party Agents; remote Core proxies aiPlat APIs.

### 10.2 Resolve rules

- `resolve_named_workspace` for `kind: remote` does **not** map to local `agents/` / `eval_results/`.
- Context carries `kind=remote`, `base_url`, and empty/sentinel local paths.
- Services that require local disk paths must refuse remote contexts with an explicit error (not silent default).

### 10.3 Proxy (sole egress)

- Route: `/core/workspace-proxy/{profile_id}/{path}` (GET/POST only).
- Built-in allowlist (method + path pattern):
  - GET: `/core/workspace/agents`, `/core/evaluation/sets`, `/core/evaluation/agents/{id}/score|history|attributable-report`, `/core/evaluation/external-targets`
  - POST: `/core/evaluation/exam`, `/core/evaluation/external-exam`, `/core/evaluation/external-targets`
- Rebuild URL from registered `base_url` + allowlisted path; SSRF via `is_blocked_url`; redirects disabled; body/timeout caps.
- Dev escape: `AIPLAT_REMOTE_CORE_ALLOW_PRIVATE=1` (audit-logged).
- Inject server-side `Authorization` from `auth_secret_env` when set; strip inbound `X-Aiplat-Workspace-Id`.
- Audit: `profile_id + tenant + actor + method + path + host`.
- Failures are explicit; **never** silently fall back to local `default`.

### 10.4 UI

- Eval picker lists local and remote; remote shows host label.
- When remote is selected, Eval API calls use the proxy prefix; local registry create/list still hit this Core.
- Copy: 「远程 Core = 换 API 目标；≠ 本机分区；≠ 外部拉模式 Agent。」

## Acceptance gates

Phase 1 is not complete until evidence shows: legacy reads without a selector resolve to the existing `default` paths; writes without a selector return `400 workspace_required`; `default` and a created workspace have isolated Agent and evaluation-result reads/writes/history; unauthorized access returns `403`; async jobs preserve and revalidate workspace identity; and the UI prevents stale responses/state after switching. Tests should include concurrent requests, unknown IDs, malformed registry, and path/symlink escape attempts.

Phase 2: remote list/exam reach the selected remote Core via proxy; switching back restores local `default`; unregistered destinations and non-allowlisted routes are rejected; local workspace header is not present on outbound proxy requests. Phase 2 does not authorize arbitrary SSH, arbitrary proxying, or cross-workspace aggregate rankings.
