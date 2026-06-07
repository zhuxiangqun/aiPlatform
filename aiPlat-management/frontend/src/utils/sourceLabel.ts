import type { Agent, Skill, ToolInfo } from '../services';

/**
 * Get a human-readable source/origin label for agents, skills, and tools.
 * 
 * Unified logic used across all Core and Workspace listing pages.
 */
export function getSourceLabel(
  provenance?: { scope?: string; source?: string } | null
): string {
  const scope = provenance?.scope || '';
  if (scope === 'engine') return '引擎内置';
  const source = provenance?.source || '';
  if (source) return source.length > 20 ? source.slice(0, 20) + '…' : source;
  if (scope === 'workspace') return '本地创建';
  return '-';
}

/**
 * Extract provenance from agent/skill metadata or tool provenance.
 */
export function extractProvenance(
  record: Agent | Skill | ToolInfo | any
): { scope?: string; source?: string } {
  // Agent / Skill: metadata.provenance
  const metaProv = (record as any)?.metadata?.provenance;
  if (metaProv && typeof metaProv === 'object' && !Array.isArray(metaProv)) {
    return metaProv as { scope?: string; source?: string };
  }
  // Tool: provenance (top-level)
  if ((record as any)?.provenance && typeof (record as any).provenance === 'object' && !Array.isArray((record as any).provenance)) {
    return (record as any).provenance as { scope?: string; source?: string };
  }
  // Fallback: scope from record
  return { scope: ((record as any)?.scope as string) || '' };
}
