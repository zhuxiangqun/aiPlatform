/**
 * EnterpriseKPIs — Define and track enterprise business metrics.
 *
 * Routes: Value Center → Enterprise KPIs
 * API: GET/POST /api/core/value/{t}/goals + PUT source + GET trend
 */
import React, { useState, useEffect } from 'react';

interface KPI {
  goal_id: string;
  description: string;
  target_metric: string;
  baseline_value: number;
  target_value: number;
  current_value: number;
  progress_pct: number;
  achieved: boolean;
  owner: string;
  period: string;
  category?: string;
  linked_agent?: string;
}

const CATEGORIES = [
  { key: 'efficiency', label: '运营效率', color: '#3b82f6' },
  { key: 'quality', label: '质量提升', color: '#22c55e' },
  { key: 'safety', label: '安全合规', color: '#ef4444' },
  { key: 'innovation', label: '创新突破', color: '#a855f7' },
  { key: 'experience', label: '员工体验', color: '#eab308' },
];

const AGENTS = [
  'contract_review_agent', 'service_agent', 'security_agent',
  'ci_fix_agent', 'notes_agent', 'report_agent',
];

const EnterpriseKPIs: React.FC = () => {
  const [kpis, setKpis] = useState<KPI[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<KPI | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchKPIs = async () => {
    const res = await fetch('/api/core/value/all/goals');
    const data = await res.json();
    setKpis(data);
    setLoading(false);
  };

  useEffect(() => { fetchKPIs(); }, []);

  const saveKPI = async (form: any) => {
    const method = editing ? 'PUT' : 'POST';
    const url = editing
      ? `/api/core/value/all/goals/${form.goal_id}`
      : '/api/core/value/all/goals';
    const body: any = { ...form };
    if (!editing) body.goal_id = form.goal_id;

    await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

    // If linked agent specified, configure source
    if (form.linked_agent) {
      await fetch(`/api/core/value/all/goals/${form.goal_id}/source`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ collection_method: 'auto', linked_agent: form.linked_agent, category: form.category }),
      });
    }

    setShowModal(false);
    setEditing(null);
    fetchKPIs();
  };

  const deleteKPI = async (id: string) => {
    await fetch(`/api/core/value/all/goals/${id}`, { method: 'DELETE' });
    fetchKPIs();
  };

  if (loading) return <div style={pageStyle}><p style={{ color: '#94a3b8' }}>加载中...</p></div>;

  return (
    <div style={pageStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700 }}>Enterprise KPIs</h1>
        <button onClick={() => { setEditing(null); setShowModal(true); }}
          style={btnPrimary}>+ 新建指标</button>
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid #334155', textAlign: 'left' }}>
            <th style={thStyle}>名称</th><th style={thStyle}>基线</th><th style={thStyle}>目标</th>
            <th style={thStyle}>当前</th><th style={thStyle}>进度</th><th style={thStyle}>关联</th>
            <th style={thStyle}>类别</th><th style={thStyle}>操作</th>
          </tr>
        </thead>
        <tbody>
          {kpis.map(k => (
            <tr key={k.goal_id} style={{ borderBottom: '1px solid #1e293b' }}>
              <td style={tdStyle}>
                <div style={{ fontWeight: 600 }}>{k.description}</div>
                <div style={{ fontSize: 11, color: '#64748b' }}>{k.goal_id}</div>
              </td>
              <td style={tdStyle}>{k.baseline_value}</td>
              <td style={tdStyle}>{k.target_value}</td>
              <td style={tdStyle}>{k.current_value || '—'}</td>
              <td style={tdStyle}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ background: '#1e293b', borderRadius: 4, height: 6, width: 80 }}>
                    <div style={{ background: k.achieved ? '#22c55e' : k.progress_pct >= 0.8 ? '#eab308' : '#ef4444', height: 6, borderRadius: 4, width: `${Math.min(k.progress_pct * 80, 80)}px` }} />
                  </div>
                  <span style={{ fontSize: 12 }}>{(k.progress_pct * 100).toFixed(0)}%</span>
                </div>
              </td>
              <td style={tdStyle}>
                {k.linked_agent || <span style={{ color: '#64748b', fontSize: 12 }}>未关联</span>}
              </td>
              <td style={tdStyle}>
                <span style={{ color: CATEGORIES.find(c => c.key === k.category)?.color || '#94a3b8', fontSize: 12, fontWeight: 600 }}>
                  {CATEGORIES.find(c => c.key === k.category)?.label || '运营'}
                </span>
              </td>
              <td style={tdStyle}>
                <button onClick={() => { setEditing(k); setShowModal(true); }} style={btnSmall}>编辑</button>
                <button onClick={() => deleteKPI(k.goal_id)} style={{ ...btnSmall, color: '#ef4444', marginLeft: 4 }}>删除</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Modal */}
      {showModal && (
        <div style={modalOverlay} onClick={() => setShowModal(false)}>
          <div style={modalStyle} onClick={e => e.stopPropagation()}>
            <h2 style={{ fontSize: 18, marginBottom: 16 }}>{editing ? '编辑指标' : '新建指标'}</h2>
            <KPIForm initial={editing} onSave={saveKPI} onCancel={() => setShowModal(false)} />
          </div>
        </div>
      )}
    </div>
  );
};

