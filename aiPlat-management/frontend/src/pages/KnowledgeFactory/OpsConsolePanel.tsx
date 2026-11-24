/**
 * OpsConsolePanel — N24 运维台薄壳管理端 UI。
 *
 * 经 FDE `/ops-console*` → CoreFacade；聚合统一审计近窗 + SLO 概况；
 * 可选有界导出（AIPLAT_KNOWLEDGE_OPS_CONSOLE_EXPORT=1）。
 * 不宣称全量运维台 / 通用下载产品化 / certified。
 */
import React, { useCallback, useState } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import { Download, Gauge, RefreshCw } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

type OpsSnapshot = {
  status?: string;
  via?: string;
  note?: string;
  window_hours?: number;
  certified?: boolean;
  n24_full_conformance?: boolean;
  n24_unified_audit_freeze?: boolean;
  full_ops_console?: boolean;
  export_complete?: boolean;
  wrote?: boolean;
  output_path?: string | null;
  audit?: { recent_count?: number; listed?: number; window_hours?: number };
  slo?: {
    snapshot_status?: string;
    miss_metrics?: string[];
    miss_count?: number;
  };
  panels?: Record<string, boolean>;
};

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'reason' in detail) {
    return String((detail as { reason?: unknown }).reason || JSON.stringify(detail));
  }
  return detail ? JSON.stringify(detail) : '请求失败';
}

const OpsConsolePanel: React.FC = () => {
  const [tenantId, setTenantId] = useState('lock-service');
  const [domainId, setDomainId] = useState('');
  const [windowHours, setWindowHours] = useState(24);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [snap, setSnap] = useState<OpsSnapshot | null>(null);
  const [gateNote, setGateNote] = useState('');
  const [exportNote, setExportNote] = useState('');

  const reload = useCallback(async () => {
    if (!tenantId.trim()) return;
    setLoading(true);
    try {
      const p = new URLSearchParams({
        tenant_id: tenantId.trim(),
        window_hours: String(windowHours || 24),
        include_live: 'false',
      });
      if (domainId.trim()) p.set('domain_id', domainId.trim());
      const r = await fetch(API(`/ops-console/snapshot?${p.toString()}`));
      const body = (await r.json().catch(() => ({}))) as OpsSnapshot & {
        detail?: unknown;
      };
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setSnap(body);
    } catch (e: unknown) {
      setSnap(null);
      toast?.error?.((e as Error)?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, [tenantId, domainId, windowHours]);

  const runGate = useCallback(async () => {
    try {
      const r = await fetch(API('/ops-console/gate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      const ok = body.ok === true;
      setGateNote(
        ok
          ? `gate ok · certified=${String(body.certified)} · full=${String(body.full_ops_console)}`
          : `gate fail · ${(body.issues || []).join(',') || 'unknown'}`,
      );
    } catch (e: unknown) {
      setGateNote((e as Error)?.message || 'gate 失败');
    }
  }, []);

  const runExport = useCallback(async () => {
    if (!tenantId.trim()) return;
    setExporting(true);
    try {
      const r = await fetch(API('/ops-console/export'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: tenantId.trim(),
          domain_id: domainId.trim(),
          window_hours: windowHours || 24,
          include_live: false,
          write: true,
        }),
      });
      const body = (await r.json().catch(() => ({}))) as OpsSnapshot & {
        detail?: unknown;
      };
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setExportNote(
        body.status === 'ok'
          ? `export ok · wrote=${String(body.wrote)} · path=${String(body.output_path || '—')} · complete=${String(body.export_complete)}`
          : `export ${String(body.status)} · ${body.note || ''}`,
      );
    } catch (e: unknown) {
      setExportNote((e as Error)?.message || '导出失败');
    } finally {
      setExporting(false);
    }
  }, [tenantId, domainId, windowHours]);

  return (
    <Card className="border-gray-800 bg-gray-950/40">
      <CardHeader className="flex flex-row items-center justify-between gap-2 py-3">
        <div className="flex items-center gap-2 text-[13px] text-gray-200">
          <Gauge className="h-4 w-4 text-emerald-400/80" />
          <span>运维台薄壳（N24 residual）</span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => void runGate()}
          >
            Gate
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={exporting || !tenantId.trim()}
            onClick={() => void runExport()}
          >
            <Download className={`h-3.5 w-3.5 mr-1 ${exporting ? 'animate-pulse' : ''}`} />
            导出
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={loading}
            onClick={() => void reload()}
          >
            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-[12px] text-gray-400">
        <p className="text-gray-500">
          聚合统一审计近窗计数与 SLO 达标概况；可选有界 JSON 导出。非全量运维台 /
          非通用下载产品化 / 非 certified。壳：AIPLAT_KNOWLEDGE_OPS_CONSOLE=1；导出：
          AIPLAT_KNOWLEDGE_OPS_CONSOLE_EXPORT=1。
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
            <span>domain（可选）</span>
            <input
              className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={domainId}
              onChange={(e) => setDomainId(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>window_hours</span>
            <input
              type="number"
              min={1}
              max={720}
              className="w-24 rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={windowHours}
              onChange={(e) => setWindowHours(Number(e.target.value) || 24)}
            />
          </label>
        </div>
        {gateNote ? <p className="text-gray-500">{gateNote}</p> : null}
        {exportNote ? <p className="text-gray-500">{exportNote}</p> : null}
        {snap ? (
          <div className="rounded border border-gray-800 bg-black/30 p-3 space-y-2 font-mono text-[11px]">
            <div>
              status={String(snap.status)} · via={String(snap.via || '—')} ·
              certified={String(snap.certified)} · full_ops=
              {String(snap.full_ops_console)} · freeze=
              {String(snap.n24_unified_audit_freeze)}
            </div>
            {snap.status === 'ok' ? (
              <>
                <div>
                  audit.recent={String(snap.audit?.recent_count ?? 0)} /
                  listed={String(snap.audit?.listed ?? 0)}
                </div>
                <div>
                  slo.status={String(snap.slo?.snapshot_status || '—')} ·
                  miss={String(snap.slo?.miss_count ?? 0)}
                  {(snap.slo?.miss_metrics || []).length
                    ? ` [${(snap.slo?.miss_metrics || []).join(', ')}]`
                    : ''}
                </div>
                <div>
                  panels=
                  {JSON.stringify(snap.panels || {})}
                </div>
              </>
            ) : (
              <div className="text-amber-400/90">{snap.note || snap.status}</div>
            )}
          </div>
        ) : (
          <p className="text-gray-600">点击刷新加载运维台快照。</p>
        )}
      </CardContent>
    </Card>
  );
};

export default OpsConsolePanel;
