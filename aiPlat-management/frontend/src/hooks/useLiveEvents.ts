import { useEffect, useRef, useState, useCallback } from 'react';

export interface LiveEvent {
  id?: string;
  trace_id?: string;
  span_id?: string;
  parent_span_id?: string;
  run_id?: string;
  kind?: string;
  name?: string;
  status?: string;
  target_type?: string;
  target_id?: string;
  start_time?: number;
  end_time?: number;
  duration_ms?: number;
  args_json?: string;
  result_json?: string;
  args?: Record<string, unknown>;
  result?: Record<string, unknown>;
  error?: string;
  type?: string;
  input_tokens?: number;
  output_tokens?: number;
  cost?: number;
}

const POLL_BASE_MS = 1500;
const POLL_MAX_MS = 15000;
const FETCH_TIMEOUT_MS = 8000;
const TERMINAL = new Set(['completed', 'success', 'succeeded', 'failed', 'error', 'cancelled', 'canceled', 'timeout', 'done']);

function isControlMessage(data: LiveEvent): boolean {
  return !data.kind && !data.name;
}

function isTerminalStatus(st: string): boolean {
  return Boolean(st) && TERMINAL.has(st) && st !== 'running' && st !== 'accepted' && st !== 'pending';
}

async function fetchJson(
  url: string,
  signal?: AbortSignal,
): Promise<{ ok: boolean; body: any }> {
  const res = await fetch(url, { signal });
  if (!res.ok) return { ok: false, body: null };
  const body = await res.json();
  return { ok: true, body };
}

async function fetchSyscallEvents(runId: string, signal?: AbortSignal): Promise<LiveEvent[]> {
  const { ok, body } = await fetchJson(
    `/api/core/syscalls/events?run_id=${encodeURIComponent(runId)}&limit=500`,
    signal,
  );
  if (!ok) return [];
  return (body?.items || body?.events || []) as LiveEvent[];
}

async function fetchRunStatus(
  runId: string,
  signal?: AbortSignal,
): Promise<{ status: string; notFound: boolean; error?: string }> {
  const res = await fetch(
    `/api/core/executions/${encodeURIComponent(runId)}/status`,
    { signal },
  );
  if (res.status === 404) return { status: '', notFound: true };
  if (!res.ok) return { status: '', notFound: false };
  const body = await res.json();
  if (body?.not_found === true) return { status: '', notFound: true };
  const err = body?.error != null ? String(body.error) : undefined;
  return { status: String(body?.status || '').toLowerCase(), notFound: false, error: err };
}

