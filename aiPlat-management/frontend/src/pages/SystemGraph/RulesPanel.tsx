import React, { useEffect, useState } from 'react';
import { BookOpen, Send, Plus, Trash2, AlertTriangle, CheckCircle } from 'lucide-react';

interface Rule {
  name: string;
  description: string;
  premises_count: number;
  conclusion: string;
}

interface DesignResult {
  rule: any;
  validation: { valid: boolean; errors: string[]; warnings: string[] };
  existing_related: { name: string; description: string }[];
  domain: string;
  error?: string;
}

const DOMAINS = ['ai-knowledge', 'ship-design', 'it-ops', 'default'];

const RulesPanel: React.FC = () => {
  const [domain, setDomain] = useState('ai-knowledge');
  const [rules, setRules] = useState<Rule[]>([]);
  const [nlText, setNlText] = useState('');
  const [loading, setLoading] = useState(false);
  const [designResult, setDesignResult] = useState<DesignResult | null>(null);
  const [deployMsg, setDeployMsg] = useState('');
  const [deployError, setDeployError] = useState('');

  // Load rules for domain
  const loadRules = async (d: string) => {
    try {
      const r = await fetch(`/api/core/knowledge-graph/rules?domain_id=${d}`);
      const data = await r.json();
      setRules(data.rules || []);
    } catch { setRules([]); }
  };

  useEffect(() => { loadRules(domain); }, [domain]);

  // Design: NL → Rule
  const handleDesign = async () => {
    if (!nlText.trim()) return;
    setLoading(true);
    setDesignResult(null);
    setDeployMsg('');
    setDeployError('');
    try {
      const r = await fetch('/api/core/knowledge-graph/rules/design', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain_id: domain, text: nlText }),
      });
      const data = await r.json();
      setDesignResult(data);
    } catch (e: any) {
      setDesignResult({ rule: null, validation: { valid: false, errors: [e.message], warnings: [] }, existing_related: [], domain, error: e.message });
    } finally {
      setLoading(false);
    }
  };

  // Deploy rule
  const handleDeploy = async () => {
    if (!designResult?.rule) return;
    setLoading(true);
    setDeployMsg('');
    setDeployError('');
    try {
      const r = await fetch('/api/core/knowledge-graph/rules/deploy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain_id: domain, rule: designResult.rule }),
      });
      const data = await r.json();
      if (data.deployed) {
        setDeployMsg(`✅ 规则 "${data.rule_name}" 已部署 (共 ${data.total_rules} 条规则)`);
        loadRules(domain);
      } else {
        setDeployError(data.error || 'Deploy failed');
      }
    } catch (e: any) {
      setDeployError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '16px', maxWidth: '800px', margin: '0 auto' }}>
      {/* Domain selector */}
      <div style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <label style={{ fontWeight: 600, fontSize: '14px' }}>域:</label>
        <select
          value={domain}
          onChange={(e) => { setDomain(e.target.value); setDesignResult(null); }}
          style={{ padding: '6px 12px', borderRadius: '6px', border: '1px solid #d1d5db', fontSize: '14px' }}
        >
          {DOMAINS.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
        <span style={{ color: '#6b7280', fontSize: '12px' }}>{rules.length} 条规则</span>
      </div>

      {/* Existing rules */}
      {rules.length > 0 && (
        <div style={{ marginBottom: '20px' }}>
          <h4 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>已有规则</h4>
          <div style={{ maxHeight: '200px', overflowY: 'auto', border: '1px solid #e5e7eb', borderRadius: '8px' }}>
            {rules.map((r) => (
              <div key={r.name} style={{ padding: '8px 12px', borderBottom: '1px solid #f3f4f6', fontSize: '13px' }}>
                <span style={{ fontWeight: 600 }}>{r.name}</span>
                <span style={{ color: '#6b7280', marginLeft: '8px' }}>{r.description}</span>
                <span style={{ float: 'right', color: '#9ca3af', fontSize: '11px' }}>
                  → {r.conclusion} ({r.premises_count} premises)
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* NL Input */}
      <div style={{ marginBottom: '12px' }}>
        <label style={{ fontWeight: 600, fontSize: '14px', display: 'block', marginBottom: '6px' }}>
          <BookOpen size={14} style={{ display: 'inline', marginRight: '4px' }} />
          用自然语言描述业务规则
        </label>
        <textarea
          value={nlText}
          onChange={(e) => setNlText(e.target.value)}
          placeholder="例如：当一个AI方法被某个系统实现时，两者应该关联起来。或者：客户合同金额超过100万时标记为高价值。"
          rows={3}
          style={{
            width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #d1d5db',
            fontSize: '14px', resize: 'vertical', fontFamily: 'inherit',
          }}
          disabled={loading}
        />
      </div>

      {/* Design button */}
      <button
        onClick={handleDesign}
        disabled={loading || !nlText.trim()}
        style={{
          padding: '8px 20px', borderRadius: '8px', border: 'none', cursor: loading ? 'not-allowed' : 'pointer',
          background: loading ? '#9ca3af' : '#6366f1', color: '#fff', fontSize: '14px', fontWeight: 600,
          display: 'inline-flex', alignItems: 'center', gap: '6px', marginRight: '8px',
        }}
      >
        <Send size={14} /> {loading ? '生成中...' : 'AI 生成规则'}
      </button>

      {/* Design result */}
      {designResult && (
        <div style={{ marginTop: '16px', border: '1px solid #e5e7eb', borderRadius: '12px', padding: '16px', background: '#f9fafb' }}>
          {designResult.error && (
            <div style={{ color: '#ef4444', padding: '8px', background: '#fef2f2', borderRadius: '6px', marginBottom: '8px' }}>
              <AlertTriangle size={14} style={{ display: 'inline', marginRight: '4px' }} />
              {designResult.error}
            </div>
          )}

          {/* Validation */}
          {designResult.validation && (
            <div style={{ marginBottom: '12px' }}>
              {designResult.validation.valid ? (
                <span style={{ color: '#059669', fontWeight: 600 }}>
                  <CheckCircle size={14} style={{ display: 'inline', marginRight: '4px' }} /> 规则有效
                </span>
              ) : (
                <span style={{ color: '#ef4444', fontWeight: 600 }}>
                  <AlertTriangle size={14} style={{ display: 'inline', marginRight: '4px' }} /> 规则需修正
                </span>
              )}
              {designResult.validation.errors.map((e: string, i: number) => (
                <div key={i} style={{ color: '#ef4444', fontSize: '12px', marginTop: '2px' }}>❌ {e}</div>
              ))}
              {designResult.validation.warnings.map((w: string, i: number) => (
                <div key={i} style={{ color: '#d97706', fontSize: '12px', marginTop: '2px' }}>⚠️ {w}</div>
              ))}
            </div>
          )}

          {/* Related rules */}
          {designResult.existing_related && designResult.existing_related.length > 0 && (
            <div style={{ marginBottom: '8px', fontSize: '12px', color: '#6b7280' }}>
              相关已有规则: {designResult.existing_related.map((r: any) => r.name).join(', ')}
            </div>
          )}

          {/* Generated rule preview */}
          {designResult.rule && (
            <div style={{ marginBottom: '12px' }}>
              <h5 style={{ fontSize: '13px', fontWeight: 600, marginBottom: '4px' }}>生成的规则:</h5>
              <pre style={{
                background: '#1f2937', color: '#e5e7eb', padding: '12px', borderRadius: '8px',
                fontSize: '12px', overflow: 'auto', maxHeight: '200px',
              }}>
                {JSON.stringify(designResult.rule, null, 2)}
              </pre>
            </div>
          )}

          {/* Deploy button */}
          {designResult.rule && designResult.validation.valid && (
            <button
              onClick={handleDeploy}
              disabled={loading}
              style={{
                padding: '8px 16px', borderRadius: '8px', border: 'none', cursor: loading ? 'not-allowed' : 'pointer',
                background: loading ? '#9ca3af' : '#059669', color: '#fff', fontSize: '13px', fontWeight: 600,
                display: 'inline-flex', alignItems: 'center', gap: '6px',
              }}
            >
              <Plus size={14} /> 部署到 {domain}
            </button>
          )}

          {deployMsg && <div style={{ marginTop: '8px', color: '#059669', fontSize: '13px', fontWeight: 600 }}>{deployMsg}</div>}
          {deployError && <div style={{ marginTop: '8px', color: '#ef4444', fontSize: '13px' }}>{deployError}</div>}
        </div>
      )}
    </div>
  );
};

export default RulesPanel;
