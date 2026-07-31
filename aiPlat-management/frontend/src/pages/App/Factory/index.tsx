import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Plus, Send, Loader2, Clock, CheckCircle, XCircle, ExternalLink } from 'lucide-react';
import { projectApi, builderTeamApi, type ProjectItem, type ProjectRun } from '../../../services';
import { Card, CardContent, Button, Textarea, toast } from '../../../components/ui';
import { toastGateError } from '../../../components/ui';
import type { BuilderSession } from '../../../services';

// ── Simple inline chat (replaces crashing ChatWidget) ──
const InlineChat: React.FC<{
  projectId: string;
  initialMessage?: string;
  onPhaseChange?: (phase: string) => void;
}> = ({ projectId, initialMessage, onPhaseChange }) => {
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [autoSent, setAutoSent] = useState(false);
  const bottomRef = React.useRef<HTMLDivElement>(null);

  const send = useCallback(async (msg: string) => {
    if (!msg.trim()) return;
    setSending(true);
    setMessages(prev => [...prev, { role: 'user', content: msg }]);
    try {
      const resp = await projectApi.chat(projectId, msg);
      setMessages(prev => [...prev, { role: 'assistant', content: resp.reply || '(no response)' }]);
      if (resp.prd_ready && onPhaseChange) onPhaseChange('prd_ready');
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: '发送失败，请重试' }]);
    } finally { setSending(false); }
  }, [projectId, onPhaseChange]);

  // Auto-send initial message
  useEffect(() => {
    if (initialMessage && !autoSent) {
      setAutoSent(true);
      send(initialMessage);
    }
  }, [initialMessage, autoSent, send]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const handleSend = () => { const m = input.trim(); if (m) { setInput(''); send(m); } };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-3 space-y-2 min-h-[200px] max-h-[400px]">
        {messages.map((m, i) => (
          <div key={i} className={`p-2 rounded text-sm ${m.role === 'assistant' ? 'bg-primary/10 border border-primary/20 text-gray-200' : 'bg-dark-card border border-dark-border text-gray-300'}`}>
            <div className="text-[10px] text-gray-500 mb-1">{m.role === 'assistant' ? 'AI PM' : '你'}</div>
            <div className="whitespace-pre-wrap break-words">{m.content}</div>
          </div>
        ))}
        {sending && <div className="flex items-center gap-2 text-xs text-gray-500"><Loader2 className="w-3 h-3 animate-spin" />思考中...</div>}
        <div ref={bottomRef} />
      </div>
      <div className="p-2 border-t border-dark-border flex gap-2">
        <Textarea value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }} placeholder="输入需求..." rows={2} className="flex-1 text-xs" />
        <Button variant="primary" onClick={handleSend} loading={sending} icon={<Send className="w-3 h-3" />} />
      </div>
    </div>
  );
};

