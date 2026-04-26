import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, RotateCw, Search } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Modal, Table, toast } from '../../../components/ui';
import { diagnosticsApi } from '../../../services';

const LazyECharts: any = React.lazy(() => import('echarts-for-react'));

const badge = (v: string): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  const x = String(v || '').toLowerCase();
  if (x === 'ok' || x === 'success') return 'success';
  if (x.includes('warn')) return 'warning';
  if (x.includes('fail') || x.includes('error')) return 'error';
  return 'default';
};

const DEFAULT_ROOTS = 'aiPlat-core,aiPlat-management/frontend';

const CodeIntel: React.FC = () => {
  const [roots, setRoots] = useState(DEFAULT_ROOTS);
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
      const res = await diagnosticsApi.codeIntelScan({ roots: roots.trim() || undefined });
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

  const stats = data?.stats || {};
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

  const graphData = useMemo(() => {
    // ECharts graph series expects: nodes[{id,name,value,category,symbolSize,itemStyle}], links[{source,target}]
    const list = (filtered.length ? filtered : nodes) as any[];
    const idSet = new Set<string>(list.map((n) => String(n?.path || n?.id || '')).filter(Boolean));
    const rootsArr = roots
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean);
    const categories = rootsArr.map((r) => ({ name: r }));

    const deg = new Map<string, number>();
    for (const n of list) {
      const id = String(n?.path || n?.id || '');
      const out = Array.isArray(n?.out) ? n.out.length : 0;
      const inn = Number(n?.in || 0);
      deg.set(id, out + inn);
    }

    const nodes0 = list
      .map((n) => {
        const id = String(n?.path || n?.id || '');
        const issuesCount = Number(n?.issue_count || 0);
        const d = deg.get(id) || 0;
        const size = Math.min(40, 8 + d * 0.6 + issuesCount * 2);
        const catIdx = Math.max(0, rootsArr.findIndex((r) => id.startsWith(r + '/')));
        const color = issuesCount > 0 ? '#ff9f43' : d > 12 ? '#4d9fff' : '#22c55e';
        return {
          id,
          name: id,
          value: { degree: d, issues: issuesCount, in: Number(n?.in || 0), out: Array.isArray(n?.out) ? n.out.length : 0 },
          category: catIdx >= 0 ? catIdx : 0,
          symbolSize: size,
          itemStyle: { color },
        };
      })
      .filter((x) => x.id);

    const edges0 = ((data?.edges || []) as any[])
      .map((e) => ({ source: String(e?.from || ''), target: String(e?.to || '') }))
      .filter((e) => idSet.has(e.source) && idSet.has(e.target));

    return { categories, nodes: nodes0, links: edges0 };
  }, [data, filtered, nodes, roots]);

  const graphOption = useMemo(() => {
    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        formatter: (p: any) => {
          if (p?.dataType === 'node') {
            const v = p?.data?.value || {};
            return `
              <div style="max-width:520px;white-space:normal;">
                <div style="font-weight:600">${p.data.name}</div>
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
          label: { show: false },
          force: { repulsion: 90, edgeLength: [40, 120], gravity: 0.06 },
          lineStyle: { color: 'rgba(255,255,255,0.18)', width: 1, curveness: 0.12 },
          emphasis: { focus: 'adjacency', lineStyle: { width: 2, opacity: 0.9 } },
        },
      ],
    };
  }, [graphData]);

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
          <div className="flex flex-col md:flex-row gap-3 md:items-center md:justify-between">
            <div className="flex gap-2 flex-1">
              <Input value={roots} onChange={(e: any) => setRoots(String(e.target.value || ''))} placeholder="roots（逗号分隔）" />
              <Input value={q} onChange={(e: any) => setQ(String(e.target.value || ''))} placeholder="搜索文件路径" />
            </div>
            <div className="flex items-center gap-2">
              <Button variant={view === 'graph' ? 'primary' : 'secondary'} onClick={() => setView('graph')}>
                拓扑图
              </Button>
              <Button variant={view === 'table' ? 'primary' : 'secondary'} onClick={() => setView('table')}>
                表格
              </Button>
              <Button variant="secondary" icon={<Search size={14} />} onClick={load} loading={loading}>
                扫描
              </Button>
              <Button variant="secondary" icon={<RotateCw size={14} />} onClick={load} loading={loading}>
                刷新
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
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
              <div className="text-xs text-gray-500">status</div>
              <div className="mt-1">
                <Badge variant={badge(data?.status || 'default')}>{String(data?.status || '-')}</Badge>
              </div>
            </div>
          </div>

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
                        const file = String(p?.data?.id || p?.data?.name || '');
                        if (!file) return;
                        // Open a combined panel to act as a "command palette"
                        openDetail('节点操作', { file, hint: '可用：Blast / 依赖 / 风险', out: (nodes.find((x: any) => x?.path === file)?.out || []) as any[] });
                        // Also trigger blast in background (best-effort)
                        runBlast(file);
                      }
                    },
                  }}
                />
              </React.Suspense>
            </div>
          ) : (
            <Table columns={columns as any} data={filtered} rowKey="id" loading={loading} />
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default CodeIntel;
