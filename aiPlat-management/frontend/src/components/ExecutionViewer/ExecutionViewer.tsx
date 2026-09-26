import { useEffect, useMemo, useState, useRef } from 'react';
import ReactFlow, {
  Background, Controls, Edge, Node, Position, MarkerType,
  ReactFlowProvider, useReactFlow,
} from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';
import './tokens.css';
import type { ExecutionNode as ENode, ExecutionViewerProps } from './types';
import { useLiveEvents } from '../../hooks/useLiveEvents';
import { useLiveGraph } from '../../hooks/useLiveGraph';
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

/** Kinds shown on the transparent "执行轨迹" strip (user-facing actions). */
const ACTION_TRAIL_KINDS = new Set([
  'llm', 'reason', 'skill', 'tool', 'mcp', 'mcp_admin', 'routing', 'observe', 'done',
]);

function formatDur(ms?: number): string {
  if (ms == null || !Number.isFinite(ms) || ms <= 0) return '';
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}

function actionTrailLabel(n: ENode): string {
  const t = (n.type || '').toLowerCase();
  const raw = String(n.name || '');
  const bare = raw.replace(/^(技能·|LLM·|Skill · |Agent · )/i, '');
  if (t === 'llm' || t === 'reason') return `推理 ${bare || 'LLM'}`;
  if (t === 'skill') return `Skill · ${bare}`;
  if (t === 'tool') return `Tool · ${bare}`;
  if (t === 'mcp' || t === 'mcp_admin') return `MCP · ${bare}`;
  if (t === 'routing') {
    if (/skill_route/i.test(raw)) return '路由 · 选技能';
    if (/routing/i.test(raw) || raw === 'routing') return '路由决策';
    return `路由 · ${bare}`;
  }
  if (t === 'observe' || raw === 'observation') return '观察结果';
  if (t === 'done' || raw === 'auto_done') return '本轮完成';
  return bare || raw;
}

function nodeSemanticName(n: ENode): string {
  return String(n.details?.semanticName || n.name || '');
}

function isContainerNode(n: ENode): boolean {
  const role = String(n.details?.role || '');
  const semantic = nodeSemanticName(n);
  const nm = n.name || '';
  return (
    role === 'container'
    || semantic === 'agent_start' || semantic === 'agent_end'
    || semantic === 'skill_start' || semantic === 'skill_end'
    || nm === 'agent_start' || nm === 'agent_end'
    || nm === 'skill_start' || nm === 'skill_end'
    || /^step_\d+$/i.test(nm) || /^step_\d+$/i.test(semantic)
  );
}

function collectActionTrail(roots: ENode[]): ENode[] {
  const out: ENode[] = [];
  const walk = (nodes: ENode[]) => {
    for (const n of nodes) {
      const t = (n.type || '').toLowerCase();
      // Skip pure containers; keep real work units
      if (ACTION_TRAIL_KINDS.has(t) && !isContainerNode(n)) {
        out.push(n);
      }
      if (n.children?.length) walk(n.children);
    }
  };
  walk(roots);
  out.sort(
    (a, b) =>
      (Number(a.startTime || 0) - Number(b.startTime || 0)) ||
      a.name.localeCompare(b.name),
  );
  // Dedup routing noise: keep one routing per step window (same parentId)
  const seen = new Set<string>();
  const deduped: ENode[] = [];
  for (const n of out) {
    const t = (n.type || '').toLowerCase();
    if (t === 'routing') {
      const key = `routing:${n.parentId || n.parentSpanId || n.id}`;
      if (seen.has(key)) continue;
      seen.add(key);
    }
    // Dedup identical skill/tool work under the same parent (executor + syscall mirror)
    if (t === 'skill' || t === 'tool' || t === 'mcp' || t === 'mcp_admin') {
      const sem = nodeSemanticName(n);
      const key = `${t}:${n.parentId || n.parentSpanId || ''}:${sem}`;
      if (seen.has(key)) continue;
      seen.add(key);
    }
    deduped.push(n);
  }
  return deduped;
}

