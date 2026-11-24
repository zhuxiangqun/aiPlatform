/**
 * OpsConsolePanel — N24 运维台产品面第一刀管理端 UI。
 *
 * 默认走 `/ops-console/product/*`（无 residual env 门）：概览 / Schema / 导出。
 * full_ops_console=true；certified 恒 false。
 */
import React, { useCallback, useState } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import { Download, Gauge, RefreshCw, Save } from 'lucide-react';

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
  product_surface?: boolean;
  wrote?: boolean;
  output_path?: string | null;
  audit?: { recent_count?: number; listed?: number; window_hours?: number };
  slo?: {
    snapshot_status?: string;
    miss_metrics?: string[];
    miss_count?: number;
  };
  panels?: Record<string, boolean>;
  payload?: {
    download_filename?: string;
    [key: string]: unknown;
  };
};

type TabId = 'overview' | 'schema' | 'export';

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
  const [tab, setTab] = useState<TabId>('overview');
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [savingSchema, setSavingSchema] = useState(false);
  const [snap, setSnap] = useState<OpsSnapshot | null>(null);
  const [gateNote, setGateNote] = useState('');
  const [exportNote, setExportNote] = useState('');
  const [schemaNote, setSchemaNote] = useState('');
  const [objectTypeId, setObjectTypeId] = useState('OpsProbeType');
  const [schemaText, setSchemaText] = useState(
    '{\n  "object_type_id": "OpsProbeType",\n  "label": "",\n  "fields": []\n}\n',
  );

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
      const r = await fetch(API(`/ops-console/product/snapshot?${p.toString()}`));
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
      const r = await fetch(API('/ops-console/product/gate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      const ok = body.ok === true;
      setGateNote(
        ok
          ? `product gate ok · certified=${String(body.certified)} · full=${String(body.full_ops_console)}`
          : `product gate fail · ${(body.issues || []).join(',') || 'unknown'}`,
      );
    } catch (e: unknown) {
      setGateNote((e as Error)?.message || 'gate 失败');
    }
  }, []);

  const loadSchema = useCallback(async () => {
    if (!tenantId.trim() || !objectTypeId.trim()) return;
    try {
      const p = new URLSearchParams({
        tenant_id: tenantId.trim(),
        object_type_id: objectTypeId.trim(),
      });
      const r = await fetch(API(`/ops-console/product/schema?${p.toString()}`));
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      const defn = body.definition;
      if (defn && typeof defn === 'object') {
        setSchemaText(JSON.stringify(defn, null, 2) + '\n');
        setSchemaNote(
          `loaded · status=${String(body.status)} · items=${String((body.items || []).length)}`,
        );
      } else {
        setSchemaNote('no current definition; edit JSON then save as draft');
      }
    } catch (e: unknown) {
      setSchemaNote((e as Error)?.message || 'schema 加载失败');
    }
  }, [tenantId, objectTypeId]);

  const saveSchema = useCallback(async () => {
    if (!tenantId.trim() || !objectTypeId.trim()) return;
    setSavingSchema(true);
    try {
      let definition: Record<string, unknown>;
      try {
        definition = JSON.parse(schemaText) as Record<string, unknown>;
      } catch {
        throw new Error('schema JSON 无法解析');
      }
      const r = await fetch(API('/ops-console/product/schema'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: tenantId.trim(),
          object_type_id: objectTypeId.trim(),
          definition,
          actor: 'ops-console-ui',
          reason: 'ops console product schema save',
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setSchemaNote(
        `saved draft · version=${String(body.version || body.draft?.version || '—')}`,
      );
    } catch (e: unknown) {
      setSchemaNote((e as Error)?.message || 'schema 保存失败');
    } finally {
      setSavingSchema(false);
    }
  }, [tenantId, objectTypeId, schemaText]);

  const runExport = useCallback(async () => {
    if (!tenantId.trim()) return;
    setExporting(true);
    try {
      const r = await fetch(API('/ops-console/product/export'), {
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
      const payload = body.payload || {};
      const filename =
        String(payload.download_filename || `${tenantId.trim()}-ops-console-product.json`);
      const blob = new Blob([JSON.stringify(payload, null, 2) + '\n'], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      setExportNote(
        body.status === 'ok'
          ? `export ok · browser download=${filename} · wrote=${String(body.wrote)} · complete=${String(body.export_complete)}`
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
          <span>运维台产品面（N24 第一刀）</span>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" size="sm" variant="ghost" onClick={() => void runGate()}>
            Gate
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
          默认可用：概览 + ObjectType schema JSON 编辑 + 浏览器下载导出。
          full_ops_console=true；非 certified / 非可视化表单设计器。
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
        <div className="flex gap-2">
          {(
            [
              ['overview', '概览'],
              ['schema', 'Schema'],
              ['export', '导出'],
            ] as const
          ).map(([id, label]) => (
            <Button
              key={id}
              type="button"
              size="sm"
              variant={tab === id ? 'outline' : 'ghost'}
              onClick={() => setTab(id)}
            >
              {label}
            </Button>
          ))}
        </div>
        {gateNote ? <p className="text-gray-500">{gateNote}</p> : null}

        {tab === 'overview' ? (
          snap ? (
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
                  <div>panels={JSON.stringify(snap.panels || {})}</div>
                </>
              ) : (
                <div className="text-amber-400/90">{snap.note || snap.status}</div>
              )}
            </div>
          ) : (
            <p className="text-gray-600">点击刷新加载产品面快照（无需 residual env）。</p>
          )
        ) : null}

        {tab === 'schema' ? (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-2 items-end">
              <label className="flex flex-col gap-1">
                <span>object_type_id</span>
                <input
                  className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
                  value={objectTypeId}
                  onChange={(e) => setObjectTypeId(e.target.value)}
                />
              </label>
              <Button type="button" size="sm" variant="ghost" onClick={() => void loadSchema()}>
                加载
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={savingSchema}
                onClick={() => void saveSchema()}
              >
                <Save className="h-3.5 w-3.5 mr-1" />
                保存 draft
              </Button>
            </div>
            <textarea
              className="w-full min-h-[180px] rounded border border-gray-700 bg-gray-900 px-2 py-1 font-mono text-[11px] text-gray-200"
              value={schemaText}
              onChange={(e) => setSchemaText(e.target.value)}
            />
            {schemaNote ? <p className="text-gray-500">{schemaNote}</p> : null}
          </div>
        ) : null}

        {tab === 'export' ? (
          <div className="space-y-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={exporting || !tenantId.trim()}
              onClick={() => void runExport()}
            >
              <Download className={`h-3.5 w-3.5 mr-1 ${exporting ? 'animate-pulse' : ''}`} />
              浏览器下载 JSON
            </Button>
            {exportNote ? <p className="text-gray-500">{exportNote}</p> : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
};

export default OpsConsolePanel;
