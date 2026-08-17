import React, { useEffect, useState, useCallback } from 'react';
import { RefreshCw, Activity, ChevronDown, ChevronRight } from 'lucide-react';
import { runApi, type RunEvent } from '../../services';

interface RunEventTimelineProps {
  runId: string;
  maxHeight?: string;
}

const EVENT_COLORS: Record<string, string> = {
  run_started: 'text-green-400',
  run_completed: 'text-green-400',
  run_failed: 'text-red-400',
  stage_started: 'text-blue-400',
  stage_completed: 'text-blue-400',
  stage_failed: 'text-red-400',
  tool_start: 'text-yellow-400',
  tool_end: 'text-yellow-400',
  approval_requested: 'text-purple-400',
  approval_resolved: 'text-purple-400',
  hitl_paused: 'text-orange-400',
  hitl_resumed: 'text-orange-400',
  skill_start: 'text-cyan-400',
  skill_end: 'text-cyan-400',
  llm_start: 'text-indigo-400',
  llm_end: 'text-indigo-400',
  error: 'text-red-500',
};

function eventColor(type: string): string {
  if (EVENT_COLORS[type]) return EVENT_COLORS[type];
  // fallback: color by prefix (stage_* / tool_* / run_*)
  const prefix = type.split('_')[0];
  return EVENT_COLORS[`${prefix}_started`] || 'text-gray-300';
}

function fmtTs(ts?: number | null): string {
  if (!ts) return '-';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('zh-CN', { hour12: false });
}

function payloadSummary(payload?: Record<string, unknown> | null): string {
  if (!payload || typeof payload !== 'object') return '';
  const parts: string[] = [];
  for (const k of ['stage_id', 'stage', 'skill', 'tool', 'status', 'agent', 'phase']) {
    const v = (payload as Record<string, unknown>)[k];
    if (v != null && typeof v === 'string' && v.length < 120) parts.push(`${k}=${v}`);
  }
  return parts.join(' · ');
}

export const RunEventTimeline: React.FC<RunEventTimelineProps> = ({ runId, maxHeight = '260px' }) => {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await runApi.listEvents(runId, { limit: 500 });
      const items = Array.isArray((res as { items?: RunEvent[] }).items)
        ? (res as { items: RunEvent[] }).items
        : Array.isArray((res as { events?: RunEvent[] }).events)
          ? (res as { events: RunEvent[] }).events
          : [];
      setEvents(items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => { load(); }, [load]);

  const toggle = (seq: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(seq)) next.delete(seq); else next.add(seq);
      return next;
    });
  };

  return (
    <div className="mt-2 rounded border border-dark-border bg-dark-card/60">
      <div className="flex items-center justify-between px-2 py-1.5 border-b border-dark-border">
        <span className="text-[11px] text-gray-400 flex items-center gap-1">
          <Activity className="w-3 h-3" /> 事件回放（{events.length}）
        </span>
        <button
          onClick={load}
          className="text-[10px] text-gray-500 hover:text-gray-300 flex items-center gap-1"
          title="刷新事件"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>
      <div className="overflow-y-auto" style={{ maxHeight }}>
        {loading && events.length === 0 ? (
          <div className="p-3 text-[11px] text-gray-500">加载事件中…</div>
        ) : error ? (
          <div className="p-3 text-[11px] text-red-400">加载失败: {error}</div>
        ) : events.length === 0 ? (
          <div className="p-3 text-[11px] text-gray-500">暂无事件记录</div>
        ) : (
          <ul className="divide-y divide-dark-border/60">
            {events.map((ev) => (
              <li key={ev.seq} className="px-2 py-1 hover:bg-dark-hover/20">
                <button onClick={() => toggle(ev.seq)} className="w-full text-left flex items-start gap-2">
                  <span className="text-[10px] text-gray-600 font-mono mt-0.5 shrink-0">{ev.seq}</span>
                  <span className={`text-[11px] font-mono shrink-0 ${eventColor(ev.type)}`}>{ev.type}</span>
                  <span className="text-[10px] text-gray-600 shrink-0 mt-0.5">{fmtTs(ev.created_at)}</span>
                  <span className="text-[11px] text-gray-500 truncate flex-1">{payloadSummary(ev.payload)}</span>
                  {expanded.has(ev.seq)
                    ? <ChevronDown className="w-3 h-3 text-gray-600 shrink-0 mt-0.5" />
                    : <ChevronRight className="w-3 h-3 text-gray-600 shrink-0 mt-0.5" />}
                </button>
                {expanded.has(ev.seq) && ev.payload && (
                  <pre className="mt-1 ml-6 p-2 rounded bg-dark-hover/20 text-[10px] text-gray-400 whitespace-pre-wrap overflow-x-auto max-h-56 overflow-y-auto">
                    {JSON.stringify(ev.payload, null, 2)}
                  </pre>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

export default RunEventTimeline;
