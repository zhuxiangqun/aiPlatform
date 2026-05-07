import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Plus, Save, Trash2, Users, Eye, Pencil, X } from 'lucide-react';
import { builderTeamApi, type AgentCatalogItem, type PipelineStageConfig, type TeamConfig } from '../../../services';
import { AgentCatalog } from '../../../components/Builder/AgentCatalog';
import { TeamCanvas } from '../../../components/Builder/TeamCanvas';
import { Card, CardHeader, CardContent, Button, toast, Select } from '../../../components/ui';

let _idCounter = 0;

/** Derive output artifact name from agent's role/phase */
function outputFor(agentId: string, phase: string, agentOutput?: string): string {
  if (agentOutput) return agentOutput;
  // fallback: legacy auto-detection for agents without output_artifact
  // Remove this block once all AGENT.md files define output_artifact
  const id = agentId || '';
  if (id.includes('backend')) return 'backend_code';
  if (id.includes('frontend')) return 'frontend_code';
  if (id.includes('architect')) return 'architecture';
  if (id.includes('pm') || id.includes('product') || phase === 'planning') return 'prd';
  if (id.includes('qa') || id.includes('test') || phase === 'testing') return 'test_report';
  if (id.includes('programmer') || phase === 'development') return 'code';
  return phase ? `${phase}_output` : 'artifact';
}

/** Derive input artifacts from the stages added so far */
function inputsFor(prevStages: PipelineStageConfig[]): string[] {
  if (prevStages.length === 0) return ['prd'];
  const upstreamOutputs = prevStages
    .filter((s) => s.output_artifact)
    .map((s) => s.output_artifact);
  // Always include 'prd' since most stages read the requirements
  if (!upstreamOutputs.includes('prd')) upstreamOutputs.unshift('prd');
  return upstreamOutputs;
}

const TeamAssemblyPage: React.FC = () => {
  const nav = useNavigate();
  const [stages, setStages] = useState<PipelineStageConfig[]>([]);
  const [teamName, setTeamName] = useState('');
  const [saving, setSaving] = useState(false);
  const [savedTeams, setSavedTeams] = useState<TeamConfig[]>([]);
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
    const raw = agent as Record<string, unknown>;
    const agentId = (agent.agent_id || raw.id || 'unknown') as string;
    const displayName = (agent.display_name || raw.name || agentId) as string;
    const desc = (agent.description || '') as string;
    const id = `${agentId}_${++_idCounter}`;
    setStages((prev) => {
      const output = outputFor(agentId, agent.phase || '', (agent as Record<string, unknown>).output_artifact as string);
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
          input_artifacts: i === 0 ? ['prd'] : ['prd'],
          output_artifact: `stage_${i}_output`,
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
    } catch (e: unknown) { toast.error(e instanceof Error ? e.message : '保存失败'); }
    finally { setSaving(false); }
  }, [stages, teamName, editingTeamId, loadTeams]);

  const deleteTeam = useCallback(async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try { await builderTeamApi.deleteTeam(id); loadTeams(); } catch { toast.error('删除失败'); }
  }, [loadTeams]);

  const editTeam = useCallback((team: TeamConfig) => {
    setEditingTeamId(team.team_id);
    setTeamName(team.name);
    setStages(team.stages.map((s, i) => ({ ...s, order: i,
      input_artifacts: (s as Record<string, unknown>).input_artifacts as string[] || (i === 0 ? ['prd'] : ['prd']),
      output_artifact: (s as Record<string, unknown>).output_artifact as string || `stage_${i}_output`,
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
                  <th className="py-3 px-4 text-xs font-medium text-gray-500">名称</th>
                  <th className="py-3 px-4 text-xs font-medium text-gray-500 hidden md:table-cell">描述</th>
                  <th className="py-3 px-4 text-xs font-medium text-gray-500">角色</th>
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
                    <td className="py-3 px-4 hidden md:table-cell">
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

      {/* Builder section */}
      {showBuilder && (
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          <Card>
            <CardHeader
              title={editingTeamId ? `编辑：${teamName}` : '新建团队'}
              extra={<Button size="sm" variant="ghost" onClick={clearBuilder} icon={<X className="w-3.5 h-3.5" />}>取消</Button>}
            />
          </Card>
          <div className="grid grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)] gap-4">
            <AgentCatalog onAdd={addAgent} />
            <div className="space-y-4">
              <TeamCanvas stages={stages} onUpdate={setStages} />
              <Card>
                <CardHeader title={editingTeamId ? '更新团队' : '保存为新团队'} />
                <CardContent>
                  <div className="flex gap-2">
                    <input
                      className="flex-1 bg-dark-hover border border-dark-border rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-500"
                      value={teamName} onChange={(e) => setTeamName(e.target.value)}
                      placeholder="团队名称（如：标准研发团队）"
                    />
                    <Button variant="primary" onClick={saveTeam} loading={saving} icon={<Save className="w-4 h-4" />}>
                      {editingTeamId ? '更新' : '保存'}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </motion.div>
      )}

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