export function useLiveEvents(runId: string | null) {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [status, setStatus] = useState<'disconnected' | 'connecting' | 'streaming' | 'done' | 'error'>('disconnected');
  const [error, setError] = useState<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);
  const seenIdsRef = useRef<Set<string>>(new Set());
  const doneRef = useRef(false);
  const eventCountRef = useRef(0);
  const pollInFlightRef = useRef(false);
  const pollAbortRef = useRef<AbortController | null>(null);
  const backoffMsRef = useRef(POLL_BASE_MS);
  const consecutiveFailRef = useRef(0);

  const ingestMany = useCallback((items: LiveEvent[]) => {
    const fresh: LiveEvent[] = [];
    for (const data of items) {
      if (!data || typeof data !== 'object') continue;
      if (isControlMessage(data)) continue;
      const eid = data.id || (data.span_id && data.name ? `${data.span_id}::${data.name}::${data.status || ''}` : '');
      if (eid) {
        if (seenIdsRef.current.has(eid)) continue;
        seenIdsRef.current.add(eid);
      }
      fresh.push(data);
    }
    if (fresh.length === 0) return;
    eventCountRef.current += fresh.length;
    setEvents(prev => [...prev, ...fresh]);
  }, []);

  useEffect(() => {
    if (!runId) {
      setEvents([]);
      setStatus('disconnected');
      seenIdsRef.current = new Set();
      doneRef.current = false;
      eventCountRef.current = 0;
      return;
    }

    setEvents([]);
    setStatus('connecting');
    setError(null);
    seenIdsRef.current = new Set();
    doneRef.current = false;
    eventCountRef.current = 0;
    pollInFlightRef.current = false;
    backoffMsRef.current = POLL_BASE_MS;
    consecutiveFailRef.current = 0;
    let cancelled = false;
    let pollTimer: number | null = null;

    const abortPoll = () => {
      if (pollAbortRef.current) {
        try { pollAbortRef.current.abort(); } catch { /* ignore */ }
        pollAbortRef.current = null;
      }
    };

    const markDone = async () => {
      if (doneRef.current) return;
      doneRef.current = true;
      abortPoll();
      if (pollTimer != null) {
        window.clearTimeout(pollTimer);
        pollTimer = null;
      }
      // Final hydrate — SSE type:done can race ahead of event payloads / proxy flush
      try {
        const ctrl = new AbortController();
        const kill = window.setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
        try {
          const items = await fetchSyscallEvents(runId, ctrl.signal);
          if (!cancelled) ingestMany(items);
        } finally {
          window.clearTimeout(kill);
        }
      } catch { /* best-effort */ }
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
      if (!cancelled) setStatus('done');
    };

    const schedulePoll = (delayMs?: number) => {
      if (cancelled || doneRef.current) return;
      if (pollTimer != null) window.clearTimeout(pollTimer);
      const wait = delayMs ?? backoffMsRef.current;
      pollTimer = window.setTimeout(() => { void runPoll(); }, wait);
    };

    const runPoll = async () => {
      if (cancelled || doneRef.current) return;
      // Single-flight: never stack polls when previous is still pending
      if (pollInFlightRef.current) {
        schedulePoll(Math.max(backoffMsRef.current, 500));
        return;
      }
      pollInFlightRef.current = true;
      abortPoll(); // cancel any stray prior request
      const ctrl = new AbortController();
      pollAbortRef.current = ctrl;
      const kill = window.setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
      let failed = false;
      try {
        const items = await fetchSyscallEvents(runId, ctrl.signal);
        if (cancelled || doneRef.current) return;
        ingestMany(items);
        const { status: st, notFound, error: stErr } = await fetchRunStatus(runId, ctrl.signal);
        if (cancelled || doneRef.current) return;
        if (notFound) {
          // Stream/queue: row may appear shortly after run_id is returned.
          consecutiveFailRef.current += 1;
          if (consecutiveFailRef.current >= 40) {
            setError(`执行记录不存在（${runId}），已停止轮询`);
            await markDone();
            return;
          }
          failed = true;
          backoffMsRef.current = Math.min(POLL_MAX_MS, POLL_BASE_MS * 2);
        } else if (isTerminalStatus(st)) {
          await markDone();
          return;
        } else {
          consecutiveFailRef.current = 0;
          backoffMsRef.current = POLL_BASE_MS;
          if (st === 'queued' || st === 'pending' || (stErr && /session_locked/i.test(stErr))) {
            setError(stErr || 'session_locked');
          }
        }
      } catch {
        failed = true;
        consecutiveFailRef.current += 1;
        // Exponential backoff on error / timeout / abort: 1.5s → 3s → 6s → 12s → 15s
        backoffMsRef.current = Math.min(
          POLL_MAX_MS,
          POLL_BASE_MS * Math.pow(2, Math.min(consecutiveFailRef.current, 4)),
        );
        // After many failures, surface error but keep soft-polling (core may recover)
        if (consecutiveFailRef.current >= 5 && !cancelled && !doneRef.current) {
          setError(`事件轮询失败（退避 ${Math.round(backoffMsRef.current / 1000)}s），后端可能过载`);
        }
      } finally {
        window.clearTimeout(kill);
        if (pollAbortRef.current === ctrl) pollAbortRef.current = null;
        pollInFlightRef.current = false;
      }
      if (!cancelled && !doneRef.current) {
        schedulePoll(failed ? backoffMsRef.current : POLL_BASE_MS);
      }
    };

    // Immediate snapshot (don't wait for SSE / first poll)
    (async () => {
      try {
        const ctrl = new AbortController();
        const kill = window.setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
        try {
          const items = await fetchSyscallEvents(runId, ctrl.signal);
          if (cancelled) return;
          ingestMany(items);
          const { status: st, notFound, error: stErr } = await fetchRunStatus(runId, ctrl.signal);
          if (cancelled) return;
          if (notFound) {
            // Stream/queue often connects before skill_execution row exists — keep waiting.
            if (!doneRef.current) setStatus('streaming');
          } else if (isTerminalStatus(st)) {
            await markDone();
          } else if (!doneRef.current) {
            setStatus('streaming');
            if (st === 'queued' || st === 'pending' || (stErr && /session_locked/i.test(stErr))) {
              setError(stErr || 'session_locked');
            }
          }
        } finally {
          window.clearTimeout(kill);
        }
      } catch {
        if (!cancelled && !doneRef.current) setStatus('streaming');
      }
    })();

    const url = `/api/core/observation/runs/${encodeURIComponent(runId)}/stream`;
    const es = new EventSource(url);
    sourceRef.current = es;

    es.onopen = () => {
      if (!cancelled && !doneRef.current) {
        setStatus('streaming');
        setError(null);
        // SSE connected — slow poll as safety net only
        backoffMsRef.current = Math.max(POLL_BASE_MS * 2, 3000);
      }
    };

    es.onmessage = (e) => {
      if (cancelled || doneRef.current) return;
      try {
        const data = JSON.parse(e.data) as LiveEvent;
        if (data.type === 'done') {
          // Guard: backend used to emit done when syscall_events was still empty
          // while the agent thread was starting — that froze the viewer empty.
          void (async () => {
            if (cancelled || doneRef.current) return;
            let st = '';
            try {
              const r = await fetchRunStatus(runId);
              st = r.status;
              if (r.notFound) {
                // Do not freeze as done — background skill/agent may still be starting.
                try { es.close(); } catch { /* ignore */ }
                if (sourceRef.current === es) sourceRef.current = null;
                setStatus('streaming');
                setError(null);
                backoffMsRef.current = POLL_BASE_MS;
                schedulePoll(0);
                return;
              }
            } catch { /* ignore */ }
            if (cancelled || doneRef.current) return;
            if (!isTerminalStatus(st)) {
              try { es.close(); } catch { /* ignore */ }
              if (sourceRef.current === es) sourceRef.current = null;
              setStatus('streaming');
              setError(null);
              backoffMsRef.current = POLL_BASE_MS;
              schedulePoll(0);
              return;
            }
            await markDone();
          })();
          return;
        }
        if (data.type === 'heartbeat') return;
        if (isControlMessage(data)) return;
        ingestMany([data]);
        consecutiveFailRef.current = 0;
      } catch {
        // skip malformed
      }
    };

    es.onerror = () => {
      if (cancelled || doneRef.current) return;
      // Wrong MIME (octet-stream via broken proxy) aborts EventSource; stop retrying and rely on poll.
      try { es.close(); } catch { /* ignore */ }
      if (sourceRef.current === es) sourceRef.current = null;
      if (eventCountRef.current === 0) {
        setError('SSE 不可用，已改用轮询加载事件');
      }
      if (!doneRef.current) {
        setStatus('streaming');
        // Tighten poll a bit when SSE died, but still single-flight + backoff
        backoffMsRef.current = POLL_BASE_MS;
        schedulePoll(0);
      }
    };

    // Start poll loop (single-flight, never setInterval)
    schedulePoll(POLL_BASE_MS);

    return () => {
      cancelled = true;
      if (pollTimer != null) window.clearTimeout(pollTimer);
      abortPoll();
      pollInFlightRef.current = false;
      es.close();
      sourceRef.current = null;
    };
  }, [runId, ingestMany]);

  const close = () => {
    if (sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
    }
    if (pollAbortRef.current) {
      try { pollAbortRef.current.abort(); } catch { /* ignore */ }
      pollAbortRef.current = null;
    }
    doneRef.current = true;
    setStatus('done');
  };

  return { events, status, error, close };
}
