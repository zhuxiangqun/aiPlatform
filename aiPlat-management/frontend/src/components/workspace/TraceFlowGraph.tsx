import React, { useEffect, useMemo, useState } from 'react';
import ReactFlow, { Background, Controls, Node, Edge, MarkerType, Position } from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';
import { diagnosticsApi } from '../../services';

interface Props {
  runId: string;
}

interface SyscallEvent {
  id?: number;
  span_id?: string;
  trace_id?: string;
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
  parent_span_id?: string;
  created_at?: number;
}

const NODE_COLORS: Record<string, string> = {
  llm_generate: '#3b82f6',
  llm: '#3b82f6',
  tool_call: '#f59e0b',
  tool: '#f59e0b',
  skill_call: '#8b5cf6',
  skill: '#8b5cf6',
  mcp_call: '#10b981',
  reason: '#6366f1',
  observe: '#ec4899',
  default: '#6b7280',
};

const KINDS: Record<string, string> = {
  llm_generate: 'LLM',
  sys_llm_generate: 'LLM',
  tool_call: 'Tool',
  sys_tool_call: 'Tool',
  skill_call: 'Skill',
  sys_skill_call: 'Skill',
  kb_retrieve: '检索',
  sys_kb_retrieve: '检索',
  reason: '推理',
  observe: '观察',
};

const _fmtMs = (ms: number) => {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
};

function layoutDagre(nodes: Node[], edges: Edge[]) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', ranksep: 60, nodesep: 80 });

  for (const n of nodes) {
    g.setNode(n.id, { width: 200, height: 60 });
  }
  for (const e of edges) {
    g.setEdge(e.source, e.target);
  }
  dagre.layout(g);

  return {
    nodes: nodes.map((n) => {
      const dn = g.node(n.id);
      return { ...n, position: { x: dn.x - 100, y: dn.y - 30 } };
    }),
    edges,
  };
}

export const TraceFlowGraph: React.FC<Props> = ({ runId }) => {
  const [events, setEvents] = useState<SyscallEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const fetchEvents = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await diagnosticsApi.listSyscalls({ run_id: runId, limit: 200 });
      const list = (res as any).items || (res as any).events || [];
      setEvents(list);
      if (list.length === 0) setError('该执行未产生可追踪的系统调用事件');
    } catch {
      setError('获取执行流程失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchEvents(); }, [runId]);

  const { nodes, edges } = useMemo(() => {
    if (events.length === 0) return { nodes: [], edges: [] };

    const spanMap = new Map<string, SyscallEvent>();
    const parentMap = new Map<string, string[]>();
    for (const e of events) {
      const sid = e.span_id || `ev_${e.id}`;
      spanMap.set(sid, e);
      const parentSid = (e as any).parent_span_id || '';
      if (parentSid) {
        if (!parentMap.has(parentSid)) parentMap.set(parentSid, []);
        parentMap.get(parentSid)!.push(sid);
      }
    }

    const roots = events.filter((e) => !(e as any).parent_span_id);
    if (roots.length === 0 && events.length > 0) {
      roots.push(events[0]);
    }

    // Build tree levels
    const levelMap = new Map<string, number>();
    function assignLevel(sid: string, level: number) {
      if (levelMap.has(sid) && levelMap.get(sid)! <= level) return;
      levelMap.set(sid, level);
      const children = parentMap.get(sid) || [];
      for (const child of children) assignLevel(child, level + 1);
    }
    for (const r of roots) {
      const sid = r.span_id || `ev_${r.id}`;
      assignLevel(sid, 0);
    }

    const nodeList: Node[] = [];
    const edgeList: Edge[] = [];
    let y = 0;

    for (const e of events) {
      const sid = e.span_id || `ev_${e.id}`;
      const kind = KINDS[e.kind || ''] || e.kind || 'default';
      const name = e.name || e.target_type || '';
      const status = e.status || 'unknown';
      const dur = e.duration_ms ? _fmtMs(e.duration_ms) : '';
      const color = NODE_COLORS[e.kind || ''] || NODE_COLORS.default;

      nodeList.push({
        id: sid,
        type: 'default',
        data: {
          label: (
            <div style={{ fontSize: 11, lineHeight: 1.3 }}>
              <div style={{ fontWeight: 600, color }}>{kind}</div>
              <div style={{ color: '#9ca3af' }}>{name || '-'}</div>
              {dur && <div style={{ color: '#6b7280', fontSize: 10 }}>{dur}</div>}
            </div>
          ),
        },
        position: { x: 0, y },
        style: {
          background: '#1f2937',
          border: `1px solid ${status === 'ok' ? '#22c55e' : status === 'error' ? '#ef4444' : '#374151'}`,
          borderRadius: 8,
          padding: '6px 12px',
          width: 200,
        },
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
      });
      y += 100;

      const parentSid = (e as any).parent_span_id;
      if (parentSid && spanMap.has(parentSid)) {
        edgeList.push({
          id: `${parentSid}->${sid}`,
          source: parentSid,
          target: sid,
          type: 'smoothstep',
          animated: false,
          style: { stroke: '#374151', strokeWidth: 1.5 },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#374151' },
        });
      }
    }

    return layoutDagre(nodeList, edgeList);
  }, [events]);

  if (loading) return <div className="text-xs text-gray-500 py-8 text-center">加载执行流程...</div>;
  if (error) return <div className="text-xs text-gray-500 py-4">{error}</div>;
  if (events.length === 0) return null;

  const nodeCount = events.length;
  const height = Math.max(300, nodeCount * 90);

  return (
    <div style={{ height, width: '100%', border: '1px solid #374151', borderRadius: 8, overflow: 'hidden' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        attributionPosition="bottom-right"
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={true}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#374151" gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
      <div className="text-[10px] text-gray-600 absolute bottom-1 left-2 z-10">
        {nodeCount} 步
      </div>
    </div>
  );
};
