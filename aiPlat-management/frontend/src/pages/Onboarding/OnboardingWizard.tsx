/**
 * OnboardingWizard — 7-step guided self-service onboarding flow.
 *
 * Steps: 注册 → 验证 → 模型 → 工具 → Agent → 检查 → 上线
 * API:  GET  /onboarding/progress
 *       POST /onboarding/progress/{step_key}
 *       POST /onboarding/activate
 */
import React, { useState, useEffect } from 'react';

interface Step { step: number; key: string; name: string; done: boolean; }
interface ProgressData { tenant_id: string; status: string; steps: Step[]; progress_pct: number; estimated_completion: string; }

const OnboardingWizard: React.FC = () => {
  const [progress, setProgress] = useState<ProgressData | null>(null);
  const [currentStep, setCurrentStep] = useState(3); // skip register+verify for demo
  const [models, setModels] = useState<any[]>([]);
  const [templates, setTemplates] = useState<any[]>([]);
  const [readiness, setReadiness] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchProgress();
    fetch('/api/platform/onboarding/model-recommendations').then(r => r.json()).then(setModels);
    fetch('/api/platform/onboarding/agent-templates').then(r => r.json()).then(setTemplates);
  }, []);

  const fetchProgress = async () => {
    setLoading(true);
    const res = await fetch('/api/platform/onboarding/progress');
    const data = await res.json();
    setProgress(data);
    setLoading(false);
  };

  const markDone = async (stepKey: string) => {
    await fetch(`/api/platform/onboarding/progress/${stepKey}`, { method: 'POST' });
    await fetchProgress();
  };

  const checkReadiness = async () => {
    const res = await fetch('/api/platform/onboarding/readiness-check');
    const data = await res.json();
    setReadiness(data);
    return data.ready;
  };

  const activate = async () => {
    const ready = await checkReadiness();
    if (!ready) return;
    await fetch('/api/platform/onboarding/activate', { method: 'POST' });
    await fetchProgress();
  };

  if (loading || !progress) return <div style={pageStyle}><p style={{ color: '#94a3b8' }}>加载中...</p></div>;

  return (
    <div style={pageStyle}>
      {/* Header */}
      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <h1 style={{ fontSize: 28, fontWeight: 800, marginBottom: 8 }}>入驻向导</h1>
        <div style={{ fontSize: 13, color: '#94a3b8' }}>{progress.estimated_completion}</div>
      </div>

      {/* Progress Bar */}
      <div style={{ display: 'flex', justifyContent: 'center', gap: 0, marginBottom: 32 }}>
        {progress.steps.map((s, i) => (
          <div key={s.key} style={{ display: 'flex', alignItems: 'center' }}>
            <button onClick={() => setCurrentStep(s.step)}
              style={{
                width: 36, height: 36, borderRadius: '50%', border: 'none', cursor: 'pointer',
                background: s.done ? '#22c55e' : currentStep === s.step ? '#3b82f6' : '#334155',
                color: '#fff', fontWeight: 700, fontSize: 14,
              }}>
              {s.done ? '✓' : s.step}
            </button>
            {i < progress.steps.length - 1 && (
              <div style={{ width: 24, height: 2, background: s.done ? '#22c55e' : '#334155' }} />
            )}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'center', gap: 0, marginBottom: 32, fontSize: 11, color: '#94a3b8' }}>
        {progress.steps.map(s => (
          <div key={s.key} style={{ width: 60, textAlign: 'center' }}>{s.name}</div>
        ))}
      </div>

      {/* Step Content */}
      <div style={cardStyle}>
        {currentStep === 3 && (
          <StepModel models={models} onDone={() => { markDone('model'); setCurrentStep(4); }} />
        )}
        {currentStep === 4 && (
          <StepTools onDone={() => { markDone('tools'); setCurrentStep(5); }} />
        )}
        {currentStep === 5 && (
          <StepAgent templates={templates} onDone={() => { markDone('agent'); setCurrentStep(6); }} />
        )}
        {currentStep === 6 && (
          <StepChecklist readiness={readiness} onCheck={checkReadiness} onActivate={activate} />
        )}
        {currentStep === 7 && (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🚀</div>
            <h2 style={{ fontSize: 24, marginBottom: 8 }}>上线成功！</h2>
            <p style={{ color: '#94a3b8', marginBottom: 20 }}>你的 AI 平台已就绪，可以开始使用了</p>
            <button onClick={() => window.location.href = '/value-center'} style={btnPrimary}>
              进入 Value Center
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

// ── Step 3: Model Selection ──
const StepModel: React.FC<{ models: any[]; onDone: () => void }> = ({ models, onDone }) => {
  const [selectedModel, setSelectedModel] = useState('');
  return (
    <div>
      <h2 style={{ fontSize: 18, marginBottom: 16 }}>Step 3: 配置模型</h2>
      <p style={{ fontSize: 13, color: '#94a3b8', marginBottom: 16 }}>
        选择 AI 使用的推理模型和 Embedding 模型。选错没关系，上线后可以随时调整。
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12, marginBottom: 20 }}>
        {models.map(m => (
          <div key={m.model} onClick={() => setSelectedModel(m.model)}
            style={{
              padding: 16, borderRadius: 8, cursor: 'pointer',
              background: selectedModel === m.model ? '#1e3a5f' : '#0f172a',
              border: `1px solid ${selectedModel === m.model ? '#3b82f6' : '#1e293b'}`,
            }}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>{m.purpose}</div>
            <div style={{ fontSize: 13, color: '#3b82f6', marginBottom: 4 }}>{m.model}</div>
            <div style={{ fontSize: 12, color: '#64748b' }}>¥{m.cost_per_1M}/1M tokens</div>
            <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>适合: {m.suitable.join(', ')}</div>
          </div>
        ))}
      </div>
      <button onClick={onDone} style={btnPrimary}>下一步 → 工具</button>
    </div>
  );
};

// ── Step 4: Tool Connection ──
const StepTools: React.FC<{ onDone: () => void }> = ({ onDone }) => {
  const tools = [
    { id: 'document_parser', name: '文档解析', desc: 'PDF/Word/PPT → 结构化文本' },
    { id: 'api_call', name: 'API调用', desc: '对接外部系统(CRM/ERP)' },
    { id: 'database_query', name: '数据库查询', desc: 'SQL/NoSQL数据检索' },
    { id: 'code_analysis', name: '代码分析', desc: '静态分析+安全扫描' },
  ];
  const [connected, setConnected] = useState<string[]>([]);

  const connect = async (toolId: string) => {
    await fetch('/api/platform/onboarding/tools/connect', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool_name: toolId }),
    });
    setConnected([...connected, toolId]);
  };

  return (
    <div>
      <h2 style={{ fontSize: 18, marginBottom: 16 }}>Step 4: 接入工具</h2>
      <p style={{ fontSize: 13, color: '#94a3b8', marginBottom: 16 }}>
        启用你需要用到的工具。每个工具一键接入，无需写代码。
      </p>
      <div style={{ display: 'grid', gap: 8, marginBottom: 20 }}>
        {tools.map(t => (
          <div key={t.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 12, background: '#0f172a', borderRadius: 8 }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>{t.name}</div>
              <div style={{ fontSize: 12, color: '#64748b' }}>{t.desc}</div>
            </div>
            <button onClick={() => connect(t.id)} style={{
              padding: '6px 16px', borderRadius: 6, border: 'none', cursor: 'pointer',
              background: connected.includes(t.id) ? '#22c55e' : '#3b82f6', color: '#fff', fontSize: 12, fontWeight: 600,
            }}>
              {connected.includes(t.id) ? '✓ 已接入' : '接入'}
            </button>
          </div>
        ))}
      </div>
      <button onClick={onDone} style={btnPrimary}>下一步 → Agent</button>
    </div>
  );
};

