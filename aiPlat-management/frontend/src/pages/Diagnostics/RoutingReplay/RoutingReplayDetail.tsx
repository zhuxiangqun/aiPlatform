import React, { Suspense, useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import PageHeader from '../../../components/common/PageHeader';
import { Badge, Button, Card, CardContent, CardHeader, Modal, Select, Table, Tabs } from '../../../components/ui';
import { skillApi, workspaceSkillApi } from '../../../services';
import { toastGateError } from '../../../utils/governanceError';
const LazyECharts: any = React.lazy(() => import('echarts-for-react'));

const fmtTs = (ts?: number | null) => {
  if (!ts) return '-';
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return String(ts);
  }
};

const emaSmooth = (vals: Array<number | null | undefined>, s: number) => {
  const alpha = Math.max(0, Math.min(Number(s || 0), 0.99));
  if (!alpha) return vals.map((v) => (v == null ? null : Number(v)));
  let last: number | null = null;
  return vals.map((v) => {
    if (v == null) return null;
    const x = Number(v);
    if (last == null) {
      last = x;
      return x;
    }
    last = alpha * last + (1 - alpha) * x;
    return last;
  });
};

const uniqueSorted = (arr: number[]) => Array.from(new Set(arr)).sort((a, b) => a - b);

const downloadText = (filename: string, text: string, mime = 'text/plain') => {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};

const toCsv = (rows: any[][], header: string[]) => {
  const esc = (v: any) => {
    const s = v == null ? '' : String(v);
    if (s.includes('"') || s.includes(',') || s.includes('\n')) return `"${s.replace(/"/g, '""')}"`;
    return s;
  };
  return [header.map(esc).join(','), ...rows.map((r) => (r || []).map(esc).join(','))].join('\n');
};

type RoutingPin = {
  id: string;
  title: string;
  kind?: 'scalar' | 'hist';
  tag?: string;
  // legacy compatibility
  metric?: string;
  since_hours: number;
  bucket_minutes: number;
  skill_id?: string;
  compare_profiles: boolean;
  compare_scopes: boolean;
  smoothing: number;
};
const PINS_KEY = 'routing_dashboard_pins_v1';

const addPin = (pin: RoutingPin) => {
  try {
    const s = localStorage.getItem(PINS_KEY);
    const arr = s ? JSON.parse(s) : [];
    const next = Array.isArray(arr) ? arr : [];
    next.unshift(pin);
    localStorage.setItem(PINS_KEY, JSON.stringify(next.slice(0, 50)));
  } catch {
    // ignore
  }
};

const gateReasonPrimary = (s: any) => {
  // Frontend best-effort mapping (until backend enumerates it)
  const strict = String(s?.strict_outcome || '');
  const gate = String(s?.top1_gate_hint || '');
  const err = String(s?.result_error || '');
  if (gate === 'permission_deny') return 'permission';
  if (gate === 'approval_required') return 'approval';
  if (err === 'approval_required') return 'approval';
  if (err === 'policy_denied') return 'policy';
  if (strict === 'no_eligible') return 'threshold';
  if (strict === 'misroute' || strict === 'miss_tool' || strict === 'miss_no_action') return 'routing';
  return 'other';
};

