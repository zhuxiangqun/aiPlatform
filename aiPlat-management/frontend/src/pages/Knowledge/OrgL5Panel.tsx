/**
 * OrgL5Panel — Phase 2–3: OrgGoal / OrgRun / HITL / weekly KPI / memory.
 */
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { Play, RefreshCw, Check, X, BarChart3, Search } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/org${path}`;

type Goal = {
  goal_id: string;
  title?: string;
  status?: string;
  domain_id?: string;
};

type Run = {
  run_id: string;
  goal_id?: string;
  status?: string;
  week_label?: string;
  exceptions?: { reason?: string; hitl_ticket_id?: string }[];
  metrics_partial?: Record<string, number>;
};

type Weekly = {
  run_count?: number;
  kpis?: {
    mtta_seconds?: number | null;
    root_cause_rate?: number | null;
    exception_ratio?: number | null;
    mtta_note?: string | null;
  };
  failure_attribution_top?: { reason: string; count: number }[];
  pending_hitl?: { run_id: string; hitl_ticket_id?: string }[];
  memory_entries?: number;
  links?: { label: string; href: string }[];
  authority_note?: string;
};

export const OrgL5Panel: React.FC<{ compact?: boolean }> = ({ compact }) => {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [weekly, setWeekly] = useState<Weekly | null>(null);
  const [fieldOps, setFieldOps] = useState<{
    signoff_ready?: boolean;
    c5_pack_ready?: boolean;
    m4_claim_allowed?: boolean;
    fleet?: { status?: string; allowed?: boolean };
    items?: { id: string; label: string; ok: boolean; detail?: string }[];
  } | null>(null);
  const [ingress, setIngress] = useState<{
    channel?: string;
    sign_configured?: boolean;
    confirm_required?: boolean;
    post?: { post_id?: string; ok?: boolean; status?: string };
  } | null>(null);
  const [iface, setIface] = useState<{
    status?: string;
    authority_source?: string;
    compat_live?: boolean;
    spec?: { interface_ref?: string; enabled?: boolean; adapter?: string; bound_action_ids?: string[] };
    validation?: { ok?: boolean; declared?: boolean; warnings?: string[] };
  } | null>(null);
  const [fleetGate, setFleetGate] = useState<{
    status?: string;
    allowed?: boolean;
    allow_fleet?: boolean;
    checks?: { id: string; ok: boolean; detail?: string }[];
  } | null>(null);
  const [memHits, setMemHits] = useState<
    { run_id?: string; exception_reasons?: string[]; summary?: string }[]
  >([]);
  const [memQ, setMemQ] = useState('hitl');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [usage, setUsage] = useState<{
    run_count?: number;
    token_total?: number;
    billing?: null;
  } | null>(null);
  const [week, setWeek] = useState('w1');

  const goalId = goals[0]?.goal_id || 'goal-it-ops-alert-sla';

  const load = async () => {
    setBusy(true);
    try {
      const [gR, rR, wR, fR, flR, iR, cR, uR] = await Promise.all([
        fetch(API('/goals?domain_id=it-ops')),
        fetch(API('/runs?limit=10')),
        fetch(API(`/goals/${goalId}/weekly?domain_id=it-ops`)),
        fetch(API('/field-ops/checklist?domain_id=it-ops')),
        fetch(API('/fleet/gate?domain_id=it-ops')),
        fetch(API('/interfaces/it-ops')),
        fetch(API('/channels/feishu/status')),
        fetch(API('/usage/weekly?domain_id=it-ops')),
      ]);
      const gD = await gR.json();
      const rD = await rR.json();
      if (gR.ok) setGoals(gD.goals || []);
      if (rR.ok) setRuns(rD.runs || []);
      if (wR.ok) setWeekly(await wR.json());
      if (fR.ok) setFieldOps(await fR.json());
      if (flR.ok) setFleetGate(await flR.json());
      if (iR.ok) setIface(await iR.json());
      if (cR.ok) setIngress(await cR.json());
      if (uR.ok) setUsage(await uR.json());
    } catch {
      setMsg('加载失败');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const triggerRun = async () => {
    setBusy(true);
    setMsg('');
    try {
      const r = await fetch(API(`/goals/${goalId}/runs`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-AIPLAT-ROLE': localStorage.getItem('aiplat_role') || '',
        },
        body: JSON.stringify({ domain_id: 'it-ops', dry_actions: true, week_label: week }),
      });
      const d = await r.json();
      setMsg(r.ok ? `Run ${d.run_id} → ${d.status}` : d.detail || '失败');
      await load();
    } catch {
      setMsg('网络错误');
    } finally {
      setBusy(false);
    }
  };

  const resume = async (runId: string, approve: boolean) => {
    setBusy(true);
    try {
      const r = await fetch(API(`/runs/${runId}/resume`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approve, resolution: approve ? 'approved' : 'rejected' }),
      });
      const d = await r.json();
      setMsg(r.ok ? `Resume → ${d.run?.status}` : JSON.stringify(d.detail || d));
      await load();
    } catch {
      setMsg('网络错误');
    } finally {
      setBusy(false);
    }
  };

  const searchMem = async () => {
    setBusy(true);
    try {
      const r = await fetch(
        API(`/memory/search?q=${encodeURIComponent(memQ)}&domain_id=it-ops&limit=10`),
      );
      const d = await r.json();
      if (r.ok) setMemHits(d.hits || []);
    } catch {
      setMemHits([]);
    } finally {
      setBusy(false);
    }
  };

  const fmtRate = (v: number | null | undefined) =>
    typeof v === 'number' ? `${(v * 100).toFixed(0)}%` : '—';

  return (
    <Card className="border-teal-500/20" id="org-l5-panel">
      <CardHeader>
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <span className="text-sm font-medium text-gray-100">组织试点状态（可跳过）</span>
            <p className="text-[11px] text-gray-500 mt-1 font-normal">
              看 it-ops 告警分诊试点跑了没有。默认沙箱演示，不是客户已签收。日常建说明书不必打开。
            </p>
          </div>
          <Button variant="ghost" size="sm" loading={busy} onClick={load}>
            <RefreshCw className="w-3 h-3" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-[11px]">
        {goals[0] && (
          <div className="rounded border border-teal-800/40 bg-teal-950/20 p-2">
            <div className="text-teal-300 font-medium">{goals[0].title || goals[0].goal_id}</div>
            <div className="text-gray-500 mt-0.5">
              {goals[0].goal_id} · status={goals[0].status} · {goals[0].domain_id}
            </div>
          </div>
        )}
        <div className="flex gap-2 items-center flex-wrap">
          <select
            className="bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-gray-200"
            value={week}
            onChange={(e) => setWeek(e.target.value)}
          >
            <option value="w1">week w1</option>
            <option value="w2">week w2</option>
          </select>
          <Button size="sm" loading={busy} onClick={triggerRun}>
            <Play className="w-3 h-3 mr-1" />
            触发 OrgRun
          </Button>
        </div>
        {!compact && (
          <ul className="space-y-1 max-h-40 overflow-auto">
            {runs.map((r) => (
              <li
                key={r.run_id}
                className="flex justify-between gap-2 items-center border-b border-slate-800/60 py-1"
              >
                <span className="text-gray-300">
                  <span className="font-mono text-teal-300">{r.run_id}</span>
                  <span className="ml-2 text-gray-500">{r.week_label || '—'}</span>
                  <span className="ml-2">{r.status}</span>
                </span>
                {r.status === 'needs_hitl' && (
                  <span className="flex gap-1">
                    <Button size="sm" variant="ghost" onClick={() => resume(r.run_id, true)}>
                      <Check className="w-3 h-3 text-emerald-400" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => resume(r.run_id, false)}>
                      <X className="w-3 h-3 text-rose-400" />
                    </Button>
                  </span>
                )}
              </li>
            ))}
            {runs.length === 0 && <li className="text-gray-500">尚无 Run — 先 FDE⑦ 种 it-ops 图再触发</li>}
          </ul>
        )}

        {/* Phase 3 weekly */}
        <div className="rounded border border-amber-800/40 bg-amber-950/15 p-2 space-y-1.5">
          <div className="flex items-center gap-1 text-amber-300 font-medium">
            <BarChart3 className="w-3 h-3" />
            周报 KPI（D2）
            {weekly?.run_count != null && (
              <span className="text-gray-500 font-normal ml-1">runs={weekly.run_count}</span>
            )}
          </div>
          {weekly?.kpis ? (
            <div className="grid grid-cols-3 gap-2 text-gray-300">
              <div>
                MTTA{' '}
                <span className="font-mono text-amber-200">
                  {weekly.kpis.mtta_seconds != null ? weekly.kpis.mtta_seconds.toFixed(0) + 's' : '—'}
                </span>
              </div>
              <div>
                根因率 <span className="font-mono text-amber-200">{fmtRate(weekly.kpis.root_cause_rate)}</span>
              </div>
              <div>
                例外比 <span className="font-mono text-amber-200">{fmtRate(weekly.kpis.exception_ratio)}</span>
              </div>
            </div>
          ) : (
            <div className="text-gray-500">加载周报…</div>
          )}
          {weekly?.kpis?.mtta_note && (
            <div className="text-[10px] text-gray-500">{weekly.kpis.mtta_note}</div>
          )}
          {(weekly?.failure_attribution_top || []).length > 0 && (
            <div className="text-gray-400">
              归因 Top：
              {weekly!.failure_attribution_top!.map((f) => (
                <span key={f.reason} className="ml-2">
                  {f.reason}×{f.count}
                </span>
              ))}
            </div>
          )}
          {(weekly?.pending_hitl || []).length > 0 && (
            <div className="text-rose-300/80">
              待批 HITL：{weekly!.pending_hitl!.map((p) => p.run_id).join(', ')}
            </div>
          )}
          <div className="flex flex-wrap gap-3">
            {(weekly?.links || []).map((l) => (
              <Link key={l.href} to={l.href} className="text-sky-400 hover:underline">
                {l.label} →
              </Link>
            ))}
          </div>
          {weekly?.authority_note && (
            <div className="text-[10px] text-amber-500/70">{weekly.authority_note}</div>
          )}
        </div>

        {/* Phase 3 memory search */}
        {!compact && (
          <div className="rounded border border-slate-700/60 p-2 space-y-1.5">
            <div className="text-slate-300 font-medium">组织记忆 · 例外判例</div>
            <div className="flex gap-2">
              <input
                className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-gray-200"
                value={memQ}
                onChange={(e) => setMemQ(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && searchMem()}
                placeholder="如 hitl / fetch"
              />
              <Button size="sm" loading={busy} onClick={searchMem}>
                <Search className="w-3 h-3 mr-1" />
                检索
              </Button>
            </div>
            <ul className="max-h-24 overflow-auto space-y-0.5 text-gray-400">
              {memHits.map((h, i) => (
                <li key={(h.run_id || '') + i}>
                  <span className="text-teal-300 font-mono">{h.run_id}</span>{' '}
                  {(h.exception_reasons || []).join(',') || h.summary}
                </li>
              ))}
            </ul>
          </div>
        )}

        {msg && <div className="text-amber-500/80">{msg}</div>}

        {/* Phase 4 fleet + field */}
        <div className="rounded border border-violet-800/40 bg-violet-950/20 p-2 space-y-1.5">
          <div className="text-violet-300 font-medium">Phase C · Interface / 飞书入站</div>
          <div className="text-gray-400">
            飞书入站:{' '}
            <span className="text-violet-200">{ingress?.channel || 'feishu'}</span>
            <span className="ml-2">
              签名{ingress?.sign_configured ? '已配' : '未配'}
            </span>
            <span className="ml-2">确认门={String(ingress?.confirm_required ?? true)}</span>
            {ingress?.post?.post_id && (
              <span className="ml-2 font-mono">post={ingress.post.post_id}</span>
            )}
          </div>
          <div className="text-gray-400">
            用量账本:{' '}
            <span className="text-violet-200">runs={usage?.run_count ?? 0}</span>
            <span className="ml-2">tokens={usage?.token_total ?? 0}</span>
            <span className="ml-2">billing=none</span>
          </div>
          <div className="text-gray-400">
            Interface:{' '}
            <span className="text-violet-200 font-mono">
              {iface?.spec?.interface_ref || '—'}
            </span>
            {iface?.spec?.enabled != null && (
              <span className="ml-2">enabled={String(iface.spec.enabled)}</span>
            )}
            {iface?.validation?.ok != null && (
              <span className="ml-2">
                valid={String(iface.validation.ok)} declared={String(!!iface.validation.declared)}
              </span>
            )}
            <span className="ml-2">
              src={iface?.compat_live ? 'connector.live' : iface?.authority_source || '—'}
            </span>
          </div>
          {(iface?.spec?.bound_action_ids || []).length > 0 && (
            <div className="text-[10px] text-gray-500">
              bound actions: {(iface!.spec!.bound_action_ids || []).join(', ')}
            </div>
          )}
          <div className="text-gray-400">
            Fleet gate: <span className="text-violet-200">{fleetGate?.status || '—'}</span>
            {fleetGate?.allow_fleet != null && (
              <span className="ml-2">allow_fleet={String(fleetGate.allow_fleet)}</span>
            )}
          </div>
          {(fleetGate?.checks || []).slice(0, 4).map((c) => (
            <div key={c.id} className="text-[10px] text-gray-500">
              {c.ok ? '✓' : '✗'} {c.id}: {c.detail}
            </div>
          ))}
          <div className="text-gray-400">
            签收包:{' '}
            <span className={fieldOps?.c5_pack_ready ? 'text-emerald-400' : 'text-amber-400'}>
              {fieldOps?.c5_pack_ready ? 'c5 ready' : 'c5 pending'}
            </span>
            <span className="text-gray-600 ml-2">
              m4_claim={String(fieldOps?.m4_claim_allowed ?? false)}
            </span>
          </div>
          <div className="text-gray-400">
            现场签收自动项:{' '}
            <span className={fieldOps?.signoff_ready ? 'text-emerald-400' : 'text-amber-400'}>
              {fieldOps?.signoff_ready ? 'ready' : 'pending'}
            </span>
            <span className="text-gray-600 ml-2">M4 宣称仍须人工+客户沙箱</span>
          </div>
          {(fieldOps?.items || [])
            .filter((i) =>
              [
                'runbook',
                'channel_charter',
                'signoff_pack',
                'sandbox_io',
                'pilot_runs',
                'fleet_default_deny',
                'customer_sandbox_stub',
                'http_json_adapter',
                'digital_post',
                'usage_ledger',
                'feishu_ingress',
                'oncall',
                'live_unlock',
              ].includes(i.id),
            )
            .map((i) => (
              <div key={i.id} className="text-[10px] text-gray-500">
                {i.ok ? '✓' : '✗'} {i.label}
              </div>
            ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default OrgL5Panel;
