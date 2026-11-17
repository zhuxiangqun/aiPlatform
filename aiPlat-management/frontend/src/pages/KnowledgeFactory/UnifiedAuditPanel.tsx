/**
 * UnifiedAuditPanel — N24 Batch J4 统一审计只读管理端薄 UI。
 *
 * 经 FDE `/unified-audit*`（J3）→ CoreFacade；不写总线；不宣称 certified。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import { ListTree, RefreshCw } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

type UnifiedEvent = {
  stream?: string;
  event_id?: string;
  event_type?: string;
  occurred_at?: number | string;
  actor?: string;
  subject?: string;
};

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'reason' in detail) {
    return String((detail as { reason?: unknown }).reason || JSON.stringify(detail));
  }
  return detail ? JSON.stringify(detail) : '请求失败';
}

const STREAM_OPTIONS = [
  { id: 'all', label: '三流全部' },
  { id: 'package', label: 'package' },
  { id: 'action_execution', label: 'action_execution' },
  { id: 'revision_audit', label: 'revision_audit' },
] as const;

const UnifiedAuditPanel: React.FC = () => {
  const [tenantId, setTenantId] = useState('lock-service');
  const [streamFilter, setStreamFilter] = useState<string>('all');
  const [packageId, setPackageId] = useState('');
  const [actionPrefix, setActionPrefix] = useState('');
  const [events, setEvents] = useState<UnifiedEvent[]>([]);
  const [streams, setStreams] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [gateNote, setGateNote] = useState('');

  const q = (extra: Record<string, string> = {}) => {
    const p = new URLSearchParams({ tenant_id: tenantId.trim(), ...extra });
    return p.toString();
  };

  const reload = useCallback(async () => {
    if (!tenantId.trim()) return;
    setLoading(true);
    try {
      const extra: Record<string, string> = { limit: '80' };
      if (streamFilter !== 'all') extra.streams = streamFilter;
      if (packageId.trim()) extra.package_id = packageId.trim();
      if (actionPrefix.trim()) extra.action_id_prefix = actionPrefix.trim();
      const r = await fetch(API(`/unified-audit?${q(extra)}`));
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      if (body.certified === true || body.n24_full_conformance === true) {
        // 为什么：UI 侧诚实锁，与 suite/gate 一致
        toast?.error?.('汇合视图误标 certified — 违反诚实锁');
      }
      setEvents(body.events || []);
      setStreams(Array.isArray(body.streams) ? body.streams : []);
    } catch (e: unknown) {
      setEvents([]);
      setStreams([]);
      toast?.error?.((e as Error)?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, [tenantId, streamFilter, packageId, actionPrefix]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const runGate = async () => {
    setLoading(true);
    try {
      const suiteRes = await fetch(
        API(`/unified-audit/suite?${q({ tenant_id: tenantId.trim() || 'n24-unified-audit-tenant' })}`),
        { method: 'POST' },
      );
      const suite = await suiteRes.json().catch(() => ({}));
      if (!suiteRes.ok) throw new Error(detailMessage(suite.detail));
      const gateRes = await fetch(API('/unified-audit/gate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ suite }),
      });
      const gate = await gateRes.json().catch(() => ({}));
      if (!gateRes.ok) throw new Error(detailMessage(gate.detail));
      const certified = Boolean(gate.certified);
      setGateNote(`suite ok · gate certified=${certified}（J4 诚实锁：须为 false）`);
      if (certified) {
        toast?.error?.('gate.certified 为 true — 违反诚实锁');
      } else {
        toast?.success?.('门槛门诚实：certified=false');
      }
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || 'suite/gate 失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="border-gray-700/60 bg-gray-900/40">
      <CardHeader className="flex flex-row items-center justify-between gap-2 py-3 px-4">
        <div className="flex items-center gap-2 text-sm text-gray-200">
          <ListTree className="h-4 w-4 text-sky-300/90" />
          <span>Unified Audit 视图（N24 J4）</span>
          <span className="text-[11px] text-gray-500 font-normal">
            只读汇合 · 非写总线 · 非 certified
          </span>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={loading}
            onClick={() => void reload()}
          >
            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </Button>
          <Button type="button" variant="ghost" size="sm" disabled={loading} onClick={() => void runGate()}>
            suite/gate
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 px-4 pb-4">
        <p className="text-[11px] text-gray-500 leading-relaxed">
          展示 Package / ActionExecution / revision_audit 三流只读汇合。
          不写入统一总线表，也不合并 ActionStore <code className="text-gray-400">action_audit</code>。
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <label className="text-[11px] text-gray-400 space-y-1">
            tenant_id
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            streams
            <select
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={streamFilter}
              onChange={(e) => setStreamFilter(e.target.value)}
            >
              {STREAM_OPTIONS.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            package_id（可选）
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={packageId}
              onChange={(e) => setPackageId(e.target.value)}
              placeholder="filter package stream"
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            action_id_prefix（可选）
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={actionPrefix}
              onChange={(e) => setActionPrefix(e.target.value)}
              placeholder="e.g. knowledge_revision:"
            />
          </label>
        </div>

        {gateNote && (
          <div className="text-[11px] text-amber-200/80 border border-amber-800/40 rounded px-2 py-1.5">
            {gateNote}
          </div>
        )}

        <div className="text-[11px] text-gray-500">
          活动流：{streams.length ? streams.join(', ') : '—'} · 事件 {events.length}
        </div>

        {events.length === 0 ? (
          <div className="text-[11px] text-gray-500">暂无事件（检查 tenant / 过滤条件）</div>
        ) : (
          <ul className="max-h-56 overflow-auto space-y-1.5 text-[11px] font-mono text-gray-400">
            {events.map((ev, i) => (
              <li
                key={`${ev.stream || ''}-${ev.event_id || ''}-${i}`}
                className="rounded border border-gray-800/80 bg-gray-950/40 px-2 py-1.5"
              >
                <span className="text-sky-300/90">[{ev.stream || '?'}]</span>{' '}
                {ev.event_type || '?'} · {ev.subject || ev.event_id || '—'}
                {ev.actor ? ` · ${ev.actor}` : ''}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
};

export default UnifiedAuditPanel;
