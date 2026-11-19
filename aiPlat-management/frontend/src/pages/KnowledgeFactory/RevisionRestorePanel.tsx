/**
 * RevisionRestorePanel — N24 Batch J2 审批式 restore 管理端薄 UI。
 *
 * 经 FDE `/revision-restore/*`（J1）→ CoreFacade；禁止自批；不宣称 certified / 全量总线。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import { History, RefreshCw } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

type RestoreRequest = {
  request_id?: string;
  id?: string;
  status?: string;
  entity_type?: string;
  entity_id?: string;
  target_revision?: number;
  requester?: string;
  reason?: string;
};

type AuditEvent = {
  event_type?: string;
  entity_type?: string;
  entity_id?: string;
  actor?: string;
  reason?: string;
  ts?: string;
};

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'reason' in detail) {
    return String((detail as { reason?: unknown }).reason || JSON.stringify(detail));
  }
  return detail ? JSON.stringify(detail) : '请求失败';
}

const RevisionRestorePanel: React.FC = () => {
  const [tenantId, setTenantId] = useState('lock-service');
  const [actor, setActor] = useState('factory-approver');
  const [requester, setRequester] = useState('factory-requester');
  const [entityType, setEntityType] = useState('fact');
  const [entityId, setEntityId] = useState('');
  const [targetRevision, setTargetRevision] = useState('1');
  const [reason, setReason] = useState('n24-j2-ui-restore');
  const [requests, setRequests] = useState<RestoreRequest[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
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
      const [reqRes, auditRes] = await Promise.all([
        fetch(API(`/revision-restore/requests?${q({ status: 'pending', limit: '50' })}`)),
        fetch(API(`/revision-restore/audit?${q({ limit: '30' })}`)),
      ]);
      const reqBody = await reqRes.json().catch(() => ({}));
      const auditBody = await auditRes.json().catch(() => ({}));
      if (!reqRes.ok) throw new Error(detailMessage(reqBody.detail));
      if (!auditRes.ok) throw new Error(detailMessage(auditBody.detail));
      setRequests(reqBody.requests || []);
      setEvents(auditBody.events || []);
    } catch (e: unknown) {
      setRequests([]);
      setEvents([]);
      toast?.error?.((e as Error)?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const submitRequest = async () => {
    if (!entityId.trim() || !requester.trim() || !reason.trim()) {
      toast?.error?.('entity_id / requester / reason 必填');
      return;
    }
    const rev = Number(targetRevision);
    if (!Number.isFinite(rev) || rev < 1) {
      toast?.error?.('target_revision 须 ≥ 1');
      return;
    }
    setLoading(true);
    try {
      const r = await fetch(API(`/revision-restore/requests?${q()}`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entity_type: entityType,
          entity_id: entityId.trim(),
          target_revision: rev,
          requester: requester.trim(),
          reason: reason.trim(),
        }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      toast?.success?.(`已提交 restore 请求 ${d.request_id || d.id || ''}`.trim());
      await reload();
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || '提交失败');
    } finally {
      setLoading(false);
    }
  };

  const decide = async (requestId: string, action: 'approve' | 'reject') => {
    if (!actor.trim() || !reason.trim()) {
      toast?.error?.('审批人 actor / reason 必填');
      return;
    }
    if (actor.trim() === requester.trim()) {
      // 与账本硬门一致：禁止自批
      toast?.error?.('审批人不能与请求人相同');
      return;
    }
    setLoading(true);
    try {
      const r = await fetch(
        API(`/revision-restore/requests/${encodeURIComponent(requestId)}/${action}?${q()}`),
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ actor: actor.trim(), reason: reason.trim() }),
        },
      );
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(d.detail));
      toast?.success?.(action === 'approve' ? `已批准 ${requestId}` : `已拒绝 ${requestId}`);
      await reload();
    } catch (e: unknown) {
      toast?.error?.((e as Error)?.message || '裁决失败');
    } finally {
      setLoading(false);
    }
  };

  const runGate = async () => {
    setLoading(true);
    try {
      const suiteRes = await fetch(API(`/revision-restore/suite?${q()}`), { method: 'POST' });
      const suite = await suiteRes.json().catch(() => ({}));
      if (!suiteRes.ok) throw new Error(detailMessage(suite.detail));
      const gateRes = await fetch(API('/revision-restore/gate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ suite }),
      });
      const gate = await gateRes.json().catch(() => ({}));
      if (!gateRes.ok) throw new Error(detailMessage(gate.detail));
      const certified = Boolean(gate.certified);
      setGateNote(
        `suite ok · gate certified=${certified}（J2 诚实锁：须为 false）`,
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
          <History className="h-4 w-4 text-amber-300/90" />
          <span>Revision Restore 审批（N24 J2）</span>
          <span className="text-[11px] text-gray-500 font-normal">
            经 HTTP→Facade · 非 certified
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
          提交 restore 请求后须由<strong className="text-gray-400 font-medium">不同 actor</strong>批准才会写头。
          本面板不合并 Package+Action 全量审计总线，也不宣称 N24 认证。
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
            审批人 actor（≠ requester）
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={actor}
              onChange={(e) => setActor(e.target.value)}
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            requester
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={requester}
              onChange={(e) => setRequester(e.target.value)}
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
            entity_type
            <select
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={entityType}
              onChange={(e) => setEntityType(e.target.value)}
            >
              <option value="fact">fact</option>
              <option value="claim">claim</option>
              <option value="source">source</option>
            </select>
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            entity_id
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono"
              value={entityId}
              onChange={(e) => setEntityId(e.target.value)}
              placeholder="fact/claim/source id"
            />
          </label>
          <label className="text-[11px] text-gray-400 space-y-1">
            target_revision
            <input
              className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
              value={targetRevision}
              onChange={(e) => setTargetRevision(e.target.value)}
            />
          </label>
          <div className="flex items-end">
            <Button type="button" size="sm" disabled={loading} onClick={() => void submitRequest()}>
              提交 restore 请求
            </Button>
          </div>
        </div>

        {gateNote && (
          <div className="text-[11px] text-amber-200/80 border border-amber-800/40 rounded px-2 py-1.5">
            {gateNote}
          </div>
        )}

        <div>
          <div className="text-[12px] text-gray-300 mb-1.5">
            Pending 请求（{requests.length}）
          </div>
          {requests.length === 0 ? (
            <div className="text-[11px] text-gray-500">暂无 pending</div>
          ) : (
            <ul className="space-y-2">
              {requests.map((row) => {
                const rid = String(row.request_id || row.id || '');
                return (
                  <li
                    key={rid || `${row.entity_type}:${row.entity_id}:${row.target_revision}`}
                    className="rounded border border-gray-800 bg-gray-950/50 px-3 py-2 text-[12px] text-gray-300 space-y-1"
                  >
                    <div className="font-mono text-[11px] text-gray-400">{rid}</div>
                    <div>
                      {row.entity_type}:{row.entity_id} → rev {row.target_revision}
                      <span className="ml-2 text-gray-500">by {row.requester}</span>
                    </div>
                    {row.reason && <div className="text-gray-500">{row.reason}</div>}
                    <div className="flex gap-2 pt-1">
                      <Button
                        type="button"
                        size="sm"
                        disabled={loading || !rid}
                        onClick={() => void decide(rid, 'approve')}
                      >
                        批准
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        disabled={loading || !rid}
                        onClick={() => void decide(rid, 'reject')}
                      >
                        拒绝
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div>
          <div className="text-[12px] text-gray-300 mb-1.5">
            Revision audit（近 {events.length} 条 · 账本内）
          </div>
          {events.length === 0 ? (
            <div className="text-[11px] text-gray-500">暂无事件</div>
          ) : (
            <ul className="max-h-40 overflow-auto space-y-1 text-[11px] font-mono text-gray-500">
              {events.map((ev, i) => (
                <li key={`${ev.ts || ''}-${ev.event_type || ''}-${i}`}>
                  [{ev.event_type || '?'}] {ev.entity_type}:{ev.entity_id}
                  {ev.actor ? ` · ${ev.actor}` : ''}
                  {ev.reason ? ` — ${ev.reason}` : ''}
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default RevisionRestorePanel;
