/**
 * ObjectTypePublishPanel — N02 ObjectType 人审发布管理端薄门户。
 *
 * 经 FDE `/object-types*` → CoreFacade；显式 residual：有界多租户 bulk-transition
 *（须服务端 AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK=1）。不宣称种子替换 / certified。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import { FileStack, RefreshCw } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

type ObjectTypeVersion = {
  object_type_id?: string;
  version?: string;
  status?: string;
  actor?: string;
  reason?: string;
  role?: string;
  updated_at?: string;
};

const TRANSITIONS: Record<string, string[]> = {
  draft: ['in_review', 'rejected'],
  in_review: ['published', 'rejected', 'draft'],
  published: [],
  rejected: ['draft'],
};

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'reason' in detail) {
    return String((detail as { reason?: unknown }).reason || JSON.stringify(detail));
  }
  return detail ? JSON.stringify(detail) : '请求失败';
}

const ObjectTypePublishPanel: React.FC = () => {
  const [tenantId, setTenantId] = useState('lock-service');
  const [filterOid, setFilterOid] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [actor, setActor] = useState('factory-reviewer');
  const [role, setRole] = useState('reviewer');
  const [reason, setReason] = useState('n02-portal-ui');
  const [draftOid, setDraftOid] = useState('');
  const [draftVersion, setDraftVersion] = useState('1.0.0');
  const [draftDefJson, setDraftDefJson] = useState('{"name":"demo"}');
  const [bulkJson, setBulkJson] = useState(
    '[{"tenant_id":"tenant-a","object_type_id":"Demo","version":"1.0.0","to_status":"in_review"}]',
  );
  const [bulkNote, setBulkNote] = useState('');
  const [items, setItems] = useState<ObjectTypeVersion[]>([]);
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
      const extra: Record<string, string> = { limit: '100' };
      if (filterOid.trim()) extra.object_type_id = filterOid.trim();
      if (filterStatus.trim()) extra.status = filterStatus.trim();
      const r = await fetch(API(`/object-types?${q(extra)}`));
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setItems(Array.isArray(body.items) ? body.items : []);
    } catch (e: unknown) {
      setItems([]);
      toast?.error?.((e as Error)?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, [tenantId, filterOid, filterStatus]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const runBulk = async () => {
    if (!actor.trim() || !reason.trim()) {
      toast?.error?.('actor / reason 必填');
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(bulkJson || '[]');
    } catch {
      toast?.error?.('bulk JSON 非法');
      return;
    }
    if (!Array.isArray(parsed)) {
      toast?.error?.('bulk JSON 须为数组');
      return;
    }
    setLoading(true);
    setBulkNote('');
    try {
      const r = await fetch(API('/object-types/bulk-transition'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items: parsed,
          actor: actor.trim(),
          reason: reason.trim(),
          role: role.trim(),
        }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      const status = String(d.status || '');
      setBulkNote(
        `${status} · ok=${d.ok_count ?? 0} fail=${d.fail_count ?? 0}` +
          (d.note ? ` · ${d.note}` : '') +
          (d.certified === false ? ' · certified=false' : ''),
      );
      if (
        status === 'object_type_bulk_unavailable' ||
        status === 'invalid' ||
        Number(d.fail_count || 0) > 0
      ) {
        toast?.error?.(
          String(d.note || d.error || `${status} fail=${d.fail_count ?? 0}`),
        );
      } else if (status === 'ok') {
        toast?.success?.(`bulk ${status}`);
        await reload();
      } else {
        toast?.error?.(String(d.note || d.error || status || 'bulk 失败'));
      }
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || 'bulk 失败');
    } finally {
      setLoading(false);
    }
  };

  const submitDraft = async () => {
    if (!draftOid.trim() || !draftVersion.trim() || !actor.trim() || !reason.trim()) {
      toast?.error?.('object_type_id / version / actor / reason 必填');
      return;
    }
    let definition: Record<string, unknown>;
    try {
      definition = JSON.parse(draftDefJson || '{}') as Record<string, unknown>;
    } catch {
      toast?.error?.('definition 须为合法 JSON');
      return;
    }
    if (!definition || typeof definition !== 'object' || Array.isArray(definition)) {
      toast?.error?.('definition 须为 JSON 对象');
      return;
    }
    setLoading(true);
    try {
      const r = await fetch(API(`/object-types/drafts?${q()}`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          object_type_id: draftOid.trim(),
          version: draftVersion.trim(),
          definition,
          actor: actor.trim(),
          reason: reason.trim(),
        }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      toast?.success?.(
        `已提交草稿 ${d.object_type_id || draftOid}@${d.version || draftVersion}`,
      );
      await reload();
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || '提交草稿失败');
    } finally {
      setLoading(false);
    }
  };

  const transition = async (row: ObjectTypeVersion, toStatus: string) => {
    const oid = String(row.object_type_id || '').trim();
    const ver = String(row.version || '').trim();
    if (!oid || !ver) {
      toast?.error?.('缺少 object_type_id / version');
      return;
    }
    if (!actor.trim() || !reason.trim()) {
      toast?.error?.('actor / reason 必填');
      return;
    }
    if (toStatus === 'published' && !role.trim()) {
      toast?.error?.('publish 须填写 role（如 reviewer）');
      return;
    }
    setLoading(true);
    try {
      const r = await fetch(
        API(
          `/object-types/${encodeURIComponent(oid)}/versions/${encodeURIComponent(ver)}/transition?${q()}`,
        ),
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            to_status: toStatus,
            actor: actor.trim(),
            reason: reason.trim(),
            role: role.trim(),
          }),
        },
      );
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      toast?.success?.(`${oid}@${ver} → ${toStatus}`);
      await reload();
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || '转换失败');
    } finally {
      setLoading(false);
    }
  };

  const runGate = async () => {
    setLoading(true);
    try {
      const suiteRes = await fetch(API('/object-types/suite'), { method: 'POST' });
      const suite = await suiteRes.json().catch(() => ({}));
      if (!suiteRes.ok) throw new Error(detailMessage(suite.detail));
      const gateRes = await fetch(API('/object-types/gate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ suite }),
      });
      const gate = await gateRes.json().catch(() => ({}));
      if (!gateRes.ok) throw new Error(detailMessage(gate.detail));
      const certified = Boolean(gate.certified);
      setGateNote(
        `suite ok=${Boolean(suite.ok)} · gate certified=${certified}（N02 诚实锁：须为 false）`,
      );
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
          <FileStack className="h-4 w-4 text-sky-300/90" />
          <span>ObjectType 人审发布（N02 薄门户）</span>
          <span className="text-[11px] text-gray-500 font-normal">
            经 HTTP→Facade · 非 certified · 非多域批量
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
          draft → in_review → published|rejected；publish 须配置角色（默认 reviewer）。
          本面板不替换种子真源，也不宣称 N02 全量门户认证。
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
            actor
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={actor}
              onChange={(e) => setActor(e.target.value)}
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            role（publish 必填）
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="reviewer"
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            reason
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            过滤 object_type_id
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={filterOid}
              onChange={(e) => setFilterOid(e.target.value)}
              placeholder="可选"
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            过滤 status
            <select
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
            >
              <option value="">（全部）</option>
              <option value="draft">draft</option>
              <option value="in_review">in_review</option>
              <option value="published">published</option>
              <option value="rejected">rejected</option>
            </select>
          </label>
        </div>

        {gateNote && (
          <div className="text-[11px] text-amber-200/80 border border-amber-800/40 rounded px-2 py-1.5">
            {gateNote}
          </div>
        )}

        <div className="rounded border border-gray-800 bg-gray-950/40 px-3 py-3 space-y-2">
          <div className="text-[12px] text-gray-300">提交草稿</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <label className="text-[11px] text-gray-400 space-y-1">
              object_type_id
              <input
                className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
                value={draftOid}
                onChange={(e) => setDraftOid(e.target.value)}
              />
            </label>
            <label className="text-[11px] text-gray-400 space-y-1">
              version
              <input
                className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
                value={draftVersion}
                onChange={(e) => setDraftVersion(e.target.value)}
              />
            </label>
          </div>
          <label className="text-[11px] text-gray-400 space-y-1 block">
            definition JSON
            <textarea
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono min-h-[64px]"
              value={draftDefJson}
              onChange={(e) => setDraftDefJson(e.target.value)}
            />
          </label>
          <Button type="button" size="sm" disabled={loading} onClick={() => void submitDraft()}>
            提交草稿
          </Button>
        </div>

        <div className="rounded border border-gray-800 bg-gray-950/40 px-3 py-3 space-y-2">
          <div className="text-[12px] text-gray-300">
            多租户批量转换 residual（须服务端开启 AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK）
          </div>
          <label className="text-[11px] text-gray-400 space-y-1 block">
            items JSON
            <textarea
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono min-h-[72px]"
              value={bulkJson}
              onChange={(e) => setBulkJson(e.target.value)}
            />
          </label>
          {bulkNote && (
            <div className="text-[11px] text-amber-200/80 border border-amber-800/40 rounded px-2 py-1.5">
              {bulkNote}
            </div>
          )}
          <Button type="button" size="sm" disabled={loading} onClick={() => void runBulk()}>
            批量转换
          </Button>
        </div>

        <div>
          <div className="text-[12px] text-gray-300 mb-1.5">版本列表（{items.length}）</div>
          {items.length === 0 ? (
            <div className="text-[11px] text-gray-500">暂无版本</div>
          ) : (
            <ul className="space-y-2">
              {items.map((row) => {
                const oid = String(row.object_type_id || '');
                const ver = String(row.version || '');
                const st = String(row.status || '');
                const next = TRANSITIONS[st] || [];
                return (
                  <li
                    key={`${oid}@${ver}`}
                    className="rounded border border-gray-800 bg-gray-950/50 px-3 py-2 text-[12px] text-gray-300 space-y-1"
                  >
                    <div className="font-mono text-[11px] text-gray-400">
                      {oid}@{ver} · <span className="text-sky-300/90">{st}</span>
                    </div>
                    <div className="text-gray-500">
                      by {row.actor || '—'}
                      {row.role ? ` · role=${row.role}` : ''}
                      {row.updated_at ? ` · ${row.updated_at}` : ''}
                    </div>
                    {row.reason && <div className="text-gray-500">{row.reason}</div>}
                    {next.length > 0 && (
                      <div className="flex flex-wrap gap-2 pt-1">
                        {next.map((to) => (
                          <Button
                            key={to}
                            type="button"
                            size="sm"
                            variant={to === 'published' ? 'default' : 'secondary'}
                            disabled={loading}
                            onClick={() => void transition(row, to)}
                          >
                            → {to}
                          </Button>
                        ))}
                      </div>
                    )}
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

export default ObjectTypePublishPanel;
