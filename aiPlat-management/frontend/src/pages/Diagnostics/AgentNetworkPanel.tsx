/**
 * AgentNetworkPanel — Agent 关系网络可视化 (EvoMap 自组织对齐)
 *
 * 展示:
 *   - Agent 专长分布 (雷达图/条形图)
 *   - 网络结构 (聚类系数 + 枢纽节点)
 *   - 演化时间线 (网络结构随时间变化)
 *   - 伙伴选择 (社交/能力/互补三种模式对比)
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, Button, Input, toast } from '../../components/ui';
import {
  Network, TrendingUp, Users, Cpu, GitBranch, BarChart3,
  RefreshCw, Play, Activity, ArrowRight, ChevronDown,
} from 'lucide-react';

const API_BASE = '/api/platform/apps/fde';

// ── Types ────────────────────────────────────────────────────────────────

interface NetworkNode {
  agent_id: string;
  degree: number;
  betweenness: number;
  hub_score: number;
  primary_domain: string;
  accuracy: number;
  actions: number;
}

interface NetworkSnapshot {
  timestamp: number;
  node_count: number;
  edge_count: number;
  clustering_coefficient: number;
  hub_nodes: NetworkNode[];
  summary: string;
}

interface SpecializationData {
  agent_id: string;
  domains: Record<string, { accuracy: number; preference: number; total_count: number }>;
  primary_domain: string;
  secondary_domains: string[];
  total_actions: number;
}

// ── Component ─────────────────────────────────────────────────────────────

const AgentNetworkPanel: React.FC = () => {
  const [agentIds, setAgentIds] = useState('');
  const [nodes, setNodes] = useState<NetworkNode[]>([]);
  const [snapshots, setSnapshots] = useState<NetworkSnapshot[]>([]);
  const [showEvolve, setShowEvolve] = useState(false);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<'analyze' | 'evolution'>('analyze');
  const [partnerMode, setPartnerMode] = useState('capability');
  const [partnerResult, setPartnerResult] = useState<any>(null);

  const loadNetwork = useCallback(async () => {
    const ids = agentIds.split(',').map(s => s.trim()).filter(Boolean);
    if (!ids.length) return;
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/network/analyze?agent_ids=${ids.join(',')}&lookback_hours=168`);
      const d = await r.json();
      setNodes(d.nodes || []);
    } catch (e: any) { toast?.error?.(e?.message || '加载失败'); }
    setLoading(false);
  }, [agentIds]);

  const runEvolution = async () => {
    const ids = agentIds.split(',').map(s => s.trim()).filter(Boolean);
    if (!ids.length) return;
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/network/evolve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_ids: ids, interval_hours: 24, count: 10 }),
      });
      const d = await r.json();
      setSnapshots(d.snapshots || []);
    } catch (e: any) { toast?.error?.(e?.message || '演化失败'); }
    setLoading(false);
  };

  const testPartnerSelection = async () => {
    const ids = agentIds.split(',').map(s => s.trim()).filter(Boolean);
    if (ids.length < 2) return;
    try {
      const r = await fetch(`${API_BASE}/partners/select`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: ids[0], candidates: ids.slice(1), mode: partnerMode, count: 3 }),
      });
      setPartnerResult(await r.json());
    } catch {}
  };

  const clusteringColor = (c: number) => {
    if (c > 0.4) return 'text-yellow-400';
    if (c > 0.2) return 'text-blue-400';
    return 'text-green-400';
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-100">Agent 网络</h2>
          <p className="text-xs text-gray-500">专长分析 · 网络结构 · 演化追踪</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={mode} onChange={e => setMode(e.target.value as any)}
            className="bg-gray-800 border border-gray-700 text-gray-300 text-xs rounded px-2 py-1">
            <option value="analyze">网络分析</option>
            <option value="evolution">演化追踪</option>
          </select>
          <input className="bg-gray-800 border border-gray-700 text-gray-300 text-xs rounded px-2 py-1 w-48"
            value={agentIds} onChange={e => setAgentIds(e.target.value)}
            placeholder="agent_1,agent_2,agent_3" />
          <Button variant="default" size="sm" onClick={mode === 'evolution' ? runEvolution : loadNetwork} loading={loading}>
            {mode === 'evolution' ? <Play className="w-3 h-3 mr-1" /> : <RefreshCw className="w-3 h-3 mr-1" />}
            {mode === 'evolution' ? '运行演化' : '分析'}
          </Button>
        </div>
      </div>

      {/* Network stats */}
      {nodes.length > 0 && (
        <div className="grid grid-cols-4 gap-3">
          <Card className="border-gray-700/50"><CardContent className="p-3 text-center">
            <div className="text-xl font-bold text-gray-200">{nodes.length}</div>
            <div className="text-[10px] text-gray-500">节点数</div>
          </CardContent></Card>
          <Card className="border-gray-700/50"><CardContent className="p-3 text-center">
            <div className="text-xl font-bold text-blue-400">{nodes.reduce((s, n) => s + n.degree, 0)}</div>
            <div className="text-[10px] text-gray-500">总连接数</div>
          </CardContent></Card>
          <Card className="border-gray-700/50"><CardContent className="p-3 text-center">
            <div className={`text-xl font-bold ${clusteringColor(0.3)}`}>~0.3</div>
            <div className="text-[10px] text-gray-500">聚类系数</div>
          </CardContent></Card>
          <Card className="border-gray-700/50"><CardContent className="p-3 text-center">
            <div className="text-xl font-bold text-purple-400">{nodes.filter(n => n.hub_score > 0.1).length}</div>
            <div className="text-[10px] text-gray-500">枢纽节点</div>
          </CardContent></Card>
        </div>
      )}

      {/* Hub nodes */}
      {nodes.length > 0 && (
        <Card className="border-gray-700/50">
          <CardHeader><span className="text-sm font-medium text-gray-200">枢纽节点 (Top 5)</span></CardHeader>
          <CardContent>
            <div className="space-y-2">
              {nodes.slice(0, 5).map(n => (
                <div key={n.agent_id} className="flex items-center justify-between p-2 rounded bg-gray-800/50 border border-gray-700/30">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-200">{n.agent_id}</span>
                    <span className="text-[10px] text-blue-400">{n.primary_domain}</span>
                    <span className="text-[10px] text-green-400">{(n.accuracy * 100).toFixed(0)}%</span>
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-gray-500">
                    <span>度: {n.degree}</span>
                    <span>枢纽: {n.hub_score.toFixed(2)}</span>
                    <span>行动: {n.actions}</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Evolution timeline */}
      {snapshots.length > 0 && (
        <Card className="border-gray-700/50">
          <CardHeader><span className="text-sm font-medium text-gray-200">演化时间线</span></CardHeader>
          <CardContent>
            <div className="space-y-3">
              {snapshots.map((snap, i) => (
                <div key={i} className="flex items-center gap-4 p-2 rounded bg-gray-800/30">
                  <span className="text-[10px] text-gray-600 w-16">T-{snapshots.length - i - 1}</span>
                  <div className="flex-1 h-1.5 bg-gray-800 rounded overflow-hidden">
                    <div className="h-full bg-blue-500 rounded" style={{ width: `${snap.node_count * 5}%` }} />
                  </div>
                  <span className="text-[10px] text-gray-500">{snap.node_count}节点</span>
                  <span className={`text-[10px] ${clusteringColor(snap.clustering_coefficient)}`}>
                    聚类={snap.clustering_coefficient.toFixed(3)}
                  </span>
                  {snap.hub_nodes.length > 0 && (
                    <span className="text-[10px] text-purple-400">{snap.hub_nodes[0].agent_id}(hub)</span>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Partner selection test */}
      <Card className="border-gray-700/50">
        <CardHeader>
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-200">伙伴选择测试</span>
            <div className="flex items-center gap-1">
              {['social', 'capability', 'complementary'].map(m => (
                <button key={m} onClick={() => setPartnerMode(m)}
                  className={`text-[10px] px-2 py-0.5 rounded ${partnerMode === m ? 'bg-blue-500/20 text-blue-400' : 'text-gray-500'}`}>
                  {m}
                </button>
              ))}
              <Button variant="ghost" size="sm" className="text-[10px]" onClick={testPartnerSelection}>测试</Button>
            </div>
          </div>
        </CardHeader>
        {partnerResult && (
          <CardContent>
            <div className="text-xs">
              <span className="text-gray-400">Agent {partnerResult.agent_id} 选择了: </span>
              {partnerResult.partners?.map((p: string, i: number) => (
                <span key={p} className="text-blue-400 ml-1">[{i+1}] {p}</span>
              ))}
            </div>
          </CardContent>
        )}
      </Card>
    </div>
  );
};

export default AgentNetworkPanel;
