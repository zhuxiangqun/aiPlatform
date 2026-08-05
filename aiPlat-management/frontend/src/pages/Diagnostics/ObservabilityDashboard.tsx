import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, BarChart3, Brain, Clock, AlertTriangle, Activity, Zap, Database, BellRing, ExternalLink, Settings, Save } from 'lucide-react';
import { diagnosticsApi } from '../../services';

interface LLMStats {
  total_calls: number;
  success_rate: number;
  avg_latency_ms: number;
  max_latency_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost: number;
}

interface KindStats {
  count: number;
  avg_latency_ms: number;
}

interface ThroughputPoint {
  ts: number;
  count: number;
}

interface ErrorTimelinePoint {
  ts: number;
  total: number;
  errors: number;
  error_rate: number;
}

interface ModelUsage {
  model: string;
  count: number;
  input_tokens: number;
  output_tokens: number;
}

interface TopError {
  error: string;
  count: number;
}

interface Stats {
  llm_stats: LLMStats;
  syscall_by_kind: Record<string, KindStats>;
  active_runs: number;
  throughput: ThroughputPoint[];
  error_timeline: ErrorTimelinePoint[];
  model_usage: ModelUsage[];
  top_errors: TopError[];
}

const KIND_ICONS: Record<string, string> = {
  sys_llm_generate: '🧠', sys_tool_call: '🔧', sys_skill_call: '⚡',
  sys_observe: '👁️', sys_reason: '💭', default: '📋',
};
const KIND_LABELS: Record<string, string> = {
  sys_llm_generate: 'LLM 调用', sys_tool_call: '工具调用', sys_skill_call: '技能调用',
  sys_observe: '观察', sys_reason: '推理', default: '未知',
};

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}
function formatMs(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}
function formatTs(ts: number): string {
  const d = new Date(ts * 1000);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

const ObservabilityDashboard: React.FC = () => {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [alertConfig, setAlertConfig] = useState<any[]>([]);
  const [alertOpen, setAlertOpen] = useState(false);
  const [alertSaving, setAlertSaving] = useState(false);

  const fetchAlerts = useCallback(async () => {
    try {
      const resp = await fetch('/api/core/diagnostics/observability/alerts');
      const data = await resp.json();
      setAlertConfig(data.alerts || []);
    } catch {}
  }, []);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);

  const toggleAlert = (idx: number) => {
    setAlertConfig(prev => prev.map((a, i) => i === idx ? { ...a, enabled: !a.enabled } : a));
  };

  const updateAlertValue = (idx: number, value: number) => {
    setAlertConfig(prev => prev.map((a, i) => i === idx ? { ...a, value, condition: `${a.condition.replace(/\d+/, String(value))}` } : a));
  };

  const saveAlerts = useCallback(async () => {
    setAlertSaving(true);
    try {
      await fetch('/api/core/diagnostics/observability/alerts', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alerts: alertConfig }),
      });
      alert('告警配置已保存');
      fetchStats(); // refresh stats to include new alert results
    } catch (e: any) {
      alert('保存失败: ' + (e?.message || ''));
    } finally {
      setAlertSaving(false);
    }
  }, [alertConfig]);

  const fetchStats = useCallback(async () => {
    try {
      const res = await (diagnosticsApi as any).getObservabilityStats();
      setStats(res as Stats);
    } catch (e: any) {
      setError(e?.message || 'Failed to load stats');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
    const timer = setInterval(fetchStats, 30_000);
    return () => clearInterval(timer);
  }, [fetchStats]);

  if (loading) return <div style={{ color: '#9ca3af', padding: 40, textAlign: 'center' }}>加载中...</div>;
  if (error) return <div style={{ color: '#ef4444', padding: 40, textAlign: 'center' }}>{error}</div>;
  if (!stats) return null;

  const { llm_stats: llm, syscall_by_kind: kinds, active_runs, throughput, error_timeline, model_usage, top_errors, active_alerts } = stats as any;

  const cardStyle: React.CSSProperties = {
    background: '#1f2937', borderRadius: 10, padding: '16px 20px',
    border: '1px solid #374151', display: 'flex', flexDirection: 'column', gap: 6,
  };
  const labelStyle: React.CSSProperties = { fontSize: 11, color: '#6b7280', display: 'flex', alignItems: 'center', gap: 4 };
  const valueStyle: React.CSSProperties = { fontSize: 24, fontWeight: 700, color: '#e5e7eb' };
  const subStyle: React.CSSProperties = { fontSize: 11, color: '#9ca3af' };

  const maxThroughput = Math.max(1, ...throughput.map((p: any) => p.count));
  const maxErrorTotal = Math.max(1, ...error_timeline.map((p: any) => p.total));

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1200, color: '#e5e7eb' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <BarChart3 size={24} color="#8b5cf6" />
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>可观测性仪表板</h1>
        <span style={{ fontSize: 11, color: '#6b7280', marginLeft: 8 }}>每 30s 自动刷新</span>
      </div>

      <p style={{ fontSize: 12, color: '#9ca3af', marginBottom: 20, lineHeight: 1.6 }}>
        <strong>LLM 调用运营数据</strong>——展示过去 24 小时内所有 LLM 请求的吞吐量、成功率、延迟、Token 消耗和模型分布。
        数据来源：<code>sys_llm_generate</code> 的每次调用记录。刚重启时数据为空，Pipeline 执行后会自然填充。
        下方 Syscall 分布、模型使用分布、错误 Top 列表分别按类型/模型/错误信息聚合展示。
      </p>

      <Link to="/diagnostics" className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 transition-colors mb-4">
        <ArrowLeft className="w-3 h-3" />返回诊断中心
      </Link>

      {/* Active alerts */}
      {active_alerts && active_alerts.length > 0 && (
        <div style={{
          display: 'flex', flexDirection: 'column', gap: 6,
          background: '#450a0a', borderRadius: 10, padding: '12px 16px',
          border: '1px solid #ef4444', marginBottom: 20,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <BellRing size={16} color="#ef4444" />
            <span style={{ fontSize: 13, fontWeight: 600, color: '#fca5a5' }}>活跃告警</span>
          </div>
          {active_alerts.map((a: any, i: number) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: 10, paddingLeft: 24,
              fontSize: 12, color: '#fca5a5',
            }}>
              <AlertTriangle size={12} color="#ef4444" />
              <span style={{ flex: 1 }}>{a.description}</span>
              <span style={{ fontWeight: 600 }}>{a.current}{a.unit}</span>
              <span style={{ color: '#9ca3af', fontSize: 11 }}>阈值: {a.threshold}{a.unit}</span>
            </div>
          ))}
        </div>
      )}

      {/* LLM overview cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12, marginBottom: 16 }}>
        <div style={cardStyle}>
          <div style={labelStyle}><Brain size={14} /> LLM 调用总数</div>
          <div style={valueStyle}>{llm.total_calls}</div>
          <div style={subStyle}>成功率 {llm.success_rate}%</div>
        </div>
        <div style={cardStyle}>
          <div style={labelStyle}><Zap size={14} /> 总 Token 消耗</div>
          <div style={valueStyle}>{formatTokens(llm.total_input_tokens + llm.total_output_tokens)}</div>
          <div style={subStyle}>输入 {formatTokens(llm.total_input_tokens)} / 输出 {formatTokens(llm.total_output_tokens)}</div>
        </div>
        <div style={cardStyle}>
          <div style={labelStyle}><Clock size={14} /> 平均延迟</div>
          <div style={valueStyle}>{formatMs(llm.avg_latency_ms)}</div>
          <div style={subStyle}>最大 {formatMs(llm.max_latency_ms)}</div>
        </div>
        <div style={cardStyle}>
          <div style={labelStyle}><Activity size={14} /> 活跃运行</div>
          <div style={{ ...valueStyle, color: active_runs > 0 ? '#3b82f6' : '#9ca3af' }}>{active_runs}</div>
          <div style={subStyle}>最近 1 小时</div>
        </div>
        <div style={cardStyle}>
          <div style={labelStyle}><Database size={14} /> 预估成本</div>
          <div style={valueStyle}>${llm.total_cost.toFixed(4)}</div>
          <div style={subStyle}>24h 累计</div>
        </div>
      </div>

      {/* Quick links */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
        <Link to="/diagnostics/syscalls" style={{
          fontSize: 11, color: '#8b5cf6', textDecoration: 'none',
          display: 'flex', alignItems: 'center', gap: 4,
          padding: '4px 10px', borderRadius: 6, background: 'rgba(139,92,246,0.1)',
          border: '1px solid rgba(139,92,246,0.2)',
        }}>
          <ExternalLink size={10} /> 查看所有 Syscall 事件
        </Link>
        <Link to="/diagnostics/traces" style={{
          fontSize: 11, color: '#3b82f6', textDecoration: 'none',
          display: 'flex', alignItems: 'center', gap: 4,
          padding: '4px 10px', borderRadius: 6, background: 'rgba(59,130,246,0.1)',
          border: '1px solid rgba(59,130,246,0.2)',
        }}>
          <ExternalLink size={10} /> 查看链路追踪
        </Link>
        <Link to="/diagnostics/run-comparison" style={{
          fontSize: 11, color: '#22c55e', textDecoration: 'none',
          display: 'flex', alignItems: 'center', gap: 4,
          padding: '4px 10px', borderRadius: 6, background: 'rgba(34,197,94,0.1)',
          border: '1px solid rgba(34,197,94,0.2)',
        }}>
          <ExternalLink size={10} /> Run 对比
        </Link>
        {top_errors.length > 0 && (
          <Link to="/diagnostics/ops" style={{
            fontSize: 11, color: '#ef4444', textDecoration: 'none',
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '4px 10px', borderRadius: 6, background: 'rgba(239,68,68,0.1)',
            border: '1px solid rgba(239,68,68,0.2)',
          }}>
            <AlertTriangle size={10} /> 查看 Ops / DLQ
          </Link>
        )}
      </div>

      {/* Throughput chart */}
      {throughput.length > 0 && (
        <div style={{ ...cardStyle, marginBottom: 16 }}>
          <div style={labelStyle}>事件吞吐量 (最近 1 小时, 5 分钟窗口)</div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 80, paddingTop: 8 }}>
            {throughput.map((p: any, i: number) => (
              <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 12 }}>
                <span style={{ fontSize: 9, color: '#6b7280', marginBottom: 2 }}>{p.count}</span>
                <div style={{
                  width: '100%', maxWidth: 24,
                  height: `${(p.count / maxThroughput) * 56}px`,
                  background: p.count > 0 ? '#8b5cf6' : '#374151',
                  borderRadius: '3px 3px 0 0',
                  minHeight: 2,
                  transition: 'height 0.3s',
                }} />
                <span style={{ fontSize: 8, color: '#6b7280', marginTop: 3, transform: 'rotate(-30deg)', whiteSpace: 'nowrap' }}>
                  {formatTs(p.ts)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Error timeline */}
      {error_timeline.length > 0 && (
        <div style={{ ...cardStyle, marginBottom: 16 }}>
          <div style={labelStyle}><AlertTriangle size={14} /> 错误率趋势 (最近 6 小时, 30 分钟窗口)</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingTop: 8 }}>
            {error_timeline.map((p: any, i: number) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 9, color: '#6b7280', width: 40 }}>{formatTs(p.ts)}</span>
                <div style={{ flex: 1, background: '#374151', borderRadius: 3, height: 16, position: 'relative', overflow: 'hidden' }}>
                  <div style={{
                    height: '100%', borderRadius: 3,
                    width: `${(p.total / maxErrorTotal) * 100}%`,
                    background: '#1f2937', position: 'absolute',
                  }} />
                  <div style={{
                    height: '100%', borderRadius: 3,
                    width: `${(p.errors / Math.max(1, p.total)) * (p.total / maxErrorTotal) * 100}%`,
                    background: '#ef4444', position: 'absolute',
                  }} />
                </div>
                <span style={{ fontSize: 9, color: p.error_rate > 20 ? '#ef4444' : '#9ca3af', width: 40, textAlign: 'right' }}>
                  {p.error_rate}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Syscall by kind + Model usage side by side */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        {/* Syscall by kind */}
        <div style={cardStyle}>
          <div style={{ ...labelStyle, marginBottom: 4 }}>Syscall 分布 (24h)</div>
          {Object.keys(kinds).length === 0 ? (
            <div style={{ fontSize: 12, color: '#6b7280' }}>暂无数据</div>
          ) : (
            Object.entries(kinds).map(([kind, k]: [string, any]) => (
              <div key={kind} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
                <span style={{ fontSize: 13 }}>{KIND_ICONS[kind] || KIND_ICONS.default}</span>
                <span style={{ fontSize: 12, color: '#e5e7eb', flex: 1 }}>{KIND_LABELS[kind] || kind}</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: '#8b5cf6' }}>{k.count}</span>
                <span style={{ fontSize: 10, color: '#6b7280', width: 50, textAlign: 'right' }}>{formatMs(k.avg_latency_ms)}</span>
              </div>
            ))
          )}
        </div>

        {/* Model usage */}
        <div style={cardStyle}>
          <div style={{ ...labelStyle, marginBottom: 4 }}>模型使用分布</div>
          {model_usage.length === 0 ? (
            <div style={{ fontSize: 12, color: '#6b7280' }}>暂无数据</div>
          ) : (
            model_usage.map((m: any, i: number) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
                <span style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: ['#8b5cf6', '#3b82f6', '#22c55e', '#f59e0b', '#ef4444'][i % 5],
                  flexShrink: 0,
                }} />
                <span style={{ fontSize: 12, color: '#e5e7eb', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {m.model}
                </span>
                <span style={{ fontSize: 11, fontWeight: 600, color: '#e5e7eb' }}>{m.count}</span>
                <span style={{ fontSize: 10, color: '#6b7280' }}>{formatTokens(m.input_tokens + m.output_tokens)} tokens</span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Top errors */}
      {top_errors.length > 0 && (
        <div style={cardStyle}>
          <div style={{ ...labelStyle, marginBottom: 4 }}><AlertTriangle size={14} /> Top 错误 (24h)</div>
          {top_errors.map((e: any, i: number) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: '#ef4444', width: 28 }}>{e.count}x</span>
              <span style={{ fontSize: 11, color: '#9ca3af', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {e.error}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Alert threshold configuration */}
      <div style={{ marginTop: 24 }}>
        <button onClick={() => setAlertOpen(!alertOpen)} style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: '#1f2937', border: '1px solid #374151', borderRadius: 6,
          color: alertOpen ? '#8b5cf6' : '#9ca3af', cursor: 'pointer', fontSize: 12, padding: '6px 12px',
        }}>
          <Settings size={14} /> 告警阈值配置 {alertOpen ? '▲' : '▼'}
        </button>
        {alertOpen && (
          <div style={{
            marginTop: 8, background: '#1f2937', borderRadius: 10, border: '1px solid #374151',
            padding: 16, display: 'flex', flexDirection: 'column', gap: 10,
          }}>
            <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>
              配置告警阈值，当指标超过阈值时在仪表板顶部显示红色告警。
            </div>
            {alertConfig.map((rule, idx) => (
              <div key={rule.id} style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
                background: rule.enabled ? 'rgba(139,92,246,0.08)' : '#111827',
                borderRadius: 6, border: `1px solid ${rule.enabled ? 'rgba(139,92,246,0.3)' : '#374151'}`,
              }}>
                <label style={{
                  display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', flex: 1,
                }}>
                  <input type="checkbox" checked={rule.enabled} onChange={() => toggleAlert(idx)}
                    style={{ accentColor: '#8b5cf6', cursor: 'pointer' }} />
                  <span style={{
                    fontSize: 12, color: rule.enabled ? '#e5e7eb' : '#6b7280',
                    textDecoration: rule.enabled ? 'none' : 'line-through',
                  }}>
                    {rule.description}
                  </span>
                </label>
                {rule.enabled && (
                  <>
                    <span style={{ fontSize: 11, color: '#9ca3af' }}>
                      {rule.condition.replace(/\d+/, '{value}')}
                    </span>
                    <input
                      type="number"
                      value={rule.value}
                      onChange={e => updateAlertValue(idx, Number(e.target.value))}
                      style={{
                        width: 60, fontSize: 11, textAlign: 'center',
                        background: '#111827', border: '1px solid #374151', borderRadius: 4,
                        padding: '2px 6px', color: '#e5e7eb',
                      }}
                    />
                    <span style={{ fontSize: 10, color: '#6b7280', width: 30 }}>{rule.unit}</span>
                  </>
                )}
              </div>
            ))}
            <button
              onClick={saveAlerts}
              style={{
                display: 'flex', alignItems: 'center', gap: 6, alignSelf: 'flex-end',
                background: '#8b5cf6', border: 'none', borderRadius: 6,
                color: '#fff', cursor: 'pointer', fontSize: 12, padding: '6px 16px',
                opacity: alertSaving ? 0.6 : 1,
              }}
              disabled={alertSaving}
            >
              <Save size={14} /> {alertSaving ? '保存中...' : '保存配置'}
            </button>
          </div>
        )}
      </div>

      {/* Refresh button */}
      <div style={{ marginTop: 24, textAlign: 'center' }}>
        <button onClick={fetchStats} style={{
          background: '#374151', border: '1px solid #4b5563', borderRadius: 6,
          color: '#9ca3af', cursor: 'pointer', fontSize: 12, padding: '6px 16px',
        }}>
          🔄 立即刷新
        </button>
      </div>
    </div>
  );
};

export default ObservabilityDashboard;
