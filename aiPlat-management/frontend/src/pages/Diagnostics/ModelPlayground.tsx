import { useState, useCallback, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Play, Zap, Clock, AlertTriangle, Brain, Copy, Plus, Key, X } from 'lucide-react';
import { Card, CardHeader, CardContent, Button, toast } from '../../components/ui';

interface ModelInfo {
  name: string;
  provider?: string;
  status?: string;
  available?: boolean;
  category?: string;
  strength?: string;
  context?: string;
}

interface ModelConfig {
  name: string;
  api_key?: string;
  api_base?: string;
}

interface CompareResult {
  model: string;
  content?: string;
  latency_ms?: number;
  input_tokens?: number;
  output_tokens?: number;
  error?: string;
  status: string;
}

const COLORS = ['#8b5cf6', '#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#ec4899'];

const ModelPlayground: React.FC = () => {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [modelConfigs, setModelConfigs] = useState<Record<string, ModelConfig>>({});
  const [configTarget, setConfigTarget] = useState<string | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [apiBaseInput, setApiBaseInput] = useState('');
  const [prompt, setPrompt] = useState('');
  const [results, setResults] = useState<CompareResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [showModelPicker, setShowModelPicker] = useState(false);

  useEffect(() => {
    fetch('/api/core/diagnostics/playground/models')
      .then(r => r.json())
      .then(d => setModels(d.models || []))
      .catch(() => {});
  }, []);

  const toggleModel = useCallback((name: string) => {
    setSelectedModels(prev =>
      prev.includes(name) ? prev.filter(m => m !== name) : [...prev, name].slice(0, 6)
    );
  }, []);

  const handleModelClick = useCallback((m: ModelInfo) => {
    if (selectedModels.includes(m.name)) {
      toggleModel(m.name);
      return;
    }
    if (selectedModels.length >= 6) return;
    if (m.available) {
      // Installed model — select directly
      toggleModel(m.name);
    } else {
      // Market model — show config dialog
      setConfigTarget(m.name);
      setApiKeyInput('');
      setApiBaseInput('');
    }
  }, [selectedModels, toggleModel]);

  const confirmConfig = useCallback(() => {
    if (!configTarget || !apiKeyInput.trim()) {
      toast.error('请输入 API Key');
      return;
    }
    setModelConfigs(prev => ({
      ...prev,
      [configTarget]: { name: configTarget, api_key: apiKeyInput.trim(), api_base: apiBaseInput.trim() || undefined },
    }));
    toggleModel(configTarget);
    setConfigTarget(null);
  }, [configTarget, apiKeyInput, apiBaseInput, toggleModel]);

  const removeConfig = useCallback((name: string) => {
    setModelConfigs(prev => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
    toggleModel(name);
  }, [toggleModel]);

  const runCompare = useCallback(async () => {
    if (!prompt.trim()) { toast.error('请输入 Prompt'); return; }
    if (selectedModels.length === 0) { toast.error('请至少选择一个模型'); return; }
    setLoading(true);
    setResults([]);
    try {
      const payload = selectedModels.map(name => ({
        name,
        ...(modelConfigs[name] || {}),
      }));
      const resp = await fetch('/api/core/diagnostics/playground/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: prompt.trim(), models: payload }),
      });
      const data = await resp.json();
      setResults(data.results || []);
    } catch (e: any) {
      toast.error('请求失败: ' + (e?.message || ''));
    } finally {
      setLoading(false);
    }
  }, [prompt, selectedModels, modelConfigs]);

  const copyResult = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success('已复制到剪贴板');
  };

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1400, color: '#e5e7eb', minHeight: '100vh' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <Zap size={24} color="#f59e0b" />
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>模型 Playground</h1>
        <span style={{ fontSize: 11, color: '#6b7280' }}>对比多个 LLM 的输出</span>
      </div>

      <Link to="/diagnostics" className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 transition-colors mb-4">
        <ArrowLeft className="w-3 h-3" />返回诊断中心
      </Link>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16, marginBottom: 20 }}>
        {/* Prompt input */}
        <Card className="border-dark-border bg-dark-card">
          <CardContent>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Brain size={14} color="#8b5cf6" />
                <span style={{ fontSize: 12, fontWeight: 600, color: '#e5e7eb' }}>Prompt</span>
              </div>
              <textarea
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                placeholder="输入你想对比的 prompt..."
                rows={4}
                style={{
                  width: '100%', background: '#111827', border: '1px solid #374151',
                  borderRadius: 8, padding: '10px 14px', color: '#e5e7eb', fontSize: 13,
                  fontFamily: 'monospace', resize: 'vertical',
                }}
              />
            </div>
          </CardContent>
        </Card>

        {/* Model selection + run */}
        <Card className="border-dark-border bg-dark-card">
          <CardContent>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingTop: 12, flexWrap: 'wrap' }}>
              {/* Selected models chips */}
              {selectedModels.map((m, i) => (
                <div key={m} style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  background: `${COLORS[i % COLORS.length]}20`, border: `1px solid ${COLORS[i % COLORS.length]}40`,
                  borderRadius: 20, padding: '4px 12px', fontSize: 12, color: COLORS[i % COLORS.length],
                }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: COLORS[i % COLORS.length] }} />
                  {m}
                  {modelConfigs[m] && <Key size={10} />}
                  <button onClick={() => modelConfigs[m] ? removeConfig(m) : toggleModel(m)} style={{
                    background: 'none', border: 'none', color: COLORS[i % COLORS.length],
                    cursor: 'pointer', fontSize: 14, padding: '0 2px',
                  }}>✕</button>
                </div>
              ))}
              <div style={{ position: 'relative' }}>
                <Button variant="ghost" onClick={() => setShowModelPicker(!showModelPicker)} icon={<Plus size={14} />}>
                    选择模型 ({selectedModels.length}/6)
                </Button>
                {showModelPicker && (
                  <div style={{
                    position: 'absolute', top: '100%', left: 0, zIndex: 50,
                    background: '#1f2937', border: '1px solid #374151', borderRadius: 8,
                    padding: 8, minWidth: 360, maxHeight: 440, overflowY: 'auto',
                    boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
                  }}>
                    {models.length === 0 ? (
                      <div style={{ fontSize: 12, color: '#6b7280', padding: 8 }}>暂无可用模型</div>
                    ) : (
                      <>
                        {/* Installed models section */}
                        <div style={{ fontSize: 10, color: '#6b7280', padding: '4px 8px 2px', fontWeight: 600 }}>
                          📦 已安装 · 可直接使用
                        </div>
                        {models.filter(m => m.available).map(m => {
                          const sel = selectedModels.includes(m.name);
                          return (
                            <div key={m.name}
                              onClick={() => handleModelClick(m)}
                              style={{
                                display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px',
                                borderRadius: 4, cursor: 'pointer', fontSize: 12, color: '#e5e7eb',
                                background: sel ? 'rgba(34,197,94,0.15)' : undefined,
                              }}
                              onMouseEnter={e => { if (!sel) e.currentTarget.style.background = '#374151'; }}
                              onMouseLeave={e => { if (!sel) e.currentTarget.style.background = 'transparent'; }}
                            >
                              <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#22c55e' }} />
                              <span style={{ flex: 1 }}>{m.name}</span>
                              {m.provider && <span style={{ fontSize: 9, color: '#6b7280' }}>{m.provider}</span>}
                              {sel && <span style={{ color: '#22c55e', fontSize: 14 }}>✓</span>}
                            </div>
                          );
                        })}

                        {/* Market catalog section */}
                        <div style={{ fontSize: 10, color: '#6b7280', padding: '8px 8px 2px', fontWeight: 600, marginTop: 4 }}>
                          🏪 市场模型 · 接入后可对比
                        </div>
                        {models.filter(m => !m.available).map(m => {
                          const sel = selectedModels.includes(m.name);
                          const hasConfig = !!modelConfigs[m.name];
                          return (
                            <div key={m.name}
                              onClick={() => handleModelClick(m)}
                              title={m.strength ? `${m.strength}${m.context ? ' · ' + m.context + ' 上下文' : ''}` : ''}
                              style={{
                                display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px',
                                borderRadius: 4, cursor: 'pointer', fontSize: 12, color: sel ? '#e5e7eb' : '#9ca3af',
                                background: sel ? 'rgba(139,92,246,0.15)' : undefined,
                                opacity: sel ? 1 : 0.75,
                              }}
                              onMouseEnter={e => { if (!sel) { e.currentTarget.style.background = '#374151'; e.currentTarget.style.opacity = '1'; } }}
                              onMouseLeave={e => { if (!sel) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.opacity = '0.75'; } }}
                            >
                              <span style={{ color: hasConfig ? '#22c55e' : '#6b7280' }}>{hasConfig ? '🔑' : '＋'}</span>
                              <span style={{ flex: 1 }}>{m.name}</span>
                              {m.provider && <span style={{ fontSize: 9, color: '#6b7280' }}>{m.provider}</span>}
                              {m.context && <span style={{ fontSize: 9, color: '#4b5563' }}>{m.context}</span>}
                              {hasConfig && <span style={{ fontSize: 9, color: '#22c55e' }}>已配置</span>}
                              {sel && <span style={{ color: '#8b5cf6', fontSize: 14 }}>✓</span>}
                            </div>
                          );
                        })}
                      </>
                    )}
                  </div>
                )}
              </div>
              <div style={{ flex: 1 }} />
              <Button variant="primary" onClick={runCompare} loading={loading} icon={<Play size={14} />}>
                运行对比
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Results */}
      {results.length > 0 && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${Math.min(results.length, 3)}, 1fr)`,
          gap: 16,
        }}>
          {results.map((r, i) => {
            const color = COLORS[i % COLORS.length];
            const isError = r.status === 'error';
            return (
              <Card key={r.model} className="border-dark-border bg-dark-card" {...({ style: { borderTop: `3px solid ${isError ? '#ef4444' : color}` } } as any)}>
                <CardHeader>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 10, height: 10, borderRadius: '50%', background: color }} />
                    <span style={{ fontSize: 13, fontWeight: 600, color: '#e5e7eb' }}>{r.model}</span>
                  </div>
                </CardHeader>
                <CardContent>
                  {isError ? (
                    <div style={{ fontSize: 12, color: '#fca5a5', background: '#450a0a', borderRadius: 6, padding: '8px 12px' }}>
                      <AlertTriangle size={12} style={{ display: 'inline', marginRight: 6 }} />
                      {r.error}
                    </div>
                  ) : (
                    <>
                      {/* Metrics */}
                      <div style={{ display: 'flex', gap: 10, marginBottom: 10, fontSize: 11, color: '#9ca3af' }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                          <Clock size={12} /> {r.latency_ms}ms
                        </span>
                        <span>输入: {r.input_tokens}</span>
                        <span>输出: {r.output_tokens}</span>
                      </div>
                      {/* Output */}
                      <div style={{ position: 'relative' }}>
                        <pre style={{
                          fontSize: 11, color: '#e5e7eb', background: '#111827', borderRadius: 6,
                          padding: '10px 12px', maxHeight: 350, overflowY: 'auto',
                          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                          margin: 0,
                        }}>
                          {r.content || '(空输出)'}
                        </pre>
                        {r.content && (
                          <button
                            onClick={() => copyResult(r.content!)}
                            style={{
                              position: 'absolute', top: 8, right: 8,
                              background: '#374151', border: 'none', borderRadius: 4,
                              color: '#9ca3af', cursor: 'pointer', fontSize: 12,
                              padding: '2px 6px',
                            }}
                            title="复制"
                          >
                            <Copy size={12} />
                          </button>
                        )}
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Empty state */}
      {!loading && results.length === 0 && (
        <div style={{
          textAlign: 'center', padding: 60, color: '#6b7280',
          border: '1px dashed #374151', borderRadius: 12, background: '#1f2937',
        }}>
          <Zap size={32} style={{ marginBottom: 12, opacity: 0.2 }} />
          <div style={{ fontSize: 14 }}>输入 Prompt、选择模型、点击"运行对比"</div>
          <div style={{ fontSize: 11, marginTop: 4 }}>最多同时对比 6 个模型</div>
        </div>
      )}
      {/* Config dialog for market models */}
      {configTarget && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.6)', zIndex: 100,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div style={{
            background: '#1f2937', border: '1px solid #374151', borderRadius: 12,
            padding: 24, width: 400, boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#e5e7eb' }}>接入 {configTarget}</div>
                <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                  {models.find(m => m.name === configTarget)?.provider || ''} · 密钥仅用于本次对比，不会保存
                </div>
              </div>
              <button onClick={() => setConfigTarget(null)} style={{
                background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: 18,
              }}><X size={18} /></button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 4 }}>API Key</div>
                <input
                  type="password"
                  value={apiKeyInput}
                  onChange={e => setApiKeyInput(e.target.value)}
                  placeholder="sk-..."
                  autoFocus
                  style={{
                    width: '100%', background: '#111827', border: '1px solid #374151',
                    borderRadius: 6, padding: '8px 12px', color: '#e5e7eb', fontSize: 13,
                    fontFamily: 'monospace',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
              <div>
                <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 4 }}>API Base URL <span style={{ color: '#6b7280' }}>(可选)</span></div>
                <input
                  value={apiBaseInput}
                  onChange={e => setApiBaseInput(e.target.value)}
                  placeholder="默认自动推断"
                  style={{
                    width: '100%', background: '#111827', border: '1px solid #374151',
                    borderRadius: 6, padding: '8px 12px', color: '#e5e7eb', fontSize: 13,
                    fontFamily: 'monospace',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
                <Button variant="ghost" onClick={() => setConfigTarget(null)}>取消</Button>
                <Button variant="primary" onClick={confirmConfig} icon={<Key size={14} />}>接入并选择</Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ModelPlayground;
