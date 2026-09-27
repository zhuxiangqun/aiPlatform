import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { workspaceAgentApi, kbApi, apiClient } from '../services';
import type { Agent } from '../services';
import { Button, Modal, Textarea, toast } from './ui';
import { toastGateError } from './ui';
import ExecutionViewer from './ExecutionViewer/ExecutionViewer';
import { browserTestApi } from '../services/browserTestApi';
import GrillPanel from './grilling/GrillPanel';
import { buildAgentTaskExamples, buildExamplesFromSchema, isGenericExampleSet } from '../utils/executionSamples';

/** Parse the first top-level JSON object from a string (ignore trailing junk). */
function parseFirstJsonObject(s: string): Record<string, unknown> | null {
  const start = s.indexOf('{');
  if (start < 0) return null;
  const slice = s.slice(start);
  let depth = 0;
  let inStr = false;
  let esc = false;
  for (let i = 0; i < slice.length; i++) {
    const c = slice[i];
    if (inStr) {
      if (esc) { esc = false; continue; }
      if (c === '\\') { esc = true; continue; }
      if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') { inStr = true; continue; }
    if (c === '{') depth += 1;
    else if (c === '}') {
      depth -= 1;
      if (depth === 0) {
        try {
          const d = JSON.parse(slice.slice(0, i + 1));
          return d && typeof d === 'object' && !Array.isArray(d) ? (d as Record<string, unknown>) : null;
        } catch {
          return null;
        }
      }
    }
  }
  return null;
}

/** Unwrap agent output envelopes to plain readable text.
 *  Handles nested {text|output}, {"type":"done","answer"}, and JSON-string forms
 *  even when observation trails are concatenated after the JSON.
 */
function unwrapOutput(raw: unknown): string | unknown {
  let cur: unknown = raw;
  for (let depth = 0; depth < 8; depth++) {
    if (cur == null) return cur;

    if (typeof cur === 'object') {
      const o = cur as Record<string, unknown>;
      const typ = String(o.type || '').toLowerCase();
      if (typeof o.answer === 'string' && (typ === 'done' || typ === 'final' || typ === 'response' || typ === '')) {
        cur = o.answer;
        continue;
      }
      if (typeof o.response === 'string' && (typ === 'chitchat' || typ === 'done' || typ === '')) {
        cur = o.response;
        continue;
      }
      if (typeof o.text === 'string') {
        cur = o.text;
        continue;
      }
      if (o.text && typeof o.text === 'object') {
        cur = o.text;
        continue;
      }
      if (typeof o.output === 'string') {
        cur = o.output;
        continue;
      }
      if (o.output && typeof o.output === 'object') {
        cur = o.output;
        continue;
      }
      return cur;
    }

    if (typeof cur === 'string') {
      const s = cur.trim();
      if (!s) return s;
      // Fast path: whole string is JSON
      if (s.startsWith('{')) {
        try {
          const d = JSON.parse(s);
          if (d && typeof d === 'object') { cur = d; continue; }
        } catch { /* fall through to prefix parse */ }
        const d = parseFirstJsonObject(s);
        if (d) { cur = d; continue; }
      }
      // Embedded JSON envelope somewhere in the text
      if (s.includes('"type"') && s.includes('"answer"')) {
        const d = parseFirstJsonObject(s);
        if (d && typeof d.answer === 'string') { cur = d; continue; }
      }
      return s;
    }

    return cur;
  }
  return cur;
}

function outputAsText(raw: unknown): string {
  const u = unwrapOutput(raw);
  if (typeof u === 'string') return u;
  if (u == null) return '';
  try { return JSON.stringify(u, null, 2); } catch { return String(u); }
}

/** Heuristic: agent paused for user confirmation (template / path / clarify). */
function detectAwaitingUser(text: string): { awaiting: boolean; summary: string } {
  const t = text || '';
  const hits = [
    /没有可用模版/,
    /需要你确认/,
    /需要你确认模版/,
    /是否使用默认模版/,
    /用默认模版吗/,
    /请确认模版/,
    /请二选一/,
    /请提供模版/,
    /上传模版/,
    /阻塞项/,
    /等待用户/,
    /暂停生成/,
    /请回复上述/,
    /模版来源/,
  ].filter((re) => re.test(t));
  if (hits.length === 0) return { awaiting: false, summary: '' };
  // Prefer a short excerpt around the first strong marker
  const m = t.match(/#{0,3}\s*[^\n]*(?:需要你确认模版|需要你确认|是否使用默认模版|没有可用模版|阻塞项|暂停生成)[^\n]*/);
  const summary = (m?.[0] || 'Agent 已暂停，正在等待你确认模版（可用默认或指定路径）').replace(/^#+\s*/, '').slice(0, 140);
  return { awaiting: true, summary };
}

type RunVerdictTone = 'green' | 'red' | 'amber' | 'blue' | 'gray';
type RunVerdict = { kind: string; label: string; hint: string; tone: RunVerdictTone; ok: boolean | null };

/** Single place for “这次执行是否正常” — used by badge / banner / toast. */
function deriveRunVerdict(opts: {
  status?: string | null;
  error?: unknown;
  outputText?: string;
  awaiting?: boolean;
  awaitSummary?: string;
}): RunVerdict {
  const status = String(opts.status || '').toLowerCase();
  const errRaw = opts.error;
  const errStr =
    errRaw == null || errRaw === ''
      ? ''
      : String(
          typeof errRaw === 'string'
            ? errRaw
            : (errRaw as any)?.message || (errRaw as any)?.detail || JSON.stringify(errRaw),
        ).slice(0, 220);

  if (!status || status === 'running' || status === 'accepted') {
    return { kind: 'running', label: '执行中', hint: '流程进行中，节点跑完后再看最终状态。', tone: 'blue', ok: null };
  }
  if (status === 'timeout') {
    return {
      kind: 'timeout',
      label: '超时',
      hint: errStr || '等待超时了。可稍后打开「查看诊断详情」确认是否已在后台结束。',
      tone: 'red',
      ok: false,
    };
  }
  if (status === 'failed' || status === 'error' || status === 'cancelled' || status === 'canceled') {
    return {
      kind: 'failed',
      label: '未成功',
      hint: errStr || '这次没有跑完。可先看错误信息，再打开诊断详情核对。',
      tone: 'red',
      ok: false,
    };
  }
  if (opts.awaiting) {
    return {
      kind: 'awaiting',
      label: '需要你确认',
      hint: opts.awaitSummary || 'Agent 暂停了，补一句确认后再继续；这时还不算最终成功。',
      tone: 'amber',
      ok: null,
    };
  }
  if (status === 'completed' || status === 'ok' || status === 'success') {
    if (errStr) {
      return { kind: 'partial', label: '已结束（有告警）', hint: errStr, tone: 'amber', ok: null };
    }
    if (!(opts.outputText || '').trim()) {
      return {
        kind: 'partial',
        label: '已结束（无输出）',
        hint: '状态是完成，但没有可读输出。不确定的话打开诊断详情看一眼。',
        tone: 'amber',
        ok: null,
      };
    }
    return {
      kind: 'success',
      label: '已正常结束',
      hint: '可以慢慢看下方输出和执行轨迹，确认产物是否符合预期。',
      tone: 'green',
      ok: true,
    };
  }
  if (errStr) {
    return { kind: 'failed', label: '未成功', hint: errStr, tone: 'red', ok: false };
  }
  return {
    kind: 'unknown',
    label: `状态 ${status || '未知'}`,
    hint: '暂时不好自动判断，打开诊断详情更稳妥。',
    tone: 'gray',
    ok: null,
  };
}

const VERDICT_TONE_CLASS: Record<RunVerdictTone, string> = {
  green: 'border-green-700/50 bg-green-950/35 text-green-100',
  red: 'border-red-700/50 bg-red-950/35 text-red-100',
  amber: 'border-amber-700/50 bg-amber-950/35 text-amber-100',
  blue: 'border-blue-700/50 bg-blue-950/35 text-blue-100',
  gray: 'border-gray-600/50 bg-gray-900/40 text-gray-200',
};

const VERDICT_BADGE_CLASS: Record<RunVerdictTone, string> = {
  green: 'bg-green-900/50 text-green-300',
  red: 'bg-red-900/50 text-red-300',
  amber: 'bg-amber-900/50 text-amber-200',
  blue: 'bg-blue-900/50 text-blue-300',
  gray: 'bg-gray-800 text-gray-300',
};

function RunVerdictBanner({ verdict }: { verdict: RunVerdict }) {
  return (
    <div className={`p-2.5 rounded-lg border text-sm transition-colors duration-500 ${VERDICT_TONE_CLASS[verdict.tone]}`}>
      <div className="font-medium text-gray-100/95">{verdict.label}</div>
      <div className="text-xs opacity-75 mt-1 leading-relaxed">{verdict.hint}</div>
    </div>
  );
}

/** Prefer the persistent banner; only toast when user must notice (fail / await). */
function notifyRunVerdict(v: RunVerdict, opts?: { preferBanner?: boolean; delayMs?: number }) {
  const fire = () => {
    if (opts?.preferBanner && v.ok === true) return;
    if (v.kind === 'awaiting') {
      toast.warning(v.label, v.hint);
      return;
    }
    if (v.ok === false) {
      toast.error(v.label, v.hint);
      return;
    }
    if (opts?.preferBanner) return;
    if (v.ok === true) {
      toast.success(v.label);
      return;
    }
    toast.warning(v.label, v.hint);
  };
  const delay = Math.max(0, opts?.delayMs ?? 0);
  if (delay > 0) {
    window.setTimeout(fire, delay);
    return;
  }
  fire();
}

/** Extract absolute .pptx paths from agent result text for one-click download. */
function extractPptxPaths(text: string): string[] {
  if (!text) return [];
  const re = /(?:\/(?:Users|home|var|tmp)[^\s`"')\]}>]+?\.pptx|~\/\.aiplat\/[^\s`"')\]}>]+?\.pptx)/g;
  const found = text.match(re) || [];
  const out: string[] = [];
  for (const raw of found) {
    const p = raw.replace(/[.,;:]+$/, '');
    if (!p.startsWith('/') && !p.startsWith('~')) continue;
    // Skip template files — user wants the generated deck
    if (/\/templates\//.test(p) || /default\.pptx$/i.test(p)) continue;
    if (!out.includes(p)) out.push(p);
  }
  // Prefer ~/.aiplat/output (and absolute equivalents)
  out.sort((a, b) => {
    const score = (p: string) => (/\/output\//.test(p) ? 0 : 1);
    return score(a) - score(b);
  });
  return out.slice(0, 5);
}

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
  const [llmGenerating, setLlmGenerating] = useState(false);
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
  const [showGrill, setShowGrill] = useState(false);
  const [confirmReply, setConfirmReply] = useState('');
  const [templateUploading, setTemplateUploading] = useState(false);
  const [availableTemplates, setAvailableTemplates] = useState<Array<{ filename: string; path: string; is_default?: boolean }>>([]);
  const [selectedTemplatePath, setSelectedTemplatePath] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const templateFileInputRef = useRef<HTMLInputElement>(null);
  // ── Routing state ──
  const [routingResult, setRoutingResult] = useState<{ intent: string; confidence: number; primary_route?: { kind: string; target: string; score: number }; suggested_skill_ids: string[]; suggested_tool_ids: string[]; entities: Record<string, unknown>; should_clarify: boolean } | null>(null);
  const [routingLoading, setRoutingLoading] = useState(false);

  // ── Knowledge base selector (for RAG agents) ──
  const [domains, setDomains] = useState<{ id: string; name: string; collection_id: string }[]>([]);
  const [selectedDomain, setSelectedDomain] = useState('');

  const isSiteTester = agent?.skills?.includes('site_tester') || agent?.name === 'site_tester_agent' || agent?.name === '全站自动化测试' || agent?.display_name === '全站自动化测试' || false;

  const isRagAgent = agent?.agent_type === 'materials_chat';

  const resultText = useMemo(() => outputAsText(result?.output), [result?.output]);
  const awaitInfo = useMemo(() => detectAwaitingUser(resultText), [resultText]);
  const pptxPaths = useMemo(() => extractPptxPaths(resultText), [resultText]);
  const displayVerdict = useMemo(
    () =>
      deriveRunVerdict({
        status: result?.status,
        error: result?.error || result?.error_message,
        outputText: resultText,
        awaiting: awaitInfo.awaiting,
        awaitSummary: awaitInfo.summary,
      }),
    [result?.status, result?.error, result?.error_message, resultText, awaitInfo.awaiting, awaitInfo.summary],
  );

  // When Agent pauses for template confirm, refresh template library for picker
  useEffect(() => {
    if (!awaitInfo.awaiting) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/core/workspace/templates');
        const data = await res.json().catch(() => ({}));
        const list = Array.isArray((data as any)?.templates) ? (data as any).templates : [];
        if (cancelled) return;
        setAvailableTemplates(list.map((t: any) => ({
          filename: String(t.filename || ''),
          path: String(t.path || ''),
          is_default: !!t.is_default,
        })).filter((t: any) => t.path));
        setSelectedTemplatePath((prev) => {
          if (prev && list.some((t: any) => t.path === prev)) return prev;
          const def = list.find((t: any) => t.is_default) || list[0];
          return def ? String(def.path) : '';
        });
      } catch {
        if (!cancelled) setAvailableTemplates([]);
      }
    })();
    return () => { cancelled = true; };
  }, [awaitInfo.awaiting, result?.run_id]);

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
      setHelpLoading(true);
      setInput('');
      setResult(null);
      try {
        const res = await workspaceAgentApi.getExecutionHelp(agent.id);
        setHelpMarkdown(String((res as any)?.help_markdown || ''));
        let exs = (((res as any)?.examples || []) as Array<{ title: string; content: string }>);
        const schema = ((res as any)?.input_schema as Record<string, unknown> | null) || null;
        const label = agent.display_name || agent.name || agent.id;
        const meta = (agent.metadata || {}) as Record<string, unknown>;
        const reqSkills = Array.isArray(meta.required_skills) ? (meta.required_skills as string[]) : [];
        const skillIds = [...new Set([...(agent.skills || []), ...reqSkills])];
        if (isGenericExampleSet(exs)) {
          if (schema && Object.keys(schema).length > 0) {
            const generated = buildExamplesFromSchema(schema, label);
            if (generated.length > 0) exs = generated;
          } else {
            exs = buildAgentTaskExamples({
              displayName: label,
              description: agent.description || String(meta.description || ''),
              skillIds,
              toolIds: agent.tools || [],
            });
          }
        }
        setExamples(exs);
        // Do NOT auto-fill — user clicks「填入」
      } catch {
        const label = agent.display_name || agent.name || agent.id;
        const meta = (agent.metadata || {}) as Record<string, unknown>;
        const reqSkills = Array.isArray(meta.required_skills) ? (meta.required_skills as string[]) : [];
        setHelpMarkdown('');
        setExamples(
          buildAgentTaskExamples({
            displayName: label,
            description: agent.description || String(meta.description || ''),
            skillIds: [...new Set([...(agent.skills || []), ...reqSkills])],
            toolIds: agent.tools || [],
          }),
        );
      } finally {
        setHelpLoading(false);
      }
    };
    load();
  }, [open, agent?.id]);

  const handleGenerateLlmExamples = async (persist: boolean) => {
    if (!agent) return;
    try {
      setLlmGenerating(true);
      const res = await workspaceAgentApi.generateExecutionExamples(agent.id, { persist });
      const exs = (res?.examples || []) as Array<{ title: string; content: string }>;
      if (!exs.length) {
        toast.error('未生成可用用例');
        return;
      }
      setExamples(exs);
      if (exs[0]?.content) setInput(exs[0].content);
      const src = res?.source === 'llm' ? 'LLM' : '启发式回退';
      if (persist && res?.persisted) {
        toast.success(`已生成 ${exs.length} 条（${src}）并写入 AGENT.md`);
      } else if (persist && !res?.persisted) {
        toast.warning(`已生成 ${exs.length} 条，但写入 AGENT.md 失败`);
      } else {
        toast.success(`已生成 ${exs.length} 条（${src}），已填入第一条`);
      }
      if (res?.warning) toast.warning(String(res.warning));
    } catch (e: any) {
      toastGateError(e, 'LLM 生成用例失败');
    } finally {
      setLlmGenerating(false);
    }
  };

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  /** Build continue message for an explicit template path. */
  const buildTemplateContinueMsg = useCallback((templatePath: string) => {
    const baseTask = (input.trim() && !input.includes('【用户确认'))
      ? input.trim()
      : '（沿用上轮任务：生成接待用 PPT）';
    return [
      '【用户确认·继续生成】',
      `1. 模版路径：${templatePath}`,
      '2. 保存目录：~/.aiplat/output/',
      `请立即调用技能 ppt_generation（template_path=${templatePath}，output_dir=~/.aiplat/output），回报绝对路径。禁止用 code 工具拼装 pptx，不要再询问模版。`,
      '',
      '—— 原任务 ——',
      baseTask,
    ].join('\n');
  }, [input]);

  /** Build the default-template continue message (方案 B confirmation). */
  const buildDefaultTemplateContinueMsg = useCallback(() => {
    const def = availableTemplates.find((t) => t.is_default)?.path
      || availableTemplates.find((t) => /default\.pptx$/i.test(t.filename))?.path
      || '~/.aiplat/templates/default.pptx';
    return buildTemplateContinueMsg(def);
  }, [availableTemplates, buildTemplateContinueMsg]);

  /** Re-execute agent with a confirmation / continue message; keep fullscreen for live flow. */
  const runContinueExecute = useCallback(async (msg: string) => {
    if (!agent || !msg.trim()) return;
    setInput(msg);
    setConfirmReply('');
    setLoading(true);
    setResult(null);
    stopPolling();
    try {
      const execPayload: any = {
        input: { message: msg },
        options: { toolset, stream: true },
        config: {},
      };
      const res = await workspaceAgentApi.execute(agent.id, execPayload);
      const status = String((res as any)?.status || 'ok');
      const runId = (res as any)?.run_id || (res as any)?.execution_id || '';
      setResult({
        status,
        execution_id: String((res as any)?.execution_id || ''),
        run_id: runId,
        output: unwrapOutput((res as any)?.output),
        error: (res as any)?.error,
        eval: (res as any)?.eval,
        duration_ms: (res as any)?.duration_ms,
      });
      if (status === 'running' && runId) {
        setFlowFullscreen(true);
        let polls = 0;
        let stopped = false;
        pollingRef.current = setInterval(async () => {
          if (stopped) return;
          polls++;
          try {
            const sData = await apiClient.get<{ status?: string; output?: unknown; error?: unknown; duration_ms?: number }>(
              `/core/executions/${encodeURIComponent(runId)}/status`
            );
            const newStatus = String(sData?.status || '');
            if (newStatus && newStatus !== 'running' && newStatus !== 'accepted') {
              stopped = true;
              stopPolling();
              const done = newStatus === 'completed' || newStatus === 'ok' || newStatus === 'success';
              const out = unwrapOutput(sData?.output);
              const text = outputAsText(out);
              const ai = detectAwaitingUser(text);
              setResult(prev => ({
                ...prev!,
                status: done ? 'completed' : newStatus,
                output: typeof out === 'string' ? out : (out ?? prev?.output),
                error: sData?.error || prev?.error,
                duration_ms: sData?.duration_ms ?? prev?.duration_ms,
              }));
              if (done && ai.awaiting) {
                // Keep fullscreen so user can confirm again without closing
                toast.warning('Agent 在等你确认', ai.summary);
              } else if (done) {
                toast.success('执行完成');
              }
            }
          } catch { /* keep polling */ }
          if (polls >= 150) { stopPolling(); toast.error('执行超时（300s）'); }
        }, 2000);
      } else if (status === 'completed') {
        const ai = detectAwaitingUser(outputAsText(unwrapOutput((res as any)?.output)));
        if (ai.awaiting) toast.warning('Agent 在等你确认', ai.summary);
        else toast.success('执行完成');
      }
    } catch (e: any) {
      setResult({ status: 'failed', error: String(e?.message || e) });
      toastGateError(e, '继续执行失败');
    } finally {
      setLoading(false);
    }
  }, [agent, toolset, stopPolling]);

  /** Continue with currently selected library template. */
  const continueWithSelectedTemplate = useCallback(() => {
    const path = selectedTemplatePath
      || availableTemplates.find((t) => t.is_default)?.path
      || '~/.aiplat/templates/default.pptx';
    runContinueExecute(buildTemplateContinueMsg(path));
  }, [selectedTemplatePath, availableTemplates, buildTemplateContinueMsg, runContinueExecute]);

  /** Upload .pptx/.potx into ~/.aiplat/templates then continue with that path. */
  const uploadTemplateAndContinue = useCallback(async (file: File) => {
    if (!agent || !file) return;
    const name = file.name || '';
    if (!/\.(pptx|potx)$/i.test(name)) {
      toast.error('请上传 .pptx 或 .potx 模版');
      return;
    }
    setTemplateUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch('/api/core/workspace/templates/upload', { method: 'POST', body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !(data as any)?.ok) {
        throw new Error(String((data as any)?.detail || (data as any)?.error || `upload failed (${res.status})`));
      }
      const path = String((data as any).path || '');
      const filename = String((data as any).filename || name);
      toast.success(`模版已上传: ${filename}`);
      await runContinueExecute(buildTemplateContinueMsg(path));
    } catch (e: any) {
      toast.error(`上传模版失败: ${e?.message || e}`);
    } finally {
      setTemplateUploading(false);
    }
  }, [agent, buildTemplateContinueMsg, runContinueExecute]);

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
      const out0 = unwrapOutput((result as any)?.output);
      setResult({ status, execution_id: String((result as any)?.execution_id || ''), run_id: runId, output: out0, error: (result as any)?.error, tokens: (result as any)?.tokens, eval: execEval, duration_ms: execDuration, steps: execSteps });
      // v2.9: auto-show GrillPanel when backend suggests clarification
      if ((result as any)?.metadata?.grill_suggested) {
        setShowGrill(true);
      }
      const await0 = detectAwaitingUser(outputAsText(out0));
      if (runId && (status === 'running' || status === 'accepted')) {
        setFlowFullscreen(true);
      } else if (runId && status === 'completed' && !await0.awaiting) {
        setFlowFullscreen(true);
      } else if (await0.awaiting) {
        // Show flow + confirm panel together (do not force-close fullscreen)
        if (runId) setFlowFullscreen(true);
        toast.warning('Agent 在等你确认', await0.summary);
      }
      // ── Stream mode: poll execution status until completion ──
      if (status === 'running' && runId) {
        let polls = 0;
        let stopped = false;
        const applyDone = (newStatus: string, sData: any) => {
          if (stopped) return;
          stopped = true;
          stopPolling();
          const done = newStatus === 'completed' || newStatus === 'ok' || newStatus === 'success';
          const out = unwrapOutput(sData?.output);
          const text = outputAsText(out);
          const awaitInfo = detectAwaitingUser(text);
          setResult(prev => ({
            ...prev!,
            status: done ? 'completed' : (newStatus || 'failed'),
            output: typeof out === 'string' ? out : (out ?? prev?.output),
            error: sData?.error || prev?.error,
            duration_ms: sData?.duration_ms ?? prev?.duration_ms,
          }));
          const v = deriveRunVerdict({
            status: done ? 'completed' : (newStatus || 'failed'),
            error: sData?.error,
            outputText: text,
            awaiting: awaitInfo.awaiting,
            awaitSummary: awaitInfo.summary,
          });
          notifyRunVerdict(v, { preferBanner: true, delayMs: v.ok === false || v.kind === 'awaiting' ? 600 : 0 });
        };
        pollingRef.current = setInterval(async () => {
          if (stopped) return;
          polls++;
          try {
            const sData = await apiClient.get<{ status?: string; output?: unknown; error?: unknown; duration_ms?: number }>(
              `/core/executions/${encodeURIComponent(runId)}/status`
            );
            const newStatus = String(sData?.status || '');
            if (newStatus && newStatus !== 'running' && newStatus !== 'accepted') {
              applyDone(newStatus, sData);
              return;
            }
          } catch {
            // Fallback: /core/runs/{id} also carries terminal status
            try {
              const rData = await apiClient.get<{ status?: string; output?: unknown; error?: unknown; duration_ms?: number }>(
                `/core/runs/${encodeURIComponent(runId)}`
              );
              const newStatus = String(rData?.status || '');
              if (newStatus && newStatus !== 'running' && newStatus !== 'accepted') {
                applyDone(newStatus, rData);
                return;
              }
            } catch { /* still running */ }
          }
          if (polls >= 150) { stopPolling(); toast.error('执行超时（300s）', 'Agent 可能仍在后台运行，查看诊断详情获取最新状态。'); }
        }, 2000);
      }
      if (status !== 'running' && status !== 'accepted') {
        const v = deriveRunVerdict({
          status,
          error: (result as any)?.error,
          outputText: outputAsText(out0),
          awaiting: await0.awaiting,
          awaitSummary: await0.summary,
        });
        // Soft: banner is primary; toast only for fail/await, and slightly delayed
        notifyRunVerdict(v, { preferBanner: !!runId, delayMs: 800 });
      }
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
    window.open(`/api/platform/apps/browser/test/download?path=${encodeURIComponent(caseExcelPath)}`, '_blank');
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
                  lines.push(`下载: ${window.location.origin}/api/platform/apps/browser/test/download?path=${encodeURIComponent(s.result_path)}`);
                }
                if (s.video_path) {
                  lines.push(`录屏: ${s.video_path}`);
                  lines.push(`下载: ${window.location.origin}/api/platform/apps/browser/test/download?path=${encodeURIComponent(s.video_path)}`);
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
    <>
    <input
      ref={templateFileInputRef}
      type="file"
      accept=".pptx,.potx,application/vnd.openxmlformats-officedocument.presentationml.presentation"
      style={{ display: 'none' }}
      onChange={async (e) => {
        const f = e.target.files?.[0];
        e.target.value = '';
        if (f) await uploadTemplateAndContinue(f);
      }}
    />
    <Modal
      open={open}
      onClose={() => { stopPolling(); onClose(); setInput(''); setRoutingResult(null); setConfirmReply(''); }}
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
            <Button variant="secondary" onClick={() => { stopPolling(); onClose(); setInput(''); setResult(null); setRoutingResult(null); }} disabled={loading}>关闭</Button>
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

          <Textarea
            label="输入（JSON 或文本）"
            rows={14}
            value={input}
            onChange={(e: any) => setInput(e.target.value)}
            placeholder='点右侧「填入」加载测试用例，或直接输入 JSON / 文本'
          />
              <div className="text-xs text-gray-500 mt-2">
                提示：如果输入不是合法 JSON，会自动封装为 {'{ "message": "..." }'} 传给 Agent。
              </div>
              {/* ── Advanced: intent routing preflight (optional, not required for execute) ── */}
              <details className="mt-3 rounded-lg border border-dark-border bg-dark-card/40 group">
                <summary className="cursor-pointer select-none px-3 py-2 text-xs text-gray-500 hover:text-gray-300 list-none flex items-center gap-1.5">
                  <span className="text-gray-600 group-open:rotate-90 transition-transform inline-block">▸</span>
                  高级 · 意图预检（可选）
                </summary>
                <div className="px-3 pb-3 border-t border-dark-border/60">
                  <p className="text-xs text-gray-500 mt-2 mb-2">
                    规则关键词预检当前输入是否更适合别的 Agent；不改变本次执行目标，日常可忽略。
                  </p>
                  <div className="flex items-center gap-2">
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
                    <div className="mt-2 p-3 rounded-lg border border-dark-border bg-dark-bg">
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

                      {hasEntities && (
                        <div className="flex flex-wrap gap-1.5 mb-2">
                          {Object.entries(routingResult.entities).map(([k, v]) => (
                            <span key={k} className="text-xs px-1.5 py-0.5 rounded bg-dark-card border border-dark-border text-gray-400">
                              {k}: <span className="text-gray-200">{String(v)}</span>
                            </span>
                          ))}
                        </div>
                      )}

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

                      {routingResult.should_clarify ? (
                        <div className="space-y-2">
                          <div className="text-xs text-orange-400">⚠️ 置信度较低，建议澄清需求后再执行</div>
                          {!showGrill ? (
                            <button
                              onClick={() => setShowGrill(true)}
                              className="text-xs px-2 py-1 rounded bg-blue-900/30 border border-blue-700/50 text-blue-400 hover:bg-blue-900/50"
                            >
                              📋 开始需求澄清
                            </button>
                          ) : null}
                        </div>
                      ) : (
                        <div className="text-xs text-gray-500">💡 {isMatch ? '可以直接执行' : '可切换到推荐 Agent 后执行'}</div>
                      )}
                    </div>
                      );
                    })()
                  )}
                </div>
              </details>
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
                  <div className="mb-3">
                    <RunVerdictBanner verdict={displayVerdict} />
                  </div>
                  <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                    <span className="text-sm font-medium text-gray-100">执行结果</span>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs px-2 py-0.5 rounded ${VERDICT_BADGE_CLASS[displayVerdict.tone]}`} title={result.status}>
                        {displayVerdict.label}
                      </span>
                      <span className="text-[10px] text-gray-500 font-mono">{result.status}</span>
                    </div>
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
                  {awaitInfo.awaiting && (
                    <div className="mb-3 p-3 rounded-lg border border-amber-700/50 bg-amber-950/30 text-sm text-amber-100 space-y-2">
                      <div className="font-medium">⏸ Agent 已暂停，在等你回复</div>
                      <div className="text-xs text-amber-200/90">{awaitInfo.summary}</div>
                      <div className="text-xs text-amber-200/70">
                        模版需你确认一次（方案 B）。可从已有库选择、用默认模版，或上传新模版后继续。
                      </div>
                      {availableTemplates.length > 0 && (
                        <div className="flex flex-wrap items-center gap-2 pt-1">
                          <label className="text-xs text-amber-200/80">已有模版</label>
                          <select
                            className="text-xs bg-dark-bg border border-amber-800/40 rounded px-2 py-1 text-amber-50 max-w-[280px]"
                            value={selectedTemplatePath}
                            onChange={(e) => setSelectedTemplatePath(e.target.value)}
                          >
                            {availableTemplates.map((t) => (
                              <option key={t.path} value={t.path}>
                                {t.filename}{t.is_default ? '（默认）' : ''}
                              </option>
                            ))}
                          </select>
                          <Button
                            variant="primary"
                            size="sm"
                            disabled={loading || templateUploading || !selectedTemplatePath}
                            onClick={continueWithSelectedTemplate}
                          >
                            用此模版继续
                          </Button>
                        </div>
                      )}
                      <div className="flex flex-wrap gap-2 pt-1">
                        <Button
                          variant="primary"
                          size="sm"
                          disabled={loading || templateUploading}
                          onClick={() => runContinueExecute(buildDefaultTemplateContinueMsg())}
                        >
                          使用默认模版继续
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          disabled={loading || templateUploading}
                          onClick={() => templateFileInputRef.current?.click()}
                        >
                          {templateUploading ? '上传中…' : '上传模版并继续'}
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          disabled={loading}
                          onClick={() => {
                            const hint = '\n\n【补充】模版路径：~/.aiplat/templates/default.pptx\n保存目录：~/.aiplat/output/\n请用上述模版继续生成。';
                            setInput((prev) => (prev.trim() ? prev + hint : hint.trim()));
                            toast.success('已填入模版确认，请点「执行」');
                          }}
                        >
                          填入确认到输入框
                        </Button>
                      </div>
                    </div>
                  )}
                  {pptxPaths.length > 0 && (
                    <div className="mb-3 flex flex-wrap gap-2 items-center">
                      {pptxPaths.map((p) => (
                        <Button
                          key={p}
                          variant="primary"
                          size="sm"
                          onClick={() => {
                            window.open(
                              `/api/platform/apps/browser/test/download?path=${encodeURIComponent(p)}`,
                              '_blank',
                              'noopener,noreferrer',
                            );
                          }}
                        >
                          ⬇ 下载 {p.split('/').pop()}
                        </Button>
                      ))}
                      <span className="text-[10px] text-gray-500 font-mono break-all">{pptxPaths[0]}</span>
                    </div>
                  )}
                  {result.error && (
                    <pre className="mb-2 text-xs text-red-200/90 overflow-auto max-h-40 bg-red-950/20 border border-red-900/40 rounded-lg p-3 whitespace-pre-wrap break-words">
                      {String(typeof result.error === 'string' ? result.error : JSON.stringify(result.error, null, 2))}
                    </pre>
                  )}
                  {resultText ? (
                    <pre className="text-xs text-gray-300 overflow-auto max-h-80 bg-dark-card border border-dark-border rounded-lg p-3 whitespace-pre-wrap break-words">
                      {resultText}
                    </pre>
                  ) : result.output != null ? (
                    <pre className="text-xs text-gray-300 overflow-auto max-h-60 bg-dark-card border border-dark-border rounded-lg p-3">
                      {typeof result.output === 'string' ? result.output : JSON.stringify(result.output as object, null, 2)}
                    </pre>
                  ) : null}
                  {result.execution_id && (
                    <div className="mt-3 flex items-center justify-between gap-2 flex-wrap">
                      <div className="text-xs text-gray-400 break-all">execution_id: {result.execution_id}</div>
                      <div className="flex gap-2">
                        <Button variant="secondary" size="sm" onClick={async () => { try { await navigator.clipboard.writeText(result.execution_id || ''); toast.success('已复制'); } catch { toast.error('复制失败'); } }}>复制ID</Button>
                        <Button variant="secondary" size="sm" onClick={() => { window.open(`/diagnostics/links?execution_id=${encodeURIComponent(result.execution_id || '')}&include_spans=true`, '_blank', 'noopener,noreferrer'); }}>查看诊断详情</Button>
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

        {/* v2.9: Grilling clarification panel — replaces low-confidence warning */}
        {showGrill && agent && (
          <GrillPanel
            mode="inline"
            entryPoint="agent_chat"
            domainId=""
            title={`需求澄清 — ${agent.name}`}
            onComplete={(output) => {
              const flat = output.answers as Record<string, string>;
              const clarified = Object.keys(flat).length > 0
                ? `\n\n[已澄清]\n${Object.entries(flat).map(([k, v]) => `- ${k}: ${v}`).join('\n')}`
                : '';
              setInput((prev) => prev + '\n' + clarified);
              setShowGrill(false);
              toast.success('需求已澄清，可以执行了');
            }}
            onClose={() => setShowGrill(false)}
          />
        )}

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
              <div className="text-xs font-medium text-gray-300">测试用例 — 点「填入」写入左侧输入框</div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  loading={llmGenerating}
                  disabled={loading || llmGenerating}
                  onClick={() => handleGenerateLlmExamples(false)}
                  title="用 LLM 生成更贴合本 Agent 职责的冒烟用例（可选）"
                >
                  ✨ LLM 生成
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  loading={llmGenerating}
                  disabled={loading || llmGenerating}
                  onClick={() => handleGenerateLlmExamples(true)}
                  title="生成后写入 AGENT.md 的 execution_examples，下次打开优先使用"
                >
                  生成并保存
                </Button>
              </div>
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
          {examples.length === 0 && !helpLoading && (
            <div className="space-y-2">
              <div className="text-xs text-gray-500">暂无测试用例。</div>
              <Button
                variant="secondary"
                size="sm"
                loading={llmGenerating}
                disabled={loading || llmGenerating}
                onClick={() => handleGenerateLlmExamples(false)}
              >
                ✨ LLM 生成用例
              </Button>
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
              <span className={`text-xs px-2 py-0.5 rounded ${VERDICT_BADGE_CLASS[displayVerdict.tone]}`} title={result.status}>
                {displayVerdict.label}
              </span>
              <span className="text-[10px] text-gray-500 font-mono hidden sm:inline">{result.status}</span>
              <Button variant="secondary" onClick={() => setFlowFullscreen(false)}>✕ 关闭</Button>
            </div>
          </div>
          <div className="flex-1 min-h-0 flex flex-col p-2">
            <div className="flex-1 min-h-0">
              <ExecutionViewer
                runId={result.run_id}
                live={true}
                running={result.status === 'running' || displayVerdict.kind === 'running'}
                title=""
                height={Math.max(240, window.innerHeight - (result.output || result.error || awaitInfo.awaiting || displayVerdict.ok !== null ? 320 : 100))}
                onLiveStatusChange={async (liveSt) => {
                if (liveSt !== 'done' || result.status === 'completed' || result.status === 'failed' || result.status === 'timeout') return;
                try {
                  const sData = await apiClient.get<{ status?: string; output?: unknown; error?: unknown; duration_ms?: number }>(
                    `/core/executions/${encodeURIComponent(result.run_id!)}/status`
                  );
                  const newStatus = String(sData?.status || 'completed');
                  const done = newStatus === 'completed' || newStatus === 'ok' || newStatus === 'success';
                  setResult(prev => prev ? {
                    ...prev,
                    status: done ? 'completed' : newStatus,
                    output: unwrapOutput(sData?.output) ?? prev.output,
                    error: sData?.error || prev.error,
                    duration_ms: sData?.duration_ms ?? prev.duration_ms,
                  } : prev);
                  stopPolling();
                } catch {
                  // Do not invent success — leave status as-is
                  stopPolling();
                  toast.warning('状态待确认', '实时事件已结束，但未能拉取最终状态。可打开诊断详情核对。');
                }
              }}
              />
            </div>
            {(resultText || result.error || awaitInfo.awaiting || displayVerdict.ok === false || displayVerdict.ok === true || displayVerdict.kind === 'partial') && (
              <div className="flex-shrink-0 border-t border-dark-border bg-dark-card p-3 max-h-[42vh] overflow-y-auto mt-2 rounded-lg space-y-2">
                <RunVerdictBanner verdict={displayVerdict} />
                {awaitInfo.awaiting && (
                  <div className="p-3 rounded-lg border border-amber-700/50 bg-amber-950/30 text-sm text-amber-100 space-y-2">
                    <div className="font-medium">⏸ Agent 已暂停，在等你回复</div>
                    <div className="text-xs text-amber-200/90">{awaitInfo.summary}</div>
                    <div className="text-xs text-amber-200/70">
                      可从已有库选择模版、一键用默认，或在下方输入确认后发送。
                    </div>
                    {availableTemplates.length > 0 && (
                      <div className="flex flex-wrap items-center gap-2 pt-1">
                        <label className="text-xs text-amber-200/80">已有模版</label>
                        <select
                          className="text-xs bg-dark-bg border border-amber-800/40 rounded px-2 py-1 text-amber-50 max-w-[280px]"
                          value={selectedTemplatePath}
                          onChange={(e) => setSelectedTemplatePath(e.target.value)}
                        >
                          {availableTemplates.map((t) => (
                            <option key={t.path} value={t.path}>
                              {t.filename}{t.is_default ? '（默认）' : ''}
                            </option>
                          ))}
                        </select>
                        <Button
                          variant="primary"
                          size="sm"
                          disabled={loading || templateUploading || !selectedTemplatePath}
                          onClick={continueWithSelectedTemplate}
                        >
                          用此模版继续
                        </Button>
                      </div>
                    )}
                    <div className="flex flex-wrap gap-2 pt-1">
                      <Button
                        variant="primary"
                        size="sm"
                        disabled={loading || templateUploading}
                        onClick={() => runContinueExecute(buildDefaultTemplateContinueMsg())}
                      >
                        使用默认模版继续
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={loading || templateUploading}
                        onClick={() => templateFileInputRef.current?.click()}
                      >
                        {templateUploading ? '上传中…' : '上传模版并继续'}
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={loading}
                        onClick={() => {
                          setFlowFullscreen(false);
                          const hint = '\n\n【补充】模版路径：~/.aiplat/templates/default.pptx\n保存目录：~/.aiplat/output/\n请用上述模版继续生成。';
                          setInput((prev) => (prev.trim() ? prev + hint : hint.trim()));
                          toast.success('已回到执行窗，请编辑后点「执行」');
                        }}
                      >
                        回到输入框编辑
                      </Button>
                    </div>
                    <div className="pt-1 space-y-1.5">
                      <Textarea
                        value={confirmReply}
                        onChange={(e: any) => setConfirmReply(e.target.value)}
                        placeholder="例如：用默认模版；日期两个候选都写上；保存到 ~/.aiplat/output/"
                        rows={2}
                        className="text-xs bg-dark-bg border-amber-800/40 text-amber-50"
                      />
                      <Button
                        variant="primary"
                        size="sm"
                        disabled={loading || !confirmReply.trim()}
                        onClick={() => {
                          const base = (input.trim() && !input.includes('【用户确认'))
                            ? input.trim()
                            : '（沿用上轮任务）';
                          const msg = [
                            '【用户确认·继续生成】',
                            confirmReply.trim(),
                            '',
                            '—— 原任务 ——',
                            base,
                          ].join('\n');
                          runContinueExecute(msg);
                        }}
                      >
                        发送确认并继续
                      </Button>
                    </div>
                  </div>
                )}
                {result.error && (
                  <>
                    <div className="text-xs font-medium text-red-300">错误信息</div>
                    <pre className="text-xs text-red-200/90 whitespace-pre-wrap break-words bg-red-950/20 border border-red-900/40 rounded p-2">
                      {String(typeof result.error === 'string' ? result.error : JSON.stringify(result.error, null, 2))}
                    </pre>
                  </>
                )}
                {resultText && (
                  <>
                    <div className="text-xs font-medium text-gray-300">执行输出</div>
                    <pre className="text-xs text-gray-300 whitespace-pre-wrap break-words">
                      {resultText}
                    </pre>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </Modal>
    </>
  );
};

export default ExecuteAgentModal;
