/**
 * UserWorkbench — End-user task submission + Spec management console.
 */
import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

interface Capability { id: string; name: string; desc: string; icon: string; }
interface Step { name: string; status: string; }
interface Result { summary: string; warnings: string[]; }
interface TaskEntry { run_id: string; capability: string; spec_id?: string; description: string; status: string; progress?: { current_step: number; total_steps: number; steps: Step[] }; result?: Result; created_at: string; }
interface SpecEntry { spec_id: string; latest_version: number; latest_status: string; updated_at: string; trigger: string; created_by: string; }
interface TimelineEvent { ts: string; type: string; spec_id: string; summary: string; }
interface FDEData {
  pending_decisions: { spec_id: string; version: number; days_in_review: number; execution_summary: string; }[];
  signal_alerts: { spec_id: string; type: string; severity: string; detail: string; suggested_action: string; }[];
  trace_anomalies: { spec_id: string; total_steps: number; hesitation_count: number; repeat_count: number; anomaly_warnings: string[]; }[];
  training: { enabled: boolean; quality_count: number; threshold: number; progress_pct: number; ready_to_trigger: boolean; latest_model: string; dataset_count: number; };
  timeline: TimelineEvent[];
  last_updated: string;
}

const STATUS_COLORS: Record<string, string> = { draft:'#94a3b8', pending:'#3b82f6', executing:'#f59e0b', review:'#a855f7', revising:'#ec4899', stable:'#22c55e', archived:'#64748b' };
const STATUS_LABELS: Record<string, string> = { draft:'草稿', pending:'待执行', executing:'执行中', review:'待审查', revising:'修订中', stable:'稳定', archived:'归档' };

