/**
 * Named workspace partition — local Agent/eval_results + remote Core profiles.
 * Contract: docs/architecture/plans/workspace-isolation-contract.md
 */

export const NAMED_WORKSPACE_HEADER = 'X-Aiplat-Workspace-Id';
export const NAMED_WORKSPACE_STORAGE_KEY = 'aiplat.eval.named_workspace_id';
export const NAMED_WORKSPACE_KIND_KEY = 'aiplat.eval.named_workspace_kind';
export const NAMED_WORKSPACE_BOUNDARY =
  '本工作区一期只隔离 Agent 与评测结果；traces/缓存/附件/其它 DB 仍共享。';
export const REMOTE_CORE_BOUNDARY =
  '远程 Core = 换 API 目标；≠ 本机分区；≠ 外部拉模式 Agent。';

export type NamedWorkspaceKind = 'local' | 'remote';

export function getStoredNamedWorkspaceId(): string {
  try {
    const v = (localStorage.getItem(NAMED_WORKSPACE_STORAGE_KEY) || '').trim();
    return v || 'default';
  } catch {
    return 'default';
  }
}

export function getStoredNamedWorkspaceKind(): NamedWorkspaceKind {
  try {
    const v = (localStorage.getItem(NAMED_WORKSPACE_KIND_KEY) || '').trim().toLowerCase();
    return v === 'remote' ? 'remote' : 'local';
  } catch {
    return 'local';
  }
}

export function isRemoteNamedWorkspace(): boolean {
  return getStoredNamedWorkspaceKind() === 'remote';
}

export function setStoredNamedWorkspaceId(id: string, kind: NamedWorkspaceKind = 'local'): void {
  const next = (id || '').trim() || 'default';
  const k: NamedWorkspaceKind = kind === 'remote' ? 'remote' : 'local';
  try {
    localStorage.setItem(NAMED_WORKSPACE_STORAGE_KEY, next);
    localStorage.setItem(NAMED_WORKSPACE_KIND_KEY, k);
  } catch {
    /* ignore */
  }
}

/** Headers for local partition. Remote business calls omit this (proxy strips anyway). */
export function namedWorkspaceHeaders(endpoint?: string): Record<string, string> {
  if (isRemoteNamedWorkspace()) {
    // Local registry create/list still hits this Core — bootstrap with default.
    if (endpoint && endpoint.startsWith('/core/workspaces')) {
      return { [NAMED_WORKSPACE_HEADER]: 'default' };
    }
    return {};
  }
  return { [NAMED_WORKSPACE_HEADER]: getStoredNamedWorkspaceId() };
}

/**
 * When a remote profile is selected, rewrite Eval API paths through the allowlisted proxy.
 * Leaves /core/workspaces and already-proxied paths on this Core.
 */
export function resolveEvalEndpoint(endpoint: string): string {
  const ep = endpoint || '';
  if (!isRemoteNamedWorkspace()) return ep;
  if (ep.startsWith('/core/workspaces')) return ep;
  if (ep.startsWith('/core/workspace-proxy/')) return ep;
  if (
    ep.startsWith('/core/workspace/agents') ||
    ep.startsWith('/core/evaluation/')
  ) {
    const id = encodeURIComponent(getStoredNamedWorkspaceId());
    const rest = ep.replace(/^\//, '');
    return `/core/workspace-proxy/${id}/${rest}`;
  }
  return ep;
}
