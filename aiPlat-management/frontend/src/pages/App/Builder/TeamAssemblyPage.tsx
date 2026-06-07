import React, { useState, useCallback, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Plus, Save, Trash2, Eye, Pencil, Download, Upload, Bookmark, BookOpen, MessageSquare } from 'lucide-react';
import { builderTeamApi, type AgentCatalogItem, type PipelineStageConfig, type TeamConfig } from '../../../services';
import { AgentCatalog } from '../../../components/Builder/AgentCatalog';
import { TeamCanvas } from '../../../components/Builder/TeamCanvas';
import { Card, CardHeader, CardContent, Button, toast, Select, Modal } from '../../../components/ui';
import { toastGateError } from '../../../components/ui';

let _idCounter = 0;

/** Derive output artifact name from agent's configured output_artifact field */
function outputFor(_agentId: string, _phase: string, agentOutput?: string): string {
  if (agentOutput) return agentOutput;
  return _phase ? `${_phase}_output` : 'artifact';
}

/** Derive input artifacts from upstream stage outputs */
function inputsFor(prevStages: PipelineStageConfig[]): string[] {
  if (prevStages.length === 0) return [];
  const upstreamOutputs = prevStages
    .filter((s) => s.output_artifact)
    .map((s) => s.output_artifact);
  return upstreamOutputs;
}

