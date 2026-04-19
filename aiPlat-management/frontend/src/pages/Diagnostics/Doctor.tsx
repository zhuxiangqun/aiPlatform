import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { diagnosticsApi } from '../../services';
import { Card, CardContent, CardHeader, Badge } from '../../components/ui';
import { ActionableFixes } from '../../components/common/ActionableFixes';

const Doctor: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [runningSmoke, setRunningSmoke] = useState(false);

  const refresh = async () => {
    setError(null);
    const res = await diagnosticsApi.getDoctor();
    setData(res);
  };

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

  const jsonText = useMemo(() => JSON.stringify(data || {}, null, 2), [data]);

  const copyReport = async () => {
    try {
      await navigator.clipboard.writeText(jsonText);
    } catch (e) {
      console.error(e);
    }
  };

  const downloadReport = () => {
    const blob = new Blob([jsonText], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `doctor-report-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const runSmoke = async () => {
    setRunningSmoke(true);
    try {
      await diagnosticsApi.runE2ESmoke({});
      await refresh();
    } catch (e) {
      console.error(e);
    } finally {
      setRunningSmoke(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Doctor</h1>
          <p className="text-sm text-gray-500 mt-1">一键聚合诊断：健康检查、adapter 配置、autosmoke 配置与建议</p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/onboarding"
            className="px-3 py-2 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-sm"
          >
            去初始化向导
          </Link>
          <button
            onClick={runSmoke}
            disabled={runningSmoke}
            className="px-3 py-2 rounded-lg bg-primary text-white hover:opacity-90 disabled:opacity-60 transition-colors text-sm"
          >
            {runningSmoke ? '运行中…' : '一键跑 Smoke'}
          </button>
          <button
            onClick={copyReport}
            className="px-3 py-2 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-sm"
          >
            复制报告
          </button>
          <button
            onClick={downloadReport}
            className="px-3 py-2 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-sm"
          >
            下载 JSON
          </button>
          <button
            onClick={refresh}
            className="px-3 py-2 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-sm"
          >
            刷新
          </button>
        </div>
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

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">Strong Gate（default tenant）</div>
              <Badge variant={data?.strong_gate?.enabled ? 'warning' : 'success'}>
                {data?.strong_gate?.enabled ? 'enabled' : 'off'}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-sm text-gray-500 mb-3">
              {data?.strong_gate?.enabled ? '当前 default tenant 已开启强门禁（所有工具执行需审批）' : '当前未启用强门禁'}
            </div>
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto mt-3">
              {JSON.stringify(data?.strong_gate || {}, null, 2)}
            </pre>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">诊断即修复</div>
              <Badge variant="info">actions</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <ActionableFixes actions={data?.actions} recommendations={data?.recommendations} onAfterAction={refresh} />
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">Raw</div>
              <Badge variant="default">JSON</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
              {jsonText}
            </pre>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Doctor;
