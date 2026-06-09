import type { Agent, Skill, ToolInfo } from '../services';

function _short(s: string, max = 20): string {
  return s.length > max ? s.slice(0, max) + '…' : s;
}

/**
 * Get a human-readable source/origin label for agents, skills, tools, and MCP.
 *
 * Unified logic used across all Core and Workspace listing pages.
 *
 * Labels:
 *   engine, no source  → 引擎内置
 *   workspace, local    → 本地
 *   workspace, external  → 导入 · <source>
 *   engine, external     → 引擎 · <source>
 */
export function getSourceLabel(
  provenance?: { scope?: string; source?: string } | null
): string {
  const scope = provenance?.scope || '';
  const source = provenance?.source || '';

  // Workspace items with external source (git/zip import)
  if (scope === 'workspace' && source && source !== 'local') {
    return `导入 · ${_short(source)}`;
  }
  // Engine items with external source (rare — git-imported engine entity)
  if (scope === 'engine' && source && source !== 'builtin') {
    return `引擎 · ${_short(source)}`;
  }
  // Standard engine built-in
  if (scope === 'engine') return '引擎内置';
  // Standard workspace local creation
  if (scope === 'workspace') return '本地';
  // Fallback
  if (source && source !== 'local' && source !== 'builtin') return _short(source);
  return '-';
}

/**
 * Extract provenance from agent/skill metadata or tool/MCP provenance.
 */
export function extractProvenance(
  record: Agent | Skill | ToolInfo | any
): { scope?: string; source?: string } {
  // Agent / Skill: metadata.provenance
  const metaProv = (record as any)?.metadata?.provenance;
  if (metaProv && typeof metaProv === 'object' && !Array.isArray(metaProv)) {
    return metaProv as { scope?: string; source?: string };
  }
  // Tool / MCP: provenance (top-level)
  if ((record as any)?.provenance && typeof (record as any).provenance === 'object' && !Array.isArray((record as any).provenance)) {
    return (record as any).provenance as { scope?: string; source?: string };
  }
  // Fallback: scope from record
  return { scope: ((record as any)?.scope as string) || '' };
}
