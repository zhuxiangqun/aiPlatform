import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, RotateCw, Search } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Modal, Table, toast } from '../../../components/ui';
import { diagnosticsApi } from '../../../services';
import {
  CODE_GRAPH_EGO_NODE_CAP,
  capEgoNodes,
  codeGraphEdgeOpacity,
  codeGraphEmphasisLabel,
  codeGraphLabelOption,
} from '../../../lib/codeGraphViewPolicy';

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

type Panel = 'overview' | 'explore' | 'insights';

const CodeIntel: React.FC = () => {
  const [roots, setRoots] = useState(DEFAULT_ROOTS);
  const [mode, setMode] = useState<'layer' | 'folder' | 'file'>('layer');
  const [depth, setDepth] = useState<number>(2);
  const [limit, setLimit] = useState<number>(CODE_GRAPH_EGO_NODE_CAP);
  const [minDegree, setMinDegree] = useState<number>(1);
  const [focusSearchNeighborhood, setFocusSearchNeighborhood] = useState(true);
  /** Expert: force all labels. Default off — hover/select only. */
  const [showLabels, setShowLabels] = useState(false);
  const [repulsion, setRepulsion] = useState<number>(220);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<any | null>(null);
  const [q, setQ] = useState('');
  const [center, setCenter] = useState('');
  const [panel, setPanel] = useState<Panel>('overview');
  const [view, setView] = useState<'graph' | 'table'>('graph');
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailTitle, setDetailTitle] = useState('');
  const [detailPayload, setDetailPayload] = useState<any>(null);
  const [archSummary, setArchSummary] = useState<any>(null);

  const load = async (opts?: { scanMode?: 'layer' | 'folder' | 'file' }) => {
    const scanMode = opts?.scanMode || mode;
    setLoading(true);
    try {
      const res = await diagnosticsApi.codeIntelScan({
        roots: roots.trim() || undefined,
        mode: scanMode,
        depth,
        limit: scanMode === 'file' ? limit : 0,
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
    // First paint: layer overview only (no file hairball).
    void load({ scanMode: 'layer' });
    fetch('/api/core/knowledge-graph/architecture')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setArchSummary(d))
      .catch(() => setArchSummary(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (mode === 'file') {
      setMinDegree((v) => (v < 2 ? 2 : v));
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

  const pickCenter = (path: string, nextMode: 'layer' | 'folder' | 'file' = 'file') => {
    const p = String(path || '').trim();
    if (!p) return;
    setCenter(p);
    setQ(p);
    setMode(nextMode);
    setPanel('explore');
    setView('graph');
    if (nextMode === 'file') {
      void load({ scanMode: 'file' });
    }
  };

  const filtered = useMemo(() => {
    const qq = (center || q).trim().toLowerCase();
    if (!qq) return nodes;
    return nodes.filter((n) => String(n?.path || '').toLowerCase().includes(qq));
  }, [nodes, q, center]);

  const focusedNodes = useMemo(() => {
    const qq = (center || q).trim().toLowerCase();
    if (!qq || !focusSearchNeighborhood) return nodes;
    const matched = new Set<string>(
      nodes
        .filter((n) => String(n?.path || '').toLowerCase().includes(qq))
        .map((n) => String(n?.path || n?.id || '')),
    );
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
  }, [nodes, q, center, focusSearchNeighborhood, data]);

  const canDrawExploreGraph =
    panel === 'explore' && Boolean((center || q).trim()) && mode !== 'layer';

  const graphData = useMemo(() => {
    if (!canDrawExploreGraph) {
      return { categories: [] as { name: string }[], nodes: [] as any[], links: [] as any[] };
    }
    const base = focusedNodes;
    const list = ((center || q).trim() ? (filtered.length ? filtered : base) : base) as any[];
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

    const qq = (center || q).trim().toLowerCase();
    const matched = new Set<string>(
      qq
        ? list
            .filter((n) => String(n?.path || '').toLowerCase().includes(qq))
            .map((n) => String(n?.path || n?.id || ''))
        : [],
    );
    const nodes1 = list.filter((n) => {
      const id = String(n?.path || n?.id || '');
      const d = deg.get(id) || 0;
      return d >= Math.max(0, minDegree) || matched.has(id);
    });

    const nodesMapped = nodes1
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
          degree: d,
          value: { degree: d, issues: issuesCount, in: Number(n?.in || 0), out: Array.isArray(n?.out) ? n.out.length : 0 },
          category: catIdx >= 0 ? catIdx : 0,
          symbolSize: size,
          itemStyle: { color },
        };
      })
      .filter((x) => x.id);

    const capped = capEgoNodes(nodesMapped, center || q, CODE_GRAPH_EGO_NODE_CAP);
    const idSet2 = new Set<string>(capped.map((n) => n.id));

    const edges0 = ((data?.edges || []) as any[])
      .map((e) => ({
        source: String(e?.from || e?.source || ''),
        target: String(e?.to || e?.target || ''),
        weight: Number(e?.weight || 1),
      }))
      .filter((e) => idSet2.has(e.source) && idSet2.has(e.target));

    return { categories, nodes: capped, links: edges0 };
  }, [canDrawExploreGraph, data, filtered, focusedNodes, minDegree, mode, q, center, roots]);

  const graphOption = useMemo(() => {
    const edgeCount = graphData.links.length;
    const opacity = codeGraphEdgeOpacity(edgeCount);
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
                <div style="opacity:0.75;margin-top:6px">点击：打开 Blast/依赖/风险</div>
              </div>
            `;
          }
          return `${p?.data?.source} → ${p?.data?.target}`;
        },
      },
      legend: graphData.categories.length
        ? [{ data: graphData.categories.map((c: any) => c.name) }]
        : undefined,
      series: [
        {
          type: 'graph',
          layout: 'force',
          roam: true,
          draggable: true,
          data: graphData.nodes,
          links: graphData.links,
          categories: graphData.categories,
          label: codeGraphLabelOption(showLabels),
          labelLayout: { hideOverlap: true },
          force: { repulsion: rep, edgeLength: edgeLen, gravity: mode === 'folder' ? 0.03 : 0.06 },
          lineStyle: { color: `rgba(255,255,255,${opacity})`, width: 1, curveness: 0.18 },
          emphasis: codeGraphEmphasisLabel(),
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

  const layerCards = useMemo(() => {
    if (mode !== 'layer') return nodes.slice(0, 24);
    return nodes.slice(0, 24);
  }, [mode, nodes]);

  const archFlows = useMemo(() => {
    const links = archSummary?.sankey?.links || archSummary?.links || [];
    return (Array.isArray(links) ? links : []).slice(0, 12);
  }, [archSummary]);

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
        width: 360,
        render: (_: any, r: any) => {
          const file = String(r?.path || '');
          return (
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="secondary" onClick={() => pickCenter(file, 'file')}>
                设为中心
              </Button>
              <Button variant="secondary" onClick={() => openDetail(`Dependencies: ${file}`, { file, out: r?.out || [], in: r?.in || 0 })}>
                依赖
              </Button>
              <Button variant="primary" onClick={() => runBlast(file)}>
                Blast
              </Button>
            </div>
          );
        },
      },
    ],
    [issueMap, roots],
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
          <h1 className="text-2xl font-semibold text-gray-200">代码智能</h1>
          <p className="text-sm text-gray-500 mt-1">
            理解优先：先看层/仓总览，再以中心点展开影响面（默认不铺全仓毛球）
          </p>
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
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant={panel === 'overview' ? 'primary' : 'secondary'} onClick={() => { setPanel('overview'); setMode('layer'); void load({ scanMode: 'layer' }); }}>
                总览
              </Button>
              <Button size="sm" variant={panel === 'explore' ? 'primary' : 'secondary'} onClick={() => setPanel('explore')}>
                邻域探索
              </Button>
              <Button size="sm" variant={panel === 'insights' ? 'primary' : 'secondary'} onClick={() => setPanel('insights')}>
                风险洞察
              </Button>
            </div>

            <div className="flex flex-col md:flex-row gap-2 md:items-center md:justify-between">
              <div className="flex flex-col md:flex-row gap-2 flex-1 min-w-0">
                <div className="flex-1 min-w-0">
                  <Input value={roots} onChange={(e: any) => setRoots(String(e.target.value || ''))} placeholder="roots（逗号分隔）" />
                </div>
                <div className="flex-1 min-w-0">
                  <Input
                    value={q}
                    onChange={(e: any) => setQ(String(e.target.value || ''))}
                    placeholder="搜索路径；回车或「展开邻域」设为中心"
                    onKeyDown={(e: any) => {
                      if (e.key === 'Enter' && q.trim()) {
                        pickCenter(q.trim(), 'file');
                      }
                    }}
                  />
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2 justify-end">
                <Button
                  className="shrink-0"
                  variant="secondary"
                  icon={<Search size={14} />}
                  onClick={() => {
                    if (q.trim()) pickCenter(q.trim(), 'file');
                    else void load();
                  }}
                  loading={loading}
                >
                  {q.trim() ? '展开邻域' : '扫描'}
                </Button>
                <Button className="shrink-0" variant="secondary" icon={<RotateCw size={14} />} onClick={() => void load()} loading={loading}>
                  刷新
                </Button>
              </div>
            </div>

            {panel === 'explore' ? (
              <div className="flex flex-wrap items-center gap-2">
                <Button className="shrink-0" size="sm" variant={mode === 'folder' ? 'primary' : 'secondary'} onClick={() => { setMode('folder'); void load({ scanMode: 'folder' }); }}>
                  目录
                </Button>
                <Button className="shrink-0" size="sm" variant={mode === 'file' ? 'primary' : 'secondary'} onClick={() => { setMode('file'); void load({ scanMode: 'file' }); }}>
                  文件
                </Button>
                <Button className="shrink-0" size="sm" variant={view === 'graph' ? 'primary' : 'secondary'} onClick={() => setView('graph')}>
                  图
                </Button>
                <Button className="shrink-0" size="sm" variant={view === 'table' ? 'primary' : 'secondary'} onClick={() => setView('table')}>
                  表
                </Button>
                {center ? (
                  <span className="text-xs text-gray-500">
                    中心: <code className="text-sky-300">{center}</code>
                    <button type="button" className="ml-2 text-gray-500 hover:text-gray-300" onClick={() => { setCenter(''); setQ(''); }}>
                      清除
                    </button>
                  </span>
                ) : null}
                <Button className="shrink-0" size="sm" variant="secondary" onClick={() => setAdvancedOpen((v) => !v)}>
                  {advancedOpen ? '收起高级' : '高级'}
                </Button>
              </div>
            ) : null}

            {advancedOpen && panel === 'explore' ? (
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
                ) : (
                  <div className="flex items-center gap-2">
                    <div className="text-xs text-gray-500">limit</div>
                    <input
                      type="number"
                      value={limit}
                      onChange={(e) => setLimit(Math.max(20, Math.min(200, Number(e.target.value || CODE_GRAPH_EGO_NODE_CAP))))}
                      className="h-9 w-28 px-2 bg-dark-bg border border-dark-border rounded-lg text-sm text-gray-100"
                    />
                  </div>
                )}
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
                  {showLabels ? '标签：全开(专家)' : '标签：仅悬停'}
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
            </div>
            <div className="bg-dark-card border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500">status</div>
              <div className="mt-1">
                <Badge variant={badge(data?.status || 'default')}>{String(data?.status || '-')}</Badge>
              </div>
            </div>
          </div>

          {panel === 'overview' ? (
            <div className="space-y-4">
              <div className="text-xs text-gray-500">
                层/模块卡片（架构聚合）。点一项进入「邻域探索」。全量力导向请到邻域探索并指定中心。
              </div>
              {archFlows.length > 0 ? (
                <div className="bg-dark-card border border-dark-border rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-2">跨层依赖摘要</div>
                  <div className="flex flex-wrap gap-2">
                    {archFlows.map((f: any, i: number) => (
                      <span key={i} className="text-[11px] px-2 py-1 rounded border border-dark-border text-gray-300">
                        {String(f.source)} → {String(f.target)}
                        {f.value != null ? ` · ${f.value}` : ''}
                      </span>
                    ))}
                  </div>
                  <div className="mt-2">
                    <Link to="/system-graph" className="text-xs text-sky-400 hover:underline">
                      打开系统图谱 · 架构全景
                    </Link>
                  </div>
                </div>
              ) : null}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {layerCards.map((n: any) => {
                  const path = String(n?.path || n?.id || '');
                  const deg =
                    (Array.isArray(n?.out) ? n.out.length : Number(n?.out_count || 0)) + Number(n?.in || 0);
                  return (
                    <button
                      key={path}
                      type="button"
                      onClick={() => pickCenter(path, 'file')}
                      className="text-left rounded-lg border border-dark-border bg-dark-card p-3 hover:border-sky-600/50 transition-colors"
                    >
                      <div className="text-sm text-gray-200 font-medium truncate">{path}</div>
                      <div className="text-[11px] text-gray-500 mt-1">
                        deg≈{deg} · issues={Number(n?.issue_count || 0)}
                      </div>
                    </button>
                  );
                })}
              </div>
              {!loading && layerCards.length === 0 ? (
                <div className="text-sm text-gray-500 py-8 text-center">暂无层数据，点「扫描」拉取架构聚合</div>
              ) : null}
            </div>
          ) : null}

          {panel === 'insights' ? (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="bg-dark-card border border-dark-border rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-2">Top Degree</div>
                  {(insights?.top_degree || []).slice(0, 8).map((it: any, idx: number) => (
                    <div key={idx} className="flex items-center justify-between gap-2 text-xs text-gray-300 py-1">
                      <button type="button" className="underline text-left" onClick={() => pickCenter(String(it.path || ''), 'file')}>
                        {String(it.path || '').slice(0, 42)}
                      </button>
                      <span className="text-gray-500">deg={Number(it.degree || 0)}</span>
                    </div>
                  ))}
                </div>
                <div className="bg-dark-card border border-dark-border rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-2">Top Issues</div>
                  {(insights?.top_issues || []).slice(0, 8).map((it: any, idx: number) => (
                    <div key={idx} className="flex items-center justify-between gap-2 text-xs text-gray-300 py-1">
                      <button type="button" className="underline text-left" onClick={() => pickCenter(String(it.path || ''), 'file')}>
                        {String(it.path || '').slice(0, 42)}
                      </button>
                      <span className="text-gray-500">issues={Number(it.issue_count || 0)}</span>
                    </div>
                  ))}
                </div>
                <div className="bg-dark-card border border-dark-border rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-2">Top Blast</div>
                  {(insights?.top_blast || []).slice(0, 8).map((it: any, idx: number) => (
                    <div key={idx} className="flex items-center justify-between gap-2 text-xs text-gray-300 py-1">
                      <button type="button" className="underline text-left" onClick={() => pickCenter(String(it.path || ''), 'file')}>
                        {String(it.path || '').slice(0, 42)}
                      </button>
                      <span className="text-gray-500">blast={Number(it.blast_count || 0)}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="bg-dark-card border border-dark-border rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-2">Top Hubs</div>
                  {(governance?.top_hubs || []).slice(0, 10).map((it: any, idx: number) => (
                    <div key={idx} className="flex items-center justify-between gap-2 text-xs text-gray-300 py-1">
                      <button type="button" className="underline text-left" onClick={() => pickCenter(String(it.path || ''), 'file')}>
                        {String(it.path || '').slice(0, 48)}
                      </button>
                      <span className="text-gray-500">deg={Number(it.degree || 0)}</span>
                    </div>
                  ))}
                </div>
                <div className="bg-dark-card border border-dark-border rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-2">Cycles</div>
                  {(governance?.top_cycles || []).slice(0, 10).map((it: any, idx: number) => (
                    <div key={idx} className="flex items-center justify-between gap-2 text-xs text-gray-300 py-1">
                      <button type="button" className="underline text-left" onClick={() => openDetail(`Cycle #${idx + 1}`, it)}>
                        size={Number(it.size || 0)}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
              {Array.isArray(insights?.recommendations) && insights.recommendations.length ? (
                <div className="bg-dark-card border border-dark-border rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-2">建议</div>
                  <ul className="list-disc ml-5 text-xs text-gray-300 space-y-1">
                    {insights.recommendations.map((x: any, idx: number) => (
                      <li key={idx}>{String(x)}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}

          {panel === 'explore' ? (
            <div className="space-y-3">
              {!canDrawExploreGraph ? (
                <div className="rounded-lg border border-amber-800/40 bg-amber-950/15 px-4 py-10 text-center space-y-2">
                  <div className="text-sm text-amber-100">指定中心后再画邻域图</div>
                  <div className="text-[11px] text-gray-500 max-w-md mx-auto">
                    在上方搜索路径并「展开邻域」，或从「总览 / 风险洞察」点选文件。默认标签仅悬停显示，节点上限 {CODE_GRAPH_EGO_NODE_CAP}。
                  </div>
                </div>
              ) : view === 'graph' ? (
                <>
                  <div className="text-xs text-gray-500">
                    邻域图 · 节点 {graphData.nodes.length}/{CODE_GRAPH_EGO_NODE_CAP} · 边 {graphData.links.length}
                    {showLabels ? ' · 标签全开(专家)' : ' · 标签仅悬停/选中'}
                  </div>
                  <div className="bg-dark-card border border-dark-border rounded-lg overflow-hidden" style={{ height: 560 }}>
                    <React.Suspense fallback={<div className="text-sm text-gray-500 p-4">图谱加载中…</div>}>
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
                                openDetail('目录节点详情', p?.data || {});
                              } else {
                                setCenter(file);
                                openDetail('节点详情', {
                                  file,
                                  out: (nodes.find((x: any) => x?.path === file)?.out || []) as any[],
                                  issues: issueMap.get(file) || [],
                                });
                                void runBlast(file);
                              }
                            }
                          },
                        }}
                      />
                    </React.Suspense>
                  </div>
                </>
              ) : (
                <Table columns={columns as any} data={filtered} rowKey="id" loading={loading} />
              )}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default CodeIntel;
