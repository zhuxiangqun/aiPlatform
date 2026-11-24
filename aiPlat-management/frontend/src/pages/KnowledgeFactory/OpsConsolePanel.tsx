/**
 * OpsConsolePanel — N24 运维台产品面管理端 UI。
 *
 * 默认走 `/ops-console/product/*`：概览 / Schema 表单+JSON / 导出。
 * full_ops_console=true；certified 恒 false。
 */
import React, { useCallback, useState } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import { Download, Gauge, Plus, RefreshCw, Save, Trash2 } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

const FIELD_TYPES = ['string', 'number', 'boolean', 'object', 'array'] as const;

type FieldType = (typeof FIELD_TYPES)[number];

type SchemaField = {
  name: string;
  type: FieldType;
  required: boolean;
  description: string;
};

type SchemaForm = {
  object_type_id: string;
  label: string;
  fields: SchemaField[];
};

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

function emptyForm(objectTypeId: string): SchemaForm {
  return { object_type_id: objectTypeId, label: '', fields: [] };
}

function coerceForm(raw: unknown, objectTypeId: string): SchemaForm {
  const body = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const fieldsIn = Array.isArray(body.fields) ? body.fields : [];
  const fields: SchemaField[] = [];
  for (const item of fieldsIn) {
    if (!item || typeof item !== 'object') continue;
    const row = item as Record<string, unknown>;
    const name = String(row.name || '').trim();
    if (!name) continue;
    const t = String(row.type || 'string').toLowerCase();
    const type = (FIELD_TYPES.includes(t as FieldType) ? t : 'string') as FieldType;
    fields.push({
      name,
      type,
      required: Boolean(row.required),
      description: String(row.description || ''),
    });
  }
  return {
    object_type_id: String(body.object_type_id || objectTypeId).trim() || objectTypeId,
    label: String(body.label || ''),
    fields,
  };
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
  const [schemaForm, setSchemaForm] = useState<SchemaForm>(() => emptyForm('OpsProbeType'));
  const [schemaText, setSchemaText] = useState(
    '{\n  "object_type_id": "OpsProbeType",\n  "label": "",\n  "fields": []\n}\n',
  );
  const [showJson, setShowJson] = useState(false);

  const syncJsonFromForm = useCallback((form: SchemaForm) => {
    setSchemaText(JSON.stringify(form, null, 2) + '\n');
  }, []);

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
      const form = coerceForm(body.form || body.definition, objectTypeId.trim());
      setSchemaForm(form);
      syncJsonFromForm(form);
      if (body.definition || body.form) {
        setSchemaNote(
          `loaded · form_fields=${String(form.fields.length)} · items=${String((body.items || []).length)}`,
        );
      } else {
        setSchemaNote('no current definition; edit form then save as draft');
      }
    } catch (e: unknown) {
      setSchemaNote((e as Error)?.message || 'schema 加载失败');
    }
  }, [tenantId, objectTypeId, syncJsonFromForm]);

  const saveSchema = useCallback(async () => {
    if (!tenantId.trim() || !objectTypeId.trim()) return;
    setSavingSchema(true);
    try {
      let formPayload = schemaForm;
      if (showJson) {
        try {
          const parsed = JSON.parse(schemaText) as Record<string, unknown>;
          formPayload = coerceForm(parsed, objectTypeId.trim());
          setSchemaForm(formPayload);
        } catch {
          throw new Error('schema JSON 无法解析');
        }
      }
      const r = await fetch(API('/ops-console/product/schema'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: tenantId.trim(),
          object_type_id: objectTypeId.trim(),
          form: {
            object_type_id: objectTypeId.trim(),
            label: formPayload.label,
            fields: formPayload.fields,
          },
          actor: 'ops-console-ui',
          reason: 'ops console product schema form save',
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      const next = coerceForm(body.form || body.definition, objectTypeId.trim());
      setSchemaForm(next);
      syncJsonFromForm(next);
      setSchemaNote(
        `saved draft · via_form=${String(body.via_form)} · version=${String(body.version || body.draft?.version || '—')}`,
      );
    } catch (e: unknown) {
      setSchemaNote((e as Error)?.message || 'schema 保存失败');
    } finally {
      setSavingSchema(false);
    }
  }, [tenantId, objectTypeId, schemaForm, schemaText, showJson, syncJsonFromForm]);

  const updateField = useCallback(
    (index: number, patch: Partial<SchemaField>) => {
      setSchemaForm((prev) => {
        const fields = prev.fields.map((f, i) => (i === index ? { ...f, ...patch } : f));
        const next = { ...prev, fields };
        syncJsonFromForm(next);
        return next;
      });
    },
    [syncJsonFromForm],
  );

  const addField = useCallback(() => {
    setSchemaForm((prev) => {
      const next = {
        ...prev,
        fields: [
          ...prev.fields,
          { name: `field_${prev.fields.length + 1}`, type: 'string' as FieldType, required: false, description: '' },
        ],
      };
      syncJsonFromForm(next);
      return next;
    });
  }, [syncJsonFromForm]);

  const removeField = useCallback(
    (index: number) => {
      setSchemaForm((prev) => {
        const next = { ...prev, fields: prev.fields.filter((_, i) => i !== index) };
        syncJsonFromForm(next);
        return next;
      });
    },
    [syncJsonFromForm],
  );

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
          <span>运维台产品面（N24）</span>
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
          默认可用：概览 + Schema 表单字段编辑（可切 JSON）+ 浏览器下载导出。
          full_ops_console=true；非 certified / 非自由布局设计器。
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
                  onChange={(e) => {
                    const v = e.target.value;
                    setObjectTypeId(v);
                    setSchemaForm((prev) => ({ ...prev, object_type_id: v }));
                  }}
                />
              </label>
              <label className="flex flex-col gap-1">
                <span>label</span>
                <input
                  className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
                  value={schemaForm.label}
                  onChange={(e) => {
                    const label = e.target.value;
                    setSchemaForm((prev) => {
                      const next = { ...prev, label };
                      syncJsonFromForm(next);
                      return next;
                    });
                  }}
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
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setShowJson((v) => !v)}
              >
                {showJson ? '表单模式' : 'JSON 高级'}
              </Button>
            </div>

            {!showJson ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-gray-500">字段表单</span>
                  <Button type="button" size="sm" variant="ghost" onClick={addField}>
                    <Plus className="h-3.5 w-3.5 mr-1" />
                    添加字段
                  </Button>
                </div>
                {schemaForm.fields.length === 0 ? (
                  <p className="text-gray-600">暂无字段；点击添加字段或加载已有 schema。</p>
                ) : (
                  <div className="space-y-2">
                    {schemaForm.fields.map((field, index) => (
                      <div
                        key={`f-${index}`}
                        className="grid grid-cols-1 md:grid-cols-12 gap-2 rounded border border-gray-800 bg-black/20 p-2"
                      >
                        <label className="md:col-span-3 flex flex-col gap-1">
                          <span>name</span>
                          <input
                            className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
                            value={field.name}
                            onChange={(e) => updateField(index, { name: e.target.value })}
                          />
                        </label>
                        <label className="md:col-span-2 flex flex-col gap-1">
                          <span>type</span>
                          <select
                            className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
                            value={field.type}
                            onChange={(e) =>
                              updateField(index, { type: e.target.value as FieldType })
                            }
                          >
                            {FIELD_TYPES.map((t) => (
                              <option key={t} value={t}>
                                {t}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="md:col-span-2 flex items-end gap-2 pb-1">
                          <input
                            type="checkbox"
                            checked={field.required}
                            onChange={(e) => updateField(index, { required: e.target.checked })}
                          />
                          <span>required</span>
                        </label>
                        <label className="md:col-span-4 flex flex-col gap-1">
                          <span>description</span>
                          <input
                            className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
                            value={field.description}
                            onChange={(e) =>
                              updateField(index, { description: e.target.value })
                            }
                          />
                        </label>
                        <div className="md:col-span-1 flex items-end">
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={() => removeField(index)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <textarea
                className="w-full min-h-[180px] rounded border border-gray-700 bg-gray-900 px-2 py-1 font-mono text-[11px] text-gray-200"
                value={schemaText}
                onChange={(e) => setSchemaText(e.target.value)}
              />
            )}
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
