/**
 * Org pilot entry — post, this week's runs, pending gates, weekly KPI.
 * Starts a run only through POST /goals/{id}/runs. No second runner.
 */
import React, { useEffect, useState } from 'react';

const API = (path: string) => `/api/platform/apps/org${path}`;

type Post = {
  post_id?: string;
  title?: string;
  org_goal_id?: string;
  enabled?: boolean;
  domain_id?: string;
};

type Weekly = {
  run_count?: number;
  kpis?: {
    mtta_seconds?: number | null;
    root_cause_rate?: number | null;
    exception_ratio?: number | null;
  };
  pending_hitl?: { run_id?: string; hitl_ticket_id?: string }[];
};

type Ingress = {
  inbound?: { id?: string; open?: boolean }[];
  outbound_only?: { id?: string; configured?: boolean }[];
};

type FieldOps = {
  c5_pack_ready?: boolean;
  m4_claim_allowed?: boolean;
};

type ValueCard = {
  baseline_source?: string;
  baseline_missing?: boolean;
  saved_person_hours?: number | null;
  mtta_delta_seconds?: number | null;
  platform_kpis?: {
    mtta_seconds?: number | null;
    root_cause_rate?: number | null;
    exception_ratio?: number | null;
    closed_runs?: number;
  };
  formula_notes?: string[];
};

type InboxItem = {
  kind?: string;
  id?: string;
  title?: string;
  status?: string;
  summary?: string;
};

type H4Rules = {
  enabled?: boolean;
  sandbox_only?: boolean;
  sandbox_ok?: boolean;
  confidence_min?: number;
  daily_auto_rate_max?: number;
  called_apply?: boolean;
  circuit_reason?: string;
  io_mode?: string;
  sandbox_pass_rate?: number | null;
  live_refused_today?: number;
  live_auto_pass_rate?: number | null;
  auto_applied_shadow?: boolean;
  delta_note?: string;
};

type H5View = {
  items?: { draft_id?: string; status?: string; title?: string; listed?: boolean }[];
  candidates?: { case_id?: string; title?: string }[];
  auto_listed?: boolean;
};

const roleHeaders = () => ({
  'X-AIPLAT-ROLE': localStorage.getItem('aiplat_role') || '',
});