// ── Step 5: Agent Creation ──
const StepAgent: React.FC<{ templates: any[]; onDone: () => void }> = ({ templates, onDone }) => {
  const [selected, setSelected] = useState('');

  const createAgent = async (tplId: string) => {
    await fetch('/api/platform/onboarding/agent/create-from-template', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template_id: tplId, agent_name: tplId }),
    });
    setSelected(tplId);
  };

  return (
    <div>
      <h2 style={{ fontSize: 18, marginBottom: 16 }}>Step 5: 创建第一个 Agent</h2>
      <p style={{ fontSize: 13, color: '#94a3b8', marginBottom: 16 }}>
        选择一个场景模板，系统会自动生成 Agent 配置、绑定工具、设定 KPI。
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: 20 }}>
        {templates.map(t => (
          <div key={t.id} onClick={() => createAgent(t.id)}
            style={{
              padding: 20, borderRadius: 8, cursor: 'pointer', textAlign: 'center',
              background: selected === t.id ? '#1e3a5f' : '#0f172a',
              border: `1px solid ${selected === t.id ? '#3b82f6' : '#1e293b'}`,
            }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>{t.icon}</div>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>{t.name}</div>
            <div style={{ fontSize: 12, color: '#64748b' }}>{t.description}</div>
            {selected === t.id && <div style={{ color: '#22c55e', fontSize: 12, marginTop: 8 }}>✓ 已创建</div>}
          </div>
        ))}
      </div>
      <button onClick={onDone} style={btnPrimary}>下一步 → 就绪检查</button>
    </div>
  );
};

