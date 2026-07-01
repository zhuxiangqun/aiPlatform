import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, GitBranch, TrendingUp, AlertTriangle, Edit3 } from 'lucide-react';

const SEVERITY_COLORS: Record<string, string> = {
  low: '#22c55e', medium: '#f59e0b', high: '#ef4444', critical: '#dc2626',
};
const STATUS_COLORS: Record<string, string> = {
  draft: '#94a3b8', pending: '#3b82f6', executing: '#f59e0b', review: '#a855f7',
  revising: '#ec4899', stable: '#22c55e', archived: '#64748b',
};
const STATUS_LABELS: Record<string, string> = {
  draft: '草稿', pending: '待执行', executing: '执行中', review: '待审查',
  revising: '修订中', stable: '稳定', archived: '已归档',
};

type Tab = 'lifecycle' | 'trace' | 'radar';

const SpecDetailPage: React.FC = () => {
  const { specId } = useParams<{ specId: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialTab = (searchParams.get('tab') as Tab) || 'lifecycle';
  const [tab, setTab] = useState<Tab>(['lifecycle','trace','radar'].includes(initialTab) ? initialTab : 'lifecycle');
  const [history, setHistory] = useState<any[]>([]);
  const [trace, setTrace] = useState<any>(null);
  const [radar, setRadar] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!specId) return;
    Promise.all([
      fetch(`/api/core/workbench/spec/${specId}/history`).then(r => r.json()),
      fetch(`/api/core/workbench/spec/${specId}/trace`).then(r => r.json()),
      fetch(`/api/core/workbench/spec/${specId}/radar`).then(r => r.json()),
    ])
      .then(([h, t, r]) => { setHistory(h?.versions || []); setTrace(t); setRadar(r); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [specId]);

  if (loading) return <div style={{ padding: 24, color: '#94a3b8' }}>加载中...</div>;
  if (!specId) return <div style={{ padding: 24, color: '#ef4444' }}>缺少 specId</div>;

  const latestVersion = history[history.length - 1];
  const [reviseOpen, setReviseOpen] = useState(false);
  const [reviseContent, setReviseContent] = useState('');
  const [reviseDetail, setReviseDetail] = useState('');
  const [reviseStages, setReviseStages] = useState('');
  const [revising, setRevising] = useState(false);
  const [reviseResult, setReviseResult] = useState<any>(null);
  const [acceptanceCriteria, setAcceptanceCriteria] = useState('');
  const [deliverable, setDeliverable] = useState('');

  const openRevise = () => {
    const content = latestVersion?.content || {};
    const { agent_md, tools, evals, stage_configs, acceptance_criteria, deliverable, ...rest } = content;
    setReviseContent(JSON.stringify({ agent_md, tools, evals, stage_configs, ...rest }, null, 2));
    setReviseDetail('');
    setReviseStages('');
    setAcceptanceCriteria(acceptance_criteria || '');
    setDeliverable(deliverable || '');
    setReviseResult(null);
    setReviseOpen(true);
  };

  const submitRevise = async () => {
    if (!reviseContent.trim()) return;
    setRevising(true);
    try {
      let content: any = {};
      try { content = JSON.parse(reviseContent); } catch { content = { agent_md: reviseContent }; }
      // Merge Matter fields (acceptance criteria + deliverable) into content
      content.acceptance_criteria = acceptanceCriteria;
      content.deliverable = deliverable;
      const body: any = {
        content, re_execute: true,
        trigger_detail: reviseDetail || 'Manual revision from SpecDetail',
        created_by: 'developer',
      };
      if (reviseStages.trim()) {
        body.affected_stages = reviseStages.split(',').map((s: string) => parseInt(s.trim())).filter((n: number) => !isNaN(n));
      }
      const res = await fetch(`/api/core/workbench/spec/${specId}/revise`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      setReviseResult(data);
      if (data.version) {
        // Refresh history
        const hRes = await fetch(`/api/core/workbench/spec/${specId}/history`);
        const h = await hRes.json();
        setHistory(h?.versions || []);
      }
    } catch (e: any) {
      setReviseResult({ error: e.message });
    }
    setRevising(false);
  };

  const cardBase: React.CSSProperties = {
    background: '#1e293b', borderRadius: 10, padding: 20,
    border: '1px solid #334155',
  };
  const tabBar: React.CSSProperties = {
    display: 'flex', gap: 0, marginBottom: 20, borderBottom: '1px solid #334155',
  };
  const tabBtn = (key: Tab, icon: React.ReactNode, label: string): React.CSSProperties => ({
    padding: '10px 20px', fontSize: 13, fontWeight: 600,
    color: tab === key ? '#3b82f6' : '#64748b',
    background: tab === key ? 'rgba(59,130,246,0.08)' : 'transparent',
    border: 'none', borderBottom: tab === key ? '2px solid #3b82f6' : '2px solid transparent',
    cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
  });

  return (
    <div style={{ padding: 24, maxWidth: 1000 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={() => navigate(-1)} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: '#64748b', padding: 4, display: 'flex',
          }}>
            <ArrowLeft size={18} />
          </button>
          <div>
            <h2 style={{ fontSize: 20, margin: 0, color: '#f1f5f9' }}>{specId}</h2>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>
              v{latestVersion?.version || '?'} · {STATUS_LABELS[latestVersion?.status] || '未知'}
            </div>
          </div>
        </div>
        <button onClick={openRevise} style={{
          background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 8,
          padding: '8px 18px', cursor: 'pointer', fontSize: 13, fontWeight: 600,
          display: 'flex', alignItems: 'center', gap: 6,
        }}>
          <Edit3 size={14} /> 修订 Spec
        </button>
      </div>

      {/* Tabs */}
      <div style={tabBar}>
        <button style={tabBtn('lifecycle', <GitBranch size={14} />, '版本历史')} onClick={() => setTab('lifecycle')}>版本历史</button>
        <button style={tabBtn('trace', <TrendingUp size={14} />, '决策痕迹')} onClick={() => setTab('trace')}>决策痕迹</button>
        <button style={tabBtn('radar', <AlertTriangle size={14} />, '信号雷达')} onClick={() => setTab('radar')}>信号雷达</button>
      </div>

      {/* Tab: Lifecycle */}
      {tab === 'lifecycle' && (
        <div>
          {history.length === 0 ? (
            <div style={{ ...cardBase, textAlign: 'center', color: '#94a3b8', fontSize: 14 }}>
              暂无版本历史
            </div>
          ) : (
            history.map((v: any, i: number) => (
              <div key={i} style={{
                ...cardBase, marginBottom: 10, display: 'flex', gap: 16, alignItems: 'flex-start',
                borderLeft: `4px solid ${STATUS_COLORS[v.status] || '#334155'}`,
              }}>
                <div style={{ minWidth: 40, textAlign: 'center' }}>
                  <div style={{ fontSize: 18, fontWeight: 700, color: '#f1f5f9' }}>v{v.version}</div>
                  <span style={{
                    padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 600,
                    background: `${STATUS_COLORS[v.status] || '#334155'}20`,
                    color: STATUS_COLORS[v.status] || '#94a3b8',
                  }}>
                    {STATUS_LABELS[v.status] || v.status}
                  </span>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, color: '#e2e8f0', marginBottom: 4 }}>
                    由 {v.created_by || '未知'} · {v.created_at?.slice(0, 10) || ''}
                  </div>
                  <div style={{ fontSize: 12, color: '#64748b' }}>
                    {v.trigger_detail || ''}
                  </div>
                  {v.execution_run_id && (
                    <div style={{ fontSize: 11, color: '#3b82f6', marginTop: 4, fontFamily: 'monospace' }}>
                      run: {v.execution_run_id}
                    </div>
                  )}
                  {v.affected_stages && v.affected_stages !== 'ALL' && (
                    <div style={{ fontSize: 11, color: '#f59e0b', marginTop: 2 }}>
                      仅重跑 stage: {JSON.stringify(v.affected_stages)}
                    </div>
                  )}
                  {v.execution_summary && (
                    <div style={{
                      fontSize: 12, color: '#94a3b8', marginTop: 6,
                      background: '#0f172a', padding: '6px 10px', borderRadius: 4,
                    }}>
                      {v.execution_summary}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Tab: Trace */}
      {tab === 'trace' && (
        <div>
          {!trace || trace.error ? (
            <div style={{ ...cardBase, textAlign: 'center', color: '#94a3b8', fontSize: 14 }}>
              暂无可视化数据 — 需在 DynamicRouter 模式下执行一次 Spec
            </div>
          ) : (
            <>
              {/* Stats */}
              <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
                {[
                  { label: '总步数', value: trace.total_steps },
                  { label: '犹豫步', value: trace.hesitation_count, warn: true },
                  { label: '重复调用', value: trace.repeat_count, danger: true },
                  { label: '唯一 Agent', value: trace.agent_call_order?.length || 0 },
                ].map((s, i) => (
                  <div key={i} style={{
                    flex: 1, ...cardBase, padding: 12, textAlign: 'center',
                  }}>
                    <div style={{ fontSize: 11, color: '#64748b' }}>{s.label}</div>
                    <div style={{
                      fontSize: 20, fontWeight: 700, marginTop: 2,
                      color: s.danger && s.value > 0 ? '#ef4444'
                        : s.warn && s.value > 1 ? '#f59e0b' : '#f1f5f9',
                    }}>
                      {s.value}
                    </div>
                  </div>
                ))}
              </div>

              {/* Decision chain */}
              <div style={cardBase}>
                <h3 style={{ fontSize: 14, margin: '0 0 12px', color: '#f1f5f9' }}>执行决策链</h3>
                <div style={{ fontFamily: 'monospace', fontSize: 13, lineHeight: 1.8, color: '#cbd5e1' }}>
                  {(trace.raw_steps || []).map((s: any, i: number) => (
                    <div key={i} style={{
                      padding: '8px 0', borderBottom: '1px solid #1e293b',
                      background: s.is_hesitation ? 'rgba(245,158,11,0.06)' : s.is_repeat ? 'rgba(239,68,68,0.04)' : 'transparent',
                    }}>
                      <span style={{ color: '#64748b', width: 24, display: 'inline-block', fontSize: 12 }}>{s.step}.</span>
                      <span style={{ color: s.agent ? '#3b82f6' : '#64748b', fontWeight: 600 }}>
                        {s.agent || 'FINISH'}
                      </span>
                      {s.is_hesitation && <span style={{ fontSize: 10, color: '#f59e0b', marginLeft: 6, fontWeight: 600 }}>犹豫</span>}
                      {s.is_repeat && <span style={{ fontSize: 10, color: '#ef4444', marginLeft: 6, fontWeight: 600 }}>重复</span>}
                      <div style={{ fontSize: 12, color: '#64748b', marginTop: 2, marginLeft: 24 }}>
                        {s.reasoning}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Anomalies */}
              {(trace.anomalies || []).length > 0 && (
                <div style={{ ...cardBase, marginTop: 16, border: '1px solid #f59e0b30' }}>
                  <h3 style={{ fontSize: 14, margin: '0 0 10px', color: '#f59e0b' }}>异常</h3>
                  {trace.anomalies.map((a: string, i: number) => (
                    <div key={i} style={{ padding: '6px 10px', fontSize: 13, color: '#e2e8f0', background: 'rgba(245,158,11,0.06)', borderRadius: 4, marginBottom: 4 }}>
                      {a}
                    </div>
                  ))}
                </div>
              )}

              {/* Spec suggestions from trace */}
              {(trace.spec_suggestions || []).length > 0 && (
                <div style={{ ...cardBase, marginTop: 16, border: '1px solid #3b82f630' }}>
                  <h3 style={{ fontSize: 14, margin: '0 0 10px', color: '#3b82f6' }}>Spec 调整建议</h3>
                  {trace.spec_suggestions.map((s: string, i: number) => (
                    <div key={i} style={{ padding: '6px 10px', fontSize: 13, color: '#e2e8f0', background: 'rgba(59,130,246,0.06)', borderRadius: 4, marginBottom: 4 }}>
                      {s}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Tab: Radar */}
      {tab === 'radar' && (
        <div>
          {!radar || (radar.suggestions || []).length === 0 ? (
            <div style={{ ...cardBase, textAlign: 'center', color: '#22c55e', fontSize: 14 }}>
              未检测到用户反馈信号异常
            </div>
          ) : (
            <>
              {/* Severity summary */}
              <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
                {['low', 'medium', 'high', 'critical'].map(severity => {
                  const count = radar.suggestions.filter((s: any) => s.severity === severity).length;
                  return (
                    <div key={severity} style={{
                      flex: 1, ...cardBase, padding: 12, textAlign: 'center',
                      border: `1px solid ${SEVERITY_COLORS[severity]}30`,
                    }}>
                      <div style={{ fontSize: 24, fontWeight: 700, color: SEVERITY_COLORS[severity] }}>{count}</div>
                      <div style={{ fontSize: 11, color: '#64748b' }}>
                        {severity === 'low' ? '低' : severity === 'medium' ? '中' : severity === 'high' ? '高' : '严重'}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Cards */}
              {radar.suggestions.map((s: any, i: number) => (
                <div key={i} style={{
                  ...cardBase, marginBottom: 10,
                  borderLeft: `4px solid ${SEVERITY_COLORS[s.severity] || '#334155'}`,
                }}>
                  <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                    <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 600,
                      background: `${SEVERITY_COLORS[s.severity]}20`, color: SEVERITY_COLORS[s.severity] }}>
                      {s.severity.toUpperCase()}
                    </span>
                    <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 10, background: '#334155', color: '#94a3b8' }}>
                      {s.type}
                    </span>
                    {s.evidence_count > 0 && <span style={{ fontSize: 11, color: '#64748b' }}>{s.evidence_count} 条证据</span>}
                  </div>
                  <div style={{ fontSize: 13, color: '#e2e8f0', marginBottom: 6 }}>{s.detail}</div>
                  <div style={{ fontSize: 12, color: '#3b82f6', background: 'rgba(59,130,246,0.06)', padding: '6px 10px', borderRadius: 4 }}>
                    {s.suggested_action}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {/* ── Revise Modal ── */}
      {reviseOpen && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 100,
          background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }} onClick={() => setReviseOpen(false)}>
          <div onClick={e => e.stopPropagation()} style={{
            background: '#1e293b', border: '1px solid #334155', borderRadius: 14,
            padding: 24, width: 600, maxHeight: '85vh', overflow: 'auto',
          }}>
            <h3 style={{ fontSize: 16, margin: '0 0 16px', color: '#f1f5f9' }}>
              修订 Spec: {specId}
            </h3>

            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>Spec 内容 (JSON)</div>
              <textarea value={reviseContent} onChange={e => setReviseContent(e.target.value)}
                style={{
                  width: '100%', minHeight: 200, background: '#0f172a', border: '1px solid #334155',
                  borderRadius: 8, padding: 12, color: '#e2e8f0', fontSize: 12,
                  fontFamily: 'monospace', resize: 'vertical',
                }} />
            </div>

            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>修订原因</div>
              <input value={reviseDetail} onChange={e => setReviseDetail(e.target.value)}
                placeholder="例如：用户反馈边界条件X未覆盖..."
                style={{
                  width: '100%', background: '#0f172a', border: '1px solid #334155',
                  borderRadius: 6, padding: '8px 12px', color: '#e2e8f0', fontSize: 13,
                }} />
            </div>

            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>交付物定义 (Matter)</div>
              <input value={deliverable} onChange={e => setDeliverable(e.target.value)}
                placeholder="如：产出一份 PDF 报告 / 一段 JSON 配置 / 一份 Markdown 文档"
                style={{
                  width: '100%', background: '#0f172a', border: '1px solid #334155',
                  borderRadius: 6, padding: '8px 12px', color: '#e2e8f0', fontSize: 13,
                }} />
            </div>

            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>验收标准 (Matter)</div>
              <input value={acceptanceCriteria} onChange={e => setAcceptanceCriteria(e.target.value)}
                placeholder="如：准确率 > 90% / 长度 < 500字 / 包含完整的引用来源"
                style={{
                  width: '100%', background: '#0f172a', border: '1px solid #334155',
                  borderRadius: 6, padding: '8px 12px', color: '#e2e8f0', fontSize: 13,
                }} />
            </div>

            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>
                只重跑 stage 索引 (逗号分隔，留空=全量重跑)
              </div>
              <input value={reviseStages} onChange={e => setReviseStages(e.target.value)}
                placeholder="例如: 1,3"
                style={{
                  width: '100%', background: '#0f172a', border: '1px solid #334155',
                  borderRadius: 6, padding: '8px 12px', color: '#e2e8f0', fontSize: 13,
                }} />
            </div>

            {reviseResult && (
              <div style={{
                padding: 10, borderRadius: 6, marginBottom: 16, fontSize: 12,
                background: reviseResult.error ? '#422006' : '#052e16',
                color: reviseResult.error ? '#fbbf24' : '#22c55e',
              }}>
                {reviseResult.error
                  ? `修订失败: ${reviseResult.error}`
                  : `v${reviseResult.version} 已创建${reviseResult.run_id ? '，重执行已触发' : ''}`}
              </div>
            )}

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button onClick={() => setReviseOpen(false)} style={{
                background: '#334155', color: '#e2e8f0', border: 'none',
                borderRadius: 6, padding: '8px 16px', cursor: 'pointer', fontSize: 13,
              }}>
                取消
              </button>
              <button onClick={submitRevise} disabled={revising || !reviseContent.trim()} style={{
                background: '#3b82f6', color: '#fff', border: 'none',
                borderRadius: 6, padding: '8px 16px', cursor: 'pointer', fontSize: 13,
                fontWeight: 600, opacity: revising ? 0.5 : 1,
              }}>
                {revising ? '提交中...' : '修订并重执行'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SpecDetailPage;
