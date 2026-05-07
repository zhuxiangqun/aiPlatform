import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { CheckCircle, ArrowLeft, Play, Clock, BarChart3, Eye, Pencil, X } from 'lucide-react';
import { projectApi, type ProjectItem, type ProjectRun, type BuilderSession } from '../../../services';
import { BuilderPipeline } from '../../../components/Builder/BuilderPipeline';
import { ChatWidget } from '../../../components/ui/ChatWidget';
import { Card, CardHeader, CardContent, Button, toast } from '../../../components/ui';

const ProjectDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const [project, setProject] = useState<ProjectItem | null>(null);
  const [phase, setPhase] = useState('idle');
  const [starting, setStarting] = useState(false);
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [prdReady, setPrdReady] = useState(false);
  const [confirmedPrd, setConfirmedPrd] = useState<Record<string, unknown> | null>(null);
  const [session, setSession] = useState<BuilderSession | null>(null);
  const [runHistory, setRunHistory] = useState<ProjectRun[]>([]);
  const [showPrdDetail, setShowPrdDetail] = useState(false);
  const [editingPrd, setEditingPrd] = useState(false);
  const [chatKey, setChatKey] = useState(0);

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        const p = await projectApi.get(id);
        setProject(p);
        setRunHistory(p.runs || []);
        const raw = p as Record<string, unknown>;
        if (raw.confirmed_prd) {
          setConfirmedPrd(raw.confirmed_prd as Record<string, unknown>);
          setPrdReady(true);
        }
        // Check pipeline state — may be in mid-execution
        try {
          const st = await projectApi.getState(id);
          const s = (st.state || {}) as Record<string, unknown>;
          const pPhase = s.phase as string || '';
          if (pPhase && !['idle', 'dialogue'].includes(pPhase)) {
            setPhase(pPhase);
            setSession({
              session_id: id, phase: pPhase as BuilderSession['phase'],
              requirement: '', iteration: (s.iteration as number) || 0,
              error: (s.error as string) || '',
              prd: null, architecture: null, code: null, test_report: null,
              messages: [],
              ...(s as Record<string, unknown>),  // include all artifact keys (prd, backend_code, frontend_code, test_plan)
            } as BuilderSession);
          }
        } catch { /* getState may not be available */ }
      } catch { nav('/app/projects'); }
    })();
  }, [id]);

  // Poll pipeline state when executing (backend runs async)
  const pollRef = useRef<ReturnType<typeof setInterval>>();
  useEffect(() => {
    if (phase !== 'executing' || !id) return;
    pollRef.current = setInterval(async () => {
      try {
        const st = await projectApi.getState(id);
        const s = (st.state || {}) as Record<string, unknown>;
        if (s.phase) setPhase(s.phase as string);
        setSession((prev) => prev ? {
          ...prev,
          ...(s as Record<string, unknown>),  // merge all artifact keys
          iteration: (s.iteration || prev.iteration) as number,
          error: (s.error || prev.error) as string,
        } as BuilderSession : prev);
        if (st.runs) setRunHistory(st.runs);
        const p = s.phase as string || '';
        if (p === 'done' || p === 'failed' || p.includes('awaiting')) {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch { /* retry next tick */ }
    }, 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [phase, id]);

  const handleSend = useCallback(async (message: string) => {
    if (!id) throw new Error('no project');
    const resp = await projectApi.chat(id, message);
    if (resp.prd_ready) setPrdReady(true);
    return resp.reply;
  }, [id]);

  const confirmAndStart = useCallback(async () => {
    if (!id) return;
    setStarting(true);
    try {
      await projectApi.confirm(id, confirmedPrd || undefined);
      const result = await projectApi.start(id);
      const newPhase = result.phase || 'executing';
      setPhase(newPhase);
      const s = result.state || {};
      setSession({ session_id: id, phase: newPhase as BuilderSession['phase'],
                   requirement: '', iteration: s.iteration || 0, error: s.error || '',
                   prd: null, architecture: s.architecture || null, code: s.code || null,
                   test_report: s.test_report || null, messages: [] });
    } catch { toast.error('启动失败'); }
    finally { setStarting(false); }
  }, [id]);

  const startEditing = useCallback(async () => {
    setEditingPrd(true);
    setPrdReady(false);
    setChatKey((k) => k + 1);
    // Send existing PRD as context to PM
    if (id && confirmedPrd) {
      const prdJson = JSON.stringify(confirmedPrd, null, 2);
      await projectApi.chat(id, `以下是我之前已确认的 PRD，请基于此继续完善。我需要调整或优化其中某些部分：\n\n\`\`\`json\n${prdJson}\n\`\`\``);
    }
  }, [id, confirmedPrd]);

  const refreshState = async () => {
    if (!id) return;
    try {
      const st = await projectApi.getState(id);
      const s = (st.state || {}) as Record<string, unknown>;
      const p = s.phase as string || 'executing';
      setPhase(p);
      setRunHistory(st.runs || []);
      setSession({
        session_id: id, phase: p as BuilderSession['phase'],
        requirement: '', iteration: (s.iteration as number) || 0,
        error: (s.error as string) || '',
        prd: null, messages: [],
        ...(s as Record<string, unknown>),
      } as BuilderSession);
    } catch { /* ignore */ }
  };

  const approve = useCallback(async () => {
    if (!id) return;
    setPipelineLoading(true);
    try {
      await projectApi.approve(id);
      await refreshState();
    } catch { toast.error('操作失败'); }
    finally { setPipelineLoading(false); }
  }, [id]);

  const rollbackStage = useCallback(async (stageId: string) => {
    if (!id) return;
    setPipelineLoading(true);
    try {
      await projectApi.rollback(id, stageId);
      if (stageId === 'prd') {
        setPhase('dialogue');
        setSession(null);
        return;
      }
      await refreshState();
    } catch { toast.error('回退失败'); }
    finally { setPipelineLoading(false); }
  }, [id]);

  const startFix = useCallback(async () => {
    if (!id) return;
    setPipelineLoading(true);
    try {
      await projectApi.startFix(id);
      await refreshState();
    } catch { toast.error('启动修复失败'); }
    finally { setPipelineLoading(false); }
  }, [id]);

  const [showReject, setShowReject] = useState(false);
  const [rejectFeedback, setRejectFeedback] = useState('');
  const rejectHITL = useCallback(async () => {
    if (!id || !rejectFeedback.trim()) return;
    try {
      await projectApi.reject(id, rejectFeedback.trim());
      setShowReject(false);
      setRejectFeedback('');
      await refreshState();
    } catch { toast.error('驳回失败'); }
  }, [id, rejectFeedback]);

  const stories = (confirmedPrd?.user_stories as Array<Record<string, unknown>>) || [];
  const constraints = (confirmedPrd?.constraints as string[]) || [];

  const teamLabel = project?.team_stages
    ? project.team_stages.slice(0, 4).map(s => s.agent_name).join(' → ') +
      (project.team_stages.length > 4 ? ` +${project.team_stages.length - 4}` : '')
    : '';

  if (phase === 'idle' || phase === 'dialogue') {
    return (
      <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-4 space-y-4">
        <div className="flex items-center gap-3">
          <Button variant="ghost" onClick={() => nav('/app/projects')}><ArrowLeft className="w-4 h-4" /></Button>
          <div><h1 className="text-lg font-bold text-gray-100">{project?.name || '项目'}</h1>
          {teamLabel && <p className="text-[11px] text-gray-500 mt-0.5">团队：{teamLabel} ({project?.team_stages?.length || 0} 角色)</p>}
          <p className="text-xs text-gray-500">{project?.description}</p></div>
        </div>

        {/* PRD summary card — shown when confirmed PRD exists */}
        {confirmedPrd && !editingPrd && (
          <div className="p-4 rounded-lg border border-green-500/30 bg-green-500/5">
            <div className="flex items-start justify-between mb-3">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <CheckCircle className="w-4 h-4 text-green-400" />
                  <span className="text-sm font-semibold text-green-300">PRD 已确认</span>
                </div>
                <p className="text-sm text-gray-200 font-medium">{confirmedPrd.title as string || 'Untitled'}</p>
                <p className="text-xs text-gray-400 mt-0.5">{stories.length} 个 User Stories · {confirmedPrd.scope as string || '-'}</p>
              </div>
              <div className="flex gap-2 flex-shrink-0">
                <Button size="sm" onClick={() => setShowPrdDetail(true)} icon={<Eye className="w-3.5 h-3.5" />}>查看详情</Button>
                <Button size="sm" onClick={startEditing} icon={<Pencil className="w-3.5 h-3.5" />}>修改需求</Button>
              </div>
            </div>
            {/* Inline PRD preview */}
            <div className="pl-1 space-y-1 text-xs">
              {stories.slice(0, 2).map((us: Record<string, unknown>, i: number) => (
                <div key={i} className="text-gray-400">
                  <span className="text-primary font-medium">{us.id as string}</span> {(us.description as string || '').slice(0, 80)}
                  {(us.description as string || '').length > 80 ? '...' : ''}
                </div>
              ))}
              {stories.length > 2 && (
                <button onClick={() => setShowPrdDetail(true)} className="text-primary text-[11px] hover:underline cursor-pointer">
                  + {stories.length - 2} 条更多 → 点击查看全部
                </button>
              )}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_380px] gap-4">
          <Card className="flex flex-col">
            <CardHeader title="需求对话" />
            <CardContent className="flex-1 flex flex-col p-0">
              <ChatWidget
                key={chatKey}
                title="AI 产品经理"
                initialMessage={(!prdReady && !confirmedPrd) ? project?.description : undefined}
                placeholder="描述你的需求..."
                onSend={handleSend}
                maxHeight="55vh"
              />
            </CardContent>
          </Card>

          <Card><CardHeader title="运行历史" />
            <CardContent>
              {runHistory.length === 0 ? (<div className="text-xs text-gray-500">暂无运行记录</div>) : (
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {runHistory.slice(-8).reverse().map((r, i) => (
                    <details key={r.run_id || i} className="text-xs rounded border border-dark-border group">
                      <summary className="p-2 cursor-pointer hover:bg-dark-hover/30 flex items-center gap-2">
                        <Clock className="w-3 h-3 text-gray-500" />
                        <span className="text-gray-400">{r.started_at?.slice(0, 16) || '-'}</span>
                        <span className={r.pass_rate >= 0.8 ? 'text-green-400' : 'text-yellow-400'}>通过率 {(r.pass_rate * 100).toFixed(0)}%</span>
                        <span className="text-gray-500 ml-auto">{r.iteration || 0} 迭代 · {r.tokens_used?.toLocaleString() || 0} tokens</span>
                      </summary>
                      <div className="p-2 border-t border-dark-border space-y-1 bg-dark-hover/10">
                        <div className="flex gap-2"><span className="text-gray-500">Phase:</span><span className="text-gray-300">{r.phase || '-'}</span></div>
                        <div className="flex gap-2"><span className="text-gray-500">Run ID:</span><span className="text-gray-300 font-mono">{r.run_id || '-'}</span></div>
                        {r.error && <div className="flex gap-2"><span className="text-red-400">错误:</span><span className="text-red-300">{r.error}</span></div>}
                        <div className="flex gap-2"><span className="text-gray-500">完成时间:</span><span className="text-gray-300">{r.finished_at?.slice(0, 16) || '进行中'}</span></div>
                      </div>
                    </details>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {prdReady && !editingPrd && (
          <div className="p-4 rounded-lg border border-green-500/30 bg-green-500/5">
            <div className="text-xs text-gray-400 mb-3">确认需求后启动流水线</div>
            <Button variant="primary" onClick={confirmAndStart} loading={starting} icon={<Play className="w-4 h-4" />}>确认需求，开始构建</Button>
          </div>
        )}
      </motion.div>
      <PrdDetailModal open={showPrdDetail} prd={confirmedPrd} onClose={() => setShowPrdDetail(false)} onEdit={startEditing} />
      </>
    );
  }

  return (
    <>
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-4 space-y-4">
      <div className="flex items-center gap-3">
        <Button variant="ghost" onClick={() => nav('/app/projects')}><ArrowLeft className="w-4 h-4" /></Button>
        <div><h1 className="text-lg font-bold text-gray-100">{project?.name || '项目'}</h1>
        {teamLabel && <p className="text-[11px] text-gray-500 mt-0.5">团队：{teamLabel}</p>}</div>
      </div>
      <Card>
        <CardHeader title="流水线执行" extra={
          <div className="flex gap-2">
            <select className="text-xs bg-dark-hover border border-dark-border rounded px-2 py-1 text-gray-300"
              onChange={(e) => { if (e.target.value) rollbackStage(e.target.value); e.target.value = ''; }}
              defaultValue="">
              <option value="">↩ 回退...</option>
              <option value="prd">回退 PRD（需求对话）</option>
              {session?.architecture && <option value="architect">回退架构设计</option>}
              {(session as Record<string,unknown>).frontend_code && <option value="frontend_code">回退前端代码</option>}
              {(session as Record<string,unknown>).backend_code && <option value="backend_code">回退后端代码</option>}
              {(session as Record<string,unknown>).code && <option value="code">回退代码</option>}
            </select>
            <Button variant="secondary" size="sm" onClick={() => {
              if (!id) return;
              const a = document.createElement('a');
              a.href = `/api/platform/builder/projects/${id}/deploy`;
              a.download = `${id}_deploy.zip`;
              a.click();
            }}>📦 下载部署包</Button>
          </div>
        } />
        {showReject && (
          <div className="mt-3 flex gap-2">
            <input
              className="flex-1 bg-dark-hover border border-dark-border rounded px-2 py-1 text-xs text-gray-200"
              value={rejectFeedback}
              onChange={(e) => setRejectFeedback(e.target.value)}
              placeholder="驳回理由..."
              onKeyDown={(e) => e.key === 'Enter' && rejectHITL()}
            />
            <Button variant="primary" size="sm" onClick={rejectHITL} disabled={!rejectFeedback.trim()}>
              提交驳回
            </Button>
          </div>
        )}
        <CardContent>{session && (
          <BuilderPipeline
            session={session}
            teamStages={project?.team_stages}
            onRegenerate={(key) => rollbackStage(key)}
            onApprove={approve}
            onReject={(key) => { setShowReject(true); }}
            onRollback={(key) => rollbackStage(key)}
            loading={pipelineLoading}
          />
        )}</CardContent>
      </Card>
    </motion.div>
    <PrdDetailModal open={showPrdDetail} prd={confirmedPrd} onClose={() => setShowPrdDetail(false)} onEdit={startEditing} />
    </>
  );
};

// Shared modal — rendered outside phase conditions
const PrdDetailModal: React.FC<{
  open: boolean; prd: Record<string, unknown> | null; onClose: () => void; onEdit: () => void
}> = ({ open, prd, onClose, onEdit }) => {
  if (!open || !prd) return null;
  const stories = (prd.user_stories as Array<Record<string, unknown>>) || [];
  const constraints = (prd.constraints as string[]) || [];
  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center" onClick={onClose}>
      <motion.div initial={{ scale: 0.95 }} animate={{ scale: 1 }}
        className="bg-dark-card border border-dark-border rounded-xl p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-gray-100">PRD 详情</h2>
          <Button size="sm" variant="ghost" onClick={onClose}><X className="w-4 h-4" /></Button>
        </div>
        <div className="space-y-4 text-sm">
          <div><span className="text-gray-400">标题：</span><span className="text-gray-100">{prd.title as string}</span></div>
          <div><span className="text-gray-400">概述：</span><span className="text-gray-300">{prd.overview as string}</span></div>
          <div><span className="text-gray-400">Scope：</span><span className="text-primary">{prd.scope as string}</span></div>
          <div><span className="text-gray-400">User Stories ({stories.length})：</span>
            <div className="mt-2 space-y-2">{stories.map((us: Record<string, unknown>, i: number) => (
              <details key={i} className="p-3 rounded border border-dark-border bg-dark-hover/30">
                <summary className="text-gray-200 cursor-pointer font-medium">
                  <span className="text-primary">{us.id as string}</span> {us.description as string}
                  <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-dark-border text-gray-400">{us.priority as string}</span>
                </summary>
                <div className="mt-2 space-y-1 pl-4">{(us.acceptance_criteria as string[] || []).map((ac: string, j: number) => (<div key={j} className="text-xs text-gray-400">· {ac}</div>))}</div>
              </details>
            ))}</div>
          </div>
          {constraints.length > 0 && (<div><span className="text-gray-400">约束：</span><ul className="mt-1 space-y-0.5 pl-4 list-disc">{constraints.map((c: string, i: number) => (<li key={i} className="text-xs text-gray-400">{c}</li>))}</ul></div>)}
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="ghost" onClick={onClose}>关闭</Button>
          <Button variant="primary" onClick={() => { onClose(); onEdit(); }} icon={<Pencil className="w-3.5 h-3.5" />}>修改需求</Button>
        </div>
      </motion.div>
    </div>
  );
};

export default ProjectDetailPage;
