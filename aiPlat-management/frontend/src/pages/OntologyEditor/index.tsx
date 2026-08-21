import { useState, useEffect, useCallback } from 'react';
import { reportPageData, clearPageData } from '../../lib/pageDataBridge';
import { Box, ChevronRight, Plus, Trash2, Save, RefreshCw, Sparkles, ChevronDown } from 'lucide-react';
import { apiClient } from '../../services/apiClient';

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
  const [domains, setDomains] = useState<Domain[]>([]);
  const [selectedDomain, setSelectedDomain] = useState<string>('');
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
  const [monitorTab, setMonitorTab] = useState(false);
  const [scenarioTab, setScenarioTab] = useState(false);
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
    if (!confirm(`Delete domain "${id}"? This cannot be undone.`)) return;
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

  const handleDeleteClass = async (className: string) => {
    if (!confirm(`Delete class "${className}"?`)) return;
    try {
      await apiClient.delete(api(`/domains/${selectedDomain}/classes/${className}`));
      setSelectedClass('');
      setClassData(null);
      loadSchema(selectedDomain);
    } catch (e: any) {
      setError('Failed to delete class: ' + (e.message || ''));
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
    if (monitorTab && selectedDomain) fetchMonitor();
  }, [monitorTab, selectedDomain]);

  const fetchScenario = async () => {
    try {
      const res = await apiClient.get('/platform/apps/ontology-editor/scenarios/recommend?mode=maturity');
      setScenarioData(res as any);
    } catch {}
  };

  useEffect(() => {
    if (scenarioTab) fetchScenario();
  }, [scenarioTab]);

  const startNewClass = () => {
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
    <div style={{ display: 'flex', height: '100vh', fontFamily: 'monospace', fontSize: 13 }}>
      {/* Left sidebar — domain list */}
      <div style={{ width: 280, borderRight: '1px solid #444', background: '#1a1a2e', padding: 12, overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <h3 style={{ margin: 0, color: '#e0e0e0', fontSize: 15 }}>Ontology Domains</h3>
          <button onClick={() => setShowCreate(true)} style={iconBtnStyle} title="Create domain"><Plus size={16} /></button>
        </div>
        <button onClick={fetchDomains} style={{ ...iconBtnStyle, marginBottom: 8 }} title="Refresh"><RefreshCw size={14} /></button>

        {showCreate && (
          <div style={{ marginBottom: 10, padding: 8, background: '#2a2a4a', borderRadius: 6 }}>
            <input placeholder="domain_id" value={newDomainId} onChange={e => setNewDomainId(e.target.value)}
              style={inputStyle} />
            <input placeholder="Display name" value={newDomainName} onChange={e => setNewDomainName(e.target.value)}
              style={{ ...inputStyle, marginTop: 4 }} />
            <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
              <button onClick={handleCreateDomain} style={btnPrimaryStyle}>Create</button>
              <button onClick={() => setShowCreate(false)} style={btnSecondaryStyle}>Cancel</button>
            </div>
          </div>
        )}

        {domains.map(d => (
          <div key={d.id}
            onClick={() => setSelectedDomain(d.id)}
            style={{
              padding: '8px 10px', marginBottom: 4, borderRadius: 6, cursor: 'pointer',
              background: selectedDomain === d.id ? '#3a3a6a' : '#22223a',
              color: '#ccc', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
            <div>
              <div style={{ fontWeight: 600, color: '#e0e0e0' }}>{d.name}</div>
              <div style={{ fontSize: 11, color: '#888' }}>{d.id} · {d.class_count} classes · v{d.version}</div>
            </div>
            <button onClick={(e) => { e.stopPropagation(); handleDeleteDomain(d.id); }}
              style={{ ...iconBtnStyle, opacity: 0.5 }} title="Delete"><Trash2 size={13} /></button>
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

        {!selectedDomain ? (
          <div style={{ textAlign: 'center', marginTop: 100, color: '#666' }}>
            <Box size={48} style={{ marginBottom: 12 }} />
            <p>Select a domain from the left panel to edit its ontology schema</p>
          </div>
        ) : loading ? (
          <div style={{ textAlign: 'center', marginTop: 100 }}>Loading...</div>
        ) : (
          <div style={{ display: 'flex', gap: 20 }}>
            {/* Class list */}
            <div style={{ width: 260, flexShrink: 0 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                <h3 style={{ margin: 0, fontSize: 14 }}>{schema?.name || selectedDomain} Classes</h3>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button onClick={() => { setMonitorTab(false); setScenarioTab(!scenarioTab); }}
                    style={{ ...btnSecondaryStyle, fontSize: 11, padding: '3px 8px' }}>
                    {scenarioTab ? 'Classes' : 'Scenarios'}
                  </button>
                  <button onClick={() => { setScenarioTab(false); setMonitorTab(!monitorTab); }}
                    style={{ ...btnSecondaryStyle, fontSize: 11, padding: '3px 8px' }}>
                    {monitorTab ? 'Classes' : 'Monitor'}
                  </button>
                  <button onClick={startNewClass} style={iconBtnStyle} title="New class"><Plus size={15} /></button>
                  <button onClick={handlePublish} style={iconBtnStyle} title="Publish"><Save size={15} /></button>
                </div>
              </div>

              {/* NL→YAML generator */}
              <div style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', gap: 4 }}>
                  <input placeholder="Describe a new class in natural language..."
                    value={nlDescription} onChange={e => setNlDescription(e.target.value)}
                    style={{ ...inputStyle, flex: 1, fontSize: 11 }} />
                  <button onClick={handleNlGenerate} disabled={generating || !nlDescription.trim()}
                    style={{ ...btnPrimaryStyle, padding: '4px 8px' }} title="Generate">
                    {generating ? '...' : <><Sparkles size={13} /> Gen</>}
                  </button>
                </div>
              </div>

              {schema?.classes && Object.entries(schema.classes as Record<string, any>).map(([name, cls]) => (
                <div key={name}
                  onClick={() => selectClass(name)}
                  style={{
                    padding: '6px 10px', marginBottom: 3, borderRadius: 5, cursor: 'pointer',
                    background: selectedClass === name ? '#3a3a6a' : '#1a1a2e',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  }}>
                  <div>
                    <div style={{ fontWeight: 500 }}>{name}</div>
                    <div style={{ fontSize: 11, color: '#888' }}>{cls.label}</div>
                  </div>
                  <button onClick={(e) => { e.stopPropagation(); handleDeleteClass(name); }}
                    style={{ ...iconBtnStyle, opacity: 0.4 }}><Trash2 size={12} /></button>
                </div>
              ))}
            </div>

             {/* Monitor panel */}
             {monitorTab && (
               <div style={{ flex: 1 }}>
                 <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                   <h4 style={{ margin: 0, fontSize: 13, color: '#888' }}>State Distribution</h4>
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
                     {engineRunning ? (
                       <RefreshCw size={13} style={{ animation: 'spin 1s linear infinite' }} />
                     ) : (
                       <RefreshCw size={13} />
                     )}
                     {engineRunning ? 'Running…' : 'Run Engine'}
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
                  <div style={{ color: '#555', fontSize: 12 }}>No state data yet. Run the ontology engine to populate.</div>
                )}
                <h4 style={{ margin: '16px 0 12px', fontSize: 13, color: '#888' }}>Bottlenecks</h4>
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
                  <div style={{ color: '#555', fontSize: 12 }}>No bottlenecks detected.</div>
                )}
                <h4 style={{ margin: '16px 0 12px', fontSize: 13, color: '#f88' }}>SLA Violations</h4>
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
                  <div style={{ color: '#555', fontSize: 12 }}>No SLA violations.</div>
                )}
                <h4 style={{ margin: '16px 0 12px', fontSize: 13, color: '#888' }}>7-Day Trend</h4>
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
                  <div style={{ color: '#555', fontSize: 12 }}>No trend data yet.</div>
                )}
              </div>
            )}

            {/* Scenario selection panel */}
            {scenarioTab && (
              <div style={{ flex: 1 }}>
                <h4 style={{ margin: '0 0 12px', fontSize: 13, color: '#888' }}>
                  Domain Maturity — Build Priority
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
                    No domains registered. Create domains first.
                  </div>
                )}
              </div>
            )}

            {/* Class detail / edit panel */}
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
                  onEdit={() => { setEditForm({ ...classData, class_name: selectedClass }); setEditing(true); }}
                />
              ) : (
                <div style={{ textAlign: 'center', marginTop: 60, color: '#555' }}>
                  Select a class or click <Plus size={14} style={{ verticalAlign: 'middle' }} /> to create one
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ClassDetail({ name, data, onEdit }: { name: string; data: any; onEdit: () => void }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ margin: 0 }}>{name} <span style={{ color: '#888', fontWeight: 400 }}>({data.label})</span></h3>
        <button onClick={onEdit} style={btnSecondaryStyle}>Edit</button>
      </div>
      {data.description && <p style={{ color: '#aaa', marginBottom: 16 }}>{data.description}</p>}

      <Section title="Required Fields">
        {data.required_fields?.length ? data.required_fields.join(', ') : <span style={{ color: '#666' }}>none</span>}
      </Section>
      <Section title="Optional Fields">
        {data.optional_fields?.length ? data.optional_fields.join(', ') : <span style={{ color: '#666' }}>none</span>}
      </Section>
      <Section title="Categories">{data.categories?.join(', ') || 'none'}</Section>
      <Section title="Custom Fields">
        {data.fields?.length ? (
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
            <thead><tr style={{ color: '#888' }}><th style={{ textAlign: 'left' }}>Name</th><th style={{ textAlign: 'left' }}>Type</th><th style={{ textAlign: 'left' }}>Values</th></tr></thead>
            <tbody>
              {data.fields.map((f: any, i: number) => (
                <tr key={i}><td style={{ padding: '2px 8px 2px 0' }}>{f.name}</td><td>{f.type}</td><td>{f.values?.join(', ') || '-'}</td></tr>
              ))}
            </tbody>
          </table>
        ) : <span style={{ color: '#666' }}>none</span>}
      </Section>
      {data.states?.enum && (
        <Section title={`States (default: ${data.states.default || '—'})`}>
          {data.states.enum.map((s: any) => (
            <span key={s.name} style={{ display: 'inline-block', padding: '2px 8px', margin: 2, background: '#2a2a4a', borderRadius: 4, fontSize: 12 }}>
              {s.label || s.name}
            </span>
          ))}
        </Section>
      )}
      {data.transitions?.length > 0 && (
        <Section title="Transitions">
          {data.transitions.map((t: any, i: number) => (
            <div key={i} style={{ fontSize: 12, marginBottom: 4 }}>
              [{t.from?.join(', ')}] → {t.to}: {t.description}
            </div>
          ))}
        </Section>
      )}
      {data.side_effects?.length > 0 && (
        <Section title="Side Effects">
          {data.side_effects.map((s: any, i: number) => (
            <div key={i} style={{ fontSize: 12 }}>
              {s.when}: {s.actions?.map((a: any) => a.type).join(', ')}
            </div>
          ))}
        </Section>
      )}
      {data.synonyms?.length > 0 && <Section title="Synonyms">{data.synonyms.join(', ')}</Section>}
    </div>
  );
}

