import { useState, useEffect } from 'react';
import { Shield, CheckCircle, AlertTriangle, Activity, RefreshCw, FileText } from 'lucide-react';
import { apiClient } from '../../services/apiClient';
import { reportPageData, clearPageData } from '../../lib/pageDataBridge';

interface MechanismStatus {
  status: string;
  detail: string;
}

interface DashboardData {
  overall_health: number;
  health_level: string;
  mechanism_status: Record<string, MechanismStatus>;
  pending_approvals: number;
  mapping_coverage: Array<{ domain_id: string; source_id: string; coverage: number; status: string }>;
  cycle_history: Array<{ cycle_id: string; domain_id: string; overall_health: number; health_level: string }>;
  audit_summary: { total_events_today: number; denied_calls: number };
}

// HarnessEval 落地：评测观测聚合视图（证据树 + 路由 trace + 经验状态）
interface EvalObservabilityData {
  sources: Array<{ kind: string; path: string; present: boolean }>;
  evidence_tree: null | {
    present: boolean;
    verdict?: { score: number; confidence?: string; summary?: string };
    known_gaps?: Array<{ claim?: string; file?: string; line?: number }>;
    cross_check_issues?: number;
  };
  guard_trace: null | {
    present: boolean;
    mode?: string;
    verdict?: string;
    failed_guards?: string[];
    skipped_checks?: Array<{ check?: string; reason_skipped?: string | null }>;
  };
  experiences: {
    count: number;
    by_status: Record<string, number>;
    recent: Array<{ rule_id?: string; status?: string; content?: string }>;
  };
  org_harness?: OrgHarnessData | null;
}

/** Duty-board verdict — never invent success_rate */
interface DutyBoard {
  status?: 'go' | 'watch' | 'block' | 'unavailable' | string;
  label?: string;
  reasons?: string[];
  availability?: { runs?: boolean; gold?: boolean; approvals?: boolean };
  checks?: Record<string, string>;
  thresholds?: Record<string, number>;
  thresholds_source?: string;
  release_habit?: string;
}

/** Org harness dark ledger — HITL / approvals + gold P/R / P0 miss */
interface OrgHarnessData {
  ok?: boolean;
  scope?: string;
  data_available?: boolean;
  availability?: { runs?: boolean; gold?: boolean; approvals?: boolean };
  duty_board?: DutyBoard;
  summary?: {
    runs_scanned?: number;
    hitl_wait_sec_total?: number;
    avg_serial_ratio?: number | null;
    serial_ratio?: number | null;
    wall_sec?: number | null;
    approval_count?: number;
    approval_pending?: number;
    avg_approval_latency_sec?: number | null;
    avg_approvals_per_run?: number | null;
    hitl_episode_count?: number;
    open_unresolved?: number;
    gold_precision?: number | null;
    gold_recall?: number | null;
    gold_p0_recall?: number | null;
    p0_miss_rate?: number | null;
    gold_regressing?: boolean;
    gold_novel_count?: number | null;
    gold_avg_comment_count?: number | null;
    gold_elapsed_sec?: number | null;
  };
  recommendations?: Array<{ severity?: string; action?: string; detail?: string }>;
  runs?: Array<{
    run_id?: string;
    serial_ratio?: number | null;
    hitl_wait_sec_total?: number;
    wall_sec?: number | null;
  }>;
  gold_regression?: {
    report_count?: number;
    p0_miss_rate?: number | null;
    regressing?: boolean;
    latest?: {
      precision?: number | null;
      recall?: number | null;
      p0_recall?: number | null;
      novel_count?: number | null;
      avg_comment_count?: number | null;
      elapsed_sec?: number | null;
      written_at?: string;
      profile?: string;
      harness_factors?: Record<string, unknown> | null;
    } | null;
    delta_vs_prev?: {
      precision?: number | null;
      recall?: number | null;
      p0_recall?: number | null;
      avg_comment_count?: number | null;
      elapsed_sec?: number | null;
    } | null;
    harness_factor_delta?: Record<string, { from?: unknown; to?: unknown }>;
  };
  notes?: string[];
}

