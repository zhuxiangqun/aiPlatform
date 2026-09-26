import React from 'react';
import { Button } from '../ui';
import {
  RunVerdictBanner,
  VERDICT_BADGE_CLASS,
  deriveRunVerdict,
  outputAsText,
  type RunVerdict,
} from './runVerdict';
import { ArtifactDownloadBar, skillOutputDisplayText } from './artifactDownloads';
import { coerceSkillEnvelope } from './artifactDownloads';

function coerceForRender(raw: unknown): unknown {
  return coerceSkillEnvelope(raw);
}

export type ExecuteResultLike = {
  status?: string;
  success?: boolean;
  output?: unknown;
  error?: unknown;
  error_message?: string;
  error_detail?: any;
  duration_ms?: number;
  latency?: number;
  run_id?: string;
  execution_id?: string;
  tokens?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
};

type Props = {
  result: ExecuteResultLike;
  /** Optional custom output renderer (e.g. StructuredSkillOutput). */
  renderOutput?: (text: string, raw: unknown) => React.ReactNode;
  onOpenFlow?: () => void;
  loading?: boolean;
  /** Extra blocks under the banner (HITL, downloads…). */
  children?: React.ReactNode;
  title?: string;
};

function normalizeStatus(result: ExecuteResultLike): string {
  if (result.status) return String(result.status);
  if (result.success === false) return 'failed';
  if (result.success === true) return 'completed';
  return '';
}

function pickError(result: ExecuteResultLike): unknown {
  return (
    result.error_message ||
    result.error ||
    (result.error_detail?.message ? result.error_detail : null) ||
    null
  );
}

export function useExecuteVerdict(result: ExecuteResultLike | null, opts?: { awaiting?: boolean; awaitSummary?: string }): RunVerdict | null {
  if (!result) return null;
  const status = normalizeStatus(result);
  const outputText = outputAsText(result.output);
  return deriveRunVerdict({
    status,
    error: pickError(result),
    outputText,
    awaiting: opts?.awaiting,
    awaitSummary: opts?.awaitSummary,
  });
}

const ExecuteResultPanel: React.FC<Props> = ({
  result,
  renderOutput,
  onOpenFlow,
  loading,
  children,
  title = '执行结果',
}) => {
  const status = normalizeStatus(result);
  const outputText = skillOutputDisplayText(result.output) || outputAsText(result.output);
  const err = pickError(result);
  const verdict = deriveRunVerdict({ status, error: err, outputText });
  const duration = result.duration_ms ?? (result.latency != null ? Math.round(result.latency) : undefined);
  const runId = result.run_id || result.execution_id;

  return (
    <div className="mt-4 p-4 rounded-lg border border-dark-border bg-dark-bg">
      <div className="mb-3">
        <RunVerdictBanner verdict={verdict} />
      </div>
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <span className="text-sm font-medium text-gray-100">{title}</span>
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-0.5 rounded ${VERDICT_BADGE_CLASS[verdict.tone]}`} title={status}>
            {verdict.label}
          </span>
          {status ? <span className="text-[10px] text-gray-500 font-mono">{status}</span> : null}
        </div>
        {result.tokens && (
          <span className="text-xs text-gray-400 ml-3">
            Token: {result.tokens.total_tokens?.toLocaleString() || '-'}
            <span className="text-gray-500 ml-1">
              (Prompt {result.tokens.prompt_tokens?.toLocaleString() || '-'} + Output{' '}
              {result.tokens.completion_tokens?.toLocaleString() || '-'})
            </span>
          </span>
        )}
        {duration != null && (
          <span className="text-xs text-gray-500 ml-3">⏱ {(duration / 1000).toFixed(1)}s</span>
        )}
      </div>

      {children}
      <ArtifactDownloadBar raw={result.output} />

      {err ? (
        <pre className="mb-2 text-xs text-red-200/90 overflow-auto max-h-40 bg-red-950/20 border border-red-900/40 rounded-lg p-3 whitespace-pre-wrap break-words">
          {String(
            typeof err === 'string'
              ? err
              : (err as any)?.message || JSON.stringify(err, null, 2),
          )}
        </pre>
      ) : null}

      {outputText ? (
        renderOutput ? (
          renderOutput(outputText, coerceForRender(result.output))
        ) : (
          <pre className="text-xs text-gray-300 overflow-auto max-h-80 bg-dark-card border border-dark-border rounded-lg p-3 whitespace-pre-wrap break-words">
            {outputText}
          </pre>
        )
      ) : null}

      {runId && (
        <div className="mt-3 flex items-center justify-between gap-2 flex-wrap">
          <div className="text-xs text-gray-400 break-all">run_id: {runId}</div>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(String(runId));
                } catch {
                  /* ignore */
                }
              }}
              disabled={loading}
            >
              复制 ID
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                window.open(
                  `/diagnostics/links?execution_id=${encodeURIComponent(String(runId))}&include_spans=true`,
                  '_blank',
                  'noopener,noreferrer',
                );
              }}
              disabled={loading}
            >
              查看诊断详情
            </Button>
          </div>
        </div>
      )}

      {runId && onOpenFlow && (
        <div className="mt-3">
          <Button variant="primary" onClick={onOpenFlow} disabled={loading}>
            ▶ 查看执行流程（全屏）
          </Button>
        </div>
      )}
    </div>
  );
};

export default ExecuteResultPanel;
