import React, { useCallback, useEffect, useMemo, useState, memo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  Edge,
  Handle,
  MarkerType,
  Node,
  NodeProps,
  Position,
  useEdgesState,
  useNodesState,
} from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';
import {
  classDisplay,
  fieldDisplay,
  localKey,
  propDisplay,
} from '../../utils/ontologyDisplay';

interface OntologyClass {
  uri: string;
  label: string;
  parent: string | null;
  required_fields: string[];
  optional_fields: string[];
  categories: string[];
  description?: string;
  fields?: Array<{ name?: string; id?: string; label?: string; description?: string }>;
  states?: any;
  transitions?: any[];
  side_effects?: any[];
  implements?: string[];
}

interface OntologyProp {
  uri: string;
  label: string;
  name?: string;
  domain: string[];
  range: string[];
  transitive?: boolean;
  symmetric?: boolean;
  description?: string;
}

interface DataProp {
  uri: string;
  label: string;
  domain: string[];
  range?: string | string[];
}

interface ProcessDef {
  id?: string;
  label?: string;
  description?: string;
  starter_class?: string;
  steps?: Array<{ label?: string; entity_class?: string; target_state?: string }>;
}

interface InterfaceDef {
  name: string;
  label?: string;
  description?: string;
}

interface RuleDef {
  name?: string;
  id?: string;
  label?: string;
  description?: string;
}

export type GraphViewMode = 'all' | 'structure' | 'behavior';

interface Props {
  classes: OntologyClass[];
  objectProperties: OntologyProp[];
  dataProperties?: DataProp[];
  processes?: ProcessDef[];
  interfaces?: InterfaceDef[];
  inferenceRules?: RuleDef[];
  name?: string;
  /** 默认全部：类/属性/关系 + 动作/状态/流程/规则 */
  viewMode?: GraphViewMode;
}

function extractActionLines(transitions: any[] | undefined): string[] {
  const out: string[] = [];
  for (const t of transitions || []) {
    const from = Array.isArray(t.from) ? t.from.join('/') : String(t.from || '?');
    const to = String(t.to || '?');
    const trig = t.trigger || {};
    if (trig.type === 'action' && trig.action_id) {
      const short = String(trig.action_id).split(':').pop() || trig.action_id;
      out.push(`⚡${short} ${from}→${to}`);
    } else if (trig.type === 'relation_exists') {
      out.push(`🔗${trig.relation || 'rel'} ${from}→${to}`);
    } else if (trig.type === 'relation_count') {
      out.push(`#${trig.relation || 'rel'} ${from}→${to}`);
    } else if (trig.type === 'property_condition') {
      out.push(`φ ${trig.field || 'field'} ${from}→${to}`);
    } else {
      out.push(`${from}→${to}`);
    }
  }
  return out;
}

function stateLabels(states: any): string[] {
  const enumList = states?.enum;
  if (!Array.isArray(enumList)) return [];
  return enumList.map((s: any) => String(s.label || s.name || '')).filter(Boolean);
}

const STATE_COLORS: Record<string, string> = {
  emerging: '#eab308', established: '#22c55e', industrial: '#3b82f6',
  deprecated: '#ef4444', retired: '#ef4444', canonical: '#a855f7',
  draft: '#9ca3af', published: '#3b82f6', active: '#22c55e',
  archived: '#6b7280', extracted: '#f59e0b', verified: '#14b8a6',
};

const CLASS_COLORS: Record<string, string> = {
  root: '#6366f1', project: '#3b82f6', design: '#14b8a6',
  equipment: '#f59e0b', system: '#8b5cf6', document: '#22c55e',
  change: '#ef4444', order: '#3b82f6', lock: '#14b8a6',
  default: '#6b7280',
};

function getColor(label: string): string {
  const lower = (label || '').toLowerCase();
  for (const [key, color] of Object.entries(CLASS_COLORS)) {
    if (lower.includes(key)) return color;
  }
  return CLASS_COLORS.default;
}

