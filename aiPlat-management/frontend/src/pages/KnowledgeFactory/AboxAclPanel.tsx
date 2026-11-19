/**
 * AboxAclPanel — N07/N22 deepen ABox 实例/字段 ACL 管理端薄 UI。
 *
 * 经 `/api/platform/apps/fde/graph/acl/*`；不宣称 certified / 全量权限产品。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import { Lock, RefreshCw } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

type EntityEntry = {
  deny_roles?: Record<string, string[]>;
  allow_roles?: Record<string, string[]>;
};

type FieldEntry = {
  visibility?: string;
  redaction?: string;
  replace_with?: string;
};

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'reason' in detail) {
    return String((detail as { reason?: unknown }).reason || JSON.stringify(detail));
  }
  return detail ? JSON.stringify(detail) : '请求失败';
}

function parseRoleMap(raw: string): Record<string, string[]> | undefined {
  const t = raw.trim();
  if (!t) return undefined;
  // role:act1|act2,role2:*
  const out: Record<string, string[]> = {};
  for (const part of t.split(',')) {
    const [role, acts] = part.trim().split(':');
    if (!role) continue;
    out[role.trim()] = (acts || '*')
      .split('|')
      .map((a) => a.trim())
      .filter(Boolean);
  }
  return Object.keys(out).length ? out : undefined;
}

const AboxAclPanel: React.FC = () => {
  const [domainId, setDomainId] = useState('lock-service');
  const [entityId, setEntityId] = useState('');
  const [denyRaw, setDenyRaw] = useState('viewer:read');
  const [allowRaw, setAllowRaw] = useState('');
  const [fieldEntity, setFieldEntity] = useState('');
  const [fieldName, setFieldName] = useState('');
  const [visibility, setVisibility] = useState('role:admin');
  const [redaction, setRedaction] = useState('mask');
  const [entities, setEntities] = useState<Record<string, EntityEntry>>({});
  const [fields, setFields] = useState<Record<string, FieldEntry>>({});
  const [loading, setLoading] = useState(false);
  const [certified, setCertified] = useState(false);
  const [previewEntity, setPreviewEntity] = useState('');
  const [previewRole, setPreviewRole] = useState('viewer');
  const [previewAction, setPreviewAction] = useState('read');
  const [previewPayload, setPreviewPayload] = useState('{"ssn":"123-45-6789","name":"demo"}');
  const [previewOut, setPreviewOut] = useState('');

  const reload = useCallback(async () => {
    if (!domainId.trim()) return;
    setLoading(true);
    try {
      const r = await fetch(API(`/graph/acl/${encodeURIComponent(domainId.trim())}`));
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      const acl = body.acl || {};
      setEntities((acl.entities as Record<string, EntityEntry>) || {});
      setFields((acl.fields as Record<string, FieldEntry>) || {});
      setCertified(Boolean(body.certified));
    } catch (e: unknown) {
      setEntities({});
      setFields({});
      toast?.error?.((e as Error)?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, [domainId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const saveEntity = async () => {
    if (!entityId.trim()) {
      toast?.error?.('entity_id 必填');
      return;
    }
    setLoading(true);
    try {
      const r = await fetch(
        API(`/graph/acl/${encodeURIComponent(domainId.trim())}/entities/${encodeURIComponent(entityId.trim())}`),
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            deny_roles: parseRoleMap(denyRaw),
            allow_roles: parseRoleMap(allowRaw),
          }),
        },
      );
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      toast?.success?.('已保存实例 ACL');
      await reload();
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const saveField = async () => {
    if (!fieldEntity.trim() || !fieldName.trim()) {
      toast?.error?.('field entity / field_name 必填');
      return;
    }
    setLoading(true);
    try {
      const r = await fetch(
        API(
          `/graph/acl/${encodeURIComponent(domainId.trim())}/fields/${encodeURIComponent(fieldEntity.trim())}/${encodeURIComponent(fieldName.trim())}`,
        ),
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            visibility: visibility.trim() || 'all',
            redaction,
            replace_with: '[REDACTED]',
          }),
        },
      );
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      toast?.success?.('已保存 ABox 字段 ACL');
      await reload();
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const removeEntity = async (id: string) => {
    if (!id) return;
    setLoading(true);
    try {
      const r = await fetch(
        API(`/graph/acl/${encodeURIComponent(domainId.trim())}/entities/${encodeURIComponent(id)}`),
        { method: 'DELETE' },
      );
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      toast?.success?.(d.status === 'ok' ? '已删除实例 ACL' : '未找到');
      await reload();
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || '删除失败');
    } finally {
      setLoading(false);
    }
  };

  const removeField = async (key: string) => {
    const idx = key.lastIndexOf('.');
    if (idx <= 0) return;
    const eid = key.slice(0, idx);
    const fname = key.slice(idx + 1);
    setLoading(true);
    try {
      const r = await fetch(
        API(
          `/graph/acl/${encodeURIComponent(domainId.trim())}/fields/${encodeURIComponent(eid)}/${encodeURIComponent(fname)}`,
        ),
        { method: 'DELETE' },
      );
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      toast?.success?.(d.status === 'ok' ? '已删除字段 ACL' : '未找到');
      await reload();
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || '删除失败');
    } finally {
      setLoading(false);
    }
  };

  const runPreview = async () => {
    if (!previewEntity.trim()) {
      toast?.error?.('preview entity_id 必填');
      return;
    }
    let payload: Record<string, unknown> = {};
    try {
      payload = JSON.parse(previewPayload || '{}') as Record<string, unknown>;
    } catch {
      toast?.error?.('payload 须为合法 JSON');
      return;
    }
    setLoading(true);
    try {
      const r = await fetch(API(`/graph/acl/${encodeURIComponent(domainId.trim())}/preview`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entity_id: previewEntity.trim(),
          role: previewRole.trim(),
          action: previewAction.trim() || 'read',
          payload,
        }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      setPreviewOut(JSON.stringify(d, null, 2));
      if (d.certified) toast?.error?.('异常：预览返回 certified=true');
    } catch (e: unknown) {
      setPreviewOut('');
      toast?.error?.((e as Error)?.message || '预览失败');
    } finally {
      setLoading(false);
    }
  };

  const entityKeys = Object.keys(entities);
  const fieldKeys = Object.keys(fields);

  return (
    <Card className="border-gray-700/60 bg-gray-900/40">
      <CardHeader className="flex flex-row items-center justify-between gap-2 px-4 py-3">
        <div className="flex items-center gap-2 text-sm text-gray-200">
          <Lock className="h-4 w-4 text-amber-400" />
          ABox 实例 ACL（薄面板 · 非 certified）
        </div>
        <Button type="button" variant="ghost" size="sm" disabled={loading} onClick={() => void reload()}>
          <RefreshCw className="h-3.5 w-3.5 mr-1" />
          刷新
        </Button>
      </CardHeader>
      <CardContent className="space-y-4 px-4 pb-4">
        <p className="text-[11px] text-gray-500 leading-relaxed">
          管理域级 <code className="text-gray-400">abox_acl.json</code>（实例 deny/allow + 字段脱敏）。
          API 返回 <code className="text-gray-400">certified=false</code>
          {certified ? '（异常：后端宣称 certified）' : '（当前诚实）'}；与 Wiki field_permissions 薄面板互补，非全量权限产品。
        </p>

        <label className="text-[11px] text-gray-400 space-y-1 block">
          domain_id
          <input
            className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
            value={domainId}
            onChange={(e) => setDomainId(e.target.value)}
          />
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <label className="text-[11px] text-gray-400 space-y-1">
            entity_id
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={entityId}
              onChange={(e) => setEntityId(e.target.value)}
              placeholder="entity-…"
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            deny_roles（role:acts,…）
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={denyRaw}
              onChange={(e) => setDenyRaw(e.target.value)}
              placeholder="viewer:read|*"
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            allow_roles（可空）
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={allowRaw}
              onChange={(e) => setAllowRaw(e.target.value)}
              placeholder="admin:*"
            />
          </label>
          <div className="flex items-end">
            <Button type="button" size="sm" disabled={loading} onClick={() => void saveEntity()}>
              保存实例 ACL
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <label className="text-[11px] text-gray-400 space-y-1">
            field entity_id
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={fieldEntity}
              onChange={(e) => setFieldEntity(e.target.value)}
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            field_name
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={fieldName}
              onChange={(e) => setFieldName(e.target.value)}
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            visibility
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={visibility}
              onChange={(e) => setVisibility(e.target.value)}
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            redaction
            <select
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={redaction}
              onChange={(e) => setRedaction(e.target.value)}
            >
              <option value="mask">mask</option>
              <option value="truncate">truncate</option>
              <option value="replace">replace</option>
              <option value="remove">remove</option>
            </select>
          </label>
          <div className="flex items-end">
            <Button type="button" size="sm" disabled={loading} onClick={() => void saveField()}>
              保存字段 ACL
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <div className="text-[12px] text-gray-300 mb-1.5">实例规则（{entityKeys.length}）</div>
            {entityKeys.length === 0 ? (
              <div className="text-[11px] text-gray-500">暂无</div>
            ) : (
              <ul className="space-y-1.5 max-h-40 overflow-auto text-[11px] font-mono text-gray-400">
                {entityKeys.map((id) => (
                  <li
                    key={id}
                    className="rounded border border-gray-800 bg-gray-950/50 px-2 py-1.5 break-all flex flex-wrap items-center justify-between gap-2"
                  >
                    <span>
                      {id}
                      <span className="ml-2 text-gray-500">
                        deny={JSON.stringify(entities[id]?.deny_roles || {})}
                      </span>
                    </span>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={loading}
                      onClick={() => void removeEntity(id)}
                    >
                      删除
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <div className="text-[12px] text-gray-300 mb-1.5">字段规则（{fieldKeys.length}）</div>
            {fieldKeys.length === 0 ? (
              <div className="text-[11px] text-gray-500">暂无</div>
            ) : (
              <ul className="space-y-1.5 max-h-40 overflow-auto text-[11px] font-mono text-gray-400">
                {fieldKeys.map((key) => (
                  <li
                    key={key}
                    className="rounded border border-gray-800 bg-gray-950/50 px-2 py-1.5 break-all flex flex-wrap items-center justify-between gap-2"
                  >
                    <span>
                      {key}
                      <span className="ml-2 text-gray-500">
                        {fields[key]?.visibility}/{fields[key]?.redaction}
                      </span>
                    </span>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={loading}
                      onClick={() => void removeField(key)}
                    >
                      删除
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="border-t border-gray-800 pt-3 space-y-2">
          <div className="text-[12px] text-gray-300">按角色预览（dry-run · 非 certified）</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <label className="text-[11px] text-gray-400 space-y-1">
              entity_id
              <input
                className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
                value={previewEntity}
                onChange={(e) => setPreviewEntity(e.target.value)}
              />
            </label>
            <label className="text-[11px] text-gray-400 space-y-1">
              role
              <input
                className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
                value={previewRole}
                onChange={(e) => setPreviewRole(e.target.value)}
              />
            </label>
            <label className="text-[11px] text-gray-400 space-y-1">
              action
              <input
                className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
                value={previewAction}
                onChange={(e) => setPreviewAction(e.target.value)}
              />
            </label>
            <div className="flex items-end">
              <Button type="button" size="sm" disabled={loading} onClick={() => void runPreview()}>
                预览
              </Button>
            </div>
          </div>
          <label className="text-[11px] text-gray-400 space-y-1 block">
            sample payload (JSON)
            <textarea
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono min-h-[64px]"
              value={previewPayload}
              onChange={(e) => setPreviewPayload(e.target.value)}
            />
          </label>
          {previewOut ? (
            <pre className="max-h-40 overflow-auto rounded border border-gray-800 bg-gray-950/70 p-2 text-[11px] text-gray-400 whitespace-pre-wrap">
              {previewOut}
            </pre>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
};

export default AboxAclPanel;
