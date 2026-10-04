import { useEffect, useMemo, useState, useRef, useCallback } from 'react';
import ReactFlow, {
  Background, Controls, Edge, Node, Position, MarkerType,
  ReactFlowProvider, useReactFlow, applyNodeChanges, applyEdgeChanges,
  type NodeChange, type EdgeChange,
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
  routing:    { icon: '🧭', color: '#3b82f6', label: '路由' },
  skill:      { icon: '⚡', color: '#8b5cf6', label: 'Skill' },
  agent:      { icon: '🤖', color: '#3b82f6', label: 'Agent' },
  step:       { icon: '🔄', color: '#8b5cf6', label: 'Step' },
  done:       { icon: '✅', color: '#22c55e', label: 'Done' },
  reason:     { icon: '🧠', color: '#6366f1', label: 'LLM' },
  context:    { icon: '📎', color: '#0ea5e9', label: '准备' },
  observe:    { icon: '👁', color: '#ec4899', label: '观察' },
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

/** Kinds shown on the process trail — include prep/context so every step is visible. */
const ACTION_TRAIL_KINDS = new Set([
  'llm', 'reason', 'skill', 'tool', 'mcp', 'mcp_admin', 'routing', 'observe', 'done',
  'context', 'gate', 'security', 'hitl', 'diag', 'trace', 'runtime', 'metric',
]);

function formatDur(ms?: number): string {
  if (ms == null || !Number.isFinite(ms) || ms <= 0) return '';
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}

/** Backend often stores unix seconds; Date.now() is ms. */
function startTimeMs(startTime?: number): number | undefined {
  if (startTime == null || !Number.isFinite(startTime) || startTime <= 0) return undefined;
  return startTime < 1e12 ? startTime * 1000 : startTime;
}

/** While running, duration_ms is null → UI used to show 0ms; prefer wall-clock elapsed. */
function effectiveDurationMs(n: Pick<ENode, 'status' | 'startTime' | 'duration'>, nowMs: number): number {
  if (n.status === 'running') {
    const start = startTimeMs(n.startTime);
    if (start != null) return Math.max(0, nowMs - start);
  }
  const d = n.duration;
  return d != null && Number.isFinite(d) && d > 0 ? d : 0;
}

/** Prefer chronological process order; keep LLM-prep markers just before generate. */
function trailSortKey(n: ENode): number {
  const t = Number(n.startTime || 0);
  const sem = nodeSemanticName(n).toLowerCase();
  const nm = (n.name || '').toLowerCase();
  if (/context_snapshot/i.test(sem) || /context_snapshot/i.test(nm)) return t - 0.003;
  if (/pre_llm_prep/i.test(sem) || /pre_llm_prep/i.test(nm)) return t - 0.002;
  if (/llm_enter/i.test(sem) || /llm_enter/i.test(nm)) return t - 0.001;
  return t;
}

function actionTrailLabel(n: ENode): string {
  const t = (n.type || '').toLowerCase();
  const raw = String(n.name || '');
  const bare = raw.replace(/^(技能·|LLM·|Skill · |Agent · |路由 · |准备 · |观察 · |完成 · )/i, '');
  const sem = nodeSemanticName(n);
  const args = (n.details?.args && typeof n.details.args === 'object') ? (n.details.args as Record<string, unknown>) : {};
  const skillFromArgs = String(
    args.skill || args.skill_id || args.selected_skill || args.selected_name || args.selected_skill_id || '',
  ).trim();
  // Real skill execution (not routing telemetry)
  if (t === 'skill' && !/skill_route/i.test(sem) && !/skill_route/i.test(bare)) {
    const id = skillFromArgs || bare || '执行';
    return `Skill · ${id}`;
  }
  if (t === 'llm' || t === 'reason') {
    if (/refresh|刷新/i.test(bare) || /refresh|刷新/i.test(sem)) return '推理 · LLM 刷新';
    return `推理 · ${bare || 'generate'}`;
  }
  if (t === 'routing' || /^skill_route$/i.test(bare) || /^skill_route$/i.test(raw) || /^routing_/i.test(bare) || /^routing_/i.test(sem) || /skill_route/i.test(sem)) {
    if (/routing_decision/i.test(sem) || /routing_decision/i.test(bare)) {
      const who = skillFromArgs && skillFromArgs !== 'none' ? skillFromArgs : '';
      return who ? `路由 · 决策→${who}` : '路由 · 决策';
    }
    if (/routing_strict_eval/i.test(sem) || /routing_strict/i.test(bare)) {
      const who = skillFromArgs && skillFromArgs !== 'none' ? skillFromArgs : '';
      return who ? `路由 · 严格评估(${who})` : '路由 · 严格评估';
    }
    if (/routing_explain/i.test(sem) || /routing_explain/i.test(bare)) {
      return '路由 · 解释';
    }
    if (/skill_route/i.test(sem) || /skill_route/i.test(bare) || /skill_route/i.test(raw)) {
      if (skillFromArgs && skillFromArgs !== 'none') return `路由 · 选中 ${skillFromArgs}`;
      return '路由 · 选技能';
    }
    if (skillFromArgs && skillFromArgs !== 'none') return `路由 · ${skillFromArgs}`;
    return '路由 · 选技能';
  }
  if (t === 'tool') return `Tool · ${bare}`;
  if (t === 'mcp' || t === 'mcp_admin') return `MCP · ${bare}`;
  if (t === 'context' || /pre_llm_prep|llm_enter|context_snapshot/i.test(sem) || /pre_llm_prep|llm_enter|context_snapshot/i.test(bare)) {
    if (/pre_llm_prep/i.test(sem) || /pre_llm_prep/i.test(bare)) return '准备 · LLM 前置';
    if (/llm_enter/i.test(sem) || /llm_enter/i.test(bare)) return '准备 · 进入推理';
    if (/context_snapshot/i.test(sem) || /context_snapshot/i.test(bare)) return '准备 · 上下文快照';
    return `准备 · ${bare || sem || '上下文'}`;
  }
  if (t === 'observe' || raw === 'observation' || sem === 'observation') return '观察 · 本轮结果';
  if (t === 'done' || raw === 'auto_done' || /skill_delivery/i.test(sem) || /skill_delivery/i.test(bare)) {
    if (/skill_delivery/i.test(sem) || /skill_delivery/i.test(bare)) return '完成 · Skill 交付';
    if (raw === 'auto_done' || sem === 'auto_done') return '完成 · 自动收尾';
    if (raw === 'final_answer' || sem === 'final_answer') return '完成 · 最终回答';
    return '完成 · 本轮结束';
  }
  if (t === 'gate' || t === 'security') return `门禁 · ${bare || sem || t}`;
  if (t === 'hitl') return `人工 · ${bare || '待确认'}`;
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

function bareActionName(n: ENode): string {
  return String(n.name || '')
    .replace(/^(技能·|LLM·|Skill · |Agent · |Tool · |MCP · )/i, '')
    .trim();
}

function collectActionTrail(roots: ENode[], spineExclude: ENode[] = []): ENode[] {
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
  // Spine session roots (e.g. Skill · X) must not reappear as trail chips.
  // Skill-only runs: spine is skill_start / skill root → omit ALL skill-kind from trail
  // (routing / LLM / tool under it remain). Agent runs keep skills on the trail.
  const spineIds = new Set(spineExclude.map((s) => s.id));
  const spineIsSkillSession = spineExclude.some((s) => {
    const sem = nodeSemanticName(s);
    const t = (s.type || '').toLowerCase();
    return (
      sem === 'skill_start'
      || sem === 'skill_end'
      || (t === 'skill' && !s.parentId)
      || (String(s.details?.role || '') === 'container' && (t === 'skill' || /skill/i.test(String(s.name || ''))))
    );
  });
  const spineSkillLabels = new Set(
    spineExclude
      .map((s) => bareActionName(s).toLowerCase())
      .filter(Boolean),
  );
  // Also index semantic names (requirement_analysis vs Skill · requirement_analysis)
  for (const s of spineExclude) {
    const sem = nodeSemanticName(s).toLowerCase();
    if (sem && sem !== 'skill_start' && sem !== 'skill_end') spineSkillLabels.add(sem);
  }

  // Dedup routing noise: keep one routing per step window (same parentId)
  const seen = new Set<string>();
  const deduped: ENode[] = [];
  for (const n of out) {
    if (spineIds.has(n.id)) continue;
    const t = (n.type || '').toLowerCase();
    if (t === 'skill') {
      if (spineIsSkillSession) continue;
      const label = bareActionName(n).toLowerCase();
      const sem = nodeSemanticName(n).toLowerCase();
      if (label && spineSkillLabels.has(label)) continue;
      if (sem && spineSkillLabels.has(sem)) continue;
      // Same visible title as any spine chip
      if ([...spineSkillLabels].some((L) => L && (label === L || sem === L || label.includes(L) || L.includes(label)))) {
        continue;
      }
    }
    if (t === 'routing') {
      // Keep decision / strict_eval / skill_route as separate chips (different labels)
      const sem = nodeSemanticName(n).toLowerCase() || bareActionName(n).toLowerCase() || n.id;
      const key = `routing:${n.parentId || n.parentSpanId || ''}:${sem}`;
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
    if (t === 'routing' || /skill_route|routing_/i.test(String(k.name || '')) || /skill_route|routing_/i.test(nodeSemanticName(k))) {
      bits.push(actionTrailLabel(k).replace(/^路由 · /, ''));
    } else if (t === 'skill') {
      const nm = (k.name || '').replace(/^(技能·|Skill · )/i, '');
      const args = (k.details?.args && typeof k.details.args === 'object')
        ? (k.details.args as Record<string, unknown>)
        : {};
      const sid = String(args.skill || args.skill_id || '').trim();
      bits.push(/skill_route/i.test(nm) && sid ? sid : nm);
    } else if (t === 'tool') bits.push(`tool:${(k.name || '').replace(/^Tool · /, '')}`);
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

/** All descendants under a step (depth-first, time-sorted siblings). */
function collectRoundDescendants(step: ENode): ENode[] {
  const out: ENode[] = [];
  const walk = (nodes: ENode[]) => {
    const sorted = [...nodes].sort(
      (a, b) =>
        trailSortKey(a) - trailSortKey(b) ||
        a.name.localeCompare(b.name),
    );
    for (const n of sorted) {
      out.push(n);
      if (n.children?.length) walk(n.children);
    }
  };
  walk(step.children || []);
  return out;
}

type RoundSection = {
  id: string;
  label: string;
  step: ENode;
  /** Ordered user-facing actions for this round's mini-path. */
  path: ENode[];
  /** Every descendant node under the round (including path nodes). */
  nodes: ENode[];
};

/**
 * Build per-ReAct-round sections from spine step_* containers.
 * Fallback: when no step_* exists (standalone skill), one synthetic section.
 */
function buildRoundSections(spine: ENode[], roots: ENode[]): RoundSection[] {
  const steps = spine.filter((n) => /^step_\d+$/i.test(n.name || '') || /^step_\d+$/i.test(nodeSemanticName(n)));
  if (steps.length > 0) {
    return steps.map((step) => {
      const all = collectRoundDescendants(step);
      // Full process trail: every non-container child in time order (prep/route/llm/skill/…)
      const path = all.filter((n) => !isContainerNode(n));
      const num = (step.name || nodeSemanticName(step) || '').match(/step_(\d+)/i)?.[1];
      return {
        id: step.id,
        label: num ? `轮次 ${num}` : (step.name || '轮次'),
        step,
        path,
        nodes: all,
      };
    });
  }
  // Standalone skill / tool / agent session without step_* containers.
  // Use the action trail as 该轮路径; flatten the whole tree for 本轮节点
  // (not only children of agent_start — those miss generate/route leaves).
  const trail = collectActionTrail(roots, spine);
  if (trail.length === 0 && spine.length === 0) return [];
  const workRoot = spine.find(isReactRoundStep) || spine[0] || roots[0];
  if (!workRoot) return [];
  const seen = new Set<string>();
  const all: ENode[] = [];
  const push = (n: ENode) => {
    if (seen.has(n.id)) return;
    seen.add(n.id);
    all.push(n);
  };
  for (const r of roots) {
    push(r);
    collectRoundDescendants(r).forEach(push);
  }
  for (const n of trail) push(n);
  const path = trail.length
    ? trail
    : all.filter((n) => ACTION_TRAIL_KINDS.has((n.type || '').toLowerCase()) && !isContainerNode(n));
  return [{
    id: workRoot.id,
    label: '本轮',
    step: workRoot,
    path,
    nodes: all.filter((n) => !isContainerNode(n) || path.some((p) => p.id === n.id)),
  }];
}

function nodeChipLabel(n: ENode): string {
  if (ACTION_TRAIL_KINDS.has((n.type || '').toLowerCase()) && !isContainerNode(n)) {
    return actionTrailLabel(n);
  }
  const t = (n.type || '').toLowerCase();
  const bare = bareActionName(n) || n.name || t || '节点';
  const meta = CANVAS_NODES[t];
  if (meta && meta.label !== 'Unknown') return `${meta.label} · ${bare}`;
  return bare;
}

/** Which ReAct round / session lane a node belongs to (for column layout). */
function resolveRoundGroup(n: ENode, byId: Map<string, ENode>): string {
  let cur: ENode | undefined = n;
  const guard = new Set<string>();
  while (cur && !guard.has(cur.id)) {
    guard.add(cur.id);
    const s = nodeSemanticName(cur);
    const nm = cur.name || '';
    if (/step_\d+/i.test(nm) || /step_\d+/i.test(s) || (cur.type || '').toLowerCase() === 'step') {
      const num = (nm.match(/step_(\d+)/i) || s.match(/step_(\d+)/i))?.[1];
      return num ? `轮次${num}` : (nm || s || '轮次');
    }
    if (
      s === 'agent_end' || s === 'skill_end' || s === 'auto_done'
      || nm === 'agent_end' || nm === 'skill_end' || nm === '完成' || nm === 'auto_done'
    ) {
      return '收尾';
    }
    if (
      s === 'agent_start' || s === 'skill_start'
      || nm === 'agent_start' || nm === 'skill_start'
      || String(cur.details?.role || '') === 'container' && ((cur.type || '') === 'agent' || (cur.type || '') === 'skill')
    ) {
      return '会话';
    }
    cur = cur.parentId ? byId.get(cur.parentId) : undefined;
  }
  return '其它';
}

function sortRoundGroups(keys: string[]): string[] {
  const rank = (k: string) => {
    if (k === '会话') return 0;
    const m = k.match(/^轮次(\d+)$/);
    if (m) return 100 + Number(m[1]);
    if (k === '收尾') return 9000;
    if (k === '其它' || k === '__root__') return 9500;
    return 5000;
  };
  return [...keys].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

function isReactRoundStep(n: ENode): boolean {
  const s = nodeSemanticName(n);
  const nm = n.name || '';
  // Match step_1 / Agent · step_1 / semantic step_1
  return /step_\d+/i.test(nm) || /step_\d+/i.test(s) || (n.type || '').toLowerCase() === 'step';
}

function isSessionStart(n: ENode): boolean {
  const s = nodeSemanticName(n);
  const nm = n.name || '';
  const role = String(n.details?.role || '');
  return (
    s === 'agent_start' || s === 'skill_start'
    || nm === 'agent_start' || nm === 'skill_start'
    || (role === 'container' && (/^Agent · /i.test(nm) || /^Skill · /i.test(nm)))
  );
}

function walkTree(nodes: ENode[], fn: (n: ENode) => void) {
  for (const n of nodes) {
    fn(n);
    if (n.children?.length) walkTree(n.children, fn);
  }
}

/** Collapse duplicate pre_llm_prep + close session once a ReAct step exists. */
function normalizeLiveTree(roots: ENode[]): ENode[] {
  const cloneKids = (nodes: ENode[]): ENode[] =>
    nodes.map((n) => ({
      ...n,
      children: n.children?.length ? cloneKids(n.children) : n.children,
    }));
  const out = cloneKids(roots);
  let hasStep = false;
  let generateRunning = false;
  walkTree(out, (n) => {
    if (isReactRoundStep(n)) hasStep = true;
    const nm = (n.name || '').toLowerCase();
    const sem = nodeSemanticName(n).toLowerCase();
    if (
      n.status === 'running'
      && (n.type === 'llm' || n.type === 'reason' || nm.includes('generate') || sem === 'generate')
    ) {
      generateRunning = true;
    }
  });
  if (hasStep) {
    walkTree(out, (n) => {
      const sem = nodeSemanticName(n);
      if (
        (sem === 'agent_start' || sem === 'skill_start' || n.name === 'agent_start' || n.name === 'skill_start')
        && n.status === 'running'
      ) {
        n.status = 'completed';
      }
    });
  }
  const isDiagCtx = (n: ENode) => {
    const sem = nodeSemanticName(n).toLowerCase();
    const nm = (n.name || '').toLowerCase();
    return (
      sem === 'pre_llm_prep' || sem === 'llm_enter' || sem === 'context_snapshot'
      || nm.includes('pre_llm_prep') || nm.includes('llm_enter') || nm.includes('context_snapshot')
    );
  };
  // Once generate is in flight, prep/enter diagnostics are done
  if (generateRunning) {
    walkTree(out, (n) => {
      if (isDiagCtx(n) && n.status === 'running') n.status = 'completed';
    });
  }
  // Collect prep / llm_enter twins; keep one of each name
  const byDiagName = new Map<string, ENode[]>();
  walkTree(out, (n) => {
    if (!isDiagCtx(n)) return;
    const key = nodeSemanticName(n).toLowerCase() || (n.name || '').toLowerCase();
    if (!byDiagName.has(key)) byDiagName.set(key, []);
    byDiagName.get(key)!.push(n);
  });
  const dropIds = new Set<string>();
  for (const group of byDiagName.values()) {
    if (group.length < 2) continue;
    const keep =
      group.find((n) => n.status === 'completed' || n.status === 'failed')
      || group[group.length - 1];
    for (const n of group) {
      if (n.id !== keep.id) dropIds.add(n.id);
    }
  }
  // Reparent orphan prep/LLM leaves under the latest step_* so they leave the
  // 「其它」 column (no edge) and join 轮次N. generate often arrives with empty
  // parent_span_id when nested TraceGate spans miss the step container id.
  let latestStep: ENode | undefined;
  walkTree(out, (n) => {
    if (isReactRoundStep(n)) {
      if (
        !latestStep
        || Number(n.startTime || 0) >= Number(latestStep.startTime || 0)
      ) {
        latestStep = n;
      }
    }
  });
  if (latestStep) {
    const isOrphanLlm = (n: ENode) => {
      const t = (n.type || '').toLowerCase();
      const sem = nodeSemanticName(n).toLowerCase();
      const nm = (n.name || '').toLowerCase();
      return (
        t === 'llm' || t === 'reason'
        || sem === 'generate' || /^generate$/i.test(nm)
        || nm.includes('llm·generate') || nm.includes('推理 ·')
      );
    };
    const reparentOrphans = (nodes: ENode[], parent?: ENode): ENode[] => {
      const kept: ENode[] = [];
      for (const n of nodes) {
        if (dropIds.has(n.id)) continue;
        const kids = n.children?.length ? reparentOrphans(n.children, n) : n.children;
        const orphanLeaf =
          !parent
          && !isReactRoundStep(n)
          && !isSessionStart(n)
          && !isContainerNode(n)
          && (isDiagCtx(n) || isOrphanLlm(n));
        if (orphanLeaf && latestStep && n.id !== latestStep.id) {
          // Attach under step; skip adding as root
          if (!latestStep.children) latestStep.children = [];
          if (!latestStep.children.some((c) => c.id === n.id)) {
            latestStep.children.push({ ...n, parentId: latestStep.id, children: kids });
          }
          continue;
        }
        kept.push({ ...n, children: kids });
      }
      return kept;
    };
    return reparentOrphans(out);
  }
  const prune = (nodes: ENode[]): ENode[] => {
    const kept = nodes.filter((n) => !dropIds.has(n.id));
    for (const n of kept) {
      if (n.children?.length) n.children = prune(n.children);
    }
    return kept;
  };
  return prune(out);
}

// Legacy compat — kept for reference
const ICONS: Record<string, string> = { ...Object.fromEntries(Object.entries(CANVAS_NODES).map(([k, v]) => [k, v.icon])), default: '📋' };
const TYPE_COLORS: Record<string, string> = { ...Object.fromEntries(Object.entries(CANVAS_NODES).map(([k, v]) => [k, v.color])), default: '#6b7280' };

const STATUS_CONFIG: Record<string, { ring: string; dot: string; badge: string }> = {
  running: { ring: '2px solid #3b82f6', dot: 'bg-blue-400 animate-pulse ring-2 ring-blue-400/30', badge: '执行中' },
  completed: { ring: '2px solid #22c55e', dot: 'bg-green-400 ring-2 ring-green-400/30', badge: '✅' },
  failed: { ring: '2px solid #ef4444', dot: 'bg-red-400 ring-2 ring-red-400/30', badge: '❌' },
  warning: { ring: '2px solid #f59e0b', dot: 'bg-yellow-400 ring-2 ring-yellow-400/30', badge: '⚠️' },
  idle: { ring: '2px solid #374151', dot: 'bg-gray-500 ring-1 ring-gray-500/20', badge: '等待' },
};

/** Running badge text — LLM looks like「推理中」, not a stuck health check. */
function runningBadgeForNode(n: ENode): string {
  const kind = String(n.type || n.details?.kind || '').toLowerCase();
  const nm = String(n.name || '').toLowerCase();
  if (kind === 'llm' || kind === 'reason' || nm === 'generate' || nm.includes('generate')) {
    return '推理中';
  }
  if (kind === 'skill' || nm.startsWith('skill_')) return '技能中';
  if (kind === 'tool') return '工具中';
  if (/^step_\d+$/i.test(nm) || kind === 'step') return '轮次中';
  if (nm === 'agent_start' || nm === 'skill_start' || kind === 'agent') return '进行中';
  return '执行中';
}

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
  const groups = sortRoundGroups([...groupMap.keys()].filter((k) => k !== '__root__'));
  if (groups.length === 0) return layoutDagre(nodes, edges);

  const colW = 260, colGap = 28, nodeH = 80, nodeGap = 16, padX = 20, padY = 36;
  const layed = nodes.map((n) => ({ ...n }));
  let colX = padX;
  const width = padX + groups.length * (colW + colGap);

  for (const g of groups) {
    const gNodes = groupMap.get(g) || [];
    // Time order within a round column so top→bottom ≈ execution order
    const ordered = [...gNodes].sort(
      (a, b) =>
        (Number(a.startTime || 0) - Number(b.startTime || 0)) ||
        a.name.localeCompare(b.name),
    );
    let y = padY;
    for (const gn of ordered) {
      const idx = layed.findIndex((n) => n.id === gn.id);
      if (idx >= 0) {
        layed[idx].position = { x: colX, y };
        // Column title via first node annotation
        if (y === padY) {
          const prev = layed[idx].data?.label;
          layed[idx] = {
            ...layed[idx],
            data: {
              ...layed[idx].data,
              label: (
                <div>
                  <div style={{
                    fontSize: 10, fontWeight: 700, color: '#a5b4fc', marginBottom: 4,
                    letterSpacing: 0.3,
                  }}>
                    ▌{g}
                  </div>
                  {prev}
                </div>
              ),
            },
          };
        }
      }
      y += nodeH + nodeGap;
    }
    colX += colW + colGap;
  }

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
      if (node.status === 'running') {
        rows.push(row('进度', '等待模型返回…（完成后才有 token）', '#3b82f6'));
      } else {
        if ((d.input_tokens ?? 0) > 0) rows.push(row('输入 Token', `${d.input_tokens}`, '#3b82f6'));
        if ((d.output_tokens ?? 0) > 0) rows.push(row('输出 Token', `${d.output_tokens}`, '#22c55e'));
        if ((d.input_tokens ?? 0) === 0 && (d.output_tokens ?? 0) === 0) {
          rows.push(row('Token', '提供方未回传用量（已完成）', '#6b7280'));
        }
      }
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
      rows.push(row('步骤', actionTrailLabel(node)));
      const sel =
        args.skill || args.selected_skill || args.selected_name || args.selected_skill_id || args.skill_id;
      if (sel) rows.push(row('选中技能', sel, '#8b5cf6'));
      if (args.selected_kind) rows.push(row('选中类型', args.selected_kind));
      if (args.strict_outcome || args.strict_eligible != null) {
        rows.push(row('严格评估', args.strict_outcome ?? (args.strict_eligible ? 'eligible' : 'gated')));
      }
      if (args.query_excerpt) rows.push(row('用户输入', args.query_excerpt));
      if (args.candidates && Array.isArray(args.candidates) && args.candidates.length > 0) {
        const candNames = args.candidates.map((c: any) => `${c.name || c.skill_id} (${c.score?.toFixed(1) ?? '?'})`).join(', ');
        rows.push(row('候选列表', candNames));
      }
      break;
    }
    case 'skill': {
      // Header already shows Skill · name — avoid repeating it as "技能执行"
      const skillId = args.skill_id || args.skill || args.name || d.target;
      if (skillId && String(skillId) !== bareActionName(node)) {
        rows.push(row('技能 ID', skillId, '#8b5cf6'));
      }
      if (node.status === 'running') {
        rows.push(row('进度', '执行中…', '#3b82f6'));
      }
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

const ExecutionViewer: React.FC<ExecutionViewerProps> = ({ nodes: propNodes, title, running, elapsed, summary, height = 500, onNodeClick, live, runId, replayRunId, onLiveStatusChange, detailMode = 'inline' }) => {
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
    ? (graph.error || liveErrorLegacy)
    : liveErrorLegacy;
  // Replay mode: step through historical events
  const replay = useReplayEvents(replayRunId || null);
  // Peak counters must be declared before any early return (hooks rules)
  const peakRef = useRef({ reactTotal: 0, reactDone: 0, nodeTotal: 0, nodeDone: 0, runId: '' });
  // Refresh wall-clock elapsed for running nodes (backend duration_ms stays null until complete).
  const [nowTick, setNowTick] = useState(() => Date.now());

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
    // Keep routing_decision / routing_strict_eval / skill_route as separate nodes
    // (labels distinguish them). Only fold skill_candidates into skill_route.
    for (const [key, entry] of merged) {
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
    // Session spine: once any step_* exists, agent_start/skill_start are no longer
    // the active wait — mark them completed so the canvas does not keep「进行中」on 会话.
    const hasReactStep = [...merged.values()].some((m) => {
      const nm = m.node.name || '';
      return /^step_\d+$/i.test(nm);
    });
    const agentEnded = [...merged.values()].some(
      (m) => m.node.name === 'agent_end' && (m.node.status === 'completed' || m.node.status === 'failed'),
    );
    if (agentEnded || hasReactStep) {
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
    if (skillEnded || hasReactStep) {
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
    const forceCloseRunning = (nodes: ENode[]): ENode[] =>
      nodes.map((n) => ({
        ...n,
        status: n.status === 'running' || n.status === 'idle' ? 'completed' : n.status,
        children: n.children?.length ? forceCloseRunning(n.children) : n.children,
      }));

    // Authoritative RunGraph projection — no mergeEvents heuristics
    let roots: ENode[] = [];
    if (useGraph && graph.roots.length > 0) {
      roots = graph.roots;
    } else if (live && liveEvents.length > 0) {
      roots = mergeEvents(liveEvents, 'ev');
    } else if (replayRunId && replay.visibleEvents.length > 0) {
      roots = mergeEvents(replay.visibleEvents, 'replay');
    } else {
      roots = propNodes || [];
    }
    // Always: if parent says not running, or SSE done while parent is not explicitly
    // in-flight, force-close leftover running nodes. When parent running===true
    // (新一轮已启动), do not force-close from a stale liveStatus==='done'.
    if (running === false || (live && liveStatus === 'done' && running !== true)) {
      return forceCloseRunning(normalizeLiveTree(roots));
    }
    return normalizeLiveTree(roots);
  }, [useGraph, graph.roots, live, liveEvents, liveStatus, running, propNodes, replayRunId, replay.visibleEvents]);

  useEffect(() => {
    const hasRunning = (nodes: ENode[]): boolean => {
      for (const n of nodes) {
        if (n.status === 'running') return true;
        if (n.children?.length && hasRunning(n.children)) return true;
      }
      return false;
    };
    if (!hasRunning(dataNodes) && running !== true) return;
    const id = window.setInterval(() => setNowTick(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [dataNodes, running]);

  const [selectedNode, setSelectedNode] = useState<ENode | null>(null);
  const [expandedSubFlows, setExpandedSubFlows] = useState<Set<string>>(new Set());
  /** null = auto: open while running, collapsed when done (frees canvas). */
  const [roundsPanelOpen, setRoundsPanelOpen] = useState<boolean | null>(null);

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

  // Auto-expand every node that has children so the canvas shows the full tree
  // (not only spine containers). Previously only agent_start/step_* were expanded;
  // if expand ids went stale mid-run, the graph could collapse to a single leaf
  // (often「完成」) while peak counters still showed 11/11.
  useEffect(() => {
    const next = new Set<string>();
    const walk = (nodes: ENode[]) => {
      for (const n of nodes) {
        const kids = n.children || [];
        if (kids.length > 0) {
          next.add(n.id);
          walk(kids);
        }
      }
    };
    walk(dataNodes);

    setExpandedSubFlows((prev) => {
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

  // Parent `running` is authoritative when explicitly set (execute status poll).
  // true → show in-flight even if prior graph SSE is still `done` (按失败点重跑).
  // false → force idle even if SSE still streaming (orphan/timeout).
  const parentRunning = replayRunId
    ? replay.playing
    : running === true
      ? true
      : running === false
        ? false
        : (live ? liveStatus === 'streaming' : !!running);
  // Soft-seal: canvas already has completed auto_done/agent_end and no running work —
  // don't keep 「进行中」just because status poll still says running (POST_LOOP hang race).
  // Fail-rerun remounts with new runId so this won't hide a fresh in-flight run.
  const trajectorySealed = useMemo(() => {
    let hasTerminal = false;
    let workRunning = false;
    const walk = (nodes: ENode[]) => {
      for (const n of nodes) {
        const s = nodeSemanticName(n);
        const nm = n.name || '';
        const term =
          s === 'agent_end' || s === 'skill_end' || s === 'auto_done' || s === 'final_answer'
          || nm === 'agent_end' || nm === 'skill_end' || nm === '完成' || nm === 'auto_done'
          || /skill_delivery/i.test(s) || /skill_delivery/i.test(nm)
          || n.type === 'done';
        if (term && (n.status === 'completed' || n.status === 'failed' || n.status === 'warning')) {
          hasTerminal = true;
        }
        if (n.status === 'running') workRunning = true;
        if (n.children?.length) walk(n.children);
      }
    };
    walk(dataNodes);
    return hasTerminal && !workRunning;
  }, [dataNodes]);
  const actualRunning = parentRunning && !trajectorySealed;
  const showLiveProgress =
    actualRunning || ((liveStatus === 'streaming' || liveStatus === 'connecting') && !trajectorySealed);
  const roundsExpanded = roundsPanelOpen ?? true;
  // Refit canvas after rounds panel collapse/expand changes available height
  const prevRoundsExpanded = useRef(roundsExpanded);
  useEffect(() => {
    if (prevRoundsExpanded.current === roundsExpanded) return;
    prevRoundsExpanded.current = roundsExpanded;
    // nudge layout consumers: remount key not available here; fitView runs on layoutSig
    // via a tiny delay so the flex height settles first
    const t = window.setTimeout(() => {
      try {
        window.dispatchEvent(new Event('resize'));
      } catch { /* ignore */ }
    }, 80);
    return () => window.clearTimeout(t);
  }, [roundsExpanded]);
  const { nodes, edges, canvasWidth } = useMemo(() => {
    const nodeList: Node[] = [];
    const edgeList: Edge[] = [];
    const groupMap = new Map<string, ENode[]>();
    const byId = new Map(flattenedNodes.map((n) => [n.id, n]));

    // Assign round/session lane for column layout (ignore stale n.group)
    const withGroup = flattenedNodes.map((n) => ({
      ...n,
      group: resolveRoundGroup(n, byId),
    }));

    for (const n of withGroup) {
      const g = n.group || '其它';
      if (!groupMap.has(g)) groupMap.set(g, []);
      groupMap.get(g)!.push(n);
    }

    // Build nodes
    for (const n of withGroup) {
      const hasChildren = !!(n.children && n.children.length > 0);
      const isExpanded = expandedSubFlows.has(n.id);
      const color = n.color || TYPE_COLORS[n.type] || TYPE_COLORS.default;
      const sc = STATUS_CONFIG[n.status] || STATUS_CONFIG.idle;
      const icon = n.icon || (hasChildren ? '📦' : ICONS[n.type] || ICONS.default);
      const durMs = effectiveDurationMs(n, nowTick);
      const durText = formatDur(durMs);
      const totalTokens = (n.details?.input_tokens ?? 0) + (n.details?.output_tokens ?? 0);
      const hasTokenInfo = (n.details?.input_tokens ?? 0) > 0 || (n.details?.output_tokens ?? 0) > 0;
      const tokenText = hasTokenInfo ? (totalTokens >= 1000 ? `${(totalTokens / 1000).toFixed(1)}K` : String(totalTokens)) : '';
      const cost = n.details?.cost ?? 0;
      const costText = cost > 0 ? `$${cost.toFixed(4)}` : '';
      const displayName = nodeChipLabel(n);

      nodeList.push({
        id: n.id,
        type: 'default',
        data: {
          label: (
            <div style={{ position: 'relative', padding: '4px 0' }}>
              <div style={{ fontSize: 13, fontWeight: 600, color, display: 'flex', alignItems: 'center', gap: 4 }}>
                {icon} <span style={{ color: 'var(--ev-text-primary)' }}>{displayName}</span>
              </div>
              <div style={{ fontSize: 10, marginTop: 2, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                {n.status !== 'idle' && (
                  <span style={{ color }}>
                    {n.status === 'running' ? `${runningBadgeForNode(n)}…` : sc.badge}
                    {durText ? ` · ${durText}` : ''}
                  </span>
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
                {n.group && n.group !== '其它' && (
                  <span style={{ color: '#a5b4fc', fontSize: 9 }}>· {n.group}</span>
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
              {n.status !== 'idle' && (
                <div style={{
                  position: 'absolute', top: -12, left: -12,
                  width: 10, height: 10, borderRadius: '50%',
                  background: color,
                  boxShadow: `0 0 ${n.status === 'running' ? 6 : 3}px ${color}`,
                }} />
              )}
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

    // Hierarchy edges (light) — parent → child
    for (const n of withGroup) {
      if (!n.parentId) continue;
      const parent = byId.get(n.parentId);
      if (!parent) continue;
      const edgeColor = n.status === 'running' ? '#3b82f6' :
                       n.status === 'completed' ? '#22c55e' :
                       n.status === 'failed' ? '#ef4444' : '#374151';
      edgeList.push({
        id: `${n.parentId}->${n.id}`,
        source: n.parentId,
        target: n.id,
        type: 'smoothstep',
        animated: n.status === 'running' && actualRunning,
        style: { stroke: edgeColor, strokeWidth: 1.25, strokeDasharray: '4,3', opacity: 0.45 },
        markerEnd: { type: MarkerType.ArrowClosed, color: edgeColor },
      });
    }

    // Temporal path within each round column (solid) — this is the readable execution flow
    for (const [, gNodes] of groupMap) {
      const timeline = [...gNodes]
        .filter((k) => !isContainerNode(k) || isReactRoundStep(k))
        .sort(
          (a, b) =>
            (Number(a.startTime || 0) - Number(b.startTime || 0)) ||
            a.name.localeCompare(b.name),
        );
      // Prefer action-trail kinds when available; else all non-container
      const actions = timeline.filter(
        (k) => ACTION_TRAIL_KINDS.has((k.type || '').toLowerCase()) || isReactRoundStep(k),
      );
      const seq = actions.length >= 2 ? actions : timeline;
      for (let i = 1; i < seq.length; i++) {
        const a = seq[i - 1];
        const b = seq[i];
        const id = `flow_${a.id}->${b.id}`;
        if (edgeList.some((e) => e.id === id || (e.source === a.id && e.target === b.id))) continue;
        edgeList.push({
          id,
          source: a.id,
          target: b.id,
          type: 'smoothstep',
          animated: b.status === 'running' && actualRunning,
          style: { stroke: '#6366f1', strokeWidth: 2.5, opacity: 0.9 },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#6366f1' },
        });
      }
    }

    // Spine timeline: 会话 agent → 轮次1 (cross-column) + 轮次 → 收尾
    const sessionNodes = withGroup.filter((k) => isSessionStart(k));
    const stepNodes = withGroup.filter((k) => isReactRoundStep(k)).sort(
      (a, b) =>
        (Number(a.startTime || 0) - Number(b.startTime || 0)) ||
        a.name.localeCompare(b.name),
    );
    if (sessionNodes[0] && stepNodes[0]) {
      const a = sessionNodes[0];
      const b = stepNodes[0];
      const id = `seq_session->${b.id}`;
      if (!edgeList.some((e) => e.id === id || (e.source === a.id && e.target === b.id))) {
        edgeList.push({
          id,
          source: a.id,
          target: b.id,
          type: 'smoothstep',
          animated: false,
          style: { stroke: '#94a3b8', strokeWidth: 2.5, opacity: 0.85, strokeDasharray: '6 4' },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
        });
      }
    }
    const spinePeers = withGroup.filter(
      (k) => isReactRoundStep(k) || nodeSemanticName(k) === 'agent_end' || k.name === '完成',
    ).sort(
      (a, b) =>
        (Number(a.startTime || 0) - Number(b.startTime || 0)) ||
        a.name.localeCompare(b.name),
    );
    for (let i = 1; i < spinePeers.length; i++) {
      const a = spinePeers[i - 1];
      const b = spinePeers[i];
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

    const groups = sortRoundGroups([...groupMap.keys()].filter((k) => k !== '__root__'));
    if (groups.length > 0) {
      const result = layoutColumns(nodeList, edgeList, groupMap);
      return { nodes: result.nodes, edges: result.edges, canvasWidth: (result as any).width || 1600 };
    }
    const result = layoutDagre(nodeList, edgeList);
    return { nodes: result.nodes, edges: result.edges, canvasWidth: 0 };
  }, [flattenedNodes, actualRunning, expandedSubFlows, nowTick]);

  // Linear spine for "where am I" — ignore side branches (routing/context)
  const spine = useMemo(() => {
    const isStart = (n: ENode) => isSessionStart(n);
    const isSpineKid = (c: ENode) => {
      const s = nodeSemanticName(c);
      return (
        isReactRoundStep(c)
        || s === 'agent_end' || s === 'auto_done' || s === 'skill_end'
        || c.name === 'agent_end' || c.name === 'auto_done' || c.name === 'skill_end'
      );
    };
    let start = dataNodes.find(isStart) || dataNodes.find((n) => String(n.details?.role || '') === 'container');
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
    // Also pick up step_* that landed as siblings/roots (parent link race)
    const seen = new Set(items.map((n) => n.id));
    walkTree(dataNodes, (n) => {
      if (seen.has(n.id)) return;
      if (isReactRoundStep(n) || nodeSemanticName(n) === 'agent_end' || n.name === 'agent_end') {
        items.push(n);
        seen.add(n.id);
      }
    });
    if (!start) {
      for (const n of dataNodes) {
        if (isSpineKid(n) && !seen.has(n.id)) {
          items.push(n);
          seen.add(n.id);
        }
      }
    }
    // Canonical order: session start → step_N (numeric) → 完成/end
    const isEnd = (n: ENode) => {
      const s = nodeSemanticName(n);
      return s === 'agent_end' || s === 'auto_done' || s === 'skill_end'
        || n.name === 'agent_end' || n.name === 'auto_done' || n.name === 'skill_end' || n.name === '完成';
    };
    const stepNum = (n: ENode) => {
      const m = (n.name || nodeSemanticName(n) || '').match(/step_(\d+)/i);
      return m ? Number(m[1]) : 1e9;
    };
    const head = items.filter((n) => isSessionStart(n) || (start && n.id === start.id));
    const mid = items.filter((n) => isReactRoundStep(n) && !isEnd(n) && !head.some((h) => h.id === n.id))
      .sort((a, b) => stepNum(a) - stepNum(b) || Number(a.startTime || 0) - Number(b.startTime || 0));
    const tail = items.filter((n) => isEnd(n) && !head.some((h) => h.id === n.id) && !mid.some((m) => m.id === n.id));
    const rest = items.filter(
      (n) => !head.some((h) => h.id === n.id) && !mid.some((m) => m.id === n.id) && !tail.some((t) => t.id === n.id),
    );
    return [...head, ...mid, ...rest, ...tail];
  }, [dataNodes]);

  /** Flat, time-ordered user-facing actions (LLM / Skill / Tool / MCP / …). */
  const actionTrail = useMemo(() => collectActionTrail(dataNodes, spine), [dataNodes, spine]);

  /** Prefer ReAct spine (Agent → step_N → 完成); only fall back to action trail when no session. */
  const mainPathNodes = useMemo(() => {
    if (spine.some(isReactRoundStep) || spine.some(isSessionStart)) return spine;
    if (actionTrail.length) return actionTrail;
    return spine;
  }, [spine, actionTrail]);

  /** Per-ReAct-round: mini-path + all descendant nodes. */
  const roundSections = useMemo(() => buildRoundSections(spine, dataNodes), [spine, dataNodes]);

  const focusNode = (n: ENode) => {
    setSelectedNode(n);
    onNodeClick?.(n);
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
    const st = String(liveStatus || '').toLowerCase();
    const queued = st === 'queued' || st === 'pending' || /session_locked/i.test(String(liveError || ''));
    const waiting = live && liveStatus !== 'error' && !queued;
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
        <div>
          {queued
            ? '⏸ 排队中：等待同会话前序执行释放锁…'
            : waiting
              ? '⏳ 正在加载执行步骤…'
              : '暂无执行步骤事件'}
        </div>
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
  // 轮次 = step_* only（不要把「完成」算成第 2 轮）
  const reactRoundNodes = flattenedNodes.filter(isReactRoundStep);
  const reactRoundDone = reactRoundNodes.filter(
    (n) => n.status === 'completed' || n.status === 'failed' || n.status === 'warning',
  ).length;
  const sessionFinished = flattenedNodes.some((n) => {
    const s = nodeSemanticName(n);
    const nm = n.name || '';
    return (
      (s === 'agent_end' || s === 'skill_end' || s === 'auto_done'
        || nm === 'agent_end' || nm === 'skill_end' || nm === '完成' || nm === 'auto_done')
      && (n.status === 'completed' || n.status === 'failed' || n.status === 'warning')
    );
  });
  if ((runId || replayRunId || '') !== peakRef.current.runId) {
    peakRef.current = {
      reactTotal: 0,
      reactDone: 0,
      nodeTotal: 0,
      nodeDone: 0,
      runId: runId || replayRunId || '',
    };
  }
  // Prefer live roundSections count when available (matches 按轮次 panel)
  const roundTotalLive = Math.max(roundSections.length, reactRoundNodes.length);
  const roundDoneLive = roundSections.length > 0
    ? roundSections.filter((r) => {
        const st = r.step.status;
        return st === 'completed' || st === 'failed' || st === 'warning'
          || (!actualRunning && r.nodes.length > 0 && r.nodes.every(
            (n) => n.status === 'completed' || n.status === 'failed' || n.status === 'warning',
          ));
      }).length
    : reactRoundDone;
  peakRef.current.reactTotal = Math.max(peakRef.current.reactTotal, roundTotalLive);
  peakRef.current.reactDone = Math.max(peakRef.current.reactDone, roundDoneLive);
  const nodeTotalNow = Math.max(flattenedNodes.length, peakRef.current.nodeTotal);
  const nodeDoneNow = Math.max(done, peakRef.current.nodeDone);
  peakRef.current.nodeTotal = nodeTotalNow;
  peakRef.current.nodeDone = nodeDoneNow;
  const canvasNodeTotal = flattenedNodes.length;
  const canvasNodeDone = done;
  // While streaming, peak avoids flicker; when done, trust live step_* count
  // (never count「完成」as a second 轮次).
  const shownRoundTotal = actualRunning
    ? Math.max(peakRef.current.reactTotal, roundTotalLive)
    : (roundTotalLive || peakRef.current.reactTotal);
  const shownRoundDone = actualRunning
    ? Math.max(peakRef.current.reactDone, roundDoneLive)
    : (roundDoneLive || peakRef.current.reactDone);
  const progressLabel =
    shownRoundTotal > 0
      ? actualRunning
        ? `轮次 ${Math.max(shownRoundDone, 1)}/${shownRoundTotal} · 进行中`
        : `轮次 ${shownRoundDone}/${shownRoundTotal}${sessionFinished ? ' · 已收尾' : ''}`
      : `${canvasNodeDone}/${canvasNodeTotal}`;

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
          {(showLiveProgress) && (
            <span style={{ fontSize: 12, color: '#3b82f6', display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ animation: 'spin 1s linear infinite' }}>⚙</span> {progressLabel}
              {elapsed != null ? ` · ${elapsed}s` : ''}
              <span style={{ color: 'var(--ev-text-muted)', marginLeft: 6 }}>
                画布节点 {canvasNodeDone}/{canvasNodeTotal}
              </span>
            </span>
          )}
          {!showLiveProgress && (liveStatus === 'done' || trajectorySealed) && (
            <span style={{ fontSize: 11, color: 'var(--ev-text-secondary)' }}>
              {progressLabel} · 画布节点 {canvasNodeDone}/{canvasNodeTotal}
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
      {spine.length > 0 || actionTrail.length > 0 ? (
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
          <span style={{ fontSize: 11, color: 'var(--ev-text-muted)', marginRight: 4 }} title="整次执行的轮次骨架（开始 → step_N → 结束）；细动作见「按轮次」">
            主路径
          </span>
          {mainPathNodes.map((n, i) => {
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
                isSessionStart(n)
                || String(n.details?.role || '') === 'container'
              ));
            const color = running ? '#3b82f6' : doneN ? '#22c55e' : '#6b7280';
            const summary = isReactRoundStep(n) ? stepActionSummary(n) : '';
            const chipLabel = isSessionStart(n)
              ? (n.name || '会话')
              : isReactRoundStep(n)
                ? (n.name || nodeSemanticName(n) || '轮次')
                : nodeChipLabel(n);
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
                  <div>{running ? '▶ ' : doneN ? '✓ ' : ''}{chipLabel}</div>
                  {summary && (
                    <div style={{ fontSize: 10, fontWeight: 500, color: '#94a3b8', marginTop: 2 }}>
                      {summary}
                    </div>
                  )}
                </button>
              </span>
            );
          })}
          {/* Avoid "当前：Skill · X" echoing the only/active spine chip */}
          {currentFocus && (() => {
            const focusIsSpineChip = spine.some((s) => s.id === currentFocus.id);
            const soleSpine = spine.length === 1 && spine[0].id === currentFocus.id;
            if (soleSpine || (focusIsSpineChip && !currentFocus.parentId)) return null;
            const parentName = currentFocus.parentId
              ? (flattenedNodes.find((x) => x.id === currentFocus.parentId)?.name || '…')
              : '';
            return (
              <span style={{ marginLeft: 'auto', fontSize: 11, color: '#93c5fd' }}>
                当前：{currentFocus.name}
                {parentName ? `（属 ${parentName}）` : ''}
              </span>
            );
          })()}
        </div>
      ) : null}

      {/* Per-round path + all nodes (collapsible — default collapsed when done) */}
      {roundSections.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: roundsExpanded ? 8 : 0,
            padding: roundsExpanded ? '8px 10px' : '6px 10px',
            borderRadius: 8,
            border: '1px solid rgba(99,102,241,0.35)',
            background: 'rgba(99,102,241,0.06)',
            flexShrink: 0,
            maxHeight: roundsExpanded ? 320 : undefined,
            overflowY: roundsExpanded ? 'auto' : 'hidden',
          }}
        >
          <button
            type="button"
            onClick={() => setRoundsPanelOpen(!roundsExpanded)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              width: '100%',
              background: 'transparent',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
              textAlign: 'left',
            }}
            title={roundsExpanded ? '收起按轮次，腾出流程图空间' : '展开按轮次详情'}
          >
            <span style={{ fontSize: 11, fontWeight: 600, color: '#a5b4fc' }}>按轮次</span>
            <span style={{ fontSize: 10, color: 'var(--ev-text-muted)', flex: 1 }}>
              {roundsExpanded
                ? '每轮路径与节点 · 点击芯片定位画布'
                : `${roundSections.length} 轮 · ${roundSections.map((r) => r.label).join('、')}${
                    roundSections[0] ? ` · ${stepActionSummary(roundSections[0].step) || '已完成'}` : ''
                  }`}
            </span>
            <span style={{ fontSize: 10, color: '#a5b4fc', fontWeight: 600, whiteSpace: 'nowrap' }}>
              {roundsExpanded ? '收起 ▴' : '展开 ▾'}
            </span>
          </button>
          {roundsExpanded && roundSections.map((round) => {
            const step = round.step;
            const running = step.status === 'running'
              || round.nodes.some((n) => n.status === 'running');
            const failed = step.status === 'failed'
              || round.nodes.some((n) => n.status === 'failed');
            const doneN = step.status === 'completed' || step.status === 'warning'
              || (!running && !failed && round.nodes.length > 0
                && round.nodes.every((n) => n.status === 'completed' || n.status === 'warning' || n.status === 'failed'));
            const headerColor = failed ? '#ef4444' : running ? '#3b82f6' : doneN ? '#22c55e' : '#94a3b8';
            const dur = formatDur(effectiveDurationMs(step, nowTick));
            const pathNodes = round.path.length > 0 ? round.path : round.nodes;
            const pathIds = new Set(pathNodes.map((n) => n.id));
            const extraNodes = round.nodes.filter((n) => !pathIds.has(n.id));
            const summary = stepActionSummary(step);
            const renderChip = (n: ENode) => {
              const nRunning = n.status === 'running';
              const nFailed = n.status === 'failed';
              const nDone = n.status === 'completed' || n.status === 'warning';
              const color = nFailed ? '#ef4444' : nRunning ? '#3b82f6' : nDone ? (n.color || '#22c55e') : '#6b7280';
              const d = formatDur(effectiveDurationMs(n, nowTick));
              const selected = selectedNode?.id === n.id;
              return (
                <button
                  type="button"
                  onClick={() => focusNode(n)}
                  style={{
                    fontSize: 11,
                    fontWeight: selected || nRunning ? 700 : 500,
                    color,
                    background: selected ? 'rgba(99,102,241,0.2)' : nRunning ? 'rgba(59,130,246,0.12)' : 'var(--ev-bg-primary)',
                    border: `1px solid ${selected ? '#6366f1' : color}`,
                    borderRadius: 6,
                    padding: '3px 8px',
                    cursor: 'pointer',
                    maxWidth: 240,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                  title={`${nodeChipLabel(n)} · ${n.status}${d ? ` · ${d}` : ''}`}
                >
                  {n.icon ? `${n.icon} ` : ''}
                  {nRunning ? '▶ ' : nFailed ? '✕ ' : nDone ? '✓ ' : ''}
                  {nodeChipLabel(n)}
                  {d ? ` · ${d}` : ''}
                </button>
              );
            };
            return (
              <div
                key={round.id}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 6,
                  padding: '8px 8px',
                  borderRadius: 6,
                  border: `1px solid ${running ? 'rgba(59,130,246,0.45)' : 'rgba(148,163,184,0.25)'}`,
                  background: running ? 'rgba(59,130,246,0.08)' : 'rgba(15,23,42,0.35)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    onClick={() => focusNode(step)}
                    style={{
                      fontSize: 12,
                      fontWeight: 700,
                      color: headerColor,
                      background: 'transparent',
                      border: 'none',
                      padding: 0,
                      cursor: 'pointer',
                    }}
                    title={`${step.name} · ${step.status}`}
                  >
                    {running ? '▶ ' : failed ? '✕ ' : doneN ? '✓ ' : ''}
                    {round.label}
                    <span style={{ fontWeight: 500, color: '#94a3b8', marginLeft: 6 }}>
                      {step.name}
                      {dur ? ` · ${dur}` : ''}
                    </span>
                  </button>
                  {summary && (
                    <span style={{ fontSize: 10, color: '#94a3b8' }}>
                      {summary}
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span style={{ fontSize: 10, color: 'var(--ev-text-muted)' }} title="本轮全部可观测步骤（准备/路由/推理/技能/观察/完成）">
                    完整步骤（{pathNodes.length}）
                  </span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
                    {pathNodes.length === 0 ? (
                      <span style={{ fontSize: 11, color: '#64748b' }}>暂无步骤节点</span>
                    ) : pathNodes.map((n, i) => (
                      <span key={n.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        {i > 0 && <span style={{ color: '#64748b', fontSize: 11 }}>→</span>}
                        {renderChip(n)}
                      </span>
                    ))}
                  </div>
                </div>
                {extraNodes.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <span style={{ fontSize: 10, color: 'var(--ev-text-muted)' }}>
                      其它节点（{extraNodes.length}）
                    </span>
                    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
                      {extraNodes.map((n) => (
                        <span key={`all-${n.id}`}>{renderChip(n)}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {roundsExpanded && actionTrail.length > 0 && roundSections.every((r) => r.path.length === 0) && (
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 10, color: 'var(--ev-text-muted)', width: '100%' }}>其它动作</span>
              {actionTrail.map((n, i) => (
                <span key={n.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                  {i > 0 && <span style={{ color: '#64748b', fontSize: 11 }}>→</span>}
                  <button
                    type="button"
                    onClick={() => focusNode(n)}
                    style={{
                      fontSize: 11,
                      fontWeight: selectedNode?.id === n.id || n.status === 'running' ? 700 : 500,
                      color: n.status === 'failed' ? '#ef4444' : n.status === 'running' ? '#3b82f6' : '#22c55e',
                      background: 'var(--ev-bg-primary)',
                      border: '1px solid currentColor',
                      borderRadius: 6,
                      padding: '3px 8px',
                      cursor: 'pointer',
                    }}
                  >
                    {actionTrailLabel(n)}
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Fallback flat trail when no round sections could be built */}
      {roundSections.length === 0 && actionTrail.length > 0 && (
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
              按时间列出实际动作（推理 / Skill / Tool / MCP），点击可定位
            </span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
            {actionTrail.map((n, i) => {
              const running = n.status === 'running';
              const failed = n.status === 'failed';
              const doneN = n.status === 'completed' || n.status === 'warning';
              const color = failed ? '#ef4444' : running ? '#3b82f6' : doneN ? (n.color || '#22c55e') : '#6b7280';
              const dur = formatDur(effectiveDurationMs(n, nowTick));
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

      {/* Detail panel (skip when parent owns it — e.g. fullscreen footer) */}
      {detailMode === 'inline' && selectedNode && (
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
            {effectiveDurationMs(selectedNode, nowTick) > 0 ? (
              <span>耗时: {formatDur(effectiveDurationMs(selectedNode, nowTick))}</span>
            ) : null}
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
  // Controlled RF state — without onNodesChange, RF11 keeps stale positions and
  // new/updated nodes stack at (0,0); only the top card (often「完成」) is visible.
  const [rfNodes, setRfNodes] = useState<Node[]>(nodes);
  const [rfEdges, setRfEdges] = useState<Edge[]>(edges);
  const layoutSig = useMemo(
    () => nodes.map((n) => `${n.id}@${Math.round(n.position?.x || 0)},${Math.round(n.position?.y || 0)}`).join('|')
      + `::${edges.map((e) => e.id).join(',')}`,
    [nodes, edges],
  );

  useEffect(() => {
    setRfNodes(nodes);
    setRfEdges(edges);
  }, [layoutSig, nodes, edges]);

  useEffect(() => {
    if (nodes.length === 0) return;
    const t = window.setTimeout(() => {
      try { fitView({ padding: 0.2, duration: 200, minZoom: 0.15, maxZoom: 1.2 }); } catch { /* ignore */ }
    }, 80);
    return () => window.clearTimeout(t);
  }, [layoutSig, fitView, nodes.length]);

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setRfNodes((nds) => applyNodeChanges(changes, nds));
  }, []);
  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    setRfEdges((eds) => applyEdgeChanges(changes, eds));
  }, []);

  return (
    <>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        fitViewOptions={{ padding: 0.2 }}
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
