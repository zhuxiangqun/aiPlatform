import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, Eye, RefreshCw, XCircle } from 'lucide-react';

import { approvalsApi, type ApprovalRequestSummary } from '../../../../services';
import { Badge, Button, Card, CardContent, CardHeader, Modal, Table, toast } from '../../../../components/ui';

const Approvals: React.FC = () => {
  const [items, setItems] = useState<ApprovalRequestSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<any>(null);

  const fetchPending = async () => {
    setLoading(true);
    try {
      const res = await approvalsApi.listPending({ limit: 200, offset: 0 });
      setItems(res.items || []);
    } catch (e: any) {
      toast.error(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPending();
  }, []);

  const openDetail = async (requestId: string) => {
    try {
      const d = await approvalsApi.get(requestId);
      setDetail(d);
      setDetailOpen(true);
    } catch (e: any) {
      toast.error(e?.message || '加载失败');
    }
  };

  const approve = async (requestId: string) => {
    try {
      await approvalsApi.approve(requestId, 'admin', '');
      toast.success('已批准');
      fetchPending();
    } catch (e: any) {
      toast.error(e?.message || '批准失败');
    }
  };

  const reject = async (requestId: string) => {
    try {
      await approvalsApi.reject(requestId, 'admin', '');
      toast.success('已拒绝');
      fetchPending();
    } catch (e: any) {
      toast.error(e?.message || '拒绝失败');
    }
  };

  const columns = useMemo(
    () => [
      {
        title: 'request_id',
        dataIndex: 'request_id',
        key: 'request_id',
        render: (v: string) => <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{String(v || '').slice(0, 12)}</code>,
      },
      {
        title: 'change_id',
        key: 'change_id',
        render: (_: any, r: ApprovalRequestSummary) => {
          const cid = (r as any).change_id;
          if (!cid) return <span className="text-xs text-gray-500">-</span>;
          return (
            <Link to={`/diagnostics/change-control/${encodeURIComponent(String(cid))}`} className="text-xs underline text-gray-300 hover:text-white">
              {String(cid)}
            </Link>
          );
        },
      },
      { title: 'operation', dataIndex: 'operation', key: 'operation' },
      {
        title: 'status',
        dataIndex: 'status',
        key: 'status',
        render: (v: string) => <Badge variant={v === 'pending' ? 'warning' : 'default'}>{v}</Badge>,
      },
      {
        title: 'candidate',
        key: 'candidate',
        render: (_: any, r: ApprovalRequestSummary) => {
          const meta = r.metadata || {};
          const cid = (meta as any).candidate_id;
          return cid ? <code className="text-xs">{String(cid)}</code> : '-';
        },
      },
      {
        title: 'actions',
        key: 'actions',
        render: (_: any, r: ApprovalRequestSummary) => (
          <div className="flex items-center gap-2">
            <Button variant="ghost" icon={<Eye size={14} />} onClick={() => openDetail(r.request_id)}>
              查看
            </Button>
            {(r as any)?.change_id ? (
              <Link to={`/diagnostics/change-control/${encodeURIComponent(String((r as any).change_id))}`}>
                <Button variant="ghost">变更</Button>
              </Link>
            ) : null}
            <Button variant="secondary" icon={<CheckCircle2 size={14} />} onClick={() => approve(r.request_id)}>
              批准
            </Button>
            <Button variant="secondary" icon={<XCircle size={14} />} onClick={() => reject(r.request_id)}>
              拒绝
            </Button>
          </div>
        ),
      },
    ],
    []
  );

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Approvals</h1>
          <div className="text-sm text-gray-500 mt-1">审批中心（复用 core /api/core/approvals API）</div>
        </div>
        <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={fetchPending} loading={loading}>
          刷新
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">Pending Requests</div>
        </CardHeader>
        <CardContent>
          <Table columns={columns as any} data={items} rowKey={(r: any) => String(r.request_id)} />
        </CardContent>
      </Card>

      <Modal
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title={detail?.request_id ? `Approval: ${detail.request_id}` : 'Approval'}
        width={920}
        footer={<Button onClick={() => setDetailOpen(false)}>关闭</Button>}
      >
        <pre className="text-xs text-gray-200 bg-dark-bg border border-dark-border rounded-lg p-3 overflow-auto">
          {JSON.stringify(detail || {}, null, 2)}
        </pre>
      </Modal>
    </div>
  );
};

export default Approvals;
