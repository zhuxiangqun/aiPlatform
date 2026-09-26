import { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { reportPageData, clearPageData } from '../../lib/pageDataBridge';
import { Box, ChevronRight, Plus, Trash2, Save, RefreshCw, Sparkles, ChevronDown } from 'lucide-react';
import { apiClient } from '../../services/apiClient';
import {
  DOMAIN_FILTER_CHIPS,
  domainBucket,
  type DomainFilter,
} from '../../utils/domainBuckets';
import { classDisplay, fieldDisplay, hasCjk } from '../../utils/ontologyDisplay';
import { Link } from 'react-router-dom';

interface Domain {
  id: string; name: string; description: string; version: string;
  class_count: number; property_count: number; rule_count: number;
}

interface ClassDef {
  label: string; description: string; required_fields: string[];
  optional_fields: string[]; categories: string[]; fields: any[];
  states?: any; parent?: string; synonyms?: string[];
  transitions?: any[]; side_effects?: any[];
}

function api(path: string) {
  return `/platform/apps/ontology-editor${path}`;  // apiClient prepends /api
}

export default function OntologyEditor() {
  const [searchParams] = useSearchParams();
  const [domains, setDomains] = useState<Domain[]>([]);
  const [selectedDomain, setSelectedDomain] = useState<string>('');
  const [domainFilter, setDomainFilter] = useState<DomainFilter>('preferred');
  const [schema, setSchema] = useState<any>(null);
  const [selectedClass, setSelectedClass] = useState<string>('');
  const [classData, setClassData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [newDomainId, setNewDomainId] = useState('');
  const [newDomainName, setNewDomainName] = useState('');
  const [nlDescription, setNlDescription] = useState('');
  const [generating, setGenerating] = useState(false);
  const [deletingClass, setDeletingClass] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{ name: string; title: string } | null>(null);
  const [rightPanel, setRightPanel] = useState<'class' | 'monitor' | 'maturity'>('class');
  const [stateDist, setStateDist] = useState<any>(null);
  const [bottlenecks, setBottlenecks] = useState<any>(null);
  const [slaViolations, setSlaViolations] = useState<any>(null);
  const [trends, setTrends] = useState<any>(null);
  const [engineRunning, setEngineRunning] = useState(false);
  const [engineResult, setEngineResult] = useState<string>('');
  const [scenarioData, setScenarioData] = useState<any>(null);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState<any>({});

  const fetchDomains = useCallback(async () => {
    try {
      const res = await apiClient.get<{ domains: Domain[]; total: number }>(api('/domains'));
      setDomains((res as any).domains || []);  
    } catch (e: any) {
      setError('Failed to load domains: ' + (e.message || ''));
    }
  }, []);

  useEffect(() => { fetchDomains(); }, [fetchDomains]);

  // ?domain=lock-service 预选；若当前筛选看不到该域则切到「全部」
  useEffect(() => {
    const fromUrl = (searchParams.get('domain') || '').trim();
    if (!fromUrl || !domains.length) return;
    if (!domains.some((d) => d.id === fromUrl)) return;
    setSelectedDomain(fromUrl);
    setDomainFilter((prev) =>
      prev === 'all' || domainBucket(fromUrl) === prev ? prev : 'all',
    );
  }, [domains, searchParams]);

  const visibleDomains = useMemo(() => {
    return domains.filter(
      (d) =>
        domainFilter === 'all' ||
        domainBucket(d.id) === domainFilter ||
        d.id === selectedDomain,
    );
  }, [domains, domainFilter, selectedDomain]);

  const loadSchema = useCallback(async (domainId: string) => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get<{ schema: any }>(api(`/domains/${domainId}/schema`));
      setSchema((res as any).schema);
    } catch (e: any) {
      setError('Failed to load schema: ' + (e.message || ''));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedDomain) { loadSchema(selectedDomain); setSelectedClass(''); setClassData(null); }
  }, [selectedDomain, loadSchema]);

  const selectClass = (name: string) => {
    setRightPanel('class');
    setSelectedClass(name);
    if (schema?.classes?.[name]) {
      setClassData(schema.classes[name]);
      setEditing(false);
    }
  };

  const handleCreateDomain = async () => {
    if (!newDomainId || !newDomainName) return;
    try {
      await apiClient.post(api('/domains'), { id: newDomainId, name: newDomainName });
      setShowCreate(false);
      setNewDomainId('');
      setNewDomainName('');
      fetchDomains();
    } catch (e: any) {
      setError('Failed to create domain: ' + (e.message || ''));
    }
  };

  const handleDeleteDomain = async (id: string) => {
    // 域删除仍少见；延后一帧再 confirm，避免算进 click handler 时长
    await new Promise((r) => setTimeout(r, 0));
    if (!window.confirm(`确定删除域「${id}」？不可恢复。`)) return;
    try {
      await apiClient.delete(api(`/domains/${id}`));
      if (selectedDomain === id) { setSelectedDomain(''); setSchema(null); setSelectedClass(''); }
      fetchDomains();
    } catch (e: any) {
      setError('Failed to delete: ' + (e.message || ''));
    }
  };

  const handleUpsertClass = async () => {
    if (!selectedDomain || !editForm.label) return;
    const name = editForm.class_name || editForm.label.replace(/\s/g, '');
    try {
      await apiClient.post(api(`/domains/${selectedDomain}/classes`), {
        class_name: name,
        class_data: editForm,
      });
      setEditing(false);
      loadSchema(selectedDomain);
    } catch (e: any) {
      setError('Failed to save class: ' + (e.message || ''));
    }
  };

  // 不用 window.confirm：它会同步堵住 click，Chrome 会报 handler took 1–3s
  const requestDeleteClass = (className: string) => {
    setPendingDelete({
      name: className,
      title: classDisplay({ name: className, uri: className }),
    });
  };

  const cancelPendingDelete = () => setPendingDelete(null);

  const confirmPendingDelete = async () => {
    if (!pendingDelete || !selectedDomain) return;
    const className = pendingDelete.name;
    setPendingDelete(null);
    setDeletingClass(className);
    setError('');
    try {
      await apiClient.delete(
        api(`/domains/${selectedDomain}/classes/${encodeURIComponent(className)}`),
      );
      setSelectedClass((cur) => (cur === className ? '' : cur));
      setClassData((cur) => (selectedClass === className ? null : cur));
      await Promise.all([loadSchema(selectedDomain), fetchDomains()]);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '';
      const text = typeof msg === 'object' ? (msg.message || JSON.stringify(msg)) : String(msg);
      setError(`删除失败: ${text}`);
    } finally {
      setDeletingClass(null);
    }
  };

  const handlePublish = async () => {
    try {
      await apiClient.post(api(`/domains/${selectedDomain}/publish`));
      fetchDomains();
    } catch (e: any) {
      setError('Failed to publish: ' + (e.message || ''));
    }
  };

  const handleNlGenerate = async () => {
    if (!nlDescription.trim() || !selectedDomain) return;
    setGenerating(true);
    try {
      const res = await apiClient.post<{ suggestion: any }>(api(`/domains/${selectedDomain}/generate-from-description`), {
        description: nlDescription,
      });
      setEditForm((res as any).suggestion);
      setEditing(true);
      setNlDescription('');
    } catch (e: any) {
      setError('Generation failed: ' + (e.message || ''));
    } finally {
      setGenerating(false);
    }
  };

  const runEngine = async () => {
    if (!selectedDomain) return;
    setEngineRunning(true);
    setEngineResult('Starting engine pipeline (this may take 1-3 minutes for LLM processing)...');
    try {
      const res = await apiClient.post<{ processed: number; total: number; domain: string; from_kb?: boolean }>(
        `/core/domains/${selectedDomain}/build-instances?limit=3`
      );
      const data = res as any;
      const from = data.from_kb ? 'KB documents' : 'wiki pages';
      const msg = data.processed !== undefined
        ? `Done: ${data.processed} ${from} processed`
        : data.status === 'no_pages'
          ? 'No wiki pages or KB docs found for this domain'
          : `Completed: ${data.domain ?? selectedDomain}`;
      setEngineResult(msg);
      setTimeout(() => fetchMonitor(), 3000);
    } catch (e: any) {
      setEngineResult(`Engine pipeline started (running in background — check Monitor in 2-3 min)`);
    } finally {
      setEngineRunning(false);
    }
  };

  const fetchMonitor = async () => {
    if (!selectedDomain) return;
    try {
      const [sd, bo, sl, tr] = await Promise.all([
        apiClient.get(api(`/domains/${selectedDomain}/monitor/state-distribution`)),
        apiClient.get(api(`/domains/${selectedDomain}/monitor/bottlenecks`)),
        apiClient.get(api(`/domains/${selectedDomain}/monitor/sla-violations`)),
        apiClient.get(api(`/domains/${selectedDomain}/monitor/trends?days=7`)),
      ]);
      setStateDist(sd as any);
      setBottlenecks(bo as any);
      setSlaViolations(sl as any);
      setTrends(tr as any);
    } catch {}
  };

  useEffect(() => {
    if (rightPanel === 'monitor' && selectedDomain) fetchMonitor();
  }, [rightPanel, selectedDomain]);

  const fetchScenario = async () => {
    try {
      const res = await apiClient.get('/platform/apps/ontology-editor/scenarios/recommend?mode=maturity');
      setScenarioData(res as any);
    } catch {}
  };

  useEffect(() => {
    if (rightPanel === 'maturity') fetchScenario();
  }, [rightPanel]);

  const startNewClass = () => {
    setRightPanel('class');
    setEditForm({
      label: '', description: '', required_fields: ['name', 'description'],
      optional_fields: [], categories: [], fields: [],
      states: { default: 'draft', enum: [{ name: 'draft', label: '草稿', description: '' }] },
      transitions: [], side_effects: [], synonyms: [],
    });
    setEditing(true);
  };

  // P2-4: 向数字人上报本体编辑器实时状态
  useEffect(() => {
    const classCount = schema?.classes ? Object.keys(schema.classes).length : 0;
    reportPageData('/ontology-editor', {
      domainCount: domains.length,
      selectedDomain: selectedDomain || undefined,
      classCount,
      selectedClass: selectedClass || undefined,
      hasSchema: !!schema,
    });
    return () => clearPageData('/ontology-editor');
  }, [domains, selectedDomain, schema, selectedClass]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: 'system-ui, sans-serif', fontSize: 13 }}>
      {/* 使用说明：本 Tab 是高级 YAML 编辑，日常应走「从文档生成」 */}
      <div style={{
        flexShrink: 0,
        margin: '8px 12px 0',
        padding: '10px 14px',
        borderRadius: 8,
        border: '1px solid #334155',
        background: 'linear-gradient(180deg, #0f172a 0%, #020617 100%)',
        color: '#cbd5e1',
        lineHeight: 1.55,
      }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', marginBottom: 4 }}>
          高级编辑 · 使用说明（一般可跳过）
        </div>
        <div style={{ fontSize: 12, color: '#94a3b8' }}>
          这里直接改域 YAML（类定义）。日常补知识图请用
          <Link to="/knowledge/business?tab=factory" style={{ color: '#38bdf8', margin: '0 4px' }}>从文档生成 → 确认</Link>
          ；看结构/删脏类用
          <Link to="/knowledge/business?tab=domains" style={{ color: '#38bdf8', margin: '0 4px' }}>手动画类</Link>
          。左侧默认「常用交付」；类名显示为「英文（中文）」。
        </div>
      </div>

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      {/* Left sidebar — domain list */}
      <div style={{ width: 300, borderRight: '1px solid #444', background: '#1a1a2e', padding: 12, overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <h3 style={{ margin: 0, color: '#e0e0e0', fontSize: 15 }}>业务域本体</h3>
          <button onClick={() => setShowCreate(true)} style={iconBtnStyle} title="新建域"><Plus size={16} /></button>
        </div>
        <div style={{ fontSize: 10, color: '#888', marginBottom: 8 }}>
          权威=域 YAML · 显示 {visibleDomains.length}/{domains.length}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 10 }}>
          {DOMAIN_FILTER_CHIPS.map((f) => {
            const n =
              f.id === 'all'
                ? domains.length
                : domains.filter((d) => domainBucket(d.id) === f.id).length;
            const active = domainFilter === f.id;
            return (
              <button
                key={f.id}
                type="button"
                title={f.hint}
                onClick={() => setDomainFilter(f.id)}
                style={{
                  fontSize: 10,
                  padding: '3px 7px',
                  borderRadius: 4,
                  cursor: 'pointer',
                  border: active ? '1px solid #38bdf8' : '1px solid #444',
                  background: active ? '#0c4a6e' : '#1e1e32',
                  color: active ? '#e0f2fe' : '#999',
                }}
              >
                {f.label} {n}
              </button>
            );
          })}
        </div>
        <button onClick={fetchDomains} style={{ ...iconBtnStyle, marginBottom: 8 }} title="刷新"><RefreshCw size={14} /></button>

        {showCreate && (
          <div style={{ marginBottom: 10, padding: 8, background: '#2a2a4a', borderRadius: 6 }}>
            <input placeholder="域 ID（如 lock-service）" value={newDomainId} onChange={e => setNewDomainId(e.target.value)}
              style={inputStyle} />
            <input placeholder="显示名（中文）" value={newDomainName} onChange={e => setNewDomainName(e.target.value)}
              style={{ ...inputStyle, marginTop: 4 }} />
            <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
              <button onClick={handleCreateDomain} style={btnPrimaryStyle}>创建</button>
              <button onClick={() => setShowCreate(false)} style={btnSecondaryStyle}>取消</button>
            </div>
          </div>
        )}

        {visibleDomains.length === 0 && (
          <div style={{ fontSize: 11, color: '#888', padding: '12px 4px' }}>
            当前分类下无域。点「全部」或换其它分类。
          </div>
        )}

        {visibleDomains.map(d => (
          <div key={d.id}
            onClick={() => setSelectedDomain(d.id)}
            style={{
              padding: '8px 10px', marginBottom: 4, borderRadius: 6, cursor: 'pointer',
              background: selectedDomain === d.id ? '#3a3a6a' : '#22223a',
              color: '#ccc', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
            <div>
              <div style={{ fontWeight: 600, color: '#e0e0e0' }}>{d.name}</div>
              <div style={{ fontSize: 11, color: '#888' }}>{d.id} · {d.class_count} 类 · v{d.version}</div>
            </div>
            <button onClick={(e) => { e.stopPropagation(); handleDeleteDomain(d.id); }}
              style={{ ...iconBtnStyle, opacity: 0.5 }} title="删除"><Trash2 size={13} /></button>
          </div>
        ))}
      </div>

      {/* Main panel — schema editor */}
      <div style={{ flex: 1, padding: 20, overflowY: 'auto', background: '#0f0f1a', color: '#d0d0d0' }}>
        {error && (
          <div style={{ padding: 10, marginBottom: 12, background: '#5a1a1a', borderRadius: 6, color: '#f88' }}>
            {error} <button onClick={() => setError('')} style={{ ...iconBtnStyle, marginLeft: 10 }}>×</button>
          </div>
        )}

        {pendingDelete && (
          <div style={{
            position: 'fixed', inset: 0, zIndex: 80, background: 'rgba(0,0,0,0.55)',
            display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: '18vh',
          }}>
            <div style={{
              width: '100%', maxWidth: 400, margin: '0 16px', padding: 16,
              background: '#1e1e32', border: '1px solid #444', borderRadius: 10, color: '#e2e8f0',
            }}>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>确认删除类？</div>
              <div style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.5, marginBottom: 14 }}>
                将删除「{pendingDelete.title}」。走说明书提案写入（非直接改 YAML）。脏类可删；真类请谨慎。
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button type="button" onClick={cancelPendingDelete} style={btnSecondaryStyle}>取消</button>
                <button
                  type="button"
                  onClick={() => { void confirmPendingDelete(); }}
                  style={{ ...btnPrimaryStyle, background: '#b91c1c' }}
                >
                  确认删除
                </button>
              </div>
            </div>
          </div>
        )}

        {deletingClass && (
          <div style={{
            marginBottom: 12, padding: '8px 12px', borderRadius: 6,
            background: '#0c4a6e', border: '1px solid #0369a1', color: '#e0f2fe', fontSize: 12,
          }}>
            正在删除「{classDisplay({ name: deletingClass, uri: deletingClass })}」…（提案写入中）
          </div>
        )}

        {!selectedDomain ? (
          <div style={{ textAlign: 'center', marginTop: 80, color: '#666' }}>
            <Box size={48} style={{ marginBottom: 12 }} />
            <p style={{ color: '#94a3b8' }}>从左侧选一个业务域（默认「常用交付」里找 lock-service）</p>
            <p style={{ fontSize: 12, color: '#64748b', marginTop: 8 }}>
              不确定？请先回「从文档生成」，这里只改说明书 YAML。
            </p>
          </div>
        ) : loading ? (
          <div style={{ textAlign: 'center', marginTop: 100, color: '#94a3b8' }}>加载中…</div>
        ) : (
          <div style={{ display: 'flex', gap: 20 }}>
            {/* Class list */}
            <div style={{ width: 280, flexShrink: 0 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10, alignItems: 'center', gap: 8 }}>
                <h3 style={{ margin: 0, fontSize: 14 }}>
                  {schema?.name || selectedDomain} · 类
                </h3>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', justifyContent: 'flex-end', alignItems: 'center' }}>
                  {([
                    { id: 'class' as const, label: '类定义', hint: '属性 / 状态机 / 转移动作 / 关系（日常只看这个）' },
                    { id: 'monitor' as const, label: '运行监控', hint: '引擎运行后的状态分布、卡点、SLA（进阶，不是改类）' },
                  ]).map((p) => {
                    const active = rightPanel === p.id;
                    return (
                      <button
                        key={p.id}
                        type="button"
                        title={p.hint}
                        onClick={() => setRightPanel(p.id)}
                        style={{
                          ...btnSecondaryStyle,
                          fontSize: 11,
                          padding: '3px 8px',
                          border: active ? '1px solid #38bdf8' : '1px solid #444',
                          background: active ? '#0c4a6e' : undefined,
                          color: active ? '#e0f2fe' : undefined,
                        }}
                      >
                        {p.label}
                      </button>
                    );
                  })}
                  <button
                    type="button"
                    title="各域成熟度排名（平台参考，与改当前类无关）"
                    onClick={() => setRightPanel('maturity')}
                    style={{
                      fontSize: 10,
                      padding: '2px 6px',
                      borderRadius: 4,
                      border: 'none',
                      background: 'transparent',
                      color: rightPanel === 'maturity' ? '#38bdf8' : '#64748b',
                      cursor: 'pointer',
                      textDecoration: 'underline',
                    }}
                  >
                    成熟度?
                  </button>
                  <button onClick={startNewClass} style={iconBtnStyle} title="新建类"><Plus size={15} /></button>
                  <button onClick={handlePublish} style={iconBtnStyle} title="发布"><Save size={15} /></button>
                </div>
              </div>
              <div style={{ fontSize: 10, color: '#64748b', marginBottom: 8, lineHeight: 1.45 }}>
                {rightPanel === 'class' && (
                  <>
                    <b style={{ color: '#94a3b8' }}>类定义</b>：右侧分四块 —
                    ①属性（字段）②状态机 ③转移/动作 ④关系。点左侧类查看。
                  </>
                )}
                {rightPanel === 'monitor' && (
                  <>运行监控看的是<strong style={{ color: '#94a3b8' }}>已跑起来的实例</strong>，不是改说明书 YAML。</>
                )}
                {rightPanel === 'maturity' && (
                  <>成熟度是全平台域排名，<strong style={{ color: '#fbbf24' }}>与当前类无关</strong>。请点「类定义」回来。</>
                )}
              </div>

              {/* NL→YAML generator */}
              <div style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', gap: 4 }}>
                  <input placeholder="用自然语言描述要新增的类…"
                    value={nlDescription} onChange={e => setNlDescription(e.target.value)}
                    style={{ ...inputStyle, flex: 1, fontSize: 11 }} />
                  <button onClick={handleNlGenerate} disabled={generating || !nlDescription.trim()}
                    style={{ ...btnPrimaryStyle, padding: '4px 8px' }} title="生成">
                    {generating ? '…' : <><Sparkles size={13} /> 生成</>}
                  </button>
                </div>
              </div>

              {schema?.classes && Object.entries(schema.classes as Record<string, any>)
                .sort(([a], [b]) => {
                  // 中文 id / 疑似脏类沉底
                  const aDirty = hasCjk(a) ? 1 : 0;
                  const bDirty = hasCjk(b) ? 1 : 0;
                  if (aDirty !== bDirty) return aDirty - bDirty;
                  return a.localeCompare(b);
                })
                .map(([name, cls]) => {
                const title = classDisplay({ name, uri: name, label: cls?.label });
                const dirty = hasCjk(name) && cls?.label && !hasCjk(String(cls.label));
                return (
                <div key={name}
                  onClick={() => selectClass(name)}
                  style={{
                    padding: '6px 10px', marginBottom: 3, borderRadius: 5, cursor: 'pointer',
                    background: selectedClass === name ? '#3a3a6a' : '#1a1a2e',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    border: dirty ? '1px solid #7f1d1d' : '1px solid transparent',
                  }}>
                  <div>
                    <div style={{ fontWeight: 500, color: '#e2e8f0' }}>{title}</div>
                    {dirty && (
                      <div style={{ fontSize: 10, color: '#fca5a5' }}>疑似脏类（实例被抬成了类）</div>
                    )}
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); requestDeleteClass(name); }}
                    disabled={deletingClass === name}
                    style={{ ...iconBtnStyle, opacity: deletingClass === name ? 0.8 : 0.4 }}
                    title="删除"
                  >
                    {deletingClass === name ? <RefreshCw size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Trash2 size={12} />}
                  </button>
                </div>
              );})}
            </div>

             {/* Monitor panel */}
             {rightPanel === 'monitor' && (
               <div style={{ flex: 1 }}>
                 <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                   <h4 style={{ margin: 0, fontSize: 13, color: '#888' }}>状态分布</h4>
                   <button
                     onClick={runEngine}
                     disabled={engineRunning}
                     style={{
                       display: 'flex', alignItems: 'center', gap: 6,
                       padding: '4px 12px', borderRadius: 6,
                       background: engineRunning ? '#333' : '#4f46e5',
                       color: '#fff', border: 'none', cursor: engineRunning ? 'wait' : 'pointer',
                       fontSize: 12, fontWeight: 500,
                     }}
                   >
                     <RefreshCw size={13} style={engineRunning ? { animation: 'spin 1s linear infinite' } : undefined} />
                     {engineRunning ? '运行中…' : '跑引擎'}
                   </button>
                 </div>
                 {engineResult && (
                   <div style={{
                     padding: '4px 10px', marginBottom: 8, borderRadius: 4,
                     background: engineResult.startsWith('Done') || engineResult.startsWith('Completed') ? '#1a3a2a' : '#3a1a1a',
                     color: '#ccc', fontSize: 11,
                   }}>
                     {engineResult}
                   </div>
                 )}
                {stateDist?.distribution?.length ? (
                  <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                    {(() => {
                      const grouped: Record<string, any[]> = {};
                      stateDist.distribution.forEach((d: any) => {
                        (grouped[d.class_name] = grouped[d.class_name] || []).push(d);
                      });
                      return Object.entries(grouped).map(([cls, items]) => (
                        <div key={cls} style={{ marginBottom: 10 }}>
                          <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 4 }}>{cls}</div>
                          {items.map((d: any, i: number) => (
                            <span key={i} style={{
                              display: 'inline-block', padding: '2px 8px', margin: 2,
                              background: '#2a2a4a', borderRadius: 4, fontSize: 11,
                            }}>
                              {d.state_name}: {d.count}
                            </span>
                          ))}
                        </div>
                      ));
                    })()}
                  </div>
                ) : (
                  <div style={{ color: '#555', fontSize: 12 }}>暂无状态数据。点「跑引擎」后才会有。</div>
                )}
                <h4 style={{ margin: '16px 0 12px', fontSize: 13, color: '#888' }}>卡点</h4>
                {bottlenecks?.bottlenecks?.length ? (
                  <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                    {bottlenecks.bottlenecks.map((b: any, i: number) => (
                      <div key={i} style={{
                        padding: '6px 10px', marginBottom: 4, borderRadius: 4,
                        background: '#2a1a1a', fontSize: 11, display: 'flex', justifyContent: 'space-between',
                      }}>
                        <span>{b.entity_name} ({b.class_name}: {b.current_state})</span>
                        <span style={{ color: '#f88' }}>{Math.round(b.stuck_seconds / 60)}m</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ color: '#555', fontSize: 12 }}>未检测到卡点。</div>
                )}
                <h4 style={{ margin: '16px 0 12px', fontSize: 13, color: '#f88' }}>SLA 违规</h4>
                {slaViolations?.violations?.length ? (
                  <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                    {slaViolations.violations.map((v: any, i: number) => (
                      <div key={i} style={{
                        padding: '6px 10px', marginBottom: 4, borderRadius: 4,
                        background: '#3a1a1a', fontSize: 11, display: 'flex', justifyContent: 'space-between',
                      }}>
                        <span>{v.entity_name} ({v.class_name}: {v.from_state} → {v.to_state})</span>
                        <span style={{ color: '#faa' }}>{v.description || 'SLA breach'}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ color: '#555', fontSize: 12 }}>无 SLA 违规。</div>
                )}
                <h4 style={{ margin: '16px 0 12px', fontSize: 13, color: '#888' }}>7 日趋势</h4>
                {trends?.trends?.length ? (
                  <div style={{ fontSize: 11 }}>
                    {trends.trends.map((d: any, i: number) => (
                      <div key={i} style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '4px 8px', marginBottom: 2, background: '#1a1a2e', borderRadius: 4,
                      }}>
                        <span style={{ color: '#888', width: 80 }}>{d.date.slice(5)}</span>
                        <div style={{ flex: 1, height: 8, background: '#222', borderRadius: 4, margin: '0 8px', overflow: 'hidden' }}>
                          <div style={{
                            height: '100%', background: d.total > 0 ? '#4a4aff' : '#333',
                            width: `${Math.min(100, (d.total || 0) * 5)}%`,
                            borderRadius: 4, transition: 'width 0.3s',
                          }} />
                        </div>
                        <span style={{ color: '#ccc', minWidth: 30, textAlign: 'right' }}>{d.total || 0}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ color: '#555', fontSize: 12 }}>暂无趋势数据。</div>
                )}
              </div>
            )}

            {/* Scenario selection panel */}
            {rightPanel === 'maturity' && (
              <div style={{ flex: 1 }}>
                <h4 style={{ margin: '0 0 12px', fontSize: 13, color: '#888' }}>
                  域成熟度排名（参考 · 非改类）
                </h4>
                {scenarioData?.recommendations?.length ? (
                  <div style={{ maxHeight: 500, overflowY: 'auto' }}>
                    {scenarioData.recommendations.map((r: any, i: number) => (
                      <div key={i} style={{
                        padding: '12px', marginBottom: 8, borderRadius: 6,
                        background: r.recommendation === 'build_first' ? '#1a2a1a' : '#1a1a2e',
                        border: r.recommendation === 'build_first' ? '1px solid #3a3' : '1px solid #333',
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                          <span style={{ fontWeight: 600, fontSize: 13 }}>
                            {r.domain_id}
                            <span style={{ color: '#888', marginLeft: 8, fontSize: 11 }}>
                              ({r.level || r.maturity_score})
                            </span>
                          </span>
                          <span style={{
                            padding: '2px 8px', borderRadius: 4, fontSize: 11,
                            background: r.recommendation === 'build_first' ? '#3a3' : '#666',
                            color: '#fff',
                          }}>
                            {r.recommendation === 'build_first' ? 'P0 优先' : r.recommendation === 'plan_second' ? 'P1 计划' : '延后'}
                          </span>
                        </div>
                        <div style={{ fontSize: 11, color: '#888' }}>
                          Maturity: {r.maturity_score} | Gap: {r.gap_cost_hours || '?'} hours
                        </div>
                        {r.value_formula && (
                          <div style={{
                            marginTop: 8, padding: '6px 10px', background: '#111', borderRadius: 4,
                            fontSize: 11, color: '#aaa', fontStyle: 'italic',
                          }}>
                            {r.value_formula}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ color: '#555', fontSize: 12 }}>
                    暂无域数据。请先创建域。
                  </div>
                )}
              </div>
            )}

            {/* Class detail / edit panel */}
            {rightPanel === 'class' && (
            <div style={{ flex: 1 }}>
              {editing ? (
                <ClassEditForm
                  data={editForm}
                  onChange={setEditForm}
                  onSave={handleUpsertClass}
                  onCancel={() => setEditing(false)}
                />
              ) : classData ? (
                <ClassDetail
                  name={selectedClass}
                  data={classData}
                  domainProps={schema?.object_properties || schema?.properties || []}
                  onEdit={() => { setEditForm({ ...classData, class_name: selectedClass }); setEditing(true); }}
                />
              ) : (
                <div style={{ textAlign: 'center', marginTop: 60, color: '#64748b' }}>
                  点左侧类查看「属性 / 状态 / 动作」分区，或点 <Plus size={14} style={{ verticalAlign: 'middle' }} /> 新建
                </div>
              )}
            </div>
            )}
          </div>
        )}
      </div>
      </div>
    </div>
  );
}

function ClassDetail({
  name,
  data,
  domainProps,
  onEdit,
}: {
  name: string;
  data: any;
  domainProps?: any[];
  onEdit: () => void;
}) {
  const title = classDisplay({ name, uri: name, label: data?.label });
  const dirty = hasCjk(name);
  const req = data.required_fields || [];
  const opt = data.optional_fields || [];
  const custom = data.fields || [];
  const states = data.states?.enum || [];
  // YAML 约定：transitions 嵌在 states 下（states.transitions），兼容顶层 transitions
  const transitions = data.states?.transitions || data.transitions || [];
  const sideEffects = data.side_effects || [];
  const synonyms = data.synonyms || [];
  const relatedProps = (domainProps || []).filter((p: any) => {
    const d = String(p.domain || p.from || '');
    const r = String(p.range || p.to || '');
    return d.includes(name) || r.includes(name) || d.endsWith(name) || r.endsWith(name);
  });

  const fmtFrom = (from: unknown): string => {
    if (Array.isArray(from)) return from.map(String).join(', ');
    if (from == null || from === '') return '*';
    return String(from);
  };

  const fmtTrigger = (t: any): string => {
    const trig = t?.trigger || t?.action;
    if (!trig) return '';
    if (typeof trig === 'string') return `动作：${trig}`;
    if (typeof trig !== 'object') return '';
    const typ = String(trig.type || '');
    if (typ === 'action' || trig.action_id) {
      return `动作：${trig.action_id || trig.action || '?'}`;
    }
    if (typ === 'relation_exists') {
      return `条件：存在关系 ${trig.relation || '?'}`;
    }
    if (typ === 'relation_count') {
      const op = trig.operator || '>=';
      return `条件：关系 ${trig.relation || '?'} 数量 ${op} ${trig.threshold ?? '?'}`;
    }
    return JSON.stringify(trig);
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, gap: 8 }}>
        <h3 style={{ margin: 0 }}>{title}</h3>
        <button onClick={onEdit} style={btnSecondaryStyle}>编辑</button>
      </div>
      {dirty && (
        <div style={{ fontSize: 11, color: '#fca5a5', background: '#450a0a', border: '1px solid #7f1d1d', borderRadius: 6, padding: '6px 10px', marginBottom: 12 }}>
          疑似脏类：类 ID 是中文/像实例名。建议在「手动画类」删除，真类应是英文 ID（如 InstallOrder）。
        </div>
      )}
      {data.description && <p style={{ color: '#aaa', marginBottom: 14, fontSize: 12 }}>{data.description}</p>}

      <Block title="① 属性（字段）" hint="实例上要填的数据项。必填 / 可选 / 自定义枚举。">
        <div style={{ fontSize: 12, marginBottom: 6 }}>
          <span style={{ color: '#94a3b8' }}>必填：</span>
          {req.length
            ? req.map((f: string) => fieldDisplay(f, custom)).join('、')
            : <span style={{ color: '#555' }}>无</span>}
        </div>
        <div style={{ fontSize: 12, marginBottom: 6 }}>
          <span style={{ color: '#94a3b8' }}>可选：</span>
          {opt.length
            ? opt.map((f: string) => fieldDisplay(f, custom)).join('、')
            : <span style={{ color: '#555' }}>无</span>}
        </div>
        {custom.length > 0 ? (
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ color: '#888' }}>
                <th style={{ textAlign: 'left' }}>字段</th>
                <th style={{ textAlign: 'left' }}>类型</th>
                <th style={{ textAlign: 'left' }}>取值</th>
              </tr>
            </thead>
            <tbody>
              {custom.map((f: any, i: number) => (
                <tr key={i}>
                  <td style={{ padding: '2px 8px 2px 0' }}>{fieldDisplay(f.name, custom)}</td>
                  <td>{f.type}</td>
                  <td>{f.values?.join(', ') || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ fontSize: 11, color: '#555' }}>无额外自定义字段</div>
        )}
      </Block>

      <Block title="② 状态机" hint="实例生命周期有哪些状态（如 pending → accepted）。">
        {states.length ? (
          <>
            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 6 }}>
              默认状态：{data.states?.default || '—'}
            </div>
            {states.map((s: any) => (
              <span key={s.name} style={{ display: 'inline-block', padding: '2px 8px', margin: 2, background: '#2a2a4a', borderRadius: 4, fontSize: 12 }}>
                {s.label || s.name}
              </span>
            ))}
          </>
        ) : (
          <EmptyHint text="未定义状态（静态类，如设备型号，通常不需要）" />
        )}
      </Block>

      <Block title="③ 转移 / 动作" hint="状态怎么跳转；写在 states.transitions。触发器=动作或关系条件。">
        {transitions.length ? (
          transitions.map((t: any, i: number) => {
            const fromList = Array.isArray(t.from) ? t.from : t.from != null ? [t.from] : [];
            const trigger = t.trigger || {};
            const triggerType = trigger.type || t.type || '';
            let triggerText = '';
            if (triggerType === 'action' || trigger.action_id || t.action) {
              const aid =
                trigger.action_id ||
                (typeof t.action === 'string' ? t.action : t.action?.action_id) ||
                '';
              triggerText = `动作 ${aid || '（未写 action_id）'}`;
            } else if (triggerType === 'relation_exists') {
              triggerText = `存在关系 ${trigger.relation || '?'}`;
            } else if (triggerType === 'relation_count') {
              triggerText = `关系 ${trigger.relation || '?'} 数量 ${trigger.operator || '>='} ${trigger.threshold ?? ''}`;
            } else if (triggerType) {
              triggerText = `${triggerType}`;
            } else if (t.description) {
              triggerText = t.description;
            }
            return (
              <div key={i} style={{ fontSize: 12, marginBottom: 6, padding: '6px 8px', background: '#1a1a2e', borderRadius: 4 }}>
                <div>
                  <span style={{ color: '#94a3b8' }}>转移：</span>
                  [{fromList.join(', ')}] → {t.to}
                </div>
                {triggerText && (
                  <div style={{ color: '#86efac', marginTop: 2 }}>触发：{triggerText}</div>
                )}
                {t.description && !triggerText.includes(t.description) && (
                  <div style={{ color: '#888', marginTop: 2 }}>{t.description}</div>
                )}
              </div>
            );
          })
        ) : (
          <EmptyHint text={states.length ? '有状态但无转移规则（states.transitions 为空）' : '无转移规则（静态类通常不需要）'} />
        )}
        {sideEffects.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 4 }}>联动副作用</div>
            {sideEffects.map((s: any, i: number) => (
              <div key={i} style={{ fontSize: 12, marginBottom: 4 }}>
                时机 {s.when}：{(s.actions || []).map((a: any) => a.type || a.action_id || '?').join('、') || '—'}
              </div>
            ))}
          </div>
        )}
      </Block>

      <Block title="④ 关系（连到其他类）" hint="说明书里的对象属性：本类作为起点/终点。结构图上的线来自这里。">
        {relatedProps.length ? (
          relatedProps.map((p: any, i: number) => {
            const fromRaw = String(p.domain || p.from || '?').replace(/^.*[#/]/, '');
            const toRaw = String(p.range || p.to || '?').replace(/^.*[#/]/, '');
            const fromLabel = fromRaw.split(',').map((x: string) => classDisplay({ name: x.trim(), uri: x.trim() })).join('、');
            const toLabel = toRaw.split(',').map((x: string) => classDisplay({ name: x.trim(), uri: x.trim() })).join('、');
            return (
            <div key={i} style={{ fontSize: 12, marginBottom: 4 }}>
              {p.label || p.name || p.uri || 'rel'}：
              <span style={{ color: '#94a3b8' }}>{fromLabel}</span>
              {' → '}
              <span style={{ color: '#94a3b8' }}>{toLabel}</span>
            </div>
            );
          })
        ) : (
          <EmptyHint text="本类暂无关联的对象属性（可在手动画类/结构图查看全域关系）" />
        )}
      </Block>

      {(data.categories?.length > 0 || synonyms.length > 0) && (
        <Block title="⑤ 其它" hint="分类标签、同义词（检索别名）。">
          {data.categories?.length > 0 && (
            <div style={{ fontSize: 12, marginBottom: 4 }}>分类：{data.categories.join('、')}</div>
          )}
          {synonyms.length > 0 && (
            <div style={{ fontSize: 12 }}>同义词：{synonyms.join('、')}</div>
          )}
        </Block>
      )}
    </div>
  );
}

function Block({
  title,
  hint,
  children,
}: {
  title: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ marginBottom: 14, padding: '10px 12px', borderRadius: 8, border: '1px solid #334155', background: '#0f172a' }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', marginBottom: 2 }}>{title}</div>
      <div style={{ fontSize: 11, color: '#64748b', marginBottom: 8 }}>{hint}</div>
      {children}
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return <div style={{ fontSize: 11, color: '#555' }}>{text}</div>;
}

function ClassEditForm({ data, onChange, onSave, onCancel }: { data: any; onChange: (d: any) => void; onSave: () => void; onCancel: () => void }) {
  const update = (key: string, value: any) => onChange({ ...data, [key]: value });

  return (
    <div>
      <h3 style={{ marginBottom: 16 }}>{data.class_name || '新类'}（编辑中）</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
        <Field label="类名（英文 ID）" value={data.class_name || ''} onChange={v => update('class_name', v)} />
        <Field label="中文标签" value={data.label || ''} onChange={v => update('label', v)} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>描述</label>
        <textarea value={data.description || ''} onChange={e => update('description', e.target.value)}
          style={{ ...inputStyle, width: '100%', minHeight: 60, resize: 'vertical' }} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>必填字段（逗号分隔）</label>
        <input value={(data.required_fields || []).join(', ')} onChange={e => update('required_fields', e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean))}
          style={{ ...inputStyle, width: '100%' }} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>可选字段（逗号分隔）</label>
        <input value={(data.optional_fields || []).join(', ')} onChange={e => update('optional_fields', e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean))}
          style={{ ...inputStyle, width: '100%' }} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>分类（逗号分隔）</label>
        <input value={(data.categories || []).join(', ')} onChange={e => update('categories', e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean))}
          style={{ ...inputStyle, width: '100%' }} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>同义词（逗号分隔）</label>
        <input value={(data.synonyms || []).join(', ')} onChange={e => update('synonyms', e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean))}
          style={{ ...inputStyle, width: '100%' }} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>状态 JSON</label>
        <textarea value={JSON.stringify(data.states || {}, null, 2)}
          onChange={e => { try { update('states', JSON.parse(e.target.value)); } catch {} }}
          style={{ ...inputStyle, width: '100%', minHeight: 100, fontFamily: 'monospace', fontSize: 11, resize: 'vertical' }} />
      </div>
      <div style={{ display: 'flex', gap: 10 }}>
        <button onClick={onSave} style={btnPrimaryStyle}>保存类</button>
        <button onClick={onCancel} style={btnSecondaryStyle}>取消</button>
      </div>
    </div>
  );
}


function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <input value={value} onChange={e => onChange(e.target.value)} style={{ ...inputStyle, width: '100%' }} />
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: '6px 10px', borderRadius: 4, border: '1px solid #444',
  background: '#1a1a2e', color: '#e0e0e0', fontSize: 12, outline: 'none',
};

const labelStyle: React.CSSProperties = {
  display: 'block', marginBottom: 4, fontSize: 11, color: '#888', textTransform: 'uppercase',
};

const btnPrimaryStyle: React.CSSProperties = {
  padding: '6px 14px', background: '#4a4aff', color: '#fff', border: 'none', borderRadius: 5,
  cursor: 'pointer', fontSize: 12, fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 4,
};

const btnSecondaryStyle: React.CSSProperties = {
  padding: '6px 14px', background: '#2a2a4a', color: '#ccc', border: '1px solid #444', borderRadius: 5,
  cursor: 'pointer', fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 4,
};

const iconBtnStyle: React.CSSProperties = {
  background: 'none', border: 'none', color: '#888', cursor: 'pointer', padding: 2,
  display: 'inline-flex', alignItems: 'center',
};
