import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Plus, FolderOpen, Trash2, Clock, BarChart3, Users, CheckSquare, Square, AlertTriangle } from 'lucide-react';
import { projectApi, builderTeamApi, type ProjectItem, type TeamConfig } from '../../../services';
import { Card, CardContent, Button, Textarea, toast } from '../../../components/ui';
import { toastGateError } from '../../../components/ui';

const ProjectsPage: React.FC = () => {
  const nav = useNavigate();
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [teams, setTeams] = useState<TeamConfig[]>([]);
  const [showNew, setShowNew] = useState(false);
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [teamId, setTeamId] = useState('');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [pr, tm] = await Promise.all([
        projectApi.list(),
        builderTeamApi.listTeams(),
      ]);
      setProjects(pr.projects || []);
      setTeams(tm.teams || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const create = async () => {
    setCreating(true);
    const projectName = name.trim() || desc.trim().slice(0, 30) || '新项目';
    try {
      const project = await projectApi.create({ name: projectName, description: desc, team_id: teamId || undefined });
      setShowNew(false); setName(''); setDesc(''); setTeamId('');
      toast.success('项目已创建，正在进入需求对话...');
      nav(`/app/builder/projects/${project.project_id}`);
    } catch (e) { toastGateError(e, '创建失败'); }
    finally { setCreating(false); }
  };

  const remove = async (id: string) => {
    if (!window.confirm('确定要删除这个项目吗？所有运行记录和产物将被永久删除。')) return;
    try { await projectApi.delete(id); refresh(); } catch (e: any) { toastGateError(e, '删除失败'); }
  };

  const toggleSelect = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    if (selected.size === projects.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(projects.map(p => p.project_id)));
    }
  };

  const batchDelete = async () => {
    if (selected.size === 0) return;
    const count = selected.size;
    if (!window.confirm(`确定要删除选中的 ${count} 个项目吗？所有运行记录和产物将被永久删除。此操作不可撤销。`)) return;
    setBatchDeleting(true);
    try {
      const ids = Array.from(selected);
      await projectApi.batchDelete({ project_ids: ids });
      setSelected(new Set());
      refresh();
      toast.success(`已删除 ${count} 个项目`);
    } catch (e: any) { toastGateError(e, '批量删除失败'); }
    finally { setBatchDeleting(false); }
  };

  const cleanZeroPass = async () => {
    if (!window.confirm('确定要删除所有通过率为 0% 的项目吗？此操作不可撤销。')) return;
    setBatchDeleting(true);
    try {
      const res = await projectApi.batchDelete({ pass_rate_below: 0.01 });
      setSelected(new Set());
      refresh();
      toast.success(`已清理 ${(res as any).deleted || 0} 个项目`);
    } catch (e: any) { toastGateError(e, '清理失败'); }
    finally { setBatchDeleting(false); }
  };

  const latestRun = (p: ProjectItem) => p.runs?.[p.runs.length - 1];

  if (loading) return <div className="p-8 text-gray-500 text-sm">加载中...</div>;

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-100">项目工作台</h1>
          <p className="text-xs text-gray-500 mt-1">管理你的研发项目，跟踪开发进度</p>
        </div>
        <div className="flex items-center gap-2">
          {projects.length > 0 && (
            <>
              <Button variant="ghost" size="sm" onClick={selectAll} className="text-xs">
                {selected.size === projects.length ? '取消全选' : '全选'}
              </Button>
              {selected.size > 0 && (
                <Button variant="danger" size="sm" onClick={batchDelete} loading={batchDeleting} className="text-xs">
                  删除选中 ({selected.size})
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={cleanZeroPass} loading={batchDeleting} className="text-xs text-yellow-400">
                <AlertTriangle className="w-3 h-3 mr-1" /> 清理0%通过率
              </Button>
            </>
          )}
          <Button variant="primary" onClick={() => setShowNew(true)} icon={<Plus className="w-4 h-4" />}>
            新建项目
          </Button>
        </div>
      </div>

      {/* New project modal */}
      {showNew && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center" onClick={() => setShowNew(false)}>
          <motion.div
            initial={{ scale: 0.95 }} animate={{ scale: 1 }}
            className="bg-dark-card border border-dark-border rounded-xl p-6 w-full max-w-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-bold text-gray-100 mb-2">新建项目</h2>
            <p className="text-xs text-gray-500 mb-4">用自然语言描述你想要构建的应用，AI PM 将与你对话澄清需求，然后自动生成 PRD 并启动构建。</p>
            <div className="space-y-3">
              <Textarea value={desc} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setDesc(e.target.value)}
                placeholder="例如：构建一个电商后台管理系统，支持商品 SKU 管理、库存预警、订单状态流转。需要用户登录、权限管理、操作日志。"
                rows={4} />
              <div className="flex gap-2">
                <input className="flex-1 bg-dark-hover border border-dark-border rounded px-3 py-2 text-sm text-gray-200" placeholder="项目名称（留空自动提取）"
                  value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <details className="text-xs text-gray-500">
                <summary className="cursor-pointer text-gray-400">高级：选择团队</summary>
                <select className="w-full bg-dark-hover border border-dark-border rounded px-3 py-2 text-sm text-gray-200 mt-2"
                  value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                  <option value="">自动推荐（根据 PRD 智能组装）</option>
                  {teams.map((t) => (
                    <option key={t.team_id} value={t.team_id}>
                      {t.name} ({t.stages?.length || 0} 角色)
                    </option>
                  ))}
                </select>
              </details>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="ghost" onClick={() => setShowNew(false)}>取消</Button>
                <Button variant="primary" onClick={create} disabled={creating} loading={creating} icon={<Plus className="w-4 h-4" />}>开始构建</Button>
              </div>
            </div>
          </motion.div>
        </div>
      )}

      {/* Project cards */}
      {projects.length === 0 ? (
        <Card><CardContent>
          <div className="text-center text-gray-500 py-12">
            <FolderOpen className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="text-sm">暂无项目</p>
            <p className="text-xs mt-1">点击"新建项目"开始</p>
          </div>
        </CardContent></Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((p) => {
            const run = latestRun(p);
            return (
              <motion.div
                key={p.project_id} layout
                whileHover={{ y: -1 }}
                className={`rounded-xl border bg-dark-card p-5 cursor-pointer hover:border-primary/40 transition-colors ${selected.has(p.project_id) ? 'border-primary/60 ring-1 ring-primary/30' : 'border-dark-border'}`}
                onClick={() => selected.size > 0 ? toggleSelect(p.project_id) : nav(`/app/builder/projects/${p.project_id}`)}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <button
                      onClick={(e: React.MouseEvent) => { e.stopPropagation(); toggleSelect(p.project_id); }}
                      className="flex-shrink-0 text-gray-500 hover:text-primary transition-colors"
                    >
                      {selected.has(p.project_id) ? <CheckSquare className="w-4 h-4 text-primary" /> : <Square className="w-4 h-4" />}
                    </button>
                    <h3 className="text-sm font-semibold text-gray-100 truncate">{p.name}</h3>
                  </div>
                  <Button size="sm" variant="ghost" onClick={(e: React.MouseEvent) => { e.stopPropagation(); remove(p.project_id); }}>
                    <Trash2 className="w-3.5 h-3.5 text-gray-600 hover:text-red-400" />
                  </Button>
                </div>
                <p className="text-xs text-gray-500 mb-3 line-clamp-2">{p.description || '无描述'}</p>

                {p.team_stages && p.team_stages.length > 0 && (
                  <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
                    <Users className="w-3 h-3" />
                    <span>{p.team_name || `${p.team_stages.length} 个角色`}</span>
                  </div>
                )}

                <div className="text-xs text-gray-600 font-mono">{p.project_id}</div>

                {run ? (
                  <div className="space-y-1.5 text-xs">
                    <div className="flex items-center gap-2">
                      <Clock className="w-3 h-3 text-gray-500" />
                      <span className="text-gray-400">{run.started_at?.slice(0, 16) || '-'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <BarChart3 className="w-3 h-3 text-gray-500" />
                      <span className={run.pass_rate >= 0.8 ? 'text-green-400' : 'text-yellow-400'}>
                        通过率 {(run.pass_rate * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-gray-500">
                      <Users className="w-3 h-3" />
                      <span>本次: {(run.tokens_used || 0).toLocaleString()}</span>
                      {p.runs && p.runs.length > 1 && (
                        <span className="text-gray-600">
                          · 累计: {p.runs.reduce((s, r) => s + (r.tokens_used || 0), 0).toLocaleString()}
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] text-gray-600">
                      {p.runs?.length || 0} 次运行
                    </div>
                  </div>
                ) : (
                  <div className="text-xs text-gray-600">尚未运行</div>
                )}
              </motion.div>
            );
          })}
        </div>
      )}
    </motion.div>
  );
};

export default ProjectsPage;
