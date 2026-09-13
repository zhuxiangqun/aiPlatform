import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card, Progress } from '../ui';
import { Loader2, CheckCircle, XCircle } from 'lucide-react';

interface ProgressConfig {
  status_field?: string;
  poll_ms?: number;
  stages?: string[] | { status: string; label?: string }[];
  labels?: Record<string, string>;
  input?: Record<string, string>;
}

interface Props {
  config: ProgressConfig;
  onExecute: (skill: string, params: Record<string, any>) => Promise<any>;
  skill: string;
  stageInput?: Record<string, any>;
  onNext?: (result: any) => void;
  onComplete?: (result: any) => void;
}

/** HTTP/StatusResponse envelope values — never treat as business workflow status. */
const ENVELOPE_STATUS = new Set(['ok', 'error', 'success', '']);

const DONE_STATUS = new Set([
  'completed',
  'complete',
  'done',
  'processed',
  'ready',
  'succeeded',
  'success',
]);

const FAIL_STATUS = new Set(['failed', 'fail', 'error']);

function parseMaybeJson(v: any): any {
  if (typeof v !== 'string') return v;
  const s = v.trim();
  if (!s.startsWith('{') && !s.startsWith('[')) return v;
  try {
    return JSON.parse(s);
  } catch {
    return v;
  }
}

/** Prefer nested business status over API envelope `status: "ok"`. */
function extractBusinessStatus(res: any, statusField = 'status'): { status: string; nested: Record<string, any> } {
  if (typeof res === 'string') {
    const parsed = parseMaybeJson(res);
    if (parsed && typeof parsed === 'object') {
      return extractBusinessStatus(parsed, statusField);
    }
    return { status: String(res || ''), nested: {} };
  }
  if (!res || typeof res !== 'object') {
    return { status: '', nested: {} };
  }

  const replyObj = parseMaybeJson(res.reply);
  const nested =
    (res.result && typeof res.result === 'object' ? res.result : null) ||
    (replyObj && typeof replyObj === 'object' ? replyObj : null) ||
    {};

  const candidates = [
    nested?.[statusField],
    nested?.state,
    nested?.phase,
    replyObj && typeof replyObj === 'object' ? replyObj[statusField] : undefined,
    // Only use top-level status when it is NOT the HTTP envelope
    ENVELOPE_STATUS.has(String(res[statusField] ?? '').toLowerCase())
      ? undefined
      : res[statusField],
    res.state,
    res.phase,
  ];

  for (const c of candidates) {
    if (c !== undefined && c !== null && String(c).trim() !== '') {
      return { status: String(c).trim(), nested: nested as Record<string, any> };
    }
  }
  return { status: '', nested: nested as Record<string, any> };
}

export const ProgressPoller: React.FC<Props> = ({
  config,
  onExecute,
  skill,
  stageInput,
  onNext,
  onComplete,
}) => {
  const [status, setStatus] = useState('');
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const advancedRef = useRef(false);
  const inFlightRef = useRef(false);
  const advanceRef = useRef(onNext || onComplete);
  advanceRef.current = onNext || onComplete;

  const stages = config.stages || ['pending', 'processing', 'completed'];
  const pollMs = config.poll_ms || 3000;
  const labels = config.labels || {};
  const statusField = config.status_field || 'status';
  const inputKey = JSON.stringify({ ...(config.input || {}), ...(stageInput || {}) });

  const poll = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      setStatus((prev) => prev || 'analyzing');
      const params = { ...(config.input || {}), ...(stageInput || {}) };
      // Drop unresolved mustache placeholders
      for (const [k, v] of Object.entries(params)) {
        if (typeof v === 'string' && /^\{\{.+\}\}$/.test(v)) {
          delete params[k];
        }
      }
      const hasRef =
        Boolean(params.task_id) ||
        Boolean(params.video_path) ||
        Boolean(params.file_path) ||
        Boolean(params.local_path);
      if (!hasRef) {
        setError('缺少任务引用（task_id / video_path），无法轮询进度');
        setDone(true);
        return;
      }
      const res = await onExecute(skill, params);
      const { status: st, nested } = extractBusinessStatus(res, statusField);
      setStatus(st || 'processing');

      const statusList = Array.isArray(stages)
        ? stages.map((s: any) => (typeof s === 'string' ? s : s?.status)).filter(Boolean)
        : [];
      const idx = statusList.indexOf(st);
      if (idx >= 0 && statusList.length > 1) {
        setProgress(Math.round((idx / (statusList.length - 1)) * 100));
      } else if (DONE_STATUS.has(st.toLowerCase())) {
        setProgress(100);
      }

      const stLower = st.toLowerCase();
      if (DONE_STATUS.has(stLower)) {
        setDone(true);
        setProgress(100);
        if (!advancedRef.current) {
          advancedRef.current = true;
          const flat = {
            ...res,
            ...nested,
            task_id: nested?.task_id || res?.task_id || params.task_id,
            video_path:
              nested?.video_path ||
              nested?.file_path ||
              res?.video_path ||
              params.video_path ||
              params.file_path,
            status: st,
          };
          advanceRef.current?.(flat);
        }
      }
      if (FAIL_STATUS.has(stLower)) {
        setError(
          nested?.error_message ||
            nested?.error ||
            res?.error_message ||
            res?.error ||
            res?.detail ||
            '处理失败',
        );
        setDone(true);
      }
    } catch (e: any) {
      setError(e?.message || '轮询失败');
    } finally {
      inFlightRef.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- inputKey fingerprints config/stageInput
  }, [skill, inputKey, stages, onExecute, statusField]);

  useEffect(() => {
    if (done) return;
    poll();
    const timer = setInterval(poll, pollMs);
    return () => clearInterval(timer);
  }, [poll, done, pollMs]);

  const statusLabel = labels[status] || status || '处理中';

  return (
    <Card className="p-6 max-w-lg mx-auto">
      <h2 className="text-lg font-semibold mb-4 text-gray-100">处理进度</h2>
      <Progress value={progress} className="mb-4" />
      <div className="flex items-center gap-2 text-sm">
        {!done && <Loader2 className="w-4 h-4 animate-spin text-primary" />}
        {done && !error && <CheckCircle className="w-4 h-4 text-green-400" />}
        {error && <XCircle className="w-4 h-4 text-red-400" />}
        <span className={error ? 'text-red-400' : done ? 'text-green-400' : 'text-gray-300'}>
          {error || statusLabel}
        </span>
      </div>
    </Card>
  );
};
