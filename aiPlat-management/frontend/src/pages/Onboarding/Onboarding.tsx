import { useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle, AlertTriangle, RotateCw } from 'lucide-react';
import { onboardingApi, diagnosticsApi } from '../../services/apiClient';
import { approvalsApi } from '../../services';

type StepKey = 'adapter' | 'health' | 'smoke';

const StepBadge: React.FC<{ ok?: boolean; loading?: boolean }> = ({ ok, loading }) => {
  if (loading) return <RotateCw className="w-4 h-4 text-primary animate-spin" />;
  if (ok === true) return <CheckCircle className="w-4 h-4 text-green-500" />;
  if (ok === false) return <AlertTriangle className="w-4 h-4 text-red-500" />;
  return <span className="w-4 h-4 inline-block" />;
};

const Onboarding: React.FC = () => {
  const [activeStep, setActiveStep] = useState<StepKey>('adapter');
  const [state, setState] = useState<any>(null);
  const [loadingState, setLoadingState] = useState(false);

  // Step: Adapter
  const [adapterForm, setAdapterForm] = useState({
    name: 'DeepSeek',
    provider: 'OpenAI',
    api_base_url: 'https://api.deepseek.com',
    api_key: '',
    models: 'deepseek-reasoner,deepseek-chat',
  });
  const [adapterLoading, setAdapterLoading] = useState(false);
  const [adapterResult, setAdapterResult] = useState<any>(null);

  // Step: Health
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthResult, setHealthResult] = useState<any>(null);

  // Step: Smoke
  const [smokeLoading, setSmokeLoading] = useState(false);
  const [smokeResult, setSmokeResult] = useState<any>(null);

  // Enhancements: Default routing / init tenant
  const [defaultLlmForm, setDefaultLlmForm] = useState({ adapter_id: '', model: '' });
  const [defaultLlmResult, setDefaultLlmResult] = useState<any>(null);
  const [defaultLlmLoading, setDefaultLlmLoading] = useState(false);
  const [defaultLlmApprovalId, setDefaultLlmApprovalId] = useState<string>('');

  const [initTenantLoading, setInitTenantLoading] = useState(false);
  const [initTenantResult, setInitTenantResult] = useState<any>(null);
  const [initTenantApprovalId, setInitTenantApprovalId] = useState<string>('');

  // Enhancements: approvals + doctor + key rotation
  const [pendingApprovals, setPendingApprovals] = useState<any[]>([]);
  const [approvalsLoading, setApprovalsLoading] = useState(false);
  const [doctor, setDoctor] = useState<any>(null);
  const [doctorLoading, setDoctorLoading] = useState(false);
  const [rotateKeyForm, setRotateKeyForm] = useState<{ adapter_id: string; api_key: string }>({ adapter_id: '', api_key: '' });
  const [rotateKeyLoading, setRotateKeyLoading] = useState(false);
  const [rotateKeyResult, setRotateKeyResult] = useState<any>(null);

  // Auto-poll approvals and auto-apply on approval
  const [approvalWatch, setApprovalWatch] = useState<Record<string, { op: 'default_llm' | 'init_tenant'; created_at: number }>>({});
  const [approvalWatchLog, setApprovalWatchLog] = useState<Record<string, string>>({});
  const approvalWatchInFlight = useRef<Record<string, boolean>>({});

  const refreshApprovals = async () => {
    setApprovalsLoading(true);
    try {
      const res = await approvalsApi.listPending({ limit: 200, offset: 0 });
      const items = (res?.items || []).filter((r: any) => String(r?.operation || '').startsWith('onboarding:'));
      setPendingApprovals(items);
    } catch (e) {
      console.error(e);
      setPendingApprovals([]);
    } finally {
      setApprovalsLoading(false);
    }
  };

  const refreshDoctor = async () => {
    setDoctorLoading(true);
    try {
      const res = await diagnosticsApi.getDoctor();
      setDoctor(res);
    } catch (e) {
      console.error(e);
      setDoctor(null);
    } finally {
      setDoctorLoading(false);
    }
  };

  const refreshState = async () => {
    setLoadingState(true);
    try {
      const s = await onboardingApi.getState();
      setState(s);
      const adapters = s?.adapters?.adapters || [];
      const firstAdapterId = adapters?.[0]?.adapter_id || '';
      setDefaultLlmForm((prev) => ({
        adapter_id: prev.adapter_id || firstAdapterId,
        model: prev.model || (adapters?.[0]?.models?.[0]?.name ? String(adapters[0].models[0].name) : ''),
      }));
      setRotateKeyForm((prev) => ({ ...prev, adapter_id: prev.adapter_id || firstAdapterId }));
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingState(false);
    }
  };

  useEffect(() => {
    refreshState();
    refreshApprovals();
    refreshDoctor();
  }, []);

  // Poll approval status and auto-apply when approved
  useEffect(() => {
    const keys = Object.keys(approvalWatch || {});
    if (keys.length === 0) return;

    const timer = window.setInterval(async () => {
      for (const requestId of Object.keys(approvalWatch || {})) {
        const w = approvalWatch[requestId];
        if (!w) continue;
        if (approvalWatchInFlight.current[requestId]) continue;

        // TTL: 10 minutes
        if (Date.now() - w.created_at > 10 * 60 * 1000) {
          setApprovalWatch((prev) => {
            const next = { ...(prev || {}) };
            delete next[requestId];
            return next;
          });
          setApprovalWatchLog((prev) => ({ ...(prev || {}), [requestId]: '轮询超时（已停止）' }));
          continue;
        }

        approvalWatchInFlight.current[requestId] = true;
        try {
          const detail = await approvalsApi.get(requestId);
          const status = String(detail?.status || '');
          if (status === 'approved' || status === 'auto_approved') {
            setApprovalWatchLog((prev) => ({ ...(prev || {}), [requestId]: '已批准，正在自动生效…' }));
            if (w.op === 'default_llm') {
              setDefaultLlmApprovalId(requestId);
              await submitDefaultLLM(requestId);
            } else if (w.op === 'init_tenant') {
              setInitTenantApprovalId(requestId);
              await submitInitTenant(requestId);
            }
            setApprovalWatch((prev) => {
              const next = { ...(prev || {}) };
              delete next[requestId];
              return next;
            });
            setApprovalWatchLog((prev) => ({ ...(prev || {}), [requestId]: '已自动生效' }));
          } else if (status === 'rejected' || status === 'cancelled' || status === 'expired') {
            setApprovalWatch((prev) => {
              const next = { ...(prev || {}) };
              delete next[requestId];
              return next;
            });
            setApprovalWatchLog((prev) => ({ ...(prev || {}), [requestId]: `审批未通过：${status}` }));
          } else {
            setApprovalWatchLog((prev) => ({ ...(prev || {}), [requestId]: `等待审批中：${status || 'pending'}` }));
          }
        } catch (e) {
          console.error(e);
        } finally {
          approvalWatchInFlight.current[requestId] = false;
        }
      }
    }, 2500);

    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [approvalWatch]);

  const steps = useMemo(
    () => [
      { key: 'adapter' as StepKey, title: '配置模型 Adapter', desc: '写入 core 的 Adapter 配置并测试连通性' },
      { key: 'health' as StepKey, title: '检查全链路健康', desc: 'infra/core/platform/app 健康状态' },
      { key: 'smoke' as StepKey, title: '运行 E2E Smoke', desc: '触发一次生产级全链路冒烟' },
    ],
    []
  );

  const healthOk = useMemo(() => {
    const h = healthResult?.health || state?.health;
    if (!h) return undefined;
    const layers = ['infra', 'core', 'platform', 'app'];
    return layers.every((k) => (h?.[k]?.status || '') === 'healthy');
  }, [healthResult, state]);

  const adapterOk = useMemo(() => {
    if (!adapterResult) return undefined;
    return !!adapterResult?.test?.success;
  }, [adapterResult]);

  const smokeOk = useMemo(() => {
    if (!smokeResult) return undefined;
    return !!smokeResult?.ok;
  }, [smokeResult]);

  const runConfigureAdapter = async () => {
    setAdapterLoading(true);
    setAdapterResult(null);
    try {
      const models = adapterForm.models
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await onboardingApi.configureLLMAdapter({
        name: adapterForm.name,
        provider: adapterForm.provider,
        api_base_url: adapterForm.api_base_url,
        api_key: adapterForm.api_key,
        models,
      });
      setAdapterResult(res);
      await refreshState();
      setActiveStep('health');
    } catch (e: any) {
      setAdapterResult({ test: { success: false, error: e?.message || String(e) } });
    } finally {
      setAdapterLoading(false);
    }
  };

  const runHealthCheck = async () => {
    setHealthLoading(true);
    try {
      const res = await diagnosticsApi.getHealth('all');
      // diagnosticsApi.getHealth expects layer; we use /diagnostics/health/all via apiClient.get directly
      setHealthResult({ health: res });
      setActiveStep('smoke');
    } catch (e) {
      console.error(e);
    } finally {
      setHealthLoading(false);
    }
  };

  const runSmoke = async () => {
    setSmokeLoading(true);
    setSmokeResult(null);
    try {
      const res = await diagnosticsApi.runE2ESmoke({});
      setSmokeResult(res);
      await refreshState();
    } catch (e: any) {
      setSmokeResult({ ok: false, error: e?.message || String(e) });
    } finally {
      setSmokeLoading(false);
    }
  };

  const submitDefaultLLM = async (approvalIdOverride?: string) => {
    setDefaultLlmLoading(true);
    setDefaultLlmResult(null);
    try {
      const res = await onboardingApi.setDefaultLLM({
        adapter_id: defaultLlmForm.adapter_id,
        model: defaultLlmForm.model,
        require_approval: true,
        approval_request_id: approvalIdOverride || defaultLlmApprovalId || undefined,
      });
      setDefaultLlmResult(res);
      if (res?.status === 'approval_required' && res?.approval_request_id) {
        const rid = String(res.approval_request_id);
        setDefaultLlmApprovalId(rid);
        setApprovalWatch((prev) => ({ ...(prev || {}), [rid]: { op: 'default_llm', created_at: Date.now() } }));
        setApprovalWatchLog((prev) => ({ ...(prev || {}), [rid]: '等待审批中：pending' }));
      }
      await refreshState();
    } catch (e: any) {
      setDefaultLlmResult({ status: 'error', error: e?.message || String(e) });
    } finally {
      setDefaultLlmLoading(false);
    }
  };

  const submitInitTenant = async (approvalIdOverride?: string) => {
    setInitTenantLoading(true);
    setInitTenantResult(null);
    try {
      const res = await onboardingApi.initTenant({
        tenant_id: 'default',
        tenant_name: 'default',
        init_policies: true,
        require_approval: true,
        approval_request_id: approvalIdOverride || initTenantApprovalId || undefined,
      });
      setInitTenantResult(res);
      if (res?.status === 'approval_required' && res?.approval_request_id) {
        const rid = String(res.approval_request_id);
        setInitTenantApprovalId(rid);
        setApprovalWatch((prev) => ({ ...(prev || {}), [rid]: { op: 'init_tenant', created_at: Date.now() } }));
        setApprovalWatchLog((prev) => ({ ...(prev || {}), [rid]: '等待审批中：pending' }));
      }
      await refreshState();
    } catch (e: any) {
      setInitTenantResult({ status: 'error', error: e?.message || String(e) });
    } finally {
      setInitTenantLoading(false);
    }
  };

  const setDefaultLLM = async () => submitDefaultLLM();
  const initTenant = async () => submitInitTenant();

  const approveAndRetry = async (requestId: string) => {
    try {
      // capture op before approving (the item will disappear from pending list after approval)
      const op = pendingApprovals.find((p) => p.request_id === requestId)?.operation || '';
      await approvalsApi.approve(requestId, 'admin', '');
      await refreshApprovals();
      // Auto-retry known onboarding operations (pass approval id directly)
      if (String(op) === 'onboarding:default_llm') {
        setDefaultLlmApprovalId(requestId);
        await submitDefaultLLM(requestId);
      } else if (String(op) === 'onboarding:init_tenant') {
        setInitTenantApprovalId(requestId);
        await submitInitTenant(requestId);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const rejectApproval = async (requestId: string) => {
    try {
      await approvalsApi.reject(requestId, 'admin', '');
      await refreshApprovals();
    } catch (e) {
      console.error(e);
    }
  };

  const rotateKey = async () => {
    setRotateKeyLoading(true);
    setRotateKeyResult(null);
    try {
      const res = await onboardingApi.rotateAdapterKey({ adapter_id: rotateKeyForm.adapter_id, api_key: rotateKeyForm.api_key });
      setRotateKeyResult(res);
      setRotateKeyForm((p) => ({ ...p, api_key: '' }));
      await refreshState();
    } catch (e: any) {
      setRotateKeyResult({ status: 'error', error: e?.message || String(e) });
    } finally {
      setRotateKeyLoading(false);
    }
  };

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-200">初始化向导</h1>
          <p className="text-sm text-gray-500 mt-1">把系统快速带到“可用 + 可观测 + 可验证”的状态</p>
        </div>
        <button
          onClick={refreshState}
          className="px-3 py-2 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-sm flex items-center gap-2"
        >
          <RotateCw className={`w-4 h-4 ${loadingState ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      {/* Stepper */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {steps.map((s) => {
          const active = activeStep === s.key;
          const ok = s.key === 'adapter' ? adapterOk : s.key === 'health' ? healthOk : smokeOk;
          const loading = s.key === 'adapter' ? adapterLoading : s.key === 'health' ? healthLoading : smokeLoading;
          return (
            <button
              key={s.key}
              onClick={() => setActiveStep(s.key)}
              className={`p-4 rounded-xl border text-left transition-colors ${
                active ? 'border-primary bg-primary-light/10' : 'border-dark-border bg-dark-bg hover:bg-dark-hover'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-gray-200 font-medium">{s.title}</div>
                  <div className="text-gray-500 text-xs mt-1">{s.desc}</div>
                </div>
                <StepBadge ok={ok} loading={loading} />
              </div>
            </button>
          );
        })}
      </div>

      {/* Step content */}
      {activeStep === 'adapter' && (
        <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-4">
          <div className="text-gray-200 font-medium">Step 1：配置模型 Adapter</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-gray-500 mb-1">名称</div>
              <input
                value={adapterForm.name}
                onChange={(e) => setAdapterForm({ ...adapterForm, name: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
              />
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">Provider</div>
              <select
                value={adapterForm.provider}
                onChange={(e) => setAdapterForm({ ...adapterForm, provider: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
              >
                <option value="OpenAI">OpenAI-compatible</option>
                <option value="Anthropic">Anthropic</option>
                <option value="Custom">Custom</option>
              </select>
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">API Base URL</div>
              <input
                value={adapterForm.api_base_url}
                onChange={(e) => setAdapterForm({ ...adapterForm, api_base_url: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
              />
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">API Key</div>
              <input
                type="password"
                value={adapterForm.api_key}
                onChange={(e) => setAdapterForm({ ...adapterForm, api_key: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
              />
            </div>
            <div className="md:col-span-2">
              <div className="text-xs text-gray-500 mb-1">Models（逗号分隔）</div>
              <input
                value={adapterForm.models}
                onChange={(e) => setAdapterForm({ ...adapterForm, models: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              disabled={adapterLoading}
              onClick={runConfigureAdapter}
              className="px-4 py-2 rounded-lg bg-primary text-white text-sm hover:opacity-90 disabled:opacity-60"
            >
              保存并测试
            </button>
            {adapterResult?.test && (
              <div className="text-sm text-gray-500">
                测试结果：{adapterResult.test.success ? '成功' : `失败 - ${adapterResult.test.error || 'unknown'}`}
              </div>
            )}
          </div>
        </div>
      )}

      {activeStep === 'health' && (
        <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-4">
          <div className="text-gray-200 font-medium">Step 2：检查全链路健康</div>
          <button
            disabled={healthLoading}
            onClick={runHealthCheck}
            className="px-4 py-2 rounded-lg bg-primary text-white text-sm hover:opacity-90 disabled:opacity-60"
          >
            运行健康检查
          </button>
          <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
            {JSON.stringify(healthResult?.health || state?.health || {}, null, 2)}
          </pre>
        </div>
      )}

      {activeStep === 'smoke' && (
        <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-4">
          <div className="text-gray-200 font-medium">Step 3：运行 E2E Smoke</div>
          <button
            disabled={smokeLoading}
            onClick={runSmoke}
            className="px-4 py-2 rounded-lg bg-primary text-white text-sm hover:opacity-90 disabled:opacity-60"
          >
            触发冒烟
          </button>
          <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
            {JSON.stringify(smokeResult || {}, null, 2)}
          </pre>
        </div>
      )}

      {/* Current adapters snapshot */}
      <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-3">
        <div className="text-gray-200 font-medium">当前 Adapter 列表（core）</div>
        <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
          {JSON.stringify(state?.adapters || {}, null, 2)}
        </pre>
      </div>

      {/* Approvals inline */}
      <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-gray-200 font-medium">审批（Onboarding）</div>
          <button
            onClick={refreshApprovals}
            className="px-3 py-1.5 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-xs"
          >
            {approvalsLoading ? '刷新中…' : '刷新'}
          </button>
        </div>
        {Object.keys(approvalWatch || {}).length > 0 && (
          <div className="text-xs text-gray-500">自动轮询中：{Object.keys(approvalWatch).length} 条（批准后将自动生效）</div>
        )}
        {(pendingApprovals || []).length === 0 ? (
          <div className="text-sm text-gray-500">暂无待审批项</div>
        ) : (
          <div className="space-y-2">
            {pendingApprovals.map((p) => (
              <div key={p.request_id} className="flex items-center justify-between gap-3 bg-dark-hover border border-dark-border rounded-lg p-3">
                <div className="text-xs text-gray-300">
                  <div>
                    <span className="text-gray-500">operation：</span>
                    <code>{String(p.operation)}</code>
                  </div>
                  <div>
                    <span className="text-gray-500">request_id：</span>
                    <code>{String(p.request_id).slice(0, 12)}</code>
                  </div>
                  {approvalWatchLog?.[p.request_id] && <div className="text-gray-500 mt-1">{approvalWatchLog[p.request_id]}</div>}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => approveAndRetry(p.request_id)}
                    className="px-3 py-1.5 rounded-lg bg-primary text-white text-xs hover:opacity-90"
                  >
                    批准并重试
                  </button>
                  <button
                    onClick={() => rejectApproval(p.request_id)}
                    className="px-3 py-1.5 rounded-lg bg-dark-bg text-gray-200 border border-dark-border text-xs hover:bg-dark-border"
                  >
                    拒绝
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Enhancements */}
      <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-4">
        <div className="text-gray-200 font-medium">增强：设为默认路由（全局，需审批）</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <div className="text-xs text-gray-500 mb-1">默认 Adapter</div>
            <select
              value={defaultLlmForm.adapter_id}
              onChange={(e) => setDefaultLlmForm({ ...defaultLlmForm, adapter_id: e.target.value })}
              className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
            >
              {(state?.adapters?.adapters || []).map((a: any) => (
                <option key={a.adapter_id} value={a.adapter_id}>
                  {a.name} ({a.provider})
                </option>
              ))}
            </select>
          </div>
          <div>
            <div className="text-xs text-gray-500 mb-1">默认 Model</div>
            <input
              value={defaultLlmForm.model}
              onChange={(e) => setDefaultLlmForm({ ...defaultLlmForm, model: e.target.value })}
              placeholder="例如：deepseek-reasoner"
              className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
            />
          </div>
          <div className="md:col-span-2">
            <div className="text-xs text-gray-500 mb-1">approval_request_id（可选：批准后填入再提交）</div>
            <input
              value={defaultLlmApprovalId}
              onChange={(e) => setDefaultLlmApprovalId(e.target.value)}
              placeholder="例如：apr-xxxx"
              className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
            />
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            disabled={defaultLlmLoading}
            onClick={setDefaultLLM}
            className="px-4 py-2 rounded-lg bg-primary text-white text-sm hover:opacity-90 disabled:opacity-60"
          >
            {defaultLlmLoading ? '提交中…' : '提交审批/生效'}
          </button>
          {defaultLlmResult?.status === 'approval_required' && (
            <div className="text-sm text-gray-500">
              已创建审批：<code className="text-xs">{defaultLlmResult.approval_request_id}</code>，请到 <code>/core/approvals</code> 批准后重试提交（携带 approval_request_id）。
            </div>
          )}
          {defaultLlmResult?.status === 'updated' && <div className="text-sm text-gray-500">已更新默认路由</div>}
          {defaultLlmResult?.status === 'error' && <div className="text-sm text-red-400">失败：{defaultLlmResult.error}</div>}
        </div>
        <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
          当前 default_llm：{JSON.stringify(state?.core_state?.default_llm || null, null, 2)}
        </pre>
      </div>

      <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-4">
        <div className="text-gray-200 font-medium">增强：初始化默认 Tenant/Policies（需审批）</div>
        <div>
          <div className="text-xs text-gray-500 mb-1">approval_request_id（可选：批准后填入再提交）</div>
          <input
            value={initTenantApprovalId}
            onChange={(e) => setInitTenantApprovalId(e.target.value)}
            placeholder="例如：apr-xxxx"
            className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
          />
        </div>
        <button
          disabled={initTenantLoading}
          onClick={initTenant}
          className="px-4 py-2 rounded-lg bg-primary text-white text-sm hover:opacity-90 disabled:opacity-60"
        >
          {initTenantLoading ? '提交中…' : '初始化 default tenant'}
        </button>
        <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
          {JSON.stringify(initTenantResult || state?.core_state?.tenants || {}, null, 2)}
        </pre>
      </div>

      <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-3">
        <div className="text-gray-200 font-medium">安全：密钥存储状态</div>
        <div className="text-sm text-gray-500">
          AIPLAT_SECRET_KEY：{state?.core_state?.secrets?.configured ? '已配置（api_key 将加密存储）' : '未配置（将回退为明文存储，建议尽快配置）'}
        </div>
        {!state?.core_state?.secrets?.configured && (
          <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
            {`# 生成 Fernet key（一次性）\npython3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"\n# 设置环境变量（示例）\nexport AIPLAT_SECRET_KEY='<paste-key-here>'\n`}
          </pre>
        )}
      </div>

      <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-4">
        <div className="text-gray-200 font-medium">安全：轮换 Adapter API Key（不回显旧 key）</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <div className="text-xs text-gray-500 mb-1">选择 Adapter</div>
            <select
              value={rotateKeyForm.adapter_id}
              onChange={(e) => setRotateKeyForm({ ...rotateKeyForm, adapter_id: e.target.value })}
              className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
            >
              {(state?.adapters?.adapters || []).map((a: any) => (
                <option key={a.adapter_id} value={a.adapter_id}>
                  {a.name} ({a.provider})
                </option>
              ))}
            </select>
          </div>
          <div>
            <div className="text-xs text-gray-500 mb-1">新 API Key</div>
            <input
              type="password"
              value={rotateKeyForm.api_key}
              onChange={(e) => setRotateKeyForm({ ...rotateKeyForm, api_key: e.target.value })}
              className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
            />
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            disabled={rotateKeyLoading}
            onClick={rotateKey}
            className="px-4 py-2 rounded-lg bg-primary text-white text-sm hover:opacity-90 disabled:opacity-60"
          >
            {rotateKeyLoading ? '提交中…' : '轮换 Key'}
          </button>
          {rotateKeyResult?.status === 'rotated' && <div className="text-sm text-gray-500">已更新</div>}
          {rotateKeyResult?.status === 'error' && <div className="text-sm text-red-400">失败：{rotateKeyResult.error}</div>}
        </div>
      </div>

      <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-gray-200 font-medium">配置检查（Doctor）</div>
          <button
            onClick={refreshDoctor}
            className="px-3 py-1.5 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-xs"
          >
            {doctorLoading ? '刷新中…' : '刷新'}
          </button>
        </div>
        <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
          {JSON.stringify(doctor?.recommendations || [], null, 2)}
        </pre>
        <div className="flex items-center gap-2">
          <button
            onClick={() => copyText(`export AIPLAT_MANAGEMENT_PUBLIC_URL='${doctor?.config?.management_public_url || 'https://<your-host>'}'\n`)}
            className="px-3 py-1.5 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-xs"
          >
            复制 Public URL 示例
          </button>
          <button
            onClick={() => copyText(`export AIPLAT_AUTOSMOKE_ENABLED=true\nexport AIPLAT_AUTOSMOKE_ENFORCE=true\n`)}
            className="px-3 py-1.5 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-xs"
          >
            复制 autosmoke 示例
          </button>
        </div>
      </div>
    </div>
  );
};

export default Onboarding;