type ClassNodeData = {
  /** Already bilingual: InstallOrder（安装工单） */
  label: string;
  color: string;
  required: string[];
  optional: string[];
  dataAttrs: string[];
  outRels: string[];
  inRels: string[];
  actions: string[];
  states: string[];
  implements: string[];
  showStructure: boolean;
  showBehavior: boolean;
  cls: OntologyClass | null;
  isRoot?: boolean;
};

const ClassNode = memo(({ data }: NodeProps<ClassNodeData>) => {
  const {
    label, color, required, optional, dataAttrs, outRels, inRels,
    actions, states, implements: ifaces, showStructure, showBehavior, isRoot,
  } = data;
  const reqShow = showStructure ? (required || []).slice(0, 5) : [];
  const optShow = showStructure ? (optional || []).slice(0, 3) : [];
  const relShow = showStructure ? [...(outRels || []).slice(0, 3)] : [];
  const actShow = showBehavior ? (actions || []).slice(0, 4) : [];
  const stShow = showBehavior ? (states || []).slice(0, 6) : [];
  const ifaceShow = showBehavior ? (ifaces || []).slice(0, 3) : [];
  const moreReq = Math.max(0, (required || []).length - reqShow.length);
  const moreOpt = Math.max(0, (optional || []).length - optShow.length);
  const moreRel = Math.max(0, (outRels || []).length - relShow.length);
  const moreAct = Math.max(0, (actions || []).length - actShow.length);

  if (isRoot) {
    return (
      <div
        style={{
          background: '#1e1e2e',
          border: '2px solid #6366f1',
          borderRadius: 10,
          padding: '10px 16px',
          color: '#e0e0e0',
          fontSize: 13,
          fontWeight: 600,
          minWidth: 140,
          textAlign: 'center',
          cursor: 'grab',
        }}
      >
        <Handle type="source" position={Position.Bottom} style={{ background: '#6366f1' }} />
        {label}
      </div>
    );
  }

  return (
    <div
      style={{
        background: '#16161f',
        border: `2px solid ${color}`,
        borderRadius: 10,
        minWidth: 230,
        maxWidth: 300,
        color: '#e0e0e0',
        fontSize: 11,
        boxShadow: '0 4px 14px rgba(0,0,0,0.35)',
        cursor: 'grab',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: color }} />
      <div
        style={{
          padding: '8px 10px',
          borderBottom: '1px solid #2a2a3a',
          background: color + '22',
          borderRadius: '8px 8px 0 0',
          fontWeight: 600,
          fontSize: 12,
        }}
      >
        {label}
      </div>
      <div style={{ padding: '6px 10px', display: 'flex', flexDirection: 'column', gap: 4 }}>
        {reqShow.length > 0 && (
          <div>
            <div style={{ color: '#f59e0b', fontSize: 9, marginBottom: 2 }}>属性</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
              {reqShow.map((f) => (
                <span
                  key={f}
                  style={{
                    background: '#78350f55',
                    border: '1px solid #b4530988',
                    color: '#fcd34d',
                    borderRadius: 4,
                    padding: '1px 5px',
                    fontSize: 9,
                    fontFamily: 'ui-monospace, monospace',
                  }}
                >
                  {f}
                </span>
              ))}
              {moreReq > 0 && <span style={{ color: '#6b7280', fontSize: 9 }}>+{moreReq}</span>}
              {moreOpt > 0 && <span style={{ color: '#6b7280', fontSize: 9 }}>可选+{optShow.length + moreOpt}</span>}
            </div>
          </div>
        )}
        {relShow.length > 0 && (
          <div>
            <div style={{ color: '#c4b5fd', fontSize: 9, marginBottom: 2 }}>关系</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
              {relShow.map((r) => (
                <span
                  key={r}
                  style={{
                    background: '#4c1d9555',
                    border: '1px solid #7c3aed88',
                    color: '#ddd6fe',
                    borderRadius: 4,
                    padding: '1px 5px',
                    fontSize: 9,
                  }}
                >
                  → {r}
                </span>
              ))}
              {moreRel > 0 && <span style={{ color: '#6b7280', fontSize: 9 }}>+{moreRel}</span>}
            </div>
          </div>
        )}
        {stShow.length > 0 && (
          <div>
            <div style={{ color: '#34d399', fontSize: 9, marginBottom: 2 }}>状态</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
              {stShow.map((s) => (
                <span
                  key={s}
                  style={{
                    background: '#064e3b55',
                    border: '1px solid #05966988',
                    color: '#a7f3d0',
                    borderRadius: 4,
                    padding: '1px 5px',
                    fontSize: 9,
                  }}
                >
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}
        {actShow.length > 0 && (
          <div>
            <div style={{ color: '#fb923c', fontSize: 9, marginBottom: 2 }}>动作 / 转移</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {actShow.map((a) => (
                <span key={a} style={{ color: '#fdba74', fontSize: 9, lineHeight: 1.3 }}>{a}</span>
              ))}
              {moreAct > 0 && <span style={{ color: '#6b7280', fontSize: 9 }}>+{moreAct} 条</span>}
            </div>
          </div>
        )}
        {ifaceShow.length > 0 && (
          <div>
            <div style={{ color: '#38bdf8', fontSize: 9, marginBottom: 2 }}>接口</div>
            <div style={{ color: '#7dd3fc', fontSize: 9 }}>{ifaceShow.join(' · ')}</div>
          </div>
        )}
        {dataAttrs.length > 0 && showStructure && (
          <div>
            <div style={{ color: '#67e8f9', fontSize: 9, marginBottom: 2 }}>数据属性</div>
            <div style={{ color: '#a5f3fc', fontSize: 9 }}>{dataAttrs.slice(0, 4).join(', ')}</div>
          </div>
        )}
        {!reqShow.length && !relShow.length && !actShow.length && !stShow.length && (
          <div style={{ color: '#6b7280', fontSize: 9 }}>（本视图无附加信息）</div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} style={{ background: color }} />
    </div>
  );
});
ClassNode.displayName = 'ClassNode';

const nodeTypes = { ontologyClass: ClassNode };

function estimateHeight(data: ClassNodeData): number {
  if (data.isRoot) return 48;
  let h = 44;
  if (data.showStructure && data.required?.length) h += 28 + Math.ceil(Math.min(data.required.length, 5) / 3) * 16;
  if (data.showStructure && data.outRels?.length) h += 28 + Math.ceil(Math.min(data.outRels.length, 3) / 2) * 16;
  if (data.showBehavior && data.states?.length) h += 28;
  if (data.showBehavior && data.actions?.length) h += 20 + Math.min(data.actions.length, 4) * 14;
  if (data.showBehavior && data.implements?.length) h += 24;
  return Math.max(h, 72);
}

function layoutDagre(nodes: Node[], edges: Edge[]) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', ranksep: 90, nodesep: 48, marginx: 32, marginy: 32 });
  for (const n of nodes) {
    const h = estimateHeight(n.data as ClassNodeData);
    g.setNode(n.id, { width: 260, height: h });
  }
  for (const e of edges) {
    g.setEdge(e.source, e.target);
  }
  dagre.layout(g);
  return {
    nodes: nodes.map((n) => {
      const dn = g.node(n.id);
      const h = estimateHeight(n.data as ClassNodeData);
      return { ...n, position: { x: dn.x - 130, y: dn.y - h / 2 } };
    }),
    edges,
  };
}

export const OntologyGraph: React.FC<Props> = ({
  classes,
  objectProperties,
  dataProperties = [],
  processes = [],
  interfaces = [],
  inferenceRules = [],
  name,
  viewMode: viewModeProp,
}) => {
  const [viewMode, setViewMode] = useState<GraphViewMode>(viewModeProp || 'all');
  useEffect(() => {
    if (viewModeProp) setViewMode(viewModeProp);
  }, [viewModeProp]);

  const showStructure = viewMode === 'all' || viewMode === 'structure';
  const showBehavior = viewMode === 'all' || viewMode === 'behavior';

  const [selectedNode, setSelectedNode] = useState<OntologyClass | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<{
    label: string;
    source: string;
    target: string;
    description?: string;
  } | null>(null);

  const layouted = useMemo(() => {
    const ns: Node[] = [];
    const es: Edge[] = [];
    /** localKey → nodeId (full uri) */
    const keyToId = new Map<string, string>();

    const register = (id: string, ...aliases: string[]) => {
      keyToId.set(localKey(id), id);
      for (const a of aliases) {
        if (a) keyToId.set(localKey(a), id);
      }
    };

    const resolve = (ref: string): string | null => {
      if (!ref) return null;
      if (keyToId.has(ref)) return keyToId.get(ref)!;
      const k = localKey(ref);
      return keyToId.get(k) || null;
    };

    ns.push({
      id: '__root__',
      type: 'ontologyClass',
      data: {
        label: name || '本体',
        color: '#6366f1',
        required: [],
        optional: [],
        dataAttrs: [],
        outRels: [],
        inRels: [],
        actions: [],
        states: [],
        implements: [],
        showStructure,
        showBehavior,
        cls: null,
        isRoot: true,
      } satisfies ClassNodeData,
      position: { x: 0, y: 0 },
      sourcePosition: Position.Bottom,
      draggable: true,
    });

    for (const cls of classes) {
      const id = cls.uri || cls.label;
      register(id, cls.label, localKey(cls.uri));
    }

    // Precompute relations per class (by resolved id) — bilingual labels
    const outMap = new Map<string, string[]>();
    const inMap = new Map<string, string[]>();
    for (const prop of objectProperties || []) {
      for (const dom of prop.domain || []) {
        for (const rng of prop.range || []) {
          const s = resolve(dom);
          const t = resolve(rng);
          if (!s || !t) continue;
          const lab = propDisplay(prop);
          outMap.set(s, [...(outMap.get(s) || []), lab]);
          inMap.set(t, [...(inMap.get(t) || []), lab]);
        }
      }
    }

    const dataByClass = new Map<string, string[]>();
    for (const dp of dataProperties || []) {
      for (const dom of dp.domain || []) {
        const s = resolve(dom);
        if (!s) continue;
        const lab = propDisplay(dp);
        dataByClass.set(s, [...(dataByClass.get(s) || []), lab]);
      }
    }

    for (const cls of classes) {
      const id = cls.uri || cls.label;
      const color = getColor(cls.label || localKey(id));
      const meta = cls.fields;
      ns.push({
        id,
        type: 'ontologyClass',
        data: {
          label: classDisplay(cls),
          color,
          required: (cls.required_fields || []).map((f) => fieldDisplay(f, meta)),
          optional: (cls.optional_fields || []).map((f) => fieldDisplay(f, meta)),
          dataAttrs: dataByClass.get(id) || [],
          outRels: outMap.get(id) || [],
          inRels: inMap.get(id) || [],
          actions: extractActionLines(cls.transitions),
          states: stateLabels(cls.states),
          implements: cls.implements || [],
          showStructure,
          showBehavior,
          cls,
        } satisfies ClassNodeData,
        position: { x: 0, y: 0 },
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
        draggable: true,
      });

      if (cls.parent) {
        const parentId = resolve(cls.parent) || '__root__';
        es.push({
          id: `inherits:${parentId}->${id}`,
          source: parentId,
          target: id,
          type: 'smoothstep',
          style: { stroke: '#4b5563', strokeWidth: 2 },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#4b5563' },
          label: 'inherits（继承）',
          labelStyle: { fontSize: 10, fill: '#9ca3af' },
          labelBgStyle: { fill: '#111827', fillOpacity: 0.85 },
          labelBgPadding: [4, 2] as [number, number],
          data: { kind: 'inherits' },
        });
      } else {
        es.push({
          id: `root->${id}`,
          source: '__root__',
          target: id,
          type: 'smoothstep',
          style: { stroke: '#6366f1', strokeWidth: 1.2, strokeDasharray: '5,5' },
          data: { kind: 'root' },
        });
      }
    }

    for (const prop of objectProperties || []) {
      if (!showStructure) break;
      for (const dom of prop.domain || []) {
        for (const rng of prop.range || []) {
          const s = resolve(dom);
          const t = resolve(rng);
          if (!s || !t) continue;
          const lab = propDisplay(prop);
          const srcCls = classes.find((c) => (c.uri || c.label) === s);
          const tgtCls = classes.find((c) => (c.uri || c.label) === t);
          es.push({
            id: `rel:${s}->${prop.uri || lab}->${t}`,
            source: s,
            target: t,
            type: 'smoothstep',
            animated: true,
            style: { stroke: '#8b5cf6', strokeWidth: 2 },
            markerEnd: { type: MarkerType.ArrowClosed, color: '#8b5cf6' },
            label: lab,
            labelStyle: { fontSize: 10, fill: '#c4b5fd', fontWeight: 600 },
            labelBgStyle: { fill: '#1e1b4b', fillOpacity: 0.92 },
            labelBgPadding: [5, 3] as [number, number],
            data: {
              kind: 'relation',
              label: lab,
              description: prop.description || '',
              sourceLabel: srcCls ? classDisplay(srcCls) : localKey(s),
              targetLabel: tgtCls ? classDisplay(tgtCls) : localKey(t),
            },
          });
        }
      }
    }
    return layoutDagre(ns, es);
  }, [classes, objectProperties, dataProperties, name, showStructure, showBehavior]);

  // 可控 state + onNodesChange：否则拖拽坐标无法写回，表现为「拖不动」
  const [nodes, setNodes, onNodesChange] = useNodesState(layouted.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layouted.edges);

  useEffect(() => {
    setNodes(layouted.nodes);
    setEdges(layouted.edges);
  }, [layouted, setNodes, setEdges]);

  const onNodeClick = useCallback((_: any, node: Node) => {
    setSelectedEdge(null);
    if (node.data?.cls) setSelectedNode(node.data.cls as OntologyClass);
    else setSelectedNode(null);
  }, []);

  const onEdgeClick = useCallback((_: any, edge: Edge) => {
    setSelectedNode(null);
    if (edge.data?.kind === 'relation') {
      setSelectedEdge({
        label: String(edge.data.label || edge.label || ''),
        source: String(edge.data.sourceLabel || edge.source),
        target: String(edge.data.targetLabel || edge.target),
        description: edge.data.description,
      });
    } else {
      setSelectedEdge(null);
    }
  }, []);

  const relCount = (objectProperties || []).length;
  const classCount = (classes || []).length;
  const actionClassCount = (classes || []).filter((c) => (c.transitions || []).length > 0).length;

  return (
    <div style={{ width: '100%', height: 720, position: 'relative' }}>
      <div
        style={{
          position: 'absolute',
          top: 10,
          left: 10,
          zIndex: 5,
          background: '#111827ee',
          border: '1px solid #374151',
          borderRadius: 8,
          padding: '8px 10px',
          fontSize: 10,
          color: '#d1d5db',
          maxWidth: 260,
        }}
      >
        <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
          {([
            { id: 'all' as const, label: '全部' },
            { id: 'structure' as const, label: '结构' },
            { id: 'behavior' as const, label: '行为' },
          ]).map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => setViewMode(m.id)}
              style={{
                fontSize: 10,
                padding: '2px 8px',
                borderRadius: 4,
                border: viewMode === m.id ? '1px solid #38bdf8' : '1px solid #374151',
                background: viewMode === m.id ? '#0c4a6e88' : 'transparent',
                color: viewMode === m.id ? '#e0f2fe' : '#9ca3af',
                cursor: 'pointer',
              }}
            >
              {m.label}
            </button>
          ))}
        </div>
        <div style={{ fontWeight: 600, marginBottom: 4, color: '#e5e7eb' }}>图例</div>
        {showStructure && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
              <span style={{ width: 18, height: 2, background: '#8b5cf6', display: 'inline-block' }} />
              <span>关系（紫，{relCount}）</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
              <span style={{ width: 18, height: 2, background: '#4b5563', display: 'inline-block' }} />
              <span>继承 / 属性</span>
            </div>
          </>
        )}
        {showBehavior && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
              <span style={{ color: '#fb923c' }}>⚡</span>
              <span>动作 / 状态转移（{actionClassCount} 类有）</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
              <span style={{ color: '#34d399' }}>●</span>
              <span>状态 · 接口 · 流程/规则见下方</span>
            </div>
          </>
        )}
        <div style={{ marginTop: 4, color: '#9ca3af' }}>
          {classCount} 类 · English（中文）
        </div>
        <div style={{ color: '#6b7280', marginTop: 2 }}>
          按住卡片拖动 · 空白处平移 · 滚轮缩放
        </div>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
        panOnDrag
        zoomOnScroll
        selectNodesOnDrag={false}
        proOptions={{ hideAttribution: true }}
        style={{ height: showBehavior ? 560 : 640 }}
      >
        <Background color="#2d2d3d" gap={20} />
        <Controls />
      </ReactFlow>

      {showBehavior && (
        <div
          style={{
            position: 'absolute',
            left: 10,
            right: 10,
            bottom: 8,
            zIndex: 5,
            background: '#0f172aee',
            border: '1px solid #334155',
            borderRadius: 8,
            padding: '8px 10px',
            fontSize: 10,
            color: '#cbd5e1',
            maxHeight: 140,
            overflow: 'auto',
          }}
        >
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
            <div>
              <div style={{ color: '#fb923c', fontWeight: 600, marginBottom: 4 }}>流程 processes</div>
              {(processes || []).length === 0 && <div style={{ color: '#64748b' }}>无</div>}
              {(processes || []).slice(0, 4).map((p) => (
                <div key={p.id || p.label} style={{ marginBottom: 4 }}>
                  <div style={{ color: '#fdba74' }}>{p.label || p.id}</div>
                  <div style={{ color: '#64748b' }}>
                    起点 {p.starter_class || '—'} · {(p.steps || []).length} 步
                    {(p.steps || []).slice(0, 3).map((s) => s.label).filter(Boolean).join(' → ')
                      ? `：${(p.steps || []).slice(0, 3).map((s) => s.label).filter(Boolean).join(' → ')}`
                      : ''}
                  </div>
                </div>
              ))}
            </div>
            <div>
              <div style={{ color: '#38bdf8', fontWeight: 600, marginBottom: 4 }}>接口 interfaces</div>
              {(interfaces || []).length === 0 && <div style={{ color: '#64748b' }}>无</div>}
              {(interfaces || []).slice(0, 6).map((i) => (
                <div key={i.name} style={{ marginBottom: 2 }}>
                  <span style={{ color: '#7dd3fc' }}>{i.label || i.name}</span>
                  {i.description ? <span style={{ color: '#64748b' }}> — {i.description}</span> : null}
                </div>
              ))}
            </div>
            <div>
              <div style={{ color: '#a78bfa', fontWeight: 600, marginBottom: 4 }}>规则 / 函数 inference</div>
              {(inferenceRules || []).length === 0 && <div style={{ color: '#64748b' }}>无</div>}
              {(inferenceRules || []).slice(0, 5).map((r, idx) => (
                <div key={r.name || r.id || idx} style={{ marginBottom: 2, color: '#c4b5fd' }}>
                  {r.label || r.name || r.id || 'rule'}
                  {r.description ? <span style={{ color: '#64748b' }}> — {r.description}</span> : null}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {selectedNode && (
        <div
          style={{
            position: 'absolute',
            top: 12,
            right: 12,
            background: '#1e1e2e',
            border: '1px solid #374151',
            borderRadius: 8,
            padding: 16,
            maxWidth: 320,
            fontSize: 12,
            color: '#d1d5db',
            zIndex: 10,
            maxHeight: '85%',
            overflow: 'auto',
          }}
        >
          <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8, color: '#e0e0e0' }}>
            {classDisplay(selectedNode)}
            <button
              type="button"
              onClick={() => setSelectedNode(null)}
              style={{ float: 'right', background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: 14 }}
            >
              ×
            </button>
          </div>
          {selectedNode.description && (
            <div style={{ fontSize: 10, color: '#9ca3af', marginBottom: 8 }}>{selectedNode.description}</div>
          )}
          <div style={{ marginBottom: 8 }}>
            <span style={{ color: '#f59e0b', fontSize: 10 }}>必填属性</span>
            <div style={{ fontSize: 10, color: '#fcd34d', fontFamily: 'ui-monospace, monospace', marginTop: 2 }}>
              {(selectedNode.required_fields || []).length
                ? selectedNode.required_fields.map((f) => fieldDisplay(f, selectedNode.fields)).join('、')
                : '无'}
            </div>
          </div>
          {(selectedNode.optional_fields || []).length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <span style={{ color: '#9ca3af', fontSize: 10 }}>可选属性</span>
              <div style={{ fontSize: 10, color: '#d1d5db', fontFamily: 'ui-monospace, monospace', marginTop: 2 }}>
                {selectedNode.optional_fields.map((f) => fieldDisplay(f, selectedNode.fields)).join('、')}
              </div>
            </div>
          )}
          {(selectedNode.categories || []).length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <span style={{ color: '#6b7280', fontSize: 10 }}>分类</span>
              <div style={{ fontSize: 10, color: '#9ca3af' }}>{selectedNode.categories.join(', ')}</div>
            </div>
          )}
          {(selectedNode.implements || []).length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <span style={{ color: '#38bdf8', fontSize: 10 }}>接口</span>
              <div style={{ fontSize: 10, color: '#7dd3fc' }}>{selectedNode.implements.join(' · ')}</div>
            </div>
          )}
          {extractActionLines(selectedNode.transitions).length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <span style={{ color: '#fb923c', fontSize: 10 }}>动作 / 转移</span>
              <div style={{ fontSize: 10, color: '#fdba74', marginTop: 4 }}>
                {extractActionLines(selectedNode.transitions).map((a) => (
                  <div key={a}>{a}</div>
                ))}
              </div>
            </div>
          )}
          {(selectedNode as any).states?.enum?.length > 0 && (
            <div style={{ marginTop: 10, borderTop: '1px solid #374151', paddingTop: 8 }}>
              <span style={{ color: '#a78bfa', fontSize: 10, fontWeight: 600 }}>状态机</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                {((selectedNode as any).states?.enum || []).map((s: any) => (
                  <div
                    key={s.name}
                    style={{
                      padding: '2px 6px',
                      borderRadius: 4,
                      background: (STATE_COLORS[s.name] || '#6b7280') + '20',
                      border: '1px solid ' + (STATE_COLORS[s.name] || '#6b7280') + '40',
                      fontSize: 10,
                    }}
                  >
                    {s.label || s.name}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {selectedEdge && (
        <div
          style={{
            position: 'absolute',
            top: 12,
            right: 12,
            background: '#1e1b4b',
            border: '1px solid #7c3aed88',
            borderRadius: 8,
            padding: 16,
            maxWidth: 320,
            fontSize: 12,
            color: '#ddd6fe',
            zIndex: 10,
          }}
        >
          <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>
            关系：{selectedEdge.label}
            <button
              type="button"
              onClick={() => setSelectedEdge(null)}
              style={{ float: 'right', background: 'none', border: 'none', color: '#a78bfa', cursor: 'pointer' }}
            >
              ×
            </button>
          </div>
          <div style={{ fontSize: 11 }}>
            {selectedEdge.source} <span style={{ color: '#a78bfa' }}>→</span> {selectedEdge.target}
          </div>
          {selectedEdge.description && (
            <div style={{ fontSize: 10, color: '#c4b5fd', marginTop: 8 }}>{selectedEdge.description}</div>
          )}
        </div>
      )}
    </div>
  );
};

export default OntologyGraph;
