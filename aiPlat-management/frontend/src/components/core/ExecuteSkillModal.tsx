import React, { useEffect, useMemo, useState } from 'react';

import { Button, Modal, Textarea, toast } from '../ui';
import { skillApi, diagnosticsApi } from '../../services';
import { toastGateError } from '../ui';
import { buildExampleRefineHint, buildExamplesFromSchema, isGenericExampleSet, sanitizeExecutionExamples } from '../../utils/executionSamples';
import ExecuteResultPanel from '../execution/ExecuteResultPanel';
import ExecuteFlowFullscreen from '../execution/ExecuteFlowFullscreen';
import ExecuteOutputFullscreen from '../execution/ExecuteOutputFullscreen';
import { RunVerdictBanner, deriveRunVerdict, outputAsText } from '../execution/runVerdict';
import ExecutionQualityReviewPanel, {
  type ExecutionQualityReview,
} from '../execution/ExecutionQualityReviewPanel';
import {
  isSkillRunInFlight,
  normalizeSkillExecuteResult as normalizeSkillExecuteResultBase,
  shouldOpenSkillFlow,
} from '../../utils/skillExecute';
import { pollSkillExecutionUntilDone } from '../../utils/pollSkillExecution';
import { appendFailConstraintOverlay, buildFailConstraintOverlay } from '../../utils/failConstraintOverlay';

interface ExecuteSkillModalProps {
  open: boolean;
  skill: {
    id: string;
    name: string;
    metadata?: Record<string, unknown> | null;
    output_schema?: Record<string, unknown> | null;
  } | null;
  onClose: () => void;
  /** Jump to edit SOP when quality review fails (parent opens EditSkillModal). */
  onEditSop?: () => void;
}

function normalizeSkillExecuteResult(res: any) {
  const n = normalizeSkillExecuteResultBase(res);
  return { ...n, quality_review: res?.quality_review };
}

function applyQualityToVerdict(
  base: ReturnType<typeof deriveRunVerdict>,
  review: ExecutionQualityReview | null,
) {
  if (!review || base.kind !== 'success') return base;
  const v = String(review.verdict || '');
  if (v === 'fail') {
    return {
      ...base,
      kind: 'partial' as const,
      label: '已结束（产物待改进）',
      hint: review.headline || '流程跑通了，但产物未达可验收标准。请看下方问题点与改 SOP 指引。',
      tone: 'amber' as const,
      ok: null,
    };
  }
  if (v === 'warn') {
    return {
      ...base,
      kind: 'partial' as const,
      label: '已结束（有改进建议）',
      hint: review.headline || '产物基本可用，仍有建议项。',
      tone: 'amber' as const,
      ok: null,
    };
  }
  return base;
}

function toastForReview(rev: ExecutionQualityReview | null) {
  if (rev && String(rev.verdict) === 'fail') {
    toast.warning('执行完成，但产物质量未过关 — 见问题点与改 SOP 指引');
  } else if (rev && String(rev.verdict) === 'warn') {
    toast.info('执行完成，有改进建议');
  } else {
    toast.success('执行成功');
  }
}

