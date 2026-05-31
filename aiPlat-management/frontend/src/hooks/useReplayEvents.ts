import { useEffect, useRef, useState, useCallback } from 'react';

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
  type?: string;
  input_tokens?: number;
  output_tokens?: number;
  cost?: number;
}

interface ReplayState {
  events: LiveEvent[];
  currentIndex: number;
  visibleEvents: LiveEvent[];
  playing: boolean;
  speed: number; // events per second
  totalEvents: number;
  progress: number; // 0-100
  loading: boolean;
  error: string | null;
}

export function useReplayEvents(runId: string | null, maxEvents = 200) {
  const [state, setState] = useState<ReplayState>({
    events: [],
    currentIndex: 0,
    visibleEvents: [],
    playing: false,
    speed: 2,
    totalEvents: 0,
    progress: 0,
    loading: false,
    error: null,
  });
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch events from API
  const fetchEvents = useCallback(async () => {
    if (!runId) return;
    setState(prev => ({ ...prev, loading: true, error: null, events: [], visibleEvents: [], currentIndex: 0, progress: 0 }));
    try {
      const resp = await fetch(`/api/core/diagnostics/syscalls/core?run_id=${encodeURIComponent(runId)}&limit=${maxEvents}&offset=0`);
      const data = await resp.json();
      const items: LiveEvent[] = (data?.items || []).reverse(); // oldest first
      setState(prev => ({
        ...prev,
        events: items,
        totalEvents: items.length,
        visibleEvents: items.length > 0 ? [items[0]] : [],
        loading: false,
      }));
    } catch (e: any) {
      setState(prev => ({ ...prev, loading: false, error: e?.message || 'Failed to load events' }));
    }
  }, [runId, maxEvents]);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  // Advance logic
  const advance = useCallback(() => {
    setState(prev => {
      if (prev.events.length === 0) return prev;
      const nextIndex = prev.currentIndex + 1;
      if (nextIndex >= prev.events.length) {
        // Reached end → pause
        return { ...prev, playing: false };
      }
      return {
        ...prev,
        currentIndex: nextIndex,
        visibleEvents: prev.events.slice(0, nextIndex + 1),
        progress: ((nextIndex + 1) / prev.events.length) * 100,
      };
    });
  }, []);

  // Playback control
  useEffect(() => {
    if (state.playing && state.currentIndex < state.events.length - 1) {
      const interval = Math.max(100, 1000 / state.speed);
      timerRef.current = setInterval(advance, interval);
      return () => {
        if (timerRef.current) clearInterval(timerRef.current);
      };
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, [state.playing, state.speed, state.currentIndex, state.events.length, advance]);

  const play = useCallback(() => setState(prev => ({ ...prev, playing: true })), []);
  const pause = useCallback(() => setState(prev => ({ ...prev, playing: false })), []);
  const reset = useCallback(() => {
    setState(prev => ({
      ...prev,
      currentIndex: 0,
      visibleEvents: prev.events.length > 0 ? [prev.events[0]] : [],
      progress: prev.events.length > 0 ? 100 / prev.events.length : 0,
      playing: false,
    }));
  }, []);
  const setSpeed = useCallback((s: number) => setState(prev => ({ ...prev, speed: s })), []);

  return { ...state, play, pause, reset, setSpeed, refetch: fetchEvents };
}