const TeamAssemblyPage: React.FC = () => {
  const [stages, setStages] = useState<PipelineStageConfig[]>([]);
  const [teamName, setTeamName] = useState('');
  const [saving, setSaving] = useState(false);
  const [savedTeams, setSavedTeams] = useState<TeamConfig[]>([]);
  const [showTemplates, setShowTemplates] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<{ role: string; content: string }[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  // Quick Test Chat
  const sendChat = useCallback(async () => {
    const msg = chatInput.trim();
    if (!msg) return;
    setChatMessages(prev => [...prev, { role: 'user', content: msg }]);
    setChatInput('');
    setChatLoading(true);
    try {
      const resp = await fetch('/api/core/diagnostics/playground/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: msg,
          stages: stages.map(s => ({ id: s.id, agent_name: s.agent_name, phase: s.phase, category: s.category })),
        }),
      });
      const data = await resp.json();
      setChatMessages(prev => [...prev, { role: 'assistant', content: data.content }]);
    } catch (e: any) {
      setChatMessages(prev => [...prev, { role: 'assistant', content: '请求失败: ' + (e?.message || '') }]);
    } finally {
      setChatLoading(false);
    }
  }, [chatInput, stages]);

  // Templates: persisted in localStorage
  const getTemplates = useCallback((): { name: string; stages: PipelineStageConfig[] }[] => {
    try {
      return JSON.parse(localStorage.getItem('aiplat_pipeline_templates') || '[]');
    } catch { return []; }
  }, []);

  const saveTemplate = useCallback(() => {
    if (stages.length === 0) { toast.error('请先添加至少一个角色'); return; }
    const name = prompt('模板名称:', teamName.trim() || '');
    if (!name) return;
    const all = getTemplates();
    const idx = all.findIndex(t => t.name === name);
    if (idx >= 0) all[idx] = { name, stages };
    else all.push({ name, stages });
    localStorage.setItem('aiplat_pipeline_templates', JSON.stringify(all.slice(0, 20)));
    toast.success(`模板 "${name}" 已保存`);
  }, [stages, teamName, getTemplates]);

  const loadTemplate = useCallback((name: string) => {
    const all = getTemplates();
    const t = all.find(t => t.name === name);
    if (!t) { toast.error('模板不存在'); return; }
    setStages(t.stages);
    setTeamName(t.name);
    setEditingTeamId('');
    setShowTemplates(false);
    toast.success(`已加载模板 "${name}"`);
  }, [getTemplates]);

  const deleteTemplate = useCallback((name: string) => {
    const all = getTemplates().filter(t => t.name !== name);
    localStorage.setItem('aiplat_pipeline_templates', JSON.stringify(all));
    toast.success(`已删除模板 "${name}"`);
    setShowTemplates(false);
  }, [getTemplates]);
  const [editingTeamId, setEditingTeamId] = useState<string | null>(null);
  const [viewingTeam, setViewingTeam] = useState<TeamConfig | null>(null);
  const [showBuilder, setShowBuilder] = useState(false);
  const [catFilter, setCatFilter] = useState('');

  const loadTeams = useCallback(async () => {
    try {
      const resp = await builderTeamApi.listTeams();
      setSavedTeams(resp.teams || []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadTeams(); }, [loadTeams]);

  const addAgent = useCallback((agent: AgentCatalogItem) => {
    const raw = agent as unknown as Record<string, unknown>;
    const agentId = (agent.agent_id || raw.id || 'unknown') as string;
    const displayName = (agent.display_name || raw.name || agentId) as string;
    const desc = (agent.description || '') as string;
    const id = `${agentId}_${++_idCounter}`;
    setStages((prev) => {
      const output = outputFor(agentId, agent.phase || '', (agent as unknown as Record<string, unknown>).output_artifact as string);
      return [...prev, {
        id,
        agent_id: agentId,
        agent_name: displayName,
        description: desc,
        category: agent.category,
        tags: agent.tags,
        phase: agent.phase,
        order: prev.length,
        // Use hitl from AGENT.md metadata; fallback: design/testing phases auto-hitl
        hitl: ((agent as any).metadata?.hitl as boolean) || (agent.phase === 'design' || agent.phase === 'testing'),
        hitl_phase: (agent.hitl_phase as string) || '',
        retry_target_id: '',
        hitl_after_execute: false, hitl_after_phase: '',
        input_artifacts: inputsFor(prev),
        output_artifact: output,
      }];
    });
  }, []);

  const saveTeam = useCallback(async () => {
    if (stages.length === 0) { toast.error('请先添加至少一个角色'); return; }
    setSaving(true);
    try {
      const name = teamName.trim() || `团队 ${new Date().toLocaleDateString()}`;
      const data = {
        name,
        description: `${name} — ${stages.length} 个角色`,
        stages: stages.map((s, i) => ({ ...s, order: i,
          input_artifacts: inputsFor(stages.slice(0, i)),
          output_artifact: s.output_artifact || `stage_${i}_output`,
        })),
      };
      if (editingTeamId) {
        await builderTeamApi.updateTeam(editingTeamId, data);
        toast.success('团队已更新');
      } else {
        await builderTeamApi.createTeam(data);
        toast.success('团队已创建');
      }
      clearBuilder();
      loadTeams();
    } catch (e) { toastGateError(e, '保存失败'); }
    finally { setSaving(false); }
  }, [stages, teamName, editingTeamId, loadTeams]);

  const deleteTeam = useCallback(async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm('确定要删除此团队配置吗？此操作不可撤销。')) return;
    try { await builderTeamApi.deleteTeam(id); loadTeams(); } catch (e: any) { toastGateError(e, '删除失败'); }
  }, [loadTeams]);

  const exportPipeline = useCallback(() => {
    if (stages.length === 0) { toast.error('请先添加至少一个角色'); return; }
    const name = teamName.trim() || 'pipeline';
    const config = {
      name,
      description: '',
      stages: stages.map(({ id, agent_id, agent_name, category, tags, phase, order, hitl, hitl_phase, retry_target_id, output_artifact, input_artifacts, phase_description }) => ({
        id, agent_id, agent_name, category, tags, phase, order, hitl, hitl_phase, retry_target_id, output_artifact, input_artifacts, phase_description,
      })),
      max_iterations: 10,
      max_tokens_per_run: 100_000,
      max_stagnation: 5,
    };
    const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name.replace(/\s+/g, '_')}_pipeline.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Pipeline 配置已导出');
  }, [stages, teamName]);

  const importPipeline = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const config = JSON.parse(ev.target?.result as string);
        if (!Array.isArray(config.stages) || config.stages.length === 0) {
          toast.error('无效的 Pipeline 配置：缺少 stages 数组');
          return;
        }
        const imported: PipelineStageConfig[] = config.stages.map((s: any, i: number) => ({
          id: s.id || `imported_${i}`,
          agent_id: s.agent_id || '',
          agent_name: s.agent_name || s.name || `Stage ${i + 1}`,
          category: s.category || '',
          tags: Array.isArray(s.tags) ? s.tags : [],
          phase: s.phase || '',
          order: i,
          hitl: !!s.hitl,
          hitl_phase: s.hitl_phase || '',
          retry_target_id: s.retry_target_id || '',
          output_artifact: s.output_artifact || '',
          input_artifacts: Array.isArray(s.input_artifacts) ? s.input_artifacts : [],
          phase_description: s.phase_description || '',
        }));
        setStages(imported);
        if (config.name) setTeamName(config.name);
        setEditingTeamId('');
        toast.success(`成功导入 ${imported.length} 个阶段`);
      } catch {
        toast.error('JSON 解析失败，请检查文件格式');
      }
    };
    reader.readAsText(file);
    // Reset input so same file can be re-imported
    e.target.value = '';
  }, []);

  const editTeam = useCallback((team: TeamConfig) => {
    setEditingTeamId(team.team_id);
    setTeamName(team.name);
      setStages(team.stages.map((s, i) => ({ ...s, order: i,
        input_artifacts: (s as unknown as Record<string, unknown>).input_artifacts as string[] || [],
        output_artifact: (s as unknown as Record<string, unknown>).output_artifact as string || `stage_${i}_output`,
    })));
    setShowBuilder(true);
    setViewingTeam(null);
  }, []);

  const clearBuilder = useCallback(() => {
    setStages([]); setTeamName(''); setEditingTeamId(null); setShowBuilder(false); _idCounter = 0;
  }, []);

  const filtered = catFilter ? savedTeams.filter((t) =>
    t.stages?.some((s) => s.category === catFilter)
  ) : savedTeams;

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4 p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-100">团队组装</h1>
          <p className="text-xs text-gray-500 mt-1">管理你的研发团队，保存后可复用于任何项目</p>
        </div>
        <div className="flex gap-2 items-center">
          {stages.length > 0 && (
            <Button variant="secondary" size="sm" onClick={() => setChatOpen(!chatOpen)} icon={<MessageSquare className="w-4 h-4" />}>
              {chatOpen ? '关闭测试' : '测试'}
            </Button>
          )}
          <Select
            value={catFilter}
            onChange={(v) => setCatFilter(v || '')}
            options={[
              { value: '', label: '全部分类' },
              { value: 'engineering', label: '研发' },
              { value: 'product', label: '产品' },
              { value: 'quality', label: '质量' },
              { value: 'design', label: '设计' },
              { value: 'management', label: '管理' },
              { value: 'sales', label: '销售' },
              { value: 'support', label: '支持' },
            ]}
            placeholder="全部分类"
          />
          <div className="flex-shrink-0">
            <Button variant="primary" onClick={() => { clearBuilder(); setShowBuilder(true); }} icon={<Plus className="w-4 h-4" />}>
              新建团队
            </Button>
          </div>
        </div>
      </div>

      {/* Quick Test Chat Panel */}
      {chatOpen && (
        <div style={{
          background: '#1f2937', border: '1px solid #374151', borderRadius: 10,
          padding: 12, maxHeight: 350, display: 'flex', flexDirection: 'column',
        }}>
          <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 8 }}>
            测试当前流水线 ({stages.length} 个阶段) — 输入消息测试 AI 响应
          </div>
          <div style={{ flex: 1, overflowY: 'auto', marginBottom: 8, fontSize: 12, color: '#e5e7eb', minHeight: 100 }}>
            {chatMessages.length === 0 && (
              <div style={{ color: '#6b7280', textAlign: 'center', padding: 20 }}>
                输入消息测试当前流水线配置...
              </div>
            )}
            {chatMessages.map((m, i) => (
              <div key={i} style={{
                marginBottom: 8, padding: '6px 10px', borderRadius: 6,
                background: m.role === 'user' ? '#374151' : '#1e2640',
                borderLeft: `3px solid ${m.role === 'user' ? '#3b82f6' : '#8b5cf6'}`,
              }}>
                <div style={{ fontSize: 10, color: '#6b7280', marginBottom: 2 }}>
                  {m.role === 'user' ? '你' : 'AI'}
                </div>
                <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
              </div>
            ))}
            {chatLoading && <div style={{ fontSize: 11, color: '#6b7280', padding: 8 }}>思考中...</div>}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              value={chatInput}
              onChange={e => setChatInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); } }}
              placeholder="输入测试消息..."
              style={{
                flex: 1, background: '#111827', border: '1px solid #374151',
                borderRadius: 6, padding: '6px 12px', color: '#e5e7eb', fontSize: 12,
              }}
            />
            <Button variant="primary" size="sm" onClick={sendChat} loading={chatLoading}>
              发送
            </Button>
          </div>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {filtered.length === 0 ? (
            <div className="text-center py-6 text-sm text-gray-500">
              暂无团队，点击"新建团队"开始
            </div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="border-b border-dark-border text-left">
                  <th className="py-3 px-4 text-xs font-medium text-gray-500" style={{width:'25%',minWidth:'160px'}}>名称</th>
                  <th className="py-3 px-4 text-xs font-medium text-gray-500" style={{width:'25%',minWidth:'160px'}}>描述</th>
                  <th className="py-3 px-4 text-xs font-medium text-gray-500 min-w-[280px]">角色</th>
                  <th className="py-3 px-4 text-xs font-medium text-gray-500 w-28">操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((t) => (
                  <tr key={t.team_id} className="border-b border-dark-border hover:bg-dark-hover/30 transition-colors">
                    <td className="py-3 px-4">
                      <button onClick={() => editTeam(t)} className="text-sm font-medium text-primary hover:text-primary-hover text-left">
                        {t.name}
                      </button>
                    </td>
                    <td className="py-3 px-4">
                      <span className="text-xs text-gray-500 line-clamp-1">{t.description || '-'}</span>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex flex-wrap gap-1">
                        {t.stages?.slice(0, 4).map((s) => (
                          <span key={s.id} className="text-[10px] px-1.5 py-0.5 rounded bg-dark-hover text-gray-400">
                            {s.agent_name}
                          </span>
                        ))}
                        {t.stages && t.stages.length > 4 && (
                          <span className="text-[10px] text-gray-600">+{t.stages.length - 4}</span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex gap-0.5">
                        <Button size="sm" variant="ghost" onClick={() => setViewingTeam(t)} title="查看">
                          <Eye className="w-3.5 h-3.5" />
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => editTeam(t)} title="编辑">
                          <Pencil className="w-3.5 h-3.5" />
                        </Button>
                        <Button size="sm" variant="ghost" onClick={(e: React.MouseEvent) => deleteTeam(t.team_id, e)} title="删除">
                          <Trash2 className="w-3.5 h-3.5 text-red-400" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* Builder modal */}
      <Modal
        open={showBuilder}
        onClose={clearBuilder}
        title={editingTeamId ? `编辑：${teamName}` : '新建团队'}
        width={960}
        footer={
          <div className="flex gap-2 justify-end">
            <Button variant="ghost" onClick={clearBuilder}>取消</Button>
            <Button variant="primary" onClick={saveTeam} loading={saving} icon={<Save className="w-4 h-4" />}>
              {editingTeamId ? '更新' : '保存'}
            </Button>
          </div>
        }
      >
        <div className="grid grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)] gap-4">
          <AgentCatalog onAdd={addAgent} />
          <div className="space-y-4">
            <TeamCanvas stages={stages} onUpdate={setStages} />
            <Card>
              <CardHeader title="团队信息" />
              <CardContent>
                <div className="flex gap-2">
                  <input
                    className="flex-1 bg-dark-hover border border-dark-border rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-500"
                    value={teamName} onChange={(e) => setTeamName(e.target.value)}
                    placeholder="团队名称（如：标准研发团队）"
                  />
                  <Button variant="ghost" onClick={exportPipeline} icon={<Download className="w-4 h-4" />} title="导出为 JSON">
                    导出
                  </Button>
                  <Button variant="ghost" onClick={() => fileInputRef.current?.click()} icon={<Upload className="w-4 h-4" />} title="从 JSON 导入">
                    导入
                  </Button>
                  <Button variant="ghost" onClick={saveTemplate} icon={<Bookmark className="w-4 h-4" />} title="保存为模板">
                    模板
                  </Button>
                  <div style={{ position: 'relative' }}>
                    <Button variant="ghost" onClick={() => setShowTemplates(!showTemplates)} icon={<BookOpen className="w-4 h-4" />} title="加载模板">
                      加载
                    </Button>
                    {showTemplates && (
                      <div style={{
                        position: 'absolute', top: '100%', right: 0, zIndex: 50,
                        background: '#1f2937', border: '1px solid #374151', borderRadius: 8,
                        padding: 8, minWidth: 200, boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
                      }}>
                        {getTemplates().length === 0 ? (
                          <div style={{ fontSize: 12, color: '#6b7280', padding: 8 }}>暂无模板</div>
                        ) : (
                          getTemplates().map(t => (
                            <div key={t.name} style={{
                              display: 'flex', alignItems: 'center', gap: 6,
                              padding: '6px 8px', borderRadius: 4, cursor: 'pointer',
                              fontSize: 12, color: '#e5e7eb',
                            }}
                            onMouseEnter={e => (e.currentTarget.style.background = '#374151')}
                            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                            >
                              <span style={{ flex: 1 }} onClick={() => loadTemplate(t.name)}>
                                📋 {t.name} <span style={{ color: '#6b7280', fontSize: 10 }}>({t.stages.length} 阶段)</span>
                              </span>
                              <button onClick={() => deleteTemplate(t.name)} style={{
                                background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: 14, padding: '0 4px',
                              }} title="删除模板">✕</button>
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                  <input ref={fileInputRef} type="file" accept=".json" onChange={importPipeline} style={{ display: 'none' }} />
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </Modal>

      {/* View modal */}
      {viewingTeam && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center" onClick={() => setViewingTeam(null)}>
          <motion.div initial={{ scale: 0.95 }} animate={{ scale: 1 }}
            className="bg-dark-card border border-dark-border rounded-xl p-6 w-full max-w-lg max-h-[80vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-bold text-gray-100 mb-2">{viewingTeam.name}</h2>
            <p className="text-xs text-gray-500 mb-4">{viewingTeam.description || '无描述'}</p>
            <div className="space-y-2">
              {viewingTeam.stages?.map((s, i) => (
                <div key={s.id} className="flex items-center gap-3 p-3 rounded-lg border border-dark-border bg-dark-hover/30">
                  <span className="text-xs font-mono text-gray-500 w-5">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-200">{s.agent_name}</div>
                    <div className="text-[10px] text-gray-500">{s.category} · {s.phase} · {s.hitl ? '需确认' : '自动'}{s.retry_target_id ? ` · 回退→${s.retry_target_id}` : ''}</div>
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="ghost" onClick={() => setViewingTeam(null)}>关闭</Button>
              <Button variant="primary" onClick={() => editTeam(viewingTeam)} icon={<Pencil className="w-3.5 h-3.5" />}>编辑</Button>
            </div>
          </motion.div>
        </div>
      )}
    </motion.div>
  );
};

export default TeamAssemblyPage;
