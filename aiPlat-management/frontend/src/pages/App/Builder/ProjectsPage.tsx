import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Plus, FolderOpen, Trash2, Clock, BarChart3, Users } from 'lucide-react';
import { projectApi, builderTeamApi, type ProjectItem, type TeamConfig } from '../../../services';
import { Card, CardHeader, CardContent, Button, Textarea, toast } from '../../../components/ui';

const ProjectsPage: React.FC = () => {
  const nav = useNavigate();
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [teams, setTeams] = useState<TeamConfig[]>([]);
  const [showNew, setShowNew] = useState(false);
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [teamId, setTeamId] = useState('');
  const [loading, setLoading] = useState(true);

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
    if (!name.trim()) { toast.error('请输入项目名称'); return; }
    try {
      await projectApi.create({ name, description: desc, team_id: teamId });
      setShowNew(false); setName(''); setDesc(''); setTeamId('');
      refresh();
      toast.success('项目已创建');
    } catch (e: unknown) { toast.error(e instanceof Error ? e.message : '创建失败'); }
  };

  const remove = async (id: string) => {
    try { await projectApi.delete(id); refresh(); } catch { /* ignore */ }
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
        <Button variant="primary" onClick={() => setShowNew(true)} icon={<Plus className="w-4 h-4" />}>
          新建项目
        </Button>
      </div>

      {/* New project modal */}
      {showNew && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center" onClick={() => setShowNew(false)}>
          <motion.div
            initial={{ scale: 0.95 }} animate={{ scale: 1 }}
            className="bg-dark-card border border-dark-border rounded-xl p-6 w-full max-w-md"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-bold text-gray-100 mb-4">新建项目</h2>
            <div className="space-y-3">
              <input className="w-full bg-dark-hover border border-dark-border rounded px-3 py-2 text-sm text-gray-200" placeholder="项目名称"
                value={name} onChange={(e) => setName(e.target.value)} />
              <Textarea value={desc} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setDesc(e.target.value)}
                placeholder="例如：构建一个电商后台管理系统，支持商品 SKU 管理、库存预警、订单状态流转。PM Agent 将基于此与你多轮对话确认细节。" rows={4} />
              <select className="w-full bg-dark-hover border border-dark-border rounded px-3 py-2 text-sm text-gray-200"
                value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                <option value="">选择团队（可选）</option>
                {teams.map((t) => (
                  <option key={t.team_id} value={t.team_id}>
                    {t.name} ({t.stages?.length || 0} 个角色)
                  </option>
                ))}
              </select>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="ghost" onClick={() => setShowNew(false)}>取消</Button>
              <Button variant="primary" onClick={create}>创建</Button>
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
                className="rounded-xl border border-dark-border bg-dark-card p-5 cursor-pointer hover:border-primary/40 transition-colors"
                onClick={() => nav(`/app/projects/${p.project_id}`)}
              >
                <div className="flex items-start justify-between mb-3">
                  <h3 className="text-sm font-semibold text-gray-100">{p.name}</h3>
                  <Button size="sm" variant="ghost" onClick={(e: React.MouseEvent) => { e.stopPropagation(); remove(p.project_id); }}>
                    <Trash2 className="w-3.5 h-3.5 text-gray-600" />
                  </Button>
                </div>
                <p className="text-xs text-gray-500 mb-3 line-clamp-2">{p.description || '无描述'}</p>

                {p.team_stages && p.team_stages.length > 0 && (
                  <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
                    <Users className="w-3 h-3" />
                    <span>{p.team_name || `${p.team_stages.length} 个角色`}</span>
                  </div>
                )}

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
