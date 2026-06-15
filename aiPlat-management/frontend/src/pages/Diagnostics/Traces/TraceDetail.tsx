import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Copy, Eye, Share2 } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Modal, Table, Tabs } from '../../../components/ui';
import { diagnosticsApi } from '../../../services';

const toBadgeVariant = (status: string): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  if (status === 'healthy' || status === 'success' || status === 'completed') return 'success';
  if (status === 'degraded' || status === 'warn' || status === 'warning') return 'warning';
  if (status === 'unhealthy' || status === 'error' || status === 'failed') return 'error';
  if (status === 'running') return 'info';
  return 'default';
};

const TraceDetail: React.FC = () => {
  const { traceId } = useParams();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [spanModalOpen, setSpanModalOpen] = useState(false);
  const [selectedSpan, setSelectedSpan] = useState<any>(null);

  useEffect(() => {
    if (!traceId) return;
    let mounted = true;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await diagnosticsApi.getTrace(traceId);
        if (mounted) setData(res);
      } catch (e: any) {
        if (mounted) setError(e?.message || '加载失败');
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [traceId]);

  const trace = data?.trace || data?.result?.trace || data?.traces || data;
  const spans: any[] = Array.isArray(trace?.spans) ? trace.spans : [];
  const attrs = trace?.attributes || {};
  const jobId = attrs?.job_id;
  const jobRunId = attrs?.job_run_id;

  const spanColumns = useMemo(
    () => [
      {
        key: 'span_id',
        title: 'span_id',
        dataIndex: 'span_id',
        render: (val: string) => (
          <div className="flex items-center gap-2">
            <code className="text-xs text-gray-200">{val || '-'}</code>
            {val && (
              <Button variant="ghost" onClick={() => navigator.clipboard.writeText(val)} icon={<Copy size={14} />} />
            )}
          </div>
        ),
      },
      { key: 'name', title: 'name', dataIndex: 'name' },
      {
        key: 'status',
        title: 'status',
        dataIndex: 'status',
        render: (v: string) => <Badge variant={toBadgeVariant(v)}>{v || '-'}</Badge>,
      },
      { key: 'duration_ms', title: 'duration_ms', dataIndex: 'duration_ms' },
      { key: 'parent_span_id', title: 'parent_span_id', dataIndex: 'parent_span_id' },
      {
        key: 'actions',
        title: 'actions',
        render: (_: any, record: any) => (
          <Button
            variant="ghost"
            icon={<Eye size={14} />}
            onClick={() => {
              setSelectedSpan(record);
              setSpanModalOpen(true);
            }}
          >
            查看
          </Button>
        ),
      },
    ],
    []
  );

  return (
    <div className="space-y-4">
      <Link to="/diagnostics" className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 transition-colors">
        <ArrowLeft className="w-3 h-3" />返回诊断中心
      </Link>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Trace</h1>
          <div className="text-sm text-gray-500 mt-1 break-all">{traceId}</div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => traceId && navigator.clipboard.writeText(traceId)}
            icon={<Copy size={16} />}
          >
            复制 ID
          </Button>
          {jobId && (
            <Link
              to={`/core/jobs?job_id=${encodeURIComponent(String(jobId))}${jobRunId ? `&run_id=${encodeURIComponent(String(jobRunId))}` : ''}`}
            >
              <Button variant="secondary">打开 Job</Button>
            </Link>
          )}
          <Link to={`/diagnostics/links?trace_id=${encodeURIComponent(traceId || '')}`}>
            <Button variant="primary" icon={<Share2 size={16} />}>
              打开 Links
            </Button>
          </Link>
        </div>
      </div>

      {error && <div className="text-sm text-error">{error}</div>}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold text-gray-200">概览</div>
            {trace?.status && <Badge variant={toBadgeVariant(trace.status)}>{trace.status}</Badge>}
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-sm text-gray-500">加载中...</div>
          ) : (
            <Tabs
              tabs={[
                {
                  key: 'summary',
                  label: 'Summary',
                  children: (
                    <div className="space-y-4">
                      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                        <div className="p-3 bg-dark-bg rounded-lg">
                          <div className="text-xs text-gray-400 mb-1">trace_id</div>
                          <div className="flex items-center gap-2">
                            <code className="text-xs text-gray-200 break-all">{trace?.trace_id || traceId}</code>
                            <Button
                              variant="ghost"
                              icon={<Copy size={14} />}
                              onClick={() => navigator.clipboard.writeText(String(trace?.trace_id || traceId || ''))}
                            />
                          </div>
                        </div>
                        <div className="p-3 bg-dark-bg rounded-lg">
                          <div className="text-xs text-gray-400 mb-1">name</div>
                          <div className="text-sm font-medium text-gray-100">{trace?.name || '-'}</div>
                        </div>
                        <div className="p-3 bg-dark-bg rounded-lg">
                          <div className="text-xs text-gray-400 mb-1">duration_ms</div>
                          <div className="text-sm font-medium text-gray-100">{trace?.duration_ms ?? '-'}</div>
                        </div>
                        <div className="p-3 bg-dark-bg rounded-lg">
                          <div className="text-xs text-gray-400 mb-1">start_time</div>
                          <div className="text-sm font-medium text-gray-100">{trace?.start_time || '-'}</div>
                        </div>
                        <div className="p-3 bg-dark-bg rounded-lg">
                          <div className="text-xs text-gray-400 mb-1">end_time</div>
                          <div className="text-sm font-medium text-gray-100">{trace?.end_time || '-'}</div>
                        </div>
                        <div className="p-3 bg-dark-bg rounded-lg">
                          <div className="text-xs text-gray-400 mb-1">actions</div>
                          <div>
                            <Link to={`/diagnostics/links?trace_id=${encodeURIComponent(traceId || '')}`}>
                              <Button variant="secondary" icon={<Share2 size={14} />}>
                                打开 Links
                              </Button>
                            </Link>
                          </div>
                        </div>
                        {jobId && (
                          <div className="p-3 bg-dark-bg rounded-lg">
                            <div className="text-xs text-gray-400 mb-1">job</div>
                            <div className="space-y-2">
                              <div className="text-xs text-gray-200 break-all">job_id: {String(jobId)}</div>
                              {jobRunId && <div className="text-xs text-gray-200 break-all">job_run_id: {String(jobRunId)}</div>}
                              <div>
                                <Link
                                  to={`/core/jobs?job_id=${encodeURIComponent(String(jobId))}${jobRunId ? `&run_id=${encodeURIComponent(String(jobRunId))}` : ''}`}
                                >
                                  <Button variant="secondary">打开 Job</Button>
                                </Link>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>

                      <div>
                        <div className="text-sm font-medium text-gray-100 mb-2">attributes</div>
                        <pre className="text-xs text-gray-200 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
                          {JSON.stringify(trace?.attributes || {}, null, 2)}
                        </pre>
                      </div>
                    </div>
                  ),
                },
                {
                  key: 'spans',
                  label: `Spans (${Array.isArray(spans) ? spans.length : 0})`,
                  children: (
                    <>
                    <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group mb-2">
                      <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
                      <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
                        <div><span className="text-gray-300">span_id</span><span className="ml-2 text-gray-600">Span 唯一 ID</span></div>
                        <div><span className="text-gray-300">name</span><span className="ml-2 text-gray-600">Span 名称</span></div>
                        <div><span className="text-gray-300">status</span><span className="ml-2 text-gray-600">healthy/success/degraded/warn/failed/error</span></div>
                        <div><span className="text-gray-300">duration_ms</span><span className="ml-2 text-gray-600">耗时（毫秒）</span></div>
                        <div><span className="text-gray-300">parent_span_id</span><span className="ml-2 text-gray-600">父 Span ID</span></div>
                        <div><span className="text-gray-300">操作</span><span className="ml-2 text-gray-600">查看 Span 详情</span></div>
                      </div>
                    </details>
                    <Table columns={spanColumns as any} data={spans} rowKey={(r: any) => String(r.span_id || r.name || Math.random())} />
                    </>
                  ),
                },
              ]}
            />
          )}
        </CardContent>
      </Card>

      <Modal
        open={spanModalOpen}
        onClose={() => setSpanModalOpen(false)}
        title={selectedSpan?.span_id ? `Span: ${selectedSpan.span_id}` : 'Span 详情'}
        width={900}
        footer={<Button onClick={() => setSpanModalOpen(false)}>关闭</Button>}
      >
        <pre className="text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto">
          {JSON.stringify(selectedSpan || {}, null, 2)}
        </pre>
      </Modal>
    </div>
  );
};

export default TraceDetail;
