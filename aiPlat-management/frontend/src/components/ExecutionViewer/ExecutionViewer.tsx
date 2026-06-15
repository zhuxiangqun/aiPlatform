import { useEffect, useMemo, useState } from 'react';
import ReactFlow, { Background, Controls, Edge, Node, Position, MarkerType } from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';
import './tokens.css';
import type { ExecutionNode as ENode, ExecutionViewerProps } from './types';
import { useLiveEvents } from '../../hooks/useLiveEvents';
import { useReplayEvents } from '../../hooks/useReplayEvents';

// Canvas node type mapping: syscall event kind → Canvas node type + icon + color
const CANVAS_NODES: Record<string, { icon: string; color: string; label: string }> = {
  llm:        { icon: '🧠', color: '#6366f1', label: 'LLM' },
  tool:       { icon: '🔧', color: '#14b8a6', label: 'Tool' },
  mcp:        { icon: '🔌', color: '#10b981', label: 'MCP' },
  mcp_admin:  { icon: '🔌', color: '#10b981', label: 'MCP' },
  routing:    { icon: '🤖', color: '#3b82f6', label: 'Agent' },
  skill:      { icon: '⚡', color: '#8b5cf6', label: 'Skill' },
  agent:      { icon: '🤖', color: '#3b82f6', label: 'Agent' },
  step:       { icon: '🔄', color: '#8b5cf6', label: 'Step' },
  done:       { icon: '✅', color: '#22c55e', label: 'Done' },
  reason:     { icon: '🧠', color: '#6366f1', label: 'LLM' },
  context:    { icon: '📚', color: '#6366f1', label: 'Knowledge' },
  observe:    { icon: '📚', color: '#ec4899', label: 'Knowledge' },
  gate:       { icon: '🔀', color: '#f59e0b', label: 'Condition' },
  fork:       { icon: '🔀', color: '#ec4899', label: 'Condition' },
  security:   { icon: '🔀', color: '#22c55e', label: 'Condition' },
  hitl:       { icon: '👤', color: '#eab308', label: 'Human Input' },
  finish:     { icon: '🏁', color: '#f97316', label: 'End' },
  start:      { icon: '▶️', color: '#22c55e', label: 'Start' },
  changeset:  { icon: '✏️', color: '#eab308', label: 'Assigner' },
  metric:     { icon: '✏️', color: '#14b8a6', label: 'Assigner' },
  diag:       { icon: '✏️', color: '#06b6d4', label: 'Assigner' },
  trace:      { icon: '✏️', color: '#06b6d4', label: 'Assigner' },
  runtime:    { icon: '✏️', color: '#3b82f6', label: 'Assigner' },
  capability: { icon: '✏️', color: '#f59e0b', label: 'Assigner' },
  pipeline:   { icon: '📊', color: '#14b8a6', label: 'Agent' },
  stage:      { icon: '📊', color: '#6366f1', label: 'Agent' },
};
const CANVAS_DEFAULT = { icon: '📋', color: '#6b7280', label: 'Unknown' };

// Legacy compat — kept for reference
const ICONS: Record<string, string> = { ...Object.fromEntries(Object.entries(CANVAS_NODES).map(([k, v]) => [k, v.icon])), default: '📋' };
const TYPE_COLORS: Record<string, string> = { ...Object.fromEntries(Object.entries(CANVAS_NODES).map(([k, v]) => [k, v.color])), default: '#6b7280' };

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

