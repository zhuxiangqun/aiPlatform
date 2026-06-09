/**
 * Unified status / category / governance display labels.
 *
 * Used by all Core and Workspace list pages for consistent rendering.
 */
import type React from 'react';

// ── Listing Status (上架状态) ──────────────────────────────────

export const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft:      { label: '草稿',   color: '#888' },
  ready:      { label: '待审核', color: '#f59e0b' },
  published:  { label: '已发布', color: '#3b82f6' },
  listed:     { label: '已上架', color: '#10b981' },
  deprecated: { label: '已废弃', color: '#6b7280' },
};

export function getStatusLabel(status?: string | null): string {
  return STATUS_MAP[status || '']?.label || status || '-';
}

export function getStatusColor(status?: string | null): string {
  return STATUS_MAP[status || '']?.color || '#6b7280';
}

/** Inline status badge (matching existing page style) */
export function StatusBadge({ status }: { status?: string | null }) {
  const color = getStatusColor(status);
  return React.createElement('span', {
    className: 'inline-flex px-2 py-0.5 rounded text-xs font-medium',
    style: { color, background: `${color}15`, border: `1px solid ${color}30` },
    children: getStatusLabel(status),
  });
}

// ── Governance (治理) ──────────────────────────────────────────

export function getGovLabel(prov: Record<string, any> | null | undefined): string {
  if (!prov) return '未签名';
  if (prov.signature_verified) return '已验签';
  if (prov.signature) return '已签名';
  return '未签名';
}

export function getGovColor(prov: Record<string, any> | null | undefined): string {
  if (!prov) return '#6b7280';
  if (prov.signature_verified) return '#10b981';
  if (prov.signature) return '#3b82f6';
  return '#6b7280';
}

export function getGovDetailLabel(record: Record<string, any> | null | undefined): { label: string; color: string } {
  if (!record) return { label: '未签名', color: '#6b7280' };
  const prov = (record.metadata as any)?.provenance || {};
  if (prov?.signature_verified === true) return { label: '已验签', color: '#10b981' };
  if (prov?.signature) return { label: '已签名', color: '#3b82f6' };
  const g = (record.metadata as any)?.governance || {};
  const v = (record.metadata as any)?.verification || {};
  const st = String((g?.status || v?.status || '')).toLowerCase();
  if (st === 'verified')  return { label: 'verified', color: '#10b981' };
  if (st === 'published') return { label: 'published', color: '#3b82f6' };
  if (st === 'failed')    return { label: 'failed', color: '#ef4444' };
  if (st === 'pending')   return { label: 'pending', color: '#f59e0b' };
  return { label: '未签名', color: '#6b7280' };
}

/** Rich governance badge (用于 Workspace Skills — 含 verification status) */
export function GovDetailBadge({ record }: { record?: Record<string, any> | null }) {
  const { label, color } = getGovDetailLabel(record);
  return React.createElement('span', {
    className: 'inline-flex px-2 py-0.5 rounded text-xs font-medium',
    style: { color, background: `${color}15`, border: `1px solid ${color}30` },
    children: label,
  });
}

/** Inline governance badge */
export function GovBadge({ prov }: { prov?: Record<string, any> | null }) {
  const color = getGovColor(prov);
  return React.createElement('span', {
    className: 'inline-flex px-2 py-0.5 rounded text-xs font-medium',
    style: { color, background: `${color}15`, border: `1px solid ${color}30` },
    children: getGovLabel(prov),
  });
}

// ── Category (分类) ────────────────────────────────────────────

export const CATEGORY_COLORS: Record<string, string> = {
  general: '#9ca3af', retrieval: '#3b82f6', analysis: '#8b5cf6',
  generation: '#10b981', execution: '#f59e0b', document: '#ec4899',
  design: '#06b6d4', text: '#84cc16', tool: '#f97316', communication: '#6366f1',
  coding: '#ef4444', reasoning: '#14b8a6', search: '#3b82f6',
};

export function getCategoryColor(category?: string | null): string {
  return CATEGORY_COLORS[category || ''] || '#9ca3af';
}
