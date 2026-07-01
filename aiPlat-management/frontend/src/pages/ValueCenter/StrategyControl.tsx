/**
 * StrategyControl — Manual override for GoalAwareRouter + agent mode adjustment.
 *
 * Routes: Value Center → Strategy Control
 * API: GET /api/core/value/all/strategy + POST /api/core/roles/strategy/override
 */
import React, { useState, useEffect } from 'react';

interface StrategyStatus { params: Record<string, any>; context: string; goals_count: number; }
interface AgentConfig { agent_id: string; role: string; }

const MODE_OPTIONS = [
  { key: 'normal', label: '正常', desc: '自动根据目标状态调整', color: '#94a3b8' },
  { key: 'speed', label: '提速', desc: '减少审批, 并行执行, max_steps=10', color: '#3b82f6' },
  { key: 'quality', label: '提质', desc: '强制反思, 使用强模型', color: '#22c55e' },
  { key: 'guard', label: '加固', desc: '所有外部调用强制人工确认', color: '#ef4444' },
];

const StrategyControl: React.FC = () => {
  const [strategy, setStrategy] = useState<StrategyStatus | null>(null);
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch('/api/core/value/all/strategy').then(r => r.json()),
      fetch('/api/core/roles/agents').then(r => r.json()),
    ]).then(([s, a]) => {
      setStrategy(s);
      setAgents(a);
      setLoading(false);
    });
  }, []);

  const overrideAgent = async (agentId: string, mode: string) => {
    await fetch('/api/core/roles/strategy/override', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: agentId, mode }),
    });
    setOverrides({ ...overrides, [agentId]: mode });
  };

  if (loading) return <div style={pageStyle}><p style={{ color: '#94a3b8' }}>加载中...</p></div>;

  return (
    <div style={pageStyle}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Strategy Control</h1>

      {/* Strategy Context */}
      {strategy && (
        <div style={{ ...cardStyle, marginBottom: 16, borderLeft: '4px solid #eab308' }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>🛡️ 自动策略 (GoalAwareRouter)</div>
          {strategy.context ? (
            <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, color: '#e2e8f0', marginBottom: 12 }}>{strategy.context}</div>
          ) : (
            <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 12 }}>所有业务目标正常，无需策略调整</div>
          )}
          <div style={{ fontSize: 12, color: '#94a3b8' }}>
            活跃目标: {strategy.goals_count} · 检测参数: {JSON.stringify(strategy.params)}
          </div>
        </div>
      )}

      {/* Mode Descriptions */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: 24 }}>
        {MODE_OPTIONS.map(m => (
          <div key={m.key} style={{ ...cardStyle, borderLeft: `4px solid ${m.color}` }}>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>{m.label}模式</div>
            <div style={{ fontSize: 12, color: '#94a3b8' }}>{m.desc}</div>
          </div>
        ))}
      </div>

      {/* Agent Manual Override */}
      <div style={cardStyle}>
        <h2 style={{ fontSize: 16, marginBottom: 16 }}>手动调整 (按Agent)</h2>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #334155', textAlign: 'left' }}>
              <th style={thStyle}>Agent</th>
              <th style={thStyle}>当前角色</th>
              <th style={thStyle}>手动模式</th>
              <th style={thStyle}>操作</th>
            </tr>
          </thead>
          <tbody>
            {agents.map(a => (
              <tr key={a.agent_id} style={{ borderBottom: '1px solid #1e293b' }}>
                <td style={tdStyle}>{a.agent_id}</td>
                <td style={tdStyle}>{a.role}</td>
                <td style={tdStyle}>
                  {overrides[a.agent_id] ? (
                    <span style={{ color: MODE_OPTIONS.find(m => m.key === overrides[a.agent_id])?.color }}>
                      {MODE_OPTIONS.find(m => m.key === overrides[a.agent_id])?.label}
                    </span>
                  ) : <span style={{ color: '#64748b' }}>自动</span>}
                </td>
                <td style={tdStyle}>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {MODE_OPTIONS.filter(m => m.key !== 'normal').map(m => (
                      <button key={m.key} onClick={() => overrideAgent(a.agent_id, m.key)}
                        style={{ ...btnMode, background: overrides[a.agent_id] === m.key ? m.color : '#1e293b' }}>
                        {m.label}
                      </button>
                    ))}
                    {overrides[a.agent_id] && (
                      <button onClick={() => overrideAgent(a.agent_id, 'normal')}
                        style={{ ...btnMode, background: '#334155' }}>重置</button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const pageStyle: React.CSSProperties = { padding: 24, background: '#0f172a', minHeight: '100vh', color: '#e2e8f0' };
const cardStyle: React.CSSProperties = { background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: 20 };
const thStyle: React.CSSProperties = { padding: '8px 12px', fontSize: 12, color: '#94a3b8', fontWeight: 600 };
const tdStyle: React.CSSProperties = { padding: '8px 12px', fontSize: 13 };
const btnMode: React.CSSProperties = { border: 'none', borderRadius: 4, padding: '3px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, color: '#e2e8f0' };

export default StrategyControl;
