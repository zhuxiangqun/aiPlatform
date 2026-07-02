import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Shield, AlertTriangle, Heart, TrendingUp, TrendingDown, Minus, Activity, BarChart3 } from 'lucide-react';
import { safetyApi, EmotionStateData, CrisisCheckResult } from '../../services/safetyApi';

const TONE_COLORS: Record<string, string> = {
  neutral: '#9ca3af',
  positive: '#34d399',
  anxious: '#f59e0b',
  sad: '#6b7280',
  angry: '#ef4444',
  hopeful: '#60a5fa',
  fearful: '#c084fc',
  mixed: '#d1d5db',
};

const SafetyPanel: React.FC = () => {
  const [mode, setMode] = useState<'check' | 'flagged'>('check');
  const [testText, setTestText] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [crisisResult, setCrisisResult] = useState<CrisisCheckResult | null>(null);
  const [flagged, setFlagged] = useState<EmotionStateData[]>([]);
  const [flaggedCount, setFlaggedCount] = useState(0);

  useEffect(() => {
    loadFlagged();
  }, []);

  const loadFlagged = async () => {
    try {
      const res = await safetyApi.getFlaggedSessions();
      setFlagged(res.sessions || []);
      setFlaggedCount(res.count || 0);
    } catch {
      // quiet
    }
  };

  const runCrisisCheck = async () => {
    if (!testText) return;
    setLoading(true);
    setError(null);
    try {
      const res = await safetyApi.crisisCheck(testText, sessionId);
      setCrisisResult(res);
    } catch (e: any) {
      setError(e?.message || 'Check failed');
    } finally {
      setLoading(false);
    }
  };

  const getSeverityColor = (sev: string) => {
    switch (sev) {
      case 'critical': return '#ef4444';
      case 'high': return '#f59e0b';
      case 'medium': return '#fbbf24';
      case 'low': return '#60a5fa';
      default: return '#9ca3af';
    }
  };

  const getTrendIcon = (trend: string) => {
    if (trend === 'improving') return <TrendingUp size={14} color="#34d399" />;
    if (trend === 'declining') return <TrendingDown size={14} color="#ef4444" />;
    return <Minus size={14} color="#9ca3af" />;
  };

  const getRiskBadgeColor = (risk: string) => {
    if (risk === 'high') return { bg: 'rgba(239,68,68,0.15)', color: '#f87171' };
    if (risk === 'medium') return { bg: 'rgba(245,158,11,0.15)', color: '#fbbf24' };
    return { bg: 'rgba(52,211,153,0.15)', color: '#34d399' };
  };

  return (
    <div style={{ padding: '24px', maxWidth: 1100, margin: '0 auto', color: '#e5e7eb' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <Shield size={24} color="#34d399" />
        <h1 style={{ fontSize: 24, fontWeight: 600, color: '#e5e7eb', margin: 0 }}>Safety Monitor</h1>
      </div>
      <Link to="/diagnostics" style={{ color: '#9ca3af', fontSize: 13, marginBottom: 24, display: 'inline-flex', alignItems: 'center', gap: 4, textDecoration: 'none' }}>
        <ArrowLeft size={13} />返回诊断中心
      </Link>

      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        {(['check', 'flagged'] as const).map(m => (
          <button
            key={m}
            onClick={() => setMode(m)}
            style={{
              padding: '6px 16px',
              borderRadius: 6,
              border: `1px solid ${mode === m ? '#34d399' : '#374151'}`,
              background: mode === m ? 'rgba(52,211,153,0.15)' : 'transparent',
              color: mode === m ? '#6ee7b7' : '#9ca3af',
              fontSize: 13,
              cursor: 'pointer',
            }}
          >
            {m === 'check' ? 'Crisis Check' : `Flagged Sessions (${flaggedCount})`}
          </button>
        ))}
      </div>

      {error && (
        <div style={{ padding: 12, borderRadius: 8, background: 'rgba(239,68,68,0.1)', border: '1px solid #374151', color: '#f87171', fontSize: 13, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {mode === 'check' && (
        <div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
            <textarea
              value={testText}
              onChange={e => setTestText(e.target.value)}
              placeholder="Enter text to check for crisis signals..."
              rows={4}
              style={{ padding: '10px 12px', borderRadius: 6, background: '#1f2937', border: '1px solid #374151', color: '#e5e7eb', fontSize: 13, resize: 'vertical' }}
            />
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                value={sessionId}
                onChange={e => setSessionId(e.target.value)}
                placeholder="Session ID (optional)"
                style={{ flex: 1, padding: '8px 12px', borderRadius: 6, background: '#1f2937', border: '1px solid #374151', color: '#e5e7eb', fontSize: 13 }}
              />
              <button
                onClick={runCrisisCheck}
                disabled={loading || !testText}
                style={{ padding: '8px 20px', borderRadius: 6, background: '#059669', color: '#fff', border: 'none', fontSize: 13, cursor: 'pointer', opacity: loading ? 0.6 : 1 }}
              >
                {loading ? 'Checking...' : 'Check'}
              </button>
            </div>
          </div>

          {crisisResult && (
            <div style={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, padding: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                {crisisResult.is_crisis ? (
                  <AlertTriangle size={20} color={getSeverityColor(crisisResult.severity)} />
                ) : (
                  <Shield size={20} color="#34d399" />
                )}
                <h3 style={{ margin: 0, fontSize: 16, color: '#f3f4f6' }}>
                  {crisisResult.is_crisis ? 'Crisis Detected' : 'No Crisis'}
                </h3>
                <span style={{
                  padding: '2px 10px',
                  borderRadius: 4,
                  fontSize: 12,
                  fontWeight: 600,
                  background: `${getSeverityColor(crisisResult.severity)}22`,
                  color: getSeverityColor(crisisResult.severity),
                }}>
                  {crisisResult.severity.toUpperCase()}
                </span>
                <span style={{ fontSize: 12, color: '#9ca3af' }}>{crisisResult.signal_count} signals</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 16 }}>
                <div style={{ padding: 10, background: '#111827', borderRadius: 6 }}>
                  <div style={{ fontSize: 11, color: '#9ca3af' }}>Severity</div>
                  <div style={{ fontSize: 15, fontWeight: 600, color: getSeverityColor(crisisResult.severity) }}>{crisisResult.severity}</div>
                </div>
                <div style={{ padding: 10, background: '#111827', borderRadius: 6 }}>
                  <div style={{ fontSize: 11, color: '#9ca3af' }}>Escalation</div>
                  <div style={{ fontSize: 15, fontWeight: 600, color: crisisResult.escalation_required ? '#ef4444' : '#34d399' }}>
                    {crisisResult.escalation_required ? 'Required' : 'Not Required'}
                  </div>
                </div>
                <div style={{ padding: 10, background: '#111827', borderRadius: 6 }}>
                  <div style={{ fontSize: 11, color: '#9ca3af' }}>Signals</div>
                  <div style={{ fontSize: 15, fontWeight: 600, color: '#e5e7eb' }}>{crisisResult.signal_count}</div>
                </div>
              </div>

              {crisisResult.recommended_action && (
                <div style={{ padding: '10px 14px', background: 'rgba(52,211,153,0.08)', borderLeft: '3px solid #34d399', borderRadius: 4, marginBottom: 12, fontSize: 12, color: '#d1d5db' }}>
                  {crisisResult.recommended_action}
                </div>
              )}

              {crisisResult.signals.length > 0 && (
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #374151' }}>
                      <th style={{ textAlign: 'left', padding: '6px 8px', color: '#9ca3af', fontWeight: 500 }}>Rule</th>
                      <th style={{ textAlign: 'left', padding: '6px 8px', color: '#9ca3af', fontWeight: 500 }}>Severity</th>
                      <th style={{ textAlign: 'left', padding: '6px 8px', color: '#9ca3af', fontWeight: 500 }}>Match</th>
                    </tr>
                  </thead>
                  <tbody>
                    {crisisResult.signals.map((s, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid #1f2937' }}>
                        <td style={{ padding: '6px 8px', color: '#d1d5db', fontFamily: 'monospace', fontSize: 11 }}>{s.rule_id}</td>
                        <td style={{ padding: '6px 8px' }}>
                          <span style={{ color: getSeverityColor(s.severity), fontSize: 11, fontWeight: 600 }}>{s.severity}</span>
                        </td>
                        <td style={{ padding: '6px 8px', color: '#9ca3af', fontSize: 11 }}>{s.pattern_matched}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      )}

      {mode === 'flagged' && (
        <div>
          {flagged.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40, color: '#6b7280' }}>
              <Shield size={32} color="#374151" style={{ marginBottom: 12 }} />
              <div style={{ fontSize: 14 }}>No flagged sessions</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {flagged.map((s, i) => {
                const risk = getRiskBadgeColor(s.dependency_risk);
                return (
                  <div key={i} style={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, padding: 16 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Heart size={16} color={TONE_COLORS[s.current_tone] || '#9ca3af'} />
                        <span style={{ fontSize: 14, fontWeight: 600, color: '#e5e7eb' }}>{s.session_id}</span>
                        {getTrendIcon(s.trend)}
                      </div>
                      <span style={{
                        padding: '2px 10px',
                        borderRadius: 4,
                        fontSize: 11,
                        fontWeight: 600,
                        background: risk.bg,
                        color: risk.color,
                      }}>
                        {s.dependency_risk.toUpperCase()} RISK
                      </span>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 8 }}>
                      <div style={{ textAlign: 'center', padding: 6, background: '#111827', borderRadius: 4 }}>
                        <div style={{ fontSize: 11, color: '#9ca3af' }}>Tone</div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: TONE_COLORS[s.current_tone] || '#e5e7eb' }}>{s.current_tone}</div>
                      </div>
                      <div style={{ textAlign: 'center', padding: 6, background: '#111827', borderRadius: 4 }}>
                        <div style={{ fontSize: 11, color: '#9ca3af' }}>Trend</div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: s.trend === 'declining' ? '#ef4444' : s.trend === 'improving' ? '#34d399' : '#9ca3af' }}>{s.trend}</div>
                      </div>
                      <div style={{ textAlign: 'center', padding: 6, background: '#111827', borderRadius: 4 }}>
                        <div style={{ fontSize: 11, color: '#9ca3af' }}>Sessions/24h</div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: '#e5e7eb' }}>{s.sessions_24h}</div>
                      </div>
                      <div style={{ textAlign: 'center', padding: 6, background: '#111827', borderRadius: 4 }}>
                        <div style={{ fontSize: 11, color: '#9ca3af' }}>Avg Duration</div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: '#e5e7eb' }}>{s.avg_session_length_min}m</div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          <div style={{ textAlign: 'center', marginTop: 12 }}>
            <button
              onClick={loadFlagged}
              style={{ padding: '6px 14px', borderRadius: 6, background: '#374151', color: '#d1d5db', border: 'none', fontSize: 12, cursor: 'pointer' }}
            >
              Refresh
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default SafetyPanel;
