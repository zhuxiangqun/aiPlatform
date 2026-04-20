import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Copy, ExternalLink, Link2, RotateCw } from 'lucide-react';
import { Button, Card, CardContent, CardHeader, Input, Select, Table, toast, Badge } from '../../../components/ui';
import { diagnosticsApi } from '../../../services';
import { toastGateError } from '../../../utils/governanceError';

const fmtTs = (v: any) => {
  const n = Number(v);
  if (!Number.isFinite(n) || n <= 0) return '-';
  const d = new Date(n * 1000);
  return d.toISOString().replace('T', ' ').slice(0, 19);
};

const badge = (status: string): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  const s = String(status || '').toLowerCase();
  if (s === 'success' || s === 'completed' || s === 'ok' || s === 'enabled' || s === 'published') return 'success';
  if (s === 'approval_required') return 'warning';
  if (s === 'blocked' || s === 'failed' || s === 'error') return 'error';
  return 'default';
};

const ChangeControl: React.FC = () => {
  const { changeId } = useParams();
  const navigate = useNavigate();

  // list
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [limit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState('');
  const [state, setState] = useState<string>('');

  // detail
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<any | null>(null);

  const loadList = async () => {
    setLoading(true);
    try {
      const res = await diagnosticsApi.listChangeControls({ limit, offset });
      const data = res?.changes || {};
      const rows = Array.isArray(data.items) ? data.items : [];
      const filtered0 = q.trim()
        ? rows.filter((r: any) => String(r?.change_id || r?.target_id || '').includes(q.trim()))
        : rows;
      const filtered = state
        ? filtered0.filter((r: any) => String(r?.summary?.derived_state || '').toLowerCase() === String(state).toLowerCase())
        : filtered0;
      setItems(filtered);
      setTotal(Number(data.total || 0));
    } catch (e: any) {
      toastGateError(e, '加载失败');
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  const loadDetail = async (cid: string) => {
    setDetailLoading(true);
    try {
      const res = await diagnosticsApi.getChangeControl(cid, { limit: 200, offset: 0 });
      setDetail(res?.change || null);
    } catch (e: any) {
      toastGateError(e, '加载失败');
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const downloadJson = (filename: string, obj: any) => {
    try {
      const blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      toastGateError(e, '导出失败');
    }
  };

  const autosmoke = async (cid: string) => {
    setDetailLoading(true);
    try {
      const res = await diagnosticsApi.autosmokeChangeControl(cid);
      toast.success('已触发 autosmoke');
      // reload detail to capture new changeset event
      await loadDetail(cid);
      return res;
    } catch (e: any) {
      toastGateError(e, '触发失败');
      return null;
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    if (!changeId) loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [changeId, limit, offset]);

  useEffect(() => {
    if (changeId) loadDetail(changeId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [changeId]);

  const listColumns = useMemo(
    () => [
      { key: 'change_id', title: 'change_id', dataIndex: 'change_id', width: 190 },
      {
        key: 'name',
        title: 'operation',
        width: 220,
        render: (_: any, r: any) => <code className="text-xs">{String(r?.name || '-')}</code>,
      },
      {
        key: 'status',
        title: 'status',
        width: 140,
        render: (_: any, r: any) => {
          const st = String(r?.summary?.derived_state || r?.status || '-');
          return <Badge variant={badge(st)}>{st}</Badge>;
        },
      },
      {
        key: 'updated_at',
        title: 'updated_at',
        width: 170,
        render: (_: any, r: any) => <span className="text-xs text-gray-300">{fmtTs(r?.created_at)}</span>,
      },
      {
        key: 'approval',
        title: 'approval',
        width: 140,
        render: (_: any, r: any) => (
          <span className="text-xs text-gray-300">{r?.approval_request_id ? String(r.approval_request_id).slice(0, 12) : '-'}</span>
        ),
      },
      {
        key: 'targets',
        title: 'targets',
        render: (_: any, r: any) => {
          const ts = r?.args?.targets;
          if (!Array.isArray(ts) || ts.length === 0) return <span className="text-xs text-gray-500">-</span>;
          return (
            <div className="text-xs text-gray-300">
              {ts.slice(0, 3).map((t: any, idx: number) => (
                <span key={idx} className="mr-2">
                  {String(t?.type || '?')}:{String(t?.id || '').slice(0, 10)}
                </span>
              ))}
              {ts.length > 3 ? <span className="text-gray-500">+{ts.length - 3}</span> : null}
            </div>
          );
        },
      },
      {
        key: 'actions',
        title: 'actions',
        width: 220,
        render: (_: any, r: any) => (
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={() => navigate(`/diagnostics/change-control/${encodeURIComponent(String(r.change_id))}`)}>
              查看
            </Button>
            {r?.links?.syscalls_ui ? (
              <a className="text-xs underline text-gray-300 hover:text-white" href={String(r.links.syscalls_ui)} target="_blank" rel="noreferrer">
                Syscalls <ExternalLink size={12} className="inline ml-1" />
              </a>
            ) : null}
          </div>
        ),
      },
    ],
    [navigate],
  );

  const eventColumns = useMemo(
    () => [
      { key: 'created_at', title: 'time', width: 180, render: (_: any, r: any) => <span className="text-xs">{fmtTs(r?.created_at)}</span> },
      { key: 'name', title: 'name', width: 220, render: (_: any, r: any) => <code className="text-xs">{String(r?.name || '-')}</code> },
      { key: 'status', title: 'status', width: 140, render: (_: any, r: any) => <Badge variant={badge(String(r?.status || ''))}>{String(r?.status || '-')}</Badge> },
      { key: 'approval', title: 'approval', width: 140, render: (_: any, r: any) => <span className="text-xs">{r?.approval_request_id ? String(r.approval_request_id).slice(0, 12) : '-'}</span> },
      {
        key: 'payload',
        title: 'payload',
        render: (_: any, r: any) => (
          <pre className="text-xs text-gray-300 bg-dark-card border border-dark-border rounded-lg p-2 overflow-auto max-h-[220px]">
            {JSON.stringify({ args: r?.args, result: r?.result, error: r?.error, error_code: r?.error_code }, null, 2)}
          </pre>
        ),
      },
    ],
    [],
  );

  if (changeId) {
    const latest = detail?.latest || null;
    const ev = detail?.events?.items || [];
    const summary = detail?.summary || null;
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => navigate('/diagnostics/change-control')}>
                <ArrowLeft size={14} className="mr-1" />
                返回列表
              </Button>
              <h1 className="text-2xl font-semibold text-gray-200">Change Control</h1>
            </div>
            <div className="text-sm text-gray-500">change_id：{changeId}</div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={() => loadDetail(changeId)} loading={detailLoading} icon={<RotateCw size={14} />}>
              刷新
            </Button>
            <Button variant="primary" onClick={() => autosmoke(changeId)} loading={detailLoading}>
              触发 autosmoke
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                try {
                  navigator.clipboard.writeText(String(changeId));
                  toast.success('已复制 change_id');
                } catch {
                  // ignore
                }
              }}
            >
              <Copy size={14} className="mr-1" />
              复制 change_id
            </Button>
            <Button
              variant="secondary"
              onClick={async () => {
                try {
                  const resp = await diagnosticsApi.exportChangeControlEvidence(changeId, { format: 'zip', limit: 500 });
                  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                  const blob = await resp.blob();
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `change_${changeId}_evidence.zip`;
                  a.click();
                  URL.revokeObjectURL(url);
                  toast.success('已导出证据包（zip）');
                } catch (e: any) {
                  toast.error('导出失败', String(e?.message || e));
                }
              }}
            >
              导出证据包（zip）
            </Button>
            <Button variant="secondary" onClick={() => downloadJson(`change_${changeId}.json`, detail)}>
              导出当前页 JSON
            </Button>
            {detail?.links?.syscalls_ui ? (
              <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.syscalls_ui)} target="_blank" rel="noreferrer">
                打开 Syscalls <ExternalLink size={14} className="inline ml-1" />
              </a>
            ) : null}
            {latest?.approval_request_id ? (
              <Link className="text-sm underline text-gray-300 hover:text-white" to="/core/approvals">
                Approvals
              </Link>
            ) : null}
            {detail?.links?.audit_ui ? (
              <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.audit_ui)} target="_blank" rel="noreferrer">
                Audit <ExternalLink size={14} className="inline ml-1" />
              </a>
            ) : null}
            {detail?.links?.runs_ui ? (
              <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.runs_ui)} target="_blank" rel="noreferrer">
                Runs <ExternalLink size={14} className="inline ml-1" />
              </a>
            ) : null}
            {detail?.links?.traces_ui ? (
              <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.traces_ui)} target="_blank" rel="noreferrer">
                Traces <ExternalLink size={14} className="inline ml-1" />
              </a>
            ) : null}
          </div>
        </div>

        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">联动跳转</div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="secondary"
                icon={<Link2 size={14} />}
                onClick={() => {
                  const url = `/diagnostics/links?change_id=${encodeURIComponent(changeId)}`;
                  navigate(url);
                }}
              >
                打开 Links
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  const links = detail?.links || {};
                  const payload = { change_id: changeId, links };
                  navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
                  toast.success('已复制 links JSON');
                }}
              >
                复制 links
              </Button>
              {detail?.links?.syscalls_ui ? (
                <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.syscalls_ui)} target="_blank" rel="noreferrer">
                  Syscalls <ExternalLink size={14} className="inline ml-1" />
                </a>
              ) : null}
              {detail?.links?.audit_ui ? (
                <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.audit_ui)} target="_blank" rel="noreferrer">
                  Audit <ExternalLink size={14} className="inline ml-1" />
                </a>
              ) : null}
              {detail?.links?.approvals_ui ? (
                <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.approvals_ui)} target="_blank" rel="noreferrer">
                  Approvals <ExternalLink size={14} className="inline ml-1" />
                </a>
              ) : null}
              {detail?.links?.runs_ui ? (
                <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.runs_ui)} target="_blank" rel="noreferrer">
                  Runs <ExternalLink size={14} className="inline ml-1" />
                </a>
              ) : null}
              {detail?.links?.traces_ui ? (
                <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.traces_ui)} target="_blank" rel="noreferrer">
                  Traces <ExternalLink size={14} className="inline ml-1" />
                </a>
              ) : null}
              {detail?.links?.links_ui ? (
                <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.links_ui)} target="_blank" rel="noreferrer">
                  Links <ExternalLink size={14} className="inline ml-1" />
                </a>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">summary</div>
              {summary?.derived_state ? <Badge variant={badge(String(summary.derived_state))}>{String(summary.derived_state)}</Badge> : null}
            </div>
          </CardHeader>
          <CardContent>
            {summary ? (
              <pre className="text-xs text-gray-300 overflow-auto max-h-[220px] bg-dark-card border border-dark-border rounded-lg p-3">
                {JSON.stringify(summary, null, 2)}
              </pre>
            ) : (
              <div className="text-sm text-gray-500">暂无 summary</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">latest</div>
          </CardHeader>
          <CardContent>
            {latest ? (
              <pre className="text-xs text-gray-300 overflow-auto max-h-[320px] bg-dark-card border border-dark-border rounded-lg p-3">
                {JSON.stringify(latest, null, 2)}
              </pre>
            ) : (
              <div className="text-sm text-gray-500">暂无记录</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">events</div>
          </CardHeader>
          <CardContent>
            <Table rowKey={(r: any) => String(r.id)} loading={detailLoading} data={ev} columns={eventColumns as any} emptyText="暂无 events" />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Change Control</h1>
          <p className="text-sm text-gray-500 mt-1">统一的变更控制台（change_id → Syscalls/Audit/Approvals）</p>
        </div>
        <Button variant="secondary" onClick={loadList} loading={loading} icon={<RotateCw size={14} />}>
          刷新
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-gray-200">列表</div>
            <div className="flex items-center gap-2">
              <Input value={q} onChange={(e: any) => setQ(e.target.value)} placeholder="按 change_id 过滤（本地过滤）" />
              <Select
                value={state}
                onChange={(v) => setState(String(v || ''))}
                options={[
                  { value: '', label: '全部状态' },
                  { value: 'blocked', label: 'blocked' },
                  { value: 'approval_required', label: 'approval_required' },
                  { value: 'success', label: 'success' },
                  { value: 'failed', label: 'failed' },
                  { value: 'unknown', label: 'unknown' },
                ]}
                placeholder="状态筛选"
              />
              <Button
                variant="secondary"
                onClick={() => {
                  setOffset(0);
                  loadList();
                }}
              >
                应用
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <Table
            rowKey={(r: any) => String(r.change_id || r.target_id)}
            loading={loading}
            data={items}
            columns={listColumns as any}
            emptyText="暂无变更记录"
          />
          <div className="flex items-center justify-between mt-3 text-xs text-gray-500">
            <div>
              total：{total}，limit：{limit}，offset：{offset}
            </div>
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => setOffset(Math.max(0, offset - limit))} disabled={offset <= 0}>
                上一页
              </Button>
              <Button variant="secondary" onClick={() => setOffset(offset + limit)} disabled={offset + limit >= total}>
                下一页
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default ChangeControl;
