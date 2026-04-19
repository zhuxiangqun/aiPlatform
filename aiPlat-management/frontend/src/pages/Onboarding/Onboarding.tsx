import { useEffect, useMemo, useState } from 'react';
import { CheckCircle, AlertTriangle, RotateCw } from 'lucide-react';
import { onboardingApi, diagnosticsApi } from '../../services/apiClient';

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

  const refreshState = async () => {
    setLoadingState(true);
    try {
      const s = await onboardingApi.getState();
      setState(s);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingState(false);
    }
  };

  useEffect(() => {
    refreshState();
  }, []);

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
    </div>
  );
};

export default Onboarding;