// Structured detail panel — renders per-kind fields instead of raw JSON
export const StructuredDetail: React.FC<{ node: ENode }> = ({ node }) => {
  const d = node.details;
  if (!d) return null;

  const kind = d.kind || node.type;
  const args = typeof d.args === 'object' ? d.args : {};
  const result = typeof d.result === 'object' ? d.result : {};

  const row = (label: string, value: any, color = 'var(--ev-text-secondary)') => {
    if (value == null || value === '' || (typeof value === 'object' && Object.keys(value).length === 0)) return null;
    const text = typeof value === 'string' ? value : JSON.stringify(value).slice(0, 300);
    return { label, text, color };
  };

  const rows: { label: string; text: string; color: string }[] = [];

  // Per-kind structured fields
  switch (kind) {
    case 'llm':
    case 'reason': {
      rows.push(row('模型调用', 'LLM Generate'));
      if (d.input_tokens != null) rows.push(row('输入 Token', `${d.input_tokens}`, '#3b82f6'));
      if (d.output_tokens != null) rows.push(row('输出 Token', `${d.output_tokens}`, '#22c55e'));
      if (d.target) rows.push(row('Skill', d.target));
      break;
    }
    case 'tool': {
      rows.push(row('工具名称', node.name));
      if (args.tool_name || args.name) rows.push(row('工具名', args.tool_name || args.name));
      if (typeof result === 'object' && Object.keys(result).length) {
        const out = result.output ?? result.result ?? result;
        rows.push(row('输出', out, '#22c55e'));
      }
      if (d.target) rows.push(row('目标', d.target));
      break;
    }
    case 'routing': {
      const routeName = node.name === 'skill_route' ? '技能选择' : node.name === 'skill_candidates' ? '候选匹配' : node.name;
      rows.push(row('步骤', routeName));
      if (args.skill || args.selected_skill) rows.push(row('选中技能', args.skill || args.selected_skill, '#8b5cf6'));
      if (args.query_excerpt) rows.push(row('用户输入', args.query_excerpt));
      if (args.candidates && Array.isArray(args.candidates) && args.candidates.length > 0) {
        const candNames = args.candidates.map((c: any) => `${c.name || c.skill_id} (${c.score?.toFixed(1) ?? '?'})`).join(', ');
        rows.push(row('候选列表', candNames));
      }
      break;
    }
    case 'skill': {
      rows.push(row('技能执行', node.name, '#8b5cf6'));
      if (typeof result === 'object' && result.output) {
        const out = typeof result.output === 'string' ? result.output.slice(0, 200) : JSON.stringify(result.output).slice(0, 200);
        rows.push(row('输出', out, '#22c55e'));
      }
      break;
    }
    case 'context':
    case 'observe':
      rows.push(row('上下文', args.context || node.name, '#6366f1'));
      break;
    case 'hitl':
      rows.push(row('人工审批', args.reason || '等待人工确认', '#eab308'));
      break;
    case 'gate':
    case 'security':
      rows.push(row('安全门禁', args.reason || node.name, node.status === 'failed' ? '#ef4444' : '#22c55e'));
      break;
    default:
      // Generic: show args/result summary (compact)
      if (args && typeof args === 'object' && Object.keys(args).length) {
        rows.push(row('输入', args));
      }
      if (result && typeof result === 'object' && Object.keys(result).length) {
        rows.push(row('输出', result, '#22c55e'));
      }
  }

  // Show detail for all kinds (engine stage description)
  if (args && typeof args === 'object' && args.detail) {
    rows.push(row('详情', args.detail));
  }

  // Error always last
  if (d.error) {
    rows.push(row('错误', String(d.error).slice(0, 300), '#ef4444'));
  }

  if (rows.length === 0) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {rows.map((r, i) => (
        <div key={i}>
          <div style={{ fontSize: 10, color: 'var(--ev-text-muted)', marginBottom: 1 }}>{r.label}</div>
          <div style={{
            fontSize: 10, color: r.color, background: 'var(--ev-bg-primary)', borderRadius: 4,
            padding: '4px 8px', maxHeight: 100, overflowY: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
          }}>{r.text}</div>
        </div>
      ))}
    </div>
  );
};

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

  const eventToNode = (e: any, i: number, prefix: string): ENode => {
    const kind = (e.kind || '').replace(/^sys_/, '') || 'default';
    const canvas = CANVAS_NODES[kind] || CANVAS_DEFAULT;
    return {
    id: (e.span_id && e.name) ? `${e.span_id}::${e.name}` : (e.id || e.span_id || `${prefix}_${i}`),
    type: kind,
    name: (e.name || e.kind || 'unknown').slice(0, 40),
    status: mapStatus(e),
    startTime: e.start_time || undefined,
    duration: e.duration_ms || 0,
    color: canvas.color,
    icon: canvas.icon,
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
    };
  };

  // Merge events — dedup by span_id+name (merge start/end of same operation),
  // then build tree from parent_span_id via span→id mapping
  const mergeEvents = (events: any[], prefix: string): ENode[] => {
    const merged = new Map<string, { node: ENode; idx: number; finalStatus: boolean }>();
    const spanToId = new Map<string, string>(); // span_id → first event's node id (for parent linking)
    for (let i = 0; i < events.length; i++) {
      const e = events[i];
      const key = (e.span_id && e.name) ? `${e.span_id}::${e.name}` : (e.id || e.span_id || `${prefix}_${i}`);
      const node = eventToNode(e, i, prefix);
      node.parentSpanId = e.parent_span_id || undefined;
      const existing = merged.get(key);
      // Track span_id → node_id mapping for parent lookup (keep first)
      const sid = e.span_id;
      if (sid && !spanToId.has(sid)) spanToId.set(sid, key);
      if (!existing || (node.status !== 'idle' && !existing.finalStatus)) {
        const isFinal = node.status === 'completed' || node.status === 'failed' || node.status === 'warning';
        if (existing) {
          if (node.details && existing.node.details) {
            node.details.args = (node.details.args && Object.keys(node.details.args).length) ? node.details.args : existing.node.details.args;
            node.details.result = (node.details.result && Object.keys(node.details.result).length) ? node.details.result : existing.node.details.result;
          }
        }
        merged.set(key, { node, idx: i, finalStatus: existing ? (existing.finalStatus || isFinal) : isFinal });
      }
    }
    // Aggregate supplementary events: routing_strict_eval → routing_decision, skill_candidates → skill_route
    // routing_decision + routing_strict_eval share same span_id → single "routing" node
    for (const [key, entry] of merged) {
      if (entry.node.name === 'routing_strict_eval' || entry.node.name === 'routing_logic') {
        // Find matching routing_decision with same parent
        for (const [k2, e2] of merged) {
          if (e2.node.name === 'routing_decision' && entry.node.parentSpanId === e2.node.parentSpanId) {
            e2.node.details = { ...e2.node.details, strictEval: entry.node.details };
            e2.node.name = 'routing';
            merged.delete(key);
            break;
          }
        }
      }
      if (entry.node.name === 'skill_candidates') {
        for (const [k2, e2] of merged) {
          if (e2.node.name === 'skill_route' && entry.node.parentSpanId === e2.node.parentSpanId) {
            e2.node.details = { ...e2.node.details, candidates: entry.node.details };
            merged.delete(key);
            break;
          }
        }
      }
    }
    // Build tree: resolve parent_span_id → node id via spanToId map
    const nodes = [...merged.values()].sort((a, b) => (a.node.startTime || a.idx) - (b.node.startTime || b.idx) || a.idx - b.idx).map(m => m.node);
    const nodeMap = new Map<string, ENode>(nodes.map(n => [n.id, n]));
    const roots: ENode[] = [];
    for (const n of nodes) {
      const parentId = n.parentSpanId ? spanToId.get(n.parentSpanId) : undefined;
      if (parentId && nodeMap.has(parentId)) {
        const parent = nodeMap.get(parentId)!;
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

  // Auto-expand nodes that have children on first load
  useEffect(() => {
    const ids = new Set<string>();
    const walk = (nodes: ENode[]) => {
      for (const n of nodes) {
        if (n.children && n.children.length > 0) ids.add(n.id);
        if (n.children) walk(n.children);
      }
    };
    walk(dataNodes);
    if (ids.size === 0) return;
    setExpandedSubFlows(prev => {
      let changed = false;
      const next = new Set(prev);
      for (const id of ids) {
        if (!next.has(id)) { next.add(id); changed = true; }
      }
      return changed ? next : prev;
    });
  }, [dataNodes]);

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
      const hasTokenInfo = (n.details?.input_tokens ?? 0) > 0 || (n.details?.output_tokens ?? 0) > 0;
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
                {hasChildren && (<span style={{ color: 'var(--ev-text-muted)', fontSize: 9 }}>{n.children!.length} 子步骤</span>)}
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

    // Build edges: intra-group, sub-flow, and inter-group connections
    const groups = [...groupMap.keys()].filter(k => k !== '__root__');

    // Build tree edges: for each flattened node with parentId, create parent → child edge
    for (const n of flattenedNodes) {
      if (!n.parentId) continue;
      const parent = flattenedNodes.find(p => p.id === n.parentId);
      if (!parent) continue;
      const expanded = expandedSubFlows.has(parent.id);
      const edgeColor = n.status === 'running' ? '#3b82f6' :
                       n.status === 'completed' ? '#22c55e' :
                       n.status === 'failed' ? '#ef4444' : '#374151';
      edgeList.push({
        id: `${n.parentId}->${n.id}`,
        source: n.parentId,
        target: n.id,
        type: 'smoothstep',
        animated: n.status === 'running' && actualRunning,
        style: { stroke: edgeColor, strokeWidth: expanded ? 1.5 : 2, strokeDasharray: expanded ? '5,3' : undefined, opacity: n.status === 'idle' ? 0.3 : 0.8 },
        markerEnd: { type: MarkerType.ArrowClosed, color: edgeColor },
      });
    }

    // Inter-group edges: connect last node of group N → first node of group N+1
    if (groups.length > 1) {
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
            {(selectedNode.details?.input_tokens ?? 0) > 0 || (selectedNode.details?.output_tokens ?? 0) > 0 ? (
              <span style={{ color: 'var(--ev-text-secondary)' }}>
                输入: {selectedNode.details.input_tokens ?? 0} · 输出: {selectedNode.details.output_tokens ?? 0} tok
              </span>
            ) : null}
            {selectedNode.details?.cost ? (
              <span style={{ color: '#f59e0b' }}>${selectedNode.details.cost.toFixed(4)}</span>
            ) : null}
          </div>
          {selectedNode.details && (
            <StructuredDetail node={selectedNode} />
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
