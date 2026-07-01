/**
 * ValueDashboard — Five-dimension business value overview with role-based views.
 *
 * Three tabs: CEO (strategic) | CFO (financial) | PM (operational)
 * Calls GET /api/core/value/{tenant}?audience=ceo|cfo|pm
 */
import React, { useState, useEffect } from 'react';

interface ValueData {
  hero_number: string;
  hero_label: string;
  breakdown?: { label: string; value: string }[];
  detail_rows?: { label: string; value: string }[];
  goal_summary?: { goal_id: string; description: string; progress_pct: number; achieved: boolean }[];
  total_runs?: number;
  month?: string;
}

const ValueDashboard: React.FC = () => {
  const [audience, setAudience] = useState<'ceo' | 'cfo' | 'pm'>('ceo');
  const [data, setData] = useState<ValueData | null>(null);
  const [loading, setLoading] = useState(false);
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));

  useEffect(() => {
    setLoading(true);
    fetch(`/api/core/value/all?month=${month}&audience=${audience}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [audience, month]);

  const tabs: { key: typeof audience; label: string; desc: string }[] = [
    { key: 'ceo', label: 'CEO视角', desc: '总价值 + 目标达成' },
    { key: 'cfo', label: 'CFO视角', desc: '成本 + 节省明细' },
    { key: 'pm', label: 'PM视角', desc: '准确率 + 满意度' },
  ];

  return (
    <div style={{ padding: 24, background: '#0f172a', minHeight: '100vh', color: '#e2e8f0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700 }}>Value Center</h1>
        <input type="month" value={month} onChange={e => setMonth(e.target.value)}
          style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, padding: '8px 12px', color: '#e2e8f0' }} />
      </div>

      {/* Role Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        {tabs.map(t => (
          <button key={t.key} onClick={() => setAudience(t.key)}
            style={{
              padding: '12px 24px', borderRadius: 8, border: 'none', cursor: 'pointer',
              fontSize: 14, fontWeight: 600,
              background: audience === t.key ? '#3b82f6' : '#1e293b',
              color: audience === t.key ? '#fff' : '#94a3b8',
            }}>
            {t.label}<br /><small style={{ fontWeight: 400 }}>{t.desc}</small>
          </button>
        ))}
      </div>

      {loading && <p>加载中...</p>}
      {!loading && data && (
        <>
          {/* Hero Card */}
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24,
          }}>
            <div style={cardStyle}>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#3b82f6' }}>{data.hero_number}</div>
              <div style={{ fontSize: 13, color: '#94a3b8' }}>{data.hero_label}</div>
            </div>
            {data.total_runs !== undefined && (
              <div style={cardStyle}>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#22c55e' }}>{data.total_runs.toLocaleString()}</div>
                <div style={{ fontSize: 13, color: '#94a3b8' }}>本月执行</div>
              </div>
            )}
          </div>

          {/* Detail Rows */}
          {data.detail_rows && (
            <div style={cardStyle}>
              <h3 style={{ margin: '0 0 12px 0', fontSize: 16 }}>详细数据</h3>
              {data.detail_rows.map((r, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #1e293b' }}>
                  <span style={{ color: '#94a3b8' }}>{r.label}</span>
                  <span style={{ fontWeight: 600 }}>{r.value}</span>
                </div>
              ))}
            </div>
          )}

          {/* Breakdown */}
          {data.breakdown && (
            <div style={{ ...cardStyle, marginTop: 16 }}>
              <h3 style={{ margin: '0 0 12px 0', fontSize: 16 }}>价值构成</h3>
              {data.breakdown.map((b, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}>
                  <span>{b.label}</span>
                  <span style={{ fontWeight: 600 }}>{b.value}</span>
                </div>
              ))}
            </div>
          )}

          {/* Goal Summary */}
          {data.goal_summary && data.goal_summary.length > 0 && (
            <div style={{ ...cardStyle, marginTop: 16 }}>
              <h3 style={{ margin: '0 0 12px 0', fontSize: 16 }}>业务目标</h3>
              {data.goal_summary.map((g, i) => (
                <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid #1e293b' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span>{g.description}</span>
                    <span style={{ color: g.achieved ? '#22c55e' : g.progress_pct >= 0.8 ? '#eab308' : '#ef4444' }}>
                      {g.achieved ? '✅' : g.progress_pct >= 0.8 ? '⚠️' : '🔴'} {(g.progress_pct * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div style={{ background: '#1e293b', borderRadius: 4, height: 8, width: '100%' }}>
                    <div style={{
                      background: g.achieved ? '#22c55e' : g.progress_pct >= 0.8 ? '#eab308' : '#ef4444',
                      height: 8, borderRadius: 4, width: `${Math.min(g.progress_pct * 100, 100)}%`,
                    }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
};

const cardStyle: React.CSSProperties = {
  background: '#1e293b', border: '1px solid #334155', borderRadius: 12,
  padding: 20,
};

export default ValueDashboard;
