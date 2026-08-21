import React, { useEffect, useState } from 'react';
import { Plus, Trash2, RefreshCw, Eye, EyeOff, ArrowRight, Search } from 'lucide-react';
import { Button, Modal, toast, Input } from '../../../components/ui';
import OntologyGraph from '../../../components/wiki/OntologyGraph';
import WikiHealthDashboard from '../../../components/wiki/WikiHealthDashboard';
import GrillPanel from '../../../components/grilling/GrillPanel';
import OntologyLearningPanel from '../../../components/ontology/OntologyLearningPanel';

const WIKI_API = '/api/core';

// ── Inline: Graph Stats + Inference Button ──
const GraphStats: React.FC<{ domainId: string }> = React.memo(({ domainId }) => {
  const [stats, setStats] = useState<{nodes:number,edges:number,inferred:number,rules?:Record<string,number>}|null>(null);
  const [inferring, setInferring] = useState(false);
  useEffect(() => {
    fetch(`${WIKI_API}/engine/graph-stats/${domainId}`).then(r => r.json()).then(d => {
      if (d.node_count > 0) setStats(s => ({ ...s, nodes: d.node_count, edges: d.edge_count, inferred: d.inferred_edges || 0 }));
    }).catch(() => {});
  }, [domainId]);
  return (
    <div className="flex items-center gap-2">
      {stats ? (
        <span>{stats.nodes}节点 {stats.edges}边{stats.inferred > 0 ? ` +${stats.inferred}推断` : ''}</span>
      ) : (
        <span className="text-gray-600">(运行引擎后构建)</span>
      )}
      <Button variant="ghost" size="sm" loading={inferring}
        onClick={async () => {
          setInferring(true);
          try {
            const r = await fetch(`${WIKI_API}/engine/infer`, {
              method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ domain_id: domainId }),
            });
            const d = await r.json();
            setStats({ nodes: d.stats?.node_count || 0, edges: (d.stats?.node_count||0)>0 ? d.applied : 0, inferred: d.applied || 0, rules: d.rule_hits || {} });
            if (d.applied > 0) {
              const rules = Object.entries(d.rule_hits || {}).filter(([,c]:any) => c > 0).map(([n,c]) => `${n}:${c}`).join(', ');
              toast.success(`推理完成：${d.applied} 条推断边 (${rules})`);
            } else toast.info('未发现可推断的新关系');
          } catch { toast.error('推理失败'); }
          finally { setInferring(false); }
        }}>
        🧠 推理
      </Button>
      <Button variant="ghost" size="sm"
        onClick={async () => {
          try {
            const r = await fetch(`${WIKI_API}/engine/synthesize`, {
              method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ domain_id: domainId }),
            });
            const d = await r.json();
            if (d.pages_written > 0) {
              const types = [];
              if (d.chains?.length > 0) types.push(`${d.chains.length}推理链`);
              if (d.fact_cards?.length > 0) types.push(`${d.fact_cards.length}事实卡`);
              if (d.conclusions?.length > 0) types.push(`${d.conclusions.length}综合结论`);
              toast.success(`合成完成：写入 ${d.pages_written} 个Wiki页面 (${types.join(', ')})`);
            } else toast.info('无可合成的新知识');
          } catch { toast.error('合成失败'); }
        }}>
        🧬 合成
      </Button>
      <Button variant="ghost" size="sm"
        onClick={async () => {
          try {
            const sample = ['什么是RAG','RAG怎么用','GraphRAG区别','工作记忆','语义检索','客服自动化','RAG原理','知识图谱为什么重要'];
            const r = await fetch(`${WIKI_API}/engine/detect-gaps`, {
              method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ domain_id: domainId, queries: sample }),
            });
            const d = await r.json();
            const types = d.summary?.by_type || {};
            const typeStr = Object.entries(types).map(([k,v]) => `${k}:${v}`).join(', ');
            if (d.gaps?.length > 0) {
              toast.success(`检测到 ${d.gaps.length} 个知识缺口 (${typeStr})`);
            } else toast.info('未检测到知识缺口');
          } catch { toast.error('检测失败'); }
        }}>
        🔍 缺口
      </Button>
      <Button variant="ghost" size="sm"
        onClick={async () => {
          try {
            const r = await fetch(`${WIKI_API}/engine/recommend/${domainId}?department=研发部&queries=RAG,知识检索`);
            const d = await r.json();
            if (d.recommendations?.length > 0) {
              const high = d.recommendations.filter((r:any) => r.priority === 'high').length;
              toast.success(`推荐 ${d.total} 条知识 (${high}条高优先级)`);
            } else toast.info('暂无推荐');
          } catch { toast.error('推荐失败'); }
        }}>
        📢 推荐
      </Button>
    </div>
  );
});

// ── AIP Assist Panel ──
const AIPAssist: React.FC<{ domainId: string }> = React.memo(({ domainId }) => {
  const [insights, setInsights] = useState<{gaps:number, reviews:number, velocity:string, suggestion:string}|null>(null);
  useEffect(() => {
    Promise.all([
      fetch(`${WIKI_API}/engine/graph-stats/${domainId}`).then(r=>r.json()).catch(()=>({})),
      fetch(`${WIKI_API}/engine/reviews/${domainId}`).then(r=>r.json()).catch(()=>({})),
      fetch(`${WIKI_API}/engine/state-history/${domainId}?limit=5`).then(r=>r.json()).catch(()=>({})),
    ]).then(([stats, reviews, hist]) => {
      const pending = (reviews.reviews || []).filter((r:any) => r.status === 'pending').length;
      const total = (hist.history || []).length;
      const velocity = total > 0 && (hist.history||[])[0]?.timestamp
        ? `${total} 次转换`
        : '无数据';
      // Simple suggestion logic
      const nodes = stats.node_count || 0;
      let suggestion = '';
      if (nodes === 0) suggestion = '上传文档或连接数据源以开始构建知识图谱';
      else if (pending > 0) suggestion = `${pending} 条待复查，建议优先处理`;
      else if (stats.inferred_edges > 0) suggestion = '推理边已生成，运行知识合成生成Wiki页';
      else suggestion = '运行引擎处理文档开始知识构建';
      setInsights({ gaps: 0, reviews: pending, velocity, suggestion });
    }).catch(()=>{});
  }, [domainId]);
  if (!insights) return null;
  return (
    <div className="bg-dark-card rounded-lg border border-dark-border p-4 space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-gray-200">🤖 AIP Assist</span>
        <span className="text-[10px] text-gray-500">智能辅助</span>
      </div>
       <div className="grid grid-cols-3 gap-2 text-xs">
         <div className="p-2 rounded bg-dark-bg border border-dark-border/30" title="待审查的关联实体变更提醒数量">
           <div className="text-gray-500">复查</div>
           <div className="text-gray-200 font-medium">{insights.reviews} 条待处理</div>
         </div>
         <div className="p-2 rounded bg-dark-bg border border-dark-border/30" title="状态机驱动的实体状态转换总次数">
           <div className="text-gray-500">状态</div>
           <div className="text-gray-200 font-medium">{insights.velocity}</div>
         </div>
         <div className="p-2 rounded bg-dark-bg border border-dark-border/30" title="基于当前本体状态的智能操作建议">
           <div className="text-gray-500">建议</div>
           <div className="text-gray-200 font-medium text-[10px]">{insights.suggestion}</div>
        </div>
      </div>
    </div>
  );
});

interface Domain {
  id: string; name: string; version: string; description: string;
  class_count: number; property_count: number;
  min_wiki_score: number; expand_subclasses: boolean; min_cross_results: number;
  system_prompt_id: string; collection_id: string;
}
interface OntoClass {
  uri?: string; label: string; required_fields: string[];
  optional_fields: string[]; categories: string[];
  states?: any; transitions?: any[]; side_effects?: any[];
  description?: string;
}