/** Engine Core Skills — same stream + live flow + quality review as workspace Skills. */
const ExecuteSkillModal: React.FC<ExecuteSkillModalProps> = ({ open, skill, onClose, onEditSop }) => {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ReturnType<typeof normalizeSkillExecuteResult> | null>(null);
  const [inputText, setInputText] = useState('');
  const [autoSmoke, setAutoSmoke] = useState(false);
  const [flowFullscreen, setFlowFullscreen] = useState(false);
  const [outputFullscreen, setOutputFullscreen] = useState(false);
  const [qualityReview, setQualityReview] = useState<ExecutionQualityReview | null>(null);
  const [qualityReviewLoading, setQualityReviewLoading] = useState(false);
  const [postFixReady, setPostFixReady] = useState(false);
  const [skillTimeoutSec, setSkillTimeoutSec] = useState(300);
  const [outputSchema, setOutputSchema] = useState<Record<string, unknown> | null>(null);
  const [helpMarkdown, setHelpMarkdown] = useState('');
  const [examples, setExamples] = useState<Array<{ title: string; content: string }>>([]);
  const [helpInputSchema, setHelpInputSchema] = useState<Record<string, unknown> | null>(null);
  const [llmGenerating, setLlmGenerating] = useState(false);
  const [helpLoading, setHelpLoading] = useState(false);
  const lastInputRef = React.useRef<unknown>(null);

  useEffect(() => {
    if (!open || !skill?.id) {
      setOutputSchema(null);
      return;
    }
    const embedded = skill.output_schema;
    if (embedded && typeof embedded === 'object' && Object.keys(embedded).length > 0) {
      setOutputSchema(embedded);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const { skillApi } = await import('../../services');
        const detail = await skillApi.get(skill.id);
        const os = detail?.output_schema;
        if (!cancelled && os && typeof os === 'object') setOutputSchema(os);
      } catch {
        if (!cancelled) setOutputSchema(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, skill?.id, skill?.output_schema]);

  const fetchQualityReview = async (opts: {
    input: unknown;
    output: unknown;
    status: string;
    execution_id?: string;
    embedded?: ExecutionQualityReview | null;
  }): Promise<ExecutionQualityReview | null> => {
    if (!skill) return null;
    const outOk =
      outputAsText(opts.output).trim().length >= 20
      || (opts.output != null && typeof opts.output === 'object' && Object.keys(opts.output as object).length > 0);
    // Only trust embedded QR while body is empty; with payload, refresh gates.
    if (opts.embedded && typeof opts.embedded === 'object' && !outOk) {
      setQualityReview(opts.embedded);
      return opts.embedded;
    }
    const st = String(opts.status || '').toLowerCase();
    if (st !== 'completed' && st !== 'ok' && st !== 'success') {
      setQualityReview(null);
      return null;
    }
    try {
      setQualityReviewLoading(true);
      const { skillApi } = await import('../../services');
      const rev = (await skillApi.reviewOutput(skill.id, {
        input: opts.input,
        output: opts.output,
        status: st,
        execution_id: opts.execution_id,
        prefer_embedded: !outOk,
      })) as ExecutionQualityReview;
      setQualityReview(rev);
      return rev;
    } catch {
      setQualityReview(null);
      return null;
    } finally {
      setQualityReviewLoading(false);
    }
  };

  const displayVerdict = useMemo(() => {
    if (!result) return null;
    const base = deriveRunVerdict({
      status: result.status,
      error: result.error_message || result.error,
      outputText: outputAsText(result.output),
    });
    return applyQualityToVerdict(base, qualityReview);
  }, [result, qualityReview]);

  useEffect(() => {
    if (!open) return;
    setResult(null);
    setInputText('');
    setFlowFullscreen(false);
    setQualityReview(null);
    setPostFixReady(false);
    const metaTimeout = Number(skill?.metadata?.timeout);
    setSkillTimeoutSec(Number.isFinite(metaTimeout) && metaTimeout > 0 ? metaTimeout : 300);
    setHelpMarkdown('');
    setExamples([]);
    setHelpInputSchema(null);
  }, [open, skill?.id]);

  useEffect(() => {
    if (!open || !skill?.id) return;
    let stopped = false;
    (async () => {
      setHelpLoading(true);
      try {
        const { skillApi } = await import('../../services');
        const res = await skillApi.getExecutionHelp(skill.id);
        if (stopped) return;
        setHelpMarkdown(String((res as any)?.help_markdown || ''));
        const helpTimeout = Number((res as any)?.timeout);
        if (Number.isFinite(helpTimeout) && helpTimeout > 0) setSkillTimeoutSec(helpTimeout);
        let exs = (((res as any)?.examples || []) as Array<{ title: string; content: string }>);
        const schema = ((res as any)?.input_schema as Record<string, unknown> | null) || null;
        setHelpInputSchema(schema && typeof schema === 'object' ? schema : null);
        const hint = `${skill.id || ''} ${skill.name || ''}`;
        if (schema && Object.keys(schema).length > 0) {
          exs = sanitizeExecutionExamples(exs, schema, hint);
          if (isGenericExampleSet(exs)) {
            const generated = buildExamplesFromSchema(schema, skill.name || skill.id, { skillHint: hint });
            if (generated.length > 0) exs = generated;
          }
        }
        setExamples(exs);
      } catch {
        if (!stopped) {
          setHelpMarkdown('');
          const local = skill.input_schema && typeof skill.input_schema === 'object'
            ? skill.input_schema as Record<string, unknown>
            : null;
          setHelpInputSchema(local);
          const generated = local
            ? buildExamplesFromSchema(local, skill.name || skill.id, { skillHint: `${skill.id || ''} ${skill.name || ''}` })
            : [];
          setExamples(generated);
        }
      } finally {
        if (!stopped) setHelpLoading(false);
      }
    })();
    return () => {
      stopped = true;
    };
  }, [open, skill?.id]);

  const handleGenerateLlmExamples = async (persist: boolean) => {
    if (!skill) return;
    if (persist) {
      const ok = window.confirm(
        '将覆盖 SKILL.md 里已保存的测试用例（execution_examples）。\n'
        + '仅当本次被判定为 LLM 成功时才会写入；启发式回退不会覆盖。确认仍要保存？',
      );
      if (!ok) return;
    }
    try {
      setLlmGenerating(true);
      const schema = helpInputSchema && Object.keys(helpInputSchema).length ? helpInputSchema : null;
      const { skillApi } = await import('../../services');
      const res = await skillApi.generateExecutionExamples(skill.id, {
        persist,
        refine_hint: buildExampleRefineHint(schema, inputText) || undefined,
      });
      const exs = (res?.examples || []) as Array<{ title: string; content: string }>;
      if (!exs.length) {
        toast.error('未生成可用用例');
        return;
      }
      const cleaned = schema && Object.keys(schema).length
        ? sanitizeExecutionExamples(exs, schema, `${skill.id || ''} ${skill.name || ''}`)
        : exs;
      if (!cleaned.length) {
        toast.error('未生成可用用例（已丢弃把说明当入参的芯片）');
        return;
      }
      setExamples(cleaned);
      const src = res?.source === 'llm' ? 'LLM' : '启发式回退';
      if (persist && res?.persisted) {
        toast.success(`已生成 ${cleaned.length} 条（${src}）并写入 SKILL.md`);
      } else if (persist && !res?.persisted) {
        toast.warning(`已生成 ${cleaned.length} 条（${src}），未写入 SKILL.md`);
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

  // Stream poll — identical contract to workspace ExecuteSkillModal
  useEffect(() => {
    if (!result || !isSkillRunInFlight(result.status) || !result.run_id || !skill) return;
    const runId = result.run_id;
    let stopped = false;
    (async () => {
      const done = await pollSkillExecutionUntilDone(runId, {
        isStopped: () => stopped,
        timeoutSec: skillTimeoutSec,
      });
      if (stopped) return;
      const normalized = normalizeSkillExecuteResult({
        ...done,
        run_id: runId,
        execution_id: runId,
      });
      setResult(normalized);
      if (done.status === 'completed') {
        const rev = await fetchQualityReview({
          input: lastInputRef.current ?? (done as any)?.input ?? null,
          output: normalized.output,
          status: 'completed',
          execution_id: runId,
          embedded: (done as any)?.quality_review || null,
        });
        if (rev) setResult((prev) => (prev ? { ...prev, quality_review: rev } : prev));
        toastForReview(rev);
      } else if (done.status === 'timeout') {
        toast.error('等待超时', String(done.error || `前端已等约 ${skillTimeoutSec}s；请看诊断详情确认是否仍在跑`));
      } else if (done.status === 'failed' || done.status === 'error') toast.error('执行失败');
    })();
    return () => {
      stopped = true;
    };
  }, [result?.run_id, result?.status, skill?.id, skillTimeoutSec]);

  const handleExecute = async (opts?: { preserveFlow?: boolean; inputOverride?: string }) => {
    if (!skill) return;
    try {
      setLoading(true);
      setQualityReview(null);
      // Re-run: keep prior result until the new run_id arrives so fullscreen stays mounted.
      if (!opts?.preserveFlow) {
        setResult(null);
      }

      const rawInput = (opts?.inputOverride !== undefined ? opts.inputOverride : inputText).trim();
      let payload: Record<string, unknown> = {};
      if (rawInput) {
        try {
          payload = JSON.parse(rawInput);
        } catch {
          payload = { message: rawInput };
        }
      }
      lastInputRef.current = payload;

      const { skillApi } = await import('../../services');
      const res = await skillApi.execute(skill.id, {
        input: payload,
        options: {
          ...((payload.options || {}) as Record<string, unknown>),
          timeout: skillTimeoutSec,
        },
      });
      const normalized = normalizeSkillExecuteResult(res);
      setResult(normalized);
      const st = String(normalized.status || '');
      const legacyStatus = String((res as any)?.legacy_status || '');
      const errCode = String((res as any)?.error?.code || '');
      const approvalId =
        (res as any)?.approval_request_id ||
        (res as any)?.error?.detail?.approval_request_id ||
        (res as any)?.error_detail?.approval_request_id;
      const runId = normalized.run_id || normalized.execution_id;

      if (legacyStatus === 'queued') {
        toast.success('已排队');
      } else if (st === 'waiting_approval' || legacyStatus === 'approval_required' || errCode === 'APPROVAL_REQUIRED') {
        toast.error(
          '签名未验签，正式执行需治理审批',
          approvalId
            ? `审批单 ${String(approvalId).slice(0, 12)}…（本机试跑已带 trial；或到 Skill 详情完成验签）`
            : '请到 Skill 详情完成签名验签后再试',
        );
      } else if (st === 'completed') {
        const rev = await fetchQualityReview({
          input: payload,
          output: normalized.output,
          status: st,
          execution_id: runId || undefined,
          embedded: (res as any)?.quality_review || null,
        });
        if (rev) setResult((prev) => (prev ? { ...prev, quality_review: rev } : prev));
        toastForReview(rev);
      }

      if (runId && shouldOpenSkillFlow(st)) {
        setFlowFullscreen(true);
      }

      if (autoSmoke && !isSkillRunInFlight(st)) {
        try {
          const smoke = await diagnosticsApi.runE2ESmoke({
            tenant_id: 'ops_smoke',
            actor_id: 'admin',
            agent_model: 'deepseek-reasoner',
          });
          toast.success(smoke?.ok ? '全链路冒烟通过' : '全链路冒烟失败');
        } catch (e: any) {
          toast.error('全链路冒烟失败', String(e?.message || 'unknown'));
        }
      }
    } catch (error: any) {
      toastGateError(error, '执行失败');
      setResult({ status: 'error', error: error.message || 'Unknown error' });
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setResult(null);
    setInputText('');
    setFlowFullscreen(false);
    setOutputFullscreen(false);
    setQualityReview(null);
    onClose();
  };

  const handleEditSop = () => {
    setFlowFullscreen(false);
    setOutputFullscreen(false);
    onEditSop?.();
  };

  const resultOutputText = result ? outputAsText(result.output) : '';

  const handleRerunSameCase = () => {
    setPostFixReady(false);
    setFlowFullscreen(true);
    // Always rebuild compact overlay — never reuse long stale backend overlay.
    const overlay = buildFailConstraintOverlay(qualityReview?.issues);
    const next = appendFailConstraintOverlay(inputText, overlay);
    if (next !== inputText) setInputText(next);
    if (overlay) toast.info('一键修复 → 同一用例重跑', '已叠加精简失败点约束');
    void handleExecute({ preserveFlow: true, inputOverride: next });
  };

  const handleApplyQualityFix = async (issueCodes: string[]) => {
    if (!skill?.id || !issueCodes.length) return;
    try {
      const { skillApi } = await import('../../services');
      const res = await skillApi.applyQualityFix(skill.id, { issue_codes: issueCodes });
      const applied = res?.applied?.length || 0;
      const skipped = res?.skipped?.length || 0;
      const paths = Array.isArray((res as any)?.paths) ? (res as any).paths.length : 0;
      if (res?.status === 'applied' && applied > 0) {
        setPostFixReady(true);
        toast.success(
          `已写入 ${applied} 类铁律${paths > 1 ? `（${paths} 个 SKILL.md）` : ''}`,
          '请点「一键修复 → 同一用例重跑」验证',
        );
      } else if (res?.status === 'noop' || skipped > 0) {
        setPostFixReady(true);
        toast.info(res?.message || '所选铁律已在 SOP 中；仍建议重跑对照');
      } else {
        toast.warning(res?.message || res?.error || '未写入任何铁律');
      }
    } catch (e: any) {
      toastGateError(e, '一键修复 SOP 失败');
    }
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={`执行 Skill: ${skill?.name || ''}`}
      width={980}
      footer={
        <>
          <Button variant="secondary" onClick={handleClose} disabled={loading}>
            关闭
          </Button>
          <Button variant="primary" onClick={handleExecute} loading={loading}>
            执行
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <Textarea
            label="输入（JSON 或文本）"
            rows={12}
            value={inputText}
            onChange={(e: any) => setInputText(e.target.value)}
            placeholder='点右侧「填入」加载测试用例，或直接输入 JSON / 文本'
          />
          <label className="mt-3 flex items-center gap-2 text-sm text-gray-400">
            <input type="checkbox" checked={autoSmoke} onChange={(e) => setAutoSmoke(e.target.checked)} />
            执行后自动运行全链路冒烟（会创建/清理资源）
          </label>
        </div>
        <div className="border border-dark-border rounded-lg bg-dark-card p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-medium text-gray-200">使用说明 / 示例</div>
            <div className="text-xs text-gray-500">{helpLoading ? '加载中...' : ''}</div>
          </div>
          {helpMarkdown ? (
            <div className="text-xs text-gray-300 whitespace-pre-wrap leading-relaxed mb-3">
              {helpMarkdown}
            </div>
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
                  title="用 LLM 生成冒烟用例；抄 schema 说明或过薄会回退启发式，且回退不会写入 SKILL.md"
                >
                  ✨ LLM 生成
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  loading={llmGenerating}
                  disabled={loading || llmGenerating}
                  onClick={() => handleGenerateLlmExamples(true)}
                  title="仅当判定为 LLM 成功时写入 SKILL.md；启发式回退不会覆盖已有用例"
                >
                  生成并保存
                </Button>
              </div>
              <div className="flex flex-col gap-2">
                {examples.map((ex, idx) => (
                  <div key={idx} className="flex items-center justify-between gap-2">
                    <div className="text-xs text-gray-300 truncate">{ex.title}</div>
                    <div className="flex gap-2">
                      <Button variant="secondary" onClick={() => setInputText(ex.content)} disabled={loading}>
                        填入
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={async () => {
                          try {
                            await navigator.clipboard.writeText(ex.content);
                            toast.success('已复制');
                          } catch {
                            toast.error('复制失败');
                          }
                        }}
                        disabled={loading}
                      >
                        复制
                      </Button>
                    </div>
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

      {result && (
        <div className="mt-4">
          <ExecuteResultPanel
            result={result as any}
            loading={loading || isSkillRunInFlight(result.status)}
            qualityReview={qualityReview}
            qualityReviewLoading={qualityReviewLoading}
            outputSchema={outputSchema ?? skill?.output_schema ?? null}
            onOpenFlow={result.run_id ? () => setFlowFullscreen(true) : undefined}
            onOpenOutput={resultOutputText ? () => setOutputFullscreen(true) : undefined}
            onEditSop={onEditSop ? handleEditSop : undefined}
            onApplyQualityFix={handleApplyQualityFix}
            fixApplied={postFixReady}
            onRerunSameCase={handleRerunSameCase}
            rerunLoading={loading}
          />
        </div>
      )}

      <ExecuteFlowFullscreen
        open={!!(flowFullscreen && result?.run_id)}
        runId={String(result?.run_id || '')}
        title={`执行流程 · ${skill?.name || 'Skill'}`}
        verdict={displayVerdict}
        status={result?.status}
        running={isSkillRunInFlight(String(result?.status || ''))}
        onClose={() => setFlowFullscreen(false)}
        footer={
          result && displayVerdict ? (
            <div className="space-y-2">
              <RunVerdictBanner verdict={displayVerdict} />
              <ExecutionQualityReviewPanel
                review={qualityReview}
                loading={qualityReviewLoading}
                persistKey="core-skill-exec"
                onEditSop={onEditSop ? handleEditSop : undefined}
                onApplyQualityFix={handleApplyQualityFix}
                fixApplied={postFixReady}
                onRerunSameCase={handleRerunSameCase}
                rerunLoading={loading}
              />
              {resultOutputText ? (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => {
                    setFlowFullscreen(false);
                    setOutputFullscreen(true);
                  }}
                >
                  📄 全屏查看产出
                </Button>
              ) : null}
            </div>
          ) : null
        }
      />

      <ExecuteOutputFullscreen
        open={!!(outputFullscreen && resultOutputText)}
        title={`产出 · ${skill?.name || 'Skill'}`}
        text={resultOutputText}
        raw={result?.output}
        schema={outputSchema ?? skill?.output_schema ?? null}
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
  );
};

export default ExecuteSkillModal;