// ── Step 6: Readiness Check ──
const StepChecklist: React.FC<{ readiness: any; onCheck: () => Promise<boolean>; onActivate: () => void }> = ({ readiness, onCheck, onActivate }) => {
  const [checks, setChecks] = useState<any[]>([]);
  const [allReady, setAllReady] = useState(false);

  const runCheck = async () => {
    const result = await onCheck();
    setChecks(readiness?.checks || [
      { name: '模型已配置', passed: false },
      { name: '至少1个工具', passed: false },
      { name: '至少1个Agent', passed: false },
      { name: 'KPI已设定', passed: false },
    ]);
    setAllReady(result);
  };

  useEffect(() => { runCheck(); }, []);

  return (
    <div>
      <h2 style={{ fontSize: 18, marginBottom: 16 }}>Step 6: 部署就绪检查</h2>
      {(checks.length ? checks : [
        { name: '模型已配置', passed: false }, { name: '工具已接入', passed: false },
        { name: 'Agent已创建', passed: false }, { name: 'KPI已设定', passed: false },
      ]).map((c: any, i: number) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 0', borderBottom: '1px solid #1e293b' }}>
          <span>{c.passed ? '✅' : '⬜'}</span>
          <span style={{ fontSize: 14 }}>{c.name}</span>
        </div>
      ))}
      <div style={{ marginTop: 20, display: 'flex', gap: 8 }}>
        <button onClick={runCheck} style={{ ...btnPrimary, background: '#334155' }}>重新检查</button>
        <button onClick={onActivate} disabled={!allReady} style={{ ...btnPrimary, opacity: allReady ? 1 : 0.5 }}>
          {allReady ? '🚀 启动上线' : '请先完成所有检查项'}
        </button>
      </div>
    </div>
  );
};

const pageStyle: React.CSSProperties = { padding: 24, background: '#0f172a', minHeight: '100vh', color: '#e2e8f0' };
const cardStyle: React.CSSProperties = { background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: 24, maxWidth: 720, margin: '0 auto' };
const btnPrimary: React.CSSProperties = { background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 8, padding: '10px 24px', cursor: 'pointer', fontSize: 14, fontWeight: 600 };

export default OnboardingWizard;
