import React from 'react';

export type RunVerdictTone = 'green' | 'red' | 'amber' | 'blue' | 'gray';
export type RunVerdictKind =
  | 'running'
  | 'success'
  | 'failed'
  | 'timeout'
  | 'awaiting'
  | 'partial'
  | 'unknown';

export type RunVerdict = {
  kind: RunVerdictKind;
  label: string;
  hint: string;
  tone: RunVerdictTone;
  ok: boolean | null;
};

export function deriveRunVerdict(opts: {
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

  if (!status || status === 'running' || status === 'accepted' || status === 'started') {
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
      hint: opts.awaitSummary || '已暂停，补一句确认后再继续；这时还不算最终成功。',
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
  if (status === 'partial') {
    return {
      kind: 'partial',
      label: '部分完成',
      hint: errStr || '有步骤未完全成功，请对照流程节点与输出核对。',
      tone: 'amber',
      ok: null,
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

export const VERDICT_TONE_CLASS: Record<RunVerdictTone, string> = {
  green: 'border-green-700/50 bg-green-950/35 text-green-100',
  red: 'border-red-700/50 bg-red-950/35 text-red-100',
  amber: 'border-amber-700/50 bg-amber-950/35 text-amber-100',
  blue: 'border-blue-700/50 bg-blue-950/35 text-blue-100',
  gray: 'border-gray-600/50 bg-gray-900/40 text-gray-200',
};

export const VERDICT_BADGE_CLASS: Record<RunVerdictTone, string> = {
  green: 'bg-green-900/50 text-green-300',
  red: 'bg-red-900/50 text-red-300',
  amber: 'bg-amber-900/50 text-amber-200',
  blue: 'bg-blue-900/50 text-blue-300',
  gray: 'bg-gray-800 text-gray-300',
};

export function RunVerdictBanner({ verdict }: { verdict: RunVerdict }) {
  return (
    <div className={`p-2.5 rounded-lg border text-sm transition-colors duration-500 ${VERDICT_TONE_CLASS[verdict.tone]}`}>
      <div className="font-medium text-gray-100/95">{verdict.label}</div>
      <div className="text-xs opacity-75 mt-1 leading-relaxed">{verdict.hint}</div>
    </div>
  );
}

/** Best-effort unwrap of nested {output|text|answer} envelopes to readable text. */
export function outputAsText(raw: unknown): string {
  let cur: unknown = raw;
  for (let depth = 0; depth < 8; depth++) {
    if (cur == null) return '';
    if (typeof cur === 'string') {
      const s = cur.trim();
      if (s.startsWith('{')) {
        try {
          const d = JSON.parse(s);
          if (d && typeof d === 'object') {
            cur = d;
            continue;
          }
        } catch {
          /* keep string */
        }
      }
      return s;
    }
    if (typeof cur === 'object') {
      const o = cur as Record<string, unknown>;
      if (typeof o.answer === 'string') {
        cur = o.answer;
        continue;
      }
      if (typeof o.text === 'string') {
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
      try {
        return JSON.stringify(cur, null, 2);
      } catch {
        return String(cur);
      }
    }
    return String(cur);
  }
  try {
    return JSON.stringify(cur, null, 2);
  } catch {
    return String(cur ?? '');
  }
}
