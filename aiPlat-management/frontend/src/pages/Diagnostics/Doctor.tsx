import { useEffect, useState } from 'react';
import { diagnosticsApi } from '../../services';
import { Card, CardContent, CardHeader, Badge } from '../../components/ui';

const Doctor: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      setError(null);
      try {
        const res = await diagnosticsApi.getDoctor();
        if (mounted) setData(res);
      } catch (e: any) {
        if (mounted) setError(e?.message || '加载失败');
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-200">Doctor</h1>
        <p className="text-sm text-gray-500 mt-1">一键聚合诊断：健康检查、adapter 配置与 autosmoke 建议</p>
      </div>

      {error && <div className="text-sm text-error bg-error-light border border-dark-border rounded-lg p-3">{error}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">Health</div>
              <Badge variant="info">/diagnostics/doctor</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
              {JSON.stringify(data?.health || {}, null, 2)}
            </pre>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">Adapters</div>
              <Badge variant={(data?.adapters?.total || 0) > 0 ? 'success' : 'warning'}>{data?.adapters?.total ?? 0}</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
              {JSON.stringify(data?.adapters || {}, null, 2)}
            </pre>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">Recommendations</div>
              <Badge variant="default">{(data?.recommendations || []).length}</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
              {JSON.stringify(data?.recommendations || [], null, 2)}
            </pre>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Doctor;

