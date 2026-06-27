
import React, { useCallback, useMemo, useState, useEffect, useRef } from 'react';
import ReactFlow, {
  Node, Edge, Controls, Background, MiniMap, useNodesState, useEdgesState,
  addEdge, Connection, MarkerType, ReactFlowProvider, useReactFlow,
  Handle, Position, BaseEdge, EdgeLabelRenderer, getBezierPath, EdgeProps,
  NodeResizer,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Play, Save, ChevronRight, ChevronDown, Square, Loader2, History, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { Button, toast } from '../../../components/ui';
import { workspaceAgentApi, workflowApi } from '../../../services';
import { ExecutionViewer } from '../../../components/ExecutionViewer';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';

/* ---------- LabeledEdge ---------- */
const LabeledEdge: React.FC<EdgeProps> = (p) => {
  const [ep, lx, ly] = getBezierPath({ sourceX: p.sourceX, sourceY: p.sourceY, sourcePosition: p.sourcePosition, targetX: p.targetX, targetY: p.targetY, targetPosition: p.targetPosition });
  const lb = (p.data as any)?.label as string | undefined;
  const bl = (p.data as any)?.branchLabel as string | undefined;
  const ec = (p.data as any)?.edgeColor || '#8b5cf6';
  return (<>
    <BaseEdge id={p.id} path={ep} markerEnd={p.markerEnd} style={p.style} />
    {lb && (<EdgeLabelRenderer><div className="nodrag nopan absolute text-[10px] px-1.5 py-0.5 rounded pointer-events-auto"
      style={{ transform: `translate(-50%,-50%) translate(${lx}px,${ly}px)`, color: '#e5e7eb', background: `${ec}20`, border: `1px solid ${ec}40` }}>{lb}</div></EdgeLabelRenderer>)}
    {bl && (<EdgeLabelRenderer><div className="nodrag nopan absolute text-[9px] px-1.5 py-0.5 rounded font-mono font-bold"
      style={{ transform: `translate(-50%,-50%) translate(${lx}px,${ly}px)`, color: bl === 'True' ? '#4ade80' : '#f87171', background: bl === 'True' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)' }}>{bl}</div></EdgeLabelRenderer>)}
  </>);
};
const edgeTypes = { labeled: LabeledEdge };
let nodeId = 0;
const getId = () => `canvas_node_${++nodeId}`;

const NODE_PALETTE = [
  { type: 'start', icon: '▶️', label: 'Start', desc: '工作流入口', color: 'green', category: '流程' },
  { type: 'end', icon: '🏁', label: 'End', desc: '工作流出口', color: 'red', category: '流程' },
  { type: 'agent', icon: '🤖', label: 'Agent', desc: 'AI Agent 执行', color: 'blue', category: 'AI' },
  { type: 'llm', icon: '🧠', label: 'LLM', desc: '直接调用大模型', color: 'purple', category: 'AI' },
  { type: 'knowledge', icon: '📚', label: 'Knowledge', desc: '知识库检索 RAG', color: 'indigo', category: 'AI' },
  { type: 'condition', icon: '🔀', label: 'Condition', desc: '条件分支 True/False', color: 'amber', category: '逻辑' },
  { type: 'loop', icon: '🔄', label: 'Loop', desc: '数组遍历/迭代', color: 'violet', category: '逻辑' },
  { type: 'code', icon: '💻', label: 'Code', desc: '执行代码片段', color: 'emerald', category: '数据' },
  { type: 'template', icon: '📄', label: 'Template', desc: 'Jinja2模板渲染', color: 'orange', category: '数据' },
  { type: 'assigner', icon: '✏️', label: 'Assigner', desc: '变量赋值/转换', color: 'rose', category: '数据' },
  { type: 'aggregator', icon: '📦', label: 'Aggregator', desc: '多分支输出聚合', color: 'lime', category: '数据' },
  { type: 'list', icon: '📋', label: 'List Op', desc: '列表过滤/排序/切片', color: 'pink', category: '数据' },
  { type: 'http', icon: '🌐', label: 'HTTP', desc: 'API 请求', color: 'cyan', category: '集成' },
  { type: 'tool', icon: '🔧', label: 'Tool', desc: '调用工具/API', color: 'teal', category: '集成' },
  { type: 'human', icon: '👤', label: 'Human Input', desc: '人工输入/审批', color: 'yellow', category: '交互' },
  { type: 'extractor', icon: '🧲', label: 'Param Extract', desc: 'LLM提取结构化参数', color: 'sky', category: 'AI' },
];

const CanvasInner: React.FC = () => {
  const rf = useReactFlow();
  const [nodes, setNodes, _onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [agents, setAgents] = useState<any[]>([]);
  const params = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const autoRunRef = useRef(false);
  const [workflowId, setWorkflowId] = useState<string | null>(params.id || null);
  const [workflowName, setWorkflowName] = useState('');
  const [saving, setSaving] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const onNodesChange = useCallback((changes: any) => { if (isRunning) return; _onNodesChange(changes); }, [isRunning, _onNodesChange]);
  const [runningPid, setRunningPid] = useState('');
  const [stopping, setStopping] = useState(false);
  const runStartRef = useRef(0);
  const [runElapsed, setRunElapsed] = useState(0);
  const [runHistory, setRunHistory] = useState<any[]>([]);
  const [showRunHistory, setShowRunHistory] = useState(false);
  const [latestVersion, setLatestVersion] = useState(0);
  const [versions, setVersions] = useState<any[]>([]);
  const [showVersions, setShowVersions] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval>>();
  const [collapsedCats, setCollapsedCats] = useState<Record<string,boolean>>({'AI':true,'逻辑':true,'数据':true,'集成':true,'交互':true,'agent':true});
  const toggleCat = (cat: string) => setCollapsedCats(p => ({...p, [cat]: !p[cat]}));
  const [menu, setMenu] = useState<{ x: number; y: number; nodeId: string } | null>(null);
  const [editNode, setEditNode] = useState<Node<any> | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [editTab, setEditTab] = useState<'config' | 'output'>('config');
  const [history, setHistory] = useState<{ nodes: Node[]; edges: Edge[] }[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const [searchTerm, setSearchTerm] = useState('');
  const [copied, setCopied] = useState<Node<any>[] | null>(null);
  const [edgeMenu, setEdgeMenu] = useState<{ x: number; y: number; edgeId: string } | null>(null);
  const [dragPos, setDragPos] = useState<{ x: number; y: number } | null>(null);
  const [canvasMenu, setCanvasMenu] = useState<{ x: number; y: number } | null>(null);
  const [highlightNode, setHighlightNode] = useState<string | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [execViewerOpen, setExecViewerOpen] = useState(false);
  const [lastRunId, setLastRunId] = useState('');
  const [execDone, setExecDone] = useState(false);
  const [, setReplayMode] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [inspectorNodeId, setInspectorNodeId] = useState<string | null>(null);
  const [inspectorVars, setInspectorVars] = useState<Record<string, any>>({});
  const [stepRunOpen, setStepRunOpen] = useState(false);
  const [stepRunNodeId, setStepRunNodeId] = useState('');
  const [stepRunInput, setStepRunInput] = useState('{}');
  const [stepRunning, setStepRunning] = useState(false);
  const [stepRunResult, setStepRunResult] = useState<any>(null);

  // Step-Run: execute a single stage with mock input
  const doStepRun = async () => {
    if (!lastRunId || !stepRunNodeId) return;
    setStepRunning(true);
    try {
      const resp = await fetch(`/api/core/graphs/runs/${lastRunId}/stages/${encodeURIComponent(stepRunNodeId)}/step-run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-AIPLAT-ACTOR-ROLE': 'admin' },
        body: JSON.stringify({ mock_input: (() => { try { return JSON.parse(stepRunInput); } catch { return { input: stepRunInput }; } })() }),
      });
      const data = await resp.json();
      setStepRunResult(data);
      // Update the canvas node with result
      setNodes(nds => nds.map(n => n.id === stepRunNodeId ? { ...n, data: { ...n.data, status: data.status === 'completed' ? 'completed' as const : 'failed' as const, _output: data.output || data.error, _elapsed: data.elapsed_ms / 1000 } } : n));
      toast.success(data.status === 'completed' ? `Step-Run 完成 · ${data.elapsed_ms}ms` : 'Step-Run 失败');
    } catch (e: any) { toast.error(e.message || 'Step-Run 失败'); }
    finally { setStepRunning(false); }
  };

  const [canvasSearch, setCanvasSearch] = useState('');
  const [canvasSearchOpen, setCanvasSearchOpen] = useState(false);
  const lastInputRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);

  const persist = useCallback(async () => {
    setSaving(true);
    try {
      const cleanNodes = nodes.map(n => ({ id: n.id, type: n.type, position: n.position, data: n.data }));
      const cleanEdges = edges.map(e => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle, type: e.type, data: e.data, style: e.style, markerEnd: e.markerEnd }));
      if (workflowId) {
        await workflowApi.update(workflowId, { name: workflowName || undefined, nodes: cleanNodes as any, edges: cleanEdges as any });
        toast.success('已保存');
      } else {
        const name = workflowName || window.prompt('请输入 workflow 名称', '未命名工作流');
        if (!name) { setSaving(false); return; }
        const r: any = await workflowApi.create({ name: name.trim(), nodes: cleanNodes as any, edges: cleanEdges as any });
        setWorkflowId(r.id);
        setWorkflowName(r.name);
        navigate(`/core/workflows/${r.id}/edit`, { replace: true });
        toast.success('已创建并保存');
      }
    } catch (e: any) { toast.error('保存失败', e?.detail || ''); }
    finally { setSaving(false); }
  }, [nodes, edges, workflowId, workflowName, navigate]);
  const pushHistory = useCallback((ns: Node[], es: Edge[]) => { setHistory(prev => { const t = prev.slice(0, historyIdx + 1); const u = [...t, { nodes: JSON.parse(JSON.stringify(ns)), edges: JSON.parse(JSON.stringify(es)) }].slice(-50); setHistoryIdx(u.length - 1); return u; }); }, [historyIdx]);
  const selectedEdgeId = useMemo(() => edges.find(e => e.selected)?.id, [edges]);
  const getConnectedIds = useCallback((nid: string) => { const ids = new Set<string>([nid]); edges.forEach(e => { if (e.source === nid) ids.add(e.target); if (e.target === nid) ids.add(e.source); }); return ids; }, [edges]);
  const displayNodes = useMemo(() => { let ns = nodes; if (canvasSearch) { const q = canvasSearch.toLowerCase(); ns = ns.map(n => { const m = ((n.data as any)?.label || '').toLowerCase().includes(q); return { ...n, style: { ...n.style, opacity: m ? 1 : 0.15, transition: 'opacity 0.2s' }, selected: m }; }); } else if (highlightNode) { const ids = getConnectedIds(highlightNode); ns = nodes.map(n => ({ ...n, style: { ...n.style, opacity: ids.has(n.id) ? 1 : 0.25, transition: 'opacity 0.2s' } })); } return ns; }, [nodes, highlightNode, getConnectedIds, canvasSearch]);
  const displayEdges = useMemo(() => {
    let es = edges;
    if (isRunning) {
      es = es.map(e => {
        const srcNode = nodes.find(n => n.id === e.source);
        const srcStatus = (srcNode?.data as any)?.status || 'idle';
        if (srcStatus === 'running') {
          // Bright flowing line: data is passing through NOW
          const color = (e.data as any)?.edgeColor || '#3b82f6';
          return { ...e, animated: true, style: { ...e.style, stroke: color, strokeWidth: 3, opacity: 1, strokeDasharray: '5,5' } };
        } else if (srcStatus === 'completed') {
          // Green solid line: data passed
          return { ...e, animated: false, style: { ...e.style, stroke: '#22c55e', strokeWidth: 2, opacity: 1 } };
        } else {
          // Idle: gray thin line, not active yet
          return { ...e, animated: false, style: { ...e.style, stroke: '#4b5563', strokeWidth: 1.5, opacity: 0.4 } };
        }
      });
    }
    if (highlightNode) {
      const ids = getConnectedIds(highlightNode);
      es = es.map(e => ({ ...e, style: { ...e.style, opacity: ids.has(e.source) && ids.has(e.target) ? 1 : 0.12, transition: 'opacity 0.2s' } }));
    }
    return es;
  }, [edges, highlightNode, getConnectedIds, isRunning, nodes]);

  /* keyboard */
  useEffect(() => { const h = (e: KeyboardEvent) => { const m = e.ctrlKey || e.metaKey; if (m && e.key === 'z' && !e.shiftKey) { e.preventDefault(); if (historyIdx > 0) { const p = history[historyIdx - 1]; setNodes(p.nodes); setEdges(p.edges); setHistoryIdx(historyIdx - 1); } } if (m && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) { e.preventDefault(); if (historyIdx < history.length - 1) { const n = history[historyIdx + 1]; setNodes(n.nodes); setEdges(n.edges); setHistoryIdx(historyIdx + 1); } } if (m && e.key === 's') { e.preventDefault(); persist(); } if (m && e.key === 'a') { e.preventDefault(); setNodes(nds => nds.map(n => ({ ...n, selected: true }))); } if (m && e.key === 'c') { if (document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'TEXTAREA') return; const s = nodes.filter(n => n.selected); if (s.length) setCopied(JSON.parse(JSON.stringify(s))); } if (m && e.key === 'v') { if (document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'TEXTAREA') return; if (copied?.length) { setNodes(nds => nds.map(n => ({ ...n, selected: false })).concat((copied || []).map(n => ({ ...n, id: getId(), position: { x: n.position.x + 30, y: n.position.y + 30 }, selected: true })))); } } if (m && e.key === 'f') { e.preventDefault(); setCanvasSearchOpen(true); setTimeout(() => document.getElementById('canvas-search-input')?.focus(), 50); } if (m && e.key === 'd') { e.preventDefault(); if (nodes.length) { const mx = Math.max(...nodes.map(n => n.position.x)) + 300; setNodes(nds => nds.map(n => ({ ...n, selected: false })).concat(nodes.map(n => ({ ...JSON.parse(JSON.stringify(n)), id: getId(), position: { x: n.position.x + mx, y: n.position.y }, selected: true })))); } } if (e.key === 'Escape') { setNodes(nds => nds.map(n => ({ ...n, selected: false }))); setMenu(null); setEditOpen(false); setCanvasSearch(''); setCanvasSearchOpen(false); } if (e.key === '?' && !m) { e.preventDefault(); setHelpOpen(v => !v); } }; document.addEventListener('keydown', h); return () => document.removeEventListener('keydown', h); }, [history, historyIdx, setNodes, setEdges, copied, nodes, setMenu, setEditOpen]);

  const prevNodesLen = useRef(0);
  useEffect(() => { const c = nodes.length + edges.length; if (c !== prevNodesLen.current && nodes.length > 0) { pushHistory(nodes, edges); prevNodesLen.current = c; } }, [nodes.length, edges.length]);

  useEffect(() => {
    workspaceAgentApi.list().then((r: any) => setAgents(r?.agents || r || []));
    if (!workflowId) return;
    workflowApi.get(workflowId).then((wf: any) => {
      setWorkflowName(wf.name || '');
      const items = wf.nodes || [];
      if (items.length) setNodes(items.map((s: any, i: number) => ({ id: s.id || `n_${i}`, type: 'stageNode', position: s.position || { x: 50 + i * 220, y: 80 }, data: { type: (s.data?.type || s.type || 'agent'), label: (s.data?.label || s.label || 'Node'), config: (s.data?.config || s.config || {}), status: 'idle', output_variables: (s.data?.output_variables || []), input_variables: (s.data?.input_variables || []), start_inputs: (s.data?.start_inputs || []) } })));
      if (wf.edges?.length) setEdges(wf.edges);
    }).catch(() => { toast.error('加载失败'); });
    workflowApi.listVersions(workflowId).then((r: any) => {
      setLatestVersion(r?.latest_version || 0);
      setVersions(r?.versions || []);
    }).catch(() => {});
  }, [workflowId]);

  /* handlers — must be BEFORE return */
  const extractOutput = (raw: string): string => {
    if (!raw || raw === '{}') return '';
    try {
      const obj = JSON.parse(raw);
      if (typeof obj === 'object' && obj !== null) {
        for (const k of ['raw_output', 'text', 'content', 'response', 'output', 'result']) {
          const v = obj[k];
          if (typeof v === 'string' && v.trim()) return v;
          if (typeof v === 'object' && v !== null) return JSON.stringify(v, null, 2);
        }
        const keys = Object.keys(obj);
        if (keys.length === 1) { const v = obj[keys[0]]; return typeof v === 'string' ? v : JSON.stringify(v, null, 2); }
        return JSON.stringify(obj, null, 2);
      }
    } catch {}
    const m1 = raw.match(/'raw_output'\s*:\s*'([^']*)'/);
    if (m1) return m1[1];
    const m2 = raw.match(/"raw_output"\s*:\s*"((?:[^"\\]|\\.)*)"/);
    if (m2) return m2[1].replace(/\\"/g, '"').replace(/\\n/g, '\n');
    return raw.slice(0, 2000);
  };
  const getAgentDraggable = (a: any) => ({ type: 'agent', label: a.display_name || a.name, agentId: a.id, phase: a.phase || '', skills: a.skills || [], model: a.config?.model || a.metadata?.model || '?' });
  const onDragStart = (e: React.DragEvent, item: any) => { e.dataTransfer.setData('application/reactflow', JSON.stringify(item)); e.dataTransfer.effectAllowed = 'move'; };
  const onDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; setDragPos({ x: e.clientX - (e.currentTarget as HTMLElement).getBoundingClientRect().left, y: e.clientY - (e.currentTarget as HTMLElement).getBoundingClientRect().top }); }, []);
  const onDrop = useCallback((e: React.DragEvent) => { if (isRunning) return; e.preventDefault(); try { const d = JSON.parse(e.dataTransfer.getData('application/reactflow')); const pos = rf.screenToFlowPosition({ x: e.clientX - 200, y: e.clientY - 80 }); const nt = d.type || 'agent'; let cfg: any = {}; if (nt === 'agent') cfg = { agentId: d.agentId || '', skills: d.skills || [], model: d.model || 'deepseek-chat' }; else if (nt === 'llm') cfg = { model: 'deepseek-chat', prompt: '', temperature: 0.7, max_tokens: 2048 }; else if (nt === 'code') cfg = { language: 'python', snippet: 'print("hello")' }; else if (nt === 'http') cfg = { method: 'GET', url: '', headers: '{}', body: '' }; else if (nt === 'condition') cfg = { expression: '', true_label: 'True', false_label: 'False' }; else if (nt === 'human') cfg = { input_prompt: '', input_fields: '[{"name":"feedback","type":"text","required":true}]' }; else if (nt === 'loop') cfg = { source_var: '', body_template: '', loop_mode: 'sequential', max_concurrency: 5 }; else if (nt === 'knowledge') cfg = { kb_name: '', query: '', top_k: 3 }; else if (nt === 'tool') cfg = { tool_name: '', params: '{}' }; else if (nt === 'list') cfg = { operation: 'filter', list_param: '' }; else if (nt === 'template') cfg = { template: '' }; else if (nt === 'aggregator') cfg = { agg_mode: 'object' }; else if (nt === 'assigner') cfg = { target_var: '', expression: '' }; setNodes(nds => [...nds, { id: getId(), type: 'stageNode', position: pos, data: { type: nt, label: d.label || d.agentName || nt.toUpperCase(), config: cfg, status: 'idle' } }]); setDragPos(null); } catch { setDragPos(null); } }, [rf, setNodes, isRunning]);
  const onNodeDoubleClick = useCallback((_e: React.MouseEvent, node: Node) => {
    const st = (node.data as any)?.status || 'idle';
    setEditNode({ ...node }); setEditOpen(true);
    // Auto-switch to output tab for completed/failed nodes during/after run
    if (st === 'completed' || st === 'failed') setEditTab('output');
    else setEditTab('config');
  }, [isRunning]);
  const onNodeContextMenu = useCallback((e: React.MouseEvent, node: Node) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY, nodeId: node.id }); }, []);
  const onEdgeClick = useCallback((_e: React.MouseEvent, edge: Edge) => { setEdges(eds => eds.map(e => e.id === edge.id ? { ...e, selected: true, style: { ...e.style, strokeWidth: 3 } } : e)); }, [setEdges]);
  const onEdgeDoubleClick = useCallback((_e: React.MouseEvent, edge: Edge) => { const c = ((edge.data as any)?.label as string) || ''; const n = window.prompt('编辑连线标签', c); if (n !== null) setEdges(eds => eds.map(e => e.id === edge.id ? { ...e, data: { ...(e.data as any || {}), label: n || undefined }, selected: false } : e)); }, [setEdges]);
  const onEdgeContextMenu = useCallback((e: React.MouseEvent, edge: Edge) => { e.preventDefault(); setEdgeMenu({ x: e.clientX, y: e.clientY, edgeId: edge.id }); }, []);
  const onConnect = useCallback((params: Connection) => { if (isRunning) return; if (params.source === params.target) { toast.error('不能连接自身'); return; } if (edges.some(e => e.source === params.source && e.target === params.target)) { toast.error('连线已存在'); return; } const sn = nodes.find(n => n.id === params.source); const st = (sn?.data as any)?.type || 'agent'; if (st === 'condition' && edges.filter(e => e.source === params.source).length >= 2) { toast.error('条件节点最多2条出线'); return; }             const tc: Record<string, string> = { agent: '#8b5cf6', llm: '#a78bfa', code: '#10b981', http: '#06b6d4', condition: '#f59e0b', human: '#eab308', loop: '#8b5cf6', knowledge: '#6366f1', tool: '#14b8a6', extractor: '#38bdf8' }; const bc = params.sourceHandle === 'true' ? '#10b981' : params.sourceHandle === 'false' ? '#ef4444' : params.sourceHandle === 'error' ? '#f97316' : tc[st] || '#8b5cf6'; const ov = (sn?.data as any)?.output_variables || []; const lb = ov.length ? ov.map((v: any) => v.name).join(', ') : undefined; const bl = params.sourceHandle === 'true' ? 'True' : params.sourceHandle === 'false' ? 'False' : params.sourceHandle === 'error' ? 'Error' : undefined;     const dt: any = { edgeColor: bc }; if (lb && !bl) dt.label = lb; if (bl) dt.branchLabel = bl; setEdges(eds => addEdge({ ...params, animated: false, style: { stroke: bc, strokeWidth: 2, strokeDasharray: params.sourceHandle === 'error' ? '5,5' : undefined }, type: (lb || bl) ? 'labeled' : 'smoothstep', markerEnd: { type: MarkerType.ArrowClosed, color: bc }, data: dt }, eds)); }, [setEdges, nodes, edges]);
  const handleReverseEdge = useCallback(() => { if (!edgeMenu) return; setEdges(eds => eds.map(e => { if (e.id !== edgeMenu.edgeId) return e; const sh = e.sourceHandle; let ns = ''; if (sh === 'true') ns = 'false'; else if (sh === 'false') ns = 'true'; return { ...e, selected: false, source: e.target, target: e.source, sourceHandle: ns || undefined, targetHandle: sh || undefined }; })); setEdgeMenu(null); }, [edgeMenu, setEdges]);
  const updateNode = useCallback((id: string, patch: any) => { setNodes(nds => nds.map(n => { if (n.id !== id) return n; const dt = { ...(n.data as any) }; if (patch.config) { dt.config = { ...dt.config, ...patch.config }; delete patch.config; } const u = { ...n, data: { ...dt, ...patch } }; setEditNode((p: any) => p?.id === id ? u : p); return u; })); }, [setNodes]);
  const handleSave = useCallback(() => { persist(); }, [persist]);



  const runOnCanvas = useCallback(async (skipSave = false) => {
    if (!workflowId) { toast.error('请先保存 workflow'); return; }
    if (!skipSave) await persist();
    setIsRunning(true);
    runStartRef.current = Date.now();
    setRunElapsed(0);
    const elapsedTimer = setInterval(() => setRunElapsed(Math.floor((Date.now() - runStartRef.current) / 1000)), 1000);
    try {
      const r: any = await workflowApi.execute(workflowId, { name: workflowName });
      const runId: string = r.run_id || r.project_id || '';
      setRunningPid(runId);
      setLastRunId(runId);
      setExecViewerOpen(true);
      setExecDone(false);
      setReplayMode(false);
      toast.success('流水线启动');

      // Start polling events API (SQLite-based)
      let attempts = 0;
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        attempts++;
        try {
          const rd: any = await workflowApi.getLatestEvent(runId);
          const ev = rd?.event;
          if (!ev) return;
          const s: any = (() => {
            try { return JSON.parse(ev.state_json || '{}'); } catch { return {}; }
          })();
          const phase = s.phase || 'executing';
          setNodes(nds => nds.map(n => {
            const nid = n.id;
            const done = !!s[`_stage_${nid}_done`];
            const failedId = s._stage_failed_id || '';
            const output = s[`_stage_output_${nid}`] || '';
            const _input = s[`_stage_input_${nid}`] || '';
            const elapsed = s[`_stage_elapsed_${nid}`] || 0;
            let st = 'idle';
            if (failedId === nid) st = 'failed';
            else if (done) st = 'completed';
            else if (s._graph_trace?.some((e: any) => e.node === nid && e.status === 'started')) st = 'running';
            return { ...n, data: { ...n.data, status: st, _output: output || undefined, _input: _input || undefined, _elapsed: elapsed } };
          }));
          // Update inspector variables if open
          if (inspectorNodeId) {
            const ivars: Record<string, any> = {};
            for (const key of Object.keys(s)) {
              if (key.startsWith('_stage_') && key.includes(inspectorNodeId)) {
                ivars[key.replace(`_stage_`, '').replace(`_${inspectorNodeId}`, '')] = s[key];
              }
            }
            setInspectorVars(ivars);
          }
            if (phase === 'done' || phase === 'failed' || attempts > 120) {
            if (pollRef.current) clearInterval(pollRef.current);
            clearInterval(elapsedTimer);
            const finalElapsed = Math.floor((Date.now() - runStartRef.current) / 1000);
            setRunElapsed(finalElapsed);
            setIsRunning(false);
            setExecDone(true);  // keep viewer open for results review
            if (phase === 'failed') toast.error('执行失败');
            else if (phase === 'done') {
              setNodes(nds => {
                const llmNode = nds.find(n => { const t = (n.data as any)?.type; return t === 'llm' || t === 'agent' || t === 'code'; });
                if (llmNode) { setEditNode({ ...llmNode }); setEditOpen(true); setEditTab('output'); }
                return nds;
              });
              toast.success(`执行完成 · ${finalElapsed}s`);
            }
          }
        } catch { /* keep trying */ }
      }, 1000);
    } catch (e: any) { toast.error('执行失败', e?.detail || ''); setIsRunning(false); }
  }, [workflowId, workflowName, nodes, edges, persist, setNodes]);

  const stopRun = useCallback(async () => {
    if (!runningPid || !workflowId) return;
    setStopping(true);
    try { await workflowApi.stopRun(workflowId, runningPid); }
    catch { /* best effort */ }
    if (pollRef.current) clearInterval(pollRef.current);
    setIsRunning(false); setStopping(false); setExecDone(true);
    setNodes(nds => nds.map(n => ({ ...n, data: { ...n.data, status: 'idle' } })));
  }, [runningPid, workflowId, setNodes]);

  // Cleanup timer on unmount
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  // Keep editNode in sync with nodes (polling updates nodes but not editNode separately)
  useEffect(() => {
    if (editNode && editOpen) {
      const fresh = nodes.find(n => n.id === editNode.id);
      if (fresh) setEditNode({ ...fresh });
    }
  }, [nodes, editOpen]);

  // Auto-run from workflow list's "执行" button
  useEffect(() => {
    const shouldRun = searchParams.get('run') === 'true';
    if (shouldRun && workflowId && nodes.length > 0 && !autoRunRef.current) {
      autoRunRef.current = true;
      setTimeout(() => runOnCanvas(true), 500); // skip save, data already loaded
    }
  }, [searchParams, workflowId, nodes.length, runOnCanvas]);

  /* ====================== RENDER ====================== */
  // Canvas-aware execution nodes for ExecutionViewer
  const canvasExecNodes = useMemo(() => nodes
    .filter(n => {
      const st = (n.data as any)?.status;
      return st === 'completed' || st === 'failed' || st === 'running';
    })
    .map(n => {
      const d = n.data as any;
      const type = d.type || 'agent';
      const canv: Record<string, { icon: string; color: string }> = {
        agent: { icon: '🤖', color: '#3b82f6' },
        llm: { icon: '🧠', color: '#6366f1' },
        tool: { icon: '🔧', color: '#14b8a6' },
        code: { icon: '💻', color: '#10b981' },
        http: { icon: '🌐', color: '#06b6d4' },
        condition: { icon: '🔀', color: '#f59e0b' },
        human: { icon: '👤', color: '#eab308' },
        loop: { icon: '🔄', color: '#8b5cf6' },
        knowledge: { icon: '📚', color: '#6366f1' },
        list: { icon: '📋', color: '#ec4899' },
        aggregator: { icon: '📦', color: '#84cc16' },
        assigner: { icon: '✏️', color: '#f472b6' },
        template: { icon: '📄', color: '#f97316' },
        start: { icon: '▶️', color: '#22c55e' },
        end: { icon: '🏁', color: '#ef4444' },
        extractor: { icon: '🧲', color: '#38bdf8' },
      };
      const ci = canv[type] || { icon: '📋', color: '#6b7280' };
      const incomingEdge = edges.find(e => e.target === n.id);
      return {
        id: n.id,
        type,
        name: d.label || n.id,
        status: (d.status === 'running' ? 'running' : d.status === 'completed' ? 'completed' : d.status === 'failed' ? 'failed' : 'idle') as any,
        icon: ci.icon,
        color: ci.color,
        duration: d._elapsed || 0,
        parentId: incomingEdge?.source,
        details: {
          args: d._input ? (typeof d._input === 'string' ? d._input.slice(0, 200) : d._input) : undefined,
          result: d._output ? (typeof d._output === 'string' ? d._output.slice(0, 300) : d._output) : undefined,
          kind: type,
        },
      };
    }), [nodes, edges]);

  return (<div className="h-[calc(100vh-4rem)] flex">
    {/* SIDEBAR */}
    <div className="w-56 flex-shrink-0 border-r border-dark-border bg-dark-card overflow-y-auto">
      <div className="px-3 py-3 border-b border-dark-border"><h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">节点面板</h2><p className="text-[10px] text-gray-600 mt-0.5">6 类 · 15 种 · 拖拽到画布</p></div>
      <div className="px-2 py-2 border-b border-dark-border"><input value={searchTerm} onChange={e => setSearchTerm(e.target.value)} placeholder="搜索节点..." className="w-full h-7 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500/40" /></div>
      <div className="p-2 space-y-3">
        {(() => {
          const catOrder = ['流程', 'AI', '逻辑', '数据', '集成', '交互'];
          const catIcons: Record<string, string> = { '流程': '●','AI': '✨','逻辑': '▸','数据': '📊','集成': '🔗','交互': '👆' };
          const filtered = searchTerm ? NODE_PALETTE.filter(nt => nt.label.toLowerCase().includes(searchTerm.toLowerCase()) || nt.type.includes(searchTerm.toLowerCase())) : null;
          const renderItem = (nt: any) => { const cnt = nodes.filter(n => (n.data as any)?.type === nt.type).length; return (<div key={nt.type} draggable onDragStart={e => onDragStart(e, { type: nt.type, label: nt.label })} className={`flex items-center gap-2 px-2 py-1.5 rounded text-xs cursor-grab active:cursor-grabbing hover:bg-dark-hover border border-transparent hover:border-${nt.color}-500/20 transition-colors`}><span className="text-xs">{nt.icon}</span><div className="flex-1"><div className="text-gray-200">{nt.label}</div><div className="text-[9px] text-gray-500">{nt.desc}</div></div>{cnt > 0 && <span className="text-[10px] px-1 py-0.5 rounded bg-dark-bg border border-dark-border/50 text-gray-500 font-mono">{cnt}</span>}<button onClick={e => { e.stopPropagation(); e.preventDefault(); const defs: Record<string, any> = { agent: { agentId: '', skills: [], model: 'deepseek-chat' }, llm: { model: 'deepseek-chat', prompt: '', temperature: 0.7, max_tokens: 2048 }, code: { language: 'python', snippet: 'print("hello")' }, http: { method: 'GET', url: '', headers: '{}', body: '' }, condition: { expression: '', true_label: 'True', false_label: 'False' }, human: { input_prompt: '', input_fields: '[{"name":"feedback","type":"text","required":true}]' }, loop: { source_var: '', body_template: '', loop_mode: 'sequential', max_concurrency: 5 }, knowledge: { kb_name: '', query: '', top_k: 3 }, tool: { tool_name: '', params: '{}' }, list: { operation: 'filter', list_param: '' }, template: { template: '' }, aggregator: { agg_mode: 'object' }, assigner: { target_var: '', expression: '' }, extractor: { model: 'deepseek-chat', schema: '{"name":"","age":0}', instruction: '' } }; setNodes(nds => [...nds, { id: getId(), type: 'stageNode', position: { x: 100 + Math.random() * 400, y: 100 + Math.random() * 300 }, data: { type: nt.type, label: nt.label, config: defs[nt.type] || {}, status: 'idle' } }]); }} className="ml-auto text-gray-600 hover:text-blue-400 text-xs px-1" title="快速添加">+</button></div>); };
          if (filtered) {
            return (<div><div className="text-[10px] text-gray-600 uppercase mb-1 px-1">搜索结果 ({filtered.length})</div>
              {filtered.map(renderItem)}
            </div>);
          }
          return catOrder.map(cat => {
            const items = NODE_PALETTE.filter(nt => nt.category === cat);
            if (!items.length) return null;
            const collapsed = collapsedCats[cat] || false;
            return (<div key={cat}>
              <div className="flex items-center gap-1 px-1 py-0.5 cursor-pointer hover:bg-dark-hover rounded text-[10px] text-gray-500 uppercase" onClick={() => toggleCat(cat)}>
                {collapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                <span>{catIcons[cat]}</span><span>{cat} ({items.length})</span>
              </div>
              {!collapsed && <div className="mt-0.5">{items.map(renderItem)}</div>}
            </div>);
          });
        })()}
        {!searchTerm && (() => { const collapsed = collapsedCats['agent'] || false; return (<div><div className="flex items-center gap-1 px-1 py-0.5 cursor-pointer hover:bg-dark-hover rounded text-[10px] text-gray-500 uppercase" onClick={() => toggleCat('agent')}>{collapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}<span>🤖</span><span>应用库 Agent ({Math.min(agents.length, 20)})</span></div>{!collapsed && <div className="mt-0.5">{agents.slice(0, 20).map(a => { const item = getAgentDraggable(a); return (<div key={a.id} draggable onDragStart={e => onDragStart(e, item)} className="flex items-center gap-2 px-2 py-1.5 rounded text-xs cursor-grab active:cursor-grabbing hover:bg-dark-hover border border-transparent hover:border-dark-border transition-colors"><span className="text-xs">🤖</span><div><div className="text-gray-200 truncate max-w-[130px]">{item.label}</div><div className="text-[9px] text-gray-500">{a.agent_type} · {item.model}</div></div></div>); })}</div>}</div>); })()}
        <div className="border-t border-dark-border/30 pt-2 mt-1"><div className="text-[9px] text-gray-600 uppercase mb-1 px-1">图例</div><div className="space-y-0.5">{[{ c: 'bg-blue-500', l: 'Agent' }, { c: 'bg-purple-500', l: 'LLM' }, { c: 'bg-emerald-500', l: 'Code' }, { c: 'bg-cyan-500', l: 'HTTP' }, { c: 'bg-amber-500', l: 'Condition' }, { c: 'bg-indigo-500', l: 'Knowledge' }, { c: 'bg-teal-500', l: 'Tool' }].map(({ c, l }) => (<div key={l} className="flex items-center gap-1.5 px-1 text-[10px]"><span className={`w-2 h-2 rounded-sm ${c}`} /><span className="text-gray-500">{l}</span></div>))}</div></div>
        <div className="border-t border-dark-border/30 pt-2 mt-1"><div className="text-[9px] text-gray-600 uppercase mb-1 px-1">系统变量</div><div className="space-y-0.5">{['sys.query', 'sys.user_id', 'sys.app_id', 'sys.session_id', 'sys.timestamp','sys.workflow_id','sys.workflow_run_id'].map(v => (<div key={v} onClick={() => { navigator.clipboard.writeText('{{' + v + '}}'); toast.success('已复制: {{' + v + '}}'); }} className="text-[10px] text-gray-600 hover:text-gray-400 cursor-pointer px-1 font-mono">{v}</div>))}</div></div>
      </div>
    </div>

    {/* MAIN CANVAS */}
    <div className="flex-1 flex flex-col">
      <div className="flex items-center justify-between px-4 py-2 border-b border-dark-border bg-dark-card">
        <div className="flex items-center gap-3"><button onClick={() => navigate('/core/workflows')} className="text-gray-500 hover:text-gray-300 text-xs">← 返回</button><input value={workflowName} onChange={e => setWorkflowName(e.target.value)} placeholder="未命名工作流" className="w-40 h-7 px-2 bg-dark-bg border border-dark-border rounded text-sm text-gray-200 font-semibold outline-none focus:border-blue-500/40" />
          <div className="relative">
            <button onClick={async () => { setShowVersions(v => !v); if (workflowId) { try { const r: any = await workflowApi.listVersions(workflowId); setLatestVersion(r?.latest_version || 0); setVersions(r?.versions || []); } catch {} } }}
              className="text-[10px] text-gray-500 hover:text-gray-300 font-mono bg-dark-bg px-1.5 py-0.5 rounded border border-dark-border/50">
              {latestVersion > 0 ? `v${latestVersion}` : '草稿'}
            </button>
            {showVersions && (
              <div className="absolute top-full left-0 mt-1 z-50 w-64 rounded-lg bg-dark-card border border-dark-border shadow-2xl max-h-60 overflow-y-auto">
                <div className="px-3 py-1.5 text-[10px] text-gray-500 uppercase border-b border-dark-border/30 flex justify-between items-center">
                  <span>版本历史</span>
                  <button onClick={async () => {
                    if (!workflowId) return;
                    try {
                      await workflowApi.publishVersion(workflowId, { name: workflowName });
                      toast.success('已发布');
                      const r: any = await workflowApi.listVersions(workflowId);
                      setLatestVersion(r?.latest_version || 0); setVersions(r?.versions || []);
                    } catch { toast.error('发布失败'); }
                  }} className="text-[9px] text-blue-400 hover:text-blue-300">发布当前</button>
                </div>
                {versions.length === 0 ? (
                  <div className="px-3 py-3 text-[10px] text-gray-600 text-center">暂无已发布版本</div>
                ) : (
                  versions.map((v: any) => (
                    <div key={v.id} className="flex items-center gap-2 px-3 py-1.5 hover:bg-dark-hover cursor-pointer text-[10px]" onClick={async () => {
                      if (!workflowId) return;
                      try {
                        await workflowApi.restoreVersion(workflowId, v.id);
                        // Reload workflow
                        const wf: any = await workflowApi.get(workflowId);
                        const items = wf.nodes || [];
                        if (items.length) setNodes(items.map((s: any, i: number) => ({ id: s.id || 'n_'+i, type: 'stageNode', position: s.position || { x: 50 + i * 220, y: 80 }, data: { type: (s.data?.type || s.type || 'agent'), label: (s.data?.label || s.label || 'Node'), config: (s.data?.config || s.config || {}), status: 'idle', output_variables: (s.data?.output_variables || []) } })));
                        if (wf.edges?.length) setEdges(wf.edges);
                        toast.success('已恢复到 v' + v.version);
                        setShowVersions(false);
                      } catch { toast.error('恢复失败'); }
                    }}>
                      <span className="text-gray-300 font-mono">v{v.version}</span>
                      <span className="text-gray-600 flex-1">{new Date(v.published_at * 1000).toLocaleDateString()}</span>
                    </div>
                  ))
                )}
              </div>
            )}
          </div><div className="flex items-center gap-1.5 text-[10px]"><span className="text-gray-500">节点</span><span className="text-gray-300 font-mono">{nodes.length}</span><span className="text-gray-600 mx-0.5">·</span><span className="text-gray-500">连线</span><span className="text-gray-300 font-mono">{edges.length}</span>{nodes.filter(n => n.selected).length > 0 && (<><span className="text-gray-600 mx-0.5">·</span><span className="text-blue-400">已选 {nodes.filter(n => n.selected).length}</span></>)}{history.length > 1 && (<><span className="text-gray-600 mx-0.5">·</span><span className="text-gray-500">{historyIdx + 1}/{history.length}</span></>)}{saving && <span className="text-green-400 text-[10px] ml-2 animate-pulse">保存中...</span>}{canvasSearchOpen && <input id="canvas-search-input" value={canvasSearch} onChange={e => setCanvasSearch(e.target.value)} placeholder="搜索节点..." className="ml-2 w-32 h-5 px-2 bg-dark-bg border border-blue-500/40 rounded text-[10px] text-gray-200 outline-none" />}</div></div>
        <div className="flex items-center gap-2">
          <button onClick={() => rf.fitView({ padding: 0.2 })} className="px-2 py-1 rounded text-[10px] text-gray-500 hover:text-gray-300 hover:bg-dark-hover" title="Fit View">⊞</button>
          <button onClick={() => {
            if (!nodes.length) return;
            // Auto-arrange: topological sort + layer layout
            const indeg: Record<string, number> = {};
            const out: Record<string, string[]> = {};
            nodes.forEach(n => { indeg[n.id] = 0; out[n.id] = []; });
            edges.forEach(e => { indeg[e.target] = (indeg[e.target]||0) + 1; (out[e.source]||[]).push(e.target); });
            const queue = nodes.filter(n => !indeg[n.id]).map(n => n.id);
            const layers: string[][] = [];
            const visited = new Set<string>();
            while (queue.length) {
              const layer: string[] = [];
              const len = queue.length;
              for (let i = 0; i < len; i++) {
                const nid = queue.shift()!;
                if (visited.has(nid)) continue;
                visited.add(nid); layer.push(nid);
                (out[nid]||[]).forEach(t => { indeg[t]--; if (indeg[t] === 0) queue.push(t); });
              }
              if (layer.length) layers.push(layer);
            }
            // Place nodes by layer
            setNodes(nds => {
              const map: Record<string, any> = {};
              nds.forEach(n => { map[n.id] = n; });
              layers.forEach((layer, li) => {
                layer.forEach((nid, ni) => {
                  if (map[nid]) map[nid] = { ...map[nid], position: { x: 50 + li * 250, y: 80 + ni * 120 } };
                });
              });
              return nds.map(n => map[n.id] || n);
            });
            setTimeout(() => rf.fitView({ padding: 0.2 }), 100);
          }} className="px-2 py-1 rounded text-[10px] text-gray-500 hover:text-gray-300 hover:bg-dark-hover" title="自动排列">☰</button>
          <button onClick={() => { if (!nodes.length) return; if (window.confirm(`清空画布上全部 ${nodes.length} 个节点和 ${edges.length} 条连线？`)) { setNodes([]); setEdges([]); } }} className="px-2 py-1 rounded text-[10px] text-gray-500 hover:text-red-400 hover:bg-dark-hover" title="清空">🗑</button>
          <button onClick={() => { const d = JSON.stringify({ nodes, edges }, null, 2); const b = new Blob([d], { type: 'application/json' }); const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = `workflow-${new Date().toISOString().slice(0, 10)}.json`; a.click(); URL.revokeObjectURL(u); }} className="px-2 py-1 rounded text-[10px] text-gray-500 hover:text-gray-300 hover:bg-dark-hover" title="导出JSON">⬇</button>
          <label className="px-2 py-1 rounded text-[10px] text-gray-500 hover:text-gray-300 hover:bg-dark-hover cursor-pointer" title="导入JSON">⬆<input type="file" accept=".json" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (!f) return; const r = new FileReader(); r.onload = () => { try { const d = JSON.parse(r.result as string); if (d.nodes?.length) { setNodes(d.nodes); setEdges(d.edges || []); toast.success(`已导入 ${d.nodes.length} 个节点`); } } catch { toast.error('JSON 格式无效'); } }; r.readAsText(f); e.target.value = ''; }} /></label>

          <div className="relative">
            <button onClick={async () => {
              setShowRunHistory(v => !v);
              if (workflowId) {
                try {
                  const r: any = await workflowApi.getRuns(workflowId);
                  setRunHistory(r.runs || []);
                } catch { setRunHistory([]); }
              }
            }} className="px-2 py-1 rounded text-[10px] text-gray-500 hover:text-gray-300 hover:bg-dark-hover transition-colors" title="运行历史"><History className="w-3.5 h-3.5" /></button>
            {showRunHistory && (
              <div className="absolute top-full right-0 mt-1 z-50 w-64 rounded-lg bg-dark-card border border-dark-border shadow-2xl max-h-60 overflow-y-auto">
                <div className="px-3 py-1.5 text-[10px] text-gray-500 uppercase border-b border-dark-border/30">运行历史</div>
                {runHistory.length === 0 ? (
                  <div className="px-3 py-3 text-[10px] text-gray-600 text-center">暂无运行记录</div>
                ) : (
                  runHistory.slice(0, 15).map((r, i) => (
                    <div key={r.project_id || i} className="flex items-center gap-2 px-3 py-1.5 hover:bg-dark-hover cursor-pointer text-[10px]" onClick={async () => {
                      setShowRunHistory(false);
                      if (r.project_id) {
                        try {
                          const rd: any = await workflowApi.listEvents(r.project_id);
                          const events = rd?.events || [];
                          if (events.length > 0) {
                            const lastState = (() => { try { return JSON.parse(events[events.length-1].state_json || '{}'); } catch { return {}; } })();
                            const allState: any = {};
                            for (const ev of events) {
                              try { Object.assign(allState, JSON.parse(ev.state_json || '{}')); } catch {}
                            }
                            setNodes(nds => nds.map(n => ({
                              ...n, data: { ...n.data, status: allState[`_stage_${n.id}_done`] ? 'completed' : lastState._stage_failed_id === n.id ? 'failed' : 'idle',
                                _output: allState[`_stage_output_${n.id}`] || '', _input: allState[`_stage_input_${n.id}`] || '', _elapsed: allState[`_stage_elapsed_${n.id}`] || 0 }
                            })));
                            setIsRunning(false);
                            // Open ExecutionViewer in replay mode
                            setLastRunId(r.project_id);
                            setExecViewerOpen(true);
                            setExecDone(true);
                            setReplayMode(true);
                          }
                          toast.success('已加载运行记录');
                        } catch { toast.error('加载失败'); }
                      }
                    }}>
                      {r.phase === 'done' ? <CheckCircle2 className="w-3 h-3 text-green-400" /> : r.phase === 'failed' ? <XCircle className="w-3 h-3 text-red-400" /> : <Clock className="w-3 h-3 text-amber-400" />}
                      <span className="text-gray-300 flex-1">Run {String(r.created_at||'').slice(0,10)}</span>
                      <span className="text-gray-600 font-mono">{r.project_id?.slice(0, 8)}</span>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          <Button icon={<Save className="w-3.5 h-3.5" />} onClick={handleSave} variant="secondary">保存</Button>
          {isRunning ? (
            <Button icon={stopping ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Square className="w-3.5 h-3.5" />} variant="primary" onClick={stopRun} className="!bg-red-500/20 !text-red-400 !border-red-500/30 hover:!bg-red-500/30">停止</Button>
          ) : (
            <Button icon={<Play className="w-3.5 h-3.5" />} variant="primary" onClick={() => runOnCanvas()}>运行</Button>
          )}
        </div>
      </div>
      {/* Execution Viewer — shows during + after pipeline runs */}
      {execViewerOpen && lastRunId && (
        <div style={{
          borderBottom: '1px solid #374151', display: 'flex', flexDirection: 'column',
        }}>
          <ExecutionViewer
            title={`流水线执行: ${workflowName || 'Workflow'}`}
            live={false}
            nodes={canvasExecNodes}
            running={isRunning}
            elapsed={runElapsed}
            summary={nodes.filter(n => n.data?.status === 'completed').length > 0 ? {
              pass: nodes.filter(n => n.data?.status === 'completed').length,
              warn: 0,
              fail: nodes.filter(n => n.data?.status === 'failed').length,
              total: nodes.length,
            } : undefined}
            height={320}
          />
          {execDone && (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '6px 0' }}>
              <button
                onClick={() => { setExecViewerOpen(false); setExecDone(false); }}
                style={{
                  background: '#374151', border: 'none', borderRadius: 4,
                  color: '#9ca3af', cursor: 'pointer', fontSize: 11, padding: '2px 12px',
                }}
              >
                关闭执行视图
              </button>
            </div>
          )}
        </div>
      )}
      {/* Variable Inspector panel */}
      {inspectorOpen && inspectorNodeId && (
        <div style={{
          borderBottom: '1px solid #374151', background: 'var(--dark-card, #1f2937)',
          padding: '10px 16px', display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 200, overflowY: 'auto',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: '#e5e7eb' }}>
              🔍 变量查看器 — {nodes.find(n => n.id === inspectorNodeId)?.data?.label || inspectorNodeId}
            </span>
            <button onClick={() => { setInspectorOpen(false); setInspectorNodeId(null); }} style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', fontSize: 14 }}>✕</button>
          </div>
          {Object.keys(inspectorVars).length === 0 ? (
            <div style={{ fontSize: 11, color: '#6b7280' }}>暂无变量数据 — 请在工作流执行中查看实时变量</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {Object.entries(inspectorVars).map(([key, val]) => (
                <div key={key} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  <span style={{ fontSize: 10, color: '#6366f1', minWidth: 120, fontWeight: 600 }}>{key}</span>
                  <span style={{ fontSize: 10, color: '#d1d5db', wordBreak: 'break-all', maxHeight: 60, overflowY: 'auto' }}>
                    {typeof val === 'string' ? val.slice(0, 300) : JSON.stringify(val).slice(0, 300)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {isRunning && !execViewerOpen && (
        <div className="flex items-center gap-3 px-4 py-1.5 bg-blue-500/10 border-b border-blue-500/20 text-xs">
          <Loader2 className="w-3 h-3 text-blue-400 animate-spin" />
          <span className="text-blue-300">执行中 · {runElapsed}s</span>
          <span className="text-gray-500">节点 {nodes.filter(n => n.data?.status === 'completed' || n.data?.status === 'running').length}/{nodes.length}</span>
          <span className="text-gray-600 font-mono ml-auto text-[10px]">{runningPid?.slice(0,12)}</span>
        </div>
      )}
      <div className="flex-1 bg-dark-bg relative" onDragOver={onDragOver} onDrop={onDrop} onDragLeave={() => setDragPos(null)} onContextMenu={e => { if ((e.target as HTMLElement).closest('.react-flow__node')) return; e.preventDefault(); if (!isRunning) setCanvasMenu({ x: e.clientX, y: e.clientY }); }} onClick={() => setCanvasMenu(null)}>
        {nodes.filter(n => n.selected).length > 1 && (<div className="absolute top-2 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-card border border-blue-500/30 shadow-lg text-xs"><span className="text-blue-300">已选 {nodes.filter(n => n.selected).length} 个</span><button onClick={() => setNodes(nds => nds.filter(n => !n.selected))} className="px-2 py-0.5 rounded bg-red-500/20 text-red-300 hover:bg-red-500/30">删除</button><button onClick={() => { const s = nodes.filter(n => n.selected); setCopied(JSON.parse(JSON.stringify(s))); }} className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 hover:bg-blue-500/30">复制</button><button onClick={() => setNodes(nds => nds.map(n => ({ ...n, selected: false })))} className="px-2 py-0.5 rounded bg-dark-hover text-gray-400 hover:text-gray-300">取消</button></div>)}
        <ReactFlow nodes={displayNodes} edges={displayEdges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} onNodeDoubleClick={onNodeDoubleClick} onNodeContextMenu={onNodeContextMenu} onEdgeClick={onEdgeClick} onEdgeDoubleClick={onEdgeDoubleClick} onEdgeContextMenu={onEdgeContextMenu} edgeTypes={edgeTypes} defaultEdgeOptions={{ animated: false, type: 'labeled' }}
          onNodeMouseEnter={(_e, node) => setHighlightNode(node.id)} onNodeMouseLeave={() => setHighlightNode(null)}
          nodeTypes={useMemo(() => ({ stageNode: (node: any) => {
            const icons: Record<string, string> = { start: '▶️', end: '🏁', agent: '🤖', llm: '🧠', code: '💻', http: '🌐', condition: '🔀', human: '👤', loop: '🔄', knowledge: '📚', tool: '🔧', list: '📋', aggregator: '📦', assigner: '✏️', template: '📄', extractor: '🧲' };
            const clrs: Record<string, string> = { start: 'border-green-500/40', end: 'border-red-500/40', agent: 'border-blue-500/40', llm: 'border-purple-500/40', code: 'border-emerald-500/40', http: 'border-cyan-500/40', condition: 'border-amber-500/40', human: 'border-yellow-500/40', loop: 'border-violet-500/40', knowledge: 'border-indigo-500/40', tool: 'border-teal-500/40', list: 'border-pink-500/40', aggregator: 'border-lime-500/40', assigner: 'border-rose-500/40', template: 'border-orange-500/40', extractor: 'border-sky-500/40' };
            const t = (node.data?.type as string) || 'agent'; const cfg = (node.data as any)?.config || {}; const isC = t === 'condition'; const isStart = t === 'start'; const isEnd = t === 'end'; const st = (node.data as any)?.status;
            const sc: Record<string, string> = { running: 'ring-2 ring-blue-400/50 shadow-lg shadow-blue-500/10', completed: 'ring-2 ring-green-400/30', failed: 'ring-2 ring-red-400/30', idle: '' };
            const hasIn = edges.some(e => e.target === node.id); const hasOut = edges.some(e => e.source === node.id);
            const inC = edges.filter(e => e.target === node.id).length; const outC = edges.filter(e => e.source === node.id).length;
            return (<div className={`px-3 py-2 rounded-lg border shadow-lg bg-dark-card ${clrs[t] || 'border-dark-border'} min-w-[160px] relative group ${sc[st] || ''}`} title={(node.data as any)?._output ? `输出: ${extractOutput(String((node.data as any)?._output)).slice(0,100)}` : (node.data as any)?.status === 'running' ? '执行中...' : (node.data as any)?.status === 'waiting' ? '等待上游完成' : (node.data as any)?.status === 'failed' ? '执行失败 — 点击查看详情' : ''}>
              <NodeResizer minWidth={160} minHeight={80} />
              {!isStart && (<Handle type="target" position={Position.Top} className="!w-3 !h-3 !bg-blue-500 !border-2 !border-dark-card" style={{ top: -6 }} title="接收上游数据" />)}
              {isC ? (<><Handle type="source" position={Position.Bottom} id="true" className="!w-3 !h-3 !bg-green-500 !border-2 !border-dark-card" style={{ bottom: -6, left: '30%' }} title="True 分支" /><Handle type="source" position={Position.Bottom} id="false" className="!w-3 !h-3 !bg-red-500 !border-2 !border-dark-card" style={{ bottom: -6, left: '70%' }} title="False 分支" /></>) : (<Handle type="source" position={Position.Bottom} className="!w-3 !h-3 !bg-purple-500 !border-2 !border-dark-card" style={{ bottom: -6 }} title="输出数据" />)}
              {!isEnd && (<Handle type="source" position={Position.Bottom} id="error" className="!w-3 !h-3 !bg-orange-500 !border-2 !border-dark-card" style={{ bottom: -6, left: '85%' }} title="错误分支 — 节点失败时走此路径" />)}
              <div className="flex items-center gap-1"><span className="text-xs">{icons[t] || '🤖'}</span><div className="text-xs font-bold text-gray-100 truncate pr-4">{(node.data as any)?.label || 'Node'}</div>{!hasIn && !hasOut && <span className="text-amber-500 text-[10px] ml-auto" title="未连线">⚠</span>}{!hasOut && hasIn && <span className="text-gray-600 text-[10px] ml-auto" title="终点">●</span>}{t === 'end' && <span className="text-red-400 text-xs ml-auto">🏁</span>}{t === 'start' && <span className="text-green-400 text-xs ml-auto">▶️</span>}<div className="flex items-center gap-1 ml-auto text-[9px]"><span className="text-blue-400/60" title={`${inC} 个上游`}>⬆{inC}</span><span className="text-purple-400/60" title={`${outC} 个下游`}>⬇{outC}</span></div></div>
              <div className="text-[9px] text-gray-500 font-mono mt-1">{t === 'agent' && <span>{cfg.model || '?'}</span>}{t === 'llm' && <span>{cfg.model || '?'} · T={cfg.temperature ?? 0.7}</span>}{t === 'code' && <span>{cfg.language || 'py'}</span>}{t === 'http' && <span>{cfg.method || 'GET'} {cfg.url?.slice(0, 25) || ''}</span>}{t === 'condition' && <span className="text-amber-300">{cfg.expression?.slice(0, 30) || 'expr'}</span>}{t === 'human' && <span>暂停等待输入</span>}{t === 'loop' && <span>{cfg.source_var || '?'} → items</span>}{t === 'knowledge' && <span>{cfg.kb_name || '?'} · top_k={cfg.top_k ?? 3}</span>}{t === 'tool' && <span>{cfg.tool_name || '?'}</span>}{t === 'list' && <span>{cfg.operation || 'filter'}</span>}{t === 'aggregator' && <span>merge upstream</span>}{t === 'assigner' && <span>{cfg.target_var || '?'}</span>}{t === 'template' && <span>Jinja2</span>}{t === 'extractor' && <span>{cfg.model || '?'} · schema keys: {cfg.schema_keys || '?'}</span>}</div>
              <div className="text-[9px] text-gray-600 mt-1 border-t border-dark-border/30 pt-1"><span className="text-blue-400/60">in:</span> upstream{t === 'agent' && <span className="ml-2"><span className="text-purple-400/60">out:</span> artifact</span>}{t === 'llm' && <span className="ml-2"><span className="text-purple-400/60">out:</span> text</span>}{t === 'code' && <span className="ml-2"><span className="text-purple-400/60">out:</span> result</span>}{t === 'http' && <span className="ml-2"><span className="text-purple-400/60">out:</span> response</span>}{isC && <span className="ml-2"><span className="text-purple-400/60">out:</span> True | False</span>}{t === 'human' && <span className="ml-2"><span className="text-purple-400/60">out:</span> form_data</span>}{t === 'loop' && <span className="ml-2"><span className="text-purple-400/60">out:</span> results</span>}{t === 'knowledge' && <span className="ml-2"><span className="text-purple-400/60">out:</span> chunks</span>}{t === 'tool' && <span className="ml-2"><span className="text-purple-400/60">out:</span> result</span>}{t === 'list' && <span className="ml-2"><span className="text-purple-400/60">out:</span> items</span>}{t === 'aggregator' && <span className="ml-2"><span className="text-purple-400/60">out:</span> combined</span>}{t === 'assigner' && <span className="ml-2"><span className="text-purple-400/60">out:</span> {cfg.target_var || 'var'}</span>}{t === 'template' && <span className="ml-2"><span className="text-purple-400/60">out:</span> text</span>}{t === 'extractor' && <span className="ml-2"><span className="text-purple-400/60">out:</span> JSON</span>}</div>
              {isC && <div className="text-[9px] flex justify-between mt-0.5"><span className="text-green-400">T: {cfg.true_label || 'True'}</span><span className="text-red-400">F: {cfg.false_label || 'False'}</span></div>}
              {(node.data as any)?.description && <div className="text-[9px] text-gray-600 mt-1 italic truncate">{(node.data as any)?.description}</div>}
              {(node.data as any)?._elapsed >= 0 && st === 'completed' && <div className="text-[9px] text-green-400 mt-0.5 font-mono">{(node.data as any)._elapsed > 0 ? `${(node.data as any)._elapsed}s` : '0ms'}</div>}
              {st === 'failed' && (node.data as any)?._output && <div className="text-[8px] text-red-400 mt-1 truncate max-w-[150px]">{extractOutput(String((node.data as any)?._output)).slice(0,60)}</div>}
              {st === 'running' && <div className="absolute -top-1 -left-1 w-3 h-3 rounded-full bg-blue-400 animate-pulse ring-2 ring-blue-400/30" title="执行中" />}
              {st === 'completed' && <div className="absolute -top-1 -left-1 w-3 h-3 rounded-full bg-green-400 ring-2 ring-green-400/30" title="已完成" />}
              {st === 'failed' && <div className="absolute -top-1 -left-1 w-3 h-3 rounded-full bg-red-400 ring-2 ring-red-400/30" title="失败" />}
              {st === 'waiting' && <div className="absolute -top-1 -left-1 w-3 h-3 rounded-full bg-amber-400 animate-pulse ring-2 ring-amber-400/20" title="等待上游完成" />}
              {st === 'exception' && <div className="absolute -top-1 -left-1 w-3 h-3 rounded-full bg-orange-500 ring-2 ring-orange-500/30" title="异常" />}
              {st === 'waiting' && <div className="absolute inset-0 bg-dark-bg/60 rounded-lg" />}
              <div className="absolute -top-2 -right-2 flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity"><button className="w-5 h-5 rounded-full bg-blue-500/30 border border-blue-500/50 flex items-center justify-center" onClick={ev => { ev.stopPropagation(); setNodes(nds => { const src = nds.find(n => n.id === node.id); if (!src) return nds; return [...nds, { ...JSON.parse(JSON.stringify(src)), id: getId(), position: { x: src.position.x + 20, y: src.position.y + 20 }, selected: false }]; }); }} title="复制"><span className="text-blue-300 text-[10px] font-bold">+</span></button><button className="w-5 h-5 rounded-full bg-red-500/30 border border-red-500/50 flex items-center justify-center" onClick={() => setNodes(nds => nds.filter(n => n.id !== node.id))} title="删除"><span className="text-red-300 text-[10px] font-bold">×</span></button></div>
            </div>);
          } } as any), [setNodes, edges])} fitView deleteKeyCode={['Backspace', 'Delete']}>
          <style>{`.react-flow__controls-button{background:#1f2937!important;border-color:#374151!important}.react-flow__controls-button:hover{background:#374151!important}.react-flow__controls-button svg{fill:#9ca3af!important}.react-flow__minimap{background:#111827!important;border:1px solid #374151!important;border-radius:8px!important}.react-flow__attribution{display:none!important}`}</style>
          <Background color="#374151" gap={16} /><Controls /><MiniMap nodeColor={(n: any) => ({ agent: '#3b82f6', llm: '#8b5cf6', code: '#10b981', http: '#06b6d4', condition: '#f59e0b' } as any)[n?.data?.type] || '#6b7280'} className="!bg-dark-card !border-dark-border" maskColor="rgba(0,0,0,0.6)" />
        </ReactFlow>
        {dragPos && <div className="absolute pointer-events-none z-40 px-3 py-2 rounded-lg border border-blue-500/40 bg-blue-500/10 text-xs text-blue-300" style={{ left: dragPos.x - 80, top: dragPos.y - 20 }}>+ 放置节点</div>}
        {selectedEdgeId && (() => { const e = edges.find(ed => ed.id === selectedEdgeId); if (!e) return null; const src = nodes.find(n => n.id === e?.source); const tgt = nodes.find(n => n.id === e?.target); const lb = (e.data as any)?.label; return (<div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-30 px-3 py-1.5 rounded-lg bg-dark-card border border-blue-500/30 shadow-lg text-[10px] flex items-center gap-2"><span className="text-gray-400">{(src?.data as any)?.label || e.source}</span><span className="text-blue-400">→</span><span className="text-gray-300">{(tgt?.data as any)?.label || e.target}</span>{lb && <span className="text-gray-500 ml-1">({lb})</span>}<button onClick={() => setEdges(eds => eds.filter(ed => ed.id !== selectedEdgeId))} className="ml-2 text-red-400 hover:text-red-300">✕</button></div>); })()}
      </div>
      {/* NODE CONTEXT MENU */}
      {menu && (<div className="fixed z-50" style={{ left: menu.x, top: menu.y }} onMouseLeave={() => setMenu(null)} onClick={() => setMenu(null)}><div className="bg-dark-card border border-dark-border rounded-lg shadow-2xl py-1 min-w-[120px]"><button className="w-full text-left px-3 py-1.5 text-xs text-gray-300 hover:bg-dark-hover" onClick={() => { setNodes(nds => nds.filter(n => n.id !== menu.nodeId)); setMenu(null); }}>✕ 删除节点</button><button className="w-full text-left px-3 py-1.5 text-xs text-gray-300 hover:bg-dark-hover" onClick={() => { navigator.clipboard.writeText(menu.nodeId); toast.success('ID已复制'); setMenu(null); }}>📋 复制ID</button><button className="w-full text-left px-3 py-1.5 text-xs text-gray-300 hover:bg-dark-hover" onClick={() => { setInspectorNodeId(menu.nodeId); setInspectorOpen(true); setMenu(null); }}>🔍 变量查看</button><button className="w-full text-left px-3 py-1.5 text-xs text-blue-300 hover:bg-dark-hover" onClick={() => { setStepRunNodeId(menu.nodeId); setStepRunInput('{}'); setStepRunResult(null); setStepRunOpen(true); setMenu(null); }}>▶ Step-Run</button><div className="border-t border-dark-border/30 my-0.5" /><button className="w-full text-left px-3 py-1.5 text-xs text-amber-400 hover:bg-dark-hover" onClick={() => { setNodes(nds => nds.map(n => n.id === menu.nodeId ? { ...n, data: { ...n.data, status: 'waiting' } } : n)); setMenu(null); }}>⏳ 模拟等待</button><button className="w-full text-left px-3 py-1.5 text-xs text-orange-400 hover:bg-dark-hover" onClick={() => { setNodes(nds => nds.map(n => n.id === menu.nodeId ? { ...n, data: { ...n.data, status: 'exception' } } : n)); setMenu(null); }}>⚠ 模拟异常</button></div></div>)}
      {/* EDGE CONTEXT MENU */}
      {edgeMenu && (<div className="fixed z-50" style={{ left: edgeMenu.x, top: edgeMenu.y }} onMouseLeave={() => setEdgeMenu(null)} onClick={() => setEdgeMenu(null)}><div className="bg-dark-card border border-dark-border rounded-lg shadow-2xl py-1 min-w-[130px]"><button className="w-full text-left px-3 py-1.5 text-xs text-gray-300 hover:bg-dark-hover" onClick={handleReverseEdge}>↔ 反转连线</button><button className="w-full text-left px-3 py-1.5 text-xs text-gray-300 hover:bg-dark-hover" onClick={() => { setEdges(eds => eds.filter(e => e.id !== edgeMenu.edgeId)); setEdgeMenu(null); }}>✕ 删除连线</button></div></div>)}
      {/* CANVAS CONTEXT MENU */}
      {canvasMenu && (<div className="fixed z-50" style={{ left: canvasMenu.x, top: canvasMenu.y }} onMouseLeave={() => setCanvasMenu(null)} onClick={() => setCanvasMenu(null)}><div className="bg-dark-card border border-dark-border rounded-lg shadow-2xl py-1 min-w-[130px]"><div className="px-3 py-1 text-[10px] text-gray-500 uppercase">添加节点</div>{NODE_PALETTE.map(nt => (<button key={nt.type} className="w-full text-left px-3 py-1.5 text-xs text-gray-300 hover:bg-dark-hover flex items-center gap-2" onClick={() => { const pos = rf.screenToFlowPosition({ x: canvasMenu.x - 200, y: canvasMenu.y - 80 }); const defs: Record<string, any> = { agent: { agentId: '', skills: [], model: 'deepseek-chat' }, llm: { model: 'deepseek-chat', prompt: '', temperature: 0.7, max_tokens: 2048 }, code: { language: 'python', snippet: 'print("hello")' }, http: { method: 'GET', url: '', headers: '{}', body: '' }, condition: { expression: '', true_label: 'True', false_label: 'False' }, human: { input_prompt: '', input_fields: '[{"name":"feedback","type":"text","required":true}]' }, loop: { source_var: '', body_template: '', loop_mode: 'sequential', max_concurrency: 5 }, knowledge: { kb_name: '', query: '', top_k: 3 }, tool: { tool_name: '', params: '{}' }, list: { operation: 'filter', list_param: '' }, template: { template: '' }, aggregator: { agg_mode: 'object' }, assigner: { target_var: '', expression: '' }, extractor: { model: 'deepseek-chat', schema: '{"name":"","age":0}', instruction: '' } }; setNodes(nds => [...nds, { id: getId(), type: 'stageNode', position: pos, data: { type: nt.type, label: nt.label, config: defs[nt.type] || {}, status: 'idle' } }]); setCanvasMenu(null); }}><span className="text-xs">{nt.icon}</span><span>{nt.label}</span></button>))}{copied && copied.length > 0 && (<button className="w-full text-left px-3 py-1.5 text-xs text-gray-300 hover:bg-dark-hover border-t border-dark-border/30 mt-0.5" onClick={() => { const pos = rf.screenToFlowPosition({ x: canvasMenu.x - 200, y: canvasMenu.y - 80 }); setNodes(nds => [...nds, ...(copied || []).map((n: any, i: number) => ({ ...JSON.parse(JSON.stringify(n)), id: getId(), position: { x: pos.x + i * 20, y: pos.y + i * 20 }, selected: false }))]); setCanvasMenu(null); }}>📋 粘贴已复制 ({(copied || []).length})</button>)}</div></div>)}
    </div>

    {/* EDIT PANEL */}
    {editOpen && editNode && (<div className="fixed inset-0 z-50"><div className="absolute inset-0 bg-black/20" onClick={() => setEditOpen(false)} /><div className="absolute right-0 top-0 bottom-0 w-[420px] bg-dark-card border-l border-dark-border shadow-2xl overflow-y-auto"><div className="sticky top-0 bg-dark-card border-b border-dark-border px-5 py-3 flex items-center justify-between"><div className="flex items-center gap-4"><h2 className="text-sm font-semibold text-gray-100">节点配置</h2><button onClick={() => { const defs: Record<string, any> = { agent: { agentId: '', skills: [], model: 'deepseek-chat' }, llm: { model: 'deepseek-chat', prompt: '', temperature: 0.7, max_tokens: 2048 }, code: { language: 'python', snippet: 'print("hello")' }, http: { method: 'GET', url: '', headers: '{}', body: '' }, condition: { expression: '', true_label: 'True', false_label: 'False' }, human: { input_prompt: '', input_fields: '[{"name":"feedback","type":"text","required":true}]' }, loop: { source_var: '', body_template: '', loop_mode: 'sequential', max_concurrency: 5 }, knowledge: { kb_name: '', query: '', top_k: 3 }, tool: { tool_name: '', params: '{}' }, list: { operation: 'filter', list_param: '' }, template: { template: '' }, aggregator: { agg_mode: 'object' }, assigner: { target_var: '', expression: '' }, extractor: { model: 'deepseek-chat', schema: '{"name":"","age":0}', instruction: '' } }; const t = (editNode.data as any).type || 'agent'; updateNode(editNode.id, { config: defs[t] || {}, output_variables: [] }); }} className="text-[10px] text-gray-600 hover:text-gray-400">↺ 重置</button><div className="flex rounded bg-dark-bg border border-dark-border overflow-hidden"><button onClick={() => setEditTab('config')} className={`px-2.5 py-1 text-xs ${editTab === 'config' ? 'bg-blue-500/20 text-blue-300' : 'text-gray-500 hover:text-gray-300'}`}>配置</button><button onClick={() => setEditTab('output')} className={`px-2.5 py-1 text-xs border-l border-dark-border ${editTab === 'output' ? 'bg-blue-500/20 text-blue-300' : 'text-gray-500 hover:text-gray-300'}`}>输出</button></div></div><button onClick={() => setEditOpen(false)} className="text-gray-500 hover:text-gray-300 text-lg">✕</button></div>
      {editTab === 'config' ? (<div className="p-5 space-y-4" onFocusCapture={e => { const t = e.target as HTMLElement; if (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA') lastInputRef.current = t as any; }}>
        <div><div className="text-sm text-gray-400 mb-1">节点类型</div><select value={(editNode.data as any).type || 'agent'} onChange={e => { const t = e.target.value; const defs: Record<string, any> = { agent: { agentId: '', skills: [], model: 'deepseek-chat' }, llm: { model: 'deepseek-chat', prompt: '', temperature: 0.7, max_tokens: 2048 }, code: { language: 'python', snippet: 'print("hello")' }, http: { method: 'GET', url: '', headers: '{}', body: '' }, condition: { expression: '', true_label: 'True', false_label: 'False' }, human: { input_prompt: '', input_fields: '[{"name":"feedback","type":"text","required":true}]' }, loop: { source_var: '', body_template: '', loop_mode: 'sequential', max_concurrency: 5 }, knowledge: { kb_name: '', query: '', top_k: 3 }, tool: { tool_name: '', params: '{}' }, list: { operation: 'filter', list_param: '' }, template: { template: '' }, aggregator: { agg_mode: 'object' }, assigner: { target_var: '', expression: '' }, extractor: { model: 'deepseek-chat', schema: '{"name":"","age":0}', instruction: '' } }; setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, type: t, config: defs[t] || {} } } : n)); setEditNode({ ...editNode, data: { ...editNode.data, type: t, config: defs[t] || {} } }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"><option value="agent">🤖 Agent</option><option value="llm">🧠 LLM</option><option value="code">💻 Code</option><option value="http">🌐 HTTP</option><option value="human">👤 Human Input</option><option value="loop">🔄 Loop</option><option value="condition">🔀 Condition</option><option value="knowledge">📚 Knowledge</option><option value="tool">🔧 Tool</option><option value="template">📄 Template</option><option value="list">📋 List Op</option><option value="aggregator">📦 Aggregator</option><option value="assigner">✏️ Assigner</option><option value="extractor">🧲 Param Extract</option></select></div>
        {(() => { const t = (editNode.data as any).type; const tips: Record<string, string> = { start: '流程入口节点，无输入，定义初始变量和触发条件。每个工作流必须有一个 Start。', end: '流程出口节点，接收上游结果并输出最终返回值。每个工作流必须有一个 End。', agent: 'AI Agent 执行节点，调用配置的 Agent 完成推理/行动循环。接收上游产物作为输入，输出新的 artifact。', llm: '直接调用大语言模型，发送 Prompt 并获取文本回复。支持配置 Model、Temperature、JSON 输出 Schema、Vision 图片输入。', code: '在安全沙箱中执行代码片段（Python/JS/Bash/SQL），返回执行结果。CPU/内存受限，超时自动终止。', http: '发起 HTTP API 请求（GET/POST/PUT/DELETE），支持自定义 Headers/Body 和重试策略，返回响应数据。', condition: '根据条件表达式求值（True/False），将流程分叉到两条不同路径。支持多条件规则（AND/OR）和 11 种比较操作符。', human: '暂停流水线等待人工输入或审批，配置输入字段表单，用户提交后恢复执行。', loop: '遍历数组变量中的每个元素，对每个元素执行子模板（Jinja2 渲染），支持并行/串行模式，输出结果列表。', knowledge: '知识库检索增强生成（RAG），从指定知识库中检索相关文档片段，支持 LLM 重排序和向量检索。', tool: '调用已注册的 Tool（工具函数），传入 JSON 参数，获取工具执行结果。走 sys_tool_call 安全通道。', template: 'Jinja2 模板渲染节点，使用上游变量渲染文本模板，支持 {{var.path}} 深度变量访问和系统变量注入。', list: '列表操作节点，对上游数组变量进行过滤、排序、切片、映射等操作，输出处理后的新数组。', aggregator: '多分支聚合节点，将多个上游分支的输出合并为单个对象或数组，常用于条件分支后的汇合点。', assigner: '变量赋值/转换节点，执行表达式计算并将结果写入指定变量，支持 Jinja2 表达式和类型转换。', extractor: '参数提取节点，使用 LLM 将自然语言输入转换为结构化 JSON 参数，支持自定义 schema。' }; const tip = tips[t]; return tip ? (<div className="p-3 rounded-lg bg-dark-bg border border-dark-border/50 text-[11px] text-gray-400 leading-relaxed">{tip}</div>) : null; })()}
        <div><div className="text-sm text-gray-400 mb-1">名称</div><input value={(editNode.data as any).label || ''} onChange={e => { setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, label: e.target.value } } : n)); setEditNode({ ...editNode, data: { ...editNode.data, label: e.target.value } }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100" placeholder="节点名称" /></div>
        <div><div className="text-sm text-gray-400 mb-1">描述</div><textarea value={(editNode.data as any).description || ''} onChange={e => { setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, description: e.target.value } } : n)); setEditNode({ ...editNode, data: { ...editNode.data, description: e.target.value } }); }} rows={2} className="w-full px-3 py-1.5 bg-dark-card border border-dark-border rounded-lg text-xs text-gray-400 resize-none" placeholder="节点用途说明 (可选)" /></div>
        {(() => {
          const nt = (editNode.data as any).type;
          if (nt === 'start') return null;
          // Upstream variable reference (read-only hint)
          const uids = edges.filter(e => e.target === editNode?.id).map(e => e.source);
          const upstreamRefs: string[] = [];
          nodes.filter(n => uids.includes(n.id)).forEach(un => {
            const uname = (un.data as any)?.label || un.id;
            const si = (un.data as any)?.start_inputs || [];
            si.forEach((s: any) => { if (s.key) upstreamRefs.push(`start.${s.key} (← ${uname})`); });
            ((un.data as any)?.output_variables || []).forEach((v: any) => {
              if (v.name) upstreamRefs.push(`${uname}.${v.name} (← ${uname})`);
            });
          });
          return (
            <div>
              {upstreamRefs.length > 0 && (
                <div className="mb-2 p-2 rounded bg-dark-bg border border-dark-border/30">
                  <div className="text-[10px] text-gray-600 mb-1">上游可用变量</div>
                  <div className="flex flex-wrap gap-1">
                    {upstreamRefs.map((ref, ri) => (
                      <button key={ri} onClick={() => {
                        const varName = ref.split(' (←')[0];
                        // Insert into last focused input or the first input_variable value field
                        const field = document.querySelector('[data-ivar-idx]') as HTMLInputElement;
                        if (field) {
                          field.focus();
                          const val = field.value;
                          const pos = field.selectionStart || val.length;
                          field.value = val.slice(0, pos) + `{{${varName}}}` + val.slice(pos);
                          field.dispatchEvent(new Event('input', {bubbles: true}));
                        }
                      }} className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-400 hover:text-blue-300 hover:border-blue-500/40 font-mono transition-colors">
                        {ref}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div className="text-sm text-gray-400 mb-1">输入变量 <span className="text-[10px] text-gray-600">(自定义绑定, 默认值支持 {'{{}}'} 引用上游)</span></div>
              <div className="space-y-1.5">
                {((editNode.data as any).input_variables || []).map((v: any, vi: number) => (
                  <div key={vi} className="flex gap-1 items-center">
                    <select value={v.type || 'string'} onChange={e => {
                      const ivs = [...((editNode.data as any).input_variables || [])];
                      ivs[vi] = { ...ivs[vi], type: e.target.value };
                      setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, input_variables: ivs } } : n));
                      setEditNode({ ...editNode, data: { ...editNode.data, input_variables: ivs } });
                    }} className="h-8 w-16 px-1 bg-dark-bg border border-dark-border rounded text-xs text-gray-400">
                      <option value="string">str</option><option value="number">num</option><option value="boolean">bool</option>
                      <option value="object">obj</option><option value="array">arr</option><option value="file">file</option>
                    </select>
                    <input value={v.name || ''} onChange={e => {
                      const ivs = [...((editNode.data as any).input_variables || [])];
                      ivs[vi] = { ...ivs[vi], name: e.target.value };
                      setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, input_variables: ivs } } : n));
                      setEditNode({ ...editNode, data: { ...editNode.data, input_variables: ivs } });
                    }} placeholder="变量名" className="flex-1 h-8 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-200 font-mono" />
                    <input value={v.value || ''} data-ivar-idx={vi} onChange={e => {
                      const ivs = [...((editNode.data as any).input_variables || [])];
                      ivs[vi] = { ...ivs[vi], value: e.target.value };
                      setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, input_variables: ivs } } : n));
                      setEditNode({ ...editNode, data: { ...editNode.data, input_variables: ivs } });
                    }} placeholder="默认值 / {{上游引用}}" className="flex-1 h-8 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-400 font-mono" />
                    <input value={v.description || ''} onChange={e => {
                      const ivs = [...((editNode.data as any).input_variables || [])];
                      ivs[vi] = { ...ivs[vi], description: e.target.value };
                      setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, input_variables: ivs } } : n));
                      setEditNode({ ...editNode, data: { ...editNode.data, input_variables: ivs } });
                    }} placeholder="描述" className="w-16 h-8 px-1 bg-dark-bg border border-dark-border rounded text-xs text-gray-400" />
                    <button onClick={() => {
                      const ivs = ((editNode.data as any).input_variables || []).filter((_: any, i: number) => i !== vi);
                      setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, input_variables: ivs } } : n));
                      setEditNode({ ...editNode, data: { ...editNode.data, input_variables: ivs } });
                    }} className="text-gray-600 hover:text-red-400 text-sm px-1">✕</button>
                  </div>
                ))}
                <button onClick={() => {
                  const ivs = [...((editNode.data as any).input_variables || []), { name: '', type: 'string', value: '', description: '' }];
                  setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, input_variables: ivs } } : n));
                  setEditNode({ ...editNode, data: { ...editNode.data, input_variables: ivs } });
                }} className="text-xs text-blue-400 hover:text-blue-300">+ 添加变量</button>
              </div>
            </div>
          );
        })()}
        <div><div className="text-sm text-gray-400 mb-1">输出变量</div><div className="space-y-1.5">{((editNode.data as any).output_variables || []).map((v: any, vi: number) => (<div key={vi} className="flex gap-1 items-center"><select value={v.type || 'string'} onChange={e => { const ovs = [...((editNode.data as any).output_variables || [])]; ovs[vi] = { ...ovs[vi], type: e.target.value }; setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, output_variables: ovs } } : n)); setEditNode({ ...editNode, data: { ...editNode.data, output_variables: ovs } }); }} className="h-8 w-16 px-1 bg-dark-bg border border-dark-border rounded text-xs text-gray-400"><option value="string">str</option><option value="number">num</option><option value="boolean">bool</option><option value="object">obj</option><option value="array">arr</option><option value="file">file</option></select><input value={v.name || ''} onChange={e => { const ovs = [...((editNode.data as any).output_variables || [])]; ovs[vi] = { ...ovs[vi], name: e.target.value }; setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, output_variables: ovs } } : n)); setEditNode({ ...editNode, data: { ...editNode.data, output_variables: ovs } }); }} placeholder="变量名" className="flex-1 h-8 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-200 font-mono" /><input value={v.description || ''} onChange={e => { const ovs = [...((editNode.data as any).output_variables || [])]; ovs[vi] = { ...ovs[vi], description: e.target.value }; setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, output_variables: ovs } } : n)); setEditNode({ ...editNode, data: { ...editNode.data, output_variables: ovs } }); }} placeholder="描述" className="flex-1 h-8 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-400" /><input value={v.default || ''} onChange={e => { const ovs = [...((editNode.data as any).output_variables || [])]; ovs[vi] = {...ovs[vi], default: e.target.value}; setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data:{...n.data,output_variables:ovs} } : n)); setEditNode({...editNode, data:{...editNode.data,output_variables:ovs}}); }} placeholder="默认值" className="w-16 h-8 px-1 bg-dark-bg border border-dark-border rounded text-xs text-gray-500 font-mono" /><button onClick={() => { const ovs = ((editNode.data as any).output_variables || []).filter((_: any, i: number) => i !== vi); setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, output_variables: ovs } } : n)); setEditNode({ ...editNode, data: { ...editNode.data, output_variables: ovs } }); }} className="text-gray-600 hover:text-red-400 text-sm px-1">✕</button></div>))}<button onClick={() => { const ovs = [...((editNode.data as any).output_variables || []), { name: '', description: '', type: 'string', default: '' }]; setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, output_variables: ovs } } : n)); setEditNode({ ...editNode, data: { ...editNode.data, output_variables: ovs } }); }} className="text-xs text-blue-400 hover:text-blue-300">+ 添加变量</button></div></div>
        {/* type configs */}
        {(editNode.data as any).type === 'start' && (
          <div>
            <div className="text-sm text-gray-400 mb-1">测试输入变量 <span className="text-[10px] text-gray-600">(下游引用: {'{{start.变量名}}'})</span></div>
            <div className="space-y-1.5">
              {((editNode.data as any).start_inputs || []).map((si: any, sii: number) => (
                <div key={sii} className="flex gap-1 items-center">
                  <input value={si.key || ''} onChange={e => {
                    const sis = [...((editNode.data as any).start_inputs || [])];
                    sis[sii] = { ...sis[sii], key: e.target.value };
                    setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, start_inputs: sis } } : n));
                    setEditNode({ ...editNode, data: { ...editNode.data, start_inputs: sis } });
                  }} placeholder="变量名" className="flex-1 h-8 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-200 font-mono" />
                  <input value={si.value || ''} onChange={e => {
                    const sis = [...((editNode.data as any).start_inputs || [])];
                    sis[sii] = { ...sis[sii], value: e.target.value };
                    setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, start_inputs: sis } } : n));
                    setEditNode({ ...editNode, data: { ...editNode.data, start_inputs: sis } });
                  }} placeholder="测试值" className="flex-1 h-8 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-400 font-mono" />
                  <button onClick={() => {
                    const sis = ((editNode.data as any).start_inputs || []).filter((_:any,i:number) => i!==sii);
                    setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, start_inputs: sis } } : n));
                    setEditNode({ ...editNode, data: { ...editNode.data, start_inputs: sis } });
                  }} className="text-gray-600 hover:text-red-400 text-sm px-1">✕</button>
                </div>
              ))}
              <button onClick={() => {
                const sis = [...((editNode.data as any).start_inputs || []), { key: '', value: '' }];
                setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, start_inputs: sis } } : n));
                setEditNode({ ...editNode, data: { ...editNode.data, start_inputs: sis } });
              }} className="text-xs text-blue-400 hover:text-blue-300">+ 添加变量</button>
            </div>
          </div>
        )}
        {(editNode.data as any).type === 'agent' && (<div className="space-y-3"><div><div className="text-sm text-gray-400 mb-1">Model</div><input value={(editNode.data as any).config?.model || 'deepseek-chat'} onChange={e => { const cfg = { ...(editNode.data as any).config, model: e.target.value }; setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, config: cfg } } : n)); setEditNode({ ...editNode, data: { ...editNode.data, config: cfg } }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100" /></div><div><div className="text-sm text-gray-400 mb-1">Skills (逗号分隔)</div><input value={((editNode.data as any).config?.skills || []).join(', ')} onChange={e => { const skills = e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean); const cfg = { ...(editNode.data as any).config, skills }; setNodes(nds => nds.map(n => n.id === editNode.id ? { ...n, data: { ...n.data, config: cfg } } : n)); setEditNode({ ...editNode, data: { ...editNode.data, config: cfg } }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100" /></div><div className="flex items-center gap-1.5"><label className="flex items-center gap-1.5 text-[10px] text-gray-500 cursor-pointer"><input type="checkbox" checked={(editNode.data as any).config?.memory || false} onChange={e => { const cfg = { ...(editNode.data as any).config, memory: e.target.checked }; updateNode(editNode.id, { config: cfg }); }} className="w-3 h-3" />Memory 会话记忆</label></div></div>)}
        {(editNode.data as any).type === 'llm' && (<div className="space-y-3"><div className="grid grid-cols-2 gap-3"><div><div className="text-sm text-gray-400 mb-1">Model</div><input value={(editNode.data as any).config?.model || 'deepseek-chat'} onChange={e => { const autoT: Record<string, number> = { 'deepseek-reasoner': 0.3, 'gpt-4': 0.3, 'gpt-4o': 0.5, 'claude-3-opus': 0.3, 'claude-3-sonnet': 0.5, 'deepseek-chat': 0.7 }; const cfg = { ...(editNode.data as any).config, model: e.target.value, temperature: autoT[e.target.value] ?? ((editNode.data as any).config?.temperature ?? 0.7) }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100" /></div><div><div className="text-sm text-gray-400 mb-1">Temperature</div><input type="number" step="0.1" value={(editNode.data as any).config?.temperature ?? 0.7} onChange={e => { const cfg = { ...(editNode.data as any).config, temperature: parseFloat(e.target.value) || 0.7 }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100" /></div><div><div className="text-sm text-gray-400 mb-1">Max Tokens</div><input type="number" value={(editNode.data as any).config?.max_tokens ?? 2048} onChange={e => { const cfg = { ...(editNode.data as any).config, max_tokens: parseInt(e.target.value) || 2048 }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100" min={1} max={128000} /></div></div><div className="flex items-center gap-2 mt-2"><span className="text-[10px] text-gray-500">最大长度(字符):</span><input type="number" value={(editNode.data as any).config?.memory_window ?? 0} onChange={e => { const cfg = { ...(editNode.data as any).config, memory_window: parseInt(e.target.value) || 0 }; updateNode(editNode.id, { config: cfg }); }} className="w-16 h-6 px-1 bg-dark-bg border border-dark-border rounded text-[10px] text-gray-200" min={0} max={100000} /><span className="text-[9px] text-gray-600">(0=不限制)</span></div><div><div className="text-sm text-gray-400 mb-1">Prompt <span className="text-red-400 text-xs">*</span></div><div className="flex gap-1 mb-1">{['📝 摘要', '🌐 翻译', '🔍 审查'].map(p => (<button key={p} onClick={() => { const presets: Record<string, string> = { '📝 摘要': '请对以下内容进行简洁摘要：', '🌐 翻译': '请将以下内容翻译为中文：', '🔍 审查': '请审查以下代码并指出问题和改进建议：' }; const cfg = { ...(editNode.data as any).config, prompt: presets[p] }; updateNode(editNode.id, { config: cfg }); }} className="px-1.5 py-0.5 rounded bg-dark-bg border border-dark-border/50 text-[10px] text-gray-500 hover:text-gray-300 hover:border-blue-500/30 transition-colors">{p}</button>))}</div><textarea value={(editNode.data as any).config?.prompt || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, prompt: e.target.value }; updateNode(editNode.id, { config: cfg }); }} rows={4} className={`w-full px-3 py-2 bg-dark-card border rounded-lg text-sm text-gray-100 resize-none ${!((editNode.data as any).config?.prompt || '').trim() ? 'border-red-500/50' : 'border-dark-border'}`} placeholder="LLM system prompt..." />
            {(() => {
              const uids = edges.filter(e => e.target === editNode?.id).map(e => e.source);
              const vars: {label:string, val:string}[] = [];
              // Start inputs
              const si = (editNode?.data as any)?.start_inputs || [];
              si.forEach((s: any) => { if (s.key) vars.push({label: 'start.' + s.key, val: 'start.' + s.key}); });
              // Upstream output variables
              nodes.filter(n => uids.includes(n.id)).forEach(un => {
                (un.data as any)?.output_variables?.forEach((v: any) => {
                  if (v.name) vars.push({label: ((un.data as any)?.label || un.id) + '.' + v.name, val: v.name});
                });
              });
              // System variables
              ['sys.query','sys.user_id','sys.session_id','sys.workflow_id','sys.workflow_run_id'].forEach(sv => vars.push({label: sv, val: sv}));
              if (!vars.length) return null;
              return (
                <div className="flex flex-wrap gap-1 mb-1">
                  <span className="text-[10px] text-gray-600">变量:</span>
                  {vars.map(v => (
                    <button key={v.val} onClick={() => {
                      const ta = document.querySelector('#llm-prompt-textarea') as HTMLTextAreaElement;
                      if (ta) {
                        const start = ta.selectionStart || 0;
                        const end = ta.selectionEnd || 0;
                        const text = ((editNode.data as any).config?.prompt || '');
                        const before = text.substring(0, start);
                        const after = text.substring(end);
                        const inserted = '{{' + v.val + '}}';
                        const newText = before + inserted + after;
                        const cfg = { ...(editNode.data as any).config, prompt: newText };
                        updateNode(editNode.id, { config: cfg });
                        setTimeout(() => { ta.focus(); ta.setSelectionRange(start + inserted.length, start + inserted.length); }, 0);
                      }
                    }} className="text-[9px] px-1 py-0.5 rounded bg-dark-bg border border-dark-border/50 text-blue-400 hover:text-blue-300 hover:border-blue-500/30 font-mono transition-colors">
                      {'{' + v.label + '}'}
                    </button>
                  ))}
                </div>
              );
            })()}
            <textarea id="llm-prompt-textarea" value={(editNode.data as any).config?.prompt || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, prompt: e.target.value }; updateNode(editNode.id, { config: cfg }); }} rows={4} className={`w-full px-3 py-2 bg-dark-card border rounded-lg text-sm text-gray-100 resize-none ${!((editNode.data as any).config?.prompt || '').trim() ? 'border-red-500/50' : 'border-dark-border'}`} /><div className="flex items-center gap-2 mt-1"><label className="flex items-center gap-1.5 text-[10px] text-gray-500 cursor-pointer"><input type="checkbox" checked={(editNode.data as any).config?.vision || false} onChange={e => { const cfg = { ...(editNode.data as any).config, vision: e.target.checked }; updateNode(editNode.id, { config: cfg }); }} className="w-3 h-3" />Vision 图片输入</label>{(editNode.data as any).config?.vision && (<input value={(editNode.data as any).config?.image_url || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, image_url: e.target.value }; updateNode(editNode.id, { config: cfg }); }} placeholder="图片 URL" className="w-full h-8 mt-1 px-3 bg-dark-bg border border-dark-border rounded text-xs text-gray-200 font-mono" />)}</div><div className="mt-2"><div className="text-sm text-gray-400 mb-1">输出 Schema (JSON, 可选)</div><textarea value={(editNode.data as any).config?.output_schema || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, output_schema: e.target.value }; updateNode(editNode.id, { config: cfg }); }} rows={3} className="w-full px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-xs text-gray-100 font-mono resize-none" placeholder='{"type":"object","properties":{"name":{"type":"string"}}}'></textarea></div><div className="text-[9px] text-gray-600 text-right mt-0.5">{((editNode.data as any).config?.prompt || '').length} 字符</div></div></div>)}
        {(editNode.data as any).type === 'code' && (<div className="space-y-3"><div><div className="text-sm text-gray-400 mb-1">Language</div><select value={(editNode.data as any).config?.language || 'python'} onChange={e => { const cfg = { ...(editNode.data as any).config, language: e.target.value }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"><option>python</option><option>javascript</option><option>bash</option><option>sql</option></select></div><div><div className="text-sm text-gray-400 mb-1">Code Snippet <span className="text-red-400 text-xs">*</span></div><textarea value={(editNode.data as any).config?.snippet || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, snippet: e.target.value }; updateNode(editNode.id, { config: cfg }); }} rows={5} className={`w-full px-3 py-2 bg-dark-card border rounded-lg text-sm text-gray-100 font-mono resize-none ${!((editNode.data as any).config?.snippet || '').trim() ? 'border-red-500/50' : 'border-dark-border'}`} /></div></div>)}
        {(editNode.data as any).type === 'http' && (<div className="space-y-3"><div className="grid grid-cols-2 gap-3"><div><div className="text-sm text-gray-400 mb-1">Method</div><select value={(editNode.data as any).config?.method || 'GET'} onChange={e => { const cfg = { ...(editNode.data as any).config, method: e.target.value }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"><option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option></select></div><div><div className="text-sm text-gray-400 mb-1">URL <span className="text-red-400 text-xs">*</span></div><input value={(editNode.data as any).config?.url || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, url: e.target.value }; updateNode(editNode.id, { config: cfg }); }} className={`w-full h-10 px-3 bg-dark-card border rounded-lg text-sm text-gray-100 font-mono ${!((editNode.data as any).config?.url || '').trim() ? 'border-red-500/50' : 'border-dark-border'}`} /></div></div><div className="grid grid-cols-3 gap-2 mt-2"><div><div className="text-[10px] text-gray-500 mb-0.5">连接超时(s)</div><input type="number" value={(editNode.data as any).config?.connect_timeout ?? 10} onChange={e => { const cfg = { ...(editNode.data as any).config, connect_timeout: parseInt(e.target.value) || 10 }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-7 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-200" min={1} max={60} /></div><div><div className="text-[10px] text-gray-500 mb-0.5">读取超时(s)</div><input type="number" value={(editNode.data as any).config?.read_timeout ?? 30} onChange={e => { const cfg = { ...(editNode.data as any).config, read_timeout: parseInt(e.target.value) || 30 }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-7 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-200" min={1} max={300} /></div><div><div className="text-[10px] text-gray-500 mb-0.5">写入超时(s)</div><input type="number" value={(editNode.data as any).config?.write_timeout ?? 10} onChange={e => { const cfg = { ...(editNode.data as any).config, write_timeout: parseInt(e.target.value) || 10 }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-7 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-200" min={1} max={60} /></div></div></div>)}
        {(editNode.data as any).type === 'human' && (<div className="space-y-3"><div><div className="text-sm text-gray-400 mb-1">提示文本</div><textarea value={(editNode.data as any).config?.input_prompt || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, input_prompt: e.target.value }; updateNode(editNode.id, { config: cfg }); }} rows={3} className="w-full px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100 resize-none" placeholder="请审阅以下内容并提供反馈..."></textarea></div><div><div className="text-sm text-gray-400 mb-1">输入字段 (JSON)</div><textarea value={(editNode.data as any).config?.input_fields || '[{{"name":"feedback","type":"text","required":true}}]'} onChange={e => { const cfg = { ...(editNode.data as any).config, input_fields: e.target.value }; updateNode(editNode.id, { config: cfg }); }} rows={3} className="w-full px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-xs text-gray-100 font-mono resize-none" placeholder='[{{"name":"feedback","type":"text","required":true}}]'></textarea></div></div>)}{(editNode.data as any).type === 'loop' && (<div className="space-y-3"><div><div className="text-sm text-gray-400 mb-1">源数组变量 <span className="text-red-400 text-xs">*</span></div><select value={(editNode.data as any).config?.source_var || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, source_var: e.target.value }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"><option value="">选择上游数组变量</option>{(()=>{const uids=edges.filter(e=>e.target===editNode?.id).map(e=>e.source);const opts:{label:string,val:string}[]=[];nodes.filter(n=>uids.includes(n.id)).forEach(un=>{(un.data as any)?.output_variables?.forEach((v:any)=>{if(['array','object'].includes(v.type))opts.push({label:((un.data as any)?.label||un.id)+'.'+v.name,val:v.name});});});return opts.map(o=>(<option key={o.val} value={o.val}>{o.label}</option>));})()}</select></div><div><div className="text-sm text-gray-400 mb-1">循环体模板 (Jinja2)</div><textarea value={(editNode.data as any).config?.body_template || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, body_template: e.target.value }; updateNode(editNode.id, { config: cfg }); }} rows={4} className="w-full px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-xs text-gray-100 font-mono resize-none" placeholder="{{{{loop.item.name}}}} — 分数: {{{{loop.item.score}}}}  (loop.index={{#}})"></textarea></div><div className="grid grid-cols-2 gap-3"><div><div className="text-sm text-gray-400 mb-1">模式</div><select value={(editNode.data as any).config?.loop_mode || 'sequential'} onChange={e => { const cfg = { ...(editNode.data as any).config, loop_mode: e.target.value }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"><option value="sequential">顺序</option><option value="parallel">并行</option></select></div><div><div className="text-sm text-gray-400 mb-1">最大并行</div><input type="number" value={(editNode.data as any).config?.max_concurrency ?? 5} onChange={e => { const cfg = { ...(editNode.data as any).config, max_concurrency: parseInt(e.target.value) || 5 }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100" min={1} max={20} /></div></div></div>)}{(editNode.data as any).type === 'condition' && (<div className="space-y-3"><div><div className="flex items-center justify-between mb-1"><div className="text-sm text-gray-400">表达式 <span className="text-red-400 text-xs">*</span></div><div className="flex items-center gap-2 text-[10px]"><span className="text-gray-600">模式:</span><button onClick={() => { const cfg = {...(editNode.data as any).config, logic: 'AND', rules: (editNode.data as any).config?.rules || []}; updateNode(editNode.id, {config: cfg}); }} className={`px-1.5 py-0.5 rounded ${((editNode.data as any).config?.rules||[]).length>0 ? 'bg-blue-500/20 text-blue-300' : 'bg-dark-bg text-gray-500'}`}>多条件</button><span className="text-gray-600">|</span><button onClick={() => { const cfg = {...(editNode.data as any).config, rules: undefined}; updateNode(editNode.id, {config: cfg}); }} className={`px-1.5 py-0.5 rounded ${!((editNode.data as any).config?.rules||[]).length ? 'bg-blue-500/20 text-blue-300' : 'bg-dark-bg text-gray-500'}`}>表达式</button></div></div>{((editNode.data as any).config?.rules||[]).length>0 ? (<div className="space-y-1.5"><div className="flex items-center gap-2 mb-0.5"><span className="text-[10px] text-gray-500">逻辑</span><select value={(editNode.data as any).config?.logic || 'AND'} onChange={e => { const cfg = {...(editNode.data as any).config, logic: e.target.value}; updateNode(editNode.id, {config: cfg}); }} className="h-6 px-1 bg-dark-bg border border-dark-border rounded text-[10px] text-gray-300"><option>AND</option><option>OR</option></select></div>{((editNode.data as any).config?.rules||[]).map((r:any,ri:number)=> (<div key={ri} className="flex gap-1 items-center"><select value={r.field||''} onChange={e => { const rules = [...((editNode.data as any).config?.rules||[])]; rules[ri] = {...rules[ri], field: e.target.value}; updateNode(editNode.id, {config: {...(editNode.data as any).config, rules}}); }} className="h-7 px-1 bg-dark-bg border border-dark-border rounded text-[10px] text-gray-300 flex-1"><option value="">字段</option>{(()=>{const uids=edges.filter(e=>e.target===editNode?.id).map(e=>e.source);const opts:string[]=[];nodes.filter(n=>uids.includes(n.id)).forEach(un=>{(un.data as any)?.output_variables?.forEach((v:any)=>{opts.push(v.name)});});return opts.map(f=>(<option key={f} value={f}>{f}</option>));})()}</select><select value={r.op||'=='} onChange={e => { const rules = [...((editNode.data as any).config?.rules||[])]; rules[ri] = {...rules[ri], op: e.target.value}; updateNode(editNode.id, {config: {...(editNode.data as any).config, rules}}); }} className="h-7 px-1 bg-dark-bg border border-dark-border rounded text-[10px] text-gray-300 w-16"><option>==</option><option>!=</option><option>&gt;</option><option>&lt;</option><option>&gt;=</option><option>&lt;=</option><option>contains</option><option>is_empty</option><option>not_empty</option></select><input value={r.value||''} onChange={e => { const rules = [...((editNode.data as any).config?.rules||[])]; rules[ri] = {...rules[ri], value: e.target.value}; updateNode(editNode.id, {config: {...(editNode.data as any).config, rules}}); }} placeholder="值" className="flex-1 h-7 px-2 bg-dark-bg border border-dark-border rounded text-[10px] text-gray-200" /><button onClick={() => { const rules = ((editNode.data as any).config?.rules||[]).filter((_:any,i:number)=>i!==ri); updateNode(editNode.id, {config: {...(editNode.data as any).config, rules}}); }} className="text-gray-600 hover:text-red-400 text-xs">×</button></div>))}<button onClick={() => { const rules = [...((editNode.data as any).config?.rules||[]), {field:'',op:'==',value:''}]; updateNode(editNode.id, {config: {...(editNode.data as any).config, rules}}); }} className="text-xs text-blue-400 hover:text-blue-300">+ 添加规则</button></div>) : (<input value={(editNode.data as any).config?.expression || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, expression: e.target.value }; updateNode(editNode.id, { config: cfg }); }} className={`w-full h-10 px-3 bg-dark-card border rounded-lg text-sm text-gray-100 font-mono ${!((editNode.data as any).config?.expression || '').trim() ? 'border-red-500/50' : 'border-dark-border'}`} placeholder="output.pass_rate >= 0.8" />)}</div><div className="grid grid-cols-2 gap-3"><div><div className="text-sm text-gray-400 mb-1">True 分支</div><input value={(editNode.data as any).config?.true_label || 'True'} onChange={e => { const cfg = { ...(editNode.data as any).config, true_label: e.target.value }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100" /></div><div><div className="text-sm text-gray-400 mb-1">False 分支</div><input value={(editNode.data as any).config?.false_label || 'False'} onChange={e => { const cfg = { ...(editNode.data as any).config, false_label: e.target.value }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100" /></div></div></div>)}
        {(editNode.data as any).type === 'knowledge' && (<div className="space-y-3"><div><div className="text-sm text-gray-400 mb-1">知识库名称</div><input value={(editNode.data as any).config?.kb_name || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, kb_name: e.target.value }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100" placeholder="collection_name" /></div><div><div className="text-sm text-gray-400 mb-1">查询内容 <span className="text-red-400 text-xs">*</span></div><textarea value={(editNode.data as any).config?.query || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, query: e.target.value }; updateNode(editNode.id, { config: cfg }); }} rows={3} className={`w-full px-3 py-2 bg-dark-card border rounded-lg text-sm text-gray-100 resize-none ${!((editNode.data as any).config?.query || '').trim() ? 'border-red-500/50' : 'border-dark-border'}`} placeholder="检索关键词或问题" /></div><div><div className="text-sm text-gray-400 mb-1">Top K</div><input type="number" value={(editNode.data as any).config?.top_k ?? 3} onChange={e => { const cfg = { ...(editNode.data as any).config, top_k: parseInt(e.target.value) || 3 }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100" min={1} max={20} /></div><div className="flex items-center gap-1.5 mt-2"><label className="flex items-center gap-1.5 text-[10px] text-gray-500 cursor-pointer"><input type="checkbox" checked={(editNode.data as any).config?.rerank || false} onChange={e => { const cfg = { ...(editNode.data as any).config, rerank: e.target.checked }; updateNode(editNode.id, { config: cfg }); }} className="w-3 h-3" />LLM 重排序</label></div></div>)}
        {(editNode.data as any).type === 'tool' && (<div className="space-y-3"><div><div className="text-sm text-gray-400 mb-1">Tool 名称 <span className="text-red-400 text-xs">*</span></div><input value={(editNode.data as any).config?.tool_name || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, tool_name: e.target.value }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100" placeholder="tool_name" /></div><div><div className="text-sm text-gray-400 mb-1">参数 (JSON)</div><textarea value={(editNode.data as any).config?.params || '{}'} onChange={e => { const cfg = { ...(editNode.data as any).config, params: e.target.value }; updateNode(editNode.id, { config: cfg }); }} rows={3} className="w-full px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-xs text-gray-100 font-mono resize-none" placeholder='{"key":"value"}' /></div></div>)}{(editNode.data as any).type === 'template' && (<div className="space-y-3"><div><div className="text-sm text-gray-400 mb-1">Jinja2 模板 <span className="text-red-400 text-xs">*</span></div><textarea value={(editNode.data as any).config?.template || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, template: e.target.value }; updateNode(editNode.id, { config: cfg }); }} rows={6} className="w-full px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-xs text-gray-100 font-mono resize-none" placeholder="处理结果: {{{prd.title}}} — 评分: {{{score}}} "></textarea></div></div>)}{(editNode.data as any).type === 'list' && (<div className="space-y-3"><div><div className="text-sm text-gray-400 mb-1">操作类型</div><select value={(editNode.data as any).config?.operation || 'filter'} onChange={e => { const cfg = { ...(editNode.data as any).config, operation: e.target.value }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"><option>filter</option><option>sort</option><option>slice</option><option>map</option></select></div><div><div className="text-sm text-gray-400 mb-1">条件/参数</div><textarea value={(editNode.data as any).config?.list_param || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, list_param: e.target.value }; updateNode(editNode.id, { config: cfg }); }} rows={2} className="w-full px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-xs text-gray-100 font-mono resize-none" placeholder="filter: price>100, sort: price desc, slice: 0:10, map: item.name"></textarea></div></div>)}{(editNode.data as any).type === 'assigner' && (<div className="space-y-3"><div><div className="text-sm text-gray-400 mb-1">目标变量名 <span className="text-red-400 text-xs">*</span></div><input value={(editNode.data as any).config?.target_var || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, target_var: e.target.value }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100 font-mono" placeholder="result" /></div><div><div className="text-sm text-gray-400 mb-1">表达式 <span className="text-red-400 text-xs">*</span></div><textarea value={(editNode.data as any).config?.expression || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, expression: e.target.value }; updateNode(editNode.id, { config: cfg }); }} rows={3} className="w-full px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-xs text-gray-100 font-mono resize-none" placeholder="data['items'][:5]  — 使用 upstream vars"></textarea></div></div>)}
{(editNode.data as any).type === 'extractor' && (<div className="space-y-3"><div><div className="text-sm text-gray-400 mb-1">模型</div><input value={(editNode.data as any).config?.model || 'deepseek-chat'} onChange={e => { const cfg = { ...(editNode.data as any).config, model: e.target.value }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100" placeholder="deepseek-chat" /></div><div><div className="text-sm text-gray-400 mb-1">Schema (JSON) <span className="text-red-400 text-xs">*</span></div><textarea value={(editNode.data as any).config?.schema || '{"name":"","age":0}'} onChange={e => { const cfg = { ...(editNode.data as any).config, schema: e.target.value }; updateNode(editNode.id, { config: cfg }); }} rows={4} className="w-full px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-xs text-gray-100 font-mono resize-none" placeholder='{"name":"","age":0}' /></div><div><div className="text-sm text-gray-400 mb-1">提取指令 (可选)</div><textarea value={(editNode.data as any).config?.instruction || ''} onChange={e => { const cfg = { ...(editNode.data as any).config, instruction: e.target.value }; updateNode(editNode.id, { config: cfg }); }} rows={2} className="w-full px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-xs text-gray-100 font-mono resize-none" placeholder="提取订单信息，包括产品名称和数量" /></div></div>)}
        {/* execution options */}
        <div className="border-t border-dark-border/30 pt-3"><div className="text-[10px] text-gray-600 uppercase mb-2">执行选项</div><div className="grid grid-cols-2 gap-3"><div><div className="text-xs text-gray-500 mb-1">重试次数</div><input type="number" value={(editNode.data as any).config?.retry_count ?? 0} onChange={e => { const cfg = { ...(editNode.data as any).config, retry_count: parseInt(e.target.value) || 0 }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-8 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-200" min={0} max={5} /></div><div><div className="text-xs text-gray-500 mb-1">超时(秒)</div><input type="number" value={(editNode.data as any).config?.timeout_sec ?? 30} onChange={e => { const cfg = { ...(editNode.data as any).config, timeout_sec: parseInt(e.target.value) || 30 }; updateNode(editNode.id, { config: cfg }); }} className="w-full h-8 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-200" min={1} max={600} /></div></div></div>
        </div>        ) : (<div className="p-5 space-y-4">
          <div className="flex items-center gap-2">
            <span className={`text-xs px-2 py-0.5 rounded font-medium ${(editNode?.data as any)?.status==='completed'?'bg-green-500/10 text-green-400':(editNode?.data as any)?.status==='running'?'bg-blue-500/10 text-blue-400':(editNode?.data as any)?.status==='failed'?'bg-red-500/10 text-red-400':'bg-dark-bg text-gray-500'}`}>{(editNode?.data as any)?.status || 'idle'}</span>
            <span className="text-xs text-gray-600">{(editNode?.data as any)?.type || 'agent'}</span>
          </div>
          {(editNode?.data as any)?._input && (
            <div>
              <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
                <span>输入</span>
                <span className="text-[10px] text-gray-600">(prompt + upstream context)</span>
              </div>
              <pre className="text-xs text-gray-400 whitespace-pre-wrap break-all bg-dark-bg rounded-lg p-3 max-h-40 overflow-y-auto font-mono border border-dark-border/30">{String((editNode?.data as any)?._input || '').slice(0, 3000)}</pre>
            </div>
          )}
          {(editNode?.data as any)?._output && (
            <div>
              <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
                <span>执行输出</span>
                {(editNode?.data as any)?._elapsed ? <span className="text-green-400 font-mono">{(editNode?.data as any)?._elapsed}s</span> : null}
              </div>
              <pre className="text-xs text-gray-300 whitespace-pre-wrap break-all bg-dark-bg rounded-lg p-3 max-h-60 overflow-y-auto font-mono border border-dark-border/30">{extractOutput(String((editNode?.data as any)?._output || '')) || '(空)'}</pre>
            </div>
          )}
        </div>)
      }
    </div></div>)}


    {/* STEP-RUN DIALOG */}
    {stepRunOpen && (<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setStepRunOpen(false)}><div className="bg-dark-card border border-dark-border rounded-xl p-6 w-[400px] space-y-4" onClick={e => e.stopPropagation()}><div className="flex items-center justify-between"><h2 className="text-sm font-semibold text-gray-100">▶ Step-Run — 单步执行</h2><button onClick={() => setStepRunOpen(false)} className="text-gray-500 hover:text-gray-300">✕</button></div><div className="text-xs text-gray-400">为节点 <span className="text-blue-300">{nodes.find(n => n.id === stepRunNodeId)?.data?.label || stepRunNodeId}</span> 注入模拟输入数据</div><textarea value={stepRunInput} onChange={e => setStepRunInput(e.target.value)} rows={6} className="w-full px-3 py-2 bg-dark-bg border border-dark-border rounded-lg text-xs text-gray-200 font-mono" placeholder='{"key": "value"}' /><div className="flex items-center gap-3"><button onClick={doStepRun} disabled={stepRunning} className="px-4 py-1.5 rounded-lg bg-blue-500/20 border border-blue-500/40 text-blue-300 text-xs hover:bg-blue-500/30 disabled:opacity-50">{stepRunning ? '执行中...' : '▶ 执行'}</button><button onClick={() => setStepRunOpen(false)} className="px-4 py-1.5 rounded-lg bg-dark-hover border border-dark-border text-gray-400 text-xs hover:text-gray-300">取消</button></div>{stepRunResult && (<div className="p-3 rounded-lg bg-dark-bg border border-dark-border/50"><div className="text-xs text-gray-400 mb-2">结果{stepRunResult.elapsed_ms !== undefined ? ` · ${stepRunResult.elapsed_ms}ms` : ''}</div><pre className="text-xs text-gray-300 whitespace-pre-wrap break-all max-h-40 overflow-y-auto font-mono">{stepRunResult.error || stepRunResult.output || JSON.stringify(stepRunResult, null, 2)}</pre></div>)}</div></div>)}

    {/* HELP MODAL */}
    {helpOpen && (<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setHelpOpen(false)}><div className="bg-dark-card border border-dark-border rounded-xl p-6 w-[360px] space-y-3" onClick={e => e.stopPropagation()}><div className="flex items-center justify-between"><h2 className="text-sm font-semibold text-gray-100">快捷键</h2><button onClick={() => setHelpOpen(false)} className="text-gray-500 hover:text-gray-300">✕</button></div><div className="space-y-1 text-xs">{['Ctrl+Z 撤销', 'Ctrl+Y 重做', 'Ctrl+S 保存', 'Ctrl+C 复制', 'Ctrl+V 粘贴', 'Ctrl+A 全选', 'Ctrl+F 搜索', 'Ctrl+D 复制flow', 'Esc 取消', 'Backspace 删除', '双击节点 编辑', '双击连线 重命名', '右键节点 菜单', '右键连线 反转/删除', '右键画布 添加节点', '拖面板 创建', '? 快捷键帮助'].map(k => (<div key={k} className="text-gray-500 py-0.5"><span className="text-gray-300 font-mono">{k.split(' ')[0]}</span> {k.split(' ').slice(1).join(' ')}</div>))}</div></div></div>)}
  </div>);
};

const WorkflowCanvas: React.FC = () => (<ReactFlowProvider><CanvasInner /></ReactFlowProvider>);
export default WorkflowCanvas;