const OntologyManager: React.FC = () => {
  const [domains, setDomains] = useState<Domain[]>([]);
  const [selectedDomain, setSelectedDomain] = useState<string>('');
  const [domainClasses, setDomainClasses] = useState<OntoClass[]>([]);
  const [domainProps, setDomainProps] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showGraph, setShowGraph] = useState(false);
  const [graphData, setGraphData] = useState<any>(null);
  const [scoringOpen, setScoringOpen] = useState(false);
  const [scoringWeights, setScoringWeights] = useState({ semantic: 0.55, fts_keyword: 0.15, freshness: 0.10, credibility: 0.10, density: 0.10 });
  const [scoringSaving, setScoringSaving] = useState(false);

  const fetchScoringWeights = async () => {
    try {
      const r = await fetch(`${WIKI_API}/domains/${selectedDomain}/scoring`);
      if (!r.ok) return;
      const d = await r.json();
      if (d.semantic !== undefined) setScoringWeights(d);
    } catch {}
  };
  // ── Create domain ──
  const [createOpen, setCreateOpen] = useState(false);
  const [showWizard, setShowWizard] = useState(false);
  const [domainStats, setDomainStats] = useState<Record<string, any>>({});
  const [newId, setNewId] = useState('');
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');

  // ── Add class ──
  const [classOpen, setClassOpen] = useState(false);
  const [editingClass, setEditingClass] = useState<string | null>(null);
  const [clsName, setClsName] = useState('');
  const [clsLabel, setClsLabel] = useState('');
  const [clsReq, setClsReq] = useState('');
  const [clsOpt, setClsOpt] = useState('');
  const [clsCat, setClsCat] = useState('');

  // ── Add property ──
  const [propOpen, setPropOpen] = useState(false);
  const [editingProp, setEditingProp] = useState<string | null>(null);
  const [propName, setPropName] = useState('');
  const [propLabel, setPropLabel] = useState('');
  const [propDomain, setPropDomain] = useState('');
  const [propRange, setPropRange] = useState('');

  // ── Edit domain ──
  const [domainEditOpen, setDomainEditOpen] = useState(false);
  const [editDomainName, setEditDomainName] = useState('');
  const [editDomainDesc, setEditDomainDesc] = useState('');

  // ── Smart Generate ──
  const [genOpen, setGenOpen] = useState(false);
  const [wikiGenOpen, setWikiGenOpen] = useState(false);
  const [wikiGenCollection, setWikiGenCollection] = useState('system_docs');
  const [wikiGenDomainId, setWikiGenDomainId] = useState('');
  const [wikiGenLoading, setWikiGenLoading] = useState(false);
  const [genId, setGenId] = useState('');
  const [genName, setGenName] = useState('');
  const [genDesc, setGenDesc] = useState('');
  const [genLimit, setGenLimit] = useState(20);
  const [genSubdir, setGenSubdir] = useState('');
  const [genKeywords, setGenKeywords] = useState('');
  const [genLoading, setGenLoading] = useState(false);
  const [genResult, setGenResult] = useState<any>(null);
  const [genYamlEdit, setGenYamlEdit] = useState('');

  // ── Vault directory tree for subdirectory selection ──
  const [vaultDirs, setVaultDirs] = useState<string[]>([]);
  const fetchVaultDirs = async () => {
    try {
      const r = await fetch('/api/platform/kb/vault/list');
      const d = await r.json();
      const vaults = d.vaults || [];
      if (vaults.length > 0) {
        const vp = vaults[0].vault_id;
        const tr = await fetch(`/api/platform/kb/vault/${vp}/tree?max_depth=4`);
        const td = await tr.json();
        const dirs: string[] = [];
        const walk = (items: any[], prefix = '') => {
          for (const item of items || []) {
            if (item.type === 'directory') {
              const p = prefix ? `${prefix}/${item.name}` : item.name;
              dirs.push(p);
              if (item.children) walk(item.children, p);
            }
          }
        };
        walk(td.entries || []);
        setVaultDirs(dirs.sort());
      }
    } catch {}
  };

  // ── Propagation Simulation ──
  const [simFocus, setSimFocus] = useState('');
  const [simCounts, setSimCounts] = useState<Record<string, number>>({});
  const [simResult, setSimResult] = useState<any>(null);
  const [simLoading, setSimLoading] = useState(false);

  // ── Review Queue ──
  const [reviews, setReviews] = useState<any[]>([]);
  const [reviewLoading, setReviewLoading] = useState(false);

  // ── State History ──
  const [stateHistory, setStateHistory] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // ── Validation Report ──
  const [validationReport, setValidationReport] = useState<any>(null);
  const [validating, setValidating] = useState(false);

  // ── Evolve ──
  const [evolveOpen, setEvolveOpen] = useState(false);
  const [evolveData, setEvolveData] = useState<any>(null);
  const [evolveLoading, setEvolveLoading] = useState(false);
  const [evolveChecked, setEvolveChecked] = useState<Record<number, boolean>>({});

  // ── Repair ──
  const [repairOpen, setRepairOpen] = useState(false);
  const [repairData, setRepairData] = useState<any>(null);
  const [repairLoading, setRepairLoading] = useState(false);
  const [repairChecked, setRepairChecked] = useState<Record<string, boolean>>({});

  // ── View Instances ──
  const [instancesOpen, setInstancesOpen] = useState(false);
  const [instanceData, setInstanceData] = useState<any>(null);
  const [instanceClassLabel, setInstanceClassLabel] = useState('');

  const fetchInstances = async (classLabel: string) => {
    setInstanceClassLabel(classLabel);
    try {
      const r = await fetch(`${WIKI_API}/domains/${selectedDomain}/instances?class_label=${encodeURIComponent(classLabel)}`);
      setInstanceData(await r.json());
      setInstancesOpen(true);
    } catch { toast.error('获取实例失败'); }
  };

  const fetchValidation = async (domainId: string) => {
    setValidating(true);
    try {
      const r = await fetch(`${WIKI_API}/domains/${domainId}/verify`, { method: 'POST' });
      setValidationReport(await r.json());
    } catch { toast.error('验证报告获取失败'); }
    finally { setValidating(false); }
  };

  const openEditClass = (cls: any) => {
    const clsName = (cls.uri || '').includes('/')
      ? (cls.uri || '').split('/').pop() || cls.label
      : (cls.uri || '').split('#').pop() || cls.label;
    setEditingClass(clsName);
    setClsName(clsName);
    setClsLabel(cls.label);
    setClsReq(cls.required_fields?.join(', ') || '');
    setClsOpt(cls.optional_fields?.join(', ') || '');
    setClsCat(cls.categories?.join(', ') || '');
    setClassOpen(true);
  };

  const handleDeleteClass = async (cls: any) => {
    const clsName = (cls.uri || '').includes('/')
      ? (cls.uri || '').split('/').pop() || cls.label
      : (cls.uri || '').split('#').pop() || cls.label;
    const checkResp = await fetch(`${WIKI_API}/domains/${selectedDomain}/classes/${encodeURIComponent(clsName)}`, { method: 'DELETE' });
    const checkData = await checkResp.json();
    if (checkData.status === 'confirm_required') {
      const msg = `删除类 "${checkData.label}"？\n\n将级联删除 ${checkData.orphan_nodes} 个图节点。`;
      if (!confirm(msg)) return;
      await fetch(`${WIKI_API}/domains/${selectedDomain}/classes/${encodeURIComponent(clsName)}?force=true`, { method: 'DELETE' });
    }
    fetchDomainDetail(selectedDomain); toast.success('已删除');
  };

  const fetchDomains = async (retry = 0) => {
    try {
      const r = await fetch(`${WIKI_API}/domains`);
      if (!r.ok) throw new Error('Server error');
      const d = await r.json();
      setDomains(d.domains || []);
    } catch {
      if (retry < 2) { setTimeout(() => fetchDomains(retry + 1), 2000); }
      else if (retry === 1) { toast.error('域加载失败，服务器可能正忙 (LLM调用中)'); }
    }
  };

  const handleWikiGenDomain = async () => {
    setWikiGenLoading(true);
    try {
      const r = await fetch(`/api/core/wiki/generate-domain?collection=${wikiGenCollection}&domain_id=${wikiGenDomainId}`, { method: 'POST' });
      const d = await r.json();
      if (d.status === 'ok') {
        toast.success(`领域已生成：${d.classes} 个类，${d.entities} 个实体`);
        setWikiGenOpen(false);
        fetchDomains();
      } else {
        toast.error(d.message || '生成失败');
      }
    } catch { toast.error('生成领域失败'); }
    finally { setWikiGenLoading(false); }
  };

  const fetchDomainDetail = async (id: string) => {
    try {
      const r = await fetch(`${WIKI_API}/domains/${id}`);
      const d = await r.json();
      setDomainClasses(d.classes || []);
      setDomainProps(d.object_properties || []);
      setGraphData(d);
    } catch { }
  };

  // v2.9: Fetch ontology audit stats for all domains
  useEffect(() => {
    fetch('/api/core/diagnostics/ontology-audit/summary')
      .then(r => r.json()).then(d => {
        const stats: Record<string, any> = {};
        for (const w of (d.worst_domains || [])) {
          stats[w.domain] = { entities: w.entities, edges: w.edge_count, orphans: w.orphans };
        }
        // Add relation coverage from individual audit
        if (selectedDomain) {
          fetch(`/api/core/diagnostics/ontology-audit?domain_id=${selectedDomain}`)
            .then(r => r.json()).then(r2 => {
              const cov = r2.report?.relation_coverage;
              if (cov) {
                setDomainStats(prev => ({
                  ...prev,
                  [selectedDomain]: { ...prev[selectedDomain], covered: cov.covered, total_defined: cov.total_defined }
                }));
              }
            }).catch(() => {});
        }
        setDomainStats(stats);
      }).catch(() => {});
  }, [selectedDomain]);

  useEffect(() => { fetchDomains(); }, []);

  const handleSelect = (id: string) => {
    setSelectedDomain(id);
    setValidationReport(null);
    fetchDomainDetail(id);
    setShowGraph(false);
    // Also fetch reviews and state history
    fetch(`${WIKI_API}/engine/reviews/${id}`).then(r => r.json()).then(d => setReviews(d.reviews || [])).catch(() => {});
    fetch(`${WIKI_API}/engine/state-history/${id}`).then(r => r.json()).then(d => setStateHistory(d.history || [])).catch(() => {});
    // Auto-verify on domain select
    fetch(`${WIKI_API}/domains/${id}/verify`, { method: 'POST' }).then(r => r.json()).then(d => setValidationReport(d)).catch(() => {});
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100">本体模型管理</h1>
        <OntologyLearningPanel collection="default" />
          <p className="text-sm text-gray-500 mt-1">创建和管理领域本体模型</p>
        </div>
        <div className="flex gap-2">
          <Button icon={<Plus className="w-4 h-4" />} onClick={() => { setNewId(''); setNewName(''); setNewDesc(''); setCreateOpen(true); }}>新建域</Button>
          <Button variant="ghost" size="sm" onClick={() => setShowWizard(true)}>🧬 创建向导</Button>
          <Button variant="secondary" onClick={() => { setGenId(''); setGenName(''); setGenDesc(''); setGenLimit(20); setGenSubdir(''); setGenKeywords(''); setGenResult(null); setGenYamlEdit(''); setGenOpen(true); fetchVaultDirs(); }}>🤖 从 Vault 生成</Button>
          <Button variant="secondary" onClick={() => { setWikiGenCollection('system_docs'); setWikiGenDomainId('aiplat-system'); setWikiGenOpen(true); }}>📚 从 Wiki 集合生成</Button>
          <Button variant="secondary" icon={<Search className="w-4 h-4" />} onClick={async () => {
            try {
              toast.info('正在重建所有域的检索索引...');
              const r = await fetch(`${WIKI_API}/domains/sync-search-index-all`, { method: 'POST' });
              const data = await r.json();
              if (data.total_synced > 0) {
                toast.success(`全量重建完成: ${data.total_synced} 页 (${data.domains_processed}域, ${data.total_classes}类, ${data.total_nodes}实体)`);
              } else {
                toast.info('所有域无实体数据');
              }
            } catch { toast.error('全量重建失败'); }
          }}>重建检索索引</Button>
          <Button variant="secondary" icon={<RefreshCw className="w-4 h-4" />} onClick={() => fetchDomains()}>刷新</Button>
        </div>
      </div>

      {/* ═══════════ Wiki 知识库健康概览 ═══════ */}
      <WikiHealthDashboard />

      {/* v2.9: Ontology audit summary */}
      {selectedDomain && (
        <div className="grid grid-cols-4 gap-3 mb-4">
          <AuditStat label="实体" value={domainStats?.[selectedDomain]?.entities || '...'} color="text-blue-400" />
          <AuditStat label="边" value={domainStats?.[selectedDomain]?.edges || '...'} color="text-green-400" />
          <AuditStat label="孤儿类" value={domainStats?.[selectedDomain]?.orphans ?? '...'} color="text-yellow-400" />
          <AuditStat label="已覆盖关系" value={domainStats?.[selectedDomain]?.covered ?? '...'} color="text-purple-400" />
        </div>
      )}

      {/* ── Domain List ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {domains.map(d => (
          <div key={d.id}
            onClick={() => handleSelect(d.id)}
            className={`p-4 rounded-lg border cursor-pointer transition-colors ${
              selectedDomain === d.id ? 'border-primary bg-primary/5' : 'border-dark-border bg-dark-card hover:border-gray-600'
            }`}>
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium text-gray-200">{d.name}</div>
              <span className="text-[10px] text-gray-500">v{d.version}</span>
            </div>
            <div className="text-xs text-gray-500 mt-1">{d.id}</div>
            <div className="text-xs text-gray-400 mt-1 truncate">{d.description || '暂无描述'}</div>
            <div className="flex gap-3 mt-2 text-[10px] text-gray-500">
              <span>{d.class_count} 类</span>
              <span>{d.property_count} 关系</span>
            </div>
            <div className="flex gap-2 mt-1.5 text-[10px] text-gray-600">
              <span title="Wiki检索阈值">检索: {d.min_wiki_score}</span>
              <span title="子类展开">{d.expand_subclasses ? '子类✓' : '子类✗'}</span>
              <span title="跨域降级阈值">降级: {d.min_cross_results}</span>
            </div>
            <div className="flex gap-1 mt-2">
              <Button variant="ghost" size="sm" onClick={async (e) => { e.stopPropagation();
                await fetch(`/api/core/engine/rebuild?collection=${d.collection_id || d.id}`, { method: 'POST' });
                fetchDomains(); toast.success(`已重建 ${d.name}`);
              }} title="重建本体 A-Box"><RefreshCw className="w-3 h-3" /></Button>
              <Button variant="ghost" size="sm" onClick={async (e) => { e.stopPropagation();
                try {
                  const r = await fetch(`${WIKI_API}/domains/${d.id}/sync-search-index`, { method: 'POST' });
                  const data = await r.json();
                  if (data.synced > 0) {
                    toast.success(`${d.name}: 同步 ${data.synced} 个实体索引 (${data.classes}类/${data.nodes}实体)`);
                  } else {
                    toast.info(`${d.name}: 无实体数据`);
                  }
                } catch { toast.error('同步失败'); }
              }} title="同步实体到检索索引"><Search className="w-3 h-3" /></Button>
              <Button variant="ghost" size="sm" onClick={async (e) => { e.stopPropagation();
                if (!confirm(`确定删除域 "${d.name}"？此操作不可逆。`)) return;
                await fetch(`${WIKI_API}/domains/${d.id}`, { method: 'DELETE' });
                fetchDomains(); setSelectedDomain(''); toast.success('已删除');
              }}><Trash2 className="w-3 h-3" /></Button>
            </div>
          </div>
        ))}
        {domains.length === 0 && (
          <div className="col-span-full text-center text-gray-500 py-8 text-sm">暂无领域本体，点击"新建域"创建</div>
        )}
      </div>

      {/* ── Domain Detail ── */}
      {selectedDomain && (
        <div className="bg-dark-card rounded-lg border border-dark-border p-4 space-y-4">
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium text-gray-200">
              {domains.find(d => d.id === selectedDomain)?.name || selectedDomain}
            </div>
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => { setEditingClass(null); setClsName(''); setClsLabel(''); setClsReq(''); setClsOpt(''); setClsCat(''); setClassOpen(true); }}>+ 类</Button>
              <Button variant="ghost" size="sm" onClick={() => { setEditingProp(null); setPropName(''); setPropLabel(''); setPropDomain(''); setPropRange(''); setPropOpen(true); }}>+ 关系</Button>
              <Button variant="ghost" size="sm" onClick={() => {
                const d = domains.find(x => x.id === selectedDomain);
                if (d) { setEditDomainName(d.name); setEditDomainDesc(d.description || ''); setDomainEditOpen(true); }
              }} title="编辑域信息"><span className="text-[10px]">✏️</span></Button>
              <Button variant="ghost" size="sm" onClick={() => { if (!graphData) fetchDomainDetail(selectedDomain).then(() => setShowGraph(true)); else setShowGraph(!showGraph); }}>
                {showGraph ? <><EyeOff className="w-3 h-3" /> 表</> : <><Eye className="w-3 h-3" /> 图</>}
              </Button>
            </div>
          </div>

          {/* ── Smart Recommendation Bar ── */}
          {validationReport && (
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded text-xs ${
              validationReport.overall === 'pass' ? 'bg-green-900/15 border border-green-800/30' : 'bg-yellow-900/10 border border-yellow-800/30'
            }`}>
              <span className={validationReport.overall === 'pass' ? 'text-green-400' : 'text-yellow-400'}>
                {validationReport.overall === 'pass' ? '✅' : '⚠️'}
              </span>
              <span className="text-gray-400">
                {validationReport.classification?.classified || 0} 页已分类
                {validationReport.classification?.unclassified > 0 && (
                  <span className="text-yellow-400"> · {validationReport.classification.unclassified} 页未分类</span>
                )}
                <span className="text-gray-600"> · {validationReport.graph?.nodes || 0} 节点</span>
              </span>
              {validationReport.overall !== 'pass' && (
                (() => {
                  if (loading) {
                    return <span className="text-blue-300 ml-auto animate-pulse">🔄 正在分类+构建...</span>;
                  }
                  return (
                    <button className="text-blue-400 hover:text-blue-300 ml-auto" onClick={async () => {
                      setLoading(true);
                      try {
                        let totalApplied = 0;
                        toast.info('正在分类...');
                        for (let batch = 1; batch <= 20; batch++) {
                          const cRes = await fetch(`${WIKI_API}/domains/${selectedDomain}/classify-all?limit=5`, { method: 'POST' });
                          const cData = await cRes.json();
                          const applied = cData.applied || 0;
                          totalApplied += applied;
                          if (applied === 0 && batch > 1) break;
                        }
                        toast.info('正在构建实例...');
                        let totalInstances = 0;
                        for (let b = 1; b <= 40; b++) {
                          const r = await fetch(`${WIKI_API}/domains/${selectedDomain}/build-instances?limit=5`, { method: 'POST' });
                          const d = await r.json();
                          totalInstances += d.instances_created || 0;
                          if (!d.processed && !d.skipped) break;
                        }
                        // Build cross-page graph edges
                        toast.info('正在构建图边...');
                        const eRes = await fetch(`${WIKI_API}/domains/${selectedDomain}/build-edges`, { method: 'POST' });
                        const eData = await eRes.json();
                        toast.success(`✅ 分类 ${totalApplied} 页, 实例 ${totalInstances}, 图边 +${eData.edges_created || 0}`);
                        fetchDomainDetail(selectedDomain);
                        const v = await fetch(`${WIKI_API}/domains/${selectedDomain}/verify`, { method: 'POST' });
                        setValidationReport(await v.json());
                      } catch { toast.error('执行失败'); }
                      finally { setLoading(false); }
                    }}>→ 一键分类+构建</button>
                  );
                })()
              )}
            </div>
          )}

          {/* ── Toolbar: Model Ops ── */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] text-gray-600 mr-1">模型:</span>
            <Button variant="ghost" size="sm" onClick={() => { setEvolveData(null); setEvolveOpen(true); fetchVaultDirs(); }} className="text-xs">🔄 进化</Button>
            <Button variant="ghost" size="sm" onClick={() => { setRepairData(null); setRepairOpen(true); fetchVaultDirs(); }} className="text-xs">🔧 修复</Button>
            <span className="text-[10px] text-gray-600 mx-2">|</span>
            <span className="text-[10px] text-gray-600">数据:</span>
            <Button variant="ghost" size="sm" onClick={async () => {
              setLoading(true);
              try {
                const r = await fetch(`${WIKI_API}/domains/${selectedDomain}/cleanup-nodes`, { method: 'POST' });
                const d = await r.json();
                toast.success(`清理完成: ${d.removed || 0} 节点`);
                fetchDomainDetail(selectedDomain);
              } catch { toast.error('清理失败'); }
              finally { setLoading(false); }
            }} className="text-xs" title="清理跨域污染节点">🧹 清理</Button>
            <Button variant="ghost" size="sm" onClick={() => fetchValidation(selectedDomain)} loading={validating} className="text-xs">🔍 验证</Button>
          </div>

          {/* ── Domain Config ── */}
          {(() => { const d = domains.find(x => x.id === selectedDomain); if (!d) return null; return (
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 bg-dark-bg rounded p-2">
              <span>检索阈值: <b className="text-gray-300">{d.min_wiki_score}</b></span>
              <span>子类展开: <b className="text-gray-300">{d.expand_subclasses ? '是' : '否'}</b></span>
              <span>跨域降级: <b className="text-gray-300">{d.min_cross_results}</b></span>
              <span>Prompt: <b className="text-gray-300">{d.system_prompt_id || '—'}</b></span>
              <span>Collection: <b className="text-gray-300">{d.collection_id || d.id}</b></span>
              <button className="text-[10px] text-primary hover:underline ml-2" onClick={() => { setScoringOpen(!scoringOpen); if (!scoringOpen) fetchScoringWeights(); }}>
                {scoringOpen ? '▼ 检索权重' : '▶ 检索权重'}
              </button>
            </div>
          )})()}

          {/* ── Scoring Weights Panel ── */}
          {scoringOpen && (
            <div className="bg-dark-bg rounded p-3 border border-dark-border/50 text-xs space-y-2">
              <div className="text-gray-400 mb-1">检索评分权重（总和应 = 1.0）</div>
              {[
                { key: 'semantic', label: '语义相似度' },
                { key: 'fts_keyword', label: 'FTS5 关键词' },
                { key: 'freshness', label: '内容时效性' },
                { key: 'credibility', label: '来源可信度' },
                { key: 'density', label: '内容密度' },
              ].map(({ key, label }) => (
                <div key={key} className="flex items-center gap-2">
                  <span className="text-gray-500 w-24">{label}</span>
                  <input type="range" min="0" max="1" step="0.05"
                    value={scoringWeights[key as keyof typeof scoringWeights] || 0}
                    onChange={e => setScoringWeights(prev => ({ ...prev, [key]: parseFloat(e.target.value) }))}
                    className="flex-1 h-1 accent-primary" />
                  <span className="text-gray-300 w-10 text-right">{(scoringWeights[key as keyof typeof scoringWeights] * 100).toFixed(0)}%</span>
                </div>
              ))}
              <div className="flex gap-2 pt-1">
                <Button variant="primary" size="sm" loading={scoringSaving} onClick={async () => {
                  setScoringSaving(true);
                  try {
                    await fetch(`${WIKI_API}/domains/${selectedDomain}/scoring`, {
                      method: 'PUT', headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify(scoringWeights),
                    });
                    toast.success('权重已保存');
                  } catch { toast.error('保存失败'); }
                  finally { setScoringSaving(false); }
                }}>保存</Button>
                <Button variant="ghost" size="sm" onClick={() => setScoringWeights({ semantic: 0.55, fts_keyword: 0.15, freshness: 0.10, credibility: 0.10, density: 0.10 })}>恢复默认</Button>
              </div>
            </div>
          )}

          {/* ── Verification Report ── */}
          {validationReport && (
            <div className="bg-dark-bg rounded p-3 border border-dark-border/50 text-xs">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-200">📊 验证报告</span>
                <button className="text-gray-500 hover:text-gray-300" onClick={() => setValidationReport(null)}>✕</button>
              </div>

              {/* Overall verdict */}
              <div className={`text-xs font-medium mb-2 ${validationReport.overall === 'pass' ? 'text-green-400' : 'text-yellow-400'}`}>
                {validationReport.overall === 'pass' ? '✅ 通过' : '⚠️ 需处理'}
              </div>

              {/* Classification stats */}
              {validationReport.classification && (
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-gray-400 mb-2">
                  <span>页面: {validationReport.classification.total_pages || 0}</span>
                  <span className={validationReport.classification.classified > 0 ? 'text-green-400' : 'text-yellow-400'}>
                    已分类: {validationReport.classification.classified || 0}
                  </span>
                  <span className={validationReport.classification.unclassified > 0 ? 'text-yellow-400' : 'text-gray-500'}>
                    未分类: {validationReport.classification.unclassified || 0}
                  </span>
                  {validationReport.classification.by_category && Object.keys(validationReport.classification.by_category).length > 0 && (
                    <span>类分布: {Object.entries(validationReport.classification.by_category).map(([k,v]: any) => `${k}:${v}`).join(', ')}</span>
                  )}
                </div>
              )}

              {/* Graph stats */}
              {validationReport.graph && (
                <div className="flex gap-4 text-gray-400 mb-2">
                  <span>图节点: {validationReport.graph.nodes || 0}</span>
                  <span>图边: {validationReport.graph.edges || 0}</span>
                </div>
              )}

              {/* Issues */}
              {validationReport.issues?.length > 0 ? (
                <div className="max-h-40 overflow-y-auto space-y-1">
                  {validationReport.issues.slice(0, 10).map((it: any, i: number) => (
                    <div key={i} className={`flex items-start gap-2 p-1 rounded ${it.severity === 'warn' ? 'bg-yellow-900/10 text-yellow-300' : 'bg-blue-900/10 text-blue-300'}`}>
                      <span className="text-[10px] mt-0.5">{it.severity === 'warn' ? '⚠️' : 'ℹ️'}</span>
                      <span className="flex-1">{it.detail || it.message}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-green-400 text-xs">✅ 无异常</div>
              )}
            </div>
          )}

          {/* ── Graph View ── */}
          {showGraph && graphData && (
            <div className="border border-dark-border rounded-lg overflow-hidden">
              <OntologyGraph
                classes={graphData.classes || []}
                objectProperties={graphData.object_properties || []}
                name={graphData.name}
              />
            </div>
          )}

          {/* ── Table View ── */}
          {!showGraph && (
            <>
              <div className="text-xs text-gray-400 mb-1">类定义</div>
              <div className="text-[11px] text-blue-300/80 bg-blue-900/15 border border-blue-800/20 rounded px-2.5 py-1 mb-2">领域内的知识类别，每个类有必填/可选字段和 Wiki 分类</div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {domainClasses.map(cls => (
                  <div key={cls.uri || cls.label} className="flex items-start justify-between p-2 rounded border border-dark-border/30 bg-dark-bg text-xs">
                    <div>
                      <div className="text-gray-200 font-medium">{cls.label}</div>
                      <div className="text-gray-500 mt-0.5">
                        <span className="text-amber-400">必填: {cls.required_fields?.join(', ') || '无'}</span>
                        {cls.optional_fields?.length > 0 && <span className="ml-2 text-gray-600">可选: {cls.optional_fields.join(', ')}</span>}
                      </div>
                      {cls.categories?.length > 0 && <div className="text-gray-600">分类: {cls.categories.join(', ')}</div>}
                      <button className="text-[10px] text-blue-400 hover:text-blue-300 mt-1 inline-block"
                        onClick={(e) => { e.stopPropagation(); fetchInstances(cls.label); }}>
                        📂 查看实例 →
                      </button>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="sm" title="编辑类" onClick={() => openEditClass(cls)}><span className="text-[10px]">✏️</span></Button>
                      <Button variant="ghost" size="sm" title="删除类" onClick={() => handleDeleteClass(cls)}><Trash2 className="w-3 h-3" /></Button>
                    </div>
                  </div>
                ))}
              </div>

              {/* ── Graph Stats + Inference ── */}
              <AIPAssist domainId={selectedDomain} />

              <div className="mt-3 flex items-center gap-2 text-[10px] text-gray-500">
                <span>🕸️ 图</span>
                <GraphStats domainId={selectedDomain} />
              </div>

              {/* ── State Machine Panel ── */}
              {domainClasses.some(cls => cls.states?.enum?.length > 0) && (
                <div className="mt-4">
                  <div className="text-xs text-gray-400 mb-1">状态机</div>
                  <div className="text-[11px] text-blue-300/80 bg-blue-900/15 border border-blue-800/20 rounded px-2.5 py-1 mb-2">定义实体状态的演变规则和触发条件，自动驱动状态迁移</div>
                  <div className="space-y-4">
                    {domainClasses.filter(cls => cls.states?.enum?.length > 0).map(cls => {
                      const stateColors: Record<string, string> = {
                        emerging: '#eab308', established: '#22c55e', industrial: '#3b82f6',
                        deprecated: '#ef4444', retired: '#ef4444',
                        dev: '#f59e0b', staging: '#8b5cf6', production: '#22c55e',
                      };
                      return (
                        <div key={cls.uri || cls.label} className="p-3 rounded border border-dark-border/30 bg-dark-bg text-xs">
                          <div className="text-gray-200 font-medium mb-2">{cls.label} 状态机</div>
                          {/* State flow diagram */}
                          <div className="flex flex-wrap items-center gap-1 mb-3">
                            {(cls.states?.enum || []).map((s: any, i: number) => (
                              <React.Fragment key={s.name}>
                                {i > 0 && <span className="text-gray-600 mx-0.5">→</span>}
                                <div className="flex items-center gap-1 px-2 py-1 rounded border border-dark-border/40"
                                  style={{ borderLeftColor: stateColors[s.name] || '#6b7280', borderLeftWidth: 3 }}>
                                  <span className="w-2 h-2 rounded-full" style={{ background: stateColors[s.name] || '#6b7280' }} />
                                  <span className="text-gray-300">{s.label || s.name}</span>
                                </div>
                              </React.Fragment>
                            ))}
                          </div>
                          {/* Transition rules */}
                          {(cls.transitions || []).length > 0 && (
                            <div className="space-y-1 mt-2">
                              <div className="text-[10px] text-gray-500 mb-1">转换规则：</div>
                              {(cls.transitions || []).map((t: any, i: number) => {
                                const fromList = Array.isArray(t.from) ? t.from : [t.from];
                                const triggerLabel = t.trigger?.type === 'relation_count'
                                  ? `${t.trigger.relation} ${t.trigger.operator} ${t.trigger.threshold}`
                                  : t.trigger?.type === 'property_condition'
                                    ? `${t.trigger.field} ${t.trigger.condition}`
                                    : t.trigger?.type === 'relation_exists'
                                      ? `存在 ${t.trigger.relation} 关系`
                                      : t.trigger?.type || '';
                                return (
                                  <div key={i} className="flex items-center gap-1 text-[10px] text-gray-500 pl-2">
                                    <span className="text-gray-400">{fromList.join(' / ')}</span>
                                    <ArrowRight className="w-2.5 h-2.5" />
                                    <span className="text-gray-300">{t.to}</span>
                                    <span className="text-gray-600">({triggerLabel})</span>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                          {/* Side effects */}
                          {(cls.side_effects || []).length > 0 && (
                            <div className="text-[10px] text-gray-600 mt-1 pl-2">
                              联动：{(cls.side_effects || []).map((e: any) =>
                                e.actions?.map((a: any) => a.type).join(', ')
                              ).join('; ')}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {domainProps.length > 0 && (
                <>
                  <div className="text-xs text-gray-400 mt-4 mb-1">关系定义</div>
                  <div className="text-[11px] text-blue-300/80 bg-blue-900/15 border border-blue-800/20 rounded px-2.5 py-1 mb-2">类之间的连接方式，用于知识图谱构建和推理</div>
                  <div className="space-y-1">
                    {domainProps.map(p => (
                      <div key={p.uri || p.label} className="flex items-center gap-2 text-xs text-gray-300 p-2 rounded border border-dark-border/30 bg-dark-bg"
                        title={p.description || `${p.domain?.join(', ')} → ${p.label} → ${p.range?.join(', ')}`}>
                        <span className="text-purple-400">{p.domain?.join(', ')}</span>
                        <ArrowRight className="w-3 h-3 text-gray-500" />
                        <span className="text-purple-400">{p.label}</span>
                        <ArrowRight className="w-3 h-3 text-gray-500" />
                        <span className="text-purple-400">{p.range?.join(', ')}</span>
                        {p.transitive && <span className="text-[10px] text-gray-500" title="如果 A→B 且 B→C, 则 A→C">(传递)</span>}
                        {p.symmetric && <span className="text-[10px] text-gray-500" title="A→B 等价于 B→A">(对称)</span>}
                        <Button variant="ghost" size="sm" title="编辑关系" className="ml-auto" onClick={() => {
                          const pname = (p.uri || '').split('#').pop() || p.label;
                          setEditingProp(pname);
                          setPropName(pname);
                          setPropLabel(p.label);
                          setPropDomain((p.domain || []).join(', '));
                          setPropRange((p.range || []).join(', '));
                          setPropOpen(true);
                        }}><span className="text-[10px]">✏️</span></Button>
                        <Button variant="ghost" size="sm" title="删除关系" onClick={async () => {
                          if (!confirm('确定删除此关系？')) return;
                          const pname = (p.uri || '').split('#').pop() || p.label;
                          await fetch(`${WIKI_API}/domains/${selectedDomain}/properties/${encodeURIComponent(pname)}`, { method: 'DELETE' });
                          fetchDomainDetail(selectedDomain); toast.success('已删除');
                        }}><span className="text-[10px]">🗑️</span></Button>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Propagation Simulation ── */}
      {selectedDomain && domainClasses.some(cls => cls.states?.enum?.length > 0) && (
        <div className="bg-dark-card rounded-lg border border-dark-border p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-gray-200">🔁 传播模拟</div>
              <div className="text-xs text-gray-500 mt-0.5">模拟实例创建后的状态传播与联动影响</div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <select value={simFocus} onChange={e => { setSimFocus(e.target.value); setSimResult(null); }}
              className="h-8 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-300">
              <option value="">选择焦点类</option>
              {domainClasses.filter(cls => cls.states?.enum?.length > 0).map(cls => (
                <option key={cls.label} value={cls.label}>{cls.label}</option>
              ))}
            </select>
            {simFocus && domainClasses.filter(cls => cls.label !== simFocus).map(cls => (
              <div key={cls.label} className="flex items-center gap-1 text-xs">
                <span className="text-gray-500">{cls.label}</span>
                <button className="w-5 h-5 rounded border border-dark-border/50 text-gray-400 hover:text-gray-200"
                  onClick={() => setSimCounts(s => ({ ...s, [cls.label]: Math.max(0, (s[cls.label] || 0) - 1) }))}>-</button>
                <span className="text-gray-300 w-4 text-center">{simCounts[cls.label] || 0}</span>
                <button className="w-5 h-5 rounded border border-dark-border/50 text-gray-400 hover:text-gray-200"
                  onClick={() => setSimCounts(s => ({ ...s, [cls.label]: (s[cls.label] || 0) + 1 }))}>+</button>
              </div>
            ))}
            <Button variant="primary" size="sm" loading={simLoading}
              onClick={async () => {
                if (!simFocus) return;
                setSimLoading(true); setSimResult(null);
                try {
                  const insts: any[] = [];
                  // Focus instance
                  insts.push({ class_name: simFocus, properties: { name: simFocus + '_主实例' }, chunk_id: 'sim-c0' });
                  // Co-occurring instances
                  let ci = 1;
                  for (const [clsLabel, cnt] of Object.entries(simCounts)) {
                    for (let i = 0; i < cnt; i++) {
                      insts.push({ class_name: clsLabel, properties: { name: `${clsLabel}_${ci}` }, chunk_id: 'sim-c0' });
                      ci++;
                    }
                  }
                  // Also add 1 of focus class to trigger relation_exists
                  if (simCounts[simFocus] === undefined || simCounts[simFocus] === 0) {
                    insts.push({ class_name: simFocus, properties: { name: simFocus + '_关联' }, chunk_id: 'sim-c0' });
                  }
                  const r = await fetch(`${WIKI_API}/engine/simulate-state`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ domain_id: selectedDomain, instances: insts }),
                  });
                  setSimResult(await r.json());
                } catch { toast.error('模拟失败'); }
                finally { setSimLoading(false); }
              }}>
              ▶ 模拟
            </Button>
          </div>

          {simResult && (
            <div className="space-y-3">
              <div className="text-xs text-gray-400">{simResult.summary}</div>

              {/* Transitions */}
              {simResult.state_transitions?.length > 0 && (
                <div className="space-y-1">
                  <div className="text-[10px] text-gray-500">状态转换：</div>
                  <div className="flex flex-wrap gap-2">
                    {simResult.state_transitions.map((t: any, i: number) => {
                      const clr = t.to_state === 'deprecated' || t.to_state === 'retired' ? '#ef4444'
                        : t.to_state === 'canonical' || t.to_state === 'resolved' || t.to_state === 'industrial' ? '#22c55e'
                        : '#3b82f6';
                      return (
                        <div key={i} className="flex items-center gap-1 px-2 py-1 rounded border border-dark-border/30 bg-dark-bg text-[10px]">
                          <span className="text-gray-200">{t.entity_text?.slice(0, 15)}</span>
                          <span className="text-gray-500">{t.class_name}</span>
                          <span className="text-gray-500">→</span>
                          <span style={{ color: clr }}>{t.to_state}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Affected instances (propagation) */}
              {simResult.affected_instances?.length > 0 && (
                <div className="space-y-1">
                  <div className="text-[10px] text-gray-500">联动影响：</div>
                  <div className="flex flex-wrap gap-2">
                    {simResult.affected_instances.map((a: any, i: number) => (
                      <div key={i} className="flex items-center gap-1 px-2 py-1 rounded border border-orange-500/30 bg-orange-500/5 text-[10px]">
                        <span className="text-gray-300">{a.from_instance?.slice(0, 12)}</span>
                        <span className="text-orange-400">⚡→</span>
                        <span className="text-gray-300">{a.to_instance?.slice(0, 12)}</span>
                        <span className="text-gray-500 ml-1 truncate max-w-[120px]">{a.reason?.slice(0, 30)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Visualization: colored pills with arrows */}
              {simResult.affected_instances?.length > 0 && (
                <div className="border border-dark-border/30 rounded p-3 bg-dark-bg/50">
                  <div className="text-[10px] text-gray-500 mb-2">传播路径图</div>
                  <div className="flex flex-col gap-2">
                    {(() => {
                      // Group by from_instance
                      const groups: Record<string, any[]> = {};
                      for (const a of simResult.affected_instances) {
                        const key = a.from_instance;
                        (groups[key] = groups[key] || []).push(a);
                      }
                      const clsColors: Record<string, string> = {'AI方法': '#a855f7', 'AI系统': '#3b82f6', 'AI概念': '#22c55e', '业务问题': '#eab308', '参考资料': '#6b7280'};
                      return Object.entries(groups).map(([from, targets]) => {
                        const fromCls = simResult.state_transitions?.find((t: any) => t.entity_text === from)?.class_name || '';
                        return (
                          <div key={from} className="flex items-center gap-1 flex-wrap">
                            <div className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
                              style={{ background: (clsColors[fromCls] || '#6b7280') + '30', color: clsColors[fromCls] || '#6b7280' }}>
                              {from.slice(0, 12)}
                            </div>
                            <span className="text-orange-500 text-[10px]">⚠</span>
                            {targets.map((t: any, j: number) => (
                              <div key={j} className="flex items-center gap-0.5">
                                {j > 0 && <span className="text-gray-600 text-[10px]">,</span>}
                                <div className="px-1.5 py-0.5 rounded text-[10px] border border-dashed border-orange-500/40"
                                  style={{ background: (clsColors[t.to_class] || '#6b7280') + '20', color: clsColors[t.to_class] || '#6b7280' }}>
                                  {t.to_instance?.slice(0, 10)}
                                </div>
                              </div>
                            ))}
                          </div>
                        );
                      });
                    })()}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Review Queue ── */}
      {selectedDomain && (
        <div className="bg-dark-card rounded-lg border border-dark-border p-4 space-y-2">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-gray-200">📋 复查队列</div>
              <div className="text-[11px] text-blue-300/80 bg-blue-900/15 border border-blue-800/20 rounded px-2.5 py-1 mb-2">状态变更时自动生成的关联实例审查提醒</div>
            </div>
            <Button variant="ghost" size="sm" loading={reviewLoading}
              onClick={async () => {
                setReviewLoading(true);
                try {
                  const r = await fetch(`${WIKI_API}/engine/reviews/${selectedDomain}`);
                  const d = await r.json();
                  setReviews(d.reviews || []);
                } catch { }
                finally { setReviewLoading(false); }
              }}>刷新</Button>
          </div>
          {reviews.filter((r: any) => r.status === 'pending').length === 0 ? (
            <div className="text-xs text-gray-500 py-2">无待复查项</div>
          ) : (
            <div className="space-y-1 max-h-64 overflow-auto">
              {reviews.filter((r: any) => r.status === 'pending').map((r: any) => (
                <div key={r.id} className="flex items-center gap-2 p-1.5 rounded border border-orange-500/20 bg-orange-500/5 text-xs" title={r.reason || ''}>
                  <span className="text-gray-300 w-28 truncate">{r.from_instance}</span>
                  <span className="text-orange-400">⚠→</span>
                  <span className="text-gray-300 w-28 truncate">{r.to_instance}</span>
                  <span className="text-gray-500 flex-1 truncate" title={r.reason || ''}>{r.reason?.slice(0, 40)}</span>
                  <span className="text-gray-600 text-[10px] whitespace-nowrap">{new Date(r.timestamp * 1000).toLocaleDateString()}</span>
                  <button className="text-[10px] px-1.5 py-0.5 rounded bg-green-900/30 text-green-300 hover:bg-green-900/50"
                    onClick={async () => {
                      await fetch(`${WIKI_API}/engine/reviews/${selectedDomain}/resolve`, {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ review_id: r.id }),
                      });
                      setReviews(prev => prev.map(rr => rr.id === r.id ? { ...rr, status: 'resolved' } : rr));
                      toast.success('已标记为已复查');
                    }}>✓ 已复查</button>
                </div>
              ))}
            </div>
          )}
          {reviews.filter((r: any) => r.status !== 'pending').length > 0 && (
            <div className="text-[10px] text-gray-600">
              已复查 {reviews.filter((r: any) => r.status !== 'pending').length} 项（隐藏）
            </div>
          )}
        </div>
      )}

      {/* ── State History Timeline ── */}
      {selectedDomain && (
        <div className="bg-dark-card rounded-lg border border-dark-border p-4 space-y-2">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-gray-200">📜 状态变更历史</div>
              <div className="text-[11px] text-blue-300/80 bg-blue-900/15 border border-blue-800/20 rounded px-2.5 py-1 mb-2">状态机触发的最新状态转换记录</div>
            </div>
            <Button variant="ghost" size="sm" loading={historyLoading}
              onClick={async () => {
                setHistoryLoading(true);
                try {
                  const r = await fetch(`${WIKI_API}/engine/state-history/${selectedDomain}`);
                  setStateHistory((await r.json()).history || []);
                } catch { }
                finally { setHistoryLoading(false); }
              }}>刷新</Button>
          </div>
          {stateHistory.length === 0 ? (
            <div className="text-xs text-gray-500 py-2">暂无变更记录（运行引擎解析文档后自动记录）</div>
          ) : (
              <div className="space-y-1 max-h-48 overflow-auto">
               {stateHistory.slice(0, 30).map((h: any) => (
                 <div key={h.id} className="flex items-center gap-2 p-1 text-xs">
                   <span className="text-gray-600 text-[10px] w-16 whitespace-nowrap">
                     {new Date(h.timestamp * 1000).toLocaleTimeString()}
                   </span>
                   <span className="text-gray-300 w-24 truncate">{h.entity_name}</span>
                   <span className="text-gray-500 w-14">{h.class_name}</span>
                   <span className="text-gray-500" title={h.description || `状态: ${h.from_state}`}>{h.from_state}</span>
                   <span className="text-gray-400">→</span>
                   <span style={{ color: h.to_state === 'deprecated' || h.to_state === 'retired' ? '#ef4444' : '#22c55e' }}
                     title={h.description || `状态: ${h.to_state}`}>
                     {h.to_state}
                   </span>
                  {h.tags?.length > 0 && (
                    <span className="text-[10px] text-gray-500">[{h.tags.join(',')}]</span>
                  )}
                </div>
              ))}
              {stateHistory.length > 30 && (
                <div className="text-[10px] text-gray-600">仅显示最近 30 条，共 {stateHistory.length} 条</div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Smart Generate Modal ── */}
      <Modal open={genOpen} onClose={() => setGenOpen(false)} title="🤖 智能生成本体模型">
        {!genResult ? (
          <div className="space-y-4">
            <div className="text-xs text-gray-500">从连接的 Vault 资料中自动生成领域本体 YAML 模型</div>
            <Input label="域标识 (英文ID)" value={genId} onChange={(e: any) => setGenId(e.target.value)} placeholder="finance-compliance" />
            <Input label="域名称" value={genName} onChange={(e: any) => setGenName(e.target.value)} placeholder="金融合规" />
            <Input label="域描述 (关键词)" value={genDesc} onChange={(e: any) => setGenDesc(e.target.value)} placeholder="覆盖反洗钱AML、KYC、监管报送、风险评级等" />
            <div className="text-xs text-gray-400 mb-0.5">Vault 子目录 (可选)</div>
            <select value={genSubdir} onChange={e => setGenSubdir(e.target.value)}
              className="w-full bg-dark-bg border border-dark-border rounded px-2 py-1.5 text-xs text-gray-200">
              <option value="">— 全部 Vault —</option>
              {vaultDirs.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
            <Input label="关键词过滤 (可选)" value={genKeywords} onChange={(e: any) => setGenKeywords(e.target.value)} placeholder="RAG 检索 本体" />
            <Input label="采样文件数" value={String(genLimit)} onChange={(e: any) => setGenLimit(Number(e.target.value) || 20)} />
            <Button variant="primary" loading={genLoading} onClick={async () => {
              if (!genId.trim() || !genName.trim() || !genDesc.trim()) return toast.error('请填写标识、名称和描述');
              setGenLoading(true);
              try {
                const r = await fetch(`${WIKI_API}/domains/generate`, {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ id: genId.trim(), name: genName.trim(), description: genDesc.trim(), vault_subdir: genSubdir.trim(), keywords: genKeywords.trim(), sample_limit: genLimit }),
                });
                const d = await r.json();
                setGenResult(d);
                setGenYamlEdit(d.yaml || '');
                if (d.status === 'preview') toast.success(`生成完成: ${d.stats?.classes_generated || 0} 个类, ${d.stats?.relations_found || 0} 个关系`);
              } catch (e: any) { toast.error('生成失败: ' + (e.message || '网络错误')); }
              finally { setGenLoading(false); }
            }}>开始生成</Button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400 bg-dark-bg rounded p-2">
              <span>📁 扫描文件: {genResult.stats?.files_scanned || 0}</span>
              <span>🔍 发现实体: {genResult.stats?.entities_found || 0}</span>
              <span>📦 生成类: {genResult.stats?.classes_generated || 0}</span>
              <span>🔗 发现关系: {genResult.stats?.relations_found || 0}</span>
              <span>🔄 状态机: {genResult.stats?.state_machines || 0}</span>
            </div>
            <div className="text-xs text-gray-500">预览并编辑生成的 YAML（保存后将写入本体文件并注册到系统）</div>
            <textarea className="w-full h-72 bg-dark-bg border border-dark-border rounded p-2 text-xs text-gray-200 font-mono" 
              value={genYamlEdit} onChange={(e: any) => setGenYamlEdit(e.target.value)} />
            <div className="flex gap-2">
              <Button variant="primary" loading={loading} onClick={async () => {
                if (!genYamlEdit.trim()) return;
                setLoading(true);
                try {
                  // Write YAML + register
                  const r = await fetch(`${WIKI_API}/domains`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: genId.trim(), name: genName.trim(), description: genDesc.trim() }),
                  });
                  if (!r.ok) throw new Error('创建域失败');
                  // Write the generated YAML content
                  await fetch(`${WIKI_API}/domains/${genId.trim()}`, {
                    method: 'PUT', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: genId.trim(), name: genName.trim(), description: genDesc.trim() }),
                  });
                  setGenOpen(false); setGenResult(null); fetchDomains(); toast.success('本体模型已保存');
                } catch (e: any) { toast.error('保存失败'); }
                finally { setLoading(false); }
              }}>💾 保存并注册</Button>
              <Button variant="ghost" onClick={() => { setGenResult(null); setGenYamlEdit(''); }}>重新生成</Button>
              <Button variant="ghost" onClick={() => { setGenOpen(false); setGenResult(null); }}>取消</Button>
            </div>
          </div>
        )}
      </Modal>

      {/* ── Wiki Collection → Domain 生成 ── */}
      <Modal open={wikiGenOpen} onClose={() => setWikiGenOpen(false)} title="📚 从 Wiki 集合生成领域">
        <div className="space-y-4">
          <div className="text-xs text-gray-400">选择已有 Wiki 集合，从其中的实体和页面自动提取领域本体定义。</div>
          <Input label="Wiki 集合名" value={wikiGenCollection} onChange={(e: any) => setWikiGenCollection(e.target.value)} placeholder="system_docs" />
          <Input label="领域标识 (英文ID)" value={wikiGenDomainId} onChange={(e: any) => setWikiGenDomainId(e.target.value)} placeholder="aiplat-system" />
          <div className="flex gap-2">
            <Button variant="primary" loading={wikiGenLoading} onClick={handleWikiGenDomain}>
              🧬 生成领域
            </Button>
            <Button variant="ghost" onClick={() => setWikiGenOpen(false)}>取消</Button>
          </div>
        </div>
      </Modal>

      {/* ── Evolve Modal ── */}
      <Modal open={evolveOpen} onClose={() => setEvolveOpen(false)} title={evolveData ? "🔄 本体进化建议" : "🔄 本体进化 — 选择资料范围"}>
        {!evolveData && (
          <div className="space-y-4">
            <div className="text-xs text-gray-500">检测新增/修改的 Vault 文件，对比现有本体模型，生成增量建议</div>
            <div className="text-xs text-gray-400 mb-0.5">Vault 子目录 (可选)</div>
            <select value={genSubdir} onChange={e => setGenSubdir(e.target.value)}
              className="w-full bg-dark-bg border border-dark-border rounded px-2 py-1.5 text-xs text-gray-200">
              <option value="">— 全部 Vault —</option>
              {vaultDirs.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
            <Input label="关键词过滤 (可选)" value={genKeywords} onChange={(e: any) => setGenKeywords(e.target.value)} placeholder="" />
            <Input label="采样文件数" value={String(genLimit)} onChange={(e: any) => setGenLimit(Number(e.target.value) || 10)} />
            <Button variant="primary" loading={evolveLoading} onClick={async () => {
              setEvolveLoading(true);
              try {
                const r = await fetch(`${WIKI_API}/domains/${selectedDomain}/evolve`, {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ sample_limit: genLimit, vault_subdir: genSubdir.trim(), keywords: genKeywords.trim() }),
                });
                setEvolveData(await r.json()); setEvolveChecked({});
              } catch { toast.error('进化分析失败'); }
              finally { setEvolveLoading(false); }
            }}>开始分析</Button>
          </div>
        )}
        {evolveData && (
          <div className="space-y-4">
            <div className="text-xs text-gray-400">
              发现 {evolveData.new_files_found || 0} 个新/变更的 Vault 文件
              {evolveData.suggestions?.summary && <span> — {evolveData.suggestions.summary}</span>}
            </div>
            {evolveData.suggestions?.new_classes?.length > 0 && (
              <div>
                <div className="text-sm text-gray-200 mb-2">建议新增类 ({evolveData.suggestions.new_classes.length})</div>
                {evolveData.suggestions.new_classes.map((c: any, i: number) => (
                  <div key={i} className="flex items-start gap-2 p-2 rounded border border-dark-border/30 bg-dark-bg text-xs">
                    <input type="checkbox" checked={!!evolveChecked[i]} onChange={e => setEvolveChecked(p => ({...p, [i]: e.target.checked}))} />
                    <div>
                      <span className="text-gray-200 font-medium">{c.label}</span>
                      <span className="text-gray-500 ml-2">({c.name})</span>
                      <div className="text-gray-500 mt-0.5">{c.description}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {(!evolveData.suggestions?.new_classes?.length && !evolveData.suggestions?.new_relations?.length) && (
              <div className="text-green-400 text-xs">✅ 当前本体已覆盖所有 Vault 内容，无需变更</div>
            )}
            <div className="flex gap-2">
              <Button variant="primary" size="sm" onClick={async () => {
                const cls = (evolveData.suggestions?.new_classes || []).filter((_: any, i: number) => evolveChecked[i]);
                if (cls.length === 0) return toast.info('未勾选任何项');
                for (const c of cls) {
                  await fetch(`${WIKI_API}/domains/${selectedDomain}/classes`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: c.name, label: c.label, required_fields: c.required_fields || ['name','description'], optional_fields: [], categories: c.categories || [] }),
                  });
                }
                setEvolveOpen(false); fetchDomainDetail(selectedDomain); toast.success(`已添加 ${cls.length} 个类`);
              }}>应用勾选的 {Object.values(evolveChecked).filter(Boolean).length} 项</Button>
              <Button variant="ghost" size="sm" onClick={() => setEvolveOpen(false)}>关闭</Button>
            </div>
          </div>
        )}
      </Modal>

      {/* ── Repair Modal ── */}
      <Modal open={repairOpen} onClose={() => setRepairOpen(false)} title={repairData ? "🔧 智能修复建议" : "🔧 智能修复 — 选择资料范围"}>
        {!repairData && (
          <div className="space-y-4">
            <div className="text-xs text-gray-500">审计已有本体模型 vs Vault 内容，发现需要补全的类、字段、同义词等</div>
            <div className="text-xs text-gray-400 mb-0.5">Vault 子目录 (可选)</div>
            <select value={genSubdir} onChange={e => setGenSubdir(e.target.value)}
              className="w-full bg-dark-bg border border-dark-border rounded px-2 py-1.5 text-xs text-gray-200">
              <option value="">— 全部 Vault —</option>
              {vaultDirs.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
            <Input label="关键词过滤 (可选)" value={genKeywords} onChange={(e: any) => setGenKeywords(e.target.value)} placeholder="AML KYC" />
            <Input label="采样文件数" value={String(genLimit)} onChange={(e: any) => setGenLimit(Number(e.target.value) || 20)} />
            <Button variant="primary" loading={repairLoading} onClick={async () => {
              setRepairLoading(true);
              try {
                const r = await fetch(`${WIKI_API}/domains/${selectedDomain}/repair`, {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ sample_limit: genLimit, vault_subdir: genSubdir.trim(), keywords: genKeywords.trim() }),
                });
                setRepairData(await r.json()); setRepairChecked({});
              } catch { toast.error('修复分析失败'); }
              finally { setRepairLoading(false); }
            }}>开始分析</Button>
          </div>
        )}
        {repairData?.repair_suggestions && (
          <div className="space-y-4 max-h-[70vh] overflow-y-auto">
            <div className="text-xs text-gray-400">
              扫描 {repairData.files_scanned || 0} 份 Vault 文件，
              检查 {repairData.existing_classes || 0} 个现有类
              {repairData.repair_suggestions.summary && <div className="text-blue-300 mt-1">{repairData.repair_suggestions.summary}</div>}
            </div>

            {/* Missing Classes */}
            {repairData.repair_suggestions.missing_classes?.length > 0 && (
              <div>
                <div className="text-sm text-yellow-300 mb-1">📦 建议新增类 ({repairData.repair_suggestions.missing_classes.length})</div>
                {repairData.repair_suggestions.missing_classes.map((c: any, i: number) => (
                  <div key={`mc${i}`} className="flex items-start gap-2 p-2 rounded border border-dark-border/30 bg-dark-bg text-xs mb-1">
                    <input type="checkbox" checked={!!repairChecked[`mc${i}`]} onChange={e => setRepairChecked(p => ({...p, [`mc${i}`]: e.target.checked}))} />
                    <div>
                      <span className="text-gray-200">{c.label}</span>
                      <span className="text-gray-500 ml-1">({c.suggested_name})</span>
                      {c.category && <span className="text-gray-600 ml-1">→ {c.category}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Missing Fields */}
            {repairData.repair_suggestions.missing_fields?.length > 0 && (
              <div>
                <div className="text-sm text-yellow-300 mb-1">📝 建议补字段 ({repairData.repair_suggestions.missing_fields.length})</div>
                {repairData.repair_suggestions.missing_fields.map((f: any, i: number) => (
                  <div key={`mf${i}`} className="flex items-start gap-2 p-2 rounded border border-dark-border/30 bg-dark-bg text-xs mb-1">
                    <input type="checkbox" checked={!!repairChecked[`mf${i}`]} onChange={e => setRepairChecked(p => ({...p, [`mf${i}`]: e.target.checked}))} />
                    <div>
                      <span className="text-gray-200">{f.class}</span>
                      <span className="text-blue-400 mx-1">+{f.field}</span>
                      {f.reason && <span className="text-gray-500">— {f.reason}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Missing Synonyms */}
            {repairData.repair_suggestions.missing_synonyms?.length > 0 && (
              <div>
                <div className="text-sm text-yellow-300 mb-1">🔤 建议补同义词 ({repairData.repair_suggestions.missing_synonyms.length})</div>
                {repairData.repair_suggestions.missing_synonyms.map((s: any, i: number) => (
                  <div key={`ms${i}`} className="flex items-start gap-2 p-2 rounded border border-dark-border/30 bg-dark-bg text-xs mb-1">
                    <input type="checkbox" checked={!!repairChecked[`ms${i}`]} onChange={e => setRepairChecked(p => ({...p, [`ms${i}`]: e.target.checked}))} />
                    <div>
                      <span className="text-gray-200">{s.class}</span>
                      <span className="text-green-400 mx-1">+ {(s.suggested || []).join(', ')}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Weak Relations */}
            {repairData.repair_suggestions.weak_relations?.length > 0 && (
              <div>
                <div className="text-sm text-yellow-300 mb-1">🔗 弱关系建议 ({repairData.repair_suggestions.weak_relations.length})</div>
                {repairData.repair_suggestions.weak_relations.map((r: any, i: number) => (
                  <div key={`wr${i}`} className="text-xs text-gray-300 p-2 rounded border border-dark-border/30 bg-dark-bg mb-1">
                    {r.suggestion || JSON.stringify(r)}
                  </div>
                ))}
              </div>
            )}

            {/* Weak State Machines */}
            {repairData.repair_suggestions.weak_state_machines?.length > 0 && (
              <div>
                <div className="text-sm text-yellow-300 mb-1">⚙️ 弱状态机 ({repairData.repair_suggestions.weak_state_machines.length})</div>
                {repairData.repair_suggestions.weak_state_machines.map((w: any, i: number) => (
                  <div key={`ws${i}`} className="text-xs text-gray-300 p-2 rounded border border-dark-border/30 bg-dark-bg mb-1">
                    <span className="text-gray-200">{w.class}</span> — {w.issue}
                  </div>
                ))}
              </div>
            )}

            {!repairData.repair_suggestions.missing_classes?.length && 
             !repairData.repair_suggestions.missing_fields?.length &&
             !repairData.repair_suggestions.missing_synonyms?.length &&
             !repairData.repair_suggestions.weak_relations?.length &&
             !repairData.repair_suggestions.weak_state_machines?.length && (
              <div className="text-green-400 text-xs">✅ 本体模型完整，无需修复</div>
            )}

            <div className="flex gap-2">
              <Button variant="primary" size="sm" onClick={async () => {
                const checked = Object.entries(repairChecked).filter(([_, v]) => v);
                if (checked.length === 0) return toast.info('未勾选任何项');
                let applied = 0;
                for (const [key] of checked) {
                  const mc = repairData.repair_suggestions.missing_classes;
                  if (mc && key.startsWith('mc')) {
                    const c = mc[parseInt(key.slice(2))];
                    if (c) { 
                      await fetch(`${WIKI_API}/domains/${selectedDomain}/classes`, {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: c.suggested_name || c.label, label: c.label, required_fields: ['name','description'], optional_fields: [], categories: c.category ? [c.category] : [] }),
                      });
                      applied++;
                    }
                  }
                }
                await fetchDomainDetail(selectedDomain);
                setRepairOpen(false); toast.success(`已应用 ${applied} 项修复`);
              }}>应用勾选的 {Object.values(repairChecked).filter(Boolean).length} 项</Button>
              <Button variant="ghost" size="sm" onClick={() => setRepairOpen(false)}>关闭</Button>
            </div>
          </div>
        )}
      </Modal>

      {/* ── View Instances Modal ── */}
      <Modal open={instancesOpen} onClose={() => setInstancesOpen(false)} title={`📂 ${instanceClassLabel} 实例`}>
        {instanceData && (
          <div className="space-y-2 overflow-y-auto" style={{ maxHeight: '60vh' }}>
            <div className="text-xs text-gray-500 mb-2">共 {instanceData.total || 0} 个</div>
            {instanceData.instances?.length > 0 ? (
              instanceData.instances.map((inst: any, i: number) => (
                <div key={i} className="p-2 rounded border border-dark-border/30 bg-dark-bg text-xs">
                  <div className="flex items-center gap-2 min-w-0">
                    <a href={`/platform/kb?activeTab=wiki&category=${encodeURIComponent(inst.category || '')}`} target="_blank"
                      className="text-gray-200 font-medium hover:text-primary truncate max-w-[300px]">
                      {inst.entity_name || inst.wiki_title}
                    </a>
                    {inst.state && (
                      <span className={`px-1 py-0.5 rounded text-[10px] ${
                        inst.state === 'deprecated' || inst.state === 'retired' ? 'bg-red-900/30 text-red-300' :
                        inst.state === 'production' ? 'bg-green-900/30 text-green-300' :
                        'bg-blue-900/30 text-blue-300'
                      }`}>{inst.state}</span>
                    )}
                    <span className="text-[10px] text-gray-600 bg-dark-border/30 px-1 rounded">{inst.category}</span>
                  </div>
                  {inst.summary && <div className="text-gray-500 mt-1 line-clamp-2">{inst.summary}</div>}
                  <div className="flex gap-2 mt-1 text-[10px] text-gray-600">
                    {inst.tags?.length > 0 && inst.tags.slice(0, 4).map((t: string) => (
                      <span key={t} className="bg-dark-border/30 px-1 rounded">{t}</span>
                    ))}
                    {inst.related?.length > 0 && <span>↗ {inst.related.length} 关联</span>}
                  </div>
                </div>
              ))
            ) : (
              <div className="text-gray-500 text-xs py-4 text-center space-y-2">
                <div>暂无实例</div>
                <div className="text-[10px] text-gray-600">
                  该类别下还没有 Wiki 页面。
                  在编缉知识页面创建页面或从 Vault 导入文件后，
                  在域详情运行 <span className="text-blue-400">🔨 分类+构建</span> 即可自动归类。
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* ── Create Domain Modal ── */}
      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="创建领域本体">
        <div className="space-y-4">
          <Input label="标识 (英文ID)" value={newId} onChange={(e: any) => setNewId(e.target.value)} placeholder="ai-knowledge" />
          <Input label="名称" value={newName} onChange={(e: any) => setNewName(e.target.value)} placeholder="AI知识" />
          <Input label="描述" value={newDesc} onChange={(e: any) => setNewDesc(e.target.value)} placeholder="如: 覆盖AI方法、AI系统、核心概念、业务问题" />
          <Button variant="primary" loading={loading} onClick={async () => {
            if (!newId.trim() || !newName.trim()) return toast.error('请填写标识和名称');
            setLoading(true);
            try {
              await fetch(`${WIKI_API}/domains`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: newId.trim(), name: newName.trim(), description: newDesc.trim() }),
              });
              setCreateOpen(false); fetchDomains(); toast.success('创建成功！现在可以添加类和关系');
            } catch (e: any) { toast.error('创建失败'); }
            finally { setLoading(false); }
          }}>创建</Button>
        </div>
      </Modal>

      {/* ── Edit Domain Modal ── */}
      <Modal open={domainEditOpen} onClose={() => setDomainEditOpen(false)} title="编辑域信息">
        <div className="space-y-4">
          <Input label="名称" value={editDomainName} onChange={(e: any) => setEditDomainName(e.target.value)} />
          <Input label="描述" value={editDomainDesc} onChange={(e: any) => setEditDomainDesc(e.target.value)} />
          <Button variant="primary" loading={loading} onClick={async () => {
            if (!editDomainName.trim()) return toast.error('请填写名称');
            setLoading(true);
            try {
              await fetch(`${WIKI_API}/domains/${selectedDomain}`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: selectedDomain, name: editDomainName.trim(), description: editDomainDesc.trim() }),
              });
              setDomainEditOpen(false); fetchDomains(); toast.success('域信息已更新');
            } catch (e: any) { toast.error('更新失败'); }
            finally { setLoading(false); }
          }}>保存</Button>
        </div>
      </Modal>

      {/* ── Add / Edit Class Modal ── */}
      <Modal open={classOpen} onClose={() => { setClassOpen(false); setEditingClass(null); }} title={editingClass ? '编辑类' : '添加类'}>
        <div className="space-y-3">
          <Input label="类名 (英文)" value={clsName} onChange={(e: any) => setClsName(e.target.value)} placeholder="AITechnique" disabled={!!editingClass} />
          <Input label="标签" value={clsLabel} onChange={(e: any) => setClsLabel(e.target.value)} placeholder="AI方法" />
          <Input label="必填字段 (逗号分隔)" value={clsReq} onChange={(e: any) => setClsReq(e.target.value)} placeholder="name, description" />
          <Input label="可选字段 (逗号分隔)" value={clsOpt} onChange={(e: any) => setClsOpt(e.target.value)} placeholder="paper_ref, status" />
          <Input label="Wiki分类 (逗号分隔)" value={clsCat} onChange={(e: any) => setClsCat(e.target.value)} placeholder="ai-techniques" />
          <Button variant="primary" onClick={async () => {
            if (!clsName.trim() || !clsLabel.trim()) return toast.error('请填写类名和标签');
            try {
              if (editingClass) {
                await fetch(`${WIKI_API}/domains/${selectedDomain}/classes/${encodeURIComponent(editingClass)}`, {
                  method: 'PUT', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    name: clsName.trim(), label: clsLabel.trim(),
                    required_fields: clsReq.split(',').map(s => s.trim()).filter(Boolean),
                    optional_fields: clsOpt.split(',').map(s => s.trim()).filter(Boolean),
                    categories: clsCat.split(',').map(s => s.trim()).filter(Boolean),
                  }),
                });
                toast.success('类已更新');
              } else {
                await fetch(`${WIKI_API}/domains/${selectedDomain}/classes`, {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    name: clsName.trim(), label: clsLabel.trim(),
                    required_fields: clsReq.split(',').map(s => s.trim()).filter(Boolean),
                    optional_fields: clsOpt.split(',').map(s => s.trim()).filter(Boolean),
                    categories: clsCat.split(',').map(s => s.trim()).filter(Boolean),
                  }),
                });
                toast.success('类已添加');
              }
              setClassOpen(false); setEditingClass(null); fetchDomainDetail(selectedDomain);
            } catch (e: any) { toast.error(editingClass ? '更新失败' : '添加失败'); }
          }}>{editingClass ? '保存修改' : '添加类'}</Button>
        </div>
      </Modal>

      {/* ── Add / Edit Property Modal ── */}
      <Modal open={propOpen} onClose={() => { setPropOpen(false); setEditingProp(null); }} title={editingProp ? '编辑关系' : '添加关系'}>
        <div className="space-y-3">
          <Input label="关系名 (英文)" value={propName} onChange={(e: any) => setPropName(e.target.value)} placeholder="implements" disabled={!!editingProp} />
          <Input label="标签" value={propLabel} onChange={(e: any) => setPropLabel(e.target.value)} placeholder="实现" />
          <Input label="来源类 (逗号分隔)" value={propDomain} onChange={(e: any) => setPropDomain(e.target.value)} placeholder="AISystem" />
          <Input label="目标类 (逗号分隔)" value={propRange} onChange={(e: any) => setPropRange(e.target.value)} placeholder="AITechnique" />
          <Button variant="primary" onClick={async () => {
            if (!propName.trim() || !propLabel.trim() || !propDomain.trim() || !propRange.trim()) return toast.error('请填写完整');
            try {
              if (editingProp) {
                await fetch(`${WIKI_API}/domains/${selectedDomain}/properties/${encodeURIComponent(editingProp)}`, {
                  method: 'PUT', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    name: propName.trim(), label: propLabel.trim(),
                    domain: propDomain.split(',').map(s => s.trim()).filter(Boolean),
                    range: propRange.split(',').map(s => s.trim()).filter(Boolean),
                    transitive: false, symmetric: false,
                  }),
                });
                toast.success('关系已更新');
              } else {
                await fetch(`${WIKI_API}/domains/${selectedDomain}/properties`, {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    name: propName.trim(), label: propLabel.trim(),
                    domain: propDomain.split(',').map(s => s.trim()).filter(Boolean),
                    range: propRange.split(',').map(s => s.trim()).filter(Boolean),
                  }),
                });
                toast.success('关系已添加');
              }
              setPropOpen(false); setEditingProp(null); fetchDomainDetail(selectedDomain);
            } catch (e: any) { toast.error(editingProp ? '更新失败' : '添加失败'); }
          }}>{editingProp ? '保存修改' : '添加关系'}</Button>
        </div>
      </Modal>

      {/* v2.9: GrillingBridge — ontology class creation wizard */}
      {showWizard && (
        <GrillPanel
          mode="modal"
          entryPoint="ontology_edit"
          title="本体创建向导"
          onComplete={(output) => {
            setShowWizard(false);
            const flat = output.answers as Record<string, string>;
            if (flat['概念'] && flat['父类']) {
              toast.success(`已澄清概念: ${flat['概念']} (父类: ${flat['父类']})`);
            }
          }}
          onClose={() => setShowWizard(false)}
        />
      )}
    </div>
  );
};

// v2.9: Inline audit stat component
const AuditStat: React.FC<{ label: string; value: string | number; color: string }> = ({ label, value, color }) => (
  <div className="p-2 rounded bg-dark-card border border-dark-border/30 text-center">
    <div className={`text-lg font-bold ${color}`}>{value}</div>
    <div className="text-xs text-gray-500">{label}</div>
  </div>
);

export default OntologyManager;
