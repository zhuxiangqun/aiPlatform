import { useMemo, useState } from 'react';
import ReactFlow, { Background, Controls, Edge, Node, Position, MarkerType } from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';
import './tokens.css';
import type { ExecutionNode as ENode, ExecutionViewerProps } from './types';
import { useLiveEvents } from '../../hooks/useLiveEvents';
import { useReplayEvents } from '../../hooks/useReplayEvents';

const ICONS: Record<string, string> = {
  llm: '🧠', tool: '🔧', skill: '🎯', mcp: '🔌', reason: '💭', observe: '👁️',
  diag: '🔍', runtime: '⚙️', capability: '🧩', security: '🔒', trace: '🔗', finish: '🏁',
  start: '▶️', routing: '🧭', changeset: '📝', metric: '📊',
  step: '🔄', context: '📋', done: '✅', gate: '🚪', agent: '🤖',
  hitl: '⏸️', fork: '🍴', stage: '📊', pipeline: '🏗️',
  default: '📋',
};

const TYPE_COLORS: Record<string, string> = {
  llm: '#3b82f6', tool: '#f59e0b', skill: '#8b5cf6', mcp: '#10b981',
  reason: '#6366f1', observe: '#ec4899', diag: '#06b6d4',
  runtime: '#3b82f6', capability: '#f59e0b', security: '#22c55e', trace: '#06b6d4', finish: '#f97316',
  routing: '#a855f7', changeset: '#eab308', metric: '#14b8a6',
  step: '#8b5cf6', context: '#6b7280', done: '#22c55e', gate: '#ef4444', agent: '#3b82f6',
  hitl: '#f59e0b', fork: '#ec4899', stage: '#6366f1', pipeline: '#14b8a6',
  default: '#6b7280',
};

const STATUS_CONFIG: Record<string, { ring: string; dot: string; badge: string }> = {
  running: { ring: '2px solid #3b82f6', dot: 'bg-blue-400 animate-pulse ring-2 ring-blue-400/30', badge: '检查中' },
  completed: { ring: '2px solid #22c55e', dot: 'bg-green-400 ring-2 ring-green-400/30', badge: '✅' },
  failed: { ring: '2px solid #ef4444', dot: 'bg-red-400 ring-2 ring-red-400/30', badge: '❌' },
  warning: { ring: '2px solid #f59e0b', dot: 'bg-yellow-400 ring-2 ring-yellow-400/30', badge: '⚠️' },
  idle: { ring: '2px solid #374151', dot: 'bg-gray-500 ring-1 ring-gray-500/20', badge: '等待' },
};

function layoutDagre(nodes: Node[], edges: Edge[]) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', ranksep: 80, nodesep: 60, marginx: 20, marginy: 20 });
  for (const n of nodes) g.setNode(n.id, { width: 220, height: 64 });
  for (const e of edges) g.setEdge(e.source, e.target);
  dagre.layout(g);
  return {
    nodes: nodes.map((n) => { const dn = g.node(n.id); return { ...n, position: { x: dn.x - 110, y: dn.y - 32 } }; }),
    edges,
  };
}

function layoutColumns(nodes: Node[], edges: Edge[], groupMap: Map<string, ENode[]>) {
  const groups = [...groupMap.keys()].filter(k => k !== '__root__');
  if (groups.length === 0) return layoutDagre(nodes, edges);

  const colW = 260, colGap = 24, nodeH = 80, nodeGap = 16, padX = 20, padY = 20;
  const layed = nodes.map(n => ({ ...n }));
  let colX = padX;

  for (const g of groups) {
    const gNodes = groupMap.get(g) || [];
    const ids = new Set(gNodes.map(gn => gn.id));
    let y = padY;

    for (const nid of ids) {
      const idx = layed.findIndex(n => n.id === nid);
      if (idx >= 0) layed[idx].position = { x: colX, y };
      y += nodeH + nodeGap;
    }
    colX += colW + colGap;
  }

  const width = colX - colGap + padX;
  return { nodes: layed, edges, width };
}

