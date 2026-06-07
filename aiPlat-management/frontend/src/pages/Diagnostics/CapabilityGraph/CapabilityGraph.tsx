import { useState, useEffect, useCallback, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Sparkles, Search } from 'lucide-react';
import { Card, CardHeader, CardContent, Button } from '../../../components/ui';

interface CapNode {
  id: string;
  type: string;
  label: string;
  raw_id?: string;
  agent_type?: string;
  status?: string;
  category?: string;
  tags?: string[];
  description?: string;
  syscalls_used?: string[];
  effects?: any[];
  enabled?: boolean;
  transport?: string;
  path?: string;
}

interface CapEdge {
  from: string;
  to: string;
  relation: string;
}

interface CapGraphData {
  nodes: CapNode[];
  edges: CapEdge[];
}

interface CapHealthData {
  score: number;
  grade: string;
  signals: {
    total_nodes: number;
    total_edges: number;
    agents: number;
    skills: number;
    used_skills: number;
    tools: number;
    mcp_servers: number;
    avg_degree: number;
  };
  issues: {
    unused_skills: string[];
    orphan_agents: string[];
    unresolved_refs: Array<{ agent: string; target: string; target_type: string }>;
  };
  top_hubs: Array<{ id: string; label: string; type: string; degree: number }>;
  top_blast: Array<{ id: string; label: string; type: string; blast: number }>;
  by_type: Record<string, number>;
}

const TYPE_ICONS: Record<string, string> = {
  agent: '🤖',
  skill: '⚡',
  tool: '🔧',
  mcp_server: '🔌',
  workflow: '⚙️',
  syscall: '📡',
};

const TYPE_COLORS: Record<string, string> = {
  agent: 'bg-purple-500/15 text-purple-300 border-purple-500/25',
  skill: 'bg-amber-500/15 text-amber-300 border-amber-500/25',
  tool: 'bg-blue-500/15 text-blue-300 border-blue-500/25',
  mcp_server: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25',
  workflow: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/25',
  syscall: 'bg-pink-500/15 text-pink-300 border-pink-500/25',
};

const RELATION_LABELS: Record<string, string> = {
  requires: '需要',
  uses: '调用',
  provides: '提供',
  maps_to: '映射到',
};

