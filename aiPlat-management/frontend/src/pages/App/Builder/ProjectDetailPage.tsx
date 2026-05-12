import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { CheckCircle, ArrowLeft, Play, Clock, BarChart3, Eye, Pencil, X, Rocket, TestTube, Check, Loader2 } from 'lucide-react';
import { projectApi, type ProjectItem, type ProjectRun, type BuilderSession } from '../../../services';
import { BuilderPipeline } from '../../../components/Builder/BuilderPipeline';
import { ChatWidget } from '../../../components/ui/ChatWidget';
import { Card, CardHeader, CardContent, Button, toast } from '../../../components/ui';
import { toastGateError } from '../../../components/ui';

const ProjectDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const [project, setProject] = useState<ProjectItem | null>(null);
  const [phase, setPhase] = useState('idle');
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
    if ((phase !== 'executing' && phase !== 'paused' && !phase.includes('approval')) || !id) return;
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
        if (p === 'done' || p === 'failed') {
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
    } catch (e: any) { toastGateError(e, '启动失败'); }
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

  const approve = useCallback(() => {
    if (!id) { toast.error('项目ID未加载'); return; }
    setPipelineLoading(true);
    projectApi.approve(id)
      .then(() => { toast.success('已提交，等待执行…'); setPipelineLoading(false); })
      .catch((e) => { toastGateError(e, '操作失败'); setPipelineLoading(false); });
  }, [id]);

  const rollbackStage = useCallback((stageId: string) => {
    if (!id) return;
    projectApi.rollback(id, stageId).catch((e: any) => toastGateError(e, '回退失败'));
    if (stages.length > 0 && stageId === stages[0]?.output_artifact) {
      setPhase('dialogue');
      setSession(null);
      return;
    }
  }, [id, stages]);

  const startFix = useCallback(async () => {
    if (!id) return;
    setPipelineLoading(true);
    try {
      await projectApi.startFix(id);
      await refreshState();
    } catch (e: any) { toastGateError(e, '启动修复失败'); }
    finally { setPipelineLoading(false); }
  }, [id]);

  const handleTest = useCallback(async () => {
    if (!id) return;
    setTesting(true);
    setPhase('testing');
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
    setPhase('deploying');
    try {
      const result = await projectApi.deployToApp(id);
      setDeployResult(result as Record<string, unknown>);
      toast.success('部署成功！');
    } catch (e) { toastGateError(e, '部署失败'); }
    finally { setDeploying(false); }
  }, [id]);

  const [showReject, setShowReject] = useState(false);
  const [rejectFeedback, setRejectFeedback] = useState('');
  const rejectHITL = useCallback(() => {
    if (!id || !rejectFeedback.trim()) return;
    projectApi.reject(id, rejectFeedback.trim()).catch((e: any) => toastGateError(e, '驳回失败'));
    setShowReject(false);
    setRejectFeedback('');
  }, [id, rejectFeedback]);

  const stories = (confirmedPrd?.user_stories as Array<Record<string, unknown>>) || [];
  const constraints = (confirmedPrd?.constraints as string[]) || [];

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
  const stepIdx = currentIdx;  // for backward compat in rendering

  if (phase === 'idle' || phase === 'dialogue') {
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
          <Button variant="ghost" onClick={() => nav('/app/projects')}><ArrowLeft className="w-4 h-4" /></Button>
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
          <div className="p-4 rounded-lg border border-green-500/30 bg-green-500/5 space-y-3">
            <div className="text-xs text-gray-400">确认需求后启动流水线</div>
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" onClick={confirmAndStart} loading={starting} icon={<Play className="w-4 h-4" />}>确认需求，开始构建</Button>
              <Button variant="secondary" onClick={handleRecommendTeam} loading={recommending} icon={<Rocket className="w-4 h-4" />}>AI 推荐团队</Button>
            </div>
            {recommendedTeam && !recommendedTeam.parse_error && (
              <div className="mt-3 p-3 rounded bg-dark-hover/20 border border-blue-500/30 text-xs">
                {recommendedTeam.reasoning && <p className="text-blue-300 mb-2">{(recommendedTeam.reasoning as string)?.slice(0, 200)}</p>}
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
      <PrdDetailModal open={showPrdDetail} prd={confirmedPrd} onClose={() => setShowPrdDetail(false)} onEdit={startEditing} />
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
        <Button variant="ghost" onClick={() => nav('/app/projects')}><ArrowLeft className="w-4 h-4" /></Button>
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
            onReject={(key) => { setShowReject(true); }}
            onRollback={(key) => rollbackStage(key)}
            loading={pipelineLoading}
          />
        )}</CardContent>
      </Card>

      {/* ── Test & Deploy panel ── */}
      {session?.phase === 'done' && (
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
                <details className="mt-1">
                  <summary className="cursor-pointer text-gray-400">详细结果</summary>
                  <pre className="mt-2 text-[11px] whitespace-pre-wrap font-mono">{JSON.stringify({ e2e: testResult.e2e_smoke, repo: testResult.repo_tests }, null, 2)}</pre>
                </details>
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
        </div>
      )}
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