function stepActionSummary(step: ENode): string {
  const kids = step.children || [];
  const bits: string[] = [];
  for (const k of kids) {
    const t = (k.type || '').toLowerCase();
    if (t === 'skill') bits.push((k.name || '').replace(/^技能·/, ''));
    else if (t === 'tool') bits.push(`tool:${(k.name || '').replace(/^Tool · /, '')}`);
    else if (t === 'mcp' || t === 'mcp_admin') bits.push(`mcp:${k.name}`);
    else if (t === 'llm' || t === 'reason') bits.push('LLM');
  }
  // unique preserve order
  const uniq: string[] = [];
  for (const b of bits) {
    if (b && !uniq.includes(b)) uniq.push(b);
  }
  return uniq.slice(0, 4).join(' · ');
}

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
  for (const n of nodes) {
    const h = Math.max(64, Number((n.style as any)?.minHeight) || 64);
    const w = Math.max(220, Number((n.style as any)?.width) || 220);
    g.setNode(n.id, { width: w, height: h });
  }
  for (const e of edges) g.setEdge(e.source, e.target);
  dagre.layout(g);
  return {
    nodes: nodes.map((n) => {
      const dn = g.node(n.id);
      const w = Math.max(220, Number((n.style as any)?.width) || 220);
      const h = Math.max(64, Number((n.style as any)?.minHeight) || 64);
      return { ...n, position: { x: dn.x - w / 2, y: dn.y - h / 2 } };
    }),
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

  const rows: ({ label: string; text: string; color: string } | null)[] = [];

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
    case 'step': {
      rows.push(row('ReAct 轮次', node.name, '#8b5cf6'));
      if (args.reasoning) {
        rows.push(row('推理摘要', String(args.reasoning).slice(0, 500)));
      }
      const kids = Array.isArray(node.children) ? node.children : [];
      if (kids.length > 0) {
        const lines = kids.map((c) => {
          const dur = formatDur(c.duration);
          return `${c.icon || '•'} ${c.name}  [${c.type}]  ${c.status}${dur ? `  ${dur}` : ''}`;
        }).join('\n');
        rows.push(row(`本轮子步骤（${kids.length}）— 含 LLM / 技能`, lines, '#a78bfa'));
      } else {
        rows.push(row('本轮子步骤', '尚未挂到此节点（或仍在加载事件）', '#6b7280'));
      }
      if (args.action_result) {
        rows.push(row('动作结果', args.action_result, '#22c55e'));
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
      {rows.filter((r): r is { label: string; text: string; color: string } => r !== null).map((r, i) => (
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

const ExecutionViewer: React.FC<ExecutionViewerProps> = ({ nodes: propNodes, title, running, elapsed, summary, height = 500, onNodeClick, live, runId, replayRunId, onLiveStatusChange }) => {
  // Prefer authoritative RunGraph; fall back to legacy syscall event reconstruction.
  const graph = useLiveGraph(live ? (runId || null) : null);
  const useGraph = live && !!runId && graph.hasGraph;
  // Only fall back to legacy after RunGraph probe finished with no nodes
  const graphSettledNoGraph = live && !!runId && graph.status === 'done' && !graph.hasGraph;
  const { events: liveEvents, status: liveStatusLegacy, error: liveErrorLegacy } = useLiveEvents(
    graphSettledNoGraph ? (runId || null) : null,
  );
  const liveStatus = live && runId
    ? (useGraph || graph.status !== 'done' || graph.hasGraph ? graph.status : liveStatusLegacy)
    : liveStatusLegacy;
  const liveError = (live && runId && (useGraph || graph.status !== 'done'))
    ? graph.error
    : liveErrorLegacy;
  // Replay mode: step through historical events
  const replay = useReplayEvents(replayRunId || null);
  // Peak counters must be declared before any early return (hooks rules)
  const peakRef = useRef({ reactTotal: 0, reactDone: 0, nodeTotal: 0, nodeDone: 0, runId: '' });

  useEffect(() => {
    if (live && onLiveStatusChange) onLiveStatusChange(liveStatus);
  }, [live, liveStatus, onLiveStatusChange]);

  // Merge prop nodes with live-generated nodes + replay nodes
  // Unified status mapping: all backend statuses → frontend display status
  const mapStatus = (e: any): 'completed' | 'failed' | 'running' | 'warning' | 'idle' => {
    const s = (e.status || '').toLowerCase();
    // ReActLoop step_end uses LoopState: finished / observing (step cycle done)
    // routing emits eval / decision / selected as successful terminal markers
    if (
      s === 'ok' || s === 'success' || s === 'completed' || s === 'finished' || s === 'done'
      || s === 'observing' // step_end → observe phase completed for that step
      || s === 'eval' || s === 'decision' || s === 'selected'
    ) return 'completed';
    if (s === 'error' || s === 'failed' || s === 'policy_denied' || s === 'toolset_denied'
        || s === 'blocked' || s === 'prod_denied' || s === 'timeout') return 'failed';
    if (s === 'running' || s === 'pending' || s === 'accepted' || s === 'thinking' || s === 'acting') return 'running';
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
    const rawT = e.start_time ?? e.end_time;
    let startTime: number | undefined;
    if (typeof rawT === 'number' && Number.isFinite(rawT)) startTime = rawT;
    else if (typeof rawT === 'string' && rawT.trim()) {
      const n = Number(rawT);
      if (Number.isFinite(n) && n > 1e11) startTime = n; // epoch ms as string
      else {
        const p = Date.parse(rawT);
        if (Number.isFinite(p)) startTime = p;
      }
    }
    const rawName = String(e.name || e.kind || 'unknown');
    // Friendlier canvas labels for common syscall names
    let displayName = rawName.slice(0, 40);
    if (kind === 'llm' && /^generate$/i.test(rawName)) displayName = 'LLM·generate';
    else if (kind === 'skill' && rawName === 'skill_start') {
      const tgt = String(e.target_type || e.target_id || '').trim();
      displayName = (tgt ? `技能·${tgt}` : '技能·执行').slice(0, 40);
    } else if (kind === 'skill' && rawName === 'skill_end') {
      displayName = '技能·完成';
    } else if (kind === 'skill') displayName = `技能·${rawName}`.slice(0, 40);
    else if (kind === 'observe' || rawName === 'observation') displayName = 'observation';
    return {
    id: (e.span_id && e.name) ? `${e.span_id}::${e.name}` : (e.id || e.span_id || `${prefix}_${i}`),
    type: kind,
    name: displayName,
    status: mapStatus(e),
    startTime,
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
    // Oldest-first so start→end merges stably regardless of API order
    const eventTime = (e: any): number => {
      const raw = e?.start_time ?? e?.end_time;
      if (typeof raw === 'number' && Number.isFinite(raw)) return raw;
      if (typeof raw === 'string' && raw.trim()) {
        const n = Number(raw);
        if (Number.isFinite(n) && n > 1e11) return n;
        const p = Date.parse(raw);
        if (Number.isFinite(p)) return p;
      }
      return 0;
    };
    const ordered = [...events].sort((a, b) => eventTime(a) - eventTime(b));
    const merged = new Map<string, { node: ENode; idx: number; finalStatus: boolean }>();
    const spanToId = new Map<string, string>(); // span_id → first event's node id (for parent linking)
    for (let i = 0; i < ordered.length; i++) {
      const e = ordered[i];
      const key = (e.span_id && e.name) ? `${e.span_id}::${e.name}` : (e.id || e.span_id || `${prefix}_${i}`);
      const node = eventToNode(e, i, prefix);
      node.parentSpanId = e.parent_span_id || undefined;
      const existing = merged.get(key);
      // Track span_id → node_id mapping for parent lookup (keep first)
      const sid = e.span_id;
      if (sid && !spanToId.has(sid)) spanToId.set(sid, key);
      const isFinal = node.status === 'completed' || node.status === 'failed' || node.status === 'warning';
      // Never overwrite a final status with running/idle
      if (existing?.finalStatus && !isFinal) continue;
      if (!existing || isFinal || (node.status !== 'idle' && !existing.finalStatus)) {
        if (existing) {
          if (node.details && existing.node.details) {
            node.details.args = (node.details.args && Object.keys(node.details.args).length) ? node.details.args : existing.node.details.args;
            node.details.result = (node.details.result && Object.keys(node.details.result).length) ? node.details.result : existing.node.details.result;
            if (existing.node.duration && (!node.duration || node.duration <= 0)) {
              node.duration = existing.node.duration;
            }
          }
          // Keep earliest startTime
          if (existing.node.startTime && (!node.startTime || existing.node.startTime < node.startTime)) {
            node.startTime = existing.node.startTime;
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
        for (const [, e2] of merged) {
          if (e2.node.name === 'routing_decision' && entry.node.parentSpanId === e2.node.parentSpanId) {
            e2.node.details = { ...e2.node.details, strictEval: entry.node.details };
            e2.node.name = 'routing';
            if (entry.node.status === 'completed') e2.node.status = 'completed';
            merged.delete(key);
            break;
          }
        }
      }
      if (entry.node.name === 'skill_candidates') {
        for (const [, e2] of merged) {
          if (e2.node.name === 'skill_route' && entry.node.parentSpanId === e2.node.parentSpanId) {
            e2.node.details = { ...e2.node.details, candidates: entry.node.details };
            if (entry.node.status === 'completed') e2.node.status = 'completed';
            merged.delete(key);
            break;
          }
        }
      }
    }
    // If agent_end / skill_end completed, mark matching start completed (start may stay running)
    const agentEnded = [...merged.values()].some(
      (m) => m.node.name === 'agent_end' && (m.node.status === 'completed' || m.node.status === 'failed'),
    );
    if (agentEnded) {
      for (const entry of merged.values()) {
        if (entry.node.name === 'agent_start' && entry.node.status === 'running') {
          entry.node.status = 'completed';
          entry.finalStatus = true;
        }
      }
    }
    const skillEnded = [...merged.values()].some(
      (m) => m.node.name === 'skill_end' && (m.node.status === 'completed' || m.node.status === 'failed'),
    );
    if (skillEnded) {
      for (const entry of merged.values()) {
        if (entry.node.name === 'skill_start' && entry.node.status === 'running') {
          entry.node.status = 'completed';
          entry.finalStatus = true;
        }
      }
    }
    // When run produced a done/auto_done/agent_end/skill_end, any remaining running steps are completed
    const hasDone = [...merged.values()].some(
      (m) => (m.node.type === 'done' || m.node.name === 'auto_done' || m.node.name === 'agent_end' || m.node.name === 'skill_end')
        && m.node.status === 'completed',
    );
    if (hasDone) {
      for (const entry of merged.values()) {
        if (entry.node.status === 'running') {
          entry.node.status = 'completed';
          entry.finalStatus = true;
        }
      }
    }
    // Build tree: resolve parent_span_id → node.
    // Backend often reuses the same span_id for step_1/step_2 and agent_start/agent_end,
    // so a naive span→first-node map attaches children to the wrong parent and leaves
    // agent_end as an orphan root (dagre then makes step_N look like the graph origin).
    const nodes = [...merged.values()]
      .sort((a, b) => (Number(a.node.startTime || 0) - Number(b.node.startTime || 0)) || a.idx - b.idx)
      .map((m) => m.node);
    const nodeMap = new Map<string, ENode>(nodes.map((n) => [n.id, n]));

    // span_id → nodes that used that span (from id convention `${span}::${name}`)
    const nodesBySpan = new Map<string, ENode[]>();
    for (const n of nodes) {
      const idx = n.id.indexOf('::');
      if (idx <= 0) continue;
      const span = n.id.slice(0, idx);
      if (!nodesBySpan.has(span)) nodesBySpan.set(span, []);
      nodesBySpan.get(span)!.push(n);
    }

    const pickParent = (child: ENode): ENode | undefined => {
      const ps = child.parentSpanId;
      if (!ps) {
        // agent_end / skill_end with no parent → hang under matching start when present
        if ((child.name || '') === 'agent_end') {
          return nodes.find((n) => n.name === 'agent_start');
        }
        if ((child.name || '') === 'skill_end') {
          return nodes.find((n) => n.name === 'skill_start');
        }
        return undefined;
      }
      const cands = (nodesBySpan.get(ps) || []).filter((n) => n.id !== child.id);
      if (cands.length === 0) {
        const fid = spanToId.get(ps);
        return fid ? nodeMap.get(fid) : undefined;
      }
      if (cands.length === 1) return cands[0];

      const agentStart = cands.find((n) => n.name === 'agent_start');

      // Shared step span: assign child to the step active at child.startTime
      const steps = cands
        .filter((n) => /^step_\d+$/i.test(n.name || ''))
        .sort((a, b) => (Number(a.startTime || 0) - Number(b.startTime || 0)) || a.name.localeCompare(b.name));
      if (steps.length > 0) {
        const t = Number(child.startTime || 0);
        if (t > 0) {
          let chosen = steps[0];
          for (let i = 0; i < steps.length; i++) {
            const st = Number(steps[i].startTime || 0);
            if (st <= t) chosen = steps[i];
            else break;
          }
          return chosen;
        }
        return steps[steps.length - 1];
      }

      // Prefer agent_start over agent_end for shared agent span
      if (agentStart) return agentStart;
      const nonEnd = cands.find((n) => n.name !== 'agent_end');
      return nonEnd || cands[0];
    };

    const roots: ENode[] = [];
    for (const n of nodes) {
      n.children = undefined;
    }
    for (const n of nodes) {
      const parent = pickParent(n);
      if (parent && nodeMap.has(parent.id) && parent.id !== n.id) {
        if (!parent.children) parent.children = [];
        parent.children.push(n);
      } else {
        roots.push(n);
      }
    }

    // Order roots: agent_start / skill_start first, agent_end / skill_end last
    roots.sort((a, b) => {
      const rank = (n: ENode) => {
        if (n.name === 'agent_start' || n.name === 'skill_start') return 0;
        if (/^step_\d+$/i.test(n.name || '')) return 1;
        if (n.name === 'agent_end' || n.name === 'auto_done' || n.name === 'skill_end') return 3;
        return 2;
      };
      const ra = rank(a);
      const rb = rank(b);
      if (ra !== rb) return ra - rb;
      return (Number(a.startTime || 0) - Number(b.startTime || 0)) || a.name.localeCompare(b.name);
    });

    const sortKids = (list: ENode[]) => {
      for (const n of list) {
        if (n.children && n.children.length > 1) {
          n.children.sort(
            (a, b) =>
              (Number(a.startTime || 0) - Number(b.startTime || 0)) ||
              a.name.localeCompare(b.name),
          );
          sortKids(n.children);
        }
      }
    };
    sortKids(roots);

    return roots;
  };

  const dataNodes: ENode[] = useMemo(() => {
    // Authoritative RunGraph projection — no mergeEvents heuristics
    if (useGraph && graph.roots.length > 0) {
      return graph.roots;
    }
    let roots: ENode[] = [];
    if (live && liveEvents.length > 0) {
      roots = mergeEvents(liveEvents, 'ev');
    } else if (replayRunId && replay.visibleEvents.length > 0) {
      roots = mergeEvents(replay.visibleEvents, 'replay');
    } else {
      roots = propNodes || [];
    }
    // Legacy only: if SSE already done, force-close leftover running containers
    if (!useGraph && live && liveStatus === 'done') {
      const markDone = (nodes: ENode[]) => {
        for (const n of nodes) {
          if (n.status === 'running') n.status = 'completed';
          if (n.children?.length) markDone(n.children);
        }
      };
      markDone(roots);
    }
    return roots;
  }, [useGraph, graph.roots, live, liveEvents, liveStatus, propNodes, replayRunId, replay.visibleEvents]);

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

  // Auto-expand container roots + steps that have children (works for RunGraph labels).
  useEffect(() => {
    const next = new Set<string>();
    const walk = (nodes: ENode[]) => {
      for (const n of nodes) {
        const kids = n.children || [];
        const semantic = nodeSemanticName(n);
        const role = String(n.details?.role || '');
        if (kids.length > 0 && (
          role === 'container'
          || semantic === 'agent_start' || semantic === 'skill_start'
          || n.name === 'agent_start' || n.name === 'skill_start'
          || /^step_\d+$/i.test(n.name || '') || /^step_\d+$/i.test(semantic)
        )) {
          next.add(n.id);
        }
        if (kids.length) walk(kids);
      }
    };
    walk(dataNodes);

    setExpandedSubFlows((prev) => {
      // Union: never collapse a step the user already opened
      const merged = new Set(prev);
      for (const id of next) merged.add(id);
      if (merged.size === prev.size && [...merged].every((id) => prev.has(id))) return prev;
      return merged;
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
              <div style={{ fontSize: 10, marginTop: 2, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
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
                {n.parentId && (
                  <span style={{ color: 'var(--ev-text-muted)', fontSize: 9 }}>
                    └ 子步骤
                  </span>
                )}
              </div>
              {hasChildren && (
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); toggleSubFlow(n.id); }}
                  style={{
                    marginTop: 6,
                    width: '100%',
                    background: isExpanded ? 'rgba(99,102,241,0.25)' : 'var(--ev-bg-primary)',
                    border: '1px solid var(--ev-accent, #6366f1)',
                    borderRadius: 6,
                    color: 'var(--ev-text-primary)',
                    cursor: 'pointer',
                    fontSize: 11,
                    fontWeight: 600,
                    padding: '4px 8px',
                    lineHeight: '16px',
                    textAlign: 'left',
                  }}
                  title={isExpanded ? '折叠子流程' : '展开子流程（LLM / 技能等）'}
                >
                  {isExpanded ? '▼ 收起' : '▶ 展开'} {n.children!.length} 个子步骤
                </button>
              )}
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
          border: sc.ring,
          borderRadius: 10,
          width: 240,
          minHeight: hasChildren ? 92 : 64,
          fontSize: 12,
          color: 'var(--ev-text-primary)',
          opacity: n.status === 'idle' ? 0.45 : 1,
          boxShadow: n.status === 'running' ? `0 0 12px ${color}55` : undefined,
          overflow: 'visible',
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

    // Sibling timeline: step_1 → step_2 → agent_end under the same parent
    const kidsByParent = new Map<string, ENode[]>();
    for (const n of flattenedNodes) {
      if (!n.parentId) continue;
      if (!kidsByParent.has(n.parentId)) kidsByParent.set(n.parentId, []);
      kidsByParent.get(n.parentId)!.push(n);
    }
    for (const [, kids] of kidsByParent) {
      const timeline = kids
        .filter((k) => /^step_\d+$/i.test(k.name || '') || k.name === 'agent_end' || k.name === 'auto_done')
        .sort(
          (a, b) =>
            (Number(a.startTime || 0) - Number(b.startTime || 0)) ||
            a.name.localeCompare(b.name),
        );
      for (let i = 1; i < timeline.length; i++) {
        const a = timeline[i - 1];
        const b = timeline[i];
        const id = `seq_${a.id}->${b.id}`;
        if (edgeList.some((e) => e.id === id || (e.source === a.id && e.target === b.id))) continue;
        edgeList.push({
          id,
          source: a.id,
          target: b.id,
          type: 'smoothstep',
          animated: false,
          style: { stroke: '#94a3b8', strokeWidth: 2, opacity: 0.75 },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
        });
      }
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

  // Linear spine for "where am I" — ignore side branches (routing/context)
  const spine = useMemo(() => {
    const isStart = (n: ENode) => {
      const s = nodeSemanticName(n);
      return s === 'agent_start' || s === 'skill_start' || n.name === 'agent_start' || n.name === 'skill_start';
    };
    const isSpineKid = (c: ENode) => {
      const s = nodeSemanticName(c);
      // Spine shows ReAct rounds / terminal markers only — not every skill/tool work leaf
      // (those belong on the action trail).
      return (
        /^step_\d+$/i.test(c.name || '') || /^step_\d+$/i.test(s)
        || s === 'agent_end' || s === 'auto_done' || s === 'skill_end'
        || c.name === 'agent_end' || c.name === 'auto_done' || c.name === 'skill_end'
      );
    };
    let start = dataNodes.find(isStart) || dataNodes.find((n) => String(n.details?.role || '') === 'container');
    // Standalone skill run: single work root is both spine and trail
    if (!start && dataNodes.length === 1 && (dataNodes[0].type === 'skill' || dataNodes[0].type === 'tool')) {
      start = dataNodes[0];
    }
    const items: ENode[] = [];
    if (start) items.push(start);
    const kids = [...((start?.children) || [])]
      .filter(isSpineKid)
      .sort(
        (a, b) =>
          (Number(a.startTime || 0) - Number(b.startTime || 0)) ||
          a.name.localeCompare(b.name),
      );
    items.push(...kids);
    if (!start) {
      for (const n of dataNodes) {
        if (isSpineKid(n) || /^step_\d+$/i.test(nodeSemanticName(n))) items.push(n);
      }
    }
    return items;
  }, [dataNodes]);

  /** Flat, time-ordered user-facing actions (LLM / Skill / Tool / MCP / …). */
  const actionTrail = useMemo(() => collectActionTrail(dataNodes), [dataNodes]);

  const focusNode = (n: ENode) => {
    setSelectedNode(n);
    setExpandedSubFlows((prev) => {
      const next = new Set(prev);
      // Expand ancestors so the canvas shows the node
      const byId = new Map<string, ENode>();
      const index = (nodes: ENode[]) => {
        for (const x of nodes) {
          byId.set(x.id, x);
          if (x.children) index(x.children);
        }
      };
      index(dataNodes);
      let cur: ENode | undefined = n;
      const guard = new Set<string>();
      while (cur && !guard.has(cur.id)) {
        guard.add(cur.id);
        next.add(cur.id);
        const pid = cur.parentId;
        if (!pid) {
          // walk via parentSpan / name fallback: expand all steps + agent_start
          break;
        }
        cur = byId.get(pid);
      }
      for (const root of dataNodes) {
        if (root.name === 'agent_start') next.add(root.id);
        for (const c of root.children || []) {
          if (/^step_\d+$/i.test(c.name || '')) next.add(c.id);
        }
      }
      return next;
    });
  };

  const currentFocus = useMemo(() => {
    const running = flattenedNodes.find((n) => n.status === 'running');
    if (running) return running;
    const spineRunning = spine.find((n) => n.status === 'running');
    if (spineRunning) return spineRunning;
    return spine.filter((n) => n.status === 'completed').slice(-1)[0] || null;
  }, [flattenedNodes, spine]);

  if (flattenedNodes.length === 0) {
    // Keep "loading" copy while live — including premature SSE done (status may
    // briefly be done before poll recovers events from a still-running agent).
    const waiting = live && liveStatus !== 'error';
    return (
      <div
        style={{
          height: Math.max(200, height),
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          border: '1px solid var(--ev-border)',
          borderRadius: 12,
          color: 'var(--ev-text-muted)',
          fontSize: 13,
          background: 'var(--ev-bg-primary)',
        }}
      >
        <div>{waiting ? '⏳ 正在加载执行步骤…' : '暂无执行步骤事件'}</div>
        {live && (
          <div style={{ fontSize: 11, opacity: 0.7 }}>
            状态: {liveStatus}{liveError ? ` · ${liveError}` : ''}
            {runId ? ` · ${runId}` : ''}
          </div>
        )}
      </div>
    );
  }

  const done = flattenedNodes.filter(n => n.status === 'completed' || n.status === 'failed' || n.status === 'warning').length;
  // Stable ReAct progress: count step_* (+ agent_end); never decrease (SSE reconnect used to flash 0/1).
  const reactSteps = flattenedNodes.filter(
    (n) => /^step_\d+$/i.test(n.name || '') || n.name === 'agent_end' || n.name === 'auto_done' || n.name === 'skill_end',
  );
  const reactDone = reactSteps.filter(
    (n) => n.status === 'completed' || n.status === 'failed' || n.status === 'warning',
  ).length;
  if ((runId || replayRunId || '') !== peakRef.current.runId) {
    peakRef.current = {
      reactTotal: 0,
      reactDone: 0,
      nodeTotal: 0,
      nodeDone: 0,
      runId: runId || replayRunId || '',
    };
  }
  peakRef.current.reactTotal = Math.max(peakRef.current.reactTotal, reactSteps.length);
  peakRef.current.reactDone = Math.max(peakRef.current.reactDone, reactDone);
  peakRef.current.nodeTotal = Math.max(peakRef.current.nodeTotal, flattenedNodes.length);
  peakRef.current.nodeDone = Math.max(peakRef.current.nodeDone, done);
  const progressLabel =
    peakRef.current.reactTotal > 0
      ? `轮次 ${peakRef.current.reactDone}/${peakRef.current.reactTotal}`
      : `${peakRef.current.nodeDone}/${peakRef.current.nodeTotal}`;

  const hasGroups = flattenedNodes.some(n => n.group && n.group !== '__root__');
  const maxColNodes = hasGroups
    ? Math.max(...Object.values(flattenedNodes.reduce((acc, n) => {
        const g = n.group || '__root__';
        acc[g] = (acc[g] || 0) + 1;
        return acc;
      }, {} as Record<string, number>)))
    : 0;
  const vHeight = hasGroups
    ? Math.max(height, Math.min(maxColNodes * 96 + 60, 1200))
    : Math.max(height, Math.min(flattenedNodes.length * 72 + 80, 1200));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, height: '100%', minHeight: 0 }}>
      {/* Progress bar */}
      {(title || summary || live) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '0 4px', flexShrink: 0 }}>
          {title && <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--ev-text-primary)' }}>{title}</span>}
          {(actualRunning || liveStatus === 'streaming' || liveStatus === 'connecting') && (
            <span style={{ fontSize: 12, color: '#3b82f6', display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ animation: 'spin 1s linear infinite' }}>⚙</span> {progressLabel}
              {elapsed != null ? ` · ${elapsed}s` : ''}
              <span style={{ color: 'var(--ev-text-muted)', marginLeft: 6 }}>
                节点 {peakRef.current.nodeDone}/{peakRef.current.nodeTotal}
              </span>
            </span>
          )}
          {!actualRunning && liveStatus === 'done' && (
            <span style={{ fontSize: 11, color: 'var(--ev-text-secondary)' }}>
              {progressLabel} · 节点 {peakRef.current.nodeDone}/{peakRef.current.nodeTotal}
            </span>
          )}
          {summary && (
            <span style={{ fontSize: 11, color: 'var(--ev-text-secondary)' }}>
              {summary.pass}✅ {summary.warn}⚠️ {summary.fail}❌
            </span>
          )}
          <div style={{ flex: 1 }} />
        </div>
      )}

      {/* Linear main path — ReAct rounds */}
      {spine.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: 6,
            padding: '8px 10px',
            borderRadius: 8,
            border: '1px solid var(--ev-border)',
            background: 'var(--ev-bg-secondary)',
            flexShrink: 0,
          }}
        >
          <span style={{ fontSize: 11, color: 'var(--ev-text-muted)', marginRight: 4 }}>主路径</span>
          {spine.map((n, i) => {
            const active = currentFocus?.id === n.id || (currentFocus?.parentId === n.id);
            const runDone = spine.some(
              (x) => {
                const s = nodeSemanticName(x);
                return (
                  (s === 'agent_end' || s === 'auto_done' || s === 'skill_end'
                    || x.name === 'agent_end' || x.name === 'auto_done' || x.name === 'skill_end')
                  && (x.status === 'completed' || x.status === 'failed')
                );
              },
            )
              || (!actualRunning && liveStatus === 'done');
            const childRunning = (n.children || []).some((c) => c.status === 'running');
            const running = !runDone && (n.status === 'running' || childRunning);
            const doneN = n.status === 'completed' || n.status === 'failed'
              || (runDone && (
                nodeSemanticName(n) === 'agent_start' || nodeSemanticName(n) === 'skill_start'
                || n.name === 'agent_start' || n.name === 'skill_start'
                || String(n.details?.role || '') === 'container'
              ));
            const color = running ? '#3b82f6' : doneN ? '#22c55e' : '#6b7280';
            const summary = /^step_\d+$/i.test(n.name || '') ? stepActionSummary(n) : '';
            return (
              <span key={n.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                {i > 0 && <span style={{ color: '#64748b' }}>→</span>}
                <button
                  type="button"
                  onClick={() => focusNode(n)}
                  style={{
                    fontSize: 12,
                    fontWeight: active || running ? 700 : 500,
                    color,
                    background: running ? 'rgba(59,130,246,0.15)' : active ? 'rgba(34,197,94,0.1)' : 'transparent',
                    border: `1px solid ${running ? '#3b82f6' : active ? '#22c55e' : 'var(--ev-border)'}`,
                    borderRadius: 6,
                    padding: summary ? '4px 8px' : '2px 8px',
                    cursor: 'pointer',
                    boxShadow: running ? '0 0 8px rgba(59,130,246,0.35)' : undefined,
                    textAlign: 'left',
                    lineHeight: 1.25,
                  }}
                  title={summary ? `${n.name} · ${summary}` : `${n.name} · ${n.status}`}
                >
                  <div>{running ? '▶ ' : doneN ? '✓ ' : ''}{n.name}</div>
                  {summary && (
                    <div style={{ fontSize: 10, fontWeight: 500, color: '#94a3b8', marginTop: 2 }}>
                      {summary}
                    </div>
                  )}
                </button>
              </span>
            );
          })}
          {currentFocus && (
            <span style={{ marginLeft: 'auto', fontSize: 11, color: '#93c5fd' }}>
              当前：{currentFocus.name}
              {currentFocus.parentId ? `（属 ${flattenedNodes.find((x) => x.id === currentFocus.parentId)?.name || '…'}）` : ''}
            </span>
          )}
        </div>
      )}

      {/* Transparent action trail — LLM / Skill / Tool / MCP in order */}
      {actionTrail.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            padding: '8px 10px',
            borderRadius: 8,
            border: '1px solid rgba(99,102,241,0.35)',
            background: 'rgba(99,102,241,0.06)',
            flexShrink: 0,
            maxHeight: 120,
            overflowY: 'auto',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: '#a5b4fc' }}>执行轨迹</span>
            <span style={{ fontSize: 10, color: 'var(--ev-text-muted)' }}>
              按时间列出本轮实际动作（推理 / Skill / Tool / MCP），点击可定位
            </span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
            {actionTrail.map((n, i) => {
              const running = n.status === 'running';
              const failed = n.status === 'failed';
              const doneN = n.status === 'completed' || n.status === 'warning';
              const color = failed ? '#ef4444' : running ? '#3b82f6' : doneN ? (n.color || '#22c55e') : '#6b7280';
              const dur = formatDur(n.duration);
              const selected = selectedNode?.id === n.id;
              return (
                <span key={n.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                  {i > 0 && <span style={{ color: '#64748b', fontSize: 11 }}>→</span>}
                  <button
                    type="button"
                    onClick={() => focusNode(n)}
                    style={{
                      fontSize: 11,
                      fontWeight: selected || running ? 700 : 500,
                      color,
                      background: selected ? 'rgba(99,102,241,0.2)' : running ? 'rgba(59,130,246,0.12)' : 'var(--ev-bg-primary)',
                      border: `1px solid ${selected ? '#6366f1' : color}`,
                      borderRadius: 6,
                      padding: '3px 8px',
                      cursor: 'pointer',
                      maxWidth: 220,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                    title={`${actionTrailLabel(n)} · ${n.status}${dur ? ` · ${dur}` : ''}`}
                  >
                    {n.icon ? `${n.icon} ` : ''}
                    {running ? '▶ ' : failed ? '✕ ' : doneN ? '✓ ' : ''}
                    {actionTrailLabel(n)}
                    {dur ? ` · ${dur}` : ''}
                  </button>
                </span>
              );
            })}
          </div>
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

      {/* Flow canvas — fill remaining space; pan/zoom always enabled */}
      <div style={{
        border: '1px solid var(--ev-border)', borderRadius: 12, overflow: 'hidden',
        height: vHeight, flex: 1, minHeight: 240, width: '100%',
      }}>
        <ReactFlowProvider>
          <FlowCanvas
            nodes={nodes}
            edges={edges}
            flattenedNodes={flattenedNodes}
            onNodeClick={onNodeClick}
            setSelectedNode={setSelectedNode}
          />
        </ReactFlowProvider>
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
              background: 'transparent', border: 'none', color: 'var(--ev-text-muted)',
              cursor: 'pointer', fontSize: 16, lineHeight: 1,
            }}>✕</button>
          </div>
          <div style={{ display: 'flex', gap: 16, fontSize: 11, color: 'var(--ev-text-secondary)' }}>
            <span>类型: {selectedNode.type}</span>
            <span>状态: {selectedNode.status}</span>
            {selectedNode.duration ? <span>耗时: {selectedNode.duration}ms</span> : null}
          </div>
          <StructuredDetail node={selectedNode} />
        </div>
      )}
    </div>
  );
};

/** Inner canvas — needs ReactFlowProvider for fitView after layout. */
function FlowCanvas({
  nodes, edges, flattenedNodes, onNodeClick, setSelectedNode,
}: {
  nodes: Node[];
  edges: Edge[];
  flattenedNodes: ENode[];
  onNodeClick?: (node: ENode) => void;
  setSelectedNode: (n: ENode | null) => void;
}) {
  const { fitView } = useReactFlow();
  const fittedFor = useRef(0);

  useEffect(() => {
    if (nodes.length === 0) return;
    // Refit when node count changes (new events / expand)
    if (nodes.length !== fittedFor.current) {
      fittedFor.current = nodes.length;
      const t = window.setTimeout(() => {
        try { fitView({ padding: 0.25, duration: 200 }); } catch { /* ignore */ }
      }, 60);
      return () => window.clearTimeout(t);
    }
  }, [nodes.length, fitView]);

  return (
    <>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        minZoom={0.1}
        maxZoom={1.5}
        defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
        panOnDrag
        zoomOnScroll
        panOnScroll={false}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_e, node) => {
          const dn = flattenedNodes.find(d => d.id === node.id);
          if (dn) setSelectedNode(dn);
          if (onNodeClick) onNodeClick(dn || flattenedNodes[0]);
        }}
        style={{ width: '100%', height: '100%' }}
      >
        <Background color="#1f2937" gap={24} />
        <Controls showInteractive />
      </ReactFlow>
      <style>{`
        .react-flow__controls-button{background:#1f2937!important;border-color:#374151!important}
        .react-flow__controls-button:hover{background:#374151!important}
        .react-flow__controls-button svg{fill:#9ca3af!important}
        .react-flow__attribution{display:none!important}
        @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
      `}</style>
    </>
  );
}

// StructuredDetail already exported above
export default ExecutionViewer;
