/**
 * Poll Skill execution until terminal status (stream mode).
 * Prefer /executions/{id}/status; fall back to syscall events.
 */
export async function pollSkillExecutionUntilDone(
  runId: string,
  opts?: {
    maxAttempts?: number;
    intervalMs?: number;
    isStopped?: () => boolean;
    onTick?: (attempt: number) => void;
  },
): Promise<{ status: string; output?: unknown; error?: unknown; duration_ms?: number }> {
  const maxAttempts = opts?.maxAttempts ?? 180;
  const intervalMs = opts?.intervalMs ?? 1000;
  let attempts = 0;

  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

  while (attempts < maxAttempts) {
    if (opts?.isStopped?.()) {
      return { status: 'cancelled' };
    }
    attempts += 1;
    opts?.onTick?.(attempts);

    try {
      const resp = await fetch(`/api/core/executions/${encodeURIComponent(runId)}/status`);
      if (resp.ok) {
        const sData = await resp.json();
        const newStatus = String(sData?.status || '');
        if (newStatus && newStatus !== 'running' && newStatus !== 'accepted' && newStatus !== 'queued') {
          return {
            status: newStatus === 'ok' || newStatus === 'success' ? 'completed' : newStatus,
            output: sData?.output,
            error: sData?.error,
            duration_ms: sData?.duration_ms,
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
      if (items.some((e: any) => e.status === 'failed' || e.status === 'error')) {
        const failed = items.find((e: any) => e.status === 'failed' || e.status === 'error');
        return { status: 'failed', error: failed?.error || '执行失败' };
      }
    } catch {
      /* keep polling */
    }

    await sleep(intervalMs);
  }

  return { status: 'failed', error: '执行超时' };
}