// ── Project detail panel ──
const ProjectPanel: React.FC<{
  project: ProjectItem;
  onClose: () => void;
  onRefresh: () => void;
}> = ({ project, onClose, onRefresh }) => {
  const [phase, setPhase] = useState('dialogue');
  const [prdReady, setPrdReady] = useState(false);
  const [starting, setStarting] = useState(false);
  const [recommending, setRecommending] = useState(false);
  const [teamStages, setTeamStages] = useState<Array<{ agent_name?: string; agent_id?: string; phase?: string; id?: string }>>(project.team_stages || []);
  const [runHistory, setRunHistory] = useState<ProjectRun[]>(project.runs || []);
  const [deployUrl, setDeployUrl] = useState('');
  const [deploying, setDeploying] = useState(false);

  useEffect(() => {
    setTeamStages(project.team_stages || []);
    setRunHistory(project.runs || []);
  }, [project]);

  const handleConfirm = async () => {
    if (!project.project_id) return;
    setStarting(true);
    try {
      await projectApi.confirm(project.project_id);
      const teamResult = await projectApi.recommendTeam(project.project_id);
      const stages = (teamResult as any)?.plan_stages || [];
      setTeamStages(stages);
      setPhase('team_ready');
      toast.success('PRD 已确认，团队已推荐');
    } catch (e: any) { toastGateError(e, '确认失败'); }
    finally { setStarting(false); }
  };

  const handleStart = async () => {
    if (!project.project_id) return;
    setStarting(true);
    try {
      const result = await projectApi.start(project.project_id);
      setPhase(result.phase || 'executing');
      toast.success('Pipeline 已启动');
      onRefresh();
    } catch (e: any) { toastGateError(e, '启动失败'); }
    finally { setStarting(false); }
  };

  const handleRecommend = async () => {
    if (!project.project_id) return;
    setRecommending(true);
    try {
      const result = await projectApi.recommendTeam(project.project_id);
      const stages = (result as any)?.plan_stages || [];
      setTeamStages(stages);
      toast.success('AI 已推荐团队');
    } catch (e: any) { toastGateError(e, '推荐失败'); }
    finally { setRecommending(false); }
  };

  const handleDeploy = async () => {
    if (!project.project_id) return;
    setDeploying(true);
    try {
      const result = await projectApi.deployToApp(project.project_id);
      setDeployUrl((result as any)?.app_url || '');
      toast.success('部署成功');
    } catch (e: any) { toastGateError(e, '部署失败'); }
    finally { setDeploying(false); }
  };

  return (
    <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} className="fixed inset-y-0 right-0 w-full max-w-2xl bg-dark-card border-l border-dark-border shadow-2xl z-50 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-dark-border">
        <div>
          <h2 className="text-lg font-bold text-gray-100">{project.name}</h2>
          <p className="text-xs text-gray-500">{project.description}</p>
        </div>
        <Button variant="ghost" onClick={onClose}>✕</Button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Progress */}
        {phase === 'done' ? (
          <div className="p-3 rounded bg-green-500/10 border border-green-500/30 text-sm text-green-300">
            ✅ 构建完成
            {!deployUrl && (
              <Button variant="primary" size="sm" className="ml-3" onClick={handleDeploy} loading={deploying}>部署到 App</Button>
            )}
            {deployUrl && (
              <a href={deployUrl} target="_blank" rel="noreferrer" className="ml-3 text-primary underline text-xs flex items-center gap-1 inline-flex">
                <ExternalLink className="w-3 h-3" /> 打开应用
              </a>
            )}
          </div>
        ) : phase === 'executing' ? (
          <div className="p-3 rounded bg-blue-500/10 border border-blue-500/30 text-sm text-blue-300 flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" /> Pipeline 执行中...
          </div>
        ) : null}

        {/* Team stages */}
        {teamStages.length > 0 && (
          <div className="space-y-1">
            <h3 className="text-xs font-semibold text-gray-400 uppercase">团队配置</h3>
            <div className="flex items-center gap-1 text-xs">
              {teamStages.map((s, i) => (
                <React.Fragment key={s.id || i}>
                  <span className="px-2 py-1 rounded bg-dark-hover text-gray-300">{s.agent_name || s.agent_id}</span>
                  {i < teamStages.length - 1 && <span className="text-gray-600">→</span>}
                </React.Fragment>
              ))}
            </div>
          </div>
        )}

        {/* Chat */}
        <Card>
          <CardContent className="p-0">
            <InlineChat
              projectId={project.project_id}
              initialMessage={!prdReady ? project.description : undefined}
              onPhaseChange={(p) => { if (p === 'prd_ready') setPrdReady(true); }}
            />
          </CardContent>
        </Card>

        {/* Actions */}
        <div className="flex flex-wrap gap-2">
          {!prdReady && phase === 'dialogue' && (
            <Button variant="secondary" size="sm" onClick={handleRecommend} loading={recommending}>AI 推荐团队</Button>
          )}
          {prdReady && phase === 'dialogue' && (
            <Button variant="primary" size="sm" onClick={handleConfirm} loading={starting}>确认需求</Button>
          )}
          {phase === 'team_ready' && (
            <Button variant="primary" size="sm" onClick={handleStart} loading={starting}>启动构建</Button>
          )}
        </div>

        {/* Run history */}
        {runHistory.length > 0 && (
          <details className="text-xs">
            <summary className="text-gray-500 cursor-pointer">运行历史 ({runHistory.length})</summary>
            <div className="mt-2 space-y-1 max-h-40 overflow-y-auto">
              {runHistory.slice(-5).reverse().map((r, i) => (
                <div key={i} className="flex justify-between p-1.5 rounded bg-dark-hover/30">
                  <span className="text-gray-400">{r.started_at?.slice(0, 16)}</span>
                  <span className={r.pass_rate >= 0.8 ? 'text-green-400' : 'text-yellow-400'}>通过率 {(r.pass_rate * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    </motion.div>
  );
};

// ── Main Factory Page ──
const FactoryPage: React.FC = () => {
  const nav = useNavigate();
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [deployedApps, setDeployedApps] = useState<any[]>([]);
  const [desc, setDesc] = useState('');
  const [creating, setCreating] = useState(false);
  const [selectedProject, setSelectedProject] = useState<ProjectItem | null>(null);
  const [selectedApp, setSelectedApp] = useState<string>('');

  const loadAll = useCallback(async () => {
    try {
      const p = await projectApi.list();
      setProjects(p.projects || []);
    } catch { /* ignore */ }
    try {
      const r = await fetch('/api/platform/apps');
      const d = await r.json();
      setDeployedApps(d.apps || []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const create = async () => {
    if (!desc.trim()) return;
    setCreating(true);
    try {
      const project = await projectApi.create({ name: desc.trim().slice(0, 30) || '新项目', description: desc.trim() });
      setDesc('');
      toast.success('项目已创建');
      setSelectedProject(project);
      loadAll();
    } catch (e) { toastGateError(e, '创建失败'); }
    finally { setCreating(false); }
  };

  const getStatus = (p: ProjectItem) => {
    if (p.runs?.length === 0) return { label: '待开始', color: 'text-gray-500', bg: 'bg-gray-500/10' };
    const last = p.runs?.[p.runs.length - 1];
    if (last?.phase === 'done') return { label: '已完成', color: 'text-green-400', bg: 'bg-green-500/10' };
    if (last?.phase === 'failed') return { label: '失败', color: 'text-red-400', bg: 'bg-red-500/10' };
    return { label: '构建中', color: 'text-blue-400', bg: 'bg-blue-500/10' };
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* ── Create Section ── */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="bg-dark-card border border-dark-border rounded-xl p-5">
        <h2 className="text-lg font-bold text-gray-100 mb-3">新建应用</h2>
        <p className="text-sm text-gray-400 mb-3">用自然语言描述你想要构建的应用，AI 将自动完成需求分析、架构设计和代码生成</p>
        <Textarea
          value={desc}
          onChange={e => setDesc(e.target.value)}
          placeholder="例如：构建一个视频解析平台，支持上传、转码、AI 摘要生成..."
          rows={3}
          className="mb-3"
        />
        <Button variant="primary" onClick={create} loading={creating} icon={<Plus className="w-4 h-4" />}>
          开始构建
        </Button>
      </motion.div>

      {/* ── Projects + Apps Grid ── */}
      <div>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">我的应用 ({projects.length + deployedApps.length})</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {/* Projects */}
          {projects.map(p => {
            const status = getStatus(p);
            return (
              <motion.div
                key={p.project_id} layout
                whileHover={{ y: -1 }}
                className="rounded-lg border border-dark-border bg-dark-card p-4 cursor-pointer hover:border-primary/40 transition-colors"
                onClick={() => setSelectedProject(p)}
              >
                <div className="flex items-start justify-between mb-2">
                  <h4 className="text-sm font-medium text-gray-100 truncate">{p.name}</h4>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${status.bg} ${status.color}`}>{status.label}</span>
                </div>
                <p className="text-xs text-gray-500 line-clamp-2 mb-2">{p.description}</p>
                <div className="flex items-center gap-2 text-[10px] text-gray-600">
                  <Clock className="w-3 h-3" />
                  <span>{p.created_at?.slice(0, 10)}</span>
                  {p.runs?.length ? <span>· {p.runs.length} 次运行</span> : null}
                </div>
              </motion.div>
            );
          })}

          {/* Deployed Apps */}
          {deployedApps.map((a: any) => (
            <motion.div
              key={a.id || a.app_id}
              layout
              whileHover={{ y: -1 }}
              className="rounded-lg border border-green-500/30 bg-green-500/5 p-4 cursor-pointer hover:border-green-400/50 transition-colors"
              onClick={() => setSelectedApp(a.app_url || `http://localhost:8004/${a.app_id}`)}
            >
              <div className="flex items-start justify-between mb-2">
                <h4 className="text-sm font-medium text-gray-100 truncate">{a.name || a.app_id}</h4>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-500/10 text-green-400">✅ 已部署</span>
              </div>
              <p className="text-xs text-gray-500 line-clamp-2 mb-2">{a.description || a.mode || '已部署应用'}</p>
              <div className="flex items-center gap-1 text-[10px] text-green-400">
                <ExternalLink className="w-3 h-3" /> 打开预览
              </div>
            </motion.div>
          ))}
        </div>

        {projects.length === 0 && deployedApps.length === 0 && (
          <div className="text-center py-12 text-gray-500">
            <p className="text-lg mb-2">还没有应用</p>
            <p className="text-sm">在上方输入需求描述，开始构建你的第一个应用</p>
          </div>
        )}
      </div>

      {/* ── Project Detail Panel ── */}
      {selectedProject && (
        <ProjectPanel
          project={selectedProject}
          onClose={() => setSelectedProject(null)}
          onRefresh={loadAll}
        />
      )}

      {/* ── Deployed App Preview ── */}
      {selectedApp && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={() => setSelectedApp('')}>
          <div className="bg-dark-card border border-dark-border rounded-xl w-full max-w-5xl h-[85vh] flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-3 border-b border-dark-border">
              <span className="text-sm text-gray-300">应用预览</span>
              <div className="flex gap-2">
                <a href={selectedApp} target="_blank" rel="noreferrer" className="text-xs text-primary flex items-center gap-1"><ExternalLink className="w-3 h-3" />新窗口打开</a>
                <Button variant="ghost" size="sm" onClick={() => setSelectedApp('')}>✕</Button>
              </div>
            </div>
            <iframe src={selectedApp} className="flex-1 border-0" title="应用预览" />
          </div>
        </motion.div>
      )}
    </div>
  );
};

export default FactoryPage;
