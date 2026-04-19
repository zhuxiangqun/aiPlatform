import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { approvalsApi, diagnosticsApi, onboardingApi } from '../../services';
import { Card, CardContent, CardHeader, Badge } from '../../components/ui';

const Doctor: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [runningSmoke, setRunningSmoke] = useState(false);
  const [strongGateLoading, setStrongGateLoading] = useState(false);
  const [strongGateMsg, setStrongGateMsg] = useState<string | null>(null);
  const [strongGateApprovalId, setStrongGateApprovalId] = useState<string>('');
  const [strongGatePollStatus, setStrongGatePollStatus] = useState<string>('');
  const pollInFlight = useRef(false);

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

  const disableStrongGate = async (approvalIdOverride?: string) => {
    setStrongGateLoading(true);
    setStrongGateMsg(null);
    try {
      const res = await onboardingApi.setStrongGate({
        tenant_id: 'default',
        enabled: false,
        require_approval: true,
        approval_request_id: approvalIdOverride || strongGateApprovalId || undefined,
      });
      if (res?.status === 'approval_required' && res?.approval_request_id) {
        setStrongGateApprovalId(String(res.approval_request_id));
        setStrongGateMsg(`已创建审批：${String(res.approval_request_id)}`);
        setStrongGatePollStatus('等待审批中：pending');
      } else {
        setStrongGateMsg(JSON.stringify(res));
        setStrongGateApprovalId('');
        setStrongGatePollStatus('');
        await refresh();
      }
    } catch (e: any) {
      setStrongGateMsg(e?.message || '操作失败');
    } finally {
      setStrongGateLoading(false);
    }
  };

  // Poll approval status, auto-apply when approved
  useEffect(() => {
    if (!strongGateApprovalId) return;
    const createdAt = Date.now();
    const timer = window.setInterval(async () => {
      if (!strongGateApprovalId) return;
      if (pollInFlight.current) return;
      if (Date.now() - createdAt > 10 * 60 * 1000) {
        setStrongGatePollStatus('轮询超时（已停止）');
        return;
      }
      pollInFlight.current = true;
      try {
        const detail = await approvalsApi.get(strongGateApprovalId);
        const st = String(detail?.status || 'pending');
        if (st === 'approved' || st === 'auto_approved') {
          setStrongGatePollStatus('已批准，正在自动解除强门禁…');
          await disableStrongGate(strongGateApprovalId);
        } else if (st === 'rejected' || st === 'cancelled' || st === 'expired') {
          setStrongGatePollStatus(`审批未通过：${st}`);
        } else {
          setStrongGatePollStatus(`等待审批中：${st}`);
        }
      } catch (e) {
        console.error(e);
      } finally {
        pollInFlight.current = false;
      }
    }, 2500);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strongGateApprovalId]);

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
              {data?.strong_gate?.enabled
                ? '当前 default tenant 已开启强门禁（所有工具执行需审批）。如为误开启，可一键回滚。'
                : '当前未启用强门禁。'}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => disableStrongGate()}
                disabled={strongGateLoading || !data?.strong_gate?.enabled}
                className="px-3 py-2 rounded-lg bg-primary text-white hover:opacity-90 disabled:opacity-60 transition-colors text-sm"
              >
                {strongGateLoading ? '处理中…' : '解除强门禁（需审批）'}
              </button>
              <Link
                to="/core/approvals"
                className="px-3 py-2 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-sm"
              >
                去审批中心
              </Link>
            </div>
            {(strongGateMsg || strongGatePollStatus) && (
              <div className="mt-3 text-xs text-gray-400 space-y-1">
                {strongGateMsg && <div>{strongGateMsg}</div>}
                {strongGateApprovalId && (
                  <div>
                    approval_request_id：<code>{strongGateApprovalId}</code>
                  </div>
                )}
                {strongGatePollStatus && <div>{strongGatePollStatus}</div>}
              </div>
            )}
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto mt-3">
              {JSON.stringify(data?.strong_gate || {}, null, 2)}
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
