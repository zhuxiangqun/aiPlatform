import React, { useEffect, useMemo, useState } from 'react';
import { RefreshCw, Play } from 'lucide-react';

import { Button, Card, CardContent, CardHeader, Input, Select, Textarea, toast, Badge, Table } from '../../../components/ui';
import { diagnosticsApi } from '../../../services';
import { toastGateError } from '../../../utils/governanceError';

function tryParseJson(s: string): any | null {
  const t = (s || '').trim();
  if (!t) return null;
  try {
    return JSON.parse(t);
  } catch {
    return null;
  }
}

const ContextDiagnostics: React.FC = () => {
  const [loadingCfg, setLoadingCfg] = useState(false);
  const [cfg, setCfg] = useState<any>(null);

  const [sessionId, setSessionId] = useState('');
  const [userId, setUserId] = useState('admin');
  const [repoRoot, setRepoRoot] = useState('');
  const [enableProjectContext, setEnableProjectContext] = useState(true);
  const [enableSessionSearch, setEnableSessionSearch] = useState<'default' | 'true' | 'false'>('default');
  const [messagesJson, setMessagesJson] = useState('');

  const [loading, setLoading] = useState(false);
  const [out, setOut] = useState<any>(null);

  const [metricsLoading, setMetricsLoading] = useState(false);
  const [summary, setSummary] = useState<any>(null);
  const [recent, setRecent] = useState<any[]>([]);
  const [windowHours, setWindowHours] = useState('24');

  const loadCfg = async () => {
    setLoadingCfg(true);
    try {
      const res = await diagnosticsApi.getContextConfig();
      setCfg(res);
    } catch (e: any) {
      setCfg(null);
      toastGateError(e, '加载配置失败');
    } finally {
      setLoadingCfg(false);
    }
  };

  useEffect(() => {
    loadCfg();
    loadMetrics();
  }, []);

  const loadMetrics = async () => {
    setMetricsLoading(true);
    try {
      const wh = Number(windowHours || 24) || 24;
      const [s, r] = await Promise.all([
        diagnosticsApi.getContextMetricsSummary({ window_hours: wh, top_n: 8 }),
        diagnosticsApi.getContextMetricsRecent({ limit: 50, offset: 0 }),
      ]);
      setSummary(s);
      setRecent(Array.isArray(r?.items) ? r.items : Array.isArray(r?.syscalls?.items) ? r.syscalls.items : []);
    } catch (e: any) {
      setSummary(null);
      setRecent([]);
      toastGateError(e, '加载指标失败');
    } finally {
      setMetricsLoading(false);
    }
  };

  const summaryCards = useMemo(() => {
    const t = Number(summary?.total || 0);
    const rates = summary?.rates || {};
    const avgs = summary?.avgs || {};
    return {
      total: t,
      cacheHit: rates?.stable_cache_hit_rate,
      compaction: rates?.compaction_rate,
      ssInjected: rates?.session_search_injected_rate,
      avgTokens: avgs?.budgets_token_estimate ?? avgs?.prompt_estimated_tokens,
    };
  }, [summary]);

  const run = async () => {
    const msgs = tryParseJson(messagesJson);
    if (messagesJson.trim() && !msgs) {
      toast.error('messages JSON 解析失败');
      return;
    }
    if (!sessionId.trim() && !msgs) {
      toast.error('请填写 session_id 或提供 messages JSON');
      return;
    }
    setLoading(true);
    setOut(null);
    try {
      const body: any = {
        session_id: sessionId.trim() || undefined,
        user_id: userId.trim() || 'admin',
        repo_root: repoRoot.trim() || undefined,
        messages: msgs || undefined,
        enable_project_context: !!enableProjectContext,
      };
      if (enableSessionSearch !== 'default') body.enable_session_search = enableSessionSearch === 'true';
      const res = await diagnosticsApi.promptAssemble(body);
      setOut(res);
    } catch (e: any) {
      setOut(null);
      toastGateError(e, '组装失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Context / Prompt 组装诊断</h1>
          <p className="text-sm text-gray-500 mt-1">用于定位稳定层缓存、项目上下文、session search、注入检测等问题</p>
        </div>
        <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={loadCfg} loading={loadingCfg}>
          刷新配置
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold text-gray-200">当前配置</div>
            <Badge variant="info">{cfg?.context_engine || '-'}</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">{JSON.stringify(cfg || {}, null, 2)}</pre>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-semibold text-gray-200">Context 指标（趋势/TopN）</div>
            <div className="flex items-center gap-2">
              <Input className="w-28" value={windowHours} onChange={(e) => setWindowHours(e.target.value)} placeholder="window(h)" />
              <Button variant="secondary" onClick={loadMetrics} loading={metricsLoading}>
                刷新指标
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            <div className="bg-dark-hover border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500">total</div>
              <div className="text-gray-200 font-semibold">{String(summaryCards.total)}</div>
            </div>
            <div className="bg-dark-hover border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500">stable_cache_hit_rate</div>
              <div className="text-gray-200 font-semibold">{summaryCards.cacheHit == null ? '-' : `${(summaryCards.cacheHit * 100).toFixed(1)}%`}</div>
            </div>
            <div className="bg-dark-hover border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500">compaction_rate</div>
              <div className="text-gray-200 font-semibold">{summaryCards.compaction == null ? '-' : `${(summaryCards.compaction * 100).toFixed(1)}%`}</div>
            </div>
            <div className="bg-dark-hover border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500">session_search_injected_rate</div>
              <div className="text-gray-200 font-semibold">{summaryCards.ssInjected == null ? '-' : `${(summaryCards.ssInjected * 100).toFixed(1)}%`}</div>
            </div>
            <div className="bg-dark-hover border border-dark-border rounded-lg p-3">
              <div className="text-xs text-gray-500">avg_tokens_est</div>
              <div className="text-gray-200 font-semibold">{summaryCards.avgTokens == null ? '-' : String(Math.round(Number(summaryCards.avgTokens)))}</div>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-gray-500 mb-1">Top workspace_context_hash</div>
              <pre className="text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto max-h-[200px]">
                {JSON.stringify(summary?.top?.workspace_context_hash || [], null, 2)}
              </pre>
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">Top session_id</div>
              <pre className="text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto max-h-[200px]">
                {JSON.stringify(summary?.top?.session_id || [], null, 2)}
              </pre>
            </div>
          </div>

          <div className="mt-4">
            <div className="text-xs text-gray-500 mb-2">最近 metrics（kind=metric / name=context_assemble）</div>
            <Table
              data={recent}
              loading={metricsLoading}
              rowKey={(r: any) => String(r.id || r.created_at || Math.random())}
              columns={[
                { key: 'created_at', title: 'created_at', dataIndex: 'created_at', width: 170 },
                { key: 'tenant_id', title: 'tenant', dataIndex: 'tenant_id', width: 140 },
                { key: 'session_id', title: 'session', dataIndex: 'session_id', width: 140 },
                { key: 'target_id', title: 'target', dataIndex: 'target_id', width: 220 },
                {
                  key: 'hit',
                  title: 'cache_hit',
                  width: 100,
                  render: (_: any, r: any) => <Badge variant={(r?.result?.metrics?.stable_cache_hit ? 'success' : 'default') as any}>{String(!!r?.result?.metrics?.stable_cache_hit)}</Badge>,
                },
                {
                  key: 'tokens',
                  title: 'tokens_est',
                  width: 120,
                  render: (_: any, r: any) => String(r?.result?.metrics?.budgets_token_estimate ?? r?.result?.metrics?.prompt_estimated_tokens ?? '-'),
                },
              ]}
              emptyText="暂无记录"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">组装请求</div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-gray-500 mb-1">session_id（可选：若提供 messages 则可不填）</div>
              <Input value={sessionId} onChange={(e) => setSessionId(e.target.value)} placeholder="例如 ops_smoke / app_session_id" />
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">user_id</div>
              <Input value={userId} onChange={(e) => setUserId(e.target.value)} />
            </div>
            <div className="md:col-span-2">
              <div className="text-xs text-gray-500 mb-1">repo_root（可选）</div>
              <Input value={repoRoot} onChange={(e) => setRepoRoot(e.target.value)} placeholder="/path/to/repo（用于 project context）" />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 mt-3">
            <label className="text-xs text-gray-400 flex items-center gap-2">
              <input type="checkbox" checked={enableProjectContext} onChange={(e) => setEnableProjectContext(e.target.checked)} />
              启用 project context
            </label>
            <Select
              value={enableSessionSearch}
              onChange={(v) => setEnableSessionSearch(v as any)}
              options={[
                { label: 'session search：默认', value: 'default' },
                { label: 'session search：true', value: 'true' },
                { label: 'session search：false', value: 'false' },
              ]}
              className="w-56"
            />
            <Button variant="primary" icon={<Play size={14} />} loading={loading} onClick={run}>
              组装
            </Button>
          </div>

          <div className="mt-3">
            <div className="text-xs text-gray-500 mb-1">{'messages（可选，JSON 数组：[{"role":"user","content":"..."}]）'}</div>
            <Textarea value={messagesJson} onChange={(e) => setMessagesJson(e.target.value)} rows={6} placeholder='[{"role":"user","content":"hello"}]' />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">结果</div>
        </CardHeader>
        <CardContent>
          {!out ? (
            <div className="text-sm text-gray-500">暂无结果</div>
          ) : (
            <div className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                <div className="bg-dark-hover border border-dark-border rounded-lg p-3">
                  <div className="text-xs text-gray-500">stable_cache_hit</div>
                  <div className="text-gray-200 font-semibold">{String(out?.stable_cache_hit ?? '-')}</div>
                </div>
                <div className="bg-dark-hover border border-dark-border rounded-lg p-3">
                  <div className="text-xs text-gray-500">prompt_version</div>
                  <div className="text-gray-200 font-semibold">{String(out?.prompt_version ?? '-')}</div>
                </div>
                <div className="bg-dark-hover border border-dark-border rounded-lg p-3">
                  <div className="text-xs text-gray-500">message_count</div>
                  <div className="text-gray-200 font-semibold">{String(out?.message_count ?? '-')}</div>
                </div>
              </div>

              <pre className="text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto">{JSON.stringify(out || {}, null, 2)}</pre>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default ContextDiagnostics;
