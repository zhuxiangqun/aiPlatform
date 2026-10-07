import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, RefreshCw, ShieldCheck, AlertTriangle, XCircle, CheckCircle2, Copy, Container } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, toast } from '../../components/ui';
import { diagnosticsApi, onboardingApi } from '../../services';
import { clearPageData, reportPageData } from '../../lib/pageDataBridge';
import { toastGateError } from '../../components/ui';

const ENV_SNIPPET = `export AIPLAT_PROFILE=production
export AIPLAT_EXEC_PREFER_DOCKER=true
export AIPLAT_SANDBOX_PREFER_DOCKER=true
export AIPLAT_VECTOR_BACKEND=milvus
export AIPLAT_AGENT_EVENT_INGRESS=true`;

type ContractStackItem = {
  component?: string;
  role?: string;
  status?: string;
  anchor?: string;
};

type CheckRow = {
  id: string;
  title: string;
  status: 'pass' | 'warn' | 'fail' | string;
  detail?: string;
  hint?: string;
  contract?: {
    version?: string;
    healthy?: boolean;
    note?: string;
    stack?: ContractStackItem[];
    probes?: Record<string, string>;
  };
};

const statusBadge = (s: string) => {
  if (s === 'pass') return <Badge variant="success">pass</Badge>;
  if (s === 'warn') return <Badge variant="warning">warn</Badge>;
  return <Badge variant="error">fail</Badge>;
};

const contractStatusBadge = (s: string) => {
  if (s === 'required') return <Badge variant="info">required</Badge>;
  if (s === 'out_of_contract') return <Badge variant="default">out_of_contract</Badge>;
  return <Badge variant="default">{s || '-'}</Badge>;
};

const statusIcon = (s: string) => {
  if (s === 'pass') return <CheckCircle2 className="w-4 h-4 text-emerald-400" />;
  if (s === 'warn') return <AlertTriangle className="w-4 h-4 text-amber-400" />;
  return <XCircle className="w-4 h-4 text-red-400" />;
};

const ProductionDepth: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [data, setData] = useState<any>(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await diagnosticsApi.getProductionDepth();
      setData(res);
    } catch (e: any) {
      setData(null);
      toastGateError(e, '加载生产深度报告失败');
    } finally {
      setLoading(false);
    }
  };

  const copyEnv = async () => {
    try {
      await navigator.clipboard.writeText(ENV_SNIPPET);
      toast.success('已复制生产环境变量');
    } catch {
      toast.error('复制失败');
    }
  };

  const switchDocker = async () => {
    setSwitching(true);
    try {
      const res: any = await onboardingApi.setExecBackend({
        backend: 'docker',
        require_approval: true,
        details: 'production-depth: prefer docker isolation',
      });
      if (res?.status === 'approval_required' && res?.approval_request_id) {
        toast.error(`需要审批：${String(res.approval_request_id)}`);
        try {
          window.open('/core/approvals', '_blank', 'noopener,noreferrer');
        } catch {
          // ignore
        }
        return;
      }
      toast.success('已请求切换到 docker 执行后端');
      await load();
    } catch (e: any) {
      toastGateError(e, '切换 docker 失败');
    } finally {
      setSwitching(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const checks: CheckRow[] = Array.isArray(data?.checks) ? data.checks : [];
  const summary = data?.summary || {};
  const overall = String(data?.status || '-');

  useEffect(() => {
    reportPageData('/diagnostics/production-depth', {
      pageTitle: '生产深度',
      purpose: 'Agent OS 五处生产深度缺口自检：反思/Docker/事件/向量/可观测契约',
      itemNames: checks.map((c) => `${c.id}:${c.status}`).join(', '),
      actions: '刷新',
    });
    return () => clearPageData('/diagnostics/production-depth');
  }, [data]);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200 flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-sky-400" />
            生产深度
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            对照企业级 Agent 缺口：阶段反思、Docker 隔离、事件唤醒、向量后端、可观测契约
          </p>
        </div>
        <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={load} loading={loading}>
          刷新
        </Button>
      </div>

      <Link
        to="/diagnostics"
        className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 transition-colors"
      >
        <ArrowLeft className="w-3 h-3" />
        返回诊断中心
      </Link>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">overall</div>
          </CardHeader>
          <CardContent>{statusBadge(overall)}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">score</div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold text-gray-100">{data?.score ?? '-'}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">AIPLAT_PROFILE</div>
          </CardHeader>
          <CardContent>
            <Badge variant="default">{String(data?.profile || '(unset)')}</Badge>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">summary</div>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-gray-400 space-y-1">
              <div>pass: {summary.pass ?? 0}</div>
              <div>warn: {summary.warn ?? 0}</div>
              <div>fail: {summary.fail ?? 0}</div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">检查项</div>
        </CardHeader>
        <CardContent className="space-y-3">
          {checks.length === 0 && (
            <div className="text-sm text-gray-500">{loading ? '加载中…' : '暂无数据'}</div>
          )}
          {checks.map((c) => {
            const stack = Array.isArray(c.contract?.stack) ? c.contract!.stack! : [];
            const showHint = Boolean(c.hint) && (c.status !== 'pass' || c.id === 'observability_contract');
            return (
              <div
                key={c.id}
                className="rounded-lg border border-gray-800 bg-gray-900/40 px-3 py-3 space-y-1"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm text-gray-200 font-medium">
                    {statusIcon(c.status)}
                    {c.title}
                  </div>
                  {statusBadge(c.status)}
                </div>
                {c.detail ? (
                  <div className="text-xs text-gray-500 break-all font-mono">{c.detail}</div>
                ) : null}
                {showHint ? (
                  <div className="text-xs text-sky-400/90">
                    {c.status === 'pass' ? '说明：' : '建议：'}
                    {c.hint}
                  </div>
                ) : null}
                {c.id === 'observability_contract' && stack.length > 0 ? (
                  <div className="mt-2 space-y-1.5 border-t border-gray-800 pt-2">
                    <div className="text-[11px] text-gray-500">
                      契约栈 v{c.contract?.version || '-'} · healthy=
                      {String(c.contract?.healthy ?? '-')}
                    </div>
                    {stack.map((row) => (
                      <div
                        key={String(row.component)}
                        className="flex flex-wrap items-center gap-2 text-xs text-gray-400"
                      >
                        {contractStatusBadge(String(row.status || ''))}
                        <span className="text-gray-200 font-mono">{row.component}</span>
                        <span className="text-gray-600">·</span>
                        <span>{row.role}</span>
                        {row.status === 'out_of_contract' ? (
                          <span className="text-gray-500">
                            （可选外部接入，非平台必交付）
                          </span>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">快捷操作</div>
        </CardHeader>
        <CardContent>
          <pre className="text-xs text-gray-400 bg-black/30 rounded-lg p-3 overflow-x-auto">{ENV_SNIPPET}</pre>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button variant="secondary" icon={<Copy size={14} />} onClick={copyEnv}>
              复制环境变量
            </Button>
            <Button
              variant="secondary"
              icon={<Container size={14} />}
              onClick={switchDocker}
              loading={switching}
            >
              切换执行后端 → docker
            </Button>
            <Link to="/diagnostics/exec-backends">
              <Button variant="secondary">执行后端</Button>
            </Link>
            <Link to="/diagnostics/observability">
              <Button variant="secondary">可观测性</Button>
            </Link>
          </div>
          <div className="text-xs text-gray-500 mt-2">
            环境变量需重启进程生效；docker 切换写入 global_setting，可能触发审批。
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default ProductionDepth;
