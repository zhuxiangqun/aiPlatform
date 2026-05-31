import { useState, useCallback, useEffect } from 'react';
import { Play, Zap, Clock, AlertTriangle, Brain, Copy, RefreshCw, Plus, X } from 'lucide-react';
import { Card, CardHeader, CardContent, Button, Input, toast } from '../../components/ui';

interface ModelInfo {
  name: string;
  provider?: string;
  status?: string;
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

  const runCompare = useCallback(async () => {
    if (!prompt.trim()) { toast.error('请输入 Prompt'); return; }
    if (selectedModels.length === 0) { toast.error('请至少选择一个模型'); return; }
    setLoading(true);
    setResults([]);
    try {
      const resp = await fetch('/api/core/diagnostics/playground/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: prompt.trim(), models: selectedModels }),
      });
      const data = await resp.json();
      setResults(data.results || []);
    } catch (e: any) {
      toast.error('请求失败: ' + (e?.message || ''));
    } finally {
      setLoading(false);
    }
  }, [prompt, selectedModels]);

  const copyResult = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success('已复制到剪贴板');
  };

  const cardStyle: React.CSSProperties = {
    background: '#1f2937', borderRadius: 10, padding: '12px 16px',
    border: '1px solid #374151',
  };

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1400, color: '#e5e7eb', minHeight: '100vh' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <Zap size={24} color="#f59e0b" />
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>模型 Playground</h1>
        <span style={{ fontSize: 11, color: '#6b7280' }}>对比多个 LLM 的输出</span>
      </div>

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
                  <button onClick={() => toggleModel(m)} style={{
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
                    padding: 8, minWidth: 280, maxHeight: 300, overflowY: 'auto',
                    boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
                  }}>
                    {models.length === 0 ? (
                      <div style={{ fontSize: 12, color: '#6b7280', padding: 8 }}>暂无可用模型</div>
                    ) : (
                      models.map(m => {
                        const sel = selectedModels.includes(m.name);
                        return (
                          <div key={m.name}
                            onClick={() => toggleModel(m.name)}
                            style={{
                              display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px',
                              borderRadius: 4, cursor: 'pointer', fontSize: 12, color: '#e5e7eb',
                              background: sel ? 'rgba(139,92,246,0.15)' : undefined,
                            }}
                            onMouseEnter={e => { if (!sel) e.currentTarget.style.background = '#374151'; }}
                            onMouseLeave={e => { if (!sel) e.currentTarget.style.background = 'transparent'; }}
                          >
                            <span style={{ flex: 1 }}>{m.name}</span>
                            {m.provider && <span style={{ fontSize: 10, color: '#6b7280' }}>{m.provider}</span>}
                            {sel && <span style={{ color: '#8b5cf6', fontSize: 14 }}>✓</span>}
                          </div>
                        );
                      })
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
              <Card key={r.model} className="border-dark-border bg-dark-card" style={{
                borderTop: `3px solid ${isError ? '#ef4444' : color}`,
              }}>
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
    </div>
  );
};

export default ModelPlayground;
