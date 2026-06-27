import React, { useState, useMemo } from 'react';
import ReactFlow, { Background, Controls, Edge, Node, Position, MarkerType } from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';

interface OntologyClass {
  uri: string; label: string; parent: string | null;
  required_fields: string[]; optional_fields: string[]; categories: string[];
  states?: any; transitions?: any[]; side_effects?: any[];
}
interface OntologyProp {
  uri: string; label: string; domain: string[]; range: string[];
  transitive?: boolean; symmetric?: boolean;
}

const STATE_COLORS: Record<string, string> = {
  emerging: '#eab308', established: '#22c55e', industrial: '#3b82f6',
  deprecated: '#ef4444', retired: '#ef4444', canonical: '#a855f7',
  draft: '#9ca3af', published: '#3b82f6', active: '#22c55e',
  archived: '#6b7280', extracted: '#f59e0b', verified: '#14b8a6',
  superseded: '#ef4444', stub: '#9ca3af', defined: '#3b82f6',
  uploaded: '#f59e0b', processed: '#14b8a6', indexed: '#22c55e',
  nascent: '#eab308', identified: '#f59e0b', analyzed: '#3b82f6',
  addressed: '#14b8a6', resolved: '#22c55e', cited: '#3b82f6',
  review: '#f59e0b', approved: '#22c55e', issued: '#3b82f6',
  procured: '#14b8a6', installed: '#3b82f6', commissioned: '#22c55e',
  proposed: '#f59e0b', implemented: '#3b82f6', submitted: '#f59e0b',
  reviewed: '#14b8a6', closed: '#6b7280',
  dev: '#f59e0b', staging: '#8b5cf6', production: '#22c55e',
  preliminary: '#f59e0b', design: '#3b82f6', construction: '#14b8a6',
  delivered: '#22c55e', specified: '#f59e0b',
};

interface Props {
  classes: OntologyClass[];
  objectProperties: OntologyProp[];
  name?: string;
}

const CLASS_COLORS: Record<string, string> = {
  root: '#6366f1', project: '#3b82f6', design: '#14b8a6',
  equipment: '#f59e0b', system: '#8b5cf6', document: '#22c55e',
  change: '#ef4444', default: '#6b7280',
};

function getColor(label: string): string {
  const lower = label.toLowerCase();
  for (const [key, color] of Object.entries(CLASS_COLORS)) {
    if (lower.includes(key)) return color;
  }
  return CLASS_COLORS.default;
}

function layoutDagre(nodes: Node[], edges: Edge[]) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', ranksep: 120, nodesep: 80, marginx: 40, marginy: 40 });
  for (const n of nodes) {
    g.setNode(n.id, { width: 220, height: 80 });
  }
  for (const e of edges) {
    g.setEdge(e.source, e.target);
  }
  dagre.layout(g);
  return {
    nodes: nodes.map(n => {
      const dn = g.node(n.id);
      return { ...n, position: { x: dn.x - 110, y: dn.y - 40 } };
    }),
    edges,
  };
}

