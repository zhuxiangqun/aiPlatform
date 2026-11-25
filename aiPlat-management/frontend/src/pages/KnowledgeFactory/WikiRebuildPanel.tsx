/**
 * WikiRebuildPanel — N05 Wiki 有条件重建产品面管理端 UI。
 *
 * 默认走 `/wiki-rebuild/product/*`（无 residual env 门）。
 * wiki_rebuild_product_surface / wiki_fts_product_sync=true；
 * wiki_engine_fts_full / certified 恒 false。
 */
import React, { useCallback, useState } from 'react';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { BookOpen } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'reason' in detail) {
    return String((detail as { reason?: unknown }).reason || JSON.stringify(detail));
  }
  return detail ? JSON.stringify(detail) : '请求失败';
}

const WikiRebuildPanel: React.FC = () => {
  const [tenantId, setTenantId] = useState('demo-tenant');
  const [domainId, setDomainId] = useState('lock-service');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [pagesNote, setPagesNote] = useState('');
  const [gateNote, setGateNote] = useState('');

  const runProject = useCallback(async () => {
    if (!tenantId.trim() || !domainId.trim()) return;
    setBusy(true);
    try {
      const q = new URLSearchParams({
        tenant_id: tenantId.trim(),
        domain_id: domainId.trim(),
      });
      const r = await fetch(API(`/wiki-rebuild/product?${q}`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clear_projected: true, rebuild_mode: 'exact_replay_from_facts' }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setNote(
        `status=${String(body.status)} · written=${String(body.written)} · fts=${String(body.fts_synced)} · product=${String(body.wiki_rebuild_product_surface)} · fts_sync=${String(body.wiki_fts_product_sync)} · fts_full=${String(body.wiki_engine_fts_full)} · certified=${String(body.certified)}`,
      );
    } catch (e: unknown) {
      setNote((e as Error)?.message || '投影失败');
    } finally {
      setBusy(false);
    }
  }, [tenantId, domainId]);

  const runList = useCallback(async () => {
    if (!tenantId.trim()) return;
    try {
      const q = new URLSearchParams({
        tenant_id: tenantId.trim(),
        domain_id: domainId.trim(),
        limit: '20',
      });
      const r = await fetch(API(`/wiki-rebuild/product/pages?${q}`));
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setPagesNote(
        `total=${String(body.total)} · product=${String(body.wiki_rebuild_product_surface)} · certified=${String(body.certified)}`,
      );
    } catch (e: unknown) {
      setPagesNote((e as Error)?.message || '列表失败');
    }
  }, [tenantId, domainId]);

  const runFts = useCallback(async () => {
    setBusy(true);
    try {
      const r = await fetch(API('/wiki-rebuild/product/fts'), { method: 'POST' });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setNote(
        `fts status=${String(body.status)} · indexed=${String(body.indexed)} · rebuild=${String(body.wiki_fts_product_rebuild)} · fts_full=${String(body.wiki_engine_fts_full)} · certified=${String(body.certified)}`,
      );
    } catch (e: unknown) {
      setNote((e as Error)?.message || 'FTS 重建失败');
    } finally {
      setBusy(false);
    }
  }, []);

  const runGate = useCallback(async () => {
    try {
      const r = await fetch(API('/wiki-rebuild/product/gate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setGateNote(
        body.ok === true
          ? `product gate ok · surface=${String(body.wiki_rebuild_product_surface)} · fts_sync=${String(body.wiki_fts_product_sync)} · fts_full=${String(body.wiki_engine_fts_full)} · certified=${String(body.certified)}`
          : `product gate fail · ${(body.issues || []).join(',') || 'unknown'}`,
      );
    } catch (e: unknown) {
      setGateNote((e as Error)?.message || 'gate 失败');
    }
  }, []);

  return (
    <Card className="border-gray-800 bg-gray-950/40">
      <CardHeader className="flex flex-row items-center justify-between gap-2 py-3">
        <div className="flex items-center gap-2 text-[13px] text-gray-200">
          <BookOpen className="h-4 w-4 text-sky-400/80" />
          <span>Wiki 有条件重建产品面（N05）</span>
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={() => void runGate()}>
          Gate
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 text-[12px] text-gray-400">
        <p className="text-gray-500">
          默认可用：Fact→派生页 + 写页后有界 FTS upsert。wiki_rebuild_product_surface /
          wiki_fts_product_sync=true；非 wiki_engine_fts_full / 非 certified。
        </p>
        <div className="flex flex-wrap gap-2 items-end">
          <label className="flex flex-col gap-1">
            <span>tenant</span>
            <input
              className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>domain</span>
            <input
              className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={domainId}
              onChange={(e) => setDomainId(e.target.value)}
            />
          </label>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy || !tenantId.trim() || !domainId.trim()}
            onClick={() => void runProject()}
          >
            Project
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!tenantId.trim()}
            onClick={() => void runList()}
          >
            List
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => void runFts()}
          >
            Rebuild FTS
          </Button>
        </div>
        {note ? <p className="font-mono text-[11px] text-gray-500">{note}</p> : null}
        {pagesNote ? <p className="font-mono text-[11px] text-gray-500">{pagesNote}</p> : null}
        {gateNote ? <p className="text-gray-500">{gateNote}</p> : null}
      </CardContent>
    </Card>
  );
};

export default WikiRebuildPanel;
