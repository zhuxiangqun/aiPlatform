import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Fingerprint, ShieldCheck, GitCompare, TrendingUp, AlertTriangle, CheckCircle, X } from 'lucide-react';
import { modelAuditApi, ModelFingerprintData, AuditReportData, ComparisonData } from '../../services/modelAuditApi';

const ModelAuditPanel: React.FC = () => {
  const [modelName, setModelName] = useState('');
  const [compareA, setCompareA] = useState('');
  const [compareB, setCompareB] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fingerprint, setFingerprint] = useState<ModelFingerprintData | null>(null);
  const [report, setReport] = useState<AuditReportData | null>(null);
  const [comparison, setComparison] = useState<ComparisonData | null>(null);
  const [mode, setMode] = useState<'probe' | 'report' | 'compare'>('probe');

  const runProbe = async () => {
    if (!modelName) return;
    setLoading(true);
    setError(null);
    setFingerprint(null);
    try {
      const fp = await modelAuditApi.probe(modelName);
      setFingerprint(fp);
    } catch (e: any) {
      setError(e?.message || 'Probe failed');
    } finally {
      setLoading(false);
    }
  };

  const runReport = async () => {
    if (!modelName) return;
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const r = await modelAuditApi.report(modelName);
      setReport(r);
    } catch (e: any) {
      setError(e?.message || 'Report generation failed');
    } finally {
      setLoading(false);
    }
  };

  const runCompare = async () => {
    if (!compareA || !compareB) return;
    setLoading(true);
    setError(null);
    setComparison(null);
    try {
      const c = await modelAuditApi.compare(compareA, compareB);
      setComparison(c);
    } catch (e: any) {
      setError(e?.message || 'Comparison failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '24px', maxWidth: 1100, margin: '0 auto', color: '#e5e7eb' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <Fingerprint size={24} color="#8b5cf6" />
        <h1 style={{ fontSize: 24, fontWeight: 600, color: '#e5e7eb', margin: 0 }}>Model Audit</h1>
      </div>
      <Link to="/diagnostics" style={{ color: '#9ca3af', fontSize: 13, marginBottom: 24, display: 'inline-flex', alignItems: 'center', gap: 4, textDecoration: 'none' }}>
        <ArrowLeft size={13} />返回诊断中心
      </Link>

      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        {(['probe', 'report', 'compare'] as const).map(m => (
          <button
            key={m}
            onClick={() => { setMode(m); setError(null); }}
            style={{
              padding: '6px 16px',
              borderRadius: 6,
              border: `1px solid ${mode === m ? '#8b5cf6' : '#374151'}`,
              background: mode === m ? 'rgba(139,92,246,0.15)' : 'transparent',
              color: mode === m ? '#a78bfa' : '#9ca3af',
              fontSize: 13,
              cursor: 'pointer',
            }}
          >
            {m === 'probe' ? 'Fingerprint' : m === 'report' ? 'Audit Report' : 'Model Compare'}
          </button>
        ))}
      </div>

      {error && (
        <div style={{ padding: 12, borderRadius: 8, background: 'rgba(239,68,68,0.1)', border: '1px solid #374151', color: '#f87171', fontSize: 13, marginBottom: 16 }}>
          {error}
          <button onClick={() => setError(null)} style={{ marginLeft: 12, background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer' }}><X size={14} /></button>
        </div>
      )}

      {mode === 'probe' && (
        <div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <input
              value={modelName}
              onChange={e => setModelName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && runProbe()}
              placeholder="Model name (e.g. qwen2.5-coder:7b)"
              style={{ flex: 1, padding: '8px 12px', borderRadius: 6, background: '#1f2937', border: '1px solid #374151', color: '#e5e7eb', fontSize: 13 }}
            />
            <button
              onClick={runProbe}
              disabled={loading || !modelName}
              style={{ padding: '8px 20px', borderRadius: 6, background: '#8b5cf6', color: '#fff', border: 'none', fontSize: 13, cursor: 'pointer', opacity: loading ? 0.6 : 1 }}
            >
              {loading ? 'Running...' : 'Probe'}
            </button>
          </div>
          {fingerprint && (
            <div style={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, padding: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                <h3 style={{ margin: 0, fontSize: 16, color: '#f3f4f6' }}>{fingerprint.model_name}</h3>
                <span style={{ color: fingerprint.confidence > 0.8 ? '#34d399' : '#fbbf24', fontSize: 12 }}>
                  Confidence: {(fingerprint.confidence * 100).toFixed(0)}%
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 16 }}>
                {[
                  { label: 'Avg Latency', value: `${fingerprint.avg_latency_ms.toFixed(0)}ms` },
                  { label: 'Avg Tokens', value: fingerprint.avg_token_count.toFixed(0) },
                  { label: 'Refusal Rate', value: `${(fingerprint.refusal_rate * 100).toFixed(1)}%` },
                  { label: 'Format Compliance', value: `${(fingerprint.format_compliance * 100).toFixed(0)}%` },
                ].map(m => (
                  <div key={m.label} style={{ textAlign: 'center', padding: 8, background: '#111827', borderRadius: 6 }}>
                    <div style={{ fontSize: 11, color: '#9ca3af' }}>{m.label}</div>
                    <div style={{ fontSize: 18, fontWeight: 600, color: '#e5e7eb', marginTop: 4 }}>{m.value}</div>
                  </div>
                ))}
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #374151' }}>
                    <th style={{ textAlign: 'left', padding: '6px 8px', color: '#9ca3af', fontWeight: 500 }}>Probe</th>
                    <th style={{ textAlign: 'left', padding: '6px 8px', color: '#9ca3af', fontWeight: 500 }}>Dimension</th>
                    <th style={{ textAlign: 'right', padding: '6px 8px', color: '#9ca3af', fontWeight: 500 }}>Latency</th>
                    <th style={{ textAlign: 'right', padding: '6px 8px', color: '#9ca3af', fontWeight: 500 }}>Tokens</th>
                    <th style={{ textAlign: 'center', padding: '6px 8px', color: '#9ca3af', fontWeight: 500 }}>Hash</th>
                  </tr>
                </thead>
                <tbody>
                  {fingerprint.probes.map(p => (
                    <tr key={p.probe_id} style={{ borderBottom: '1px solid #1f2937' }}>
                      <td style={{ padding: '6px 8px', color: '#d1d5db' }}>{p.probe_id}</td>
                      <td style={{ padding: '6px 8px', color: '#9ca3af' }}>{p.dimension}</td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', color: '#e5e7eb' }}>
                        {p.error ? <span style={{ color: '#f87171' }}>err</span> : `${p.latency_ms.toFixed(0)}ms`}
                      </td>
                      <td style={{ padding: '6px 8px', textAlign: 'right', color: '#e5e7eb' }}>{p.token_count || '-'}</td>
                      <td style={{ padding: '6px 8px', textAlign: 'center', color: '#6b7280', fontFamily: 'monospace', fontSize: 11 }}>
                        {p.response_hash ? p.response_hash.substring(0, 8) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {mode === 'report' && (
        <div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <input
              value={modelName}
              onChange={e => setModelName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && runReport()}
              placeholder="Model name"
              style={{ flex: 1, padding: '8px 12px', borderRadius: 6, background: '#1f2937', border: '1px solid #374151', color: '#e5e7eb', fontSize: 13 }}
            />
            <button onClick={runReport} disabled={loading || !modelName} style={{ padding: '8px 20px', borderRadius: 6, background: '#059669', color: '#fff', border: 'none', fontSize: 13, cursor: 'pointer', opacity: loading ? 0.6 : 1 }}>
              {loading ? 'Analyzing...' : 'Generate Report'}
            </button>
          </div>
          {report && (
            <div style={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, padding: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <ShieldCheck size={20} color="#34d399" />
                <h3 style={{ margin: 0, fontSize: 16, color: '#f3f4f6' }}>{report.identity.model_name}</h3>
                <span style={{ background: 'rgba(52,211,153,0.15)', color: '#34d399', padding: '2px 8px', borderRadius: 4, fontSize: 11, marginLeft: 8 }}>
                  {(report.identity.confidence * 100).toFixed(0)}% confidence
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                <div style={{ padding: 12, background: '#111827', borderRadius: 6 }}>
                  <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 4 }}>Detected Family</div>
                  <div style={{ fontSize: 15, fontWeight: 600, color: '#e5e7eb' }}>{report.identity.detected_family}</div>
                  {report.identity.match_reasons.length > 0 && (
                    <div style={{ marginTop: 6, fontSize: 11, color: '#6b7280' }}>
                      {report.identity.match_reasons.join(', ')}
                    </div>
                  )}
                </div>
                <div style={{ padding: 12, background: '#111827', borderRadius: 6 }}>
                  <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 4 }}>Estimated Size</div>
                  <div style={{ fontSize: 15, fontWeight: 600, color: '#e5e7eb' }}>{report.identity.estimated_size}</div>
                  <div style={{ marginTop: 6, fontSize: 11, color: '#6b7280', fontFamily: 'monospace' }}>{report.identity.fingerprint_hash?.substring(0, 16)}</div>
                </div>
              </div>

              {report.recommendations.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 6 }}>Recommendations</div>
                  {report.recommendations.map((r, i) => (
                    <div key={i} style={{ padding: '6px 10px', background: 'rgba(16,185,129,0.08)', borderLeft: '2px solid #34d399', marginBottom: 4, borderRadius: 4, fontSize: 12, color: '#d1d5db' }}>
                      {r}
                    </div>
                  ))}
                </div>
              )}

              {report.risk_flags.length > 0 && (
                <div>
                  <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 6 }}>
                    <AlertTriangle size={13} style={{ display: 'inline', marginRight: 4 }} />
                    Risk Flags
                  </div>
                  {report.risk_flags.map((f, i) => (
                    <div key={i} style={{ padding: '6px 10px', background: 'rgba(245,158,11,0.08)', borderLeft: '2px solid #f59e0b', marginBottom: 4, borderRadius: 4, fontSize: 12, color: '#fbbf24' }}>
                      {f}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {mode === 'compare' && (
        <div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center' }}>
            <input value={compareA} onChange={e => setCompareA(e.target.value)} placeholder="Model A" style={{ flex: 1, padding: '8px 12px', borderRadius: 6, background: '#1f2937', border: '1px solid #374151', color: '#e5e7eb', fontSize: 13 }} />
            <GitCompare size={16} color="#6b7280" />
            <input value={compareB} onChange={e => setCompareB(e.target.value)} placeholder="Model B" style={{ flex: 1, padding: '8px 12px', borderRadius: 6, background: '#1f2937', border: '1px solid #374151', color: '#e5e7eb', fontSize: 13 }} />
            <button onClick={runCompare} disabled={loading || !compareA || !compareB} style={{ padding: '8px 20px', borderRadius: 6, background: '#7c3aed', color: '#fff', border: 'none', fontSize: 13, cursor: 'pointer', opacity: loading ? 0.6 : 1 }}>
              {loading ? 'Comparing...' : 'Compare'}
            </button>
          </div>
          {comparison && (
            <div style={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, padding: 20 }}>
              <div style={{ textAlign: 'center', marginBottom: 16 }}>
                <div style={{ fontSize: 36, fontWeight: 700, color: comparison.similarity > 0.8 ? '#34d399' : comparison.similarity > 0.5 ? '#f59e0b' : '#6b7280' }}>
                  {(comparison.similarity * 100).toFixed(1)}%
                </div>
                <div style={{ fontSize: 13, color: '#9ca3af', marginTop: 4 }}>Similarity</div>
                <div style={{ fontSize: 12, color: '#d1d5db', marginTop: 8, padding: '4px 12px', background: 'rgba(139,92,246,0.1)', borderRadius: 4, display: 'inline-block' }}>
                  {comparison.likely_relationship.replace(/_/g, ' ')}
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8, marginBottom: 12 }}>
                {Object.entries(comparison.dimension_scores).map(([k, v]) => (
                  <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 12px', background: '#111827', borderRadius: 6 }}>
                    <span style={{ fontSize: 12, color: '#9ca3af' }}>{k.replace(/_/g, ' ')}</span>
                    <span style={{ fontSize: 13, fontWeight: 600, color: v > 0.7 ? '#34d399' : v > 0.4 ? '#f59e0b' : '#6b7280' }}>
                      {(v * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>

              {comparison.details.length > 0 && (
                <div>
                  {comparison.details.map((d, i) => (
                    <div key={i} style={{ padding: '6px 10px', fontSize: 12, color: '#d1d5db', borderLeft: '2px solid #8b5cf6', marginBottom: 4, borderRadius: 4 }}>
                      {d}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ModelAuditPanel;
