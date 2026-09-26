import { useCallback, useEffect, useRef, useState } from 'react';
import type { ExecutionNode as ENode } from '../components/ExecutionViewer/types';

export type LiveGraphStatus = 'disconnected' | 'connecting' | 'streaming' | 'done' | 'error';

interface GraphNodeRaw {
  run_id?: string;
  node_id?: string;
  parent_id?: string;
  kind?: string;
  name?: string;
  label?: string;
  role?: string;
  status?: string;
  start_time?: number;
  end_time?: number;
  duration_ms?: number;
  args?: Record<string, unknown>;
  result?: unknown;
  error?: string;
  sort_key?: number;
  input_tokens?: number;
  output_tokens?: number;
  cost?: number;
  children?: GraphNodeRaw[];
  id?: string;
  parentId?: string;
}

function mapStatus(s?: string): ENode['status'] {
  const v = (s || '').toLowerCase();
  if (v === 'ok' || v === 'success' || v === 'completed' || v === 'done' || v === 'finished' || v === 'observing') {
    return 'completed';
  }
  if (v === 'error' || v === 'failed' || v === 'timeout' || v === 'cancelled' || v === 'canceled') {
    return 'failed';
  }
  if (v === 'warning' || v === 'approval_required') return 'warning';
  if (v === 'running' || v === 'pending' || v === 'accepted') return 'running';
  return 'idle';
}

const KIND_META: Record<string, { icon: string; color: string }> = {
  llm: { icon: '🧠', color: '#6366f1' },
  reason: { icon: '🧠', color: '#6366f1' },
  tool: { icon: '🔧', color: '#14b8a6' },
  mcp: { icon: '🔌', color: '#10b981' },
  skill: { icon: '⚡', color: '#8b5cf6' },
  agent: { icon: '🤖', color: '#3b82f6' },
  step: { icon: '🔄', color: '#8b5cf6' },
  done: { icon: '✅', color: '#22c55e' },
  context: { icon: '📚', color: '#6366f1' },
  observe: { icon: '📚', color: '#ec4899' },
};

function rawToENode(raw: GraphNodeRaw): ENode {
  const kind = (raw.kind || 'default').replace(/^sys_/, '');
  const meta = KIND_META[kind] || { icon: '📋', color: '#6b7280' };
  const name = String(raw.name || raw.node_id || 'unknown');
  const role = raw.role || 'work';
  // Keep semantic name for pairing; prefer distinct labels for containers.
  let label = String(raw.label || name);
  if (role === 'container' && (name === 'skill_start' || name === 'agent_start')) {
    label = name === 'agent_start'
      ? `Agent · ${raw.label || '执行'}`
      : `Skill · ${raw.label || '执行'}`;
  } else if (kind === 'skill' && name !== 'skill_start' && name !== 'skill_end') {
    label = `Skill · ${label}`;
  }
  const kids = (raw.children || []).map(rawToENode);
  return {
    id: String(raw.node_id || raw.id || name),
    type: kind,
    name: label.slice(0, 40),
    status: mapStatus(raw.status),
    parentId: raw.parentId || raw.parent_id || undefined,
    parentSpanId: raw.parent_id || undefined,
    startTime: typeof raw.start_time === 'number' ? raw.start_time : undefined,
    duration: typeof raw.duration_ms === 'number' ? raw.duration_ms : 0,
    color: meta.color,
    icon: meta.icon,
    children: kids.length ? kids : undefined,
    details: {
      args: raw.args || {},
      result: raw.result,
      error: raw.error,
      kind,
      role,
      semanticName: name,
      input_tokens: raw.input_tokens,
      output_tokens: raw.output_tokens,
      cost: raw.cost,
    },
  };
}

function upsertFlat(map: Map<string, GraphNodeRaw>, node: GraphNodeRaw) {
  const id = String(node.node_id || '');
  if (!id) return;
  const prev = map.get(id);
  map.set(id, { ...(prev || {}), ...node, node_id: id });
}

function buildRoots(map: Map<string, GraphNodeRaw>): ENode[] {
  const items = new Map<string, GraphNodeRaw>();
  for (const [id, n] of map) {
    items.set(id, { ...n, children: [] });
  }
  const roots: GraphNodeRaw[] = [];
  for (const item of items.values()) {
    const pid = item.parent_id ? String(item.parent_id) : '';
    if (pid && items.has(pid) && pid !== String(item.node_id)) {
      const parent = items.get(pid)!;
      parent.children = parent.children || [];
      parent.children.push(item);
      item.parentId = pid;
    } else {
      roots.push(item);
    }
  }
  const sort = (list: GraphNodeRaw[]) => {
    list.sort(
      (a, b) =>
        Number(a.sort_key || a.start_time || 0) - Number(b.sort_key || b.start_time || 0) ||
        String(a.name || '').localeCompare(String(b.name || '')),
    );
    for (const c of list) {
      if (c.children?.length) sort(c.children);
    }
  };
  sort(roots);
  return roots.map(rawToENode);
}

