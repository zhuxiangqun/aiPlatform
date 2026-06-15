import React, { useEffect, useMemo, useState } from 'react';
import { diagnosticsApi } from '../../services';
import ExecutionViewer from '../ExecutionViewer/ExecutionViewer';
import type { ExecutionNode } from '../ExecutionViewer/types';

interface Props {
  runId: string;
}

interface SyscallEvent {
  id?: number;
  span_id?: string;
  parent_span_id?: string;
  kind?: string;
  name?: string;
  status?: string;
  duration_ms?: number;
  error?: string;
}

export const TraceFlowGraph: React.FC<Props> = ({ runId }) => {
  const [events, setEvents] = useState<SyscallEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    setError('');
    (async () => {
      try {
        const res = await diagnosticsApi.listSyscalls({ run_id: runId, limit: 200 });
        const list = (res as any).items || (res as any).events || [];
        setEvents(list);
        if (list.length === 0) setError('该执行未产生可追踪的事件');
      } catch { setError('获取执行流程失败'); }
      finally { setLoading(false); }
    })();
  }, [runId]);

  const nodes: ExecutionNode[] = useMemo(() => {
    if (!events.length) return [];
    // Build parent-child relationships: span_id → first event (keep first for parent lookup)
    const spanMap = new Map<string, SyscallEvent>();
    for (const e of events) {
      const sid = e.span_id;
      if (sid && !spanMap.has(sid)) spanMap.set(sid, e);
    }

    const seen = new Map<string, ExecutionNode>(); // dedup by span_id::name
    const result: ExecutionNode[] = [];

    for (let i = 0; i < events.length; i++) {
      const e = events[i];
      const kind = e.kind?.replace(/^sys_/, '') || 'default';
      const name = e.name || e.kind || 'unknown';
      const status = e.status === 'ok' ? 'completed' as const
        : e.status === 'error' ? 'failed' as const : 'idle' as const;
      const parentSid = (e as any).parent_span_id || '';
      const parent = parentSid ? spanMap.get(parentSid) : null;

      const nodeId = (e.span_id && name) ? `${e.span_id}::${name}` : `ev_${e.id || i}`;

      // Dedup: merge status updates for same span_id::name (keep latest non-idle)
      const existing = seen.get(nodeId);
      if (existing) {
        if (status !== 'idle') {
          existing.status = status;
          existing.duration = e.duration_ms || existing.duration;
        }
        continue; // reuse existing node
      }

      const node: ExecutionNode = {
        id: nodeId,
        type: kind,
        name: name.length > 40 ? name.slice(0, 38) + '...' : name,
        group: parent ? String(events.findIndex(pe => pe.id === parent.id)) : (e.span_id || `root_${i}`),
        status,
        duration: e.duration_ms || 0,
        parentId: parent ? (parent.span_id && parent.name ? `${parent.span_id}::${parent.name}` : `ev_${parent.id}`) : undefined,
        color: '',
        icon: '',
      };

      seen.set(nodeId, node);
      result.push(node);
    }
    return result;
  }, [events]);

  if (loading) return <div className="text-xs text-gray-500 py-4 text-center">加载中...</div>;
  if (error) return <div className="text-xs text-gray-500 py-4">{error}</div>;
  if (!events.length) return null;

  return (
    <ExecutionViewer
      nodes={nodes}
      title={`执行流程 · ${events.length} 步`}
      height={Math.max(300, events.length * 70)}
    />
  );
};
