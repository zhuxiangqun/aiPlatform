import { useEffect, useRef, useState } from 'react';

export interface LiveEvent {
  trace_id?: string;
  span_id?: string;
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
  error?: string;
  type?: string;  // 'connected' | 'heartbeat'
  input_tokens?: number;
  output_tokens?: number;
  cost?: number;
}

export function useLiveEvents(runId: string | null) {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [status, setStatus] = useState<'disconnected' | 'connecting' | 'streaming' | 'done' | 'error'>('disconnected');
  const [error, setError] = useState<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!runId) {
      setEvents([]);
      setStatus('disconnected');
      return;
    }

    setEvents([]);
    setStatus('connecting');
    setError(null);

    const url = `/api/core/observation/runs/${encodeURIComponent(runId)}/stream`;
    const es = new EventSource(url);
    sourceRef.current = es;

    es.onopen = () => {
      setStatus('streaming');
    };

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        // Close connection gracefully on done signal
        if (data.type === 'done') {
          es.close();
          setStatus('done');
          return;
        }
        // Filter out all control messages (no kind/name = not a business event)
        if (!data.kind && !data.name) return;
        setEvents(prev => [...prev, data]);
      } catch {
        // skip malformed events
      }
    };

    es.onerror = () => {
      setStatus('error');
      setError('SSE connection error');
    };

    return () => {
      es.close();
      sourceRef.current = null;
    };
  }, [runId]);

  const close = () => {
    if (sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
      setStatus('done');
    }
  };

  return { events, status, error, close };
}