export const OntologyGraph: React.FC<Props> = ({ classes, objectProperties, name }) => {
  const [selectedNode, setSelectedNode] = useState<OntologyClass | null>(null);

  const { nodes, edges } = useMemo(() => {
    const ns: Node[] = [];
    const es: Edge[] = [];

    // Root virtual node
    ns.push({
      id: '__root__',
      type: 'input',
      data: { label: name || '本体根节点', fields: [] },
      position: { x: 0, y: 0 },
      style: { background: '#1e1e2e', border: '2px solid #6366f1', borderRadius: 8, padding: 12, fontSize: 13, color: '#e0e0e0' },
      sourcePosition: Position.Bottom,
    });

    for (const cls of classes) {
      const color = getColor(cls.label);
      const fields = [...(cls.required_fields || []), ...(cls.optional_fields || []).slice(0, 4)];
      ns.push({
        id: cls.uri,
        data: { label: cls.label, fields, required: cls.required_fields, uri: cls.uri, cls },
        position: { x: 0, y: 0 },
        style: {
          background: '#1e1e2e', border: `2px solid ${color}`, borderRadius: 8,
          padding: '10px 14px', fontSize: 13, color: '#e0e0e0', minWidth: 200,
        },
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
      });

      // Parent edge
      if (cls.parent) {
        es.push({
          id: `${cls.parent}->${cls.uri}`,
          source: cls.parent.replace(/.*#/, '__root__') === cls.parent ? '__root__' : cls.parent,
          target: cls.uri,
          type: 'smoothstep',
          style: { stroke: '#4b5563', strokeWidth: 2 },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#4b5563' },
          label: 'inherits',
          labelStyle: { fontSize: 9, fill: '#6b7280' },
        });
      } else {
        es.push({
          id: `root->${cls.uri}`,
          source: '__root__',
          target: cls.uri,
          type: 'smoothstep',
          style: { stroke: '#6366f1', strokeWidth: 1.5, strokeDasharray: '5,5' },
        });
      }
    }

    // Property edges
    for (const prop of objectProperties) {
      for (const dom of prop.domain) {
        for (const rng of prop.range) {
          if (ns.some(n => n.id === dom) && ns.some(n => n.id === rng)) {
            es.push({
              id: `${dom}->${prop.uri}->${rng}`,
              source: dom,
              target: rng,
              type: 'smoothstep',
              style: { stroke: '#8b5cf6', strokeWidth: 1.5 },
              markerEnd: { type: MarkerType.ArrowClosed, color: '#8b5cf6' },
              label: prop.label,
              labelStyle: { fontSize: 9, fill: '#a78bfa' },
              labelBgStyle: { fill: '#1e1e2e' },
              labelBgPadding: [4, 2],
            });
          }
        }
      }
    }

    return layoutDagre(ns, es);
  }, [classes, objectProperties, name]);

  const onNodeClick = (_: any, node: Node) => {
    if (node.data.cls) {
      setSelectedNode(node.data.cls as OntologyClass);
    }
  };

  return (
    <div style={{ width: '100%', height: 600 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={onNodeClick}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background color="#2d2d3d" gap={20} />
        <Controls />
      </ReactFlow>

      {/* Detail panel */}
      {selectedNode && (
        <div style={{
          position: 'absolute', top: 12, right: 12,
          background: '#1e1e2e', border: '1px solid #374151', borderRadius: 8,
          padding: 16, maxWidth: 300, fontSize: 12, color: '#d1d5db',
          zIndex: 10, maxHeight: '80%', overflow: 'auto',
        }}>
          <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8, color: '#e0e0e0' }}>
            {selectedNode.label}
            <button
              onClick={() => setSelectedNode(null)}
              style={{ float: 'right', background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: 14 }}
            >×</button>
          </div>
          <div style={{ marginBottom: 8 }}>
            <span style={{ color: '#f59e0b', fontSize: 10 }}>必填字段:</span>
            <div style={{ fontSize: 10, color: '#9ca3af' }}>
              {selectedNode.required_fields.length > 0 ? selectedNode.required_fields.join(', ') : '无'}
            </div>
          </div>
          {selectedNode.optional_fields.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <span style={{ color: '#6b7280', fontSize: 10 }}>可选字段:</span>
              <div style={{ fontSize: 10, color: '#9ca3af' }}>
                                {(selectedNode.optional_fields || []).slice(0, 10).join(', ')}
              </div>
            </div>
          )}
          {selectedNode.categories.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <span style={{ color: '#6b7280', fontSize: 10 }}>分类:</span>
              <div style={{ fontSize: 10, color: '#9ca3af' }}>
                {selectedNode.categories.join(', ')}
              </div>
            </div>
          )}

          {/* State Machine in detail panel */}
          {(selectedNode as any).states?.enum?.length > 0 && (
            <div style={{ marginTop: 10, borderTop: '1px solid #374151', paddingTop: 8 }}>
              <span style={{ color: '#a78bfa', fontSize: 10, fontWeight: 600 }}>🔁 状态机</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                {((selectedNode as any).states?.enum || []).map((s: any, i: number, arr: any[]) => (
                  <React.Fragment key={s.name}>
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: 3,
                      padding: '2px 6px', borderRadius: 4,
                      background: (STATE_COLORS[s.name] || '#6b7280') + '20',
                      border: '1px solid ' + (STATE_COLORS[s.name] || '#6b7280') + '40',
                      fontSize: 10,
                    }}>
                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: STATE_COLORS[s.name] || '#6b7280' }} />
                      <span style={{ color: '#d1d5db' }}>{s.label || s.name}</span>
                    </div>
                    {i < arr.length - 1 && <span style={{ color: '#6b7280', fontSize: 8 }}>→</span>}
                  </React.Fragment>
                ))}
              </div>
              {((selectedNode as any).transitions || []).length > 0 && (
                <div style={{ marginTop: 6 }}>
                  {((selectedNode as any).transitions || []).slice(0, 5).map((t: any, i: number) => {
                    const fromList = Array.isArray(t.from) ? t.from : [t.from];
                    const tLabel = t.trigger?.type === 'relation_count'
                      ? `${t.trigger.relation} ${t.trigger.operator} ${t.trigger.threshold}`
                      : t.trigger?.type === 'property_condition'
                        ? `${t.trigger.field} ${t.trigger.condition}`
                        : t.trigger?.type || '';
                    return (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 9, color: '#6b7280', paddingLeft: 4 }}>
                        <span style={{ color: '#9ca3af' }}>{fromList.join('/')}</span>
                        <span>→</span>
                        <span style={{ color: STATE_COLORS[t.to] || '#d1d5db' }}>{t.to}</span>
                        <span style={{ color: '#4b5563' }}>({tLabel})</span>
                      </div>
                    );
                  })}
                  {((selectedNode as any).transitions || []).length > 5 && (
                    <div style={{ fontSize: 9, color: '#4b5563', marginTop: 2 }}>
                      ...共 {((selectedNode as any).transitions).length} 条规则
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default OntologyGraph;