const ExecutionViewer: React.FC<ExecutionViewerProps> = ({ nodes: propNodes, title, running, elapsed, summary, height = 500, onNodeClick, live, runId, replayRunId }) => {
  // Live mode: generate nodes from SSE events
  const { events: liveEvents, status: liveStatus } = useLiveEvents(live ? (runId || null) : null);
  // Replay mode: step through historical events
  const replay = useReplayEvents(replayRunId || null);

  // Merge prop nodes with live-generated nodes + replay nodes
  // Unified status mapping: all backend statuses → frontend display status
  const mapStatus = (e: any): 'completed' | 'failed' | 'running' | 'warning' | 'idle' => {
    const s = (e.status || '').toLowerCase();
    if (s === 'ok' || s === 'success' || s === 'completed') return 'completed';
    if (s === 'error' || s === 'failed' || s === 'policy_denied' || s === 'toolset_denied'
        || s === 'blocked' || s === 'prod_denied') return 'failed';
    if (s === 'running' || s === 'pending') return 'running';
    if (s === 'warning' || s === 'approval_required') return 'warning';
    return 'idle';
  };

  const resolveArgs = (e: any) => {
    if (e.args && typeof e.args === 'object' && !Array.isArray(e.args)) return e.args;
    try { return JSON.parse(e.args_json || '{}'); } catch { return e.args_json || {}; }
  };

  const resolveResult = (e: any) => {
    if (e.result && typeof e.result === 'object' && !Array.isArray(e.result)) return e.result;
    try { return JSON.parse(e.result_json || '{}'); } catch { return e.result_json || {}; }
  };

  const eventToNode = (e: any, i: number, prefix: string): ENode => ({
    id: e.span_id || `${prefix}_${i}`,
    type: (e.kind || '').replace(/^sys_/, '') || 'default',
    name: (e.name || e.kind || 'unknown').slice(0, 40),
    status: mapStatus(e),
    startTime: e.start_time || undefined,
    duration: e.duration_ms || 0,
    details: {
      args: resolveArgs(e),
      result: resolveResult(e),
      error: e.error,
      target: e.target_type,
      kind: e.kind,
      input_tokens: e.input_tokens ?? undefined,
      output_tokens: e.output_tokens ?? undefined,
      cost: e.cost ?? undefined,
    },
  });

  // Merge events with same span_id — keep latest, then build tree from parent_span_id
  const mergeEvents = (events: any[], prefix: string): ENode[] => {
    const merged = new Map<string, { node: ENode; idx: number; finalStatus: boolean }>();
    for (let i = 0; i < events.length; i++) {
      const e = events[i];
      const id = e.span_id || `${prefix}_${i}`;
      const node = eventToNode(e, i, prefix);
      node.parentSpanId = e.parent_span_id || undefined;
      const existing = merged.get(id);
      if (!existing || (node.status !== 'idle' && !existing.finalStatus)) {
        const isFinal = node.status === 'completed' || node.status === 'failed' || node.status === 'warning';
        if (existing) {
          if (node.details && existing.node.details) {
            node.details.args = (node.details.args && Object.keys(node.details.args).length) ? node.details.args : existing.node.details.args;
            node.details.result = (node.details.result && Object.keys(node.details.result).length) ? node.details.result : existing.node.details.result;
          }
        }
        merged.set(id, { node, idx: i, finalStatus: existing ? (existing.finalStatus || isFinal) : isFinal });
      }
    }
    // Build tree: attach child nodes to their parent based on parent_span_id
    const nodes = [...merged.values()].sort((a, b) => (a.node.startTime || a.idx) - (b.node.startTime || b.idx) || a.idx - b.idx).map(m => m.node);
    const nodeMap = new Map<string, ENode>(nodes.map(n => [n.id, n]));
    const roots: ENode[] = [];
    for (const n of nodes) {
      if (n.parentSpanId && nodeMap.has(n.parentSpanId)) {
        const parent = nodeMap.get(n.parentSpanId)!;
        if (!parent.children) parent.children = [];
        parent.children.push(n);
      } else {
        roots.push(n);
      }
    }
    return roots;
  };

  const dataNodes: ENode[] = useMemo(() => {
    if (live && liveEvents.length > 0) {
      return mergeEvents(liveEvents, 'ev');
    }
    if (replayRunId && replay.visibleEvents.length > 0) {
      return mergeEvents(replay.visibleEvents, 'replay');
    }
    return propNodes || [];
  }, [live, liveEvents, propNodes, replayRunId, replay.visibleEvents]);

  const [selectedNode, setSelectedNode] = useState<ENode | null>(null);
  const [expandedSubFlows, setExpandedSubFlows] = useState<Set<string>>(new Set());

  // Expand all children of a sub-flow into the flat node list
  const flattenedNodes: ENode[] = useMemo(() => {
    const result: ENode[] = [];
    const visited = new Set<string>();
    const walk = (nodes: ENode[], parentId?: string) => {
      for (const n of nodes) {
        if (visited.has(n.id)) continue;
        visited.add(n.id);
        result.push(parentId ? { ...n, parentId } : n);
        if (n.children && n.children.length > 0 && expandedSubFlows.has(n.id)) {
          walk(n.children, n.id);
        }
      }
    };
    walk(dataNodes);
    return result;
  }, [dataNodes, expandedSubFlows]);

  const toggleSubFlow = (nodeId: string) => {
    setExpandedSubFlows(prev => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  };

  const actualRunning = replayRunId ? replay.playing : (live ? liveStatus === 'streaming' : running);
  const { nodes, edges, canvasWidth } = useMemo(() => {
    const nodeList: Node[] = [];
    const edgeList: Edge[] = [];
    const groupMap = new Map<string, ENode[]>();

    // Group nodes (from flattened list)
    for (const n of flattenedNodes) {
      const g = n.group || '__root__';
      if (!groupMap.has(g)) groupMap.set(g, []);
      groupMap.get(g)!.push(n);
    }

    // Build nodes
    for (const n of flattenedNodes) {
      const hasChildren = !!(n.children && n.children.length > 0);
      const isExpanded = expandedSubFlows.has(n.id);
      const color = n.color || TYPE_COLORS[n.type] || TYPE_COLORS.default;
      const sc = STATUS_CONFIG[n.status] || STATUS_CONFIG.idle;
      const icon = n.icon || (hasChildren ? '📦' : ICONS[n.type] || ICONS.default);
      const durText = n.duration ? (n.duration >= 1000 ? `${(n.duration / 1000).toFixed(1)}s` : `${n.duration}ms`) : '';
      const totalTokens = (n.details?.input_tokens ?? 0) + (n.details?.output_tokens ?? 0);
      const hasTokenInfo = n.details?.input_tokens !== undefined || n.details?.output_tokens !== undefined;
      const tokenText = hasTokenInfo ? (totalTokens >= 1000 ? `${(totalTokens / 1000).toFixed(1)}K` : String(totalTokens)) : '';
      const cost = n.details?.cost ?? 0;
      const costText = cost > 0 ? `$${cost.toFixed(4)}` : '';

      nodeList.push({
        id: n.id,
        type: 'default',
        data: {
          label: (
            <div style={{ position: 'relative', padding: '4px 0' }}>
              <div style={{ fontSize: 15, fontWeight: 600, color, display: 'flex', alignItems: 'center', gap: 4 }}>
                {icon} <span style={{ color: 'var(--ev-text-primary)' }}>{n.name}</span>
              </div>
              <div style={{ fontSize: 10, marginTop: 2, display: 'flex', alignItems: 'center', gap: 6 }}>
                {n.status !== 'idle' && (
                  <span style={{ color }}>{sc.badge}{n.status === 'running' ? '...' : ''}{durText ? ` · ${durText}` : ''}</span>
                )}
                {tokenText && (
                  <span style={{ color: 'var(--ev-text-muted)', fontSize: 9 }} title={`${n.details?.input_tokens ?? 0} in / ${n.details?.output_tokens ?? 0} out`}>
                    {tokenText} tok
                  </span>
                )}
                {costText && (
                  <span style={{ color: '#f59e0b', fontSize: 9 }}>
                    {costText}
                  </span>
                )}
                {hasChildren && (
                  <button
                    onClick={(e) => { e.stopPropagation(); toggleSubFlow(n.id); }}
                    style={{
                      background: isExpanded ? 'var(--ev-accent)' : 'var(--ev-bg-primary)',
                      border: '1px solid var(--ev-border)', borderRadius: 4,
                      color: 'var(--ev-text-secondary)', cursor: 'pointer', fontSize: 9,
                      padding: '1px 6px', lineHeight: '14px',
                    }}
                    title={isExpanded ? '折叠子流程' : '展开子流程'}
                  >
                    {isExpanded ? '▼' : '▶'} {n.children!.length} 子步骤
                  </button>
                )}
                {n.parentId && (
                  <span style={{ color: 'var(--ev-text-muted)', fontSize: 9 }}>
                    └ 子步骤
                  </span>
                )}
              </div>
              {/* Status dot */}
              {n.status !== 'idle' && (
                <div style={{
                  position: 'absolute', top: -12, left: -12,
                  width: 10, height: 10, borderRadius: '50%',
                  background: color,
                  boxShadow: `0 0 ${n.status === 'running' ? 6 : 3}px ${color}`,
                }} />
              )}
              {/* Sub-flow border accent */}
              {hasChildren && (
                <div style={{
                  position: 'absolute', bottom: -4, left: -8, right: -8,
                  height: 3, background: 'var(--ev-accent)', borderRadius: '0 0 8px 8px', opacity: 0.6,
                }} />
              )}
            </div>
          ),
        },
        position: { x: 0, y: 0 },
        style: {
          background: n.parentId ? 'var(--ev-bg-subflow)' : 'var(--ev-bg-secondary)',
          border: hasChildren ? `2px dashed var(--ev-accent)` : sc.ring,
          borderRadius: hasChildren ? 12 : 10,
          padding: '10px 18px',
          width: hasChildren ? 280 : 240,
          boxShadow: n.status === 'running' ? `0 0 10px ${color}40` : undefined,
        },
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
      });
    }

    // Build edges: for single-group and sub-flow connections
    const groups = [...groupMap.keys()].filter(k => k !== '__root__');
    if (groups.length <= 1) {
      // First pass: edges within groups
      for (const [, groupNodes] of groupMap) {
        for (let i = 1; i < groupNodes.length; i++) {
          const src = groupNodes[i - 1];
          const tgt = groupNodes[i];
          // Don't create edges from expanded sub-flow parents to their first child directly
          // (the parent is the container, children are nested)
          const fromExpandedSubFlow = expandedSubFlows.has(src.id);
          if (fromExpandedSubFlow && tgt.parentId === src.id) continue;
          const edgeColor = src.status === 'running' ? '#3b82f6' :
                           src.status === 'completed' ? '#22c55e' :
                           src.status === 'failed' ? '#ef4444' : '#374151';
          edgeList.push({
            id: `${src.id}->${tgt.id}`,
            source: src.id,
            target: tgt.id,
            type: 'smoothstep',
            animated: src.status === 'running' && actualRunning,
            style: { stroke: edgeColor, strokeWidth: tgt.parentId ? 1.5 : (src.status === 'running' ? 2.5 : 1.5), opacity: src.status === 'idle' ? 0.3 : 0.8 },
            markerEnd: { type: MarkerType.ArrowClosed, color: edgeColor },
          });
        }
      }

      // Second pass: parent→first-child edges for expanded sub-flows
      for (const [nid] of expandedSubFlows) {
        const parent = flattenedNodes.find(n => n.id === nid);
        if (parent?.children && parent.children.length > 0) {
          const firstChild = flattenedNodes.find(n => n.parentId === parent.id);
          if (firstChild) {
            edgeList.push({
              id: `sub_${parent.id}_start`,
              source: parent.id,
              target: firstChild.id,
              type: 'smoothstep',
              animated: parent.status === 'running' && actualRunning,
              style: { stroke: 'var(--ev-accent)', strokeWidth: 1.5, strokeDasharray: '5,3', opacity: 0.7 },
              markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--ev-accent)' },
            });
          }
        }
      }
    }

    // Inter-group edges: only for single-group flow
    if (groups.length <= 1) {
      for (let i = 1; i < groups.length; i++) {
        const prevNodes = groupMap.get(groups[i - 1]) || [];
        const nextNodes = groupMap.get(groups[i]) || [];
        if (prevNodes.length && nextNodes.length) {
          const lastSrc = prevNodes[prevNodes.length - 1];
          const firstTgt = nextNodes[0];
          edgeList.push({
            id: `grp_${groups[i - 1]}_to_${groups[i]}`,
            source: lastSrc.id,
            target: firstTgt.id,
            type: 'smoothstep',
            animated: actualRunning,
            style: { stroke: '#4b5563', strokeWidth: 1, opacity: 0.3, strokeDasharray: '8,4' },
            markerEnd: { type: MarkerType.ArrowClosed, color: '#4b5563' },
          });
        }
      }
    }

    const hasGroups = groups.length > 0;
    if (hasGroups) {
      const result = layoutColumns(nodeList, edgeList, groupMap);
      return { nodes: result.nodes, edges: result.edges, canvasWidth: (result as any).width || 1600 };
    }
    const result = layoutDagre(nodeList, edgeList);
    return { nodes: result.nodes, edges: result.edges, canvasWidth: 0 };
  }, [flattenedNodes, actualRunning, expandedSubFlows]);

  if (flattenedNodes.length === 0) return null;

  const done = flattenedNodes.filter(n => n.status === 'completed' || n.status === 'failed' || n.status === 'warning').length;
  const hasGroups = flattenedNodes.some(n => n.group && n.group !== '__root__');
  const maxColNodes = hasGroups
    ? Math.max(...Object.values(flattenedNodes.reduce((acc, n) => {
        const g = n.group || '__root__';
        acc[g] = (acc[g] || 0) + 1;
        return acc;
      }, {} as Record<string, number>)))
    : 0;
  const vHeight = hasGroups
    ? Math.max(height, maxColNodes * 96 + 60)
    : Math.max(height, flattenedNodes.length * 90 + 100);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {/* Progress bar */}
      {(title || summary) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '0 4px', flexShrink: 0 }}>
          {title && <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--ev-text-primary)' }}>{title}</span>}
          {actualRunning && <span style={{ fontSize: 12, color: '#3b82f6', display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ animation: 'spin 1s linear infinite' }}>⚙</span> {done}/{flattenedNodes.length} · {elapsed || 0}s</span>}
          {!actualRunning && summary && (
            <span style={{ fontSize: 11, color: 'var(--ev-text-secondary)' }}>
              {summary.pass}✅ {summary.warn}⚠️ {summary.fail}❌
            </span>
          )}
          <div style={{ flex: 1 }} />
          {actualRunning && (
            <div style={{ width: 120, height: 4, background: '#374151', borderRadius: 2 }}>
              <div style={{ width: `${(done / flattenedNodes.length) * 100}%`, height: '100%', background: '#3b82f6', borderRadius: 2, transition: 'width 0.3s' }} />
            </div>
          )}
        </div>
      )}

      {/* Replay controls */}
      {replayRunId && !replay.loading && !replay.error && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 4px', flexShrink: 0 }}>
          <button onClick={replay.playing ? replay.pause : replay.play}
            style={{
              background: 'var(--ev-accent)', border: 'none', borderRadius: 6,
              color: '#fff', cursor: 'pointer', fontSize: 12, padding: '4px 12px',
            }}>
            {replay.playing ? '⏸ 暂停' : '▶ 播放'}
          </button>
          <button onClick={replay.reset}
            style={{
              background: 'var(--ev-bg-secondary)', border: '1px solid var(--ev-border)', borderRadius: 6,
              color: 'var(--ev-text-secondary)', cursor: 'pointer', fontSize: 12, padding: '4px 10px',
            }}>
            ↺ 重放
          </button>
          <select value={replay.speed} onChange={e => replay.setSpeed(Number(e.target.value))}
            style={{
              background: 'var(--ev-bg-secondary)', border: '1px solid var(--ev-border)', borderRadius: 6,
              color: 'var(--ev-text-secondary)', fontSize: 11, padding: '4px 8px', cursor: 'pointer',
            }}>
            <option value={0.5}>0.5x</option>
            <option value={1}>1x</option>
            <option value={2}>2x</option>
            <option value={5}>5x</option>
            <option value={10}>10x</option>
          </select>
          <span style={{ fontSize: 11, color: 'var(--ev-text-secondary)' }}>
            {replay.currentIndex + 1} / {replay.totalEvents}
          </span>
          <div style={{ flex: 1, height: 4, background: '#374151', borderRadius: 2 }}>
            <div style={{ width: `${replay.progress}%`, height: '100%', background: 'var(--ev-accent)', borderRadius: 2, transition: 'width 0.2s' }} />
          </div>
        </div>
      )}
      {replayRunId && replay.loading && (
        <div style={{ textAlign: 'center', color: 'var(--ev-text-muted)', fontSize: 12, padding: 8 }}>
          加载回放数据...
        </div>
      )}
      {replayRunId && replay.error && (
        <div style={{ textAlign: 'center', color: '#ef4444', fontSize: 12, padding: 8 }}>
          {replay.error}
        </div>
      )}

      {/* Flow canvas */}
      <div style={{ border: '1px solid var(--ev-border)', borderRadius: 12, overflow: 'hidden', height: vHeight, minWidth: canvasWidth || undefined }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          nodesDraggable={!!onNodeClick}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
          onNodeClick={(_e, node) => {
            const dn = flattenedNodes.find(d => d.id === node.id);
            if (dn) setSelectedNode(dn);
            if (onNodeClick) onNodeClick(dn || flattenedNodes[0]);
          }}
        >
          <Background color="#1f2937" gap={24} />
          <Controls showInteractive={false} />
        </ReactFlow>
        <style>{`
          .react-flow__controls-button{background:#1f2937!important;border-color:#374151!important}
          .react-flow__controls-button:hover{background:#374151!important}
          .react-flow__controls-button svg{fill:#9ca3af!important}
          .react-flow__attribution{display:none!important}
          @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
        `}</style>
      </div>

      {/* Detail panel */}
      {selectedNode && (
        <div style={{
          border: '1px solid var(--ev-border)', borderRadius: 8, padding: '12px 16px',
          background: 'var(--ev-bg-secondary)', maxHeight: 300, overflowY: 'auto',
          display: 'flex', flexDirection: 'column', gap: 8, flexShrink: 0,
          position: 'relative',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: selectedNode.color || '#e5e7eb' }}>
              {selectedNode.icon} {selectedNode.name}
            </span>
            <button onClick={() => setSelectedNode(null)} style={{
              background: 'none', border: 'none', color: 'var(--ev-text-muted)', cursor: 'pointer', fontSize: 16,
            }}>✕</button>
          </div>
          <div style={{ display: 'flex', gap: 12, fontSize: 11 }}>
            <span style={{ color: 'var(--ev-text-secondary)' }}>类型: {selectedNode.type}</span>
            <span style={{ color: 'var(--ev-text-secondary)' }}>状态: {selectedNode.status}</span>
            {selectedNode.duration ? <span style={{ color: 'var(--ev-text-secondary)' }}>耗时: {selectedNode.duration}ms</span> : null}
            {selectedNode.details?.input_tokens !== undefined || selectedNode.details?.output_tokens !== undefined ? (
              <span style={{ color: 'var(--ev-text-secondary)' }}>
                输入: {selectedNode.details.input_tokens ?? 0} · 输出: {selectedNode.details.output_tokens ?? 0} tok
              </span>
            ) : null}
            {selectedNode.details?.cost ? (
              <span style={{ color: '#f59e0b' }}>${selectedNode.details.cost.toFixed(4)}</span>
            ) : null}
          </div>
          {selectedNode.details && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {selectedNode.details.args != null && (
                <div>
                  <div style={{ fontSize: 10, color: 'var(--ev-text-muted)', marginBottom: 2 }}>输入参数</div>
                  <pre style={{
                    fontSize: 10, color: 'var(--ev-text-secondary)', background: 'var(--ev-bg-primary)', borderRadius: 4,
                    padding: '4px 8px', maxHeight: 100, overflowY: 'auto', whiteSpace: 'pre-wrap',
                  }}>{typeof selectedNode.details.args === 'string' ? selectedNode.details.args : JSON.stringify(selectedNode.details.args, null, 2).slice(0, 500)}</pre>
                </div>
              )}
              {selectedNode.details.result != null && (
                <div>
                  <div style={{ fontSize: 10, color: 'var(--ev-text-muted)', marginBottom: 2 }}>输出结果</div>
                  <pre style={{
                    fontSize: 10, color: 'var(--ev-text-secondary)', background: 'var(--ev-bg-primary)', borderRadius: 4,
                    padding: '4px 8px', maxHeight: 100, overflowY: 'auto', whiteSpace: 'pre-wrap',
                  }}>{typeof selectedNode.details.result === 'string' ? selectedNode.details.result : JSON.stringify(selectedNode.details.result, null, 2).slice(0, 500)}</pre>
                </div>
              )}
              {selectedNode.details.error && (
                <div>
                  <div style={{ fontSize: 10, color: 'var(--ev-text-muted)', marginBottom: 2 }}>错误信息</div>
                  <div style={{
                    fontSize: 10, color: '#ef4444', background: 'var(--ev-bg-primary)', borderRadius: 4,
                    padding: '4px 8px',
                  }}>{String(selectedNode.details.error).slice(0, 500)}</div>
                </div>
              )}
            </div>
          )}
          {/* Sub-flow children */}
          {selectedNode.children && selectedNode.children.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div style={{ fontSize: 10, color: 'var(--ev-text-muted)', marginBottom: 2 }}>
                子流程 ({selectedNode.children.length} 步骤)
              </div>
              <div style={{
                display: 'flex', flexDirection: 'column', gap: 4,
                background: 'var(--ev-bg-subflow)', borderRadius: 6, padding: '6px 8px',
                maxHeight: 160, overflowY: 'auto',
              }}>
                {selectedNode.children.map(child => {
                  const cColor = child.color || TYPE_COLORS[child.type] || TYPE_COLORS.default;
                  const cSc = STATUS_CONFIG[child.status] || STATUS_CONFIG.idle;
                  const cIcon = child.icon || ICONS[child.type] || ICONS.default;
                  return (
                    <div key={child.id} style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      fontSize: 11, padding: '2px 0',
                      borderLeft: `3px solid ${cColor}`,
                      paddingLeft: 8,
                    }}>
                      <span>{cIcon}</span>
                      <span style={{ color: 'var(--ev-text-primary)', flex: 1 }}>{child.name}</span>
                      <span style={{ color: cColor, fontSize: 10 }}>{cSc.badge}</span>
                      {child.duration ? <span style={{ color: 'var(--ev-text-muted)', fontSize: 10 }}>{child.duration}ms</span> : null}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ExecutionViewer;
