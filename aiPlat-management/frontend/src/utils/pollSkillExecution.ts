/**
 * Poll Skill execution until terminal status (stream mode).
 * Prefer /executions/{id}/status; fall back to syscall events.
 *
 * Important: frontend wait must be ≥ skill timeout (e.g. requirement_analysis=480s).
 * Also: stream runs often return status=unknown + not_found until run_start is written —
 * that must NOT be treated as a terminal failure.
 */

const IN_FLIGHT = new Set(['running', 'accepted', 'queued', 'started', 'pending']);
const KEEP_POLLING = new Set([...IN_FLIGHT, 'unknown', '']);

function resolveMaxAttempts(opts?: {
  maxAttempts?: number;
  timeoutSec?: number;
  intervalMs?: number;
}): { maxAttempts: number; timeoutSec: number; intervalMs: number } {
  const intervalMs = Math.max(200, opts?.intervalMs ?? 1000);
  const timeoutSec = Math.max(
    60,
    Number(opts?.timeoutSec || 0) > 0 ? Number(opts?.timeoutSec) : 360,
  );
  const computed = Math.ceil((timeoutSec * 1.15) / (intervalMs / 1000));
  const maxAttempts = opts?.maxAttempts ?? Math.max(computed, 60);
  return { maxAttempts, timeoutSec, intervalMs };
}

function mapTerminalStatus(raw: string): string {
  const st = String(raw || '').toLowerCase();
  if (st === 'ok' || st === 'success' || st === 'done') return 'completed';
  if (st === 'canceled') return 'cancelled';
  return st;
}

export async function pollSkillExecutionUntilDone(
  runId: string,
  opts?: {
    maxAttempts?: number;
    /** Skill / server timeout in seconds (from metadata.timeout). */
    timeoutSec?: number;
    intervalMs?: number;
    isStopped?: () => boolean;
    onTick?: (attempt: number, info: { elapsedSec: number; timeoutSec: number }) => void;
  },
): Promise<{
  status: string;
  output?: unknown;
  input?: unknown;
  error?: unknown;
  duration_ms?: number;
  quality_review?: unknown;
}> {
  const { maxAttempts, timeoutSec, intervalMs } = resolveMaxAttempts(opts);
  let attempts = 0;

  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

  while (attempts < maxAttempts) {
    if (opts?.isStopped?.()) {
      return { status: 'cancelled' };
    }
    attempts += 1;
    const elapsedSec = Math.round((attempts * intervalMs) / 1000);
    opts?.onTick?.(attempts, { elapsedSec, timeoutSec });

    try {
      const resp = await fetch(`/api/core/executions/${encodeURIComponent(runId)}/status`);
      if (resp.ok) {
        const sData = await resp.json();
        const newStatus = String(sData?.status || '').toLowerCase();
        const notFound = Boolean(sData?.not_found);
        // Stream race: run_id returned before run_start / skill_executions row exists
        if (notFound || KEEP_POLLING.has(newStatus)) {
          /* keep polling */
        } else if (newStatus) {
          return {
            status: mapTerminalStatus(newStatus),
            output: sData?.output,
            input: sData?.input,
            error: sData?.error,
            duration_ms: sData?.duration_ms,
            quality_review: sData?.quality_review,
          };
        }
      }
    } catch {
      /* keep polling */
    }

    try {
      const resp = await fetch(`/api/core/syscalls/events?run_id=${encodeURIComponent(runId)}&limit=20`);
      const data = await resp.json();
      const items = data?.items || data?.events || [];
      const done = items.find(
        (e: any) => (e.status === 'success' || e.status === 'ok') && e.kind === 'skill' && e.result,
      );
      if (done) {
        return {
          status: 'completed',
          output: done.result?.output || done.result,
          duration_ms: done.duration_ms,
        };
      }
      if (items.some((e: any) => e.status === 'failed' || e.status === 'error' || e.status === 'timeout')) {
        const failed = items.find(
          (e: any) => e.status === 'failed' || e.status === 'error' || e.status === 'timeout',
        );
        return {
          status: failed?.status === 'timeout' ? 'timeout' : 'failed',
          error: failed?.error || (failed?.status === 'timeout' ? '执行超时' : '执行失败'),
        };
      }
    } catch {
      /* keep polling */
    }

    await sleep(intervalMs);
  }

  try {
    const resp = await fetch(`/api/core/executions/${encodeURIComponent(runId)}/status`);
    if (resp.ok) {
      const sData = await resp.json();
      const st = String(sData?.status || '').toLowerCase();
      const notFound = Boolean(sData?.not_found);
      if (notFound || KEEP_POLLING.has(st)) {
        return {
          status: 'timeout',
          error: `前端等待已超过约 ${timeoutSec}s，但服务端仍可能在运行（status=${st || 'unknown'}）。请打开诊断详情继续查看。`,
          output: sData?.output,
          input: sData?.input,
          duration_ms: sData?.duration_ms,
          quality_review: sData?.quality_review,
        };
      }
      if (st) {
        return {
          status: mapTerminalStatus(st),
          output: sData?.output,
          input: sData?.input,
          error: sData?.error,
          duration_ms: sData?.duration_ms,
          quality_review: sData?.quality_review,
        };
      }
    }
  } catch {
    /* ignore */
  }

  return {
    status: 'timeout',
    error: `执行等待超时（约 ${timeoutSec}s）。若诊断里仍显示 running，说明前端先放弃了，不是 Skill 已失败。`,
  };
}
