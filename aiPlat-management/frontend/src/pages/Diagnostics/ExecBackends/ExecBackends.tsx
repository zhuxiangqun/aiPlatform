import React, { useEffect, useState } from 'react';
import { RefreshCw, ExternalLink } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Table } from '../../../components/ui';
import { diagnosticsApi } from '../../../services';
import { toastGateError } from '../../../utils/governanceError';

const ExecBackends: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<any>(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await diagnosticsApi.getExecBackends();
      setData(res);
    } catch (e: any) {
      setData(null);
      toastGateError(e, '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const backends = Array.isArray(data?.backends) ? data.backends : [];
  const current = String(data?.current_backend || '-');
  const nonLocalRequiresApproval = !!data?.non_local_requires_approval;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Exec Backends</h1>
          <p className="text-sm text-gray-500 mt-1">当前执行后端与健康检查（用于排查非本地执行/沙箱/容器问题）</p>
        </div>
        <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={load} loading={loading}>
          刷新
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">current_backend</div>
          </CardHeader>
          <CardContent>
            <Badge variant={current === 'local' ? 'success' : 'warning'}>{current}</Badge>
            <div className="text-xs text-gray-500 mt-2">非 local 时通常需要更严格的审批/门禁。</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">non_local_requires_approval</div>
          </CardHeader>
          <CardContent>
            <Badge variant={nonLocalRequiresApproval ? 'warning' : 'default'}>{String(nonLocalRequiresApproval)}</Badge>
            <div className="text-xs text-gray-500 mt-2">当执行后端不是 local 时，默认建议强制审批。</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">快捷跳转</div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              <a className="inline-flex" href="/core/approvals">
                <Button variant="secondary" icon={<ExternalLink size={14} />}>
                  打开审批中心
                </Button>
              </a>
              <a className="inline-flex" href="/diagnostics/doctor">
                <Button variant="secondary" icon={<ExternalLink size={14} />}>
                  打开 Doctor
                </Button>
              </a>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">backends health</div>
        </CardHeader>
        <CardContent>
          <Table
            data={backends}
            loading={loading}
            rowKey={(r: any) => String(r.driver_id || r.backend || Math.random())}
            columns={[
              { key: 'driver_id', title: 'driver_id', dataIndex: 'driver_id', width: 160 },
              {
                key: 'ok',
                title: 'ok',
                dataIndex: 'ok',
                width: 90,
                render: (v: any) => <Badge variant={v ? 'success' : 'error'}>{String(!!v)}</Badge>,
              },
              { key: 'detail', title: 'detail', render: (_: any, r: any) => <span className="text-xs text-gray-300">{JSON.stringify(r)}</span> },
            ]}
            emptyText="暂无数据"
          />
        </CardContent>
      </Card>
    </div>
  );
};

export default ExecBackends;

