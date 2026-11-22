/**
 * FieldAclPanel — N07/N22 deepen 字段 ACL 管理端薄 UI。
 *
 * 经 `/api/core/wiki/ontology/field-permissions*`；不宣称 certified / 全量权限产品。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import { Shield, RefreshCw } from 'lucide-react';

const API = '/api/core/wiki/ontology/field-permissions';

type FieldPerm = {
  entity_uri?: string;
  field_name?: string;
  visibility?: string;
  redaction_strategy?: string;
};

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'reason' in detail) {
    return String((detail as { reason?: unknown }).reason || JSON.stringify(detail));
  }
  return detail ? JSON.stringify(detail) : '请求失败';
}

const FieldAclPanel: React.FC = () => {
  const [collection, setCollection] = useState('lock-service');
  const [entityUri, setEntityUri] = useState('');
  const [fieldName, setFieldName] = useState('');
  const [visibility, setVisibility] = useState('role:admin');
  const [strategy, setStrategy] = useState('mask');
  const [rows, setRows] = useState<FieldPerm[]>([]);
  const [loading, setLoading] = useState(false);
  const [certified, setCertified] = useState(false);

  const reload = useCallback(async () => {
    if (!collection.trim()) return;
    setLoading(true);
    try {
      const q = new URLSearchParams({ collection: collection.trim() });
      const r = await fetch(`${API}?${q}`);
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setRows(body.permissions || []);
      setCertified(Boolean(body.certified));
    } catch (e: unknown) {
      setRows([]);
      toast?.error?.((e as Error)?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, [collection]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const save = async () => {
    if (!entityUri.trim() || !fieldName.trim()) {
      toast?.error?.('entity_uri / field_name 必填');
      return;
    }
    setLoading(true);
    try {
      const q = new URLSearchParams({ collection: collection.trim() });
      const r = await fetch(`${API}?${q}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entity_uri: entityUri.trim(),
          field_name: fieldName.trim(),
          visibility: visibility.trim() || 'all',
          redaction_strategy: strategy,
        }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      toast?.success?.('已保存字段 ACL 规则');
      await reload();
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const remove = async (uri: string, field: string) => {
    if (!uri) return;
    setLoading(true);
    try {
      const q = new URLSearchParams({ collection: collection.trim() });
      const r = await fetch(`${API}?${q}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entity_uri: uri, field_name: field || '' }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      toast?.success?.(d.status === 'ok' ? '已删除' : '未找到');
      await reload();
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || '删除失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="border-gray-700/60 bg-gray-900/40">
      <CardHeader className="flex flex-row items-center justify-between gap-2 px-4 py-3">
        <div className="flex items-center gap-2 text-sm text-gray-200">
          <Shield className="h-4 w-4 text-sky-400" />
          字段 ACL（薄面板 · 非 certified）
        </div>
        <div className="flex gap-2">
          <Button type="button" variant="ghost" size="sm" disabled={loading} onClick={() => void reload()}>
            <RefreshCw className="h-3.5 w-3.5 mr-1" />
            刷新
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 px-4 pb-4">
        <p className="text-[11px] text-gray-500 leading-relaxed">
          管理 collection 级 <code className="text-gray-400">field_permissions.json</code> 规则（可见性 + 脱敏策略）。
          API 返回 <code className="text-gray-400">certified=false</code>
          {certified ? '（异常：后端宣称 certified）' : '（当前诚实）'}；本面板不是完整权限产品。
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <label className="text-[11px] text-gray-400 space-y-1">
            collection
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={collection}
              onChange={(e) => setCollection(e.target.value)}
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            entity_uri
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={entityUri}
              onChange={(e) => setEntityUri(e.target.value)}
              placeholder="entity://…"
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            field_name
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={fieldName}
              onChange={(e) => setFieldName(e.target.value)}
              placeholder="ssn / phone / …"
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            visibility
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={visibility}
              onChange={(e) => setVisibility(e.target.value)}
              placeholder="all | role:admin | none | scope:…"
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            redaction_strategy
            <select
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
            >
              <option value="mask">mask</option>
              <option value="truncate">truncate</option>
              <option value="replace">replace</option>
              <option value="remove">remove</option>
            </select>
          </label>
          <div className="flex items-end">
            <Button type="button" size="sm" disabled={loading} onClick={() => void save()}>
              保存规则
            </Button>
          </div>
        </div>

        <div>
          <div className="text-[12px] text-gray-300 mb-1.5">规则（{rows.length}）</div>
          {rows.length === 0 ? (
            <div className="text-[11px] text-gray-500">暂无规则</div>
          ) : (
            <ul className="space-y-2 max-h-48 overflow-auto">
              {rows.map((row) => {
                const uri = String(row.entity_uri || '');
                const field = String(row.field_name || '');
                return (
                  <li
                    key={`${uri}:${field}`}
                    className="rounded border border-gray-800 bg-gray-950/50 px-3 py-2 text-[12px] text-gray-300 flex flex-wrap items-center justify-between gap-2"
                  >
                    <div className="font-mono text-[11px] text-gray-400 break-all">
                      {uri} · {field}
                      <span className="ml-2 text-gray-500">
                        {row.visibility}/{row.redaction_strategy}
                      </span>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={loading}
                      onClick={() => void remove(uri, field)}
                    >
                      删除
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default FieldAclPanel;
