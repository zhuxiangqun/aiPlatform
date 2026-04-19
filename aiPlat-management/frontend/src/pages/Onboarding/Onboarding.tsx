import { useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle, AlertTriangle, RotateCw } from 'lucide-react';
import { onboardingApi, diagnosticsApi } from '../../services/apiClient';
import { approvalsApi, policyApi } from '../../services';
import { ActionableFixes } from '../../components/common/ActionableFixes';

type StepKey = 'adapter' | 'default_llm' | 'tenant' | 'strong_gate' | 'autosmoke' | 'secrets' | 'doctor' | 'health' | 'smoke';

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
  const [defaultLlmDetails, setDefaultLlmDetails] = useState<string>('');

  const [initTenantLoading, setInitTenantLoading] = useState(false);
  const [initTenantResult, setInitTenantResult] = useState<any>(null);
  const [initTenantApprovalId, setInitTenantApprovalId] = useState<string>('');
  const [strictToolApproval, setStrictToolApproval] = useState(true);
  const [initTenantDetails, setInitTenantDetails] = useState<string>('');

  // Enhancements: approvals + doctor + key rotation
  const [pendingApprovals, setPendingApprovals] = useState<any[]>([]);
  const [approvalsLoading, setApprovalsLoading] = useState(false);
  const [doctor, setDoctor] = useState<any>(null);
  const [doctorLoading, setDoctorLoading] = useState(false);
  const [rotateKeyForm, setRotateKeyForm] = useState<{ adapter_id: string; api_key: string }>({ adapter_id: '', api_key: '' });
  const [rotateKeyLoading, setRotateKeyLoading] = useState(false);
  const [rotateKeyResult, setRotateKeyResult] = useState<any>(null);
  const [autosmokeLoading, setAutosmokeLoading] = useState(false);
  const [autosmokeResult, setAutosmokeResult] = useState<any>(null);
  const [autosmokeApprovalId, setAutosmokeApprovalId] = useState<string>('');
  const [autosmokeForm, setAutosmokeForm] = useState({ enabled: true, enforce: true, webhook_url: '' });
  const [autosmokeDetails, setAutosmokeDetails] = useState<string>('');

  const [secretsStatus, setSecretsStatus] = useState<any>(null);
  const [secretsLoading, setSecretsLoading] = useState(false);
  const [migrateSecretsLoading, setMigrateSecretsLoading] = useState(false);
  const [migrateSecretsResult, setMigrateSecretsResult] = useState<any>(null);
  const [migrateSecretsApprovalId, setMigrateSecretsApprovalId] = useState<string>('');
  const [migrateSecretsDetails, setMigrateSecretsDetails] = useState<string>('');

  const [defaultTenantPolicy, setDefaultTenantPolicy] = useState<any>(null);
  const [tenantPolicyLoading, setTenantPolicyLoading] = useState(false);
  const [strongGateLoading, setStrongGateLoading] = useState(false);
  const [strongGateResult, setStrongGateResult] = useState<any>(null);
  const [strongGateApprovalId, setStrongGateApprovalId] = useState<string>('');
  const [strongGateDetails, setStrongGateDetails] = useState<string>('');

  // Auto-poll approvals and auto-apply on approval
  const [approvalWatch, setApprovalWatch] = useState<
    Record<
      string,
      { op: 'default_llm' | 'init_tenant' | 'autosmoke' | 'secrets_migrate' | 'strong_gate_on' | 'strong_gate_off'; created_at: number }
    >
  >({});
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

  const refreshSecrets = async () => {
    setSecretsLoading(true);
    try {
      const st = await onboardingApi.getSecretsStatus();
      setSecretsStatus(st);
    } catch (e) {
      console.error(e);
      setSecretsStatus(null);
    } finally {
      setSecretsLoading(false);
    }
  };

  const refreshDefaultTenantPolicy = async () => {
    setTenantPolicyLoading(true);
    try {
      const p = await policyApi.getTenant('default');
      setDefaultTenantPolicy(p);
    } catch (e) {
      // policy might not exist yet
      setDefaultTenantPolicy(null);
    } finally {
      setTenantPolicyLoading(false);
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
      // autosmoke config from core (best-effort)
      const sm = s?.core_state?.autosmoke;
      if (sm && typeof sm === 'object') {
        setAutosmokeForm((p) => ({
          ...p,
          enabled: sm.enabled != null ? !!sm.enabled : p.enabled,
          enforce: sm.enforce != null ? !!sm.enforce : p.enforce,
          webhook_url: sm.webhook_url != null ? String(sm.webhook_url) : p.webhook_url,
        }));
      }
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
    refreshSecrets();
    refreshDefaultTenantPolicy();
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
            } else if (w.op === 'autosmoke') {
              setAutosmokeApprovalId(requestId);
              await submitAutosmoke(requestId);
            } else if (w.op === 'secrets_migrate') {
              setMigrateSecretsApprovalId(requestId);
              await submitMigrateSecrets(requestId);
            } else if (w.op === 'strong_gate_on') {
              setStrongGateApprovalId(requestId);
              await submitStrongGate(true, requestId);
            } else if (w.op === 'strong_gate_off') {
              setStrongGateApprovalId(requestId);
              await submitStrongGate(false, requestId);
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
      { key: 'default_llm' as StepKey, title: '设为默认路由', desc: '配置全局默认 LLM 路由（需要审批时会自动轮询）' },
      { key: 'tenant' as StepKey, title: '初始化 default tenant', desc: '初始化默认租户/最小策略（可选强门禁）' },
      { key: 'strong_gate' as StepKey, title: '强门禁开关', desc: 'default tenant：控制“所有工具需审批”开关' },
      { key: 'autosmoke' as StepKey, title: '配置 autosmoke', desc: '启用 autosmoke + enforce（发布前验证）' },
      { key: 'secrets' as StepKey, title: '密钥与迁移', desc: '检查 SecretKey、迁移明文密钥、轮换 Adapter key' },
      { key: 'doctor' as StepKey, title: 'Doctor 一键检查', desc: '聚合诊断 + Quick Fix Actions（自动审批轮询）' },
      { key: 'health' as StepKey, title: '检查全链路健康', desc: 'infra/core/platform/app 健康状态' },
      { key: 'smoke' as StepKey, title: '运行 E2E Smoke', desc: '触发一次生产级全链路冒烟' },
    ],
    []
  );

  const defaultLlmOk = !!(state?.core_state?.default_llm?.adapter_id && state?.core_state?.default_llm?.model);
  const tenantOk = !!(defaultTenantPolicy || state?.core_state?.tenants?.default || state?.core_state?.tenants?.items?.find?.((t: any) => t?.tenant_id === 'default'));
  const autosmokeOk = !!state?.core_state?.autosmoke?.enabled;
  const secretsOk =
    !!state?.core_state?.secrets?.configured && (Number(secretsStatus?.plaintext_count ?? secretsStatus?.plain_count ?? 0) || 0) === 0;
  const doctorOk = (() => {
    if (!doctor) return false;
    const h = doctor?.health;
    if (typeof h?.ok === 'boolean') return h.ok;
    if (h && typeof h === 'object') {
      const coreOk = h?.core?.ok;
      if (typeof coreOk === 'boolean') return coreOk;
      const coreStatus = String(h?.core?.status || '').toLowerCase();
      if (coreStatus === 'ok' || coreStatus === 'success') return true;
    }
    return true;
  })();

  const getStepOk = (k: StepKey) => {
    if (k === 'adapter') return adapterOk;
    if (k === 'default_llm') return defaultLlmOk;
    if (k === 'tenant') return tenantOk;
    if (k === 'strong_gate') return isStrongGateEnabled;
    if (k === 'autosmoke') return autosmokeOk;
    if (k === 'secrets') return secretsOk;
    if (k === 'doctor') return doctorOk;
    if (k === 'health') return healthOk;
    if (k === 'smoke') return smokeOk;
    return undefined;
  };

  const getStepLoading = (k: StepKey) => {
    if (k === 'adapter') return adapterLoading;
    if (k === 'default_llm') return defaultLlmLoading;
    if (k === 'tenant') return initTenantLoading;
    if (k === 'strong_gate') return strongGateLoading;
    if (k === 'autosmoke') return autosmokeLoading;
    if (k === 'secrets') return secretsLoading || migrateSecretsLoading || rotateKeyLoading;
    if (k === 'doctor') return doctorLoading;
    if (k === 'health') return healthLoading;
    if (k === 'smoke') return smokeLoading;
    return false;
  };

  // After initial loads, auto-jump to first failed step (best-effort).
  useEffect(() => {
    if (!state && !doctor) return;
    const order: StepKey[] = ['adapter', 'default_llm', 'tenant', 'strong_gate', 'autosmoke', 'secrets', 'doctor', 'health', 'smoke'];
    for (const k of order) {
      const ok = getStepOk(k);
      if (ok === false) {
        setActiveStep(k);
        return;
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, doctor]);

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
        details: defaultLlmDetails || undefined,
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
        strict_tool_approval: strictToolApproval,
        require_approval: true,
        approval_request_id: approvalIdOverride || initTenantApprovalId || undefined,
        details: initTenantDetails || undefined,
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
      } else if (String(op) === 'onboarding:autosmoke') {
        setAutosmokeApprovalId(requestId);
        await submitAutosmoke(requestId);
      } else if (String(op) === 'onboarding:secrets_migrate') {
        setMigrateSecretsApprovalId(requestId);
        await submitMigrateSecrets(requestId);
      } else if (String(op) === 'onboarding:strong_gate') {
        setStrongGateApprovalId(requestId);
        // default to disabling strong gate when approving from list; user can re-run enable explicitly
        await submitStrongGate(false, requestId);
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

  const submitAutosmoke = async (approvalIdOverride?: string) => {
    setAutosmokeLoading(true);
    setAutosmokeResult(null);
    try {
      const res = await onboardingApi.setAutosmoke({
        enabled: autosmokeForm.enabled,
        enforce: autosmokeForm.enforce,
        webhook_url: autosmokeForm.webhook_url || undefined,
        require_approval: true,
        approval_request_id: approvalIdOverride || autosmokeApprovalId || undefined,
        details: autosmokeDetails || undefined,
      });
      setAutosmokeResult(res);
      if (res?.status === 'approval_required' && res?.approval_request_id) {
        const rid = String(res.approval_request_id);
        setAutosmokeApprovalId(rid);
        setApprovalWatch((prev) => ({ ...(prev || {}), [rid]: { op: 'autosmoke', created_at: Date.now() } }));
        setApprovalWatchLog((prev) => ({ ...(prev || {}), [rid]: '等待审批中：pending' }));
      }
      await refreshState();
      await refreshDoctor();
    } catch (e: any) {
      setAutosmokeResult({ status: 'error', error: e?.message || String(e) });
    } finally {
      setAutosmokeLoading(false);
    }
  };

  const submitMigrateSecrets = async (approvalIdOverride?: string) => {
    setMigrateSecretsLoading(true);
    setMigrateSecretsResult(null);
    try {
      const res = await onboardingApi.migrateSecrets({
        require_approval: true,
        approval_request_id: approvalIdOverride || migrateSecretsApprovalId || undefined,
        details: migrateSecretsDetails || undefined,
      });
      setMigrateSecretsResult(res);
      if (res?.status === 'approval_required' && res?.approval_request_id) {
        const rid = String(res.approval_request_id);
        setMigrateSecretsApprovalId(rid);
        setApprovalWatch((prev) => ({ ...(prev || {}), [rid]: { op: 'secrets_migrate', created_at: Date.now() } }));
        setApprovalWatchLog((prev) => ({ ...(prev || {}), [rid]: '等待审批中：pending' }));
      }
      await refreshSecrets();
    } catch (e: any) {
      setMigrateSecretsResult({ status: 'error', error: e?.message || String(e) });
    } finally {
      setMigrateSecretsLoading(false);
    }
  };

  const isStrongGateEnabled = useMemo(() => {
    const policy = defaultTenantPolicy?.policy;
    const tools = policy?.tool_policy?.approval_required_tools;
    if (!Array.isArray(tools)) return false;
    return tools.includes('*');
  }, [defaultTenantPolicy]);

  const submitStrongGate = async (enabled: boolean, approvalIdOverride?: string) => {
    setStrongGateLoading(true);
    setStrongGateResult(null);
    try {
      const res = await onboardingApi.setStrongGate({
        tenant_id: 'default',
        enabled,
        require_approval: true,
        approval_request_id: approvalIdOverride || strongGateApprovalId || undefined,
        details: strongGateDetails || undefined,
      });
      setStrongGateResult(res);
      if (res?.status === 'approval_required' && res?.approval_request_id) {
        const rid = String(res.approval_request_id);
        setStrongGateApprovalId(rid);
        setApprovalWatch((prev) => ({ ...(prev || {}), [rid]: { op: enabled ? 'strong_gate_on' : 'strong_gate_off', created_at: Date.now() } }));
        setApprovalWatchLog((prev) => ({ ...(prev || {}), [rid]: '等待审批中：pending' }));
      }
      await refreshDefaultTenantPolicy();
    } catch (e: any) {
      setStrongGateResult({ status: 'error', error: e?.message || String(e) });
    } finally {
      setStrongGateLoading(false);
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
          const ok = getStepOk(s.key);
          const loading = getStepLoading(s.key);
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

      {activeStep === 'default_llm' && (
        <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-4">
          <div className="text-gray-200 font-medium">Step：设为默认路由（全局，需审批）</div>
          <div className="text-xs text-gray-500">建议先完成 Adapter 配置；若触发审批会自动轮询并在批准后自动生效。</div>
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
            <div className="md:col-span-2">
              <div className="text-xs text-gray-500 mb-1">details（可选：审批说明/备注）</div>
              <textarea
                value={defaultLlmDetails}
                onChange={(e) => setDefaultLlmDetails(e.target.value)}
                placeholder="例如：将默认路由切到 deepseek-reasoner"
                className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
                rows={3}
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
            <button
              onClick={async () => {
                await refreshState();
              }}
              className="px-4 py-2 rounded-lg bg-dark-hover text-gray-200 border border-dark-border text-sm hover:bg-dark-border"
            >
              复检
            </button>
          </div>
          <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
            当前 default_llm：{JSON.stringify(state?.core_state?.default_llm || null, null, 2)}
          </pre>
          {defaultLlmResult && (
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
              {JSON.stringify(defaultLlmResult || {}, null, 2)}
            </pre>
          )}
        </div>
      )}

      {activeStep === 'tenant' && (
        <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-4">
          <div className="text-gray-200 font-medium">Step：初始化默认 Tenant/Policies（需审批）</div>
          <div>
            <div className="text-xs text-gray-500 mb-1">approval_request_id（可选：批准后填入再提交）</div>
            <input
              value={initTenantApprovalId}
              onChange={(e) => setInitTenantApprovalId(e.target.value)}
              placeholder="例如：apr-xxxx"
              className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
            />
          </div>
          <div>
            <div className="text-xs text-gray-500 mb-1">details（可选：审批说明/备注）</div>
            <textarea
              value={initTenantDetails}
              onChange={(e) => setInitTenantDetails(e.target.value)}
              placeholder="例如：初始化 default tenant 并写入最小 policy"
              className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
              rows={3}
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-300">
            <input type="checkbox" checked={strictToolApproval} onChange={(e) => setStrictToolApproval(e.target.checked)} />
            强门禁：所有工具执行都需审批（approval_required_tools=['*']）
          </label>
          <div className="flex items-center gap-2">
            <button
              disabled={initTenantLoading}
              onClick={initTenant}
              className="px-4 py-2 rounded-lg bg-primary text-white text-sm hover:opacity-90 disabled:opacity-60"
            >
              {initTenantLoading ? '提交中…' : '初始化 default tenant'}
            </button>
            <button
              onClick={async () => {
                await refreshDefaultTenantPolicy();
                await refreshState();
              }}
              className="px-4 py-2 rounded-lg bg-dark-hover text-gray-200 border border-dark-border text-sm hover:bg-dark-border"
            >
              复检
            </button>
          </div>
          <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
            {JSON.stringify(initTenantResult || state?.core_state?.tenants || {}, null, 2)}
          </pre>
        </div>
      )}

      {activeStep === 'strong_gate' && (
        <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="text-gray-200 font-medium">Step：强门禁开关（default tenant，需审批）</div>
            <button
              onClick={refreshDefaultTenantPolicy}
              className="px-3 py-1.5 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-xs"
            >
              {tenantPolicyLoading ? '刷新中…' : '刷新'}
            </button>
          </div>
          <div>
            <div className="text-xs text-gray-500 mb-1">details（可选：审批说明/备注）</div>
            <textarea
              value={strongGateDetails}
              onChange={(e) => setStrongGateDetails(e.target.value)}
              placeholder="例如：误开启强门禁，需要解除"
              className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
              rows={3}
            />
          </div>
          <div className="text-sm text-gray-500">当前状态：{isStrongGateEnabled ? '已开启（所有工具需审批）' : '未开启'}</div>
          <div className="flex items-center gap-2">
            <button
              disabled={strongGateLoading || isStrongGateEnabled}
              onClick={() => submitStrongGate(true)}
              className="px-4 py-2 rounded-lg bg-primary text-white text-sm hover:opacity-90 disabled:opacity-60"
            >
              启用强门禁
            </button>
            <button
              disabled={strongGateLoading || !isStrongGateEnabled}
              onClick={() => submitStrongGate(false)}
              className="px-4 py-2 rounded-lg bg-dark-hover text-gray-200 border border-dark-border text-sm hover:bg-dark-border disabled:opacity-60"
            >
              解除强门禁
            </button>
            <button
              onClick={async () => {
                await refreshDefaultTenantPolicy();
              }}
              className="px-4 py-2 rounded-lg bg-dark-hover text-gray-200 border border-dark-border text-sm hover:bg-dark-border"
            >
              复检
            </button>
          </div>
          {strongGateResult && (
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
              {JSON.stringify(strongGateResult || {}, null, 2)}
            </pre>
          )}
          {defaultTenantPolicy && (
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
              {JSON.stringify(defaultTenantPolicy || {}, null, 2)}
            </pre>
          )}
        </div>
      )}

      {activeStep === 'autosmoke' && (
        <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-4">
          <div className="text-gray-200 font-medium">Step：配置 autosmoke（配置中心，需审批）</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="flex items-center gap-2 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={autosmokeForm.enabled}
                onChange={(e) => setAutosmokeForm((p) => ({ ...p, enabled: e.target.checked }))}
              />
              启用 autosmoke
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={autosmokeForm.enforce}
                onChange={(e) => setAutosmokeForm((p) => ({ ...p, enforce: e.target.checked }))}
              />
              强门禁（未验证则阻止发布/启用）
            </label>
            <div className="md:col-span-2">
              <div className="text-xs text-gray-500 mb-1">Webhook URL（可选）</div>
              <input
                value={autosmokeForm.webhook_url}
                onChange={(e) => setAutosmokeForm((p) => ({ ...p, webhook_url: e.target.value }))}
                placeholder="https://hooks.slack.com/..."
                className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
              />
            </div>
            <div className="md:col-span-2">
              <div className="text-xs text-gray-500 mb-1">approval_request_id（可选）</div>
              <input
                value={autosmokeApprovalId}
                onChange={(e) => setAutosmokeApprovalId(e.target.value)}
                placeholder="例如：apr-xxxx"
                className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
              />
            </div>
            <div className="md:col-span-2">
              <div className="text-xs text-gray-500 mb-1">details（可选：审批说明/备注）</div>
              <textarea
                value={autosmokeDetails}
                onChange={(e) => setAutosmokeDetails(e.target.value)}
                placeholder="例如：开启 autosmoke 强门禁，确保发布前验证通过"
                className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
                rows={3}
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              disabled={autosmokeLoading}
              onClick={() => submitAutosmoke()}
              className="px-4 py-2 rounded-lg bg-primary text-white text-sm hover:opacity-90 disabled:opacity-60"
            >
              {autosmokeLoading ? '提交中…' : '提交审批/生效'}
            </button>
            <button
              onClick={async () => {
                await refreshState();
              }}
              className="px-4 py-2 rounded-lg bg-dark-hover text-gray-200 border border-dark-border text-sm hover:bg-dark-border"
            >
              复检
            </button>
          </div>
          <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
            {JSON.stringify(autosmokeResult || state?.core_state?.autosmoke || {}, null, 2)}
          </pre>
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

      {activeStep === 'secrets' && (
        <div className="space-y-4">
          <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-3">
            <div className="text-gray-200 font-medium">密钥存储状态</div>
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
            <div className="flex items-center justify-between">
              <div className="text-gray-200 font-medium">历史明文密钥迁移（需审批）</div>
              <button
                onClick={refreshSecrets}
                className="px-3 py-1.5 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-xs"
              >
                {secretsLoading ? '刷新中…' : '刷新'}
              </button>
            </div>
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
              {JSON.stringify(secretsStatus || {}, null, 2)}
            </pre>
            <div>
              <div className="text-xs text-gray-500 mb-1">approval_request_id（可选）</div>
              <input
                value={migrateSecretsApprovalId}
                onChange={(e) => setMigrateSecretsApprovalId(e.target.value)}
                placeholder="例如：apr-xxxx"
                className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
              />
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">details（可选：审批说明/备注）</div>
              <textarea
                value={migrateSecretsDetails}
                onChange={(e) => setMigrateSecretsDetails(e.target.value)}
                placeholder="例如：将历史明文 key 迁移为加密存储"
                className="w-full px-3 py-2 rounded-lg bg-dark-hover border border-dark-border text-gray-200 text-sm"
                rows={3}
              />
            </div>
            <div className="flex items-center gap-2">
              <button
                disabled={migrateSecretsLoading}
                onClick={() => submitMigrateSecrets()}
                className="px-4 py-2 rounded-lg bg-primary text-white text-sm hover:opacity-90 disabled:opacity-60"
              >
                {migrateSecretsLoading ? '提交中…' : '提交审批/迁移'}
              </button>
              <button
                onClick={async () => {
                  await refreshSecrets();
                  await refreshState();
                }}
                className="px-4 py-2 rounded-lg bg-dark-hover text-gray-200 border border-dark-border text-sm hover:bg-dark-border"
              >
                复检
              </button>
            </div>
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
              {JSON.stringify(migrateSecretsResult || {}, null, 2)}
            </pre>
            <div className="text-xs text-gray-500">
              说明：需要先配置 AIPLAT_SECRET_KEY；迁移会把 adapters.api_key（明文）加密到 api_key_enc 并清空 api_key。
            </div>
          </div>

          <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-4">
            <div className="text-gray-200 font-medium">轮换 Adapter API Key（不回显旧 key）</div>
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
              <button
                onClick={async () => {
                  await refreshState();
                }}
                className="px-4 py-2 rounded-lg bg-dark-hover text-gray-200 border border-dark-border text-sm hover:bg-dark-border"
              >
                复检
              </button>
              {rotateKeyResult?.status === 'rotated' && <div className="text-sm text-gray-500">已更新</div>}
              {rotateKeyResult?.status === 'error' && <div className="text-sm text-red-400">失败：{rotateKeyResult.error}</div>}
            </div>
          </div>
        </div>
      )}

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

      {activeStep === 'doctor' && (
        <div className="bg-dark-bg border border-dark-border rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-gray-200 font-medium">配置检查（Doctor）</div>
            <div className="flex items-center gap-2">
              <button
                onClick={async () => {
                  await refreshDoctor();
                  await refreshState();
                  await refreshSecrets();
                  await refreshDefaultTenantPolicy();
                }}
                className="px-3 py-1.5 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-xs"
              >
                {doctorLoading ? '刷新中…' : '刷新/复检'}
              </button>
            </div>
          </div>
          <ActionableFixes actions={doctor?.actions} recommendations={doctor?.recommendations} onAfterAction={refreshDoctor} />
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
          <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
            {JSON.stringify(doctor || {}, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
};

export default Onboarding;
