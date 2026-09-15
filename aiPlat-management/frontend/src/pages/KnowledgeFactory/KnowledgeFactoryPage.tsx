/**
 * KnowledgeFactoryPage — 知识工厂 (知识生产与本体治理聚合页)
 *
 * 三阶段流水线:
 *   ① 知识抽取 — 文档上传/粘贴 → LLM 实体+关系萃取 → 待审确认
 *   ② 跨域解析 — 跨域同名/近义实体关联消歧
 *   ③ 本体演进 — 版本化 YAML 提案 → 审核 → 应用
 *
 * 此页面聚合了原 FDE 工作台 ① 标签页中的三个面板，
 * 统一归属到侧边栏 知识工厂 组下。
 */
import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import {
  Upload, FileText, ArrowRightLeft, ArrowRight,
  RefreshCw, Brain, GitBranch, XCircle,
} from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

// ═══════════════════════════════════════════════════════════
// ① KnowledgeExtractionPanel — 文件上传 + 文本粘贴双模式
// ═══════════════════════════════════════════════════════════
const KnowledgeExtractionPanel: React.FC = () => {
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  const [pending, setPending] = useState<any[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch(API('/extractions/pending'))
      .then(r => r.json()).then(d => setPending(d.pending || []))
      .catch(() => {});
  }, []);

  const handleExtract = async () => {
    if (!text.trim() && !file) return;
    setLoading(true);
    try {
      const formData = new FormData();
      if (file) {
        formData.append('file', file);
      }
      if (text.trim()) {
        formData.append('text', text);
      }
      formData.append('domain_id', 'fde-delivery');
      formData.append('doc_name', file ? file.name : ('客户文档-' + new Date().toISOString().slice(0, 10)));

      const r = await fetch(API('/extract'), {
        method: 'POST',
        body: formData,
      });
      const d = await r.json();
      setResults(d.extractions || []);
      const newPending = (d.extractions || []).filter((e: any) => e.status === 'pending');
      setPending(prev => [...newPending, ...prev.filter(p => !newPending.find((n: any) => n.extraction_id === p.extraction_id))]);
      if (file) setFile(null);
    } catch { toast?.error?.('抽取失败'); }
    finally { setLoading(false); }
  };

  const handleConfirm = async (id: string) => {
    await fetch(API(`/extractions/${id}/confirm`), { method: 'POST' });
    setPending(prev => prev.filter(p => p.extraction_id !== id));
    toast?.success?.('已确认入库');
  };

  const handleReject = async (id: string) => {
    await fetch(API(`/extractions/${id}/reject`), { method: 'POST' });
    setPending(prev => prev.filter(p => p.extraction_id !== id));
    toast?.info?.('已忽略');
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      setFile(f);
      setText('');
    }
  };

  const removeFile = () => {
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <Card className="border-blue-500/20">
      <CardHeader>
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-blue-500/10 text-blue-400">
            <Brain className="w-5 h-5" />
          </div>
          <div>
            <span className="text-sm font-semibold text-gray-100">① 知识抽取</span>
            <span className="text-[11px] text-gray-500 ml-2">文档 → LLM 实体/关系萃取 → YAML 草稿</span>
          </div>
          {pending.length > 0 && (
            <span className="text-[10px] bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded ml-auto">
              {pending.length} 待确认
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* File upload area */}
        <div
          className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors ${
            file ? 'border-blue-500 bg-blue-500/5' : 'border-gray-700 hover:border-gray-500'
          }`}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.doc,.txt,.md,.pptx,.xlsx,.csv,.html,.json,.xml"
            onChange={handleFileChange}
            className="hidden"
          />
          {file ? (
            <div className="flex items-center justify-center gap-2">
              <FileText className="w-4 h-4 text-blue-400" />
              <span className="text-sm text-blue-300">{file.name}</span>
              <span className="text-[10px] text-gray-500">({(file.size / 1024).toFixed(1)} KB)</span>
              <button
                onClick={(e) => { e.stopPropagation(); removeFile(); }}
                className="text-gray-500 hover:text-red-400 ml-1"
              >
                <XCircle className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="text-gray-500">
              <Upload className="w-5 h-5 mx-auto mb-1" />
              <span className="text-xs">拖拽文件至此，或点击上传 (PDF/Word/Markdown/Excel 等)</span>
            </div>
          )}
        </div>

        {/* Text paste area */}
        <div className="relative">
          <div className="text-[10px] text-gray-500 mb-1">或直接粘贴文本内容</div>
          <textarea
            className="w-full h-28 bg-gray-800 border border-gray-700 rounded p-2.5 text-xs text-gray-200 resize-y"
            placeholder="粘贴产品手册、项目报告、流程文档..."
            value={text}
            onChange={e => setText(e.target.value)}
          />
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="default"
            size="sm"
            loading={loading}
            onClick={handleExtract}
            disabled={!text.trim() && !file}
          >
            {file ? `上传并抽取 "${file.name.slice(0, 20)}"` : '抽取'}
          </Button>
          {results.length > 0 && (
            <span className="text-xs text-green-400">
              {results.reduce((s: number, r: any) => s + r.entity_count, 0)} 实体,{' '}
              {results.reduce((s: number, r: any) => s + r.relation_count, 0)} 关系
            </span>
          )}
        </div>

        {/* Pending confirmations */}
        {pending.length > 0 && (
          <div className="space-y-2 pt-2 border-t border-gray-700/50">
            <div className="text-xs text-gray-500">
              待确认萃取 ({pending.length})
              <span className="text-[10px] text-gray-600 ml-1">— 置信度 60%-85%，需人工审核</span>
            </div>
            {pending.map((p: any) => (
              <div key={p.extraction_id} className="p-2.5 rounded bg-gray-800/50 border border-yellow-700/30">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-xs text-gray-200">{p.source_doc}</span>
                    <span className="text-[10px] text-gray-500 ml-2">
                      {(p.overall_confidence * 100).toFixed(0)}% · {p.entity_count}实体 · {p.relation_count}关系
                    </span>
                  </div>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-green-400 text-[10px] py-0 h-6"
                      onClick={() => handleConfirm(p.extraction_id)}
                    >
                      确认
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-red-400 text-[10px] py-0 h-6"
                      onClick={() => handleReject(p.extraction_id)}
                    >
                      忽略
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// ═══════════════════════════════════════════════════════════
// ② CrossDomainResolutionPanel — 跨域实体解析
// ═══════════════════════════════════════════════════════════
const CrossDomainResolutionPanel: React.FC = () => {
  const [candidates, setCandidates] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [viewName, setViewName] = useState('unified_customer');

  const VIEWS = [
    { key: 'unified_customer', label: '锁安↔FDE' },
    { key: 'bell_unified_client', label: 'Bell24统一客户' },
    { key: 'bell_unified_technology', label: 'Bell24技术资产' },
    { key: 'bell_group_structure', label: 'Bell24集团架构' },
  ];

  useEffect(() => {
    setLoading(true);
    fetch(API(`/resolution/candidates?view_name=${viewName}`))
      .then(r => r.json()).then(d => setCandidates(d.candidates || []))
      .catch(() => setCandidates([]))
      .finally(() => setLoading(false));
  }, [viewName]);

  const handleResolve = async (c: any) => {
    setLoading(true);
    try {
      await fetch(API('/resolution/resolve'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          view_name: viewName,
          left_id: c.left.id, left_domain: c.left.domain,
          right_id: c.right.id, right_domain: c.right.domain, confidence: c.score,
        }),
      });
      setCandidates(prev => prev.filter(x => x !== c));
      toast?.success?.('已关联');
    } catch { toast?.error?.('关联失败'); }
    finally { setLoading(false); }
  };

  return (
    <Card className="border-purple-500/20">
      <CardHeader>
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-purple-500/10 text-purple-400">
            <ArrowRightLeft className="w-5 h-5" />
          </div>
          <div>
            <span className="text-sm font-semibold text-gray-100">② 跨域解析</span>
            <span className="text-[11px] text-gray-500 ml-2">跨域实体匹配 — 精确键 / Jaro-Winkler / Embedding 余弦</span>
          </div>
          <div className="flex items-center gap-1 ml-auto">
            <select
              value={viewName}
              className="text-[10px] bg-gray-800 border border-gray-700 text-gray-400 rounded px-2 py-1"
              onChange={e => setViewName(e.target.value)}
            >
              {VIEWS.map(v => (
                <option key={v.key} value={v.key}>{v.label}</option>
              ))}
            </select>
            {candidates.length > 0 && (
              <span className="text-[10px] bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded">
                {candidates.length} 候选
              </span>
            )}
            {loading && <span className="text-[10px] text-gray-500 animate-pulse ml-1">加载中...</span>}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {candidates.length === 0 ? (
          <div className="text-xs text-gray-600 text-center py-4">
            暂无跨域候选 — 抽取更多实体后自动匹配
          </div>
        ) : (
          <div className="space-y-2">
            {candidates.slice(0, 10).map((c, i) => (
              <div key={i} className="p-2.5 rounded bg-gray-800/50 border border-gray-700/30">
                <div className="flex items-center justify-between mb-1">
                  <div className="text-xs">
                    <span className="text-gray-200">{c.left.name}</span>
                    <span className="text-gray-600 mx-1.5">↔</span>
                    <span className="text-gray-200">{c.right.name}</span>
                  </div>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded ${
                      c.score >= 0.85 ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'
                    }`}
                  >
                    {(c.score * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="text-[10px] text-gray-500 mb-1.5">
                  {c.left.domain} ↔ {c.right.domain} · {c.strategy}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-purple-400 text-[10px] py-0 h-5"
                  loading={loading}
                  onClick={() => handleResolve(c)}
                >
                  关联
                </Button>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// ═══════════════════════════════════════════════════════════
// ③ OntologyEvolutionPanel — 版本化本体治理
// ═══════════════════════════════════════════════════════════
const OntologyEvolutionPanel: React.FC = () => {
  const [proposals, setProposals] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch(API('/ontology/proposals?domain_id=fde-delivery'))
      .then(r => r.json()).then(d => setProposals(d.proposals || []))
      .catch(() => {});
  }, []);

  const handleApply = async (id: string) => {
    setLoading(true);
    try {
      await fetch(API(`/ontology/proposals/${id}/apply`), { method: 'POST' });
      setProposals(prev => prev.map(p => p.proposal_id === id ? { ...p, status: 'applied' } : p));
      toast?.success?.('提案已应用');
    } catch { toast?.error?.('应用失败'); }
    finally { setLoading(false); }
  };

  const statusLabel = (s: string) => {
    const m: Record<string, string> = {
      draft: '草稿', submitted: '已提交', approved: '已批准',
      applied: '已应用', rejected: '已驳回',
    };
    return m[s] || s;
  };

  const statusColorClass = (s: string) => {
    const m: Record<string, string> = {
      approved: 'bg-green-500/20 text-green-400',
      submitted: 'bg-yellow-500/20 text-yellow-400',
      applied: 'bg-blue-500/20 text-blue-400',
      draft: 'bg-gray-500/20 text-gray-400',
      rejected: 'bg-red-500/20 text-red-400',
    };
    return m[s] || 'bg-gray-500/20 text-gray-400';
  };

  return (
    <Card className="border-green-500/20">
      <CardHeader>
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-green-500/10 text-green-400">
            <GitBranch className="w-5 h-5" />
          </div>
          <div>
            <span className="text-sm font-semibold text-gray-100">③ 本体演进</span>
            <span className="text-[11px] text-gray-500 ml-2">版本化 YAML 提案 → 审核 → 应用</span>
          </div>
          {proposals.filter(p => p.status === 'approved').length > 0 && (
            <span className="text-[10px] bg-green-500/20 text-green-400 px-2 py-0.5 rounded ml-auto">
              {proposals.filter(p => p.status === 'approved').length} 待应用
            </span>
          )}
          <Button variant="ghost" size="sm" onClick={() => {
            fetch(API('/ontology/proposals?domain_id=fde-delivery'))
              .then(r => r.json()).then(d => setProposals(d.proposals || []));
          }}>
            <RefreshCw className="w-3 h-3" />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {proposals.length === 0 ? (
          <div className="text-xs text-gray-600 text-center py-4">
            暂无本体演进提案 — 抽取并确认实体后将自动生成
          </div>
        ) : (
          <div className="space-y-2">
            {proposals.map(p => (
              <div key={p.proposal_id} className="p-2.5 rounded bg-gray-800/50 border border-gray-700/30">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-200">
                    {p.domain_id} v{p.version_from} → v{p.version_to}
                  </span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${statusColorClass(p.status)}`}>
                    {statusLabel(p.status)}
                  </span>
                </div>
                <div className="text-[10px] text-gray-500">
                  作者: {p.author} · 影响: {p.impact_analysis || '-'}
                </div>
                {p.status === 'approved' && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-blue-400 text-[10px] py-0 h-5 mt-1"
                    loading={loading}
                    onClick={() => handleApply(p.proposal_id)}
                  >
                    应用
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// ═══════════════════════════════════════════════════════════
// KnowledgeFactoryPage — 主页面
// ═══════════════════════════════════════════════════════════
const KnowledgeFactoryPage: React.FC = () => {
  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100">知识工厂</h1>
          <p className="text-sm text-gray-500 mt-1">
            知识生产流水线：文档上传 → 实体/关系萃取 → 跨域对齐 → 本体演进 → 入库
          </p>
        </div>
      </div>

      {/* Pipeline flow indicator */}
      <div className="flex items-center gap-0 text-xs text-gray-600">
        <span className="text-blue-400 font-medium">① 知识抽取</span>
        <ArrowRight className="w-4 h-4 mx-1" />
        <span className="text-purple-400 font-medium">② 跨域解析</span>
        <ArrowRight className="w-4 h-4 mx-1" />
        <span className="text-green-400 font-medium">③ 本体演进</span>
        <span className="ml-3 text-gray-600">→ 入库到各域本体模型</span>
      </div>

      {/* Stage 1: Knowledge Extraction */}
      <KnowledgeExtractionPanel />

      {/* Stage 2: Cross-Domain Resolution */}
      <CrossDomainResolutionPanel />

      {/* Stage 3: Ontology Evolution */}
      <OntologyEvolutionPanel />

      {/* Quick links to downstream tools */}
      <Card className="border-gray-700/50">
        <CardHeader>
          <span className="text-sm font-semibold text-gray-200">下游入口</span>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <a
              href="/platform/kb/vault"
              className="p-3 rounded bg-gray-800/50 border border-gray-700/30 hover:border-gray-500 transition-colors text-xs"
            >
              <div className="text-gray-200 font-medium">Vault 文档库</div>
              <div className="text-gray-500 mt-0.5">管理原始文档和资料</div>
            </a>
            <a
              href="/infra/ontology"
              className="p-3 rounded bg-gray-800/50 border border-gray-700/30 hover:border-gray-500 transition-colors text-xs"
            >
              <div className="text-gray-200 font-medium">域本体管理</div>
              <div className="text-gray-500 mt-0.5">创建/编辑本体类与属性</div>
            </a>
            <a
              href="/platform/kb"
              className="p-3 rounded bg-gray-800/50 border border-gray-700/30 hover:border-gray-500 transition-colors text-xs"
            >
              <div className="text-gray-200 font-medium">向量知识库</div>
              <div className="text-gray-500 mt-0.5">检索已入库的知识</div>
            </a>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default KnowledgeFactoryPage;
