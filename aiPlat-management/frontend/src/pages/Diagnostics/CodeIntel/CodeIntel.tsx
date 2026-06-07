import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, RotateCw, Search } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Modal, Table, toast } from '../../../components/ui';
import { diagnosticsApi } from '../../../services';

const LazyECharts: any = React.lazy(() => import('echarts-for-react'));

const badge = (v: string): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  const x = String(v || '').toLowerCase();
  if (x === 'ok' || x === 'success') return 'success';
  if (x === 'a' || x === 'b') return 'success';
  if (x === 'c') return 'warning';
  if (x === 'd' || x === 'f') return 'error';
  if (x.includes('warn')) return 'warning';
  if (x.includes('fail') || x.includes('error')) return 'error';
  return 'default';
};

const DEFAULT_ROOTS = 'aiPlat-core,aiPlat-infra,aiPlat-platform,aiPlat-app,aiPlat-management';

const CodeIntel: React.FC = () => {
  const [roots, setRoots] = useState(DEFAULT_ROOTS);
  const [mode, setMode] = useState<'layer' | 'folder' | 'file'>('layer');
  const [depth, setDepth] = useState<number>(2);
  const [limit, setLimit] = useState<number>(350); // file mode only
  const [minDegree, setMinDegree] = useState<number>(1);
  const [focusSearchNeighborhood, setFocusSearchNeighborhood] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [repulsion, setRepulsion] = useState<number>(220);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<any | null>(null);
  const [q, setQ] = useState('');
  const [view, setView] = useState<'graph' | 'table'>('graph');
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailTitle, setDetailTitle] = useState('');
  const [detailPayload, setDetailPayload] = useState<any>(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await diagnosticsApi.codeIntelScan({
        roots: roots.trim() || undefined,
        mode,
        depth,
        limit: mode === 'file' ? limit : 0,
      } as any);
      setData(res);
    } catch (e: any) {
      toast.error('扫描失败', e?.message || 'unknown');
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Provide sane defaults when switching modes
  useEffect(() => {
    if (mode === 'file') {
      setMinDegree((v) => (v === 1 ? 2 : v));
      setRepulsion((v) => (v < 140 ? 160 : v));
    } else {
      setMinDegree((v) => (v < 1 ? 1 : v));
      setRepulsion((v) => (v < 200 ? 220 : v));
    }
  }, [mode]);

  const stats = data?.stats || {};
  const health = data?.health || {};
  const insights = data?.insights || {};
  const governance = data?.governance || {};
  const nodes = (data?.nodes || []) as any[];
  const issues = (data?.issues || []) as any[];

  const issueMap = useMemo(() => {
    const m = new Map<string, any[]>();
    for (const it of issues) {
      const f = String(it?.file || '');
      if (!m.has(f)) m.set(f, []);
      m.get(f)!.push(it);
    }
    return m;
  }, [issues]);

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase();
    if (!qq) return nodes;
    return nodes.filter((n) => String(n?.path || '').toLowerCase().includes(qq));
  }, [nodes, q]);

  const focusedNodes = useMemo(() => {
    // When searching, reduce clutter by showing: matched nodes + 1-hop neighbors.
    const qq = q.trim().toLowerCase();
    if (!qq || !focusSearchNeighborhood) return nodes;
    const matched = new Set<string>(nodes.filter((n) => String(n?.path || '').toLowerCase().includes(qq)).map((n) => String(n?.path || n?.id || '')));
    if (!matched.size) return nodes;
    const nb = new Set<string>([...matched]);
    const edges = (data?.edges || []) as any[];
    for (const e of edges) {
      const a = String(e?.from || e?.source || '');
      const b = String(e?.to || e?.target || '');
      if (!a || !b) continue;
      if (matched.has(a) || matched.has(b)) {
        nb.add(a);
        nb.add(b);
      }
    }
    return nodes.filter((n) => nb.has(String(n?.path || n?.id || '')));
  }, [nodes, q, focusSearchNeighborhood, data]);

  const graphData = useMemo(() => {
    // ECharts graph series expects: nodes[{id,name,value,category,symbolSize,itemStyle}], links[{source,target}]
    const base = focusedNodes;
    const list = (q.trim() ? (filtered.length ? filtered : base) : base) as any[];
    const rootsArr = roots
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean);
    const categories =
      mode === 'layer'
        ? [{ name: 'aiPlat-core' }, { name: 'frontend' }, { name: 'other' }]
        : rootsArr.map((r) => ({ name: r }));

    const deg = new Map<string, number>();
    for (const n of list) {
      const id = String(n?.path || n?.id || '');
      const out = Array.isArray(n?.out) ? n.out.length : Number(n?.out_count || 0);
      const inn = Number(n?.in || 0);
      deg.set(id, out + inn);
    }

    // Apply degree threshold (keep nodes above threshold OR explicitly matched)
    const qq = q.trim().toLowerCase();
    const matched = new Set<string>(
      qq ? list.filter((n) => String(n?.path || '').toLowerCase().includes(qq)).map((n) => String(n?.path || n?.id || '')) : []
    );
    const nodes1 = list.filter((n) => {
      const id = String(n?.path || n?.id || '');
      const d = deg.get(id) || 0;
      return d >= Math.max(0, minDegree) || matched.has(id);
    });
    const idSet2 = new Set<string>(nodes1.map((n) => String(n?.path || n?.id || '')).filter(Boolean));

    const nodes0 = nodes1
      .map((n) => {
        const id = String(n?.path || n?.id || '');
        const issuesCount = Number(n?.issue_count || 0);
        const d = deg.get(id) || 0;
        const size = Math.min(40, 8 + d * 0.6 + issuesCount * 2);
        const catIdx =
          mode === 'layer'
            ? id.startsWith('aiPlat-core:')
              ? 0
              : id.startsWith('frontend:')
                ? 1
                : 2
            : Math.max(0, rootsArr.findIndex((r) => id.startsWith(r + '/')));
        const color = issuesCount > 0 ? '#ff9f43' : d > 12 ? '#4d9fff' : '#22c55e';
        const parts = String(id).split('/').filter(Boolean);
        const short = parts.slice(-1)[0] || id;
        return {
          id,
          name: mode === 'file' ? short : id,
          fullName: id,
          value: { degree: d, issues: issuesCount, in: Number(n?.in || 0), out: Array.isArray(n?.out) ? n.out.length : 0 },
          category: catIdx >= 0 ? catIdx : 0,
          symbolSize: size,
          itemStyle: { color },
        };
      })
      .filter((x) => x.id);

    const edges0 = ((data?.edges || []) as any[])
      .map((e) => ({ source: String(e?.from || e?.source || ''), target: String(e?.to || e?.target || ''), weight: Number(e?.weight || 1) }))
      .filter((e) => idSet2.has(e.source) && idSet2.has(e.target));

    return { categories, nodes: nodes0, links: edges0 };
  }, [data, filtered, focusedNodes, nodes, roots, minDegree, mode, q]);

  const graphOption = useMemo(() => {
    const nodeCount = graphData.nodes.length;
    const show = !!showLabels && (mode !== 'file' || nodeCount <= 120);
    const edgeCount = graphData.links.length;
    const opacity = edgeCount > 1200 ? 0.05 : edgeCount > 600 ? 0.08 : 0.14;
    const rep = Math.max(80, Number(repulsion || (mode === 'folder' ? 240 : 160)));
    const edgeLen = mode !== 'file' ? [70, 220] : [50, 150];
    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        formatter: (p: any) => {
          if (p?.dataType === 'node') {
            const v = p?.data?.value || {};
            return `
              <div style="max-width:520px;white-space:normal;">
                <div style="font-weight:600">${p.data.fullName || p.data.name}</div>
                <div style="opacity:0.85;margin-top:4px">degree=${v.degree ?? '-'} in=${v.in ?? '-'} out=${v.out ?? '-'} issues=${v.issues ?? '-'}</div>
                <div style="opacity:0.75;margin-top:6px">点击节点：打开 Blast/依赖/风险</div>
              </div>
            `;
          }
          return `${p?.data?.source} → ${p?.data?.target}`;
        },
      },
      legend: [{ data: graphData.categories.map((c: any) => c.name) }],
      series: [
        {
          type: 'graph',
          layout: 'force',
          roam: true,
          draggable: true,
          data: graphData.nodes,
          links: graphData.links,
          categories: graphData.categories,
          label: { show: show, position: 'right', formatter: (p: any) => String(p?.data?.name || ''), fontSize: 10, color: 'rgba(255,255,255,0.75)' },
          labelLayout: { hideOverlap: true },
          force: { repulsion: rep, edgeLength: edgeLen, gravity: mode === 'folder' ? 0.03 : 0.06 },
          lineStyle: { color: `rgba(255,255,255,${opacity})`, width: 1, curveness: 0.18 },
          emphasis: { focus: 'adjacency', label: { show: true }, lineStyle: { width: 2, opacity: 0.9 } },
        },
      ],
    };
  }, [graphData, mode, repulsion, showLabels]);

  const openDetail = (title: string, payload: any) => {
    setDetailTitle(title);
    setDetailPayload(payload);
    setDetailOpen(true);
  };

  const runBlast = async (file: string) => {
    try {
      const res = await diagnosticsApi.codeIntelBlast(file, { roots: roots.trim() || undefined });
      openDetail(`Blast Radius: ${file}`, res);
    } catch (e: any) {
      toast.error('Blast 失败', e?.message || 'unknown');
    }
  };

  const columns = useMemo(
    () => [
      {
        key: 'path',
        title: 'file',
        dataIndex: 'path',
        render: (v: any, r: any) => (
          <div className="space-y-1">
            <code className="text-xs text-gray-200">{String(v)}</code>
            <div className="text-xs text-gray-500">
              out={Number(r?.out?.length || 0)} in={Number(r?.in || 0)} issues={Number(r?.issue_count || 0)}
            </div>
          </div>
        ),
      },
      {
        key: 'issues',
        title: 'issues',
        width: 110,
        render: (_: any, r: any) => {
          const c = Number(r?.issue_count || 0);
          if (!c) return <Badge variant="success">0</Badge>;
          return <Badge variant="warning">{c}</Badge>;
        },
      },
      {
        key: 'actions',
        title: 'actions',
        width: 320,
        render: (_: any, r: any) => {
          const file = String(r?.path || '');
          return (
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="secondary" onClick={() => openDetail(`Dependencies: ${file}`, { file, out: r?.out || [], in: r?.in || 0 })}>
                依赖
              </Button>
              <Button variant="secondary" onClick={() => openDetail(`Issues: ${file}`, { file, issues: issueMap.get(file) || [] })}>
                风险
              </Button>
              <Button variant="primary" onClick={() => runBlast(file)}>
                Blast
              </Button>
            </div>
          );
        },
      },
    ],
    [issueMap, roots]
  );

  return (
    <div className="space-y-4">
      <Modal open={detailOpen} onClose={() => setDetailOpen(false)} title={detailTitle} width={960}>
        <pre className="text-xs text-gray-300 overflow-auto max-h-[70vh] bg-dark-card border border-dark-border rounded-lg p-3">
          {JSON.stringify(detailPayload, null, 2)}
        </pre>
      </Modal>

      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Code Intelligence</h1>
          <p className="text-sm text-gray-500 mt-1">代码架构/影响面/风险扫描（CodeFlow 风格的 server-side MVP）</p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/diagnostics">
            <Button variant="secondary" icon={<ArrowLeft size={16} />}>
              返回
            </Button>
          </Link>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="space-y-3">
            {/* row 1: inputs + primary actions */}
            <div className="flex flex-col md:flex-row gap-2 md:items-center md:justify-between">
              <div className="flex flex-col md:flex-row gap-2 flex-1 min-w-0">
                <div className="flex-1 min-w-0">
                  <Input value={roots} onChange={(e: any) => setRoots(String(e.target.value || ''))} placeholder="roots（逗号分隔）" />
                </div>
                <div className="flex-1 min-w-0">
                  <Input value={q} onChange={(e: any) => setQ(String(e.target.value || ''))} placeholder="搜索文件路径（支持子串）" />
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2 justify-end">
                <Button className="shrink-0" variant="secondary" icon={<Search size={14} />} onClick={load} loading={loading}>
                  扫描
                </Button>
                <Button className="shrink-0" variant="secondary" icon={<RotateCw size={14} />} onClick={load} loading={loading}>
                  刷新
                </Button>
              </div>
            </div>

            {/* row 2: mode/view + advanced */}
            <div className="flex flex-wrap items-center gap-2">
              <Button className="shrink-0" size="sm" variant={mode === 'layer' ? 'primary' : 'secondary'} onClick={() => setMode('layer')}>
                架构
              </Button>
              <Button className="shrink-0" size="sm" variant={mode === 'folder' ? 'primary' : 'secondary'} onClick={() => setMode('folder')}>
                目录
              </Button>
              <Button className="shrink-0" size="sm" variant={mode === 'file' ? 'primary' : 'secondary'} onClick={() => setMode('file')}>
                文件
              </Button>
              <Button className="shrink-0" size="sm" variant={view === 'graph' ? 'primary' : 'secondary'} onClick={() => setView('graph')}>
                图
              </Button>
              <Button className="shrink-0" size="sm" variant={view === 'table' ? 'primary' : 'secondary'} onClick={() => setView('table')}>
                表
              </Button>
              <Button className="shrink-0" size="sm" variant="secondary" onClick={() => setAdvancedOpen((v) => !v)}>
                {advancedOpen ? '收起高级' : '高级'}
              </Button>
            </div>

            {advancedOpen ? (
              <div className="flex flex-wrap items-center gap-2 bg-dark-card border border-dark-border rounded-lg p-3">
                {mode === 'folder' ? (
                  <div className="flex items-center gap-2">
                    <div className="text-xs text-gray-500">depth</div>
                    <input
                      type="number"
                      value={depth}
                      onChange={(e) => setDepth(Math.max(1, Math.min(6, Number(e.target.value || 2))))}
                      className="h-9 w-24 px-2 bg-dark-bg border border-dark-border rounded-lg text-sm text-gray-100"
                    />
                  </div>
                ) : mode === 'file' ? (
                  <div className="flex items-center gap-2">
                    <div className="text-xs text-gray-500">limit</div>
                    <input
                      type="number"
                      value={limit}
                      onChange={(e) => setLimit(Math.max(50, Number(e.target.value || 300)))}
                      className="h-9 w-28 px-2 bg-dark-bg border border-dark-border rounded-lg text-sm text-gray-100"
                    />
                  </div>
                ) : null}
                <div className="flex items-center gap-2">
                  <div className="text-xs text-gray-500">minDegree</div>
                  <input
                    type="number"
                    value={minDegree}
                    onChange={(e) => setMinDegree(Math.max(0, Number(e.target.value || 0)))}
                    className="h-9 w-28 px-2 bg-dark-bg border border-dark-border rounded-lg text-sm text-gray-100"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <div className="text-xs text-gray-500">repulsion</div>
                  <input
                    type="number"
                    value={repulsion}
                    onChange={(e) => setRepulsion(Math.max(50, Number(e.target.value || 200)))}
                    className="h-9 w-28 px-2 bg-dark-bg border border-dark-border rounded-lg text-sm text-gray-100"
                  />
                </div>
                <Button className="shrink-0" size="sm" variant="secondary" onClick={() => setShowLabels((v) => !v)}>
                  {showLabels ? '隐藏标签' : '显示标签'}
                </Button>
                <Button className="shrink-0" size="sm" variant="secondary" onClick={() => setFocusSearchNeighborhood((v) => !v)}>
                  {focusSearchNeighborhood ? '搜索看邻居' : '搜索看全部'}
                </Button>
              </div>
            ) : null}
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-4">
            <div className="bg-dark-card border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500">files</div>
              <div className="text-lg text-gray-200 font-semibold">{Number(stats.files || 0)}</div>
            </div>
            <div className="bg-dark-card border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500">edges</div>
              <div className="text-lg text-gray-200 font-semibold">{Number(stats.edges || 0)}</div>
            </div>
            <div className="bg-dark-card border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500">cycles</div>
              <div className="text-lg text-gray-200 font-semibold">{Number(stats.cycles_back_edges || 0)}</div>
            </div>
            <div className="bg-dark-card border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500">issues</div>
              <div className="text-lg text-gray-200 font-semibold">{Number(stats.issues || 0)}</div>
            </div>
            <div className="bg-dark-card border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500">health</div>
              <div className="flex items-center justify-between">
                <div className="text-lg text-gray-200 font-semibold">{Number(health?.score ?? 0)}</div>
                <Badge variant={badge(String(health?.grade || 'default'))}>{String(health?.grade || '-')}</Badge>
              </div>
              <div className="text-xs text-gray-500 mt-1">avg_deg={String(health?.signals?.avg_degree ?? '-')}</div>
            </div>
            <div className="bg-dark-card border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500">status</div>
              <div className="mt-1">
                <Badge variant={badge(data?.status || 'default')}>{String(data?.status || '-')}</Badge>
              </div>
            </div>
          </div>

          {health?.effective ? (
            <div className="bg-dark-card border border-dark-border rounded-lg p-3 mb-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-xs text-gray-500">
                  有效健康度（剔除聚合点后）：score={String(health?.effective?.score ?? '-')} grade={String(health?.effective?.grade ?? '-')} avg_deg=
                  {String(health?.effective?.signals?.avg_degree ?? '-')} max_deg={String(health?.effective?.signals?.max_degree ?? '-')} excluded=
                  {String(health?.effective?.excluded_aggregators ?? 0)}
                </div>
                <Button size="sm" variant="secondary" onClick={() => openDetail('有效健康度详情', health?.effective)}>
                  详情
                </Button>
              </div>
            </div>
          ) : null}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
            <div className="bg-dark-card border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500 mb-2">Top Degree（耦合最高）</div>
              {(insights?.top_degree || []).slice(0, 5).map((it: any, idx: number) => (
                <div key={idx} className="flex items-center justify-between gap-2 text-xs text-gray-300 py-1">
                  <button className="underline text-left" onClick={() => setQ(String(it.path || ''))}>
                    {String(it.path || '').slice(0, 42)}
                  </button>
                  <span className="text-gray-500">deg={Number(it.degree || 0)}</span>
                </div>
              ))}
            </div>
            <div className="bg-dark-card border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500 mb-2">Top Issues（风险最多）</div>
              {(insights?.top_issues || []).slice(0, 5).map((it: any, idx: number) => (
                <div key={idx} className="flex items-center justify-between gap-2 text-xs text-gray-300 py-1">
                  <button className="underline text-left" onClick={() => setQ(String(it.path || ''))}>
                    {String(it.path || '').slice(0, 42)}
                  </button>
                  <span className="text-gray-500">issues={Number(it.issue_count || 0)}</span>
                </div>
              ))}
            </div>
            <div className="bg-dark-card border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500 mb-2">Top Blast（影响面最大）</div>
              {(insights?.top_blast || []).slice(0, 5).map((it: any, idx: number) => (
                <div key={idx} className="flex items-center justify-between gap-2 text-xs text-gray-300 py-1">
                  <button
                    className="underline text-left"
                    onClick={() => {
                      const p = String(it.path || '');
                      if (p) {
                        setQ(p);
                        if (mode === 'file') runBlast(p);
                      }
                    }}
                  >
                    {String(it.path || '').slice(0, 42)}
                  </button>
                  <span className="text-gray-500">blast={Number(it.blast_count || 0)}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
            <div className="bg-dark-card border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500 mb-2">Top Hubs（枢纽节点，含聚合点标记）</div>
              {(governance?.top_hubs || []).slice(0, 8).map((it: any, idx: number) => (
                <div key={idx} className="flex items-center justify-between gap-2 text-xs text-gray-300 py-1">
                  <button
                    className="underline text-left"
                    onClick={() => {
                      const p = String(it.path || '');
                      if (p) {
                        setMode('file');
                        setQ(p);
                        runBlast(p);
                      }
                    }}
                  >
                    {String(it.path || '').slice(0, 48)}
                  </button>
                  <span className="text-gray-500">
                    deg={Number(it.degree || 0)} blast={Number(it.blast_count || 0)} {it.is_aggregator ? '[聚合点]' : ''}
                  </span>
                </div>
              ))}
              <div className="mt-2">
                <Button size="sm" variant="secondary" onClick={() => openDetail('Top Hubs 全量', governance?.top_hubs || [])}>
                  查看更多
                </Button>
              </div>
            </div>
            <div className="bg-dark-card border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500 mb-2">Cycles（循环依赖 SCC）</div>
              {(governance?.top_cycles || []).slice(0, 8).map((it: any, idx: number) => (
                <div key={idx} className="flex items-center justify-between gap-2 text-xs text-gray-300 py-1">
                  <button className="underline text-left" onClick={() => openDetail(`Cycle #${idx + 1}`, it)}>
                    size={Number(it.size || 0)} edges={Number(it.internal_edges || 0)}
                  </button>
                  <span className="text-gray-500">{String((it.nodes || [])[0] || '').slice(0, 24)}</span>
                </div>
              ))}
              <div className="mt-2">
                <Button size="sm" variant="secondary" onClick={() => openDetail('Cycles 全量', governance?.top_cycles || [])}>
                  查看更多
                </Button>
              </div>
            </div>
          </div>

          {Array.isArray(insights?.recommendations) && insights.recommendations.length ? (
            <div className="bg-dark-card border border-dark-border rounded-lg p-3 mb-4">
              <div className="text-xs text-gray-500 mb-2">建议</div>
              <ul className="list-disc ml-5 text-xs text-gray-300 space-y-1">
                {insights.recommendations.map((x: any, idx: number) => (
                  <li key={idx}>{String(x)}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {mode === 'layer' ? (
            <div className="text-xs text-gray-500 mb-3">
              当前为架构聚合模式（推荐）：按业务/技术模块聚合（api/harness/services/governance… + frontend 分层），更适合看整体结构与跨层依赖。
            </div>
          ) : mode === 'folder' ? (
            <div className="text-xs text-gray-500 mb-3">
              当前为目录聚合模式：depth={depth}（路径折叠聚合，适合做“目录级”视角）。想看具体文件依赖请切换到「文件」。
            </div>
          ) : (
            <div className="text-xs text-gray-500 mb-3">
              当前为文件模式：为避免图过密默认 limit={limit}（按风险/耦合排序保留最重要节点）。可调大或切换到「架构/目录」。
            </div>
          )}

          {view === 'graph' ? (
            <div className="bg-dark-card border border-dark-border rounded-lg overflow-hidden" style={{ height: 560 }}>
              <React.Suspense
                fallback={<div className="text-sm text-gray-500 p-4">图谱加载中…</div>}
              >
                <LazyECharts
                  style={{ height: '560px', width: '100%' }}
                  option={graphOption as any}
                  notMerge={true}
                  lazyUpdate={true}
                  onEvents={{
                    click: (p: any) => {
                      if (p?.dataType === 'node') {
                        const file = String(p?.data?.fullName || p?.data?.id || p?.data?.name || '');
                        if (!file) return;
                        if (mode !== 'file') {
                          // folder node: just show summary
                          openDetail('目录节点详情', p?.data || {});
                        } else {
                          openDetail('节点详情', { file, out: (nodes.find((x: any) => x?.path === file)?.out || []) as any[], issues: issueMap.get(file) || [] });
                          runBlast(file);
                        }
                      }
                    },
                  }}
                />
              </React.Suspense>
            </div>
          ) : (
            <>
            <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group mb-3">
              <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
              <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
                <div><span className="text-gray-300">file</span><span className="ml-2 text-gray-600">文件路径 + out（出边数）· in（入边数）· issues</span></div>
                <div><span className="text-gray-300">issues</span><span className="ml-2 text-gray-600">问题数（绿标=0，黄标=有）</span></div>
                <div><span className="text-gray-300">actions</span><span className="ml-2 text-gray-600">查看节点/问题详情 / 名称冲突检测(blast)</span></div>
              </div>
            </details>
            <Table columns={columns as any} data={filtered} rowKey="id" loading={loading} />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default CodeIntel;