const OrgPilotPage: React.FC = () => {
  const [post, setPost] = useState<Post | null>(null);
  const [weekly, setWeekly] = useState<Weekly | null>(null);
  const [health, setHealth] = useState<{
    explained_count?: number;
    schema_gap_count?: number;
    semantic_coverage?: number | null;
    context_served?: number;
    context_used?: number;
    context_hit_rate?: number | null;
    repeat_reject_count?: number;
    event_preview_count?: number;
    cold_archived_count?: number;
    wrote_live_yaml?: boolean;
    m4_claim_allowed?: boolean;
  } | null>(null);
  const [ingress, setIngress] = useState<Ingress | null>(null);
  const [fieldOps, setFieldOps] = useState<FieldOps | null>(null);
  const [prep, setPrep] = useState<{
    prep_score?: string;
    prep_complete?: boolean;
    materials_ready_for_review?: boolean;
    gates?: {
      id?: string;
      label?: string;
      ok?: boolean;
      detail?: string;
      acceptance?: string;
      how_to?: string;
      owner_hint?: string;
      ui_anchor?: string;
    }[];
    playbook?: {
      step?: string;
      title?: string;
      customer_sees?: string;
      customer_approves?: string;
      gates?: string;
    }[];
    m4_claim_allowed?: boolean;
  } | null>(null);
  const [rollback, setRollback] = useState<{
    can_rollback?: string[];
    cannot_rollback?: string[];
    change_trace?: string;
  } | null>(null);
  const [inbox, setInbox] = useState<InboxItem[]>([]);
  const [snapshot, setSnapshot] = useState<Record<string, unknown> | null>(null);
  const [valueCard, setValueCard] = useState<ValueCard | null>(null);
  const [h4Rules, setH4Rules] = useState<H4Rules | null>(null);
  const [h5, setH5] = useState<H5View | null>(null);
  const [packs, setPacks] = useState<{ template_id?: string; title?: string }[]>([]);
  const [minutes, setMinutes] = useState('30');
  const [mtta, setMtta] = useState('900');
  const [roiPreview, setRoiPreview] = useState<{
    simulation?: boolean;
    saved_person_hours?: number | null;
    mtta_delta_seconds?: number | null;
    formula_notes?: string[];
    m4_claim_allowed?: boolean;
  } | null>(null);
  const [packId, setPackId] = useState('alert_triage');
  const [newDomain, setNewDomain] = useState('');
  const [oncallName, setOncallName] = useState('');
  const [oncallContact, setOncallContact] = useState('');
  const [gapHints, setGapHints] = useState<{ action_id?: string; failure_count?: number; hint?: string }[]>([]);
  const [rehRoles, setRehRoles] = useState('分诊,诊断,报告');
  const [rehNote, setRehNote] = useState('');
  const [eventType, setEventType] = useState('signal.preview');
  const [previewNote, setPreviewNote] = useState('');
  const [gapDiffs, setGapDiffs] = useState<
    {
      case_id?: string;
      class_name?: string;
      diff?: { count?: number; changes?: { path?: string; before?: unknown; after?: unknown }[] };
    }[]
  >([]);
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const headers = roleHeaders();
    const [pR, wR, cR, fR, sR, iR, vR, h4R, h5R, pkR, gR, rehR, prevR, healthR, prepR] = await Promise.all([
      fetch(API('/posts')),
      fetch(API('/goals/goal-it-ops-alert-sla/weekly?domain_id=it-ops')),
      fetch(API('/channels/feishu/status')),
      fetch(API('/field-ops/checklist?domain_id=it-ops')),
      fetch(API('/rollback/scope')),
      fetch(API('/approvals/inbox?domain_id=it-ops&limit=20'), { headers }),
      fetch(API('/value/translation?domain_id=it-ops&goal_id=goal-it-ops-alert-sla')),
      fetch(API('/approvals/auto-rules'), { headers }),
      fetch(API('/skills/drafts?domain_id=it-ops'), { headers }),
      fetch(API('/domain-packs')),
      fetch(API('/ontology/gap-hints?domain_id=it-ops')),
      fetch(API('/rehearsals?limit=1')),
      fetch(API('/events/previews?limit=1')),
      fetch(API('/health/joint?domain_id=it-ops')),
      fetch(API('/signoff/prep?domain_id=it-ops')),
    ]);
    if (pR.ok) {
      const body = await pR.json();
      const first = (body.items || [])[0];
      setPost(first?.post || null);
    }
    if (wR.ok) setWeekly(await wR.json());
    if (cR.ok) setIngress(await cR.json());
    if (fR.ok) setFieldOps(await fR.json());
    if (sR.ok) setRollback(await sR.json());
    if (iR.ok) {
      const body = await iR.json();
      setInbox(body.items || []);
    }
    if (vR.ok) setValueCard(await vR.json());
    if (h4R.ok) setH4Rules(await h4R.json());
    if (h5R.ok) setH5(await h5R.json());
    if (pkR.ok) {
      const body = await pkR.json();
      setPacks(body.items || []);
    }
    if (gR.ok) {
      const body = await gR.json();
      setGapHints(body.items || []);
    }
    if (rehR.ok) {
      const body = await rehR.json();
      const last = (body.items || [])[0];
      setRehNote(
        last
          ? `最近一次 ${last.rehearsal_id || ''} · 舰队已启动 ${last.fleet_started ? '是' : '否'}` +
            (last.conflict_probe?.concurrent_conflict ? ' · 冲突探针拒绝二次持有' : '')
          : '',
      );
    }
    if (prevR.ok) {
      const body = await prevR.json();
      const last = (body.items || [])[0];
      setPreviewNote(last ? `最近一次 ${last.preview_id || ''} · live ${last.live_started ? '已启动' : '未启动'}` : '');
    }
    if (healthR.ok) setHealth(await healthR.json());
    if (prepR.ok) setPrep(await prepR.json());
  };

  useEffect(() => {
    load().catch(() => setMsg('加载失败'));
  }, []);

  const openSnapshot = async (item: InboxItem) => {
    if (!item.kind || !item.id) return;
    const r = await fetch(API(`/approvals/${item.kind}/${item.id}/snapshot?domain_id=it-ops`), {
      headers: roleHeaders(),
    });
    if (!r.ok) {
      setMsg('快照加载失败');
      return;
    }
    const body = await r.json();
    setSnapshot(body.snapshot || body);
  };

  const exportPack = async () => {
    setMsg('');
    const r = await fetch(
      API('/signoff/evidence-pack?domain_id=it-ops&format=markdown'),
      { headers: roleHeaders() },
    );
    if (!r.ok) {
      setMsg('证据包导出失败');
      return;
    }
    const body = await r.json();
    if (body.m4_claim_allowed) {
      setMsg('接口返回异常：不得声称已签收');
      return;
    }
    setMsg(body.cover_statement || '证据包已生成（不是签字）');
    if (body.markdown) {
      const blob = new Blob([body.markdown], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `it-ops-evidence-pack-${new Date().toISOString().slice(0, 10)}.md`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const exportPrep = async () => {
    setMsg('');
    const r = await fetch(API('/signoff/prep?domain_id=it-ops&format=markdown'));
    if (!r.ok) {
      setMsg('准备度清单导出失败');
      return;
    }
    const body = await r.json();
    if (body.m4_claim_allowed) {
      setMsg('接口返回异常：不得声称已签收');
      return;
    }
    setMsg(body.cover_statement || '准备度清单已生成（不是签字）');
    if (body.markdown) {
      const blob = new Blob([body.markdown], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `it-ops-signoff-prep-${new Date().toISOString().slice(0, 10)}.md`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const scanQueue = async () => {
    setBusy(true);
    setMsg('');
    try {
      const r = await fetch(API('/approvals/auto-pass?domain_id=it-ops'), {
        method: 'POST',
        headers: roleHeaders(),
      });
      const d = await r.json();
      if (d.m4_claim_allowed || d.called_apply) {
        setMsg('扫描异常：不得写活本体');
        return;
      }
      const n = (d.passed || []).length;
      setMsg(r.ok && d.ok !== false ? `已扫队列，通过 ${n} 条（未写活本体）` : String(d.reason || '扫描未执行'));
      await load();
    } catch {
      setMsg('扫描失败');
    } finally {
      setBusy(false);
    }
  };

  const saveBaseline = async () => {
    setBusy(true);
    setMsg('');
    try {
      const r = await fetch(API('/value/baseline'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...roleHeaders() },
        body: JSON.stringify({
          tenant_id: 'default',
          baseline_minutes_per_incident: Number(minutes),
          baseline_mtta_seconds: Number(mtta),
        }),
      });
      const d = await r.json();
      setMsg(r.ok && d.ok ? '基线已写入（不是签收）' : String(d.reason || '基线写入失败'));
      await load();
    } catch {
      setMsg('基线写入失败');
    } finally {
      setBusy(false);
    }
  };

  const previewRoi = async () => {
    setBusy(true);
    setMsg('');
    try {
      const q = new URLSearchParams({
        domain_id: 'it-ops',
        trial_minutes_per_incident: String(Number(minutes) || 0),
        trial_mtta_seconds: String(Number(mtta) || 0),
      });
      const r = await fetch(API(`/value/roi-preview?${q}`));
      const d = await r.json();
      if (d.m4_claim_allowed) {
        setMsg('接口返回异常：不得声称已签收');
        return;
      }
      if (!r.ok || !d.ok) {
        setRoiPreview(null);
        setMsg(String(d.reason || d.detail?.reason || '试算失败'));
        return;
      }
      setRoiPreview(d);
      setMsg('试算完成（未写入基线，不是签收）');
    } catch {
      setMsg('试算失败');
    } finally {
      setBusy(false);
    }
  };

  const archiveCold = async () => {
    setBusy(true);
    setMsg('');
    try {
      const r = await fetch(API('/ontology/cases/archive-cold?domain_id=it-ops'), {
        method: 'POST',
        headers: roleHeaders(),
      });
      const d = await r.json();
      const n = Number(d.moved_count || 0);
      setMsg(r.ok && d.ok ? `已移入冷库 ${n} 条（未删除）` : String(d.reason || d.detail?.reason || '归档失败'));
      await load();
    } catch {
      setMsg('归档失败');
    } finally {
      setBusy(false);
    }
  };

  const previewGaps = async () => {
    setBusy(true);
    setMsg('');
    try {
      const r = await fetch(API('/ontology/gap-previews?domain_id=it-ops'));
      const d = await r.json();
      setGapDiffs(r.ok && d.ok ? d.items || [] : []);
      setMsg(
        r.ok && d.ok
          ? `预览 ${(d.items || []).length} 条 Diff（未进提案）`
          : String(d.reason || d.detail?.reason || '预览失败'),
      );
    } catch {
      setGapDiffs([]);
      setMsg('预览失败');
    } finally {
      setBusy(false);
    }
  };

  const draftGaps = async () => {
    setBusy(true);
    setMsg('');
    try {
      const r = await fetch(API('/ontology/gap-drafts?domain_id=it-ops'), {
        method: 'POST',
        headers: roleHeaders(),
      });
      const d = await r.json();
      const n = Number(d.created_count || 0);
      setMsg(r.ok && d.ok ? `已采纳 ${n} 份进提案（未写活本体）` : String(d.reason || d.detail?.reason || '起草失败'));
      setGapDiffs([]);
      await load();
    } catch {
      setMsg('起草失败');
    } finally {
      setBusy(false);
    }
  };

  const startPreview = async () => {
    setBusy(true);
    setMsg('');
    try {
      const r = await fetch(API('/events/preview'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...roleHeaders() },
        body: JSON.stringify({ domain_id: 'it-ops', event_type: eventType.trim() }),
      });
      const d = await r.json();
      setMsg(r.ok && d.ok ? '预演已记录（未进 live）' : String(d.reason || d.detail?.reason || '预演失败'));
      await load();
    } catch {
      setMsg('预演失败');
    } finally {
      setBusy(false);
    }
  };

  const startRehearsal = async () => {
    const roles = rehRoles.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
    setBusy(true);
    setMsg('');
    try {
      const r = await fetch(API('/rehearsals'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...roleHeaders() },
        body: JSON.stringify({ domain_id: 'it-ops', roles }),
      });
      const d = await r.json();
      setMsg(r.ok && d.ok ? '演练已记录（未启动舰队）' : String(d.reason || d.detail?.reason || '演练失败'));
      await load();
    } catch {
      setMsg('演练失败');
    } finally {
      setBusy(false);
    }
  };

  const installPack = async () => {
    if (!newDomain.trim()) return;
    setBusy(true);
    setMsg('');
    try {
      const r = await fetch(API('/domain-packs/install'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...roleHeaders() },
        body: JSON.stringify({
          template_id: packId,
          domain_id: newDomain.trim(),
          display_name: newDomain.trim(),
        }),
      });
      const d = await r.json();
      setMsg(r.ok && d.ok ? `已安装 ${d.domain_id}（动作草稿未登记）` : String(d.reason || '安装失败'));
    } catch {
      setMsg('安装失败');
    } finally {
      setBusy(false);
    }
  };

  const saveOncall = async () => {
    setBusy(true);
    setMsg('');
    try {
      const r = await fetch(API('/signoff/progress'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...roleHeaders() },
        body: JSON.stringify({
          oncall_name: oncallName,
          oncall_contact: oncallContact,
        }),
      });
      const d = await r.json();
      if (d.m4_claim_allowed) {
        setMsg('接口返回异常：不得声称已签收');
        return;
      }
      setMsg(r.ok && d.ok ? '值班已记录（不是签收）' : String(d.reason || '记录失败'));
      await load();
    } catch {
      setMsg('记录失败');
    } finally {
      setBusy(false);
    }
  };

  const saveRollbackDrill = async () => {
    setBusy(true);
    setMsg('');
    try {
      const r = await fetch(API('/signoff/progress'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...roleHeaders() },
        body: JSON.stringify({
          rollback_drill_done: true,
          rollback_drill_notes: 'paused_goal+io_deny per ORG_M4_SIGNOFF_PACK §5',
        }),
      });
      const d = await r.json();
      if (d.m4_claim_allowed) {
        setMsg('接口返回异常：不得声称已签收');
        return;
      }
      setMsg(r.ok && d.ok ? '回滚演练已记（不是签收）' : String(d.reason || '记录失败'));
      await load();
    } catch {
      setMsg('记录失败');
    } finally {
      setBusy(false);
    }
  };

  const run = async () => {
    if (!post?.org_goal_id) return;
    setBusy(true);
    setMsg('');
    try {
      const r = await fetch(API(`/goals/${post.org_goal_id}/runs`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...roleHeaders(),
        },
        body: JSON.stringify({
          domain_id: post.domain_id || 'it-ops',
          post_id: post.post_id || '',
          dry_actions: true,
        }),
      });
      const d = await r.json();
      const detail = d.detail?.status || d.detail?.reason || d.status || '失败';
      setMsg(r.ok ? `Run ${d.run_id || ''} → ${d.status}` : String(detail));
      await load();
    } catch {
      setMsg('网络错误');
    } finally {
      setBusy(false);
    }
  };

  const jumpAnchor = (anchor?: string) => {
    if (!anchor) return;
    const el = document.getElementById(anchor);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const kpis = weekly?.kpis;

  return (
    <div className="p-6 space-y-4 text-gray-100 max-w-3xl">
      <h1 className="text-lg font-semibold">组织试点</h1>
      <p className="text-xs text-gray-500">
        入站 {(ingress?.inbound || []).map((c) => c.id).filter(Boolean).join('、') || '—'}
        {' · '}
        只出站 {(ingress?.outbound_only || []).map((c) => c.id).filter(Boolean).join('、') || '—'}
      </p>
      <section className="rounded border border-gray-800 p-3 text-sm">
        <div className="text-gray-400 text-xs mb-1">当前岗位</div>
        <div>{post?.title || '—'}</div>
        <div className="text-xs text-gray-500">{post?.post_id} · {post?.org_goal_id}</div>
      </section>
      <section id="weekly-kpis" className="rounded border border-gray-800 p-3 text-sm">
        <div className="text-gray-400 text-xs mb-1">本周</div>
        <div>任务 {weekly?.run_count ?? 0}</div>
        <div>MTTA {kpis?.mtta_seconds ?? '—'} · 根因率 {kpis?.root_cause_rate ?? '—'} · 例外比 {kpis?.exception_ratio ?? '—'}</div>
      </section>
      <section className="rounded border border-gray-800 p-3 text-sm">
        <div className="text-gray-400 text-xs mb-1">联合健康度（只读，不是签收）</div>
        <div>
          能解释 {health?.explained_count ?? 0} · 缺口 {health?.schema_gap_count ?? 0} · 覆盖率{' '}
          {health?.semantic_coverage == null ? '—' : health.semantic_coverage.toFixed(2)}
        </div>
        <div className="text-xs text-gray-500">
          连续失败提示 {health?.repeat_reject_count ?? 0} · 事件预演 {health?.event_preview_count ?? 0}
          {' · '}
          冷库 {health?.cold_archived_count ?? 0}
          {' · '}
          命中 {health?.context_used ?? 0}/{health?.context_served ?? 0}
          {' · '}
          {health?.context_hit_rate == null ? '无注入不报率' : health.context_hit_rate.toFixed(2)}
          {' · '}
          写活本体 {health?.wrote_live_yaml ? '是' : '否'}
        </div>
      </section>
      <section id="approval-inbox" className="rounded border border-gray-800 p-3 text-sm">
        <div className="text-gray-400 text-xs mb-1">待批（只读快照，批准走原路由）</div>
        {inbox.length === 0 ? (
          <div className="text-gray-500">无</div>
        ) : (
          inbox.map((p) => (
            <button
              key={`${p.kind}-${p.id}`}
              type="button"
              className="block w-full text-left py-1 hover:text-amber-200"
              onClick={() => openSnapshot(p)}
            >
              [{p.kind}] {p.title || p.id} · {p.status}
              {p.summary ? <span className="text-gray-500"> · {p.summary}</span> : null}
            </button>
          ))
        )}
        {snapshot && (
          <>
            {snapshot.kind === 'proposal' && Array.isArray((snapshot as { diff?: { changes?: { path?: string; before?: unknown; after?: unknown }[] } }).diff?.changes) ? (
              <div className="mt-2 text-xs text-gray-300 space-y-1">
                <div className="text-gray-400">提案 Diff（只读，不批准）</div>
                {((snapshot as { diff?: { changes?: { path?: string; before?: unknown; after?: unknown }[] } }).diff?.changes || [])
                  .slice(0, 8)
                  .map((c, i) => (
                    <div key={i} className="text-gray-500">
                      {c.path}
                      {c.before !== undefined || c.after !== undefined
                        ? `: ${JSON.stringify(c.before)} → ${JSON.stringify(c.after)}`
                        : ''}
                    </div>
                  ))}
              </div>
            ) : null}
            <pre className="mt-2 text-xs text-gray-400 whitespace-pre-wrap overflow-auto max-h-48">
              {JSON.stringify(snapshot, null, 2)}
            </pre>
          </>
        )}
      </section>
      <section id="value-section" className="rounded border border-gray-800 p-3 text-sm">
        <div className="text-gray-400 text-xs mb-1">可审计收益（不是签收）</div>
        {!valueCard ? (
          <div className="text-gray-500">—</div>
        ) : valueCard.baseline_missing ? (
          <>
            <div>基线缺失 · 只显示平台指标</div>
            <div className="text-xs text-gray-500">
              MTTA {valueCard.platform_kpis?.mtta_seconds ?? '—'} · 根因率{' '}
              {valueCard.platform_kpis?.root_cause_rate ?? '—'} · 完结{' '}
              {valueCard.platform_kpis?.closed_runs ?? 0}
            </div>
            <div className="text-xs text-gray-500 mt-1">不显示节省人时 · 可先试算再写入</div>
            <div className="mt-2 flex gap-2 items-center text-xs">
              <input className="bg-transparent border border-gray-700 px-2 py-1 w-20" value={minutes} onChange={(e) => setMinutes(e.target.value)} placeholder="分钟" />
              <input className="bg-transparent border border-gray-700 px-2 py-1 w-24" value={mtta} onChange={(e) => setMtta(e.target.value)} placeholder="MTTA秒" />
              <button type="button" disabled={busy} onClick={previewRoi} className="px-2 py-1 border border-gray-700">试算</button>
              <button type="button" disabled={busy} onClick={saveBaseline} className="px-2 py-1 border border-gray-700">写入基线</button>
            </div>
            {roiPreview?.simulation ? (
              <div className="mt-2 text-xs text-gray-500">
                试算节省人时 {roiPreview.saved_person_hours ?? '—'} · MTTA Δ {roiPreview.mtta_delta_seconds ?? '—'}s
                {' · '}未写入 · 不是客户基线
              </div>
            ) : null}
          </>
        ) : (
          <>
            <div>
              节省人时 {valueCard.saved_person_hours ?? '—'} · MTTA 缩短{' '}
              {valueCard.mtta_delta_seconds ?? '—'}s
            </div>
            <div className="text-xs text-gray-500">
              来源 {valueCard.baseline_source} · 完结 {valueCard.platform_kpis?.closed_runs ?? 0}
            </div>
          </>
        )}
      </section>
      <section className="rounded border border-gray-800 p-3 text-sm">
        <div className="text-gray-400 text-xs mb-1">H4 队列自动通过（不写活本体）</div>
        {!h4Rules ? (
          <div className="text-gray-500">—</div>
        ) : (
          <>
            <div>
              规则 {h4Rules.enabled ? '已打开（沙箱）' : '关闭'}
              {' · '}
              沙箱限定 {h4Rules.sandbox_only === false ? '否' : '是'}
            </div>
            <div className="text-xs text-gray-500">
              置信度 ≥ {h4Rules.confidence_min ?? 0.95}
              {' · '}
              日通过率上限 {(h4Rules.daily_auto_rate_max ?? 0.2) * 100}%
              {' · '}
              曾调 apply {h4Rules.called_apply ? '是' : '否'}
            </div>
            <div className="text-xs text-gray-500 mt-1">
              IO {h4Rules.io_mode || '—'}
              {' · '}
              沙箱通过率{' '}
              {h4Rules.sandbox_pass_rate == null ? '—' : h4Rules.sandbox_pass_rate.toFixed(2)}
              {' · '}
              live 拒绝 {h4Rules.live_refused_today ?? 0}
              {' · '}
              live 自动通过率{' '}
              {h4Rules.live_auto_pass_rate == null ? '—' : h4Rules.live_auto_pass_rate.toFixed(2)}
              {' · '}
              灰度影子 {h4Rules.auto_applied_shadow ? '是' : '否'}
            </div>
            {h4Rules.delta_note ? (
              <div className="text-xs text-gray-500 mt-1">{h4Rules.delta_note}</div>
            ) : null}
            {h4Rules.circuit_reason ? (
              <div className="text-xs text-amber-300 mt-1">熔断：{h4Rules.circuit_reason}</div>
            ) : null}
            <button type="button" disabled={busy} onClick={scanQueue} className="mt-2 px-2 py-1 border border-gray-700 text-xs">
              扫一遍队列
            </button>
          </>
        )}
      </section>
      <section className="rounded border border-gray-800 p-3 text-sm">
        <div className="text-gray-400 text-xs mb-1">H5 技能草稿（人批才登记）</div>
        {!h5 ? (
          <div className="text-gray-500">—</div>
        ) : (
          <>
            <div>
              候选 {(h5.candidates || []).length} · 草稿 {(h5.items || []).length}
              {' · '}
              自动上架 {h5.auto_listed ? '是' : '否'}
            </div>
            <div className="text-xs text-gray-500">不写 SKILL.md。未人批不进市场。</div>
          </>
        )}
      </section>
      <section className="rounded border border-gray-800 p-3 text-sm">
        <div className="text-gray-400 text-xs mb-1">领域模板（骨架 + 动作草稿，未登记）</div>
        <div className="flex gap-2 items-center text-xs">
          <select className="bg-transparent border border-gray-700 px-2 py-1" value={packId} onChange={(e) => setPackId(e.target.value)}>
            {(packs.length ? packs : [{ template_id: 'alert_triage', title: '告警分诊' }]).map((p) => (
              <option key={p.template_id} value={p.template_id}>{p.title || p.template_id}</option>
            ))}
          </select>
          <input className="bg-transparent border border-gray-700 px-2 py-1" value={newDomain} onChange={(e) => setNewDomain(e.target.value)} placeholder="domain-id" />
          <button type="button" disabled={busy || !newDomain.trim()} onClick={installPack} className="px-2 py-1 border border-gray-700">安装</button>
        </div>
      </section>
      <section id="oncall-section" className="rounded border border-gray-800 p-3 text-sm">
        <div className="text-gray-400 text-xs mb-1">值班 / 回滚演练（不是签收）</div>
        <div className="flex gap-2 items-center text-xs">
          <input className="bg-transparent border border-gray-700 px-2 py-1" value={oncallName} onChange={(e) => setOncallName(e.target.value)} placeholder="姓名" />
          <input className="bg-transparent border border-gray-700 px-2 py-1" value={oncallContact} onChange={(e) => setOncallContact(e.target.value)} placeholder="联系方式" />
          <button type="button" disabled={busy} onClick={saveOncall} className="px-2 py-1 border border-gray-700">记录值班</button>
          <button type="button" disabled={busy} onClick={saveRollbackDrill} className="px-2 py-1 border border-gray-700">记回滚演练</button>
        </div>
        <div className="text-xs text-gray-500 mt-1">演练步骤见签收包 §5；只记结果，不自动 pause Goal / 改 IO。</div>
      </section>
      <section className="rounded border border-gray-800 p-3 text-sm">
        <div className="text-gray-400 text-xs mb-1">沙箱演练（不启动舰队）</div>
        <div className="flex gap-2 items-center text-xs">
          <input className="bg-transparent border border-gray-700 px-2 py-1 flex-1" value={rehRoles} onChange={(e) => setRehRoles(e.target.value)} placeholder="角色，逗号分隔" />
          <button type="button" disabled={busy} onClick={startRehearsal} className="px-2 py-1 border border-gray-700">记录</button>
        </div>
        {rehNote ? <div className="text-xs text-gray-500 mt-1">{rehNote}</div> : null}
      </section>
      <section className="rounded border border-gray-800 p-3 text-sm">
        <div className="text-gray-400 text-xs mb-1">事件预演（不进 live，不推渠道）</div>
        <div className="flex gap-2 items-center text-xs">
          <input className="bg-transparent border border-gray-700 px-2 py-1 flex-1" value={eventType} onChange={(e) => setEventType(e.target.value)} placeholder="event_type" />
          <button type="button" disabled={busy} onClick={startPreview} className="px-2 py-1 border border-gray-700">预演</button>
        </div>
        {previewNote ? <div className="text-xs text-gray-500 mt-1">{previewNote}</div> : null}
      </section>
      <section className="rounded border border-gray-800 p-3 text-sm">
        <div className="text-gray-400 text-xs mb-1">案例冷库（移出注入，不删除，不改 TBox）</div>
        <button type="button" disabled={busy} onClick={archiveCold} className="mb-1 px-2 py-1 border border-gray-700 text-xs">
          归档低收益
        </button>
        <div className="text-xs text-gray-500">
          已归档 {health?.cold_archived_count ?? 0} · 只供审计，不再进 ContextBus
        </div>
      </section>
      <section className="rounded border border-gray-800 p-3 text-sm">
        <div className="text-gray-400 text-xs mb-1">本体缺口（先看 Diff，确认才进提案；不写活 YAML）</div>
        <div className="flex gap-2 mb-2">
          <button type="button" disabled={busy} onClick={previewGaps} className="px-2 py-1 border border-gray-700 text-xs">
            预览 Diff
          </button>
          <button
            type="button"
            disabled={busy || gapDiffs.length === 0}
            onClick={draftGaps}
            className="px-2 py-1 border border-gray-700 text-xs"
          >
            确认采纳进提案
          </button>
        </div>
        {gapDiffs.length > 0 ? (
          <div className="mb-2 space-y-2 text-xs text-gray-300">
            {gapDiffs.map((item) => (
              <div key={item.case_id || item.class_name} className="border border-gray-800 p-2">
                <div>
                  {item.class_name} · case {item.case_id} · 变更 {item.diff?.count ?? 0} 处
                </div>
                {(item.diff?.changes || []).slice(0, 6).map((c, i) => (
                  <div key={`${item.case_id}-${i}`} className="text-gray-500">
                    {c.path}: {JSON.stringify(c.before)} → {JSON.stringify(c.after)}
                  </div>
                ))}
              </div>
            ))}
          </div>
        ) : null}
        {gapHints.length === 0 ? (
          <div className="text-gray-500">无连续失败</div>
        ) : (
          gapHints.map((h) => (
            <div key={h.action_id}>
              {h.action_id} · {h.failure_count} 次 · {h.hint}
            </div>
          ))
        )}
      </section>
      <section id="prep-gates" className="rounded border border-gray-800 p-3 text-sm">
        <div className="text-gray-400 text-xs mb-1">签收准备度（材料齐 ≠ 已签收）</div>
        <div>
          材料包 {fieldOps?.c5_pack_ready ? '就绪' : '未就绪'}
          {' · '}
          准备度 {prep?.prep_score ?? '—'}
          {' · '}
          可送审 {prep?.materials_ready_for_review ? '是' : '否'}
        </div>
        <div className="text-xs text-gray-500">
          客户签收 {fieldOps?.m4_claim_allowed || prep?.m4_claim_allowed ? '允许' : '不允许'}
          {' · '}
          全部齐套 {prep?.prep_complete ? '是' : '否'}（仍不打开 m4）
        </div>
        {(prep?.gates || []).length > 0 ? (
          <div className="mt-2 space-y-2">
            {prep?.gates?.map((g) => (
              <div key={g.id} className="border border-gray-800 p-2 text-xs">
                <div className={g.ok ? 'text-gray-200' : 'text-amber-200/90'}>
                  {g.ok ? '✓' : '·'} {g.label}
                  {g.acceptance ? ` · ${g.acceptance}` : ''}
                  {g.detail ? ` · ${g.detail}` : ''}
                </div>
                {g.how_to ? <div className="text-gray-500 mt-1">如何核：{g.how_to}</div> : null}
                {g.owner_hint ? <div className="text-gray-500">责任：{g.owner_hint}</div> : null}
                {g.ui_anchor ? (
                  <button
                    type="button"
                    className="mt-1 text-amber-200/80 underline"
                    onClick={() => jumpAnchor(g.ui_anchor)}
                  >
                    跳转到页内对应区
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
        {(prep?.playbook || []).length > 0 ? (
          <div className="mt-3 text-xs text-gray-500 space-y-1">
            <div className="text-gray-400">签收剧本（到送审；双签仍人工）</div>
            {prep?.playbook?.map((s) => (
              <div key={s.step}>
                {s.step}. {s.title} — 看：{s.customer_sees}；批：{s.customer_approves}
              </div>
            ))}
          </div>
        ) : null}
        <button
          type="button"
          onClick={exportPrep}
          className="mt-2 px-2 py-1 border border-gray-700 text-xs"
        >
          导出准备度清单
        </button>
      </section>
      <section className="rounded border border-gray-800 p-3 text-sm">
        <div className="text-gray-400 text-xs mb-1">回滚范围</div>
        <div>可回滚</div>
        {(rollback?.can_rollback || []).map((line) => <div key={line}>{line}</div>)}
        <div className="mt-2">不可回滚</div>
        {(rollback?.cannot_rollback || []).map((line) => <div key={line}>{line}</div>)}
        {rollback?.change_trace ? <div className="mt-2 text-xs text-gray-500">{rollback.change_trace}</div> : null}
      </section>
      <div id="run-actions">
      <button
        type="button"
        disabled={busy || !post?.org_goal_id}
        onClick={run}
        className="px-3 py-1 rounded bg-primary/20 text-sm disabled:opacity-40"
      >
        按岗位开跑
      </button>
      <button
        type="button"
        onClick={exportPack}
        className="ml-2 px-3 py-1 rounded border border-gray-700 text-sm"
      >
        导出签收证据
      </button>
      </div>
      {msg && <div className="text-xs text-amber-200">{msg}</div>}
    </div>
  );
};

export default OrgPilotPage;