const RoutingReplayDetail: React.FC = () => {
  const { routingDecisionId } = useParams();
  const [sp] = useSearchParams();
  const scope = (sp.get('scope') as any) === 'engine' ? 'engine' : 'workspace';
  const sinceHours = Number(sp.get('since_hours') || 24);

  const api = scope === 'engine' ? skillApi : workspaceSkillApi;
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<any>(null);
  const [metricsLoading, setMetricsLoading] = useState(false);
  // key format: `${scope}:${profile}`
  const [metricsMap, setMetricsMap] = useState<Record<string, any>>({});
  const [bucketMinutes, setBucketMinutes] = useState<number>(60);
  const [compareProfiles, setCompareProfiles] = useState<boolean>(true);
  const [compareScopes, setCompareScopes] = useState<boolean>(false);
  const [smoothing, setSmoothing] = useState<number>(0.0);
  const [graphNode, setGraphNode] = useState<any>(null);

  const rid = String(routingDecisionId || '');

  const summary = useMemo(() => {
    const explain = data?.explain?.args || {};
    const strict = data?.strict?.args || {};
    const decision = data?.decision?.args || {};
    return {
      query_excerpt: explain?.query_excerpt || '',
      selected_kind: decision?.selected_kind || explain?.selected_kind,
      selected_name: decision?.selected_name || explain?.selected_name,
      eligible_top1_skill_id: strict?.eligible_top1_skill_id,
      eligible_top1_score: strict?.eligible_top1_score,
      strict_outcome: strict?.strict_outcome,
      top1_gate_hint: explain?.top1_gate_hint,
      score_gap: explain?.score_gap,
      coding_policy_profile: strict?.coding_policy_profile || explain?.coding_policy_profile,
      threshold: strict?.threshold,
      result_status: explain?.result_status,
      result_error: explain?.result_error,
    };
  }, [data]);

  const gatePrimary = useMemo(() => gateReasonPrimary(summary), [summary]);

  const candidatesTop = useMemo(() => {
    const c = data?.explain?.args?.candidates_top;
    if (Array.isArray(c)) return c;
    const s = data?.candidates?.args?.candidates;
    return Array.isArray(s) ? s : [];
  }, [data]);

  const refresh = async () => {
    setLoading(true);
    try {
      const res: any = await (api as any).routingReplay({ routing_decision_id: rid, since_hours: sinceHours, limit: 5000 });
      setData(res);
    } catch (e: any) {
      toastGateError(e, '加载 routing_replay 失败');
    } finally {
      setLoading(false);
    }
  };

  const refreshMetrics = async (skillId?: string) => {
    setMetricsLoading(true);
    try {
      const currentProf = String(summary.coding_policy_profile || '').trim();
      const profiles = compareProfiles ? ['off', 'karpathy_v1'] : [currentProf && currentProf !== 'all' ? currentProf : 'all'];
      const scopes = compareScopes ? ['workspace', 'engine'] : [scope];
      const reqs: Array<Promise<any>> = [];
      const keys: string[] = [];
      for (const sc of scopes) {
        const api0 = sc === 'engine' ? skillApi : workspaceSkillApi;
        for (const p of profiles) {
          keys.push(`${sc}:${p}`);
          reqs.push(
            (api0 as any).routingMetrics({
              since_hours: sinceHours,
              bucket_minutes: bucketMinutes,
              skill_id: skillId || undefined,
              coding_policy_profile: p === 'all' ? undefined : p,
            })
          );
        }
      }
      const resArr = await Promise.all(reqs);
      const next: Record<string, any> = {};
      keys.forEach((k, idx) => (next[k] = resArr[idx]));
      setMetricsMap(next);
    } catch (e: any) {
      toastGateError(e, '加载 routing_metrics 失败');
    } finally {
      setMetricsLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rid, scope, sinceHours]);

  useEffect(() => {
    if (!data) return;
    const sk = String(summary.selected_name || '');
    if (String(summary.selected_kind || '') === 'skill' && sk) {
      refreshMetrics(sk);
    } else {
      refreshMetrics(undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, bucketMinutes, compareProfiles, compareScopes]);

  const chartData = useMemo(() => {
    const keys = Object.keys(metricsMap || {});
    const strictByProf: Record<string, any[]> = {};
    const gapByProf: Record<string, any[]> = {};
    const axisTs = uniqueSorted(
      keys.flatMap((k) => ((metricsMap?.[k]?.series?.strict_miss_rate as any[]) || []).map((x: any) => Number(x?.[0] || 0)))
    ).filter((x) => x > 0);
    const axisTs2 = uniqueSorted(
      keys.flatMap((k) => ((metricsMap?.[k]?.series?.score_gap_avg as any[]) || []).map((x: any) => Number(x?.[0] || 0)))
    ).filter((x) => x > 0);
    const makeSeries = (arr: any[], axis: number[]) => {
      const m = new Map<number, any>();
      (arr || []).forEach((x: any) => m.set(Number(x?.[0] || 0), x));
      return axis.map((ts) => m.get(ts) ?? null);
    };
    keys.forEach((k) => {
      strictByProf[k] = makeSeries(metricsMap?.[k]?.series?.strict_miss_rate || [], axisTs);
      gapByProf[k] = makeSeries(metricsMap?.[k]?.series?.score_gap_avg || [], axisTs2);
    });
    return { keys, axisTs, axisTs2, strictByProf, gapByProf };
  }, [metricsMap]);

  const linkages = data?.linkages || {};
  const approvalIds = Object.keys(linkages || {});
  const changeIds = approvalIds
    .map((k) => (linkages?.[k] as any)?.change_id)
    .filter((x) => x != null)
    .map((x) => String(x));

  return (
    <div className="p-6 space-y-4">
      <PageHeader title={`Routing Replay Detail`} description={`decision_id=${rid} · scope=${scope}`} />

      <Tabs
        defaultActiveKey="overview"
        tabs={[
          {
            key: 'overview',
            label: 'Overview',
            children: (
              <div className="space-y-4">
                <Card>
                  <CardHeader title="概要" />
                  <CardContent>
                    <div className="text-sm text-gray-300 space-y-2">
                      <div>
                        query: <span className="text-gray-200">{String(summary.query_excerpt || '')}</span>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                        <div>
                          strict_outcome=<code>{String(summary.strict_outcome || '-')}</code>
                        </div>
                        <div>
                          gate_reason_primary=<Badge variant={gatePrimary === 'other' ? 'default' : gatePrimary === 'routing' ? 'info' : gatePrimary === 'threshold' ? 'warning' : 'error'}>{gatePrimary}</Badge>
                        </div>
                        <div>
                          eligible_top1=<code>{String(summary.eligible_top1_skill_id || '-')}</code> score=
                          <code>{summary.eligible_top1_score == null ? '-' : Number(summary.eligible_top1_score).toFixed(1)}</code>
                        </div>
                        <div>
                          selected=<code>{String(summary.selected_kind || '-')}:{String(summary.selected_name || '-')}</code>
                        </div>
                        <div>
                          gap=<code>{summary.score_gap == null ? '-' : Number(summary.score_gap).toFixed(1)}</code> gate=
                          <code>{String(summary.top1_gate_hint || '-')}</code>
                        </div>
                        <div>
                          profile=<code>{String(summary.coding_policy_profile || '-')}</code> threshold=<code>{String(summary.threshold ?? '-')}</code>
                        </div>
                        <div>
                          result=<code>{String(summary.result_status || '-')}</code> err=<code>{String(summary.result_error || '')}</code>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button variant="secondary" onClick={refresh} loading={loading}>
                          刷新
                        </Button>
                        <Link to={`/diagnostics/routing-replay?scope=${scope}&since_hours=${sinceHours}`}>
                          <Button variant="secondary">返回列表</Button>
                        </Link>
                      </div>
                      {approvalIds.length > 0 ? (
                        <div className="text-xs text-gray-500">
                          approval_request_ids: <code>{approvalIds.slice(0, 6).join(',')}</code>{' '}
                          <Link to="/core/approvals">
                            <span className="underline">打开审批中心</span>
                          </Link>
                        </div>
                      ) : null}
                      {changeIds.length > 0 ? (
                        <div className="text-xs text-gray-500">
                          change_ids:{' '}
                          {changeIds.slice(0, 3).map((cid) => (
                            <span key={cid} className="mr-2">
                              <Link to={`/diagnostics/change-control?change_id=${encodeURIComponent(cid)}`}>
                                <span className="underline">{cid}</span>
                              </Link>
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader title="Candidates（Top）" />
                  <CardContent>
                    <Table
                      rowKey={(r: any) => String(r?.skill_id || r?.name || Math.random())}
                      data={candidatesTop}
                      columns={[
                        { title: 'skill_id', dataIndex: 'skill_id', key: 'skill_id', width: 220, render: (_: any, r: any) => String(r?.skill_id || r?.name || '') },
                        { title: 'scope', dataIndex: 'scope', key: 'scope', width: 110 },
                        { title: 'kind', dataIndex: 'skill_kind', key: 'skill_kind', width: 120 },
                        { title: 'score', key: 'score', width: 90, render: (_: any, r: any) => (r?.score == null ? '-' : Number(r.score).toFixed(1)) },
                        { title: 'perm', dataIndex: 'perm', key: 'perm', width: 100 },
                        { title: 'exec_perm', dataIndex: 'exec_perm', key: 'exec_perm', width: 110 },
                        { title: 'overlap', key: 'overlap', render: (_: any, r: any) => (Array.isArray(r?.overlap) ? r.overlap.join(' · ') : '') },
                      ]}
                    />
                  </CardContent>
                </Card>
              </div>
            ),
          },
          {
            key: 'scalars',
            label: 'Scalars',
            children: (
              <div className="space-y-4">
                <Card>
                  <CardHeader title="设置" />
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center">
                      <div className="text-sm text-gray-300">
                        分桶：
                        <div className="mt-1">
                          <Select
                            value={String(bucketMinutes)}
                            onChange={(v: any) => setBucketMinutes(Number(v))}
                            options={[
                              { label: '15 分钟', value: '15' },
                              { label: '60 分钟', value: '60' },
                              { label: '240 分钟', value: '240' },
                            ]}
                          />
                        </div>
                      </div>
                      <div className="text-sm text-gray-300">
                        平滑（EMA）：
                        <div className="mt-1 flex items-center gap-2">
                          <input
                            type="range"
                            min={0}
                            max={0.9}
                            step={0.1}
                            value={smoothing}
                            onChange={(e: any) => setSmoothing(Number(e.target.value))}
                          />
                          <code className="text-xs">{smoothing.toFixed(1)}</code>
                        </div>
                      </div>
                      <label className="text-sm text-gray-300 flex items-center gap-2">
                        <input type="checkbox" checked={compareProfiles} onChange={(e: any) => setCompareProfiles(!!e.target.checked)} />
                        对比 profile（off vs karpathy_v1）
                      </label>
                      <label className="text-sm text-gray-300 flex items-center gap-2">
                        <input type="checkbox" checked={compareScopes} onChange={(e: any) => setCompareScopes(!!e.target.checked)} />
                        对比 scope（workspace vs engine）
                      </label>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          const sid = String(summary.selected_kind || '') === 'skill' ? String(summary.selected_name || '') : undefined;
                          addPin({
                            id: `pin_${Date.now()}`,
                            title: 'strict_miss_rate',
                            kind: 'scalar',
                            tag: 'strict_miss_rate',
                            since_hours: sinceHours,
                            bucket_minutes: bucketMinutes,
                            skill_id: sid,
                            compare_profiles: compareProfiles,
                            compare_scopes: compareScopes,
                            smoothing,
                          });
                        }}
                      >
                        Pin 严格未命中
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          const sid = String(summary.selected_kind || '') === 'skill' ? String(summary.selected_name || '') : undefined;
                          addPin({
                            id: `pin_${Date.now()}`,
                            title: 'score_gap_avg',
                            kind: 'scalar',
                            tag: 'score_gap_avg',
                            since_hours: sinceHours,
                            bucket_minutes: bucketMinutes,
                            skill_id: sid,
                            compare_profiles: compareProfiles,
                            compare_scopes: compareScopes,
                            smoothing,
                          });
                        }}
                      >
                        Pin 分差
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          const payload = { meta: metricsMap?.[Object.keys(metricsMap || {})[0]]?.meta || {}, metricsMap };
                          downloadText(`routing_metrics_${rid}.json`, JSON.stringify(payload, null, 2), 'application/json');
                        }}
                      >
                        导出 JSON
                      </Button>
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader title="strict_miss_rate（按小时分桶）" />
                  <CardContent>
                    {metricsLoading ? (
                      <div className="text-sm text-gray-500">加载中...</div>
                    ) : (
                      <Suspense fallback={<div className="text-sm text-gray-500">加载图表组件...</div>}>
                        <LazyECharts
                          style={{ height: 280 }}
                          option={{
                            backgroundColor: 'transparent',
                            tooltip: { trigger: 'axis' },
                            legend: { textStyle: { color: '#9CA3AF' } },
                            grid: { left: 40, right: 20, top: 30, bottom: 40 },
                            xAxis: {
                              type: 'category',
                              axisLabel: { color: '#9CA3AF' },
                              data: (chartData.axisTs || []).map((x) => fmtTs(x)),
                            },
                            yAxis: { type: 'value', axisLabel: { color: '#9CA3AF' }, min: 0, max: 1 },
                            series: chartData.keys.map((k) => {
                              const raw = (chartData.strictByProf[k] || []).map((x: any) => (x ? x?.[1] : null));
                              const ys = emaSmooth(raw, smoothing);
                              return { name: k, type: 'line', smooth: true, showSymbol: false, data: ys };
                            }),
                          }}
                        />
                      </Suspense>
                    )}
                    <div className="mt-2">
                      <Button
                        variant="secondary"
                        onClick={() => {
                          const header = ['bucket_ts', 'bucket_time', 'series', 'strict_miss_rate', 'eligible_total', 'miss_total'];
                          const rows: any[][] = [];
                          chartData.keys.forEach((k) => {
                            const arr = metricsMap?.[k]?.series?.strict_miss_rate || [];
                            (arr || []).forEach((x: any) => rows.push([x?.[0], fmtTs(x?.[0]), k, x?.[1], x?.[2], x?.[3]]));
                          });
                          downloadText(`strict_miss_rate_${rid}.csv`, toCsv(rows, header), 'text/csv');
                        }}
                      >
                        导出 CSV
                      </Button>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader title="score_gap_avg（按小时分桶）" />
                  <CardContent>
                    {metricsLoading ? (
                      <div className="text-sm text-gray-500">加载中...</div>
                    ) : (
                      <Suspense fallback={<div className="text-sm text-gray-500">加载图表组件...</div>}>
                        <LazyECharts
                          style={{ height: 280 }}
                          option={{
                            backgroundColor: 'transparent',
                            tooltip: { trigger: 'axis' },
                            legend: { textStyle: { color: '#9CA3AF' } },
                            grid: { left: 40, right: 20, top: 30, bottom: 40 },
                            xAxis: {
                              type: 'category',
                              axisLabel: { color: '#9CA3AF' },
                              data: (chartData.axisTs2 || []).map((x) => fmtTs(x)),
                            },
                            yAxis: { type: 'value', axisLabel: { color: '#9CA3AF' } },
                            series: chartData.keys.map((k) => {
                              const raw = (chartData.gapByProf[k] || []).map((x: any) => (x ? x?.[1] : null));
                              const ys = emaSmooth(raw, smoothing);
                              return { name: k, type: 'line', smooth: true, showSymbol: false, data: ys };
                            }),
                          }}
                        />
                      </Suspense>
                    )}
                    <div className="mt-2">
                      <Button
                        variant="secondary"
                        onClick={() => {
                          const header = ['bucket_ts', 'bucket_time', 'series', 'score_gap_avg', 'count'];
                          const rows: any[][] = [];
                          chartData.keys.forEach((k) => {
                            const arr = metricsMap?.[k]?.series?.score_gap_avg || [];
                            (arr || []).forEach((x: any) => rows.push([x?.[0], fmtTs(x?.[0]), k, x?.[1], x?.[2]]));
                          });
                          downloadText(`score_gap_avg_${rid}.csv`, toCsv(rows, header), 'text/csv');
                        }}
                      >
                        导出 CSV
                      </Button>
                      <Button
                        className="ml-2"
                        variant="secondary"
                        onClick={() => {
                          const url = window.location.href;
                          navigator.clipboard?.writeText(url);
                        }}
                      >
                        复制链接
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </div>
            ),
          },
          {
            key: 'hist',
            label: 'Histograms',
            children: (
              <Card>
                <CardHeader title="selected_rank 分布（当前 selected skill）" />
                <CardContent>
                  {metricsLoading ? (
                    <div className="text-sm text-gray-500">加载中...</div>
                  ) : (
                    <Suspense fallback={<div className="text-sm text-gray-500">加载图表组件...</div>}>
                      <LazyECharts
                        style={{ height: 260 }}
                        option={{
                          backgroundColor: 'transparent',
                          tooltip: { trigger: 'axis' },
                          grid: { left: 40, right: 20, top: 20, bottom: 40 },
                          xAxis: {
                            type: 'category',
                            axisLabel: { color: '#9CA3AF' },
                            data: ['0', '1', '2', '3+'],
                          },
                          yAxis: { type: 'value', axisLabel: { color: '#9CA3AF' } },
                          series: [
                            {
                              type: 'bar',
                              data: ['0', '1', '2', '3+'].map((k) => {
                                // pick first available series for hist
                                const firstKey = Object.keys(metricsMap || {})[0];
                                return Number((metricsMap?.[firstKey] as any)?.hists?.selected_rank?.[k] || 0);
                              }),
                            },
                          ],
                        }}
                      />
                    </Suspense>
                  )}
                  <div className="mt-2">
                    <Button
                      variant="secondary"
                      onClick={() => {
                        const firstKey = Object.keys(metricsMap || {})[0];
                        const h = (metricsMap?.[firstKey] as any)?.hists?.selected_rank || {};
                        const rows = ['0', '1', '2', '3+'].map((k) => [k, Number(h?.[k] || 0)]);
                        downloadText(`selected_rank_hist_${rid}.csv`, toCsv(rows, ['bucket', 'count']), 'text/csv');
                      }}
                    >
                      导出 CSV
                    </Button>
                    <Button
                      className="ml-2"
                      variant="secondary"
                      onClick={() => {
                        const sid = String(summary.selected_kind || '') === 'skill' ? String(summary.selected_name || '') : undefined;
                        addPin({
                          id: `pin_${Date.now()}`,
                          title: 'selected_rank',
                          kind: 'hist',
                          tag: 'selected_rank',
                          since_hours: sinceHours,
                          bucket_minutes: bucketMinutes,
                          skill_id: sid,
                          compare_profiles: false,
                          compare_scopes: false,
                          smoothing: 0,
                        });
                      }}
                    >
                      Pin 直方图
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ),
          },
          {
            key: 'graph',
            label: 'Graph',
            children: (
              <Card>
                <CardHeader title="决策拓扑（Routing → Gate → Execution）" />
                <CardContent>
                  <Suspense fallback={<div className="text-sm text-gray-500">加载图表组件...</div>}>
                    <LazyECharts
                      style={{ height: 420 }}
                      onEvents={{
                        click: (p: any) => {
                          if (p?.data?.payload) setGraphNode(p.data.payload);
                        },
                      }}
                      option={(() => {
                        const nodes: any[] = [];
                        const links: any[] = [];
                        const addNode0 = (id: string, label: string, payload: any, category = 0) => {
                          nodes.push({
                            id,
                            name: label,
                            symbolSize: 45,
                            category,
                            payload,
                            label: { show: true, color: '#E5E7EB' },
                          });
                        };
                        const addLink0 = (a: string, b: string, label?: string) => {
                          links.push({ source: a, target: b, label: label ? { show: true, formatter: label, color: '#9CA3AF' } : undefined });
                        };

                        addNode0('intent', 'Intent', { kind: 'intent', query_excerpt: summary.query_excerpt }, 0);
                        addNode0('routing', 'Routing', { kind: 'routing_decision', decision: data?.decision }, 0);
                        addNode0('cands', 'Candidates', { kind: 'candidates', candidates_top: data?.explain?.args?.candidates_top, candidates: data?.candidates }, 0);
                        addNode0('strict', 'StrictEval', { kind: 'strict', strict: data?.strict }, 1);
                        addNode0('explain', 'Explain', { kind: 'explain', explain: data?.explain }, 1);
                        addNode0('gate', `Gate:${gatePrimary}`, { kind: 'gate', gate_reason_primary: gatePrimary, top1_gate_hint: summary.top1_gate_hint, result_error: summary.result_error }, 2);
                        addNode0('exec', 'Execution', { kind: 'execution', skill_syscalls: data?.skill_syscalls, tool_syscalls: data?.tool_syscalls }, 3);
                        addNode0('diff', 'Diff/Changes', { kind: 'changes', changesets: data?.changesets, linkages: data?.linkages }, 3);
                        addNode0('result', `Result:${String(summary.result_status || '-')}`, { kind: 'result', result_status: summary.result_status, result_error: summary.result_error }, 3);

                        addLink0('intent', 'routing');
                        addLink0('routing', 'cands');
                        addLink0('cands', 'strict');
                        addLink0('cands', 'explain');
                        addLink0('strict', 'gate', String(summary.strict_outcome || ''));
                        addLink0('gate', 'exec');
                        addLink0('exec', 'diff');
                        addLink0('diff', 'result');

                        return {
                          backgroundColor: 'transparent',
                          tooltip: { formatter: (p: any) => p?.data?.name || '' },
                          legend: { data: ['flow', 'eval', 'gate', 'exec'], textStyle: { color: '#9CA3AF' } },
                          series: [
                            {
                              type: 'graph',
                              layout: 'force',
                              roam: true,
                              force: { repulsion: 800, edgeLength: 160 },
                              data: nodes,
                              links,
                              categories: [
                                { name: 'flow' },
                                { name: 'eval' },
                                { name: 'gate' },
                                { name: 'exec' },
                              ],
                              lineStyle: { color: '#6B7280' },
                              edgeSymbol: ['none', 'arrow'],
                              edgeSymbolSize: 8,
                            },
                          ],
                        };
                      })()}
                    />
                  </Suspense>

                  <Modal open={!!graphNode} onClose={() => setGraphNode(null)} title="节点详情" width={860}>
                    <pre className="text-xs text-gray-300 whitespace-pre-wrap">{JSON.stringify(graphNode, null, 2)}</pre>
                  </Modal>
                </CardContent>
              </Card>
            ),
          },
          {
            key: 'timeline',
            label: 'Timeline',
            children: (
              <div className="space-y-4">
                <Card>
                  <CardHeader title="时间线（Routing Events）" />
                  <CardContent>
                    <div className="space-y-2">
                      {(data?.routing_events || []).map((ev: any, idx: number) => (
                        <div key={idx} className="border border-dark-border rounded p-2 bg-dark-card">
                          <div className="text-xs text-gray-500">
                            {fmtTs(ev?.created_at)} · <code>{String(ev?.name || '')}</code> · status=<code>{String(ev?.status || '')}</code>
                          </div>
                          <details className="mt-1">
                            <summary className="text-xs text-gray-500 cursor-pointer">args</summary>
                            <pre className="text-xs text-gray-300 whitespace-pre-wrap">{JSON.stringify(ev?.args || {}, null, 2)}</pre>
                          </details>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader title="Syscalls（Skill/Tool）" />
                  <CardContent>
                    <details>
                      <summary className="text-sm text-gray-400 cursor-pointer">skill_syscalls（{(data?.skill_syscalls || []).length}）</summary>
                      <pre className="text-xs text-gray-300 whitespace-pre-wrap">{JSON.stringify(data?.skill_syscalls || [], null, 2)}</pre>
                    </details>
                    <details className="mt-2">
                      <summary className="text-sm text-gray-400 cursor-pointer">tool_syscalls（{(data?.tool_syscalls || []).length}）</summary>
                      <pre className="text-xs text-gray-300 whitespace-pre-wrap">{JSON.stringify(data?.tool_syscalls || [], null, 2)}</pre>
                    </details>
                  </CardContent>
                </Card>
              </div>
            ),
          },
        ]}
      />
    </div>
  );
};

export default RoutingReplayDetail;