const KPIForm: React.FC<{ initial: KPI | null; onSave: (f: any) => void; onCancel: () => void }> = ({ initial, onSave, onCancel }) => {
  const [form, setForm] = useState({
    goal_id: initial?.goal_id || '',
    description: initial?.description || '',
    baseline_value: initial?.baseline_value || 0,
    target_value: initial?.target_value || 0,
    current_value: initial?.current_value || 0,
    owner: initial?.owner || '',
    period: initial?.period || '',
    category: initial?.category || 'efficiency',
    linked_agent: initial?.linked_agent || '',
  });

  return (
    <div>
      {[['指标ID', 'goal_id'], ['描述', 'description'], ['基线值', 'baseline_value'], ['目标值', 'target_value'], ['当前值', 'current_value']].map(([label, key]) => (
        <div key={key} style={{ marginBottom: 12 }}>
          <label style={labelStyle}>{label}</label>
          <input value={(form as any)[key]} onChange={e => setForm({ ...form, [key]: e.target.value })}
            style={inputStyle} type={key.includes('value') ? 'number' : 'text'} />
        </div>
      ))}
      <div style={{ marginBottom: 12 }}>
        <label style={labelStyle}>类别</label>
        <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} style={inputStyle}>
          {CATEGORIES.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}
        </select>
      </div>
      <div style={{ marginBottom: 12 }}>
        <label style={labelStyle}>关联Agent</label>
        <select value={form.linked_agent} onChange={e => setForm({ ...form, linked_agent: e.target.value })} style={inputStyle}>
          <option value="">— 不关联 —</option>
          {AGENTS.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
      </div>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
        <button onClick={onCancel} style={{ ...btnPrimary, background: '#334155' }}>取消</button>
        <button onClick={() => onSave(form)} style={btnPrimary}>保存</button>
      </div>
    </div>
  );
};

const pageStyle: React.CSSProperties = { padding: 24, background: '#0f172a', minHeight: '100vh', color: '#e2e8f0' };
const cardStyle: React.CSSProperties = { background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: 20 };
const thStyle: React.CSSProperties = { padding: '8px 12px', fontSize: 12, color: '#94a3b8', fontWeight: 600 };
const tdStyle: React.CSSProperties = { padding: '8px 12px', fontSize: 13 };
const btnPrimary: React.CSSProperties = { background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600 };
const btnSmall: React.CSSProperties = { background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: 12, padding: '4px 8px' };
const inputStyle: React.CSSProperties = { width: '100%', background: '#0f172a', border: '1px solid #334155', borderRadius: 6, padding: '8px 12px', color: '#e2e8f0', fontSize: 13 };
const labelStyle: React.CSSProperties = { display: 'block', marginBottom: 4, fontSize: 12, color: '#94a3b8' };
const modalOverlay: React.CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 };
const modalStyle: React.CSSProperties = { ...cardStyle, width: 480, maxHeight: '80vh', overflow: 'auto' };

export default EnterpriseKPIs;
