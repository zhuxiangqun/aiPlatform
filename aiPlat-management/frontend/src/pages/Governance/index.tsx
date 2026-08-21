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

const statusIcons: Record<string, string> = { good: '✅', warning: '⚠️', attention: '🟡', unknown: '❓' };
const statusLabels: Record<string, string> = {
  version_management: '版本管理', change_approval: '变更审批', mapping_validation: '映射验证',
  asset_publishing: '资产发布', agent_audit: 'Agent审计', quality_evaluation: '质量评估',
  feedback_loop: '反馈闭环',
};

export default function GovernanceDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await apiClient.get<DashboardData>('/platform/apps/ontology-editor/governance/dashboard');
      setData(res);
    } catch {}
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, []);

  if (loading) return <div style={{ padding: 20, color: '#888', fontFamily: 'monospace' }}>Loading...</div>;
  if (!data) return <div style={{ padding: 20, color: '#f88', fontFamily: 'monospace' }}>Failed to load governance data</div>;

  const hColor = data.health_level === 'good' ? '#4a4' : data.health_level === 'warning' ? '#aa4' : '#a44';

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
        <Card title="治理健康" value={`${data.overall_health}/100`} color={hColor} icon={<Activity size={18} />} />
        <Card title="健康等级" value={data.health_level} color={hColor} icon={<Shield size={18} />} />
        <Card title="待审批" value={String(data.pending_approvals)} color="#aa4" icon={<AlertTriangle size={18} />} />
        <Card title="今日调用" value={String(data.audit_summary?.total_events_today || 0)} color="#4af" icon={<FileText size={18} />} />
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
