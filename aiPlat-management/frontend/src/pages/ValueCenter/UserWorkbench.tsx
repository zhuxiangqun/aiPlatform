/**
 * UserWorkbench — End-user task submission + progress + feedback interface.
 *
 * Routes: sidebar → User Workbench
 * API: POST /workbench/submit, GET /workbench/tasks, POST /workbench/tasks/{id}/feedback
 */
import React, { useState, useEffect, useRef } from 'react';

interface Capability { id: string; name: string; desc: string; icon: string; }
interface Step { name: string; status: string; }
interface Result { summary: string; warnings: string[]; }
interface TaskEntry { run_id: string; capability: string; description: string; status: string; progress?: { current_step: number; total_steps: number; steps: Step[] }; result?: Result; created_at: string; }

const UserWorkbench: React.FC = () => {
  const [caps, setCaps] = useState<Capability[]>([]);
  const [selectedCap, setSelectedCap] = useState('general');
  const [description, setDescription] = useState('');
  const [currentTask, setCurrentTask] = useState<TaskEntry | null>(null);
  const [history, setHistory] = useState<TaskEntry[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const pollRef = useRef<number>(0);

  useEffect(() => {
    fetch('/api/core/workbench/capabilities').then(r => r.json()).then(setCaps);
    fetch('/api/core/workbench/tasks').then(r => r.json()).then(d => setHistory(d.items || []));
  }, []);

  const pollTask = (runId: string) => {
    pollRef.current = window.setInterval(async () => {
      const res = await fetch(`/api/core/workbench/tasks/${runId}`);
      const t = await res.json();
      setCurrentTask(t);
      if (t.status === 'completed' || t.status === 'failed') {
        clearInterval(pollRef.current);
        fetch('/api/core/workbench/tasks').then(r => r.json()).then(d => setHistory(d.items || []));
      }
    }, 2000);
  };

  const submit = async () => {
    if (!description.trim()) return;
    setSubmitting(true);
    const res = await fetch('/api/core/workbench/submit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description, capability: selectedCap }),
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

  return (
    <div style={{ padding: 24, background: '#0f172a', minHeight: '100vh', color: '#e2e8f0' }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>User Workbench</h1>

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
          <h2 style={{ fontSize: 16, marginBottom: 8 }}>✅ 任务完成</h2>
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
              <div style={{ fontSize: 13, fontWeight: 600 }}>{h.description?.slice(0, 50)}...</div>
              <div style={{ fontSize: 11, color: '#64748b' }}>{h.created_at} · {h.capability}</div>
            </div>
            <span style={{ fontSize: 12, color: h.status === 'completed' ? '#22c55e' : '#94a3b8' }}>
              {h.status === 'completed' ? '完成' : h.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

const cardStyle: React.CSSProperties = { background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: 20 };
const btnPrimary: React.CSSProperties = { background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600 };

export default UserWorkbench;
