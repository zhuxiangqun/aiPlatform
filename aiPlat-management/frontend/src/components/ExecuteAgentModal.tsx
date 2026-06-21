import React, { useCallback, useEffect, useRef, useState } from 'react';
import { workspaceAgentApi, kbApi } from '../services';
import type { Agent } from '../services';
import { Button, Modal, Textarea, toast } from './ui';
import { toastGateError } from './ui';
import ExecutionViewer, { StructuredDetail } from './ExecutionViewer/ExecutionViewer';
import { browserTestApi } from '../services/browserTestApi';

interface ExecuteAgentModalProps {
  open: boolean;
  agent: Agent | null;
  onClose: () => void;
}

const ExecuteAgentModal: React.FC<ExecuteAgentModalProps> = ({ open, agent, onClose }) => {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [helpLoading, setHelpLoading] = useState(false);
  const [helpMarkdown, setHelpMarkdown] = useState<string>('');
  const [examples, setExamples] = useState<Array<{ title: string; content: string }>>([]);
  const [result, setResult] = useState<{ status: string; execution_id?: string; output?: unknown; error?: any; error_message?: string; error_detail?: any; run_id?: string; tokens?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number }; eval?: { score?: number; grade?: string; total_tasks?: number; has_data?: boolean }; duration_ms?: number; steps?: number } | null>(null);
  const [toolset, setToolset] = useState<string>('workspace_default');
  const [stopping, setStopping] = useState(false);
  const [progress, setProgress] = useState<{ total_pages: number; total_actions: number; passed: number; failed: number; skipped: number; duration_ms: number } | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [caseGenLoading, setCaseGenLoading] = useState(false);
  const [caseExcelPath, setCaseExcelPath] = useState('');
  const [caseUploadedPath, setCaseUploadedPath] = useState('');
  const [autoApprove, setAutoApprove] = useState(true);
  const [flowFullscreen, setFlowFullscreen] = useState(false);
  const [selectedFlowNode, setSelectedFlowNode] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // ── Routing state ──
  const [routingResult, setRoutingResult] = useState<{ intent: string; confidence: number; primary_route?: { kind: string; target: string; score: number }; suggested_skill_ids: string[]; suggested_tool_ids: string[]; entities: Record<string, unknown>; should_clarify: boolean } | null>(null);
  const [routingLoading, setRoutingLoading] = useState(false);

  // ── Knowledge base selector (for RAG agents) ──
  const [domains, setDomains] = useState<{ id: string; name: string; collection_id: string }[]>([]);
  const [selectedDomain, setSelectedDomain] = useState('');

  const isSiteTester = agent?.skills?.includes('site_tester') || agent?.name === 'site_tester_agent' || agent?.name === '全站自动化测试' || agent?.display_name === '全站自动化测试' || false;

  const isRagAgent = agent?.agent_type === 'materials_chat';

  useEffect(() => {
    const load = async () => {
      if (!open || !agent) return;
      try {
        const t = String((agent as any)?.metadata?.toolset || '');
        if (t) setToolset(t);
        else setToolset('workspace_default');
      } catch {
        setToolset('workspace_default');
      }
      // Load domains for RAG agent knowledge base selector
      if (isRagAgent) {
        kbApi.listDomains().then(r => {
          setDomains(r.domains || []);
        }).catch(() => setDomains([]));
      }
      setHelpLoading(true);      try {
        const res = await workspaceAgentApi.getExecutionHelp(agent.id);
        setHelpMarkdown(String((res as any)?.help_markdown || ''));
        setExamples(((res as any)?.examples || []) as any);
      } catch {
        setHelpMarkdown('');
        setExamples([]);
      } finally {
        setHelpLoading(false);
      }
    };
    load();
  }, [open, agent?.id]);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const handleExecute = async () => {
    if (!agent) return;
    if (isSiteTester) {
      let parsed: Record<string, unknown> = {};
      if (input.trim()) {
        try { parsed = JSON.parse(input); } catch { parsed = { message: input }; }
      }
      const routes: string[] = Array.isArray((parsed as any).routes) ? (parsed as any).routes : [];
      let includePatterns: string[] | undefined = Array.isArray((parsed as any).include_patterns) ? (parsed as any).include_patterns : undefined;
      if (includePatterns === undefined && routes.length > 0) includePatterns = routes;
      const cfg: Record<string, unknown> = {
        base_url: String((parsed as any).base_url || ''),
        routes,
        max_recursion_depth: Number((parsed as any).max_recursion_depth ?? 3),
        include_patterns: includePatterns,
        allow_writes: Boolean((parsed as any).allow_writes),
        headless: Boolean((parsed as any).headless ?? false),
        video_enabled: Boolean((parsed as any).video_enabled ?? true),
        action_timeout_ms: Number((parsed as any).action_timeout_ms ?? 15000),
        login_url: String((parsed as any).login_url || ''),
        accounts: (parsed as any).accounts || [],
      };
      setLoading(true); setProgress(null); setResult(null); stopPolling();
      try {
        const startRes = await browserTestApi.start(cfg as any);
        if (!(startRes as any).ok) { toast.error('启动失败'); setLoading(false); return; }
        toast.success('浏览器测试已启动');
        pollingRef.current = setInterval(async () => {
          try {
            const s = await browserTestApi.status();
            setProgress(s.summary || { total_pages: 0, total_actions: 0, passed: 0, failed: 0, skipped: 0, duration_ms: 0 });
            if (!s.running) {
              stopPolling();
              try {
                const r = await browserTestApi.report(true);
                const video = (r as any).video_path || '';
                const lines: string[] = [];
                lines.push(`全站测试完成: ${r.total_pages}页 ${r.total_actions}步 ✅${r.passed} ❌${r.failed} ⏭${r.skipped}`);
                lines.push(`耗时: ${(r.total_duration_ms / 1000).toFixed(1)}s`);
                if (video) lines.push(`录像: ${video} (WebM格式，可用浏览器或VLC打开)`);
                if (r.pages) {
                  lines.push(''); lines.push('页面详情:');
                  for (const p of r.pages as any[]) {
                    lines.push(`  ${p.url} (${p.elements_found}元素→${p.actions?.length || 0}步: ✅${p.actions?.filter((a: any) => a.result === 'passed').length || 0} ❌${p.actions?.filter((a: any) => a.result === 'failed').length || 0})`);
                    if (p.actions) {
                      for (const a of (p.actions as any[]).slice(0, 5))
                        lines.push(`    [${a.result?.slice(0, 2) || '??'}] ${a.action}(${a.element_role}): ${(a.element_text || '').slice(0, 40)}`);
                      if (p.actions.length > 5) lines.push('    ...');
                    }
                  }
                }
                if (r.errors?.length) { lines.push(''); lines.push('错误:'); for (const e of r.errors.slice(0, 5)) lines.push('  - ' + e); }
                setResult({ status: 'completed', output: lines.join('\n') });
              } catch (e: any) { setResult({ status: 'failed', error: '获取报告失败: ' + (e?.message || String(e)) }); }
              setLoading(false);
            }
          } catch { /* silent */ }
        }, 2000);
      } catch (e: any) { toast.error(`启动失败: ${e?.message || e}`); setLoading(false); }
      return;
    }
    let parsedInput: Record<string, unknown> = {};
    if (input.trim()) { try { parsedInput = JSON.parse(input); } catch { parsedInput = { message: input }; } }
    setLoading(true);
    try {
      const streamOpts = { ...((parsedInput.options || {}) as Record<string, unknown>), toolset, stream: true };
      const execPayload: any = { input: parsedInput, options: streamOpts, config: (parsedInput.config || {}) as Record<string, unknown> };
      if (isRagAgent && selectedDomain) {
        execPayload.context = { scope: { collection_id: selectedDomain, doc_ids: [] }, collection_id: selectedDomain, tenant_id: 'default' };
      }
      const result = await workspaceAgentApi.execute(agent.id, execPayload);
      const status = String((result as any)?.status || 'ok');
      const runId = (result as any)?.run_id || (result as any)?.execution_id || '';
      const execEval = (result as any)?.eval;
      const execDuration = (result as any)?.duration_ms as number | undefined;
      const execSteps = ((result as any)?.metadata?.steps as number) || undefined;
      setResult({ status, execution_id: String((result as any)?.execution_id || ''), run_id: runId, output: (result as any)?.output, error: (result as any)?.error, tokens: (result as any)?.tokens, eval: execEval, duration_ms: execDuration, steps: execSteps });
      if (runId && (status === 'running' || status === 'completed' || status === 'accepted')) {
        setFlowFullscreen(true);
      }
      // ── Stream mode: poll execution status until completion ──
      if (status === 'running' && runId) {
        let polls = 0;
        let stopped = false;
        pollingRef.current = setInterval(async () => {
          if (stopped) return;
          polls++;
          try {
            const sRes = await fetch(`/api/core/executions/${encodeURIComponent(runId)}/status`);
            if (sRes.ok) {
              const sData = await sRes.json();
              const newStatus = sData?.status;
              if (newStatus && newStatus !== 'running') {
                stopped = true;
                stopPolling();
                setResult(prev => ({
                  ...prev!,
                  status: newStatus === 'completed' ? 'completed' : 'failed',
                  output: prev?.output ?? sData?.output,
                  error: sData?.error || prev?.error,
                  duration_ms: sData?.duration_ms ?? prev?.duration_ms,
                }));
                if (newStatus === 'completed') toast.success('执行完成');
                else toast.error(`执行状态: ${newStatus}`);
                return;
              }
            }
          } catch { /* still running */ }
          if (polls >= 100) { stopPolling(); toast.error('执行超时（300s）', 'Agent 可能仍在后台运行，查看诊断详情获取最新状态。'); }
        }, 3000);
      }
      if (status === 'completed') toast.success('执行成功'); else if (status !== 'running') toast.success(`状态: ${status}`);
    } catch (e: any) { setResult({ status: 'failed', error: String(e?.message || e?.detail || '执行失败') }); toastGateError(e, '执行失败'); }
    finally { setLoading(false); }
  };

  const handleStop = async () => {
    setStopping(true);
    try {
      await browserTestApi.stop();
      await browserTestApi.stopCaseExecution();
      toast.success('已请求停止');
    } catch (e: any) { toast.error(`停止失败: ${e?.message || e}`); }
    finally { setStopping(false); }
  };

  const handleAnalyzeIntent = async () => {
    if (!input.trim()) { toast.warning('请先输入内容'); return; }
    setRoutingLoading(true);
    setRoutingResult(null);
    try {
      const res = await (workspaceAgentApi as any).classify({ 
        message: input, 
        agent_id: agent?.id || '',
        agent_name: agent?.name || '',
        agent_type: (agent as any)?.agent_type || '',
        available_skills: agent?.skills || [],
        available_tools: agent?.tools || [],
      });
      setRoutingResult(res as any);
    } catch (e: any) {
      toast.error('意图分析失败', e?.message || '服务不可用');
    } finally {
      setRoutingLoading(false);
    }
  };

  const handleGenerateCases = async () => {
    let parsed: Record<string, unknown> = {};
    if (input.trim()) { try { parsed = JSON.parse(input); } catch { parsed = { message: input }; } }
    const routes: string[] = Array.isArray((parsed as any).routes) ? (parsed as any).routes : [];
    let incPat: string[] | undefined = Array.isArray((parsed as any).include_patterns) ? (parsed as any).include_patterns : undefined;
    if (incPat === undefined && routes.length > 0) incPat = routes;
    setCaseGenLoading(true);
    try {
      const res = await browserTestApi.generateCases({
        base_url: String((parsed as any).base_url || ''),
        routes,
        max_recursion_depth: Number((parsed as any).max_recursion_depth ?? 3),
        include_patterns: incPat,
        login_url: String((parsed as any).login_url || ''),
        accounts: (parsed as any).accounts,
      } as any);
      if ((res as any).ok) { setCaseExcelPath((res as any).xlsx_path || ''); toast.success(`已生成 ${(res as any).total_cases} 条测试用例`); }
      else toast.error('用例生成失败');
    } catch (e: any) { toast.error(`生成失败: ${e?.message || e}`); }
    finally { setCaseGenLoading(false); }
  };

  const handleDownloadExcel = async () => {
    if (!caseExcelPath) return;
    window.open(`/api/core/browser/test/download?path=${encodeURIComponent(caseExcelPath)}`, '_blank');
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const res = await browserTestApi.uploadCases(file);
      if ((res as any).ok) {
        setCaseUploadedPath((res as any).path);
        toast.success('文件已上传');
      } else {
        toast.error('上传失败');
      }
    } catch (err: any) {
      toast.error(`上传失败: ${err?.message || err}`);
    }
  };

  const handleExecuteCases = async () => {
    const xlsxPath = caseUploadedPath || caseExcelPath;
    if (!xlsxPath) { toast.error('请先生成或上传用例 Excel'); return; }
    setLoading(true); setResult(null); setProgress(null);
    try {
      const res = await browserTestApi.executeCases(xlsxPath, { auto_approve: autoApprove });
      if ((res as any).ok) {
        toast.success('用例执行已启动');
        pollingRef.current = setInterval(async () => {
          try {
            const s = await browserTestApi.caseExecutionStatus() as any;
            if (s.total > 0) {
              setProgress({
                total_pages: 0, total_actions: s.total,
                passed: s.passed || 0, failed: s.failed || 0, skipped: 0, duration_ms: 0,
              });
            }
            if (!s.running) {
              stopPolling();
              if (s.error) {
                setResult({ status: 'failed', output: s.error });
              } else {
                const lines: string[] = [];
                lines.push(`用例执行完成: ✅${s.passed || 0} ❌${s.failed || 0} / ${s.total || 0}`);
                if (s.result_path) {
                  lines.push(`结果文件: ${s.result_path}`);
                  lines.push(`下载: ${window.location.origin}/api/core/browser/test/download?path=${encodeURIComponent(s.result_path)}`);
                }
                if (s.video_path) {
                  lines.push(`录屏: ${s.video_path}`);
                  lines.push(`下载: ${window.location.origin}/api/core/browser/test/download?path=${encodeURIComponent(s.video_path)}`);
                }
                setResult({ status: 'completed', output: lines.join('\n') });
              }
              setLoading(false);
            } else if (s.error) {
              // Partial error during execution
              setResult({ status: 'failed', output: s.error });
              setLoading(false);
            }
          } catch { /* silent */ }
        }, 2000);
      } else {
        toast.error('执行启动失败');
      }
    } catch (e: any) { toast.error(`执行失败: ${e?.message || e}`); setLoading(false); }
  };

  return (
    <Modal
      open={open}
      onClose={() => { stopPolling(); onClose(); setInput(''); }}
      title={`执行 Agent: ${agent?.name || ''}`}
      width={980}
      footer={
        isSiteTester ? (
          <>
            <Button variant="danger" onClick={handleStop} loading={stopping} disabled={!loading && !caseGenLoading} title={loading || caseGenLoading ? '停止当前操作' : '暂无执行中的任务'}>
              ⏹ 停止
            </Button>
            <div style={{ flex: 1 }} />
            <Button variant="secondary" onClick={handleGenerateCases} loading={caseGenLoading} disabled={loading}>
              📋 测试用例生成
            </Button>
            <Button variant="primary" onClick={handleExecuteCases} loading={loading} disabled={caseGenLoading}>
              🚀 开始测试（根据测试用例）
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={() => { stopPolling(); onClose(); setInput(''); setResult(null); }} disabled={loading}>关闭</Button>
            <Button variant="primary" onClick={handleExecute} loading={loading}>执行</Button>
          </>
        )
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="mb-3">
            <div className="text-sm font-medium text-gray-300 mb-2">Toolset（运行时工具集）</div>
            <select value={toolset} onChange={(e) => setToolset(e.target.value)}
              className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
              disabled={loading}>
              <option value="safe_readonly">safe_readonly（只读）</option>
              <option value="mcp_readonly">mcp_readonly（MCP 工具）</option>
              <option value="workspace_default">workspace_default（默认）</option>
              <option value="browser">browser（浏览器/HTTP）</option>
              <option value="full">full（全量/高风险）</option>
            </select>
            <div className="text-xs text-gray-500 mt-1">
              提示：toolset 在服务端强制生效；不在白名单内的工具调用会被 sys_tool_call 拦截并记录到诊断。
            </div>
          </div>

          {isRagAgent && domains.length > 0 && (
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-300 mb-2">知识库</label>
              <select value={selectedDomain} onChange={(e) => setSelectedDomain(e.target.value)}
                className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100">
                <option value="">选择知识库...</option>
                {domains.map(d => (
                  <option key={d.id} value={d.collection_id || d.id}>{d.name} ({d.id})</option>
                ))}
              </select>
            </div>
          )}

          <Textarea label="输入（JSON 或文本）" rows={14} value={input}
                onChange={(e: any) => setInput(e.target.value)} placeholder="可直接输入文本；或输入 JSON（推荐）" />
              <div className="text-xs text-gray-500 mt-2">
                提示：如果输入不是合法 JSON，会自动封装为 {'{ "message": "..." }'} 传给 Agent。
              </div>
              {/* ── Intent analysis ── */}
              <div className="flex items-center gap-2 mt-2">
                <Button variant="secondary" size="sm" onClick={handleAnalyzeIntent} loading={routingLoading} disabled={loading || !input.trim()}>
                  🔍 分析意图
                </Button>
              </div>
              {routingResult && (
                (() => {
                  const isMatch = routingResult.primary_route?.target && agent?.name &&
                    routingResult.primary_route.target === agent.name;
                  const hasEntities = Object.keys(routingResult.entities).length > 0;
                  const incrementalSkills = routingResult.suggested_skill_ids || [];
                  const incrementalTools = routingResult.suggested_tool_ids || [];
                  const hasSuggestions = incrementalSkills.length > 0 || incrementalTools.length > 0;

                  return (
                <div className="mt-2 p-3 rounded-lg border border-dark-border bg-dark-card">
                  {/* ── Line 1: Intent + confidence ── */}
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs text-gray-300">🔍</span>
                    <span className="text-xs text-gray-200 font-medium">
                      {routingResult.intent === 'chitchat' ? '闲聊' :
                       routingResult.intent === 'order_query' ? '订单查询' :
                       routingResult.intent === 'refund_request' ? '退款申请' :
                       routingResult.intent === 'code_review' ? '代码审查' :
                       routingResult.intent === 'code_generation' ? '代码生成' :
                       routingResult.intent === 'architecture_design' ? '架构设计' :
                       routingResult.intent === 'security_audit' ? '安全审查' :
                       routingResult.intent.replace(/_/g, ' ')}
                    </span>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      routingResult.confidence >= 0.8 ? 'bg-green-900/40 text-green-300' :
                      routingResult.confidence >= 0.5 ? 'bg-blue-900/40 text-blue-300' :
                      'bg-orange-900/40 text-orange-300'
                    }`}>
                      {Math.round(routingResult.confidence * 100)}%
                    </span>
                  </div>

                  {/* ── Line 2: Agent match ── */}
                  {routingResult.primary_route?.target && (
                    <div className="text-xs mb-2">
                      {isMatch ? (
                        <span className="text-green-400">✅ 当前 Agent 适合此任务</span>
                      ) : (
                        <span className="text-orange-400">
                          ⚠️ 建议切换到: <b>{routingResult.primary_route.target}</b>
                        </span>
                      )}
                    </div>
                  )}

                  {/* ── Line 3: Entities ── */}
                  {hasEntities && (
                    <div className="flex flex-wrap gap-1.5 mb-2">
                      {Object.entries(routingResult.entities).map(([k, v]) => (
                        <span key={k} className="text-xs px-1.5 py-0.5 rounded bg-dark-bg border border-dark-border text-gray-400">
                          {k}: <span className="text-gray-200">{String(v)}</span>
                        </span>
                      ))}
                    </div>
                  )}

                  {/* ── Line 4: Incremental suggestions ── */}
                  {hasSuggestions && (
                    <div className="text-xs text-gray-500 mb-2">
                      {incrementalSkills.length > 0 && (
                        <span>💡 建议绑定: <span className="text-blue-300">{incrementalSkills.slice(0, 4).join(', ')}</span></span>
                      )}
                      {incrementalTools.length > 0 && (
                        <span className="ml-2">工具: <span className="text-blue-300">{incrementalTools.slice(0, 3).join(', ')}</span></span>
                      )}
                    </div>
                  )}

                  {/* ── Line 5: Next step hint ── */}
                  {routingResult.should_clarify ? (
                    <div className="text-xs text-orange-400">⚠️ 置信度较低，建议补充更多信息后再执行</div>
                  ) : (
                    <div className="text-xs text-gray-500">💡 {isMatch ? '可以直接执行，意图已自动注入 Agent 推理上下文' : '可切换到推荐 Agent 后执行'}</div>
                  )}
                </div>
                  );
                })()
              )}
              {isSiteTester && progress && (
                <div className="mt-3 p-3 rounded-lg border border-blue-900/40 bg-blue-950/20">
                  <div className="flex items-center gap-3 text-sm">
                    <span className="text-blue-300 font-medium">⏳ 测试进行中</span>
                    <span className="text-gray-400">|</span>
                    <span className="text-gray-300">{progress.total_pages} 页</span>
                    <span className="text-gray-300">{progress.total_actions} 步</span>
                    <span className="text-green-400">✅ {progress.passed}</span>
                    <span className="text-red-400">❌ {progress.failed}</span>
                    <span className="text-gray-500">⏭ {progress.skipped}</span>
                    <span className="text-gray-400">|</span>
                    <span className="text-gray-500">{(progress.duration_ms / 1000).toFixed(1)}s</span>
                  </div>
                </div>
              )}
              {result && !flowFullscreen && (
                <div className="mt-4 p-4 rounded-lg border border-dark-border bg-dark-bg">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-gray-100">执行结果（简版）</span>
                    <span className={`text-xs px-2 py-0.5 rounded ${result.status === 'completed' ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
                      {result.status}
                    </span>
                    {result.tokens && (
                      <span className="text-xs text-gray-400 ml-3">
                        Token: {result.tokens.total_tokens?.toLocaleString() || '-'}
                        <span className="text-gray-500 ml-1">
                          (Prompt {result.tokens.prompt_tokens?.toLocaleString() || '-'} + Output {result.tokens.completion_tokens?.toLocaleString() || '-'})
                        </span>
                      </span>
                    )}
                    {result.eval?.has_data && (
                      <span className={`text-xs px-2 py-0.5 rounded ml-3 ${
                        (result.eval.grade || '').startsWith('A') ? 'bg-green-900/40 text-green-300' :
                        (result.eval.grade || '').startsWith('B') ? 'bg-blue-900/40 text-blue-300' :
                        'bg-orange-900/40 text-orange-300'
                      }`}>
                        🏆 {result.eval.grade || '?'}级 {Math.round(result.eval.score || 0)}分 ({result.eval.total_tasks || 0}次)
                      </span>
                    )}
                    {(result.duration_ms != null || result.steps != null) && (
                      <span className="text-xs text-gray-500 ml-3">
                        {result.duration_ms != null ? `⏱ ${(result.duration_ms / 1000).toFixed(1)}s` : ''}
                        {result.duration_ms != null && result.steps != null ? ' · ' : ''}
                        {result.steps != null ? `${result.steps}步` : ''}
                      </span>
                    )}
                  </div>
                  {result.output !== undefined && result.output !== null && (
                    <pre className="text-xs text-gray-300 overflow-auto max-h-60 bg-dark-card border border-dark-border rounded-lg p-3">
                      {typeof result.output === 'string' ? result.output : JSON.stringify(result.output as object, null, 2)}
                    </pre>
                  )}
                  {result.execution_id && (
                    <div className="mt-3 flex items-center justify-between gap-2 flex-wrap">
                      <div className="text-xs text-gray-400 break-all">execution_id: {result.execution_id}</div>
                      <div className="flex gap-2">
                        <Button variant="secondary" size="sm" onClick={async () => { try { await navigator.clipboard.writeText(result.execution_id || ''); toast.success('已复制'); } catch { toast.error('复制失败'); } }}>复制ID</Button>
                        <Button variant="secondary" size="sm" onClick={() => { window.open(`/diagnostics/links?execution_id=${encodeURIComponent(result.execution_id || '')}`, '_blank', 'noopener,noreferrer'); }}>查看诊断详情</Button>
                      </div>
                    </div>
                  )}
                  {result.run_id && (
                    <div className="mt-3">
                      <Button variant="primary" onClick={() => setFlowFullscreen(true)}>▶ 查看执行流程（全屏）</Button>
                    </div>
                  )}
            </div>
          )}

          {isSiteTester && (
            <div>
              <div className="p-3 rounded-lg border border-dark-border bg-dark-card mb-3">
                <div className="text-sm font-medium text-gray-200 mb-2">📋 用例驱动测试</div>
                <div className="flex flex-col gap-2">
                  <div className="text-xs text-gray-400">① 点右下角「📋 测试用例生成」生成 Excel</div>
                  {caseExcelPath && (
                    <div className="text-xs text-gray-400">
                      已生成: <span className="text-green-400 font-mono text-[10px] break-all">{caseExcelPath}</span>
                      <Button variant="secondary" size="sm" onClick={handleDownloadExcel} style={{ marginLeft: 8 }}>⬇ 下载</Button>
                    </div>
                  )}
                  <div className="text-xs text-gray-500 mt-2">
                    ② 用 Excel 打开编辑后，选择文件上传：
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <input ref={fileInputRef} type="file" accept=".xlsx"
                      onChange={handleFileUpload}
                      style={{ display: 'none' }}
                    />
                    <Button variant="secondary" size="sm" onClick={() => fileInputRef.current?.click()}>选择文件</Button>
                    {caseUploadedPath && (
                      <span className="text-xs text-green-400 font-mono truncate" style={{ maxWidth: 300 }}>{caseUploadedPath.split('/').pop()}</span>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
                    <input type="checkbox" checked={autoApprove} onChange={e => setAutoApprove(e.target.checked)}
                      style={{ accentColor: '#1890ff' }} />
                    <label className="text-xs text-gray-400 cursor-pointer" onClick={() => setAutoApprove(!autoApprove)}>
                      自动批准所有 PENDING 用例（无需手动改 status 列）
                    </label>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">③ 点右下角「🚀 开始测试（根据测试用例）」执行</div>
                </div>
              </div>
              {result && (
                <div className="p-4 rounded-lg border border-dark-border bg-dark-bg">
                  <pre className="text-xs text-gray-300 overflow-auto max-h-60">
                    {typeof result.output === 'string' ? result.output : JSON.stringify(result.output as object, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="border border-dark-border rounded-lg bg-dark-card p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-medium text-gray-200">使用说明 / 示例</div>
            <div className="text-xs text-gray-500">{helpLoading ? '加载中...' : ''}</div>
          </div>
          {helpMarkdown ? (
            <div className="text-xs text-gray-300 whitespace-pre-wrap leading-relaxed mb-3">{helpMarkdown}</div>
          ) : (
            <div className="text-xs text-gray-500 mb-3">暂无说明。</div>
          )}
          {examples.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs font-medium text-gray-300">一键填入示例</div>
              <div className="flex flex-col gap-2">
                {examples.map((ex, idx) => (
                  <div key={idx} className="flex flex-col gap-1">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-xs text-gray-300 font-medium">{ex.title}</div>
                      <div className="flex gap-2">
                        <Button variant="secondary" size="sm" onClick={() => setInput(ex.content)} disabled={loading}>填入</Button>
                        <Button variant="secondary" size="sm" onClick={async () => { try { await navigator.clipboard.writeText(ex.content); toast.success('已复制'); } catch { toast.error('复制失败'); } }} disabled={loading}>复制</Button>
                      </div>
                    </div>
                    <div className="text-xs text-gray-500 truncate max-w-full" style={{ fontFamily: 'monospace' }}>{ex.content.length > 80 ? ex.content.slice(0, 80) + '…' : ex.content}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── 全屏执行流程弹窗 ── */}
      {flowFullscreen && result && result.run_id && (
        <div className="fixed inset-0 z-[60] bg-dark-bg flex flex-col">
          <div className="h-10 flex items-center justify-between px-4 border-b border-dark-border bg-dark-card flex-shrink-0">
            <span className="text-sm font-medium text-gray-200">
              ▶ ReAct 执行流程 · {agent?.name || 'Agent'}
            </span>
            <div className="flex items-center gap-2">
              <span className={`text-xs px-2 py-0.5 rounded ${result.status === 'completed' ? 'bg-green-900/50 text-green-300' : result.status === 'failed' ? 'bg-red-900/50 text-red-300' : 'bg-blue-900/50 text-blue-300'}`}>
                {result.status}
              </span>
              <Button variant="secondary" onClick={() => setFlowFullscreen(false)}>✕ 关闭</Button>
            </div>
          </div>
          <ExecutionViewer
            runId={result.run_id}
            live={true}
            title=""
            height={window.innerHeight - 40}
            onNodeClick={(node: any) => setSelectedFlowNode(node)}
          />
          {selectedFlowNode && (
            <div className="fixed bottom-0 left-0 right-0 z-[70] border-t border-dark-border bg-dark-card p-4 max-h-72 overflow-y-auto shadow-2xl">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-semibold" style={{ color: selectedFlowNode.color || '#e5e7eb' }}>
                  {selectedFlowNode.icon} {selectedFlowNode.name}
                </span>
                <button onClick={() => setSelectedFlowNode(null)} className="text-gray-500 hover:text-gray-300 text-lg">✕</button>
              </div>
              <div className="flex gap-4 text-xs mb-3">
                <span className="text-gray-400">类型: {selectedFlowNode.type}</span>
                <span className="text-gray-400">状态: {selectedFlowNode.status}</span>
                {selectedFlowNode.duration ? <span className="text-gray-400">耗时: {selectedFlowNode.duration}ms</span> : null}
              </div>
              <StructuredDetail node={selectedFlowNode} />
            </div>
          )}
        </div>
      )}
    </Modal>
  );
};

export default ExecuteAgentModal;