async function fetchGraph(runId: string, signal?: AbortSignal) {
  const res = await fetch(`/api/core/observation/runs/${encodeURIComponent(runId)}/graph`, { signal });
  if (!res.ok) return null;
  return res.json();
}

/**
 * Live RunGraph projection for ExecutionViewer.
 * Stays subscribed until graph_done / type:done so late open_node is not missed.
 * When the run finishes with zero graph nodes, hasGraph stays false → legacy path.
 */
export function useLiveGraph(runId: string | null) {
  const [roots, setRoots] = useState<ENode[]>([]);
  const [hasGraph, setHasGraph] = useState(false);
  const [status, setStatus] = useState<LiveGraphStatus>('disconnected');
  const [error, setError] = useState<string | null>(null);
  const nodeMapRef = useRef<Map<string, GraphNodeRaw>>(new Map());
  const sourceRef = useRef<EventSource | null>(null);
  const doneRef = useRef(false);

  const rebuild = useCallback(() => {
    setRoots(buildRoots(nodeMapRef.current));
    if (nodeMapRef.current.size > 0) setHasGraph(true);
  }, []);

  useEffect(() => {
    if (!runId) {
      setRoots([]);
      setHasGraph(false);
      setStatus('disconnected');
      nodeMapRef.current = new Map();
      doneRef.current = false;
      return;
    }

    let cancelled = false;
    doneRef.current = false;
    nodeMapRef.current = new Map();
    setStatus('connecting');
    setError(null);
    setHasGraph(false);
    setRoots([]);

    const markDone = () => {
      if (doneRef.current) return;
      doneRef.current = true;
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
      if (!cancelled) {
        setHasGraph(nodeMapRef.current.size > 0);
        setStatus('done');
      }
    };

    const applyGraphPayload = (g: any) => {
      if (!g) return;
      if (g.has_graph || (g.nodes || []).length > 0) {
        for (const n of g.nodes || []) upsertFlat(nodeMapRef.current, n);
        rebuild();
      }
      const st = String(g.status || '');
      if (st && st !== 'running') markDone();
    };

    (async () => {
      try {
        const g = await fetchGraph(runId);
        if (cancelled) return;
        applyGraphPayload(g);
        if (!doneRef.current) setStatus('streaming');
      } catch {
        if (!cancelled && !doneRef.current) setStatus('streaming');
      }

      if (cancelled || doneRef.current) return;

      const url = `/api/core/observation/runs/${encodeURIComponent(runId)}/stream`;
      const es = new EventSource(url);
      sourceRef.current = es;

      es.onopen = () => {
        if (!cancelled && !doneRef.current) setStatus('streaming');
      };

      es.onmessage = (e) => {
        if (cancelled || doneRef.current) return;
        try {
          const data = JSON.parse(e.data);
          if (data?.type === 'done' || data?.type === 'graph_done') {
            // Final hydrate so late close_node is not missed. If graph still empty,
            // keep polling — stream Mode often emits done before open_node.
            void fetchGraph(runId).then((g) => {
              if (cancelled) return;
              applyGraphPayload(g);
              const st = String(g?.status || '');
              const has = Boolean(g?.has_graph) || (g?.nodes || []).length > 0;
              if (has || (st && st !== 'running')) {
                markDone();
              }
              // else: leave streaming; interval poll will pick up nodes
            }).catch(() => { /* keep streaming */ });
            return;
          }
          if (data?.type === 'heartbeat' || data?.type === 'connected') return;
          if (data?.type === 'replay_start' || data?.type === 'replay_done') return;
          if (data?.type === 'graph_upsert' && data.node) {
            upsertFlat(nodeMapRef.current, data.node);
            rebuild();
          }
        } catch {
          /* skip */
        }
      };

      es.onerror = () => {
        if (cancelled || doneRef.current) return;
        try { es.close(); } catch { /* ignore */ }
        if (sourceRef.current === es) sourceRef.current = null;
        if (!cancelled) setError('RunGraph SSE 不可用，已回退轮询');
      };
    })();

    const poll = window.setInterval(() => {
      if (cancelled || doneRef.current) return;
      void (async () => {
        try {
          const g = await fetchGraph(runId);
          if (cancelled || doneRef.current) return;
          applyGraphPayload(g);
        } catch {
          /* ignore */
        }
      })();
    }, 1500);

    return () => {
      cancelled = true;
      window.clearInterval(poll);
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
    };
  }, [runId, rebuild]);

  return { roots, hasGraph, status, error };
}
