import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { workspaceAgentApi, workspaceSkillApi, skillApi, kbApi, apiClient } from '../services';
import type { Agent } from '../services';
import { Button, Modal, Textarea, toast } from './ui';
import { toastGateError } from './ui';
import ExecutionViewer from './ExecutionViewer/ExecutionViewer';
import { browserTestApi } from '../services/browserTestApi';
import GrillPanel from './grilling/GrillPanel';
import { buildAgentTaskExamples, buildExampleRefineHint, buildExamplesFromSchema, isGenericExampleSet, sanitizeExecutionExamples } from '../utils/executionSamples';
import ExecutionQualityReviewPanel, {
  type ExecutionQualityReview,
} from './execution/ExecutionQualityReviewPanel';
import StructuredSkillOutput from './execution/StructuredSkillOutput';
import ExecuteOutputFullscreen from './execution/ExecuteOutputFullscreen';
import { extractCodingDeliveryText, hasFileDeliveryMarkers } from './execution/fileDelivery';
import { tryParseJsonOrPythonLiteral } from './execution/pythonLiteral';
import { executeProductAsText, unwrapExecuteProduct } from './execution/executeProduct';
import { appendFailConstraintOverlay, buildFailConstraintOverlay } from '../utils/failConstraintOverlay';

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
 *  Also unwraps Python-dict-repr envelopes with x-display-profile / ```json fences
 *  (LLM sometimes returns str(dict) instead of JSON).
 */
function unwrapOutput(raw: unknown): string | unknown {
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    const o = raw as Record<string, unknown>;
    const persistRoot =
      typeof o.persisted_root === 'string' ? o.persisted_root.trim()
      : typeof o.persist_root === 'string' ? o.persist_root.trim()
      : '';
    if (typeof o.text === 'string' && persistRoot && hasFileDeliveryMarkers(o.text)) {
      return {
        text: o.text,
        persisted_root: persistRoot,
        persisted_files: o.persisted_files,
      };
    }
  }
  const peeled = unwrapExecuteProduct(raw);
  if (peeled != null && typeof peeled === 'object') return peeled;
  if (typeof peeled === 'string' && peeled.trim() && peeled !== raw) return peeled;
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
      // Display-profile envelope: dig into the profile payload
      const profile = o['x-display-profile'];
      if (typeof profile === 'string' && profile.trim()) {
        cur = profile;
        continue;
      }
      if (profile && typeof profile === 'object') {
        cur = profile;
        continue;
      }
      // Skill envelopes often use ``code`` (not text) — prefer before JSON dump.
      if (typeof o.code === 'string' && o.code.trim()) {
        cur = o.code;
        continue;
      }
      if (typeof o.generated_code === 'string' && String(o.generated_code).trim()) {
        cur = o.generated_code;
        continue;
      }
      const persistRoot =
        typeof o.persisted_root === 'string' ? o.persisted_root.trim()
        : typeof o.persist_root === 'string' ? o.persist_root.trim()
        : '';
      if (typeof o.text === 'string') {
        if (persistRoot && hasFileDeliveryMarkers(o.text)) {
          return {
            text: o.text,
            persisted_root: persistRoot,
            persisted_files: o.persisted_files,
          };
        }
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
      // Multi-file coding body: never scrape a nested {"status":"ok"} from
      // FastAPI/health (or similar) out of ```python fences.
      if (hasFileDeliveryMarkers(s)) return s;
      // Fast path: whole string is JSON
      if (s.startsWith('{') || s.startsWith('[')) {
        try {
          const d = JSON.parse(s);
          if (d && typeof d === 'object') { cur = d; continue; }
        } catch { /* fall through */ }
      }
      // Markdown fenced JSON only — not ```python / ```ts (those contain dicts)
      const fence = /```(?:json)?[^\n]*\n\s*([{\[][\s\S]*?)```/i.exec(s);
      if (fence) {
        const inner = fence[1].trim();
        try {
          const d = JSON.parse(inner);
          if (d && typeof d === 'object') { cur = d; continue; }
        } catch { /* fall through */ }
        const dFence = parseFirstJsonObject(inner);
        if (dFence) { cur = dFence; continue; }
      }
      // Python dict/list repr → JSON (local LLMs often return str(dict))
      if ((s.startsWith('{') || s.startsWith('[')) && (s.includes("'") || s.includes('None') || s.includes('True'))) {
        const d = tryParseJsonOrPythonLiteral(s);
        if (d && typeof d === 'object') { cur = d; continue; }
      }
      // Python-dict-repr / mixed: locate first real JSON object with "key"
      if (s.includes('x-display-profile') || s.includes('"title"') || s.includes('"overview"')) {
        const jsonStart = s.search(/\{\s*"/);
        if (jsonStart >= 0) {
          const d = parseFirstJsonObject(s.slice(jsonStart));
          if (d) { cur = d; continue; }
        }
      }
      if (s.startsWith('{')) {
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
  return executeProductAsText(unwrapOutput(raw));
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
    /请确认以下信息/,
    /是否已经准备好/,
    /如果你已经准备好/,
    /我们可以开始下一步/,
    /请告诉我[，,]?\s*我们/,
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
  const m = t.match(/#{0,3}\s*[^\n]*(?:需要你确认模版|需要你确认|请确认以下信息|是否已经准备好|是否使用默认模版|没有可用模版|阻塞项|暂停生成)[^\n]*/);
  const summary = (m?.[0] || 'Agent 已暂停，正在等待你确认（这时还不算最终成功）').replace(/^#+\s*/, '').slice(0, 140);
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
  /** Jump to edit Agent → SOP / 高级. */
  onEditSop?: () => void;
}

const ExecuteAgentModal: React.FC<ExecuteAgentModalProps> = ({ open, agent, onClose, onEditSop }) => {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [helpLoading, setHelpLoading] = useState(false);
  const [helpMarkdown, setHelpMarkdown] = useState<string>('');
  const [examples, setExamples] = useState<Array<{ title: string; content: string }>>([]);
  const [helpInputSchema, setHelpInputSchema] = useState<Record<string, unknown> | null>(null);
  const [llmGenerating, setLlmGenerating] = useState(false);
  const [result, setResult] = useState<{ status: string; execution_id?: string; output?: unknown; error?: any; error_message?: string; error_detail?: any; run_id?: string; tokens?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number }; eval?: { score?: number; grade?: string; total_tasks?: number; has_data?: boolean }; duration_ms?: number; steps?: number } | null>(null);
  const [qualityReview, setQualityReview] = useState<ExecutionQualityReview | null>(null);
  const [qualityReviewLoading, setQualityReviewLoading] = useState(false);
  /** Dedupe auto-fetch of quality review per run (live-done vs poll race). */
  const qualityFetchedForRunRef = useRef<string>('');
  /** One retry when empty_output was locked before output upserted (fix→rerun). */
  const emptyOutputRetriedRef = useRef<string>('');
  /** Active execution id — ignore stale graph-done / quality fetch from previous 按失败点重跑. */
  const activeRunIdRef = useRef<string>('');
  /** Abort in-flight execute HTTP while waiting for run_id (Core wedge → spinner). */
  const executeAbortRef = useRef<AbortController | null>(null);
  const [postFixReady, setPostFixReady] = useState(false);
  /** Bound Skill output_schema — drives StructuredSkillOutput without field hardcoding. */
  const [resultSchema, setResultSchema] = useState<Record<string, unknown> | null>(null);
  const lastAgentInputRef = useRef<unknown>(null);
  const [toolset, setToolset] = useState<string>('workspace_default');
  const [stopping, setStopping] = useState(false);
  const [progress, setProgress] = useState<{ total_pages: number; total_actions: number; passed: number; failed: number; skipped: number; duration_ms: number } | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [caseGenLoading, setCaseGenLoading] = useState(false);
  const [caseExcelPath, setCaseExcelPath] = useState('');
  const [caseUploadedPath, setCaseUploadedPath] = useState('');
  const [autoApprove, setAutoApprove] = useState(true);
  const [flowFullscreen, setFlowFullscreen] = useState(false);
  const [outputFullscreen, setOutputFullscreen] = useState(false);
  /** Fullscreen bottom output strip — collapsed by default so the graph keeps the viewport. */
  const [fsOutputOpen, setFsOutputOpen] = useState(false);
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

  /** Prefer coding body (## FILE / code envelope) over dumping {code, language} JSON. */
  const resultText = useMemo(() => {
    const out = result?.output;
    const coding = extractCodingDeliveryText(
      typeof out === 'string' ? out : '',
      out,
    );
    if (coding.trim()) return coding;
    return outputAsText(out);
  }, [result?.output]);
  /** Prefer unwrapped object so StructuredSkillOutput can detect architecture/PRD shapes. */
  const resultRaw = useMemo(() => unwrapOutput(result?.output), [result?.output]);
  const awaitInfo = useMemo(() => detectAwaitingUser(resultText), [resultText]);
  const pptxPaths = useMemo(() => extractPptxPaths(resultText), [resultText]);
  const displayVerdict = useMemo(() => {
    const st = String(result?.status || '').toLowerCase();
    const rid = String(result?.run_id || result?.execution_id || '').trim();
    // Only coerce running→completed when the review belongs to THIS run.
    // Otherwise 按失败点重跑 keeps stale C-grade panel while the new graph is live.
    const reviewForActiveRun =
      Boolean(qualityReview) &&
      !!rid &&
      (qualityFetchedForRunRef.current === rid || activeRunIdRef.current === rid);
    const streamLagging =
      reviewForActiveRun &&
      (!st || st === 'running' || st === 'accepted' || st === 'unknown' || st === 'started');
    const base = deriveRunVerdict({
      status: streamLagging ? 'completed' : result?.status,
      error: result?.error || result?.error_message,
      outputText: resultText,
      awaiting: awaitInfo.awaiting,
      awaitSummary: awaitInfo.summary,
    });
    // Never paint「产物待改进」over an in-flight / other-run execution
    if (!reviewForActiveRun) return base;
    if (!qualityReview || (base.kind !== 'success' && base.kind !== 'partial')) return base;
    const v = String(qualityReview.verdict || '');
    if (v === 'fail') {
      return {
        ...base,
        kind: 'partial' as const,
        label: '已结束（产物待改进）',
        hint: qualityReview.headline || '流程跑通了，但产物未达可验收标准。请看下方问题点与改 SOP 指引。',
        tone: 'amber' as const,
        ok: null,
      };
    }
    if (v === 'warn') {
      return {
        ...base,
        kind: 'partial' as const,
        label: '已结束（有改进建议）',
        hint: qualityReview.headline || '产物基本可用，仍有建议项。',
        tone: 'amber' as const,
        ok: null,
      };
    }
    return base;
  }, [result?.status, result?.error, result?.error_message, result?.run_id, result?.execution_id, resultText, awaitInfo.awaiting, awaitInfo.summary, qualityReview]);

  const resolveAgentSkillTarget = (): string | null => {
    if (!agent) return null;
    const meta = ((agent as any)?.metadata || {}) as Record<string, unknown>;
    const reqSkills = Array.isArray(meta.required_skills) ? (meta.required_skills as string[]) : [];
    const ids = [...new Set([...(agent.skills || []), ...reqSkills].map(String).filter(Boolean))];
    // Prefer skill suggested by routing when present; else first bound skill (no business-name hardcode)
    const routed = routingResult?.suggested_skill_ids?.[0];
    if (routed && ids.includes(String(routed))) return String(routed);
    if (routingResult?.primary_route?.kind === 'skill' && routingResult.primary_route.target) {
      const t = String(routingResult.primary_route.target);
      if (ids.includes(t)) return t;
    }
    return ids[0] || null;
  };

  // Load output_schema from bound skills — extensibility via Skill contract, not UI field lists
  useEffect(() => {
    if (!open || !agent) {
      setResultSchema(null);
      return;
    }
    let cancelled = false;
    const meta = ((agent as any)?.metadata || {}) as Record<string, unknown>;
    const reqSkills = Array.isArray(meta.required_skills) ? (meta.required_skills as string[]) : [];
    const ids = [...new Set([...(agent.skills || []), ...reqSkills].map(String).filter(Boolean))];
    const prefer = resolveAgentSkillTarget();
    const ordered = prefer ? [prefer, ...ids.filter((id) => id !== prefer)] : ids;

    (async () => {
      for (const id of ordered.slice(0, 8)) {
        try {
          let detail: { output_schema?: Record<string, unknown> } | null = null;
          // Engine skills first (architecture_design etc.) — avoids console 404 on workspace GET
          try {
            detail = await skillApi.get(id);
          } catch {
            detail = await workspaceSkillApi.get(id);
          }
          const os = detail?.output_schema;
          if (os && typeof os === 'object' && Object.keys(os).length > 0) {
            if (!cancelled) setResultSchema(os);
            return;
          }
        } catch {
          /* try next skill */
        }
      }
      if (!cancelled) setResultSchema(null);
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- resolveAgentSkillTarget closes over routing; ids + routing are enough
  }, [open, agent?.id, agent?.skills, routingResult?.suggested_skill_ids, routingResult?.primary_route?.target]);

  const handleRerunSameCase = () => {
    // 「同一用例」必须以上次执行输入为准；并先停掉旧轮询，避免先看到 completed 空产物就复核。
    // 若质量复核判定铁律已在 SOP：注入失败点约束（不改 SKILL.md）。
    setPostFixReady(false);
    stopPolling();
    // Best-effort cancel any lingering prior run so fail-rerun does not queue behind a wedge.
    const prevRid = String(
      activeRunIdRef.current || result?.run_id || result?.execution_id || '',
    ).trim();
    if (prevRid && prevRid !== '__pending__') {
      void apiClient
        .post(
          `/core/executions/${encodeURIComponent(prevRid)}/cancel`,
          { reason: 'fail_constraint_rerun' },
          { timeoutMs: 6000 },
        )
        .catch(() => undefined);
    }
    // Invalidate in-flight callbacks from the previous run (graph-done / quality fetch).
    // Sentinel + clear run_id: avoid keeping finished previous canvas under 「执行中」.
    activeRunIdRef.current = '__pending__';
    // Always rebuild overlay from issues — never reuse a long/stale overlay that
    // stalls local LLMs or contains echo-bait examples (run-30e631 / run-2ebd).
    const overlay = buildFailConstraintOverlay(qualityReview?.issues);
    setQualityReview(null);
    qualityFetchedForRunRef.current = '';
    emptyOutputRetriedRef.current = '';
    setResult((prev) =>
      prev
        ? {
            ...prev,
            status: 'running',
            run_id: undefined,
            execution_id: undefined,
            error: undefined,
            error_message: undefined,
            output: undefined,
            eval: undefined,
            duration_ms: undefined,
          }
        : { status: 'running' },
    );
    setFlowFullscreen(true);
    const last = lastAgentInputRef.current;
    let override = '';
    if (last && typeof last === 'object' && last !== null) {
      const o = last as Record<string, unknown>;
      const m = o.message ?? o.user_requirement ?? o.query ?? o.text;
      if (typeof m === 'string' && m.trim()) override = m.trim();
      else {
        try { override = JSON.stringify(last); } catch { override = ''; }
      }
    } else if (typeof last === 'string' && last.trim()) {
      override = last.trim();
    }
    if (!override) override = input.trim();
    override = appendFailConstraintOverlay(override, overlay);
    if (override && override !== input) setInput(override);
    if (overlay) {
      toast.info('一键修复 → 同一用例重跑', '已叠加精简失败点约束');
    }
    void handleExecute(override || undefined);
  };

  const handleApplyQualityFix = async (issueCodes: string[]) => {
    const skillId = resolveAgentSkillTarget();
    if (!skillId) {
      toast.warning('Agent 未绑定 Skill，无法写入 SKILL.md', '请点「去改 SOP」改 Agent 侧铁律');
      return;
    }
    const codes = (issueCodes || []).map(String).filter(Boolean);
    if (!codes.length) return;
    try {
      let res: { status?: string; applied?: string[]; skipped?: string[]; message?: string; error?: string };
      // Engine-shipped skills (architecture_design, …) live under /core/skills — try that first
      // to avoid a noisy 404 on /workspace/skills when the Agent only binds an engine skill.
      try {
        res = await skillApi.applyQualityFix(skillId, { issue_codes: codes });
      } catch {
        res = await workspaceSkillApi.applyQualityFix(skillId, { issue_codes: codes });
      }
      const applied = res?.applied?.length || 0;
      const skipped = res?.skipped?.length || 0;
      if (res?.status === 'applied' && applied > 0) {
        setPostFixReady(true);
        toast.success(
          `已写入 Skill「${skillId}」${applied} 类铁律`,
          '请点「一键修复 → 同一用例重跑」验证',
        );
      } else if (res?.status === 'noop' || skipped > 0) {
        setPostFixReady(true);
        toast.info(
          res?.message || '所选铁律已在 SOP 中，无需重复写入',
          '请点「一键修复 → 同一用例重跑」注入失败约束；空输出/超时先看执行轨迹',
        );
      } else {
        toast.warning(res?.message || res?.error || '未写入任何铁律');
      }
    } catch (e: any) {
      toastGateError(e, '一键修复 SOP 失败');
    }
  };

  const fetchAgentQualityReview = async (opts: {
    input: unknown;
    output: unknown;
    status: string;
    execution_id?: string;
    embedded?: ExecutionQualityReview | null;
  }) => {
    if (!agent) return null;
    const rid = String(opts.execution_id || '').trim();
    // Stale callback from previous 按失败点重跑 — drop
    if (rid && activeRunIdRef.current && rid !== activeRunIdRef.current) {
      return null;
    }
    // Never lock empty_output while the active run is still producing
    const outOkEarly =
      outputAsText(opts.output).trim().length >= 20
      || (opts.output != null && typeof opts.output === 'object' && Object.keys(opts.output as object).length > 0);
    if (!outOkEarly && !opts.embedded && rid && activeRunIdRef.current === rid) {
      // Defer — poller / live path will retry when payload arrives
      return null;
    }
    const embedded = opts.embedded;
    const embIssues = Array.isArray(embedded?.issues) ? embedded!.issues : [];
    const outOk =
      outputAsText(opts.output).trim().length >= 20
      || (opts.output != null && typeof opts.output === 'object' && Object.keys(opts.output as object).length > 0);
    // Only trust status-embedded review while the body is still empty (stream race).
    // With a real payload, always call review-output fresh — otherwise a stale A/pass
    // from finalize greenwashes new gates (undeclared_api_schema_assumption, auth TODO).
    if (
      embedded &&
      typeof embedded === 'object' &&
      (embedded.verdict != null || embIssues.length > 0) &&
      !outOk
    ) {
      if (rid && activeRunIdRef.current && rid !== activeRunIdRef.current) return null;
      if (rid) qualityFetchedForRunRef.current = rid;
      setQualityReview(embedded);
      return embedded;
    }
    const st = String(opts.status || '').toLowerCase();
    if (st !== 'completed' && st !== 'ok' && st !== 'success') {
      setQualityReview(null);
      return null;
    }
    try {
      setQualityReviewLoading(true);
      const rev = (await workspaceAgentApi.reviewOutput(agent.id, {
        input: opts.input,
        output: opts.output,
        status: st,
        execution_id: opts.execution_id,
        prefer_embedded: !outOk,
      })) as ExecutionQualityReview;
      // Drop if a newer 按失败点重跑 started while we awaited review-output
      if (rid && activeRunIdRef.current && rid !== activeRunIdRef.current) {
        return null;
      }
      if (rid) qualityFetchedForRunRef.current = rid;
      setQualityReview(rev);
      return rev;
    } catch {
      setQualityReview(null);
      return null;
    } finally {
      setQualityReviewLoading(false);
    }
  };

  // Safety net: live-done path used to finalize status without loading quality_review,
  // so the「产物质量复核 / 一键修复」panel never appeared.
  // Also: if we locked onto empty_output while output later arrives (fix→rerun race), re-review.
  useEffect(() => {
    if (!agent || !result) return;
    const st = String(result.status || '').toLowerCase();
    const rid = String(result.run_id || result.execution_id || '').trim();
    const lagging = st === 'running' || st === 'accepted' || st === 'unknown' || st === 'started' || !st;
    // Only reconcile "review exists but UI lagging" when the review belongs to THIS run.
    // Otherwise 按失败点重跑: stale empty_output review + new running → force-complete + kill poller.
    const reviewForThisRun =
      Boolean(qualityReview)
      && rid
      && (qualityFetchedForRunRef.current === rid || activeRunIdRef.current === rid);
    if (qualityReview && lagging && reviewForThisRun) {
      setResult((prev) =>
        prev && ['running', 'accepted', 'unknown', 'started', ''].includes(String(prev.status || '').toLowerCase())
          ? { ...prev, status: 'completed' }
          : prev,
      );
      setLoading(false);
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
      return;
    }
    if (qualityReview && lagging && !reviewForThisRun) {
      // Stale review from previous run — drop so new execution can proceed
      setQualityReview(null);
      return;
    }
    // Timeout/cancel has no product to grade — never keep prior-run C panel (run-94fcad UI).
    if (['timeout', 'cancelled', 'canceled'].includes(st)) {
      if (qualityReview) setQualityReview(null);
      if (rid) qualityFetchedForRunRef.current = rid;
      return;
    }
    if (st === 'failed' || st === 'error') {
      // Keep review only when it was fetched for THIS failed run
      if (qualityReview && rid && qualityFetchedForRunRef.current !== rid) {
        setQualityReview(null);
      }
      return;
    }
    if (st !== 'completed' && st !== 'ok' && st !== 'success') return;
    if (!rid) return;
    const outText = outputAsText(result.output).trim();
    const staleEmpty =
      Array.isArray(qualityReview?.issues)
      && qualityReview!.issues.some((i) => String((i as { code?: string })?.code || '') === 'empty_output')
      && outText.length >= 20;
    if (staleEmpty) {
      if (emptyOutputRetriedRef.current === rid) return;
      emptyOutputRetriedRef.current = rid;
      qualityFetchedForRunRef.current = '';
      void fetchAgentQualityReview({
        input: lastAgentInputRef.current,
        output: result.output,
        status: 'completed',
        execution_id: rid,
      });
      return;
    }
    if (qualityReview || qualityReviewLoading) return;
    if (qualityFetchedForRunRef.current === rid) return;
    // Defer quality fetch while output still empty — live-done poller may still be filling it.
    if (!outText && !result.error) return;
    qualityFetchedForRunRef.current = rid;
    void fetchAgentQualityReview({
      input: lastAgentInputRef.current,
      output: result.output,
      status: 'completed',
      execution_id: rid,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetchAgentQualityReview is stable enough; only re-run on terminal result
  }, [agent?.id, result?.status, result?.run_id, result?.execution_id, result?.output, result?.error, qualityReview, qualityReviewLoading]);

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
        setHelpInputSchema(schema && Object.keys(schema).length ? schema : null);
        const label = agent.display_name || agent.name || agent.id;
        const meta = (agent.metadata || {}) as Record<string, unknown>;
        const reqSkills = Array.isArray(meta.required_skills) ? (meta.required_skills as string[]) : [];
        const skillIds = [...new Set([...(agent.skills || []), ...reqSkills])];
        if (schema && Object.keys(schema).length > 0) {
          exs = sanitizeExecutionExamples(exs, schema, String(agent.id || label));
        }
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
        setHelpInputSchema(null);
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
    if (persist) {
      const ok = window.confirm(
        '将覆盖 AGENT.md 里已保存的测试用例（execution_examples）。\n'
        + '仅当本次被判定为 LLM 成功时才会写入；启发式回退不会覆盖。\n'
        + '编码/脚手架 Agent 请优先用系统「填入」用例；确认仍要写入？',
      );
      if (!ok) return;
    }
    try {
      setLlmGenerating(true);
      const res = await workspaceAgentApi.generateExecutionExamples(agent.id, {
        persist,
        refine_hint: buildExampleRefineHint(helpInputSchema, input) || undefined,
      });
      const exs = (res?.examples || []) as Array<{ title: string; content: string }>;
      if (!exs.length) {
        toast.error('未生成可用用例');
        return;
      }
      const cleaned = helpInputSchema && Object.keys(helpInputSchema).length
        ? sanitizeExecutionExamples(exs, helpInputSchema, String(agent.id || ''))
        : sanitizeExecutionExamples(exs, {}, String(agent.id || ''));
      if (!cleaned.length) {
        toast.error('未生成可用用例（已丢弃把说明当入参的芯片）');
        return;
      }
      setExamples(cleaned);
      const src = res?.source === 'llm' ? 'LLM' : '启发式回退';
      if (persist && res?.persisted) {
        toast.success(`已生成 ${cleaned.length} 条（${src}）并写入 AGENT.md`);
      } else if (persist && !res?.persisted) {
        toast.warning(`已生成 ${cleaned.length} 条（${src}），未写入 AGENT.md`);
      } else {
        toast.success(`已生成 ${cleaned.length} 条（${src}），请点「填入」写入输入框`);
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
                // Historical eval_results is not this-run score; drop on failure/timeout.
                eval: done ? prev?.eval : undefined,
              }));
              if (done && ai.awaiting) {
                // Keep fullscreen so user can confirm again without closing
                toast.warning('Agent 在等你确认', ai.summary);
              } else if (done) {
                toast.success('执行完成');
              } else if (newStatus === 'timeout') {
                toast.error('执行超时', String(sData?.error || '').slice(0, 160) || undefined);
              }
            }
          } catch { /* keep polling */ }
          if (polls >= 900) { stopPolling(); toast.error('执行超时（1800s）'); }
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

  const handleExecute = async (inputOverride?: string) => {
    if (!agent) return;
    // onClick={handleExecute} passes a click event as 1st arg — ignore non-strings.
    const overrideText = typeof inputOverride === 'string' ? inputOverride : undefined;
    if (isSiteTester) {
      let parsed: Record<string, unknown> = {};
      const siteRaw = (overrideText ?? input).trim();
      if (siteRaw) {
        try { parsed = JSON.parse(siteRaw); } catch { parsed = { message: siteRaw }; }
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
    // New run: stop previous poller so it cannot finalize empty_output on a stale completed row
    // while the new skill is still writing output (common after 一键修复→同一用例重跑).
    stopPolling();
    let parsedInput: Record<string, unknown> = {};
    const rawIn = (overrideText ?? input).trim();
    if (rawIn) { try { parsedInput = JSON.parse(rawIn); } catch { parsedInput = { message: rawIn }; } }
    setLoading(true);
    lastAgentInputRef.current = parsedInput;
    setQualityReview(null);
    qualityFetchedForRunRef.current = '';
    emptyOutputRetriedRef.current = '';
    // Optimistic in-flight UI — clear prior run_id so canvas does not keep the
    // finished previous graph under a new 「执行中」header.
    activeRunIdRef.current = '__pending__';
    executeAbortRef.current?.abort();
    const execAbort = new AbortController();
    executeAbortRef.current = execAbort;
    setResult((prev) =>
      prev
        ? {
            ...prev,
            status: 'running',
            run_id: undefined,
            execution_id: undefined,
            error: undefined,
            error_message: undefined,
            output: undefined,
            eval: undefined,
            duration_ms: undefined,
          }
        : { status: 'running' },
    );
    try {
      const streamOpts = { ...((parsedInput.options || {}) as Record<string, unknown>), toolset, stream: true };
      const execPayload: any = { input: parsedInput, options: streamOpts, config: (parsedInput.config || {}) as Record<string, unknown> };
      if (isRagAgent && selectedDomain) {
        execPayload.context = { scope: { collection_id: selectedDomain, doc_ids: [] }, collection_id: selectedDomain, tenant_id: 'default' };
      }
      // Stream accept must return run_id in seconds; 45s = Core likely wedged (listen but no reply).
      const result = await workspaceAgentApi.execute(agent.id, execPayload, {
        timeoutMs: 45_000,
        signal: execAbort.signal,
      });
      const status = String((result as any)?.status || 'ok');
      const runId = (result as any)?.run_id || (result as any)?.execution_id || '';
      if (runId) activeRunIdRef.current = String(runId);
      const execEval = (result as any)?.eval;
      const execDuration = (result as any)?.duration_ms as number | undefined;
      const execSteps = ((result as any)?.metadata?.steps as number) || undefined;
      const out0 = unwrapOutput((result as any)?.output);
      setResult({ status, execution_id: String((result as any)?.execution_id || ''), run_id: runId, output: out0, error: (result as any)?.error, tokens: (result as any)?.tokens, eval: execEval, duration_ms: execDuration, steps: execSteps });
      if (status === 'completed' || status === 'ok' || status === 'success') {
        await fetchAgentQualityReview({
          input: parsedInput,
          output: out0,
          status: 'completed',
          execution_id: runId || String((result as any)?.execution_id || ''),
          embedded: (result as any)?.quality_review || null,
        });
      }
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
        const outputReady = (out: unknown) => {
          const t = outputAsText(out).trim();
          if (t.length >= 20) return true;
          if (out && typeof out === 'object' && Object.keys(out as object).length > 0) return true;
          return false;
        };
        const settleTerminalPayload = async (first: any): Promise<any> => {
          // Graph/row may flip to completed before output upsert — same race as onLiveStatusChange.
          let sData = first;
          for (let i = 0; i < 16; i++) {
            const raw = String(sData?.status || '').toLowerCase();
            if (['failed', 'error', 'timeout', 'cancelled', 'canceled'].includes(raw)) return sData;
            if (sData?.error) return sData;
            if (outputReady(unwrapOutput(sData?.output)) && !sData?.pending_output) return sData;
            if (raw === 'completed' || raw === 'ok' || raw === 'success' || raw === 'done') {
              if (outputReady(unwrapOutput(sData?.output))) return sData;
            } else {
              return sData; // still transitional — caller keeps polling
            }
            await new Promise((r) => setTimeout(r, 500));
            try {
              sData = await apiClient.get(
                `/core/executions/${encodeURIComponent(runId)}/status`
              );
            } catch {
              break;
            }
          }
          return sData;
        };
        const applyDone = async (newStatus: string, sDataIn: any) => {
          if (stopped) return;
          if (activeRunIdRef.current && runId && activeRunIdRef.current !== runId) return;
          const sData = await settleTerminalPayload(sDataIn);
          if (activeRunIdRef.current && runId && activeRunIdRef.current !== runId) return;
          const rawSt = String(sData?.status || newStatus || '').toLowerCase();
          const out = unwrapOutput(sData?.output);
          const hasOut = outputReady(out);
          let doneSt = rawSt;
          if (
            (!rawSt || rawSt === 'running' || rawSt === 'accepted')
            && hasOut
            && !sData?.pending_output
          ) {
            doneSt = 'completed';
          }
          const done = doneSt === 'completed' || doneSt === 'ok' || doneSt === 'success';
          // completed-but-empty: keep outer poller alive (caller uses polls < 90).
          // Do not stopPolling / lock empty_output — 按失败点重跑后 Skill LLM 常更慢。
          if (done && !hasOut && !sData?.error) {
            setResult(prev => prev ? {
              ...prev,
              status: 'running',
              output: out ?? prev.output,
              duration_ms: sData?.duration_ms ?? prev.duration_ms,
            } : prev);
            setLoading(true);
            return;
          }
          stopped = true;
          stopPolling();
          const text = outputAsText(out);
          const awaitInfo = detectAwaitingUser(text);
          setResult(prev => ({
            ...prev!,
            status: done ? 'completed' : (doneSt || 'failed'),
            output: typeof out === 'string' ? out : (out ?? prev?.output),
            error: sData?.error || prev?.error,
            duration_ms: sData?.duration_ms ?? prev?.duration_ms,
            eval: done ? prev?.eval : undefined,
          }));
          if (done && hasOut) {
            void fetchAgentQualityReview({
              input: lastAgentInputRef.current ?? sData?.input ?? null,
              output: out,
              status: 'completed',
              execution_id: runId,
              embedded: sData?.quality_review || null,
            }).then((rev) => {
              if (rev && String(rev.verdict) === 'fail') {
                toast.warning('执行完成，但产物质量未过关 — 见问题点与改 SOP 指引');
              }
            });
          }
          const v = deriveRunVerdict({
            status: done ? 'completed' : (doneSt || 'failed'),
            error: sData?.error,
            outputText: text,
            awaiting: awaitInfo.awaiting,
            awaitSummary: awaitInfo.summary,
          });
          notifyRunVerdict(v, { preferBanner: true, delayMs: v.ok === false || v.kind === 'awaiting' ? 600 : 0 });
        };
        pollingRef.current = setInterval(async () => {
          if (stopped) return;
          if (activeRunIdRef.current && runId && activeRunIdRef.current !== runId) return;
          polls++;
          try {
            const sData = await apiClient.get<{ status?: string; output?: unknown; error?: unknown; duration_ms?: number; pending_output?: boolean; quality_review?: ExecutionQualityReview; input?: unknown }>(
              `/core/executions/${encodeURIComponent(runId)}/status`
            );
            const newStatus = String(sData?.status || '');
            const raw = newStatus.toLowerCase();
            // Keep polling while completed-but-empty / pending_output (upsert race after SOP fix / fail-constraint rerun)
            if (raw === 'completed' || raw === 'ok' || raw === 'success' || raw === 'done') {
              if (sData?.pending_output || !outputReady(unwrapOutput(sData?.output))) {
                if (polls < 90) return; // ~180s grace — fail-constraint rerun + architecture LLM
              }
              await applyDone(newStatus, sData);
              return;
            }
            if (newStatus && newStatus !== 'running' && newStatus !== 'accepted') {
              await applyDone(newStatus, sData);
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
                await applyDone(newStatus, rData);
                return;
              }
            } catch { /* still running */ }
          }
          if (polls >= 900) {
            stopPolling();
            toast.error('执行超时（1800s）', 'Agent 可能仍在后台运行，查看诊断详情获取最新状态。');
          }
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
    } catch (e: any) {
      if (activeRunIdRef.current === '__pending__') activeRunIdRef.current = '';
      const msg = String(e?.message || e?.detail || '执行失败');
      if (/请求已取消|用户取消|用户停止/.test(msg)) {
        // handleStop already painted cancelled UI
        return;
      }
      const startStuck =
        /超时|timeout|abort|failed to fetch|network|ECONNREFUSED/i.test(msg) ||
        msg.includes('后端服务');
      setResult({
        status: 'failed',
        error: startStuck
          ? `${msg}（未拿到 run_id：Core 可能卡死，请重启 aiPlat-core 后再执行）`
          : msg,
      });
      toastGateError(e, startStuck ? '启动失败' : '执行失败');
    }
    finally {
      if (executeAbortRef.current === execAbort) executeAbortRef.current = null;
      setLoading(false);
    }
  };

  const handleStop = async () => {
    // Paint cancelled immediately. A hung Core event loop (POST_LOOP after
    // auto_done) cannot serve /cancel; waiting the default 180s fetch timeout
    // is what makes the Stop button spin forever.
    const rid = String(
      activeRunIdRef.current || result?.run_id || result?.execution_id || ''
    ).trim();
    try { executeAbortRef.current?.abort(); } catch { /* ignore */ }
    executeAbortRef.current = null;
    stopPolling();
    setLoading(false);
    setStopping(false);
    if (rid && rid !== '__pending__') {
      setResult((prev) =>
        prev
          ? { ...prev, status: 'cancelled', error: '用户停止', run_id: rid, execution_id: prev.execution_id || rid }
          : { status: 'cancelled', error: '用户停止', run_id: rid, execution_id: rid }
      );
      activeRunIdRef.current = '';
      toast.success('已请求停止执行');
      try {
        await apiClient.post<{ status?: string; already_terminal?: boolean }>(
          `/core/executions/${encodeURIComponent(rid)}/cancel`,
          { reason: 'user_stop' },
          { timeoutMs: 6000 },
        );
      } catch {
        try {
          await apiClient.post(
            `/core/runs/${encodeURIComponent(rid)}/cancel`,
            { reason: 'user_stop' },
            { timeoutMs: 4000 },
          );
        } catch { /* Core may be wedged; UI already cancelled */ }
      }
    } else if (rid === '__pending__' || loading) {
      activeRunIdRef.current = '';
      setResult((prev) =>
        prev
          ? { ...prev, status: 'cancelled', error: '用户取消启动', run_id: undefined, execution_id: undefined }
          : { status: 'cancelled', error: '用户取消启动' },
      );
      toast.success('已取消启动');
    } else {
      toast.success('已请求停止');
    }
    try {
      await browserTestApi.stop();
      await browserTestApi.stopCaseExecution();
    } catch { /* browser stop optional */ }
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
            <Button variant="danger" onClick={handleStop} loading={stopping} disabled={!loading && !caseGenLoading && !['running', 'accepted', 'queued'].includes(String(result?.status || ''))} title={loading || caseGenLoading || ['running', 'accepted', 'queued'].includes(String(result?.status || '')) ? '停止当前操作' : '暂无执行中的任务'}>
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
            <Button
              variant="danger"
              onClick={handleStop}
              loading={stopping}
              disabled={
                !loading &&
                !['running', 'accepted', 'queued'].includes(String(result?.status || ''))
              }
              title={
                loading || ['running', 'accepted', 'queued'].includes(String(result?.status || ''))
                  ? '停止当前执行'
                  : '暂无执行中的任务'
              }
            >
              ⏹ 停止
            </Button>
            <div style={{ flex: 1 }} />
            <Button variant="secondary" onClick={() => { stopPolling(); onClose(); setInput(''); setResult(null); setRoutingResult(null); }} disabled={loading}>关闭</Button>
            <Button variant="primary" onClick={() => { void handleExecute(); }} loading={loading}>执行</Button>
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
                  {!['timeout', 'cancelled', 'canceled', 'running', 'accepted', 'queued'].includes(
                    String(result?.status || '').toLowerCase(),
                  ) && (
                  <div className="mb-3">
                    <ExecutionQualityReviewPanel
                      review={qualityReview}
                      loading={qualityReviewLoading}
                      persistKey="agent-exec-modal"
                      onApplyQualityFix={handleApplyQualityFix}
                      fixApplied={postFixReady}
                      onRerunSameCase={handleRerunSameCase}
                      rerunLoading={loading}
                      onEditSop={
                        onEditSop ||
                        (() => {
                          toast.info('请关闭执行窗，打开「编辑 Agent」→ SOP / 高级，按问题点加固铁律后重跑');
                        })
                      }
                    />
                  </div>
                  )}
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
                    {result.eval?.has_data &&
                      ['completed', 'ok', 'success'].includes(String(result.status || '').toLowerCase()) && (
                      <span
                        className={`text-xs px-2 py-0.5 rounded ml-3 ${
                          qualityReview && String(qualityReview.verdict) === 'fail'
                            ? 'bg-gray-800/60 text-gray-500 line-through'
                            : (result.eval.grade || '').startsWith('A')
                              ? 'bg-green-900/40 text-green-300'
                              : (result.eval.grade || '').startsWith('B')
                                ? 'bg-blue-900/40 text-blue-300'
                                : 'bg-orange-900/40 text-orange-300'
                        }`}
                        title={
                          qualityReview && String(qualityReview.verdict) === 'fail'
                            ? '历史评测仅供参考；本次产物质量复核未通过'
                            : '历史评测（eval_results），非本次执行打分'
                        }
                      >
                        历史评测 {result.eval.grade || '?'}级 {Math.round(result.eval.score || 0)}分 (
                        {result.eval.total_tasks || 0}次)
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
                    <div className="text-gray-300 min-h-[16rem]">
                      <StructuredSkillOutput text={resultText} raw={resultRaw ?? result.output} schema={resultSchema} />
                    </div>
                  ) : result.output != null ? (
                    <div className="text-gray-300 min-h-[16rem]">
                      <StructuredSkillOutput
                        text={typeof resultRaw === 'string' ? resultRaw : typeof result.output === 'string' ? result.output : ''}
                        raw={resultRaw ?? result.output}
                        schema={resultSchema}
                      />
                    </div>
                  ) : null}
                  {result.execution_id && (
                    <div className="mt-3 flex items-center justify-between gap-2 flex-wrap">
                      <div className="text-xs text-gray-400 break-all">execution_id: {result.execution_id}</div>
                      <div className="flex gap-2">
                        <Button variant="secondary" size="sm" onClick={async () => { try { await navigator.clipboard.writeText(result.execution_id || ''); toast.success('已复制'); } catch { toast.error('复制失败'); } }}>复制ID</Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          onMouseEnter={() => {
                            // Preload lazy chunk so new-tab Suspense is brief
                            void import('../pages/Diagnostics/Links/Links');
                          }}
                          onClick={() => {
                            void import('../pages/Diagnostics/Links/Links');
                            window.open(
                              `/diagnostics/links?execution_id=${encodeURIComponent(result.execution_id || '')}&include_spans=true`,
                              '_blank',
                              'noopener,noreferrer',
                            );
                          }}
                        >
                          查看诊断详情
                        </Button>
                      </div>
                    </div>
                  )}
                  <div className="mt-3 flex flex-wrap gap-2">
                    {resultText ? (
                      <Button variant="primary" onClick={() => setOutputFullscreen(true)}>
                        📄 全屏查看产出
                      </Button>
                    ) : null}
                    {result.run_id ? (
                      <Button variant="secondary" onClick={() => setFlowFullscreen(true)}>
                        ▶ 查看执行流程（全屏）
                      </Button>
                    ) : null}
                  </div>
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

      {/* ── 全屏执行流程弹窗（重跑清空 run_id 时仍保持挂载，避免闪回上一轮完成图） ── */}
      {flowFullscreen && result && (result.run_id || displayVerdict.kind === 'running' || loading) && (
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
              <Button
                variant="danger"
                onClick={() => { void handleStop(); }}
                loading={stopping}
                disabled={
                  !loading &&
                  !['running', 'accepted', 'queued'].includes(String(result?.status || ''))
                }
                title={
                  loading || ['running', 'accepted', 'queued'].includes(String(result?.status || ''))
                    ? '停止当前执行'
                    : '暂无执行中的任务'
                }
              >
                ⏹ 停止
              </Button>
              {resultText ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setFlowFullscreen(false);
                    setOutputFullscreen(true);
                  }}
                >
                  📄 全屏产出
                </Button>
              ) : null}
              <Button variant="secondary" onClick={() => setFlowFullscreen(false)}>✕ 关闭</Button>
            </div>
          </div>
          <div className="flex-1 min-h-0 flex flex-col p-2 gap-2">
            {/* Quality strip ABOVE graph — collapsed by default on fail/warn */}
            {(qualityReview || qualityReviewLoading) &&
              !['timeout', 'cancelled', 'canceled', 'running', 'accepted', 'queued'].includes(
                String(result?.status || '').toLowerCase(),
              ) && (
              <div className="flex-shrink-0 rounded-lg">
                <ExecutionQualityReviewPanel
                  review={qualityReview}
                  loading={qualityReviewLoading}
                  persistKey="agent-exec-fs"
                  onApplyQualityFix={handleApplyQualityFix}
                  fixApplied={postFixReady}
                  onRerunSameCase={handleRerunSameCase}
                  rerunLoading={loading}
                  onEditSop={
                    onEditSop ||
                    (() => {
                      toast.info('请关闭执行窗，打开「编辑 Agent」→ SOP / 高级，按问题点加固铁律后重跑');
                    })
                  }
                />
              </div>
            )}
            <div className="flex-1 min-h-0">
              {!result.run_id ? (
                <div className="h-full flex flex-col items-center justify-center gap-2 text-sm text-gray-400 px-6 text-center">
                  <span className="inline-block w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                  <span>正在启动新执行，等待 Core 返回 run_id…</span>
                  <span className="text-xs text-gray-500">若超过约 45 秒仍无进展，多半是 Core 卡死；点「停止」或重启 core 后再试</span>
                </div>
              ) : (
              <ExecutionViewer
                key={result.run_id}
                runId={result.run_id}
                live={true}
                running={displayVerdict.kind === 'running'}
                title=""
                height={Math.max(240, window.innerHeight - (qualityReview || qualityReviewLoading || result.output || result.error || awaitInfo.awaiting || displayVerdict.ok !== null ? 280 : 100))}
                onLiveStatusChange={async (liveSt) => {
                if (activeRunIdRef.current === '__pending__') return;
                if (liveSt !== 'done' || result.status === 'failed' || result.status === 'timeout') return;
                const liveRunId = String(result.run_id || '').trim();
                if (liveRunId && activeRunIdRef.current && liveRunId !== activeRunIdRef.current) return;
                // Parent already flipped to a newer run — ignore stale done from previous graph
                if (['running', 'accepted', 'queued'].includes(String(result.status || '').toLowerCase())
                  && activeRunIdRef.current && liveRunId !== activeRunIdRef.current) {
                  return;
                }
                // Allow refresh when prior review was a false empty_output (upsert race).
                const priorEmpty =
                  Array.isArray(qualityReview?.issues)
                  && qualityReview!.issues.some((i) => String((i as { code?: string })?.code || '') === 'empty_output');
                if (result.status === 'completed' && qualityReview && !priorEmpty) return;
                try {
                  type StatusPayload = {
                    status?: string;
                    output?: unknown;
                    error?: unknown;
                    duration_ms?: number;
                    input?: unknown;
                    quality_review?: ExecutionQualityReview;
                    pending_output?: boolean;
                  };
                  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
                  const outputReady = (out: unknown) => {
                    const t = outputAsText(out).trim();
                    if (t.length >= 20) return true;
                    if (out && typeof out === 'object' && Object.keys(out as object).length > 0) return true;
                    return false;
                  };
                  // Graph may close before agent/skill row upserts output — poll until
                  // payload arrives (or hard fail) so quality review does not see empty_output.
                  // Fail-constraint rerun often needs >10s — wait up to ~60s here; status poller covers the rest.
                  let sData: StatusPayload | null = null;
                  for (let i = 0; i < 60; i++) {
                    if (liveRunId && activeRunIdRef.current && liveRunId !== activeRunIdRef.current) return;
                    sData = await apiClient.get<StatusPayload>(
                      `/core/executions/${encodeURIComponent(result.run_id!)}/status`
                    );
                    const raw = String(sData?.status || '').toLowerCase();
                    if (['failed', 'error', 'timeout', 'cancelled', 'canceled'].includes(raw)) break;
                    if (sData?.error) break;
                    if (outputReady(unwrapOutput(sData?.output)) && !sData?.pending_output) break;
                    if (raw === 'completed' || raw === 'ok' || raw === 'success' || raw === 'done') {
                      if (outputReady(unwrapOutput(sData?.output))) break;
                      // completed-but-empty: keep waiting for upsert
                    }
                    await sleep(1000);
                  }
                  if (liveRunId && activeRunIdRef.current && liveRunId !== activeRunIdRef.current) return;
                  const rawSt = String(sData?.status || '').toLowerCase();
                  // Only coerce running→completed when output is actually present
                  // (or pending_output cleared). Otherwise keep running so UI stays honest.
                  const out = unwrapOutput(sData?.output);
                  const hasOut = outputReady(out);
                  let newStatus = rawSt;
                  if (
                    (!rawSt || rawSt === 'running' || rawSt === 'accepted' || rawSt === 'unknown' || rawSt === 'started')
                    && hasOut
                    && !sData?.pending_output
                  ) {
                    newStatus = 'completed';
                  } else if (
                    (!rawSt || rawSt === 'running' || rawSt === 'accepted' || rawSt === 'unknown' || rawSt === 'started')
                    && !hasOut
                    && !sData?.pending_output
                    && !sData?.error
                  ) {
                    // Graph SSE may end while Skill LLM is still generating — do NOT
                    // invent completed+empty (false empty_output → wrong「一键修复 SOP」).
                    newStatus = rawSt || 'running';
                  }
                  const stillRunning = ['running', 'accepted', 'started', 'pending', 'unknown', ''].includes(
                    String(newStatus || '').toLowerCase(),
                  );
                  const done = newStatus === 'completed' || newStatus === 'ok' || newStatus === 'success';
                  setResult(prev => prev ? {
                    ...prev,
                    status: done ? 'completed' : (stillRunning ? 'running' : newStatus),
                    output: out ?? prev.output,
                    error: sData?.error || prev.error,
                    duration_ms: sData?.duration_ms ?? prev.duration_ms,
                    eval: done ? prev.eval : undefined,
                  } : prev);
                  if (stillRunning && !hasOut) {
                    // Keep modal in loading/poll; graph-done alone is not enough
                    setLoading(true);
                    toast.info('执行仍在进行', '画布已收尾，但输出尚未写入——请稍候，勿点一键修复 SOP。');
                    return;
                  }
                  stopPolling();
                  setLoading(false);
                  if (done) {
                    // Prefer status payload over stale closure result.output
                    const reviewOut = hasOut ? out : (out ?? null);
                    void fetchAgentQualityReview({
                      input: lastAgentInputRef.current ?? sData?.input ?? null,
                      output: reviewOut,
                      status: 'completed',
                      execution_id: result.run_id!,
                      embedded: sData?.quality_review || null,
                    }).then((rev) => {
                      if (rev && String(rev.verdict) === 'fail') {
                        const codes = new Set(
                          (rev.issues || []).map((i) => String((i as { code?: string })?.code || '')),
                        );
                        if (codes.has('empty_output') || codes.has('runtime_timeout') || codes.has('runtime_failed')) {
                          toast.warning('执行完成但无可用产物', '请看执行轨迹 / 诊断详情，勿点一键修复 SOP。');
                        } else {
                          toast.warning('执行完成，但产物质量未过关 — 见上方「产物质量复核」');
                        }
                      }
                    });
                  }
                } catch {
                  // Do not invent success — leave status as-is
                  stopPolling();
                  toast.warning('状态待确认', '实时事件已结束，但未能拉取最终状态。可打开诊断详情核对。');
                }
              }}
              />
              )}
            </div>
            {(resultText || result.error || awaitInfo.awaiting || displayVerdict.ok === false || displayVerdict.ok === true || displayVerdict.kind === 'partial') && (
              <div className="flex-shrink-0 border border-dark-border bg-dark-card rounded-lg overflow-hidden">
                <div className="flex items-center justify-between gap-2 px-3 py-1.5 border-b border-dark-border/60">
                  <button
                    type="button"
                    className="text-xs text-gray-300 hover:text-gray-100 flex items-center gap-1.5 min-w-0"
                    onClick={() => setFsOutputOpen((v) => !v)}
                  >
                    <span className="font-medium">执行输出</span>
                    {result.error ? <span className="text-red-400">· 有错误</span> : null}
                    {awaitInfo.awaiting ? <span className="text-amber-300">· 等待确认</span> : null}
                    <span className="text-[10px] text-gray-500">{fsOutputOpen || awaitInfo.awaiting ? '收起 ▴' : '展开 ▾'}</span>
                  </button>
                  {!(qualityReview || qualityReviewLoading) ? (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${VERDICT_BADGE_CLASS[displayVerdict.tone]}`}>
                      {displayVerdict.label}
                    </span>
                  ) : null}
                </div>
                {(fsOutputOpen || awaitInfo.awaiting) && (
              <div className="p-3 max-h-[36vh] overflow-y-auto space-y-2">
                {!(qualityReview || qualityReviewLoading) ? <RunVerdictBanner verdict={displayVerdict} /> : null}
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
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-xs font-medium text-gray-300">执行输出</div>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          setFlowFullscreen(false);
                          setOutputFullscreen(true);
                        }}
                      >
                        📄 全屏查看
                      </Button>
                    </div>
                    <StructuredSkillOutput text={resultText} raw={resultRaw ?? result.output} schema={resultSchema} />
                  </>
                )}
              </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      <ExecuteOutputFullscreen
        open={!!(outputFullscreen && resultText)}
        title={`产出 · ${agent?.name || 'Agent'}`}
        text={resultText}
        raw={resultRaw ?? result?.output}
        schema={resultSchema}
        onClose={() => setOutputFullscreen(false)}
        onOpenFlow={
          result?.run_id
            ? () => {
                setOutputFullscreen(false);
                setFlowFullscreen(true);
              }
            : undefined
        }
      />
    </Modal>
    </>
  );
};

export default ExecuteAgentModal;