const UserWorkbench: React.FC = () => {
  const navigate = useNavigate();
  const [caps, setCaps] = useState<Capability[]>([]);
  const [selectedCap, setSelectedCap] = useState('general');
  const [selectedSpec, setSelectedSpec] = useState('');
  const [description, setDescription] = useState('');
  const [currentTask, setCurrentTask] = useState<TaskEntry | null>(null);
  const [history, setHistory] = useState<TaskEntry[]>([]);
  const [specs, setSpecs] = useState<SpecEntry[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [fdeData, setFDEData] = useState<FDEData | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [createSpecId, setCreateSpecId] = useState('');
  const [createContent, setCreateContent] = useState('');
  const [expandedCard, setExpandedCard] = useState<string | null>(null);
  const [specFilter, setSpecFilter] = useState<string>('all');
  const pollRef = useRef<number>(0);
  const dashRef = useRef<number>(0);

  const STATUS_PRIORITY: Record<string, number> = { review: 0, executing: 1, revising: 2, pending: 3, stable: 4, draft: 5, archived: 6 };
  const sortedSpecs = [...specs].sort((a, b) => {
    const pa = STATUS_PRIORITY[a.latest_status] ?? 9;
    const pb = STATUS_PRIORITY[b.latest_status] ?? 9;
    if (pa !== pb) return pa - pb;
    return (b.updated_at || '').localeCompare(a.updated_at || '');
  });
  const filteredSpecs = sortedSpecs.filter(s => {
    if (specFilter === 'all') return true;
    if (specFilter === 'review') return s.latest_status === 'review';
    if (specFilter === 'alerts') return getRadarCount(s.spec_id) > 0;
    if (specFilter === 'anomalies') return getTraceCount(s.spec_id) > 0;
    return true;
  });

  useEffect(() => {
    fetch('/api/core/workbench/capabilities').then(r => r.json()).then(setCaps);
    fetch('/api/core/workbench/tasks').then(r => r.json()).then(d => setHistory(d.items || []));
    fetch('/api/core/workbench/specs').then(r => r.json()).then(d => setSpecs(d.specs || []));
    fetch('/api/core/workbench/fde-dashboard').then(r => r.json()).then(setFDEData);
  }, []);

  useEffect(() => {
    dashRef.current = window.setInterval(async () => {
      try {
        const res = await fetch('/api/core/workbench/fde-dashboard');
        setFDEData(await res.json());
      } catch {}
    }, 30000);
    return () => clearInterval(dashRef.current);
  }, []);

  const pollTask = (runId: string) => {
    pollRef.current = window.setInterval(async () => {
      const res = await fetch(`/api/core/workbench/tasks/${runId}`);
      const t = await res.json();
      setCurrentTask(t);
      if (t.status === 'completed' || t.status === 'failed') {
        clearInterval(pollRef.current);
        fetch('/api/core/workbench/tasks').then(r => r.json()).then(d => setHistory(d.items || []));
        fetch('/api/core/workbench/specs').then(r => r.json()).then(d => setSpecs(d.specs || []));
      }
    }, 2000);
  };

  const submit = async () => {
    if (!description.trim()) return;
    setSubmitting(true);
    const res = await fetch('/api/core/workbench/submit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description, capability: selectedCap, spec_id: selectedSpec }),
    });
    const { run_id } = await res.json();
    setDescription('');
    setSubmitting(false);
    pollTask(run_id);
  };

  const sendFeedback = async (runId: string, action: string) => {
    await fetch(`/api/core/workbench/tasks/${runId}/feedback`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating: action === 'useful' ? 5 : 2, action }),
    });
  };

  const statusIcon = (s: string) => s === 'completed' ? '✅' : s === 'running' ? '🟡' : '⬜';

  const handleCreateSpec = async () => {
    if (!createSpecId.trim()) return;
    const res = await fetch('/api/core/workbench/spec/create', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spec_id: createSpecId.trim(), content: { agent_md: createContent || `# ${createSpecId}` }, created_by: 'developer' }),
    });
    const data = await res.json();
    setCreateOpen(false);
    setCreateSpecId('');
    setCreateContent('');
    if (data.spec_id) {
      navigate(`/value-center/spec/${data.spec_id}`);
      return;
    }
    // fallback refresh
    const sRes = await fetch('/api/core/workbench/specs');
    setSpecs((await sRes.json()).specs || []);
    const dashRes = await fetch('/api/core/workbench/fde-dashboard');
    setFDEData(await dashRes.json());
  };

  const handleMarkStable = async (specId: string) => {
    await fetch(`/api/core/workbench/spec/${specId}/mark-stable`, { method: 'POST' });
    const [sRes, dRes] = await Promise.all([
      fetch('/api/core/workbench/specs'),
      fetch('/api/core/workbench/fde-dashboard'),
    ]);
    setSpecs((await sRes.json()).specs || []);
    setFDEData(await dRes.json());
  };

  const getRadarCount = (specId: string) =>
    (fdeData?.signal_alerts || []).filter(a => a.spec_id === specId).length;
  const getTraceCount = (specId: string) =>
    (fdeData?.trace_anomalies || []).filter(a => a.spec_id === specId).length;

  return (
    <div style={{ padding: 24, background: '#0f172a', minHeight: '100vh', color: '#e2e8f0' }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>User Workbench</h1>

      {/* ── FDE 仪表板 ── */}
      {fdeData && (
        <div style={{ ...cardStyle, marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h2 style={{ fontSize: 16, margin: 0 }}>仪表板</h2>
            <span style={{ fontSize: 11, color: '#475569' }}>
              {fdeData.last_updated?.slice(11, 19) || ''}
            </span>
          </div>

          {fdeData.pending_decisions.length === 0 &&
            fdeData.signal_alerts.length === 0 &&
            fdeData.trace_anomalies.length === 0 &&
            !fdeData.training.ready_to_trigger && (
             <div style={{
               padding: '12px 16px', background: '#0f172a', borderRadius: 8,
               marginBottom: 16, fontSize: 12, color: '#475569', textAlign: 'center',
             }}>
               <span>暂无待处理事项 — 提交一个关联 Spec 的任务即可开始收集数据</span>
               <button onClick={async () => {
                 await fetch('/api/core/workbench/seed-demo', { method: 'POST' });
                 setTimeout(async () => {
                   const [sRes, dRes] = await Promise.all([
                     fetch('/api/core/workbench/specs'),
                     fetch('/api/core/workbench/fde-dashboard'),
                   ]);
                   setSpecs((await sRes.json()).specs || []);
                   setFDEData(await dRes.json());
                 }, 6000);
               }} style={{
                 marginLeft: 12, background: '#3b82f6', color: '#fff', border: 'none',
                 borderRadius: 6, padding: '4px 14px', cursor: 'pointer', fontSize: 12, fontWeight: 600,
               }}>
                 ⚡ 种子 Demo 数据
               </button>
             </div>
           )}

          <div style={{ display: 'flex', gap: 12, marginBottom: expandedCard ? 16 : 0 }}>
            <ExpandableCard
              id="decisions"
              title="待我决策"
              count={fdeData.pending_decisions.length}
              unit="个 Spec"
              color={fdeData.pending_decisions.length > 0 ? '#f59e0b' : '#22c55e'}
              items={fdeData.pending_decisions.map(d => ({
                label: d.spec_id,
                sub: `v${d.version} · ${d.days_in_review} 天`,
                link: `/value-center/spec/${d.spec_id}`,
              }))}
              expanded={expandedCard}
              onToggle={(newId) => {
                setExpandedCard(newId);
                setSpecFilter('review');
                setTimeout(() => document.getElementById('spec-management')?.scrollIntoView({ behavior: 'smooth' }), 100);
              }}
            />
            <ExpandableCard
              id="alerts"
              title="信号预警"
              count={fdeData.signal_alerts.length}
              unit="条"
              color={fdeData.signal_alerts.length > 0 ? '#ef4444' : '#22c55e'}
              items={fdeData.signal_alerts.map(a => ({
                label: a.spec_id,
                sub: `${a.severity} · ${a.type}`,
                link: `/value-center/spec/${a.spec_id}?tab=radar`,
              }))}
              expanded={expandedCard}
              onToggle={(newId) => {
                setExpandedCard(newId);
                setSpecFilter('alerts');
                setTimeout(() => document.getElementById('spec-management')?.scrollIntoView({ behavior: 'smooth' }), 100);
              }}
            />
            <ExpandableCard
              id="anomalies"
              title="执行异常"
              count={fdeData.trace_anomalies.length}
              unit="个 Spec"
              color={fdeData.trace_anomalies.length > 0 ? '#ef4444' : '#22c55e'}
              items={fdeData.trace_anomalies.map(a => ({
                label: a.spec_id,
                sub: `${a.repeat_count}重复 · ${a.hesitation_count}犹豫`,
                link: `/value-center/spec/${a.spec_id}?tab=trace`,
              }))}
              expanded={expandedCard}
              onToggle={(newId) => {
                setExpandedCard(newId);
                setSpecFilter('anomalies');
                setTimeout(() => document.getElementById('spec-management')?.scrollIntoView({ behavior: 'smooth' }), 100);
              }}
            />
            <ExpandableCard
              id="training"
              title="训练进度"
              count={Math.round(fdeData.training.progress_pct)}
              unit="%"
              color={fdeData.training.ready_to_trigger ? '#22c55e' : '#3b82f6'}
              items={[
                { label: '高质量样本', sub: `${fdeData.training.quality_count}/${fdeData.training.threshold}`, link: '' },
                ...(fdeData.training.latest_model ? [{ label: '最新模型', sub: fdeData.training.latest_model, link: '' }] : []),
                { label: '数据集', sub: `${fdeData.training.dataset_count} 个`, link: '' },
              ]}
              expanded={expandedCard}
              onToggle={setExpandedCard}
            />
          </div>

          <div style={{ borderTop: '1px solid #1e293b', paddingTop: 12 }}>
            <h3 style={{ fontSize: 13, color: '#94a3b8', marginBottom: 8 }}>最近 7 天活动</h3>
            <div style={{ maxHeight: 180, overflow: 'auto' }}>
              {fdeData.timeline.length === 0 ? (
                <div style={{ padding: '8px 0', fontSize: 12, color: '#475569', textAlign: 'center' }}>
                  暂无活动
                </div>
              ) : (
                fdeData.timeline.map((e: TimelineEvent, i: number) => (
                  <div key={i} style={{
                    display: 'flex', gap: 12, padding: '7px 0',
                    borderBottom: '1px solid #0f172a', fontSize: 12,
                    cursor: e.spec_id && e.spec_id !== 'all' ? 'pointer' : 'default',
                  }} onClick={() => {
                    if (e.spec_id && e.spec_id !== 'all') navigate(`/value-center/spec/${e.spec_id}`);
                  }}>
                    <span style={{
                      color: e.type === 'radar_alert' ? '#ef4444'
                           : e.type === 'trace_anomaly' ? '#f59e0b'
                           : e.type === 'training_event' ? '#a855f7'
                           : '#3b82f6',
                      whiteSpace: 'nowrap', minWidth: 75, fontSize: 11,
                    }}>
                      {e.ts?.slice(5, 16) || ''}
                    </span>
                    <span style={{
                      color: e.type === 'radar_alert' ? '#fca5a5'
                           : e.type === 'trace_anomaly' ? '#fcd34d'
                           : '#94a3b8',
                      lineHeight: 1.4,
                    }}>
                      {e.type === 'status_change' ? '📋'
                       : e.type === 'radar_alert' ? '⚠️'
                       : e.type === 'trace_anomaly' ? '🔁'
                       : '🧠'}
                      {' '}{e.summary}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Spec Management Section ── */}
      {specs.length > 0 ? (
        <div id="spec-management" style={{ ...cardStyle, marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h2 style={{ fontSize: 16, margin: 0 }}>Spec 管理</h2>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span style={{ fontSize: 12, color: '#64748b' }}>{specs.length} 个活跃 Spec</span>
              <button onClick={() => setCreateOpen(true)} style={{
                background: '#334155', color: '#e2e8f0', border: 'none',
                borderRadius: 6, padding: '5px 12px', cursor: 'pointer', fontSize: 12, fontWeight: 600,
              }}>
                + 新建
              </button>
            </div>
          </div>
          <FilterBar filter={specFilter} onFilter={(f) => { setSpecFilter(f); document.getElementById('spec-management')?.scrollIntoView({ behavior: 'smooth' }); }}
            reviewCount={specs.filter(s => s.latest_status === 'review').length}
            alertCount={specs.filter(s => getRadarCount(s.spec_id) > 0).length}
            anomalyCount={specs.filter(s => getTraceCount(s.spec_id) > 0).length}
          />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {filteredSpecs.length === 0 ? (
              <div style={{ padding: '20px 0', textAlign: 'center', fontSize: 13, color: '#475569' }}>
                无匹配的 Spec
              </div>
            ) : filteredSpecs.map((s: SpecEntry) => (
              <div key={s.spec_id} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '10px 14px', background: '#0f172a', borderRadius: 8,
                border: '1px solid #1e293b',
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#f1f5f9', cursor: 'pointer' }}
                      onClick={() => navigate(`/value-center/spec/${s.spec_id}`)}>
                      {s.spec_id}
                    </span>
                    <span style={{
                      padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 600,
                      background: `${STATUS_COLORS[s.latest_status] || '#334155'}20`,
                      color: STATUS_COLORS[s.latest_status] || '#94a3b8',
                    }}>
                      v{s.latest_version} · {STATUS_LABELS[s.latest_status] || s.latest_status}
                    </span>
                    {/* Mini-indicators */}
                    {getRadarCount(s.spec_id) > 0 && (
                      <span style={{
                        padding: '1px 5px', borderRadius: 3, fontSize: 9, fontWeight: 700,
                        background: '#ef444420', color: '#ef4444',
                      }}>
                        ⚠{getRadarCount(s.spec_id)}
                      </span>
                    )}
                    {getTraceCount(s.spec_id) > 0 && (
                      <span style={{
                        padding: '1px 5px', borderRadius: 3, fontSize: 9, fontWeight: 700,
                        background: '#f59e0b20', color: '#f59e0b',
                      }}>
                        🔁{getTraceCount(s.spec_id)}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
                    创建: {s.created_by || '—'} · {s.updated_at?.slice(0, 10) || ''}
                    {s.trigger && s.trigger !== 'manual' && (
                      <span style={{ color: '#a855f7', marginLeft: 8 }}>{s.trigger}</span>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  {s.latest_status === 'review' && (
                    <button onClick={(e) => { e.stopPropagation(); handleMarkStable(s.spec_id); }}
                      style={{
                        ...actionBtn, color: '#22c55e', borderColor: '#22c55e40',
                        fontSize: 10, padding: '3px 8px',
                      }}>
                      确认稳定
                    </button>
                  )}
                  <button onClick={() => navigate(`/value-center/spec/${s.spec_id}?tab=trace`)}
                    style={actionBtn}>
                    决策
                  </button>
                  <button onClick={() => navigate(`/value-center/spec/${s.spec_id}?tab=radar`)}
                    style={actionBtn}>
                    信号
                  </button>
                  <button onClick={() => navigate(`/value-center/spec/${s.spec_id}`)}
                    style={{ ...actionBtn, color: '#3b82f6', borderColor: '#3b82f630' }}>
                    详情 →
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div style={{ ...cardStyle, marginBottom: 16, textAlign: 'center', padding: 32 }}>
          <div style={{ fontSize: 14, color: '#94a3b8', marginBottom: 8 }}>暂无 Spec</div>
          <div style={{ fontSize: 12, color: '#475569', marginBottom: 16 }}>
            创建第一个 Spec 以开始管理 Agent 部署
          </div>
          <button onClick={() => setCreateOpen(true)} style={{
            background: '#3b82f6', color: '#fff', border: 'none',
            borderRadius: 6, padding: '8px 18px', cursor: 'pointer', fontSize: 13, fontWeight: 600,
          }}>
            + 新建 Spec
          </button>
        </div>
      )}

      {/* Submit Area */}
      <div style={cardStyle}>
        <h2 style={{ fontSize: 16, marginBottom: 12 }}>发起任务</h2>
        <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
          {(caps.length ? caps : [
            { id: 'general', name: '通用任务', desc: '', icon: '🤖' },
          ]).map(c => (
            <button key={c.id} onClick={() => setSelectedCap(c.id)}
              style={{
                padding: '10px 16px', borderRadius: 8, border: 'none', cursor: 'pointer',
                background: selectedCap === c.id ? '#3b82f6' : '#1e293b',
                color: selectedCap === c.id ? '#fff' : '#94a3b8',
                fontSize: 13, fontWeight: 600,
              }}>
              {c.icon} {c.name}
            </button>
          ))}
        </div>
        {specs.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>关联 Spec（可选，关联后可追踪执行痕迹）</div>
            <select value={selectedSpec} onChange={e => setSelectedSpec(e.target.value)}
              style={{
                background: '#0f172a', border: '1px solid #334155', borderRadius: 6,
                padding: '8px 12px', color: '#e2e8f0', fontSize: 13, width: '100%',
              }}>
              <option value="">不关联 Spec</option>
              {specs.map(s => (
                <option key={s.spec_id} value={s.spec_id}>{s.spec_id} (v{s.latest_version} · {STATUS_LABELS[s.latest_status]})</option>
              ))}
            </select>
          </div>
        )}
        <textarea value={description} onChange={e => setDescription(e.target.value)}
          placeholder="请描述你的任务，例如：请审核这份采购合同中的价格、交付和违约条款..."
          style={{ width: '100%', minHeight: 80, background: '#0f172a', border: '1px solid #334155',
            borderRadius: 8, padding: 12, color: '#e2e8f0', fontSize: 13, resize: 'vertical', marginBottom: 12 }} />
        <button onClick={submit} disabled={submitting || !description.trim()}
          style={{ ...btnPrimary, opacity: submitting ? 0.5 : 1 }}>
          {submitting ? '提交中...' : '提交任务'}
        </button>
      </div>

      {/* Progress */}
      {currentTask && currentTask.status !== 'completed' && (
        <div style={{ ...cardStyle, marginTop: 16 }}>
          <h2 style={{ fontSize: 16, marginBottom: 12 }}>执行进度</h2>
          {(currentTask.progress?.steps || []).map((s: Step, i: number) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 0', borderBottom: '1px solid #1e293b' }}>
              <span>{statusIcon(s.status)}</span>
              <span style={{ fontSize: 13 }}>{s.name}</span>
            </div>
          ))}
        </div>
      )}

      {/* Result */}
      {currentTask && currentTask.status === 'completed' && currentTask.result && (
        <div style={{ ...cardStyle, marginTop: 16, borderLeft: '4px solid #22c55e' }}>
          <h2 style={{ fontSize: 16, marginBottom: 8 }}>任务完成</h2>
          <div style={{ fontSize: 13, whiteSpace: 'pre-wrap', marginBottom: 12 }}>{currentTask.result.summary}</div>
          {currentTask.result.warnings?.length > 0 && (
            <div style={{ padding: 10, background: '#422006', borderRadius: 6, marginBottom: 12 }}>
              {currentTask.result.warnings.map((w: string, i: number) => (
                <div key={i} style={{ fontSize: 12, color: '#fbbf24' }}>⚠️ {w}</div>
              ))}
            </div>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => sendFeedback(currentTask.run_id, 'useful')} style={btnPrimary}>👍 有用</button>
            <button onClick={() => sendFeedback(currentTask.run_id, 'not_useful')} style={{ ...btnPrimary, background: '#334155' }}>👎 需要改进</button>
          </div>
        </div>
      )}

      {/* History */}
      <div style={{ ...cardStyle, marginTop: 16 }}>
        <h2 style={{ fontSize: 16, marginBottom: 12 }}>历史任务</h2>
        {history.map(h => (
          <div key={h.run_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid #1e293b' }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>
                {h.spec_id && (
                  <span style={{
                    cursor: 'pointer', color: '#a855f7', fontSize: 10, fontWeight: 600,
                    background: '#a855f710', padding: '1px 6px', borderRadius: 3, marginRight: 6,
                  }} onClick={() => navigate(`/value-center/spec/${h.spec_id}`)}>
                    Spec:{h.spec_id}
                  </span>
                )}
                {h.description?.slice(0, 50)}...
              </div>
              <div style={{ fontSize: 11, color: '#64748b' }}>{h.created_at} · {h.capability}</div>
            </div>
            <span style={{ fontSize: 12, color: h.status === 'completed' ? '#22c55e' : '#94a3b8' }}>
              {h.status === 'completed' ? '完成' : h.status}
            </span>
          </div>
        ))}
      </div>

      {/* ── Create Spec Modal ── */}
      {createOpen && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 100,
          background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }} onClick={() => setCreateOpen(false)}>
          <div onClick={e => e.stopPropagation()} style={{
            background: '#1e293b', border: '1px solid #334155', borderRadius: 14,
            padding: 24, width: 450,
          }}>
            <h3 style={{ fontSize: 16, margin: '0 0 16px', color: '#f1f5f9' }}>新建 Spec</h3>
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>Spec ID</div>
              <input value={createSpecId} onChange={e => setCreateSpecId(e.target.value)}
                placeholder="如: contract_review_v2"
                style={{
                  width: '100%', background: '#0f172a', border: '1px solid #334155',
                  borderRadius: 6, padding: '8px 12px', color: '#e2e8f0', fontSize: 13,
                }} />
            </div>
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>初始内容 (可选)</div>
              <textarea value={createContent} onChange={e => setCreateContent(e.target.value)}
                placeholder="Agent 描述或 Markdown 内容..."
                style={{
                  width: '100%', minHeight: 80, background: '#0f172a', border: '1px solid #334155',
                  borderRadius: 6, padding: '8px 12px', color: '#e2e8f0', fontSize: 13, resize: 'vertical',
                }} />
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button onClick={() => setCreateOpen(false)} style={{
                background: '#334155', color: '#e2e8f0', border: 'none',
                borderRadius: 6, padding: '8px 16px', cursor: 'pointer', fontSize: 13,
              }}>取消</button>
              <button onClick={handleCreateSpec} disabled={!createSpecId.trim()} style={{
                background: '#3b82f6', color: '#fff', border: 'none',
                borderRadius: 6, padding: '8px 16px', cursor: 'pointer', fontSize: 13,
                fontWeight: 600, opacity: createSpecId.trim() ? 1 : 0.5,
              }}>创建</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const ExpandableCard: React.FC<{
  id: string; title: string; count: number; unit: string;
  color: string; items: { label: string; sub: string; link: string }[];
  expanded: string | null; onToggle: (id: string | null) => void;
}> = ({ id, title, count, unit, color, items, expanded, onToggle }) => {
  const isExpanded = expanded === id;
  return (
    <div style={{ flex: 1 }}>
      <div onClick={() => onToggle(isExpanded ? null : id)} style={{
        background: count > 0 ? `${color}10` : '#1e293b',
        borderRadius: 10, padding: 16, cursor: 'pointer',
        border: `1px solid ${count > 0 ? color + '40' : '#334155'}`,
        position: 'relative',
      }} title={items.map(i => i.label).join(', ') || ''}>
        <div style={{ fontSize: 12, color: '#64748b', marginBottom: 6 }}>{title}</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
          <span style={{ fontSize: 28, fontWeight: 700, color }}>{count}</span>
          <span style={{ fontSize: 13, color: '#64748b' }}>{unit}</span>
        </div>
      </div>
      {isExpanded && items.length > 0 && (
        <div style={{
          marginTop: 6, background: '#0f172a', borderRadius: 8, padding: 8,
          border: `1px solid ${color}20`,
        }}>
          {items.slice(0, 5).map((item, i) => (
            <div key={i} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '5px 8px', fontSize: 12, borderBottom: i < items.length - 1 ? '1px solid #1e293b' : 'none',
            }}>
              <span style={{ color: '#e2e8f0', fontWeight: 500 }}>{item.label}</span>
              <span style={{ color: '#64748b', fontSize: 11 }}>{item.sub}</span>
            </div>
          ))}
          {items.length > 5 && (
            <div style={{ fontSize: 11, color: '#475569', textAlign: 'center', padding: '4px 0' }}>
              +{items.length - 5} 更多
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const FilterBar: React.FC<{
  filter: string; onFilter: (f: string) => void;
  reviewCount: number; alertCount: number; anomalyCount: number;
}> = ({ filter, onFilter, reviewCount, alertCount, anomalyCount }) => (
  <div style={{ display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
    {[
      { key: 'all', label: '全部' },
      { key: 'review', label: `待审查${reviewCount > 0 ? ` ${reviewCount}` : ''}`, color: '#a855f7' },
      { key: 'alerts', label: `有预警${alertCount > 0 ? ` ${alertCount}` : ''}`, color: '#ef4444' },
      { key: 'anomalies', label: `有异常${anomalyCount > 0 ? ` ${anomalyCount}` : ''}`, color: '#f59e0b' },
    ].map(f => (
      <button key={f.key} onClick={() => onFilter(f.key)} style={{
        padding: '4px 12px', borderRadius: 14, border: 'none', cursor: 'pointer',
        fontSize: 11, fontWeight: 600,
        background: filter === f.key ? (f.color || '#3b82f6') + '20' : '#0f172a',
        color: filter === f.key ? f.color || '#3b82f6' : '#64748b',
        border: filter === f.key ? `1px solid ${(f.color || '#3b82f6')}40` : '1px solid #1e293b',
      }}>
        {f.label}
      </button>
    ))}
  </div>
);

const cardStyle: React.CSSProperties = { background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: 20 };
const btnPrimary: React.CSSProperties = { background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600 };
const actionBtn: React.CSSProperties = { background: 'transparent', color: '#94a3b8', border: '1px solid #334155', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600 };

export default UserWorkbench;
