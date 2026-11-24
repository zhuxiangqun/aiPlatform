/**
 * ObjectTypePublishPanel — N02 ObjectType 人审发布管理端薄门户。
 *
 * 经 FDE `/object-types*` → CoreFacade；产品面种子目录 + published-over-seed；
 * 产品面有界多租户 bulk（`/object-types/product/bulk-transition`，无 residual env）。
 * 不宣称 seed_replacement_complete / certified。
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

type SeedCatalogItem = {
  name?: string;
  path?: string;
  object_type_count?: number;
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
  const [seedItems, setSeedItems] = useState<SeedCatalogItem[]>([]);
  const [seedName, setSeedName] = useState('');
  const [seedNote, setSeedNote] = useState('');
  const [seedApplying, setSeedApplying] = useState(false);

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

  useEffect(() => {
    void loadSeedCatalog();
  }, [loadSeedCatalog]);

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
      const r = await fetch(API('/object-types/product/bulk-transition'), {
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
        `${status} · via=${String(d.via)} · ok=${d.ok_count ?? 0} fail=${d.fail_count ?? 0}` +
          ` · product=${String(d.bulk_product_surface)}` +
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
        toast?.success?.(`bulk product ${status}`);
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

  const runBulkProductGate = async () => {
    setLoading(true);
    setBulkNote('');
    try {
      const suiteRes = await fetch(API('/object-types/product/bulk-transition/suite'), {
        method: 'POST',
      });
      const suite = await suiteRes.json().catch(() => ({}));
      if (!suiteRes.ok) throw new Error(detailMessage(suite.detail));
      const gateRes = await fetch(API('/object-types/product/bulk-transition/gate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ suite }),
      });
      const gate = await gateRes.json().catch(() => ({}));
      if (!gateRes.ok) throw new Error(detailMessage(gate.detail));
      const certified = gate.certified === true;
      setBulkNote(
        `bulk-product suite ok=${Boolean(suite.ok)} · gate certified=${certified} · surface=${String(gate.bulk_product_surface)}（须 certified=false）`,
      );
      if (suite.ok && gate.ok && !certified) {
        toast?.success?.('bulk product gate ok');
      } else {
        toast?.error?.(
          `bulk product gate fail · ${((gate.issues as string[]) || []).join(',') || 'unknown'}`,
        );
      }
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || 'bulk product gate 失败');
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

  const loadSeedCatalog = useCallback(async () => {
    try {
      const r = await fetch(API('/object-types/product/seed-files'));
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      const list = Array.isArray(body.items) ? (body.items as SeedCatalogItem[]) : [];
      setSeedItems(list);
      setSeedName((prev) => prev || String(list[0]?.name || ''));
      setSeedNote(
        `catalog ok · total=${String(body.total ?? list.length)} · mutated=${String(body.workspace_seeds_mutated)} · complete=${String(body.seed_replacement_complete)}`,
      );
    } catch (e: unknown) {
      setSeedItems([]);
      setSeedNote((e as Error)?.message || '种子目录加载失败');
    }
  }, []);

  const runSeedAuthority = async () => {
    if (!tenantId.trim()) {
      toast?.error?.('tenant_id 必填');
      return;
    }
    setSeedApplying(true);
    try {
      const r = await fetch(API('/object-types/product/seed-authority'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: tenantId.trim(),
          seed_path: seedName.trim(),
          write: true,
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setSeedNote(
        `${String(body.status)} · via=${String(body.via)} · published=${String(body.published_count)} · seed=${String(body.seed_count)} · wrote=${String(body.wrote)} · complete=${String(body.seed_replacement_complete)}`,
      );
      if (body.status === 'ok') toast?.success?.('种子权威解析已写入 allowlist');
      else toast?.error?.(String(body.note || body.error || body.status));
    } catch (e: unknown) {
      setSeedNote((e as Error)?.message || '种子权威解析失败');
      toast?.error?.((e as Error)?.message || '种子权威解析失败');
    } finally {
      setSeedApplying(false);
    }
  };

  const runGate = async () => {
    setLoading(true);
    try {
      const suiteRes = await fetch(API('/object-types/product/seed-authority/suite'), {
        method: 'POST',
      });
      const suite = await suiteRes.json().catch(() => ({}));
      if (!suiteRes.ok) throw new Error(detailMessage(suite.detail));
      const gateRes = await fetch(API('/object-types/product/seed-authority/gate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ suite }),
      });
      const gate = await gateRes.json().catch(() => ({}));
      if (!gateRes.ok) throw new Error(detailMessage(gate.detail));
      const certified = Boolean(gate.certified);
      setGateNote(
        `seed-product suite ok=${Boolean(suite.ok)} · gate certified=${certified} · surface=${String(gate.seed_product_surface)}（须 certified=false）`,
      );
      if (certified) {
        toast?.error?.('gate.certified 为 true — 违反诚实锁');
      } else {
        toast?.success?.('种子产品门槛门诚实：certified=false');
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
          <span>ObjectType 人审发布（N02）</span>
          <span className="text-[11px] text-gray-500 font-normal">
            产品面种子权威 · 非 certified · 不改写 workspace_seeds
          </span>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={loading}
            onClick={() => {
              void reload();
              void loadSeedCatalog();
            }}
          >
            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </Button>
          <Button type="button" variant="ghost" size="sm" disabled={loading} onClick={() => void runGate()}>
            seed suite/gate
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 px-4 pb-4">
        <p className="text-[11px] text-gray-500 leading-relaxed">
          draft → in_review → published|rejected；publish 须配置角色（默认 reviewer）。
          产品面可解析 workspace_seeds 只读目录并写 allowlist 权威快照；不宣称
          seed_replacement_complete / N02 certified。
        </p>

        <div className="rounded border border-emerald-900/40 bg-emerald-950/20 px-3 py-3 space-y-2">
          <div className="text-[12px] text-emerald-200/90">种子权威产品面（默认可用）</div>
          <label className="text-[11px] text-gray-400 space-y-1 block">
            seed file
            <select
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={seedName}
              onChange={(e) => setSeedName(e.target.value)}
            >
              {seedItems.length === 0 ? (
                <option value="">（无 *-object-types.json）</option>
              ) : (
                seedItems.map((it) => (
                  <option key={String(it.name)} value={String(it.name)}>
                    {String(it.name)} · types={String(it.object_type_count ?? 0)}
                  </option>
                ))
              )}
            </select>
          </label>
          {seedNote ? (
            <div className="text-[11px] text-gray-500 border border-gray-800 rounded px-2 py-1.5 font-mono">
              {seedNote}
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={loading}
              onClick={() => void loadSeedCatalog()}
            >
              刷新目录
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={seedApplying || !tenantId.trim() || !seedName.trim()}
              onClick={() => void runSeedAuthority()}
            >
              解析并写 allowlist
            </Button>
          </div>
        </div>

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
            多租户批量转换产品面（默认可用；bulk_product_surface=true；非 certified / 非种子替换）
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
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" disabled={loading} onClick={() => void runBulk()}>
              批量转换（产品面）
            </Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={loading}
              onClick={() => void runBulkProductGate()}
            >
              跑 bulk 产品门槛
            </Button>
          </div>
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