export default function CapabilityGraphPage() {
  const [searchParams] = useSearchParams();
  const [graph, setGraph] = useState<CapGraphData | null>(null);
  const [health, setHealth] = useState<CapHealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string>(searchParams.get('type') || '');
  const [q, setQ] = useState('');
  const [problemOnly, setProblemOnly] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [gRes, hRes] = await Promise.all([
        fetch('/api/core/capability-graph'),
        fetch('/api/core/capability-health'),
      ]);
      if (!gRes.ok) throw new Error(`Graph: ${gRes.status}`);
      if (!hRes.ok) throw new Error(`Health: ${hRes.status}`);
      setGraph(await gRes.json());
      setHealth(await hRes.json());
    } catch (e: any) {
      setError(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const nodeTypes = [...new Set((graph?.nodes || []).map(n => n.type))].sort();

  // Tag problematic nodes from health report
  const problemNodes = useMemo(() => {
    const map = new Map<string, string[]>(); // label → [issue tags]
    if (health?.issues) {
      for (const label of health.issues.unused_skills || []) {
        map.set(label, [...(map.get(label) || []), 'unused']);
      }
      for (const label of health.issues.orphan_agents || []) {
        map.set(label, [...(map.get(label) || []), 'orphan']);
      }
    }
    return map;
  }, [health]);

  const hasProblem = (node: CapNode) => problemNodes.has(node.label);

  const filteredNodes = (graph?.nodes || []).filter(n => {
    if (typeFilter && n.type !== typeFilter) return false;
    if (problemOnly && !hasProblem(n)) return false;
    if (q && !n.label.toLowerCase().includes(q.toLowerCase()) && !n.id.toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });
  const filteredNodeIds = new Set(filteredNodes.map(n => n.id));
  const filteredEdges = (graph?.edges || []).filter(e => filteredNodeIds.has(e.from) && filteredNodeIds.has(e.to));

  const problemTags = (node: CapNode) => {
    const tags = problemNodes.get(node.label) || [];
    return tags.map(t => {
      if (t === 'unused') return { label: '未使用', cls: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/25' };
      if (t === 'orphan') return { label: '孤立', cls: 'bg-red-500/15 text-red-300 border-red-500/25' };
      return { label: t, cls: 'bg-gray-500/15 text-gray-300' };
    });
  };

  if (loading) return <div className="flex items-center justify-center h-64 text-sm text-gray-500">加载中…</div>;
  if (error) return <div className="p-4 text-red-400">加载失败: {error}</div>;

  return (
    <div className="space-y-4 p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/diagnostics">
            <Button variant="secondary" icon={<ArrowLeft size={16} />}>
              返回
            </Button>
          </Link>
          <Sparkles className="w-5 h-5 text-amber-400" />
          <h1 className="text-lg font-semibold text-gray-100">AI 能力图谱</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={fetchData}>
            刷新
          </Button>
        </div>
      </div>

      {/* Legend */}
      <details className="bg-dark-card border border-dark-border rounded-lg p-3 text-xs text-gray-500 cursor-pointer group">
        <summary className="text-gray-400 hover:text-gray-200 select-none">📖 图例说明</summary>
        <div className="mt-3 space-y-3">
          <div>
            <div className="text-gray-300 font-medium mb-1">节点类型</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-1">
              {[
                { icon: '🤖', type: 'agent', desc: 'AI Agent（来自 AGENT.md）' },
                { icon: '⚡', type: 'skill', desc: '技能（来自 SKILL.md）' },
                { icon: '🔧', type: 'tool', desc: '工具（来自 ToolRegistry）' },
                { icon: '🔌', type: 'mcp_server', desc: 'MCP 服务器（来自 MCPManager）' },
                { icon: '⚙️', type: 'workflow', desc: '工作流（活跃 Pipeline）' },
                { icon: '📡', type: 'syscall', desc: '系统调用（sys_*）' },
              ].map(item => (
                <div key={item.type} className="flex items-center gap-1.5">
                  <span>{item.icon}</span>
                  <span className="text-gray-300">{item.type}</span>
                  <span className="text-gray-600">— {item.desc}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="text-gray-300 font-medium mb-1">边关系</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-1">
              {[
                { rel: '需要', from: 'Agent → Skill/Tool', desc: 'Agent 的 required_skills/required_tools' },
                { rel: '调用', from: 'Skill → Syscall', desc: 'SKILL.md 正文中引用的 sys_*' },
                { rel: '提供', from: 'MCP → Tool', desc: 'MCP 服务器暴露的工具' },
                { rel: '映射到', from: 'Workflow → Agent/Skill', desc: 'Pipeline Stage 绑定的 Agent' },
              ].map(item => (
                <div key={item.rel} className="flex items-center gap-1.5">
                  <span className="text-amber-300">{item.rel}</span>
                  <span className="text-gray-600">= {item.from}</span>
                  <span className="text-gray-600 hidden md:inline">— {item.desc}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="text-gray-300 font-medium mb-1">问题标签</div>
            <div className="flex flex-wrap gap-2">
              <span className="inline-block px-1.5 py-0.5 rounded text-[10px] border bg-yellow-500/15 text-yellow-300 border-yellow-500/25">未使用</span>
              <span className="text-gray-500">= Skill 没有被任何 Agent 引用</span>
              <span className="inline-block px-1.5 py-0.5 rounded text-[10px] border bg-red-500/15 text-red-300 border-red-500/25 ml-3">孤立</span>
              <span className="text-gray-500">= Agent 没有绑定任何 Skill/Tool</span>
              <span className="inline-block px-1.5 py-0.5 rounded text-[10px] border bg-red-500/15 text-red-300 border-red-500/25 ml-3">missing</span>
              <span className="text-gray-500">= Agent 引用了不存在的 Skill/Tool</span>
            </div>
          </div>
          <div>
            <div className="text-gray-300 font-medium mb-1">详情列含义</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-1">
              <div><span className="text-gray-300">agent</span><span className="text-gray-600"> — type=Agent 类型, status=状态</span></div>
              <div><span className="text-gray-300">skill</span><span className="text-gray-600"> — cat=分类, syscalls=SOP 中 syscall 引用数</span></div>
              <div><span className="text-gray-300">tool</span><span className="text-gray-600"> — 功能描述</span></div>
              <div><span className="text-gray-300">mcp_server</span><span className="text-gray-600"> — enabled/disabled + 传输方式</span></div>
            </div>
          </div>
          <div>
            <div className="text-gray-300 font-medium mb-1">Top Hubs & Blast</div>
            <div className="text-gray-600">
              <span className="text-gray-300">deg</span> = 节点的连接数（入+出），值越大越关键。
              <span className="text-gray-300 ml-3">blast</span> = 从该节点出发能到达多少个其他节点，改动影响面。
            </div>
          </div>
          <div>
            <div className="text-gray-300 font-medium mb-1">健康分</div>
            <div className="text-gray-600">
              100–90 = <span className="text-green-400">A</span> ·
              89–75 = <span className="text-green-400">B</span> ·
              74–60 = <span className="text-yellow-400">C</span> ·
              59–40 = <span className="text-yellow-400">D</span> ·
              &lt;40 = <span className="text-red-400">F</span>
              <span className="ml-2">扣分项：未使用 Skill、孤立 Agent、未解析引用、无 Tool/MCP</span>
            </div>
          </div>
        </div>
      </details>

      {/* Health bar */}
      {health && (
        <div className="flex items-center gap-3 px-4 py-2 rounded-lg bg-dark-card border border-dark-border text-xs text-gray-400">
          <span className={`font-bold text-lg ${health.score >= 75 ? 'text-green-400' : health.score >= 50 ? 'text-yellow-400' : 'text-red-400'}`}>
            {health.score} {health.grade}
          </span>
          <span className="text-gray-600">|</span>
          <span>Agent {health.signals.agents}</span>
          <span className="text-gray-600">|</span>
          <span>Skill {health.signals.used_skills}/{health.signals.skills}</span>
          <span className="text-gray-600">|</span>
          <span>Tool {health.signals.tools}</span>
          <span className="text-gray-600">|</span>
          <span>MCP {health.signals.mcp_servers}</span>
          <span className="text-gray-600">|</span>
          <span>边 {health.signals.total_edges}</span>
          {health.issues.unused_skills.length > 0 && (
            <span className="text-yellow-400 ml-auto">⚠ {health.issues.unused_skills.length} 个未使用 Skill</span>
          )}
          {health.issues.orphan_agents.length > 0 && (
            <span className="text-yellow-400 ml-2">⚠ {health.issues.orphan_agents.length} 个孤立 Agent</span>
          )}
          {health.issues.unresolved_refs?.length > 0 && (
            <span className="text-red-400 ml-2">❌ {health.issues.unresolved_refs.length} 个未解析引用</span>
          )}
        </div>
      )}

      {/* Unresolved references warning */}
      {(health?.issues?.unresolved_refs?.length || 0) > 0 && (
        <Card className="border-red-500/20 bg-red-900/10">
          <CardHeader>
            <div className="text-sm font-medium text-red-300">未解析引用</div>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {health?.issues?.unresolved_refs?.map((ref: any, i: number) => (
                <div key={i} className="text-xs text-gray-400">
                  <span className="px-1.5 py-0.5 rounded text-[10px] border bg-purple-500/15 text-purple-300 border-purple-500/25">agent</span>
                  <span className="text-gray-200 ml-1">{ref.agent}</span>
                  <span className="text-gray-500 mx-1">→</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] border bg-red-500/15 text-red-300 border-red-500/25">missing</span>
                  <span className="text-red-300 ml-1">{ref.target}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left: Node type summary */}
        <div className="lg:col-span-1 space-y-4">
          <Card>
            <CardHeader>
              <div className="text-sm font-medium text-gray-200">节点类型</div>
            </CardHeader>
            <CardContent>
              <div className="space-y-1">
                {nodeTypes.map(t => {
                  const count = filteredNodes.filter(n => n.type === t).length;
                  return (
                    <button
                      key={t}
                      onClick={() => setTypeFilter(typeFilter === t ? '' : t)}
                      className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs transition-colors
                        ${typeFilter === t ? 'bg-primary/20 text-primary' : 'text-gray-400 hover:text-gray-200 hover:bg-dark-hover'}`}
                    >
                      <span>{TYPE_ICONS[t] || '📦'}</span>
                      <span className="flex-1 text-left">{t}</span>
                      <span className="text-gray-500 font-mono">{count}</span>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* Top Hubs */}
          {health?.top_hubs && health.top_hubs.length > 0 && (
            <Card>
              <CardHeader>
                <div className="text-sm font-medium text-gray-200">Top Hubs</div>
              </CardHeader>
              <CardContent>
                <div className="space-y-1">
                  {health.top_hubs.slice(0, 10).map(h => (
                    <div key={h.id} className="flex items-center gap-2 text-xs text-gray-400">
                      <span className={TYPE_COLORS[h.type] ? `px-1.5 py-0.5 rounded text-[10px] border ${TYPE_COLORS[h.type]}` : ''}>
                        {h.type}
                      </span>
                      <span className="text-gray-200 truncate flex-1">{h.label}</span>
                      <span className="text-gray-500 font-mono">deg={h.degree}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Top Blast */}
          {health?.top_blast && health.top_blast.length > 0 && (
            <Card>
              <CardHeader>
                <div className="text-sm font-medium text-gray-200">Top Blast（影响面）</div>
              </CardHeader>
              <CardContent>
                <div className="space-y-1">
                  {health.top_blast.slice(0, 10).map(b => (
                    <div key={b.id} className="flex items-center gap-2 text-xs text-gray-400">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] border ${TYPE_COLORS[b.type] || ''}`}>
                        {b.type}
                      </span>
                      <span className="text-gray-200 truncate flex-1">{b.label}</span>
                      <span className="text-gray-500 font-mono">blast={b.blast}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right: Node + Edge tables */}
        <div className="lg:col-span-2 space-y-4">
          {/* Search */}
          <div className="flex items-center gap-2">
            <div className="flex-1 relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" />
              <input
                value={q}
                onChange={e => setQ(e.target.value)}
                placeholder="搜索节点..."
                className="w-full h-9 pl-8 pr-3 bg-dark-card border border-dark-border rounded-lg text-xs text-gray-200 placeholder:text-gray-600 focus:outline-none focus:border-primary/50"
              />
            </div>
            {typeFilter && (
              <button onClick={() => setTypeFilter('')} className="px-2 py-1 rounded text-[10px] bg-primary/10 text-primary border border-primary/20">
                {typeFilter} ×
              </button>
            )}
            <button
              onClick={() => setProblemOnly(!problemOnly)}
              className={`px-2 py-1 rounded text-[10px] border transition-colors ${problemOnly ? 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30' : 'bg-dark-bg text-gray-500 border-dark-border hover:text-gray-300'}`}
            >
              ⚠ 仅显示问题
            </button>
          </div>

          {/* Nodes table */}
          <Card>
            <CardHeader>
              <div className="text-sm font-medium text-gray-200">
                节点 <span className="text-gray-500 font-normal">{filteredNodes.length}</span>
              </div>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-500 border-b border-dark-border">
                      <th className="text-left py-2 px-2 font-medium">类型</th>
                      <th className="text-left py-2 px-2 font-medium">名称</th>
                      <th className="text-left py-2 px-2 font-medium">详情</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredNodes.slice(0, 100).map(n => {
                      const issues = problemTags(n);
                      return (
                      <tr key={n.id} className={`border-b border-dark-border/50 hover:bg-dark-hover/50 ${issues.length > 0 ? 'bg-red-900/10' : ''}`}>
                        <td className="py-1.5 px-2">
                          <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] border ${TYPE_COLORS[n.type] || ''}`}>
                            {TYPE_ICONS[n.type] || ''} {n.type}
                          </span>
                          {issues.map((iss, i) => (
                            <span key={i} className={`ml-1 inline-block px-1 py-0.5 rounded text-[10px] border ${iss.cls}`}>
                              {iss.label}
                            </span>
                          ))}
                        </td>
                        <td className={`py-1.5 px-2 font-mono max-w-[200px] truncate ${issues.length > 0 ? 'text-yellow-200' : 'text-gray-200'}`} title={n.label}>
                          {n.label}
                        </td>
                        <td className="py-1.5 px-2 text-gray-500">
                          {n.type === 'agent' && n.agent_type && <span className="mr-2">type={n.agent_type}</span>}
                          {n.type === 'agent' && n.status && <span className="mr-2">status={n.status}</span>}
                          {n.type === 'skill' && n.category && <span className="mr-2">cat={n.category}</span>}
                          {n.type === 'skill' && n.syscalls_used && n.syscalls_used.length > 0 && (
                            <span className="mr-2">syscalls={n.syscalls_used.length}</span>
                          )}
                          {n.type === 'tool' && n.description && <span className="truncate max-w-[300px] inline-block">{n.description}</span>}
                          {n.type === 'mcp_server' && <span>{n.enabled ? 'enabled' : 'disabled'} {n.transport}</span>}
                        </td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
                {filteredNodes.length > 100 && (
                  <div className="text-center text-gray-500 text-xs py-2">仅显示前 100 条，共 {filteredNodes.length} 条</div>
                )}
                {filteredNodes.length === 0 && (
                  <div className="text-center text-gray-500 text-xs py-4">无匹配节点</div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Edges table */}
          <Card>
            <CardHeader>
              <div className="text-sm font-medium text-gray-200">
                边 <span className="text-gray-500 font-normal">{filteredEdges.length}</span>
              </div>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-500 border-b border-dark-border sticky top-0 bg-dark-card">
                      <th className="text-left py-2 px-2 font-medium">From</th>
                      <th className="text-left py-2 px-2 font-medium">关系</th>
                      <th className="text-left py-2 px-2 font-medium">To</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredEdges.slice(0, 200).map((e, i) => {
                      const fromNode = graph?.nodes.find(n => n.id === e.from);
                      const toNode = graph?.nodes.find(n => n.id === e.to);
                      return (
                        <tr key={`${e.from}-${e.to}-${e.relation}-${i}`} className="border-b border-dark-border/50 hover:bg-dark-hover/50">
                          <td className="py-1 px-2">
                            <span className={`inline-block px-1 py-0.5 rounded text-[10px] border ${TYPE_COLORS[fromNode?.type || ''] || ''}`}>
                              {fromNode?.label || e.from}
                            </span>
                          </td>
                          <td className="py-1 px-2">
                            <span className="text-gray-400">{RELATION_LABELS[e.relation] || e.relation}</span>
                          </td>
                          <td className="py-1 px-2">
                            <span className={`inline-block px-1 py-0.5 rounded text-[10px] border ${TYPE_COLORS[toNode?.type || ''] || ''}`}>
                              {toNode?.label || e.to}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {filteredEdges.length > 200 && (
                  <div className="text-center text-gray-500 text-xs py-2">仅显示前 200 条，共 {filteredEdges.length} 条</div>
                )}
                {filteredEdges.length === 0 && (
                  <div className="text-center text-gray-500 text-xs py-4">无匹配边</div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
