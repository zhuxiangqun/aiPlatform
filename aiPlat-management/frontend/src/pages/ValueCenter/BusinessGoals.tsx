/**
 * BusinessGoals — Link business targets to specific agents with auto-tracking.
 *
 * Shows: goal → agent mapping, progress timeline, prediction from GoalAwareRouter
 */
import React, { useState, useEffect } from 'react';

interface Goal {
  goal_id: string; description: string; progress_pct: number; achieved: boolean;
  baseline_value: number; target_value: number; current_value: number;
}
interface StrategyStatus { params: Record<string, any>; context: string; goals_count: number; }
interface Prediction { status: string; projected_value: number; days_to_target: number; recommendation: string; }

const BusinessGoals: React.FC = () => {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [strategy, setStrategy] = useState<StrategyStatus | null>(null);
  const [predictions, setPredictions] = useState<Record<string, Prediction>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch('/api/core/value/all/goals').then(r => r.json()),
      fetch('/api/core/value/all/strategy').then(r => r.json()),
    ]).then(([g, s]) => {
      setGoals(g);
      setStrategy(s);
      // Compute predictions
      const preds: Record<string, Prediction> = {};
      g.forEach((goal: Goal) => {
        const span = goal.target_value - goal.baseline_value;
        const dailyRate = span > 0.001 ? (span * goal.progress_pct / 30) : 0.001;
        const remaining = span * (1 - goal.progress_pct);
        const daysLeft = dailyRate > 0 ? Math.ceil(remaining / dailyRate) : 999;
        const progressRatio = goal.progress_pct / 0.5;
        preds[goal.goal_id] = {
          status: progressRatio >= 1.1 ? 'on_track' : progressRatio >= 0.9 ? 'at_risk' : 'behind',
          projected_value: goal.current_value + dailyRate * 45,
          days_to_target: daysLeft,
          recommendation: progressRatio >= 1.1 ? '' : progressRatio >= 0.9 ? '建议加速' : '需要干预',
        };
      });
      setPredictions(preds);
      setLoading(false);
    });
  }, []);

  if (loading) return <div style={pageStyle}><p style={{ color: '#94a3b8' }}>加载中...</p></div>;

  const statusColor = (s: string) => s === 'on_track' ? '#22c55e' : s === 'at_risk' ? '#eab308' : '#ef4444';

  return (
    <div style={pageStyle}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Business Goals</h1>

      {/* Strategy Status */}
      {strategy && strategy.context && (
        <div style={{ ...cardStyle, marginBottom: 16, borderLeft: '4px solid #eab308' }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>当前策略</div>
          <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, color: '#e2e8f0' }}>{strategy.context}</div>
        </div>
      )}

      {/* Goal Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 16 }}>
        {goals.map(g => {
          const pred = predictions[g.goal_id];
          return (
            <div key={g.goal_id} style={cardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ fontWeight: 600, fontSize: 15 }}>{g.description}</span>
                <span style={{ fontSize: 12, color: statusColor(pred?.status || '') }}>
                  {pred?.status === 'on_track' ? '✅ 按计划' : pred?.status === 'at_risk' ? '⚠️ 有风险' : '🔴 落后'}
                </span>
              </div>

              {/* Progress bar */}
              <div style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#94a3b8', marginBottom: 4 }}>
                  <span>{g.baseline_value} (基线)</span>
                  <span>{(g.progress_pct * 100).toFixed(0)}%</span>
                  <span>{g.target_value} (目标)</span>
                </div>
                <div style={{ background: '#0f172a', borderRadius: 4, height: 10 }}>
                  <div style={{ background: statusColor(pred?.status || 'behind'), height: 10, borderRadius: 4, width: `${Math.min(g.progress_pct * 100, 100)}%` }} />
                </div>
              </div>

              {/* Prediction */}
              {pred && (
                <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 8, padding: 8, background: '#0f172a', borderRadius: 6 }}>
                  <div>预估达成值: {pred.projected_value.toFixed(1)}</div>
                  <div>预计天数: {pred.days_to_target}天</div>
                  {pred.recommendation && <div style={{ color: statusColor(pred.status), fontWeight: 600, marginTop: 4 }}>{pred.recommendation}</div>}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const pageStyle: React.CSSProperties = { padding: 24, background: '#0f172a', minHeight: '100vh', color: '#e2e8f0' };
const cardStyle: React.CSSProperties = { background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: 20 };

export default BusinessGoals;
