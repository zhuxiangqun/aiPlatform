import React, { useCallback, useEffect, useRef, useState } from 'react';
import { workspaceAgentApi } from '../../services';
import type { Agent } from '../../services';
import { Button, Modal, Textarea, toast } from '../ui';
import { toastGateError } from '../ui';
import { TraceFlowGraph } from './TraceFlowGraph';
import ExecutionViewer from '../ExecutionViewer/ExecutionViewer';
import { browserTestApi } from '../../services/browserTestApi';

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
  const [result, setResult] = useState<{ status: string; execution_id?: string; output?: unknown; error?: any; error_message?: string; error_detail?: any; run_id?: string; tokens?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } } | null>(null);
  const [toolset, setToolset] = useState<string>('workspace_default');
  const [stopping, setStopping] = useState(false);
  const [progress, setProgress] = useState<{ total_pages: number; total_actions: number; passed: number; failed: number; skipped: number; duration_ms: number } | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [caseGenLoading, setCaseGenLoading] = useState(false);
  const [caseExcelPath, setCaseExcelPath] = useState('');
  const [caseUploadedPath, setCaseUploadedPath] = useState('');
  const [autoApprove, setAutoApprove] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isSiteTester = agent?.skills?.includes('site_tester') || agent?.name === 'site_tester_agent' || agent?.name === '全站自动化测试' || agent?.display_name === '全站自动化测试' || false;

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
      setHelpLoading(true);
      try {
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
      const result = await workspaceAgentApi.execute(agent.id, { input: parsedInput, options: { ...((parsedInput.options || {}) as Record<string, unknown>), toolset }, config: (parsedInput.config || {}) as Record<string, unknown> });
      const status = String((result as any)?.status || 'ok');
      setResult({ status, execution_id: String((result as any)?.execution_id || ''), run_id: String((result as any)?.run_id || (result as any)?.execution_id || ''), output: (result as any)?.output, error: (result as any)?.error, tokens: (result as any)?.tokens });
      if (status === 'completed') toast.success('执行成功'); else toast.success(`状态: ${status}`);
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
              <option value="workspace_default">workspace_default（默认）</option>
              <option value="browser">browser（浏览器/HTTP）</option>
              <option value="full">full（全量/高风险）</option>
            </select>
            <div className="text-xs text-gray-500 mt-1">
              提示：toolset 在服务端强制生效；不在白名单内的工具调用会被 sys_tool_call 拦截并记录到诊断。
            </div>
          </div>

          <Textarea label="输入（JSON 或文本）" rows={14} value={input}
                onChange={(e: any) => setInput(e.target.value)} placeholder="可直接输入文本；或输入 JSON（推荐）" />
              <div className="text-xs text-gray-500 mt-2">
                提示：如果输入不是合法 JSON，会自动封装为 {'{ "message": "..." }'} 传给 Agent。
              </div>
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
              {result && (
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
                      <ExecutionViewer runId={result.run_id} live={true} title="ReAct 执行流程" height={400} />
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
                  <div key={idx} className="flex items-center justify-between gap-2">
                    <div className="text-xs text-gray-300 truncate">{ex.title}</div>
                    <div className="flex gap-2">
                      <Button variant="secondary" size="sm" onClick={() => setInput(ex.content)} disabled={loading}>填入</Button>
                      <Button variant="secondary" size="sm" onClick={async () => { try { await navigator.clipboard.writeText(ex.content); toast.success('已复制'); } catch { toast.error('复制失败'); } }} disabled={loading}>复制</Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
};

export default ExecuteAgentModal;