function ClassEditForm({ data, onChange, onSave, onCancel }: { data: any; onChange: (d: any) => void; onSave: () => void; onCancel: () => void }) {
  const update = (key: string, value: any) => onChange({ ...data, [key]: value });

  return (
    <div>
      <h3 style={{ marginBottom: 16 }}>{data.class_name || 'New Class'} (Editing)</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
        <Field label="Class Name" value={data.class_name || ''} onChange={v => update('class_name', v)} />
        <Field label="Label (Chinese)" value={data.label || ''} onChange={v => update('label', v)} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>Description</label>
        <textarea value={data.description || ''} onChange={e => update('description', e.target.value)}
          style={{ ...inputStyle, width: '100%', minHeight: 60, resize: 'vertical' }} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>Required Fields (comma-separated)</label>
        <input value={(data.required_fields || []).join(', ')} onChange={e => update('required_fields', e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean))}
          style={{ ...inputStyle, width: '100%' }} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>Optional Fields (comma-separated)</label>
        <input value={(data.optional_fields || []).join(', ')} onChange={e => update('optional_fields', e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean))}
          style={{ ...inputStyle, width: '100%' }} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>Categories (comma-separated)</label>
        <input value={(data.categories || []).join(', ')} onChange={e => update('categories', e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean))}
          style={{ ...inputStyle, width: '100%' }} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>Synonyms (comma-separated)</label>
        <input value={(data.synonyms || []).join(', ')} onChange={e => update('synonyms', e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean))}
          style={{ ...inputStyle, width: '100%' }} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>States JSON</label>
        <textarea value={JSON.stringify(data.states || {}, null, 2)}
          onChange={e => { try { update('states', JSON.parse(e.target.value)); } catch {} }}
          style={{ ...inputStyle, width: '100%', minHeight: 100, fontFamily: 'monospace', fontSize: 11, resize: 'vertical' }} />
      </div>
      <div style={{ display: 'flex', gap: 10 }}>
        <button onClick={onSave} style={btnPrimaryStyle}>Save Class</button>
        <button onClick={onCancel} style={btnSecondaryStyle}>Cancel</button>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <h4 style={{ margin: '0 0 4px', fontSize: 12, color: '#888', textTransform: 'uppercase' }}>{title}</h4>
      <div style={{ fontSize: 13 }}>{children}</div>
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