/** Task / intervention KPIs (Agent vs chat) — never invent fake success_rate */
interface AdoptionReport {
  total_agent_calls?: number;
  total_users?: number;
  active_users_7d?: number;
  grill_trigger_rate?: number;
  grill_completion_rate?: number;
  hitl_approval_rate?: number;
  hitl_rejection_rate?: number;
  adoption_trend?: string;
  resistance_hotspots?: Array<{ reason?: string; count?: number } | string>;
  recommendations?: string[];
  computed_at?: string;
  howl_interventions?: number | null;
  howl_by_reason?: Record<string, number>;
  howl_status?: string;
}

const statusIcons: Record<string, string> = { good: '✅', warning: '⚠️', attention: '🟡', unknown: '❓' };
const statusLabels: Record<string, string> = {
  version_management: '版本管理', change_approval: '变更审批', mapping_validation: '映射验证',
  asset_publishing: '资产发布', agent_audit: 'Agent审计', quality_evaluation: '质量评估',
  feedback_loop: '反馈闭环',
};

export default function GovernanceDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [evalObs, setEvalObs] = useState<EvalObservabilityData | null>(null);
  const [orgHarness, setOrgHarness] = useState<OrgHarnessData | null>(null);
  const [adoption, setAdoption] = useState<AdoptionReport | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await apiClient.get<DashboardData>('/platform/apps/ontology-editor/governance/dashboard');
      setData(res);
    } catch {}
    try {
      const ev = await apiClient.get<EvalObservabilityData>('/governance/eval-observability');
      setEvalObs(ev);
      if (ev?.org_harness?.ok) setOrgHarness(ev.org_harness);
    } catch {}
    try {
      const oh = await apiClient.get<OrgHarnessData>('/governance/org-harness?recent_limit=10');
      if (oh?.ok) setOrgHarness(oh);
    } catch {}
    try {
      const ad = await apiClient.get<{ status?: string; report?: AdoptionReport }>(
        '/core/diagnostics/adoption-metrics',
      );
      setAdoption(ad?.report || null);
    } catch {
      setAdoption(null);
    }
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, []);

  if (loading) return <div style={{ padding: 20, color: '#888', fontFamily: 'monospace' }}>Loading...</div>;
  if (!data) return <div style={{ padding: 20, color: '#f88', fontFamily: 'monospace' }}>Failed to load governance data</div>;

  const hColor =
    data.health_level === 'good' ? '#4a4'
    : data.health_level === 'warning' ? '#aa4'
    : data.health_level === 'unknown' || data.overall_health == null ? '#666'
    : '#a44';

  // Server-authoritative duty board (org-harness already merges adoption/HITL/Howl).
  // Never invent success_rate; missing board → unavailable.
  const duty: DutyBoard = orgHarness?.duty_board || {
    status: 'unavailable',
    label: 'UNAVAILABLE',
    reasons: ['org-harness duty_board unavailable — never invent success_rate'],
    checks: {
      gold: 'unavailable',
      serial: 'unavailable',
      approvals: 'unavailable',
      hitl: 'unavailable',
      howl: 'unavailable',
    },
    release_habit: 'run ops_harness_ready_check.sh + gold match-only before release',
  };
  const dutyColors: Record<string, string> = {
    go: '#4a4', watch: '#aa4', block: '#a44', unavailable: '#666',
  };
  const dutyColor = dutyColors[String(duty.status || 'unavailable')] || '#666';
  const checkOrUnavailable = (key: string) =>
    duty.checks?.[key] || 'unavailable';
  const goldAvail = orgHarness?.availability?.gold === true;
  const runsAvail = orgHarness?.availability?.runs === true;
  const serialVal =
    orgHarness?.summary?.avg_serial_ratio ?? orgHarness?.summary?.serial_ratio ?? null;
  const goldP = orgHarness?.summary?.gold_precision;
  const p0Miss = orgHarness?.summary?.p0_miss_rate;
  const approvalLat = orgHarness?.summary?.avg_approval_latency_sec;

  // P2-4: 向数字人上报治理仪表盘实时状态
  useEffect(() => {
    const mechanism = Object.fromEntries(
      Object.entries(data.mechanism_status || {}).map(([k, v]) => [k, v.status])
    );
    const attentionCount = Object.values(data.mechanism_status || {}).filter(v => v.status !== 'good').length;
    reportPageData('/governance', {
      overallHealth: data.overall_health,
      healthLevel: data.health_level,
      pendingApprovals: data.pending_approvals,
      todayCalls: data.audit_summary?.total_events_today || 0,
      deniedCalls: data.audit_summary?.denied_calls || 0,
      mechanismsNeedingAttention: attentionCount,
      mechanismStatus: mechanism,
    });
    return () => clearPageData('/governance');
  }, [data]);

  return (
    <div style={{ padding: 24, fontFamily: 'monospace', fontSize: 13, background: '#0f0f1a', minHeight: '100vh', color: '#d0d0d0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
        <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
          <Shield size={22} /> 治理仪表盘
        </h2>
        <button onClick={fetchData} style={iconBtnStyle}><RefreshCw size={16} /> 刷新</button>
      </div>

      {/* Health cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        <Card
          title="治理健康"
          value={data.overall_health == null ? 'unavailable' : `${data.overall_health}/100`}
          color={hColor}
          icon={<Activity size={18} />}
        />
        <Card title="健康等级" value={data.health_level || 'unknown'} color={hColor} icon={<Shield size={18} />} />
        <Card title="待审批" value={String(data.pending_approvals)} color="#aa4" icon={<AlertTriangle size={18} />} />
        <Card title="今日调用" value={String(data.audit_summary?.total_events_today || 0)} color="#4af" icon={<FileText size={18} />} />
      </div>

      {/* Duty board — release habit; never invent success_rate */}
      <div style={{
        marginBottom: 20, padding: '12px 16px', borderRadius: 8,
        border: `1px solid ${dutyColor}`, background: '#141422',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Shield size={18} color={dutyColor} />
            <span style={{ fontWeight: 700, color: dutyColor, fontSize: 15 }}>
              值班板 {duty.label || 'UNAVAILABLE'}
            </span>
            <span style={{ fontSize: 11, color: '#666' }}>
              gold={checkOrUnavailable('gold')}
              {' · '}serial={checkOrUnavailable('serial')}
              {' · '}approvals={checkOrUnavailable('approvals')}
              {' · '}hitl={checkOrUnavailable('hitl')}
              {' · '}howl={checkOrUnavailable('howl')}
            </span>
          </div>
          <span style={{ fontSize: 11, color: '#888' }}>
            {orgHarness?.availability
              ? `avail runs=${orgHarness.availability.runs ? 'y' : 'n'} gold=${orgHarness.availability.gold ? 'y' : 'n'} appr=${orgHarness.availability.approvals ? 'y' : 'n'}`
              : 'avail unknown'}
          </span>
        </div>
        {(duty.reasons?.length || 0) > 0 && (
          <div style={{ marginTop: 8, fontSize: 12, color: '#aaa' }}>
            {duty.reasons!.slice(0, 4).map((r, i) => (
              <div key={i}>· {r}</div>
            ))}
          </div>
        )}
        {duty.release_habit && (
          <div style={{ marginTop: 6, fontSize: 11, color: '#666' }}>{duty.release_habit}</div>
        )}
        {duty.thresholds_source && (
          <div style={{ marginTop: 4, fontSize: 10, color: '#555' }}>
            thresholds={duty.thresholds_source}
            {duty.thresholds?.p0_miss_rate_block != null
              ? ` · p0_block=${duty.thresholds.p0_miss_rate_block}`
              : ''}
            {duty.thresholds?.serial_ratio_high != null
              ? ` · serial_high=${duty.thresholds.serial_ratio_high}`
              : ''}
          </div>
        )}
      </div>

      {/* 7 mechanism status */}
      <div style={{ marginBottom: 20 }}>
        <h4 style={{ margin: '0 0 10px', fontSize: 14, color: '#888' }}>7 机制状态</h4>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {Object.entries(data.mechanism_status || {}).map(([key, val]) => (
            <span key={key} style={{
              padding: '6px 12px', borderRadius: 6, fontSize: 12,
              background: val.status === 'good' ? '#1a2a1a' : val.status === 'warning' ? '#2a2a1a' : '#1a1a2a',
              border: `1px solid ${val.status === 'good' ? '#3a3' : val.status === 'warning' ? '#aa3' : '#333'}`,
            }}>
              {statusIcons[val.status] || '❓'} {statusLabels[key] || key}: {val.detail?.slice(0, 40)}
            </span>
          ))}
        </div>
      </div>

      {/* Mapping coverage + Cycle History */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Mapping coverage */}
        <div>
          <h4 style={{ margin: '0 0 10px', fontSize: 14, color: '#888' }}>数据→语义映射覆盖率</h4>
          {data.mapping_coverage?.length ? (
            data.mapping_coverage.map((m, i) => (
              <div key={i} style={{ padding: '8px 12px', marginBottom: 6, borderRadius: 4,
                background: m.coverage >= 80 ? '#1a2a1a' : m.coverage >= 50 ? '#2a2a1a' : '#2a1a1a',
                display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                <span>{m.domain_id || m.source_id}</span>
                <span style={{ color: m.coverage >= 80 ? '#4a4' : m.coverage >= 50 ? '#aa4' : '#a44' }}>
                  {m.coverage}% {m.status === 'good' ? '✅' : m.status === 'warning' ? '⚠️' : '🔴'}
                </span>
              </div>
            ))
          ) : <div style={{ color: '#555', fontSize: 12 }}>No data sources configured</div>}
        </div>

        {/* Cycle history */}
        <div>
          <h4 style={{ margin: '0 0 10px', fontSize: 14, color: '#888' }}>治理循环历史</h4>
          {data.cycle_history?.length ? (
            data.cycle_history.map((c, i) => (
              <div key={i} style={{ padding: '6px 10px', marginBottom: 4, borderRadius: 4,
                background: c.overall_health >= 80 ? '#1a2a1a' : c.overall_health >= 60 ? '#2a2a1a' : '#2a1a1a',
                display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                <span>{c.domain_id}</span>
                <span style={{ color: c.overall_health >= 80 ? '#4a4' : c.overall_health >= 60 ? '#aa4' : '#a44' }}>
                  {c.overall_health} {c.health_level === 'good' ? '✅' : c.health_level === 'warning' ? '⚠️' : '🔴'}
                </span>
              </div>
            ))
          ) : <div style={{ color: '#555', fontSize: 12 }}>No cycles run yet. Click [运行全量] to start.</div>}
        </div>
      </div>

      {/* Agent task KPIs — success is intervention + adoption, not chat length */}
      <div style={{ marginTop: 24, borderTop: '1px solid #222', paddingTop: 16 }}>
        <h4 style={{ margin: '0 0 10px', fontSize: 14, color: '#888' }}>
          <CheckCircle size={14} style={{ verticalAlign: -2, marginRight: 4 }} />
          任务采纳 / 干预（Agent KPI，非对话时长）
        </h4>
        {!adoption ? (
          <div style={{ color: '#555', fontSize: 12 }}>采纳指标暂不可用（unavailable，不展示假成功率）</div>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 12 }}>
              <Card title="任务成功率" value="unavailable" color="#666" />
              <Card title="Agent 调用" value={String(adoption.total_agent_calls ?? '—')} color="#4af" />
              <Card title="7 日活跃用户" value={String(adoption.active_users_7d ?? '—')} color="#4a4" />
              <Card
                title="HITL 通过率"
                value={
                  adoption.hitl_approval_rate != null
                    ? `${(Number(adoption.hitl_approval_rate) * 100).toFixed(0)}%`
                    : 'unavailable'
                }
                color={adoption.hitl_approval_rate != null ? '#aa4' : '#666'}
              />
              <Card
                title="HITL 驳回率"
                value={
                  adoption.hitl_rejection_rate != null
                    ? `${(Number(adoption.hitl_rejection_rate) * 100).toFixed(0)}%`
                    : 'unavailable'
                }
                color={adoption.hitl_rejection_rate != null ? '#a44' : '#666'}
                icon={<AlertTriangle size={18} />}
              />
            </div>
            <div style={{ fontSize: 11, color: '#555', marginBottom: 8 }}>
              任务成功率未接组织级口径 → 标 unavailable（禁止用对话时长假绿）
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 8 }}>
              <Card
                title="澄清触发 / 完成"
                value={
                  adoption.grill_trigger_rate != null || adoption.grill_completion_rate != null
                    ? `${adoption.grill_trigger_rate ?? 'unavailable'} / ${adoption.grill_completion_rate ?? 'unavailable'}`
                    : 'unavailable'
                }
                color="#888"
              />
              <Card title="采纳趋势" value={String(adoption.adoption_trend || 'unavailable')} color="#666" />
              <Card
                title="Howl 干预次数"
                value={
                  adoption.howl_interventions != null
                    ? String(adoption.howl_interventions)
                    : 'unavailable'
                }
                color={adoption.howl_interventions != null ? '#a84' : '#666'}
              />
            </div>
            {adoption.howl_by_reason && Object.keys(adoption.howl_by_reason).length > 0 && (
              <div style={{ fontSize: 11, color: '#666', marginBottom: 8 }}>
                干预原因：{Object.entries(adoption.howl_by_reason).map(([k, v]) => `${k}=${v}`).join(' · ')}
              </div>
            )}
            {adoption.computed_at && (
              <div style={{ fontSize: 11, color: '#555', marginBottom: 8 }}>@ {adoption.computed_at}</div>
            )}
          </>
        )}
      </div>

      {/* Org harness — HITL serial / approval Amdahl dark ledger */}
      <div style={{ marginTop: 24, borderTop: '1px solid #222', paddingTop: 16 }}>
        <h4 style={{ margin: '0 0 10px', fontSize: 14, color: '#888' }}>
          <Activity size={14} style={{ verticalAlign: -2, marginRight: 4 }} />
          组织 Harness（HITL / 审批 / 黄金集 / P0 漏检）
        </h4>
        {!orgHarness?.ok ? (
          <div style={{ color: '#555', fontSize: 12 }}>未获取到组织 harness 指标（无近期 pipeline 运行或审批记录）</div>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 12 }}>
              <Card
                title="串行比 serial_ratio"
                value={serialVal != null ? String(serialVal) : 'unavailable'}
                color={serialVal != null ? '#aa4' : '#666'}
                icon={<Activity size={18} />}
              />
              <Card
                title="HITL 等待(s)"
                value={runsAvail ? String(orgHarness.summary?.hitl_wait_sec_total ?? 0) : 'unavailable'}
                color={runsAvail ? '#4af' : '#666'}
              />
              <Card
                title="审批数 / 待审"
                value={`${orgHarness.summary?.approval_count ?? 0} / ${orgHarness.summary?.approval_pending ?? 0}`}
                color="#a84"
                icon={<AlertTriangle size={18} />}
              />
              <Card
                title="审批均延迟(s)"
                value={approvalLat != null ? String(approvalLat) : 'unavailable'}
                color={approvalLat != null ? '#4a4' : '#666'}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 12 }}>
              <Card
                title="Gold Precision"
                value={goldP != null ? String(goldP) : 'unavailable'}
                color={
                  !goldAvail || goldP == null
                    ? '#666'
                    : orgHarness.summary?.gold_regressing
                      ? '#a44'
                      : '#4a4'
                }
              />
              <Card
                title="Gold Recall / P0"
                value={
                  goldAvail
                    ? `${orgHarness.summary?.gold_recall ?? '—'} / ${orgHarness.summary?.gold_p0_recall ?? '—'}`
                    : 'unavailable'
                }
                color={goldAvail ? '#4af' : '#666'}
              />
              <Card
                title="P0 漏检率"
                value={p0Miss != null ? String(p0Miss) : 'unavailable'}
                color={
                  p0Miss == null
                    ? '#666'
                    : p0Miss > 0
                      ? '#a44'
                      : '#4a4'
                }
                icon={<AlertTriangle size={18} />}
              />
              <Card
                title="评论数 / 耗时(s)"
                value={
                  goldAvail
                    ? `${orgHarness.summary?.gold_avg_comment_count ?? '—'} / ${orgHarness.summary?.gold_elapsed_sec ?? '—'}`
                    : 'unavailable'
                }
                color="#888"
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12, marginBottom: 12 }}>
              <Card
                title="Novel / 回归"
                value={
                  goldAvail
                    ? `${orgHarness.summary?.gold_novel_count ?? '—'} / ${orgHarness.summary?.gold_regressing ? '↓' : 'ok'}`
                    : 'unavailable'
                }
                color={
                  !goldAvail
                    ? '#666'
                    : orgHarness.summary?.gold_regressing
                      ? '#a44'
                      : '#888'
                }
              />
              <Card
                title="四指标口径"
                value="P · R · P0miss · comments/time"
                color="#666"
              />
            </div>
            {orgHarness.gold_regression?.delta_vs_prev && (
              <div style={{ fontSize: 11, color: '#666', marginBottom: 8 }}>
                Δ vs 上次：P {orgHarness.gold_regression.delta_vs_prev.precision ?? '—'}
                {' · '}R {orgHarness.gold_regression.delta_vs_prev.recall ?? '—'}
                {' · '}P0 {orgHarness.gold_regression.delta_vs_prev.p0_recall ?? '—'}
                {' · '}comments {orgHarness.gold_regression.delta_vs_prev.avg_comment_count ?? '—'}
                {' · '}time {orgHarness.gold_regression.delta_vs_prev.elapsed_sec ?? '—'}
                {orgHarness.gold_regression.latest?.written_at
                  ? ` · @ ${orgHarness.gold_regression.latest.written_at}`
                  : ''}
              </div>
            )}
            {orgHarness.gold_regression?.harness_factor_delta &&
              Object.keys(orgHarness.gold_regression.harness_factor_delta).length > 0 && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 11, color: '#888', marginBottom: 6 }}>
                  Harness 因子漂移（同 profile 下非 model 变更）
                </div>
                {Object.entries(orgHarness.gold_regression.harness_factor_delta).slice(0, 8).map(([k, v]) => (
                  <div key={k} style={{
                    padding: '4px 10px', marginBottom: 3, borderRadius: 4, background: '#111',
                    fontSize: 11, color: '#aaa',
                  }}>
                    <span style={{ color: '#4af' }}>{k}</span>
                    {': '}
                    {String(v?.from ?? '—')} → {String(v?.to ?? '—')}
                  </div>
                ))}
              </div>
            )}
            {(orgHarness.recommendations?.length || 0) > 0 && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 11, color: '#888', marginBottom: 6 }}>串行链改造建议</div>
                {orgHarness.recommendations!.slice(0, 5).map((rec, i) => (
                  <div key={i} style={{
                    padding: '6px 10px', marginBottom: 4, borderRadius: 4, background: '#111',
                    borderLeft: `3px solid ${rec.severity === 'high' ? '#a44' : rec.severity === 'medium' ? '#aa4' : '#444'}`,
                    fontSize: 11,
                  }}>
                    <span style={{ color: '#aaa' }}>[{rec.action}]</span> {rec.detail}
                  </div>
                ))}
              </div>
            )}
            {(orgHarness.runs?.length || 0) > 0 && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 11, color: '#666', marginBottom: 6 }}>
                  近期 runs（{orgHarness.summary?.runs_scanned ?? orgHarness.runs!.length}）
                </div>
                {orgHarness.runs!.slice(0, 8).map((r, i) => (
                  <div key={i} style={{
                    padding: '6px 10px', marginBottom: 4, borderRadius: 4, background: '#111',
                    display: 'flex', justifyContent: 'space-between', fontSize: 11,
                  }}>
                    <span style={{ color: '#aaa' }}>{r.run_id || '—'}</span>
                    <span>
                      ratio {r.serial_ratio ?? '—'} · wait {r.hitl_wait_sec_total ?? 0}s
                      {r.wall_sec != null ? ` / wall ${r.wall_sec}s` : ''}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {(orgHarness.notes?.length || 0) > 0 && (
              <div style={{ fontSize: 11, color: '#666' }}>{orgHarness.notes![0]}</div>
            )}
          </>
        )}
      </div>

      {/* HarnessEval 落地：评测观测（证据树 + 路由 trace + 经验状态） */}
      <div style={{ marginTop: 24, borderTop: '1px solid #222', paddingTop: 16 }}>
        <h4 style={{ margin: '0 0 10px', fontSize: 14, color: '#888' }}>
          <FileText size={14} style={{ verticalAlign: -2, marginRight: 4 }} />
          评测观测（证据树 / 路由 trace / 经验回写）
        </h4>
        {!evalObs ? (
          <div style={{ color: '#555', fontSize: 12 }}>未获取到评测观测数据（运行时未配置评测产物）</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
            {/* 证据树 */}
            <div style={{ padding: 10, borderRadius: 6, background: '#111', border: '1px solid #333' }}>
              <div style={{ fontSize: 11, color: '#888', marginBottom: 6 }}>证据树 Evidence Tree</div>
              {evalObs.evidence_tree?.verdict ? (
                <>
                  <div style={{ fontSize: 16, fontWeight: 700, color: evalObs.evidence_tree.verdict.score >= 1 ? '#4a4' : '#a44' }}>
                    score {evalObs.evidence_tree.verdict.score}
                  </div>
                  <div style={{ fontSize: 11, color: '#777', marginTop: 4 }}>{evalObs.evidence_tree.verdict.summary}</div>
                </>
              ) : <div style={{ color: '#555', fontSize: 12 }}>无产物</div>}
              {(evalObs.evidence_tree?.known_gaps?.length || 0) > 0 && (
                <div style={{ marginTop: 6, fontSize: 11, color: '#aa4' }}>
                  ⚠️ known_gaps: {evalObs.evidence_tree!.known_gaps!.length}
                </div>
              )}
              {(evalObs.evidence_tree?.cross_check_issues || 0) > 0 && (
                <div style={{ marginTop: 4, fontSize: 11, color: '#aa4' }}>
                  ⚠️ cross_check_issues: {evalObs.evidence_tree!.cross_check_issues}
                </div>
              )}
            </div>
            {/* 路由 trace */}
            <div style={{ padding: 10, borderRadius: 6, background: '#111', border: '1px solid #333' }}>
              <div style={{ fontSize: 11, color: '#888', marginBottom: 6 }}>守卫路由 trace</div>
              {evalObs.guard_trace?.verdict ? (
                <>
                  <div style={{ fontSize: 16, fontWeight: 700, color: evalObs.guard_trace.verdict === 'pass' ? '#4a4' : '#a44' }}>
                    {evalObs.guard_trace.verdict}
                    <span style={{ fontSize: 11, color: '#777', marginLeft: 8 }}>{evalObs.guard_trace.mode} 模式</span>
                  </div>
                  {(evalObs.guard_trace.skipped_checks?.length || 0) > 0 && (
                    <div style={{ marginTop: 6, fontSize: 11, color: '#777' }}>
                      跳过: {evalObs.guard_trace!.skipped_checks!.map(c => c.check).join(', ')}
                    </div>
                  )}
                  {(evalObs.guard_trace.failed_guards?.length || 0) > 0 && (
                    <div style={{ marginTop: 4, fontSize: 11, color: '#a44' }}>
                      ❌ {evalObs.guard_trace!.failed_guards!.join(', ')}
                    </div>
                  )}
                </>
              ) : <div style={{ color: '#555', fontSize: 12 }}>无产物</div>}
            </div>
            {/* 经验状态 */}
            <div style={{ padding: 10, borderRadius: 6, background: '#111', border: '1px solid #333' }}>
              <div style={{ fontSize: 11, color: '#888', marginBottom: 6 }}>经验回写 L2</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: '#4af' }}>{evalObs.experiences.count}</div>
              <div style={{ fontSize: 11, color: '#777', marginTop: 4 }}>
                pending {evalObs.experiences.by_status.pending || 0} · promoted {evalObs.experiences.by_status.promoted || 0}
                {' · '}rejected {evalObs.experiences.by_status.rejected || 0}
                {' · '}待确认 {(evalObs.experiences.by_status['promoted:review'] || 0)}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Card({ title, value, color, icon }: { title: string; value: string; color: string; icon?: any }) {
  return (
    <div style={{ padding: 16, borderRadius: 8, background: '#111', border: `1px solid ${color}44` }}>
      <div style={{ fontSize: 11, color: '#888', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
        {icon} {title}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color }}>{value}</div>
    </div>
  );
}

const iconBtnStyle: React.CSSProperties = {
  background: '#222', border: '1px solid #444', color: '#ccc', cursor: 'pointer',
  padding: '6px 12px', borderRadius: 4, fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 4,
};
