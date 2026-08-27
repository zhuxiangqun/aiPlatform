import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { CheckCircle, ArrowLeft, BarChart3, Play, Eye, Pencil, X, Rocket, TestTube, Clock, Sparkles, RefreshCw, Save } from 'lucide-react';
import { projectApi, type ProjectItem, type ProjectRun, type BuilderSession } from '../../../services';
import { BuilderPipeline } from '../../../components/Builder/BuilderPipeline';
import { RunEventTimeline } from '../../../components/Builder/RunEventTimeline';
import { ChatWidget } from '../../../components/ui';
import { Card, CardHeader, CardContent, Button, toast } from '../../../components/ui';
import { toastGateError } from '../../../components/ui';

const Phase = {
  idle: 'idle',
  dialogue: 'dialogue',
  executing: 'executing',
  paused: 'paused',
  done: 'done',
  failed: 'failed',
  testing: 'testing',
  deploying: 'deploying',
} as const;

const POLLABLE_PHASES: Set<string> = new Set([Phase.executing, Phase.paused]);
const TERMINAL_PHASES: Set<string> = new Set([Phase.done, Phase.failed]);
const DIALOGUE_PHASES: Set<string> = new Set([Phase.idle, Phase.dialogue]);

function isPollable(p: string) { return POLLABLE_PHASES.has(p) || p.includes('approval'); }
function isTerminal(p: string) { return TERMINAL_PHASES.has(p); }

const ProjectDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const [project, setProject] = useState<ProjectItem | null>(null);
  const [phase, setPhase] = useState<string>(Phase.idle);
  const [stepCount, setStepCount] = useState(0);
  const [starting, setStarting] = useState(false);
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [prdReady, setPrdReady] = useState(false);
  const [confirmedPrd, setConfirmedPrd] = useState<Record<string, unknown> | null>(null);
  const [session, setSession] = useState<BuilderSession | null>(null);
  const [runHistory, setRunHistory] = useState<ProjectRun[]>([]);
  const [showPrdDetail, setShowPrdDetail] = useState(false);
  const [editingPrd, setEditingPrd] = useState(false);
  const [chatKey, setChatKey] = useState(0);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<Record<string, unknown> | null>(null);
  const [deploying, setDeploying] = useState(false);
  const [deployResult, setDeployResult] = useState<Record<string, unknown> | null>(null);
  const [recommending, setRecommending] = useState(false);
  const [recommendedTeam, setRecommendedTeam] = useState<Record<string, unknown> | null>(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [healthReport, setHealthReport] = useState<Record<string, any> | null>(null);

  // Derived state — must precede callbacks that reference them
  const teamLabel = project?.team_stages
    ? project.team_stages.map(s => s.agent_name).join(' → ')
    : '';
  const stages = project?.team_stages || [];
  const totalStages = stages.length || 1;
  const currentIdx = Math.max(0, Math.min(((session as Record<string, unknown>)?.['_current_stage_idx'] as number) ?? 0, totalStages - 1));
  const maxSteps = 10;
  const stageProgress = Math.min(100, Math.round((stepCount / maxSteps) * 100));
  const segWidth = Math.round(100 / totalStages);
  const fillWidth = currentIdx * segWidth + Math.round(stageProgress / 100 * segWidth);
  const progressPct = Math.min(100, fillWidth);
  const stepIdx = currentIdx;

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        const p = await projectApi.get(id);
        setProject(p);
        setRunHistory(p.runs || []);
        const raw = p as unknown as Record<string, unknown>;
        if (raw.confirmed_prd) {
          setConfirmedPrd(raw.confirmed_prd as Record<string, unknown>);
          setPrdReady(true);
        }
        // Check pipeline state — may be in mid-execution
        try {
          const st = await projectApi.getState(id);
          const s = (st.state || {}) as Record<string, unknown>;
          const pPhase = s.phase as string || '';
          if (pPhase && !DIALOGUE_PHASES.has(pPhase)) {
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
        } catch { /* getState may not be available on brand new projects */ }
      } catch { toast.error('项目加载失败，请返回重试'); nav('/app/builder/projects'); }
    })();
  }, [id]);

  // Poll pipeline state when executing (backend runs async)
  const pollRef = useRef<ReturnType<typeof setInterval>>();
  useEffect(() => {
    if (!isPollable(phase) || !id) return;
    pollRef.current = setInterval(async () => {
      try {
        const st = await projectApi.getState(id);
        const s = (st.state || {}) as Record<string, unknown>;
        if (s.phase) setPhase(s.phase as string);
        if (s.step_count != null) setStepCount(s.step_count as number);
        else if (s.iteration != null) setStepCount(s.iteration as number);
        // force re-render: always new object ref
        setSession({ session_id: id as string, phase: (s.phase as string) || phase,
          requirement: '', iteration: (s.iteration as number) || 0,
          error: (s.error as string) || '', prd: null, messages: [],
          ...(s as Record<string, unknown>) } as BuilderSession);
        if (st.runs) setRunHistory(st.runs);
        const p = s.phase as string || '';
        if (isTerminal(p)) {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch { /* retry next tick — transient network error */ }
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
      const newPhase = result.phase || Phase.executing;
      setPhase(newPhase);
      const s = result.state || {};
      setSession({ session_id: id, phase: newPhase as BuilderSession['phase'],
                   requirement: '', iteration: (s as Record<string, unknown>).iteration as number || 0,
                   error: (s as Record<string, unknown>).error as string || '',
                   messages: [], ...(s as Record<string, unknown>) });
    } catch (e: any) { toastGateError(e, '启动失败'); }
    finally { setStarting(false); }
  }, [id, confirmedPrd]);

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

  const handleRecommendTeam = useCallback(async () => {
    if (!id) return;
    setRecommending(true);
    try {
      const resp = await projectApi.recommendTeam(id);
      setRecommendedTeam(resp.recommendation);
      if (resp.recommendation?.parse_error) {
        toast.error('AI推荐解析失败，请查看原始回复');
      } else {
        toast.success('AI已生成团队推荐');
      }
    } catch (e: any) { toastGateError(e, '推荐请求失败'); }
    finally { setRecommending(false); }
  }, [id]);

  const handleRebuild = useCallback(async () => {
    if (!id) return;
    setRebuilding(true);
    try {
      await projectApi.rebuild(id);
      toast.success('已触发重新构建，请等待流水线完成...');
      setPhase(Phase.executing);
      // Poll for state updates
      refreshState();
    } catch (e: any) { toastGateError(e, '重新构建失败'); }
    finally { setRebuilding(false); }
  }, [id]);

  const refreshState = async () => {
    if (!id) return;
    try {
      const st = await projectApi.getState(id);
      const s = (st.state || {}) as Record<string, unknown>;
      const p = s.phase as string || Phase.executing;
      setPhase(p);
      setRunHistory(st.runs || []);
      setSession({
        session_id: id, phase: p as BuilderSession['phase'],
        requirement: '', iteration: (s.iteration as number) || 0,
        error: (s.error as string) || '',
        prd: null, messages: [],
        ...(s as Record<string, unknown>),
      } as BuilderSession);
    } catch { /* transient — polling will retry */ }
  };

  const approve = useCallback(() => {
    if (!id) { toast.error('项目ID未加载'); return; }
    setPipelineLoading(true);
    projectApi.approve(id)
      .then(() => { toast.success('已提交，等待执行…'); return refreshState(); })
      .catch((e) => { toastGateError(e, '操作失败'); })
      .finally(() => setPipelineLoading(false));
  }, [id]);

  const rollbackStage = useCallback((stageId: string) => {
    if (!id) return;
    setPipelineLoading(true);
    projectApi.rollback(id, stageId)
      .then(() => {
        if (stages.length > 0 && stageId === stages[0]?.output_artifact) {
          setPhase(Phase.dialogue);
          setSession(null);
          setPrdReady(false);
          setConfirmedPrd(null);
          setEditingPrd(false);
        }
        return refreshState();
      })
      .catch((e: any) => toastGateError(e, '回退失败'))
      .finally(() => setPipelineLoading(false));
  }, [id, stages]);

  const handleTest = useCallback(async () => {
    if (!id) return;
    setTesting(true);
    setPhase(Phase.testing);
    try {
      const result = await projectApi.test(id);
      setTestResult(result as Record<string, unknown>);
      if ((result as Record<string, unknown>).all_passed) toast.success('所有测试通过！');
      else toast.error('部分测试未通过');
    } catch (e) { toastGateError(e, '测试失败'); }
    finally { setTesting(false); }
  }, [id]);

  const handleDeploy = useCallback(async () => {
    if (!id) return;
    setDeploying(true);
    setPhase(Phase.deploying);
    try {
      const result = await projectApi.deployToApp(id);
      setDeployResult(result as Record<string, unknown>);
      toast.success('部署成功！');
    } catch (e) { toastGateError(e, '部署失败'); }
    finally { setDeploying(false); }
  }, [id]);

  // ── 生成 app 运行时（launch/stop/auto-repair，2026-08-27）──
  const [runtime, setRuntime] = useState<Record<string, unknown> | null>(null);
  const [runtimeBusy, setRuntimeBusy] = useState(false);
  const handleRuntimeLaunch = useCallback(async () => {
    if (!id) return;
    setRuntimeBusy(true);
    try {
      const r = await projectApi.runtimeLaunch(id);
      setRuntime(r as Record<string, unknown>);
      toast.success('已启动生成 app');
    } catch (e) { toastGateError(e, '启动失败'); }
    finally { setRuntimeBusy(false); }
  }, [id]);
  const handleRuntimeStop = useCallback(async () => {
    if (!id) return;
    setRuntimeBusy(true);
    try {
      await projectApi.runtimeStop(id);
      setRuntime(null);
      toast.success('已停止生成 app');
    } catch (e) { toastGateError(e, '停止失败'); }
    finally { setRuntimeBusy(false); }
  }, [id]);
  const handleAutoRepair = useCallback(async () => {
    if (!id) return;
    setRuntimeBusy(true);
    try {
      const r = await projectApi.autoRepair(id);
      setRuntime({ ...(runtime || {}), repair: r as Record<string, unknown> });
      const rep = (r as Record<string, unknown>).repaired;
      if (rep) toast.success('自动修复成功（测试已通过）');
      else toast.error('自动修复未完全通过');
    } catch (e) { toastGateError(e, '自动修复失败'); }
    finally { setRuntimeBusy(false); }
  }, [id, runtime]);

  const [showReject, setShowReject] = useState(false);
  const [rejectFeedback, setRejectFeedback] = useState('');
  const rejectHITL = useCallback(() => {
    if (!id || !rejectFeedback.trim()) return;
    projectApi.reject(id, rejectFeedback.trim())
      .then(() => {
        refreshState();
        toast.success('已驳回');
      })
      .catch((e: any) => toastGateError(e, '驳回失败'))
      .finally(() => {
        setShowReject(false);
        setRejectFeedback('');
      });
  }, [id, rejectFeedback, refreshState]);

  const stories = (confirmedPrd?.user_stories as Array<Record<string, unknown>>) || [];

  if (DIALOGUE_PHASES.has(phase)) {
    return (
      <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-4 space-y-4">
        {/* ── Phase progress bar ── */}
        <div className="flex items-center gap-1 bg-dark-card border border-dark-border rounded-lg p-2">
          {stages.map((s, i) => (
            <React.Fragment key={s.id || i}>
              <span className={`flex-1 text-center text-[11px] px-1 py-1 rounded transition-colors ${
                i < stepIdx ? 'bg-green-500/20 text-green-300' :
                i === stepIdx ? 'bg-primary/20 text-primary font-semibold' :
                'text-gray-600'
              }`}>
                {i < stepIdx ? '✓ ' : ''}{s.agent_name || s.id || `阶段${i+1}`}
              </span>
              {i < stages.length - 1 && <span className="text-gray-700 text-[10px]">→</span>}
            </React.Fragment>
          ))}
        </div>
        {/* ── Progress percentage ── */}
        <div className="h-1.5 bg-dark-hover rounded-full overflow-hidden">
          <div className="h-full bg-primary rounded-full transition-all duration-700" style={{ width: `${progressPct}%` }} />
        </div>
        <div className="text-[10px] text-gray-500 text-right">{progressPct}% ({currentIdx + 1}/{totalStages} 阶段{stepCount > 0 ? ` · 步 ${stepCount}/${maxSteps}` : ''})</div>
        <div className="flex items-center gap-3">
          <Button variant="ghost" onClick={() => nav('/app/builder/projects')}><ArrowLeft className="w-4 h-4" /></Button>
          <div><h1 className="text-lg font-bold text-gray-100 truncate max-w-lg">{project?.name || '项目'}</h1>
          {teamLabel && <p className="text-[11px] text-gray-500 mt-0.5">团队：{teamLabel}</p>}
          {project?.description && <p className="text-[11px] text-gray-500 mt-0.5 line-clamp-1 max-w-md">{project?.description}</p>}</div>
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
                <Button size="sm" variant="outline" onClick={handleRebuild} loading={rebuilding} icon={<RefreshCw className="w-3.5 h-3.5" />}>重新构建</Button>
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
                        {r.run_id && <RunEventTimeline runId={r.run_id} />}
                      </div>
                    </details>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {prdReady && !editingPrd && (
          <div className="p-4 rounded-lg border border-green-500/30 bg-green-500/5 space-y-3">
            <div className="text-xs text-gray-400">确认需求后启动流水线</div>
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" onClick={confirmAndStart} loading={starting} icon={<Play className="w-4 h-4" />}>确认需求，开始构建</Button>
              <Button variant="secondary" onClick={handleRecommendTeam} loading={recommending} icon={<Rocket className="w-4 h-4" />}>AI 推荐团队</Button>
            </div>
            {recommendedTeam && !recommendedTeam.parse_error && (
              <div className="mt-3 p-3 rounded bg-dark-hover/20 border border-blue-500/30 text-xs">
                {(recommendedTeam.reasoning as string) && <p className="text-blue-300 mb-2">{(recommendedTeam.reasoning as string)?.slice(0, 200)}</p>}
                <p className="text-gray-400">推荐 {(recommendedTeam.stages as Array<Record<string, unknown>>)?.length || 0} 个阶段：</p>
                <ul className="mt-1 space-y-0.5">
                  {(recommendedTeam.stages as Array<Record<string, unknown>>)?.map((s: Record<string, unknown>, i: number) => (
                    <li key={i} className="text-gray-300">
                      <span className="text-gray-500">{String(s.order)}.</span> {String(s.agent_name || s.agent_id)} {s.hitl ? '🔒' : ''}
                      <span className="text-gray-500 ml-1">{s.phase ? `· ${s.phase}` : ''}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </motion.div>
      <PrdDetailModal open={showPrdDetail} prd={confirmedPrd} onClose={() => setShowPrdDetail(false)} onEdit={startEditing} projectId={id} onRebuild={handleRebuild} />
      </>
    );
  }

  return (
    <>
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-4 space-y-4">
      {/* ── Phase progress bar ── */}
      <div className="flex items-center gap-1 bg-dark-card border border-dark-border rounded-lg p-2">
        {stages.map((s, i) => (
          <React.Fragment key={s.id || i}>
            <span className={`flex-1 text-center text-[11px] px-1 py-1 rounded transition-colors ${
              i < stepIdx ? 'bg-green-500/20 text-green-300' :
              i === stepIdx ? 'bg-primary/20 text-primary font-semibold' :
              'text-gray-600'
            }`}>
              {i < stepIdx ? '✓ ' : ''}{s.agent_name || s.id || `阶段${i+1}`}
            </span>
            {i < stages.length - 1 && <span className="text-gray-700 text-[10px]">→</span>}
          </React.Fragment>
        ))}
      </div>
      {/* ── Progress percentage ── */}
      <div className="h-1.5 bg-dark-hover rounded-full overflow-hidden">
        <div className="h-full bg-primary rounded-full transition-all duration-700" style={{ width: `${progressPct}%` }} />
      </div>
      <div className="text-[10px] text-gray-500 text-right">{progressPct}% ({currentIdx + 1}/{totalStages} 阶段{stepCount > 0 ? ` · 步 ${stepCount}/${maxSteps}` : ''})</div>
      <div className="flex items-center gap-3">
        <Button variant="ghost" onClick={() => nav('/app/builder/projects')}><ArrowLeft className="w-4 h-4" /></Button>
        <div><h1 className="text-lg font-bold text-gray-100 truncate max-w-lg">{project?.name || '项目'}</h1>
        {teamLabel && <p className="text-[11px] text-gray-500 mt-0.5">团队：{teamLabel}</p>}</div>
      </div>
      <Card>
        <CardHeader title="流水线执行" extra={
          <div className="flex gap-2">
            <select className="text-xs bg-dark-hover border border-dark-border rounded px-2 py-1 text-gray-300"
              onChange={(e) => { if (e.target.value) rollbackStage(e.target.value); e.target.value = ''; }}
              defaultValue="">
              <option value="">↩ 回退...</option>
              {stages.filter(s => {
                const key = (s as any).output_artifact || '';
                return key && (session as Record<string,any>)?.[key];
              }).map(s => (
                <option key={(s as any).output_artifact} value={(s as any).output_artifact}>
                  回退 {(s as any).agent_name || (s as any).agent_id || (s as any).output_artifact}
                </option>
              ))}
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
            onReject={() => { setShowReject(true); }}
            onRollback={(key) => rollbackStage(key)}
            loading={pipelineLoading}
          />
        )}</CardContent>
      </Card>

      {/* ── Health Report panel ── */}
      {session?.phase === Phase.done && (
        <div className="p-4 rounded-lg border border-blue-500/30 bg-blue-500/5 mb-3">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-blue-300 flex items-center gap-2">
              <BarChart3 className="w-4 h-4" />流水线健康报告
            </h3>
            <Button variant="ghost" size="sm" onClick={async () => {
              if (!id) return;
              try { const r = await projectApi.getHealthReport(id); setHealthReport(r as any); } catch {}
            }}>
              刷新
            </Button>
          </div>
          {healthReport ? (
            <div className="space-y-2 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-2xl font-bold text-blue-300">{healthReport.overall_score}</span>
                <span className="text-gray-400">/100 综合评分</span>
              </div>
              {healthReport.dimensions?.map((d: any) => (
                <div key={d.name} className="flex items-center gap-2">
                  <span className="w-20 text-gray-400 truncate">{d.display_name || d.name}</span>
                  <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
                    <div className="h-full bg-blue-500 rounded-full" style={{ width: `${Math.min(100, (d.score/d.max_score)*100)}%` }} />
                  </div>
                  <span className="w-8 text-right">{d.score}</span>
                </div>
              ))}
              {healthReport.stages?.map((s: any) => (
                <div key={s.stage_id} className="flex items-center gap-1 text-gray-500">
                  <span className={`w-2 h-2 rounded-full ${s.verdict === 'passed' ? 'bg-green-400' : s.verdict === 'partial' ? 'bg-yellow-400' : 'bg-red-400'}`} />
                  <span>{s.agent_id}: {s.overall_score}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-500">点击刷新加载健康报告</p>
          )}
        </div>
      )}

      {/* ── Review panel ── */}
      {session?.phase === Phase.done && project?.team_stages && (
        <div className="space-y-3 mb-3">
          <div className="p-4 rounded-lg border border-purple-500/30 bg-purple-500/5">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="text-sm font-semibold text-purple-300 flex items-center gap-2">
                  <Eye className="w-4 h-4" />审阅 Pre-Release Review
                </h3>
                <p className="text-xs text-gray-400 mt-1">检查每个阶段的产出，确认无误后再部署</p>
              </div>
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={async () => {
                  if (!id) return;
                  try {
                    await projectApi.chat(id, '请检查所有阶段的产出，分析是否存在不一致或遗漏的问题，给出诊断报告。');
                    toast.success('AI 诊断已提交，查看对话获取结果');
                  } catch (e) { toastGateError(e, 'AI 诊断失败'); }
                }} icon={<Sparkles className="w-3.5 h-3.5" />}>
                  AI 诊断
                </Button>
              </div>
            </div>

            <div className="space-y-2">
              {project.team_stages.map((stage, idx) => {
                const hasOutput = session && (session as Record<string, unknown>)[stage.output_artifact || ''];
                const artifact = hasOutput ? (session as Record<string, unknown>)[stage.output_artifact || ''] as Record<string, unknown> : null;
                const summary = artifact?.summary || artifact?.description || '';
                const files = (artifact?.files as Array<{path: string}> | undefined);
                const isDone = hasOutput != null;

                return (
                  <div key={stage.id || idx}
                    className={`p-3 rounded border flex items-start justify-between gap-3 ${isDone ? 'border-green-500/30 bg-green-500/5' : 'border-dark-border bg-dark-hover/30'}`}>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-full ${isDone ? 'bg-green-400' : 'bg-gray-600'}`} />
                        <span className="text-xs font-medium text-gray-200">{stage.agent_name || stage.agent_id}</span>
                        <span className="text-[10px] text-gray-500">({stage.phase})</span>
                      </div>
                      {isDone && summary && (
                        <p className="text-[11px] text-gray-400 mt-1 line-clamp-2">{typeof summary === 'string' ? summary : JSON.stringify(summary).slice(0, 120)}</p>
                      )}
                      {isDone && files && files.length > 0 && (
                        <p className="text-[10px] text-gray-500 mt-0.5">{files.length} 个文件生成</p>
                      )}
                    </div>
                    <div className="flex gap-1 flex-shrink-0">
                      {isDone && (
                        <button
                          onClick={() => {
                            const feedback = window.prompt(
                              `修改 ${stage.agent_name || stage.agent_id} 的产出，请输入你的反馈：\n\n` +
                              `例："请增加 DELETE 接口"、"请用 apiClient 封装而不是直接写 fetch"、"字段名请用 camelCase"\n\n` +
                              `当前产出摘要：${typeof summary === 'string' ? summary.slice(0, 200) : ''}`
                            );
                            if (feedback?.trim() && id && stage.id) {
                              setPipelineLoading(true);
                              projectApi.regenerateStage(id, stage.id, feedback.trim())
                                .then(() => { toast.success('已提交修改，正在重新生成...'); refreshState(); })
                                .catch((e: any) => toastGateError(e, '重新生成失败'))
                                .finally(() => setPipelineLoading(false));
                            }
                          }}
                          className="flex items-center gap-1 px-2 py-1 text-[10px] rounded bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors"
                        >
                          <RefreshCw className="w-3 h-3" /> 修改
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* ── Test & Deploy panel ── */}
      {session?.phase === Phase.done && (
        <div className="space-y-3">
          {/* Test section */}
          <div className="p-4 rounded-lg border border-yellow-500/30 bg-yellow-500/5">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-yellow-300 flex items-center gap-2">
                  <TestTube className="w-4 h-4" />运行测试
                </h3>
                <p className="text-xs text-gray-400 mt-1">执行 E2E Smoke 测试和仓库测试</p>
              </div>
              <Button variant="secondary" onClick={handleTest} loading={testing} icon={<TestTube className="w-4 h-4" />}>
                运行测试
              </Button>
            </div>
            {testResult && (
              <div className={`mt-3 p-3 rounded text-xs ${(testResult.all_passed as boolean) ? 'bg-green-500/10 text-green-300' : 'bg-red-500/10 text-red-300'}`}>
                <p className="font-semibold mb-2">{(testResult.all_passed as boolean) ? '✓ 所有测试通过' : '✗ 部分测试未通过'}</p>
                {(() => {
                  // 测试经理真实测试报告（real_tests → test_report，结构特征判断而非硬编码 key）
                  const rt = (testResult.real_tests as Record<string, unknown> | undefined) ?? {};
                  const report = (rt.test_report as Record<string, unknown> | undefined) ?? {};
                  const results = (report.test_results as Record<string, unknown> | undefined) ?? {};
                  const bugs = (report.bug_summary as Record<string, unknown> | undefined) ?? {};
                  const failedTests = Array.isArray(bugs.failed_tests) ? (bugs.failed_tests as string[]) : [];
                  const hasReport = results && typeof results.total === 'number';
                  if (!hasReport) {
                    return (
                      <details className="mt-1">
                        <summary className="cursor-pointer text-gray-400">详细结果</summary>
                        <pre className="mt-2 text-[11px] whitespace-pre-wrap font-mono">{JSON.stringify({ e2e: testResult.e2e_smoke, repo: testResult.repo_tests }, null, 2)}</pre>
                      </details>
                    );
                  }
                  return (
                    <div className="mt-2 space-y-2">
                      <div className="flex gap-3 text-[11px]">
                        <span className="text-green-400">通过 {String(results.passed ?? 0)}</span>
                        <span className="text-red-400">失败 {String(results.failed ?? 0)}</span>
                        <span className="text-yellow-400">错误 {String(results.errors ?? 0)}</span>
                        <span className="text-gray-400">跳过 {String(results.skipped ?? 0)}</span>
                      </div>
                      {failedTests.length > 0 && (
                        <div className="bg-red-500/10 rounded p-2">
                          <p className="font-semibold text-red-300 mb-1">Bug 清单（{String(bugs.total_bugs ?? failedTests.length)}）</p>
                          <ul className="space-y-0.5">
                            {failedTests.slice(0, 8).map((t: string, i: number) => (
                              <li key={i} className="truncate" title={t}>{t}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {typeof bugs.suggested_fix === 'string' && bugs.suggested_fix.length > 0 && (
                        <div className="bg-blue-500/10 rounded p-2">
                          <p className="font-semibold text-blue-300 mb-1">修复建议</p>
                          <p className="whitespace-pre-wrap break-words text-[11px] text-gray-200">{(bugs.suggested_fix as string).slice(0, 600)}</p>
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            )}
          </div>

          {/* Deploy section */}
          <div className="p-4 rounded-lg border border-green-500/30 bg-green-500/5">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-green-300 flex items-center gap-2">
                  <Rocket className="w-4 h-4" />部署到 App
                </h3>
                <p className="text-xs text-gray-400 mt-1">一键部署到 aiPlat-app 应用层</p>
              </div>
              <Button variant="primary" onClick={handleDeploy} loading={deploying} icon={<Rocket className="w-4 h-4" />}>
                部署
              </Button>
            </div>
            {deployResult && (
              <div className="mt-3 p-3 rounded text-xs bg-green-500/10 text-green-300">
                <p className="font-semibold">✓ 部署成功</p>
                <p className="mt-1">部署目录: {(deployResult.deploy_dir as string) || '-'}</p>
                <p className="mt-1">
                  App URL: <a href={(deployResult.app_url as string) || '#'} target="_blank" rel="noreferrer" className="text-primary underline">
                    {String(deployResult.app_url || '-')}
                  </a>
                </p>
              </div>
            )}
          </div>

          {/* Runtime section: 生成 app 运行控制（daemon_jobs 托管 + 自动修复） */}
          <div className="p-4 rounded-lg border border-cyan-500/30 bg-cyan-500/5">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-cyan-300 flex items-center gap-2">
                  <Play className="w-4 h-4" />生成 app 运行时
                </h3>
                <p className="text-xs text-gray-400 mt-1">daemon_jobs 托管启动 / 停止 / 测试失败自动修复</p>
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={handleRuntimeLaunch} loading={runtimeBusy} icon={<Play className="w-4 h-4" />}>
                  启动
                </Button>
                <Button variant="secondary" onClick={handleRuntimeStop} loading={runtimeBusy} icon={<X className="w-4 h-4" />}>
                  停止
                </Button>
                <Button variant="primary" onClick={handleAutoRepair} loading={runtimeBusy} icon={<Sparkles className="w-4 h-4" />}>
                  自动修复
                </Button>
              </div>
            </div>
            {runtime && (
              <div className="mt-3 p-3 rounded text-xs bg-cyan-500/10 text-cyan-200">
                <p className="font-semibold">
                  {runtime.kind ? `入口类型: ${String(runtime.kind)}` : ''}
                  {runtime.port ? ` · 端口: ${String(runtime.port)}` : ''}
                  {runtime.pid ? ` · PID: ${String(runtime.pid)}` : ''}
                  {runtime.job_id ? ` · Job: ${String(runtime.job_id)}` : ''}
                </p>
                {runtime.error && <p className="mt-1 text-red-300">错误: {String(runtime.error)}</p>}
                {(runtime.repair as Record<string, unknown> | undefined) && (
                  <div className="mt-2 space-y-1">
                    <p className={(runtime.repair as Record<string, unknown>).repaired ? 'text-green-300' : 'text-yellow-300'}>
                      自动修复: {(runtime.repair as Record<string, unknown>).repaired ? '已通过' : '未完全通过'}
                      {' · '}轮次: {String((runtime.repair as Record<string, unknown>).rounds ?? 0)}
                      {((runtime.repair as Record<string, unknown>).writeback_files as string[] | undefined)?.length
                        ? ` · 写回 ${String(((runtime.repair as Record<string, unknown>).writeback_files as string[]).length)} 个文件` : ''}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </motion.div>
    <PrdDetailModal open={showPrdDetail} prd={confirmedPrd} onClose={() => setShowPrdDetail(false)} onEdit={startEditing} />
    </>
  );
};

// Shared modal — rendered outside phase conditions
const PrdDetailModal: React.FC<{
  open: boolean; prd: Record<string, unknown> | null; onClose: () => void; onEdit: () => void;
  projectId?: string; onRebuild?: () => void;
}> = ({ open, prd, onClose, onEdit, projectId, onRebuild }) => {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);

  const startEdit = () => { setText(JSON.stringify(prd, null, 2)); setEditing(true); };
  const cancelEdit = () => setEditing(false);

  const savePrd = async () => {
    if (!projectId) return;
    try {
      let parsed: Record<string, unknown>;
      try { parsed = JSON.parse(text); } catch { toast('JSON 格式错误，请检查'); return; }
      setSaving(true);
      await projectApi.updatePrd(projectId, parsed);
      toast.success('PRD 已保存');
      setEditing(false);
      onClose();
      if (onRebuild) onRebuild();
    } catch (e) { toastGateError(e, '保存 PRD 失败'); }
    finally { setSaving(false); }
  };

  if (!open || !prd) return null;
  const stories = (prd.user_stories as Array<Record<string, unknown>>) || [];
  const constraints = (prd.constraints as string[]) || [];

  if (editing) {
    return (
      <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center" onClick={cancelEdit}>
        <motion.div initial={{ scale: 0.95 }} animate={{ scale: 1 }}
          className="bg-dark-card border border-dark-border rounded-xl p-6 w-full max-w-2xl max-h-[85vh] flex flex-col"
          onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-bold text-gray-100">编辑 PRD (JSON)</h2>
            <Button size="sm" variant="ghost" onClick={cancelEdit}><X className="w-4 h-4" /></Button>
          </div>
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            className="flex-1 min-h-[400px] bg-dark-hover border border-dark-border rounded-lg p-3 text-sm text-gray-200 font-mono resize-none focus:outline-none focus:border-primary"
          />
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="ghost" onClick={cancelEdit}>取消</Button>
            <Button variant="primary" onClick={savePrd} loading={saving} icon={<Save className="w-4 h-4" />}>保存 PRD</Button>
          </div>
        </motion.div>
      </div>
    );
  }

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
          <Button variant="ghost" onClick={startEdit} icon={<Pencil className="w-3.5 h-3.5" />}>编辑 JSON</Button>
          <Button variant="primary" onClick={() => { onClose(); onEdit(); }} icon={<Pencil className="w-3.5 h-3.5" />}>对话修改</Button>
        </div>
      </motion.div>
    </div>
  );
};

// Temporary redirect to Studio for debugging — crashes caused by ChatWidget/motion
import { Navigate } from 'react-router-dom';
const SafeProjectDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  return <Navigate to={`/studio?project=${id}`} replace />;
};

export default SafeProjectDetailPage;
