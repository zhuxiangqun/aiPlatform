/**
 * RoleManager — Configure and monitor the four-role agent system.
 *
 * Roles:
 *   员工(Employee) — fast, cost-effective executor
 *   保安(Guard)     — anomaly defense and safety
 *   顾问(Advisor)   — quality optimizer with reflection
 *   协调员(Orchestrator) — goal-aware routing strategy
 */
import React, { useState, useEffect } from 'react';

interface AgentConfig {
  agent_id: string;
  role: string;
  model?: string;
  reflection_enabled?: boolean;
  last_updated?: string;
}

interface RoleMetrics {
  employee: any;
  guard: any;
  advisor: any;
  orchestrator: any;
}

const ROLE_INFO: Record<string, { icon: string; label: string; desc: string; color: string }> = {
  employee: { icon: '⚡', label: '员工', desc: '快速/低成本执行', color: '#3b82f6' },
  guard: { icon: '🛡️', label: '保安', desc: '安全/合规/拦截', color: '#ef4444' },
  advisor: { icon: '🔍', label: '顾问', desc: '创新/质量/优化', color: '#22c55e' },
  orchestrator: { icon: '🎯', label: '协调员', desc: '目标感知调度', color: '#eab308' },
};

const MODES = [
  { key: 'normal', label: '正常模式' },
  { key: 'speed', label: '提速模式' },
  { key: 'quality', label: '提质模式' },
  { key: 'guard', label: '加固模式' },
  { key: 'pause', label: '暂停' },
];

const RoleManager: React.FC = () => {
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [metrics, setMetrics] = useState<RoleMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    const [aRes, mRes] = await Promise.all([
      fetch('/api/core/roles/agents').then(r => r.json()).catch(() => []),
      fetch('/api/core/roles/metrics').then(r => r.json()).catch(() => ({})),
    ]);
    setAgents(Array.isArray(aRes) ? aRes : (aRes.agents || []));
    setMetrics(mRes);
    setLoading(false);
  };

  const updateRole = async (agentId: string, role: string) => {
    await fetch(`/api/core/roles/agents/${agentId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role }),
    });
    fetchData();
  };

  const overrideMode = async (agentId: string, mode: string) => {
    await fetch('/api/core/roles/strategy/override', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: agentId, mode }),
    });
    fetchData();
  };

  if (loading) return <div style={{ padding: 24, color: '#94a3b8' }}>加载中...</div>;

  return (
    <div style={{ padding: 24, background: '#0f172a', minHeight: '100vh', color: '#e2e8f0' }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Role Manager</h1>

      {/* Metrics Cards */}
      {metrics && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
          {Object.entries(ROLE_INFO).map(([key, info]) => {
            const m = (metrics as any)[key] || {};
            const value = key === 'employee' ? m.status :
              key === 'guard' ? `${m.attacks_memorized || 0}攻击` :
              key === 'advisor' ? `${m.drafts_in_storage || 0}草稿` :
              `${m.total_goals || 0}目标`;
            return (
              <div key={key} style={cardStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontSize: 24 }}>{info.icon}</span>
                  <span style={{ fontSize: 13, color: info.color, fontWeight: 600 }}>{info.label}</span>
                </div>
                <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>{value}</div>
                <div style={{ fontSize: 12, color: '#94a3b8' }}>{info.desc}</div>
              </div>
            );
          })}
        </div>
      )}

      {/* Agent Table */}
      <div style={cardStyle}>
        <h2 style={{ fontSize: 18, marginBottom: 16 }}>Agent 角色分配</h2>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #334155', textAlign: 'left' }}>
              <th style={{ padding: '8px 12px' }}>Agent</th>
              <th style={{ padding: '8px 12px' }}>角色</th>
              <th style={{ padding: '8px 12px' }}>快速操作</th>
            </tr>
          </thead>
          <tbody>
            {agents.map(a => {
              const isService = a.role === 'system_service' || a.agent_type === 'system_service';
              return (
              <tr key={a.agent_id} style={{ borderBottom: '1px solid #1e293b' }}>
                <td style={{ padding: '8px 12px' }}>
                  <div style={{ fontWeight: 600 }}>{a.agent_id}</div>
                  {a.model && <div style={{ fontSize: 12, color: '#94a3b8' }}>{a.model}</div>}
                  {a.description && <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{a.description}</div>}
                </td>
                <td style={{ padding: '8px 12px' }}>
                  {isService ? (
                    <span style={{ fontSize: 12, color: '#a855f7', fontWeight: 600, padding: '4px 10px', background: '#a855f710', borderRadius: 4 }}>
                      🔧 系统服务
                    </span>
                  ) : (
                    <select value={a.role} onChange={e => updateRole(a.agent_id, e.target.value)}
                      style={{
                        background: '#1e293b', border: '1px solid #334155', borderRadius: 6,
                        padding: '6px 12px', color: '#e2e8f0', fontSize: 13,
                      }}>
                      {Object.entries(ROLE_INFO).map(([k, v]) => (
                        <option key={k} value={k}>{v.icon} {v.label}</option>
                      ))}
                    </select>
                  )}
                </td>
                <td style={{ padding: '8px 12px' }}>
                  {isService ? (
                    <span style={{ fontSize: 12, color: '#64748b' }}>EvolutionEngine 自动调度</span>
                  ) : (
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {MODES.slice(0, -1).map(m => (
                        <button key={m.key} onClick={() => overrideMode(a.agent_id, m.key)}
                          style={{
                            padding: '4px 10px', borderRadius: 4, border: 'none', cursor: 'pointer',
                            fontSize: 11, fontWeight: 600,
                            background: '#1e293b', color: '#94a3b8',
                          }}>
                          {m.label}
                        </button>
                      ))}
                    </div>
                  )}
                </td>
              </tr>
            )})}
          </tbody>
        </table>
      </div>

      {/* Role Descriptions */}
      <div style={{ ...cardStyle, marginTop: 16 }}>
        <h2 style={{ fontSize: 18, marginBottom: 16 }}>角色说明</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
          {Object.entries(ROLE_INFO).map(([key, info]) => (
            <div key={key} style={{ padding: 12, border: `1px solid ${info.color}20`, borderRadius: 8, background: `${info.color}10` }}>
              <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>
                {info.icon} {info.label} <span style={{ color: info.color, fontSize: 13 }}>({key})</span>
              </div>
              <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 8 }}>{info.desc}</div>
              {key === 'employee' && <div style={{ fontSize: 12, color: '#64748b' }}>ReActLoop + 轻量模型 + 确定性工具</div>}
              {key === 'guard' && <div style={{ fontSize: 12, color: '#64748b' }}>ImmuneMemory + CircuitBreaker + ApprovalGate</div>}
              {key === 'advisor' && <div style={{ fontSize: 12, color: '#64748b' }}>SkillOpt双通道 + DynamicRouter反射模式</div>}
              {key === 'orchestrator' && <div style={{ fontSize: 12, color: '#64748b' }}>BusinessGoalTracker + GoalAwareRouter</div>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const cardStyle: React.CSSProperties = {
  background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: 20,
};

export default RoleManager;
