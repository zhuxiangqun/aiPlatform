import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { diagnosticsApi } from '../../services';
import { Card, CardContent, CardHeader, Badge, Button } from '../../components/ui';
import { ActionableFixes } from '../../components/common/ActionableFixes';
import { ArrowLeft, Copy, ChevronDown, ChevronRight, Shield, Cpu, Layers, Activity, CheckCircle, AlertTriangle, XCircle, Info } from 'lucide-react';

const LAYER_LABELS: Record<string, string> = { infra: '基础设施', core: 'AI引擎', platform: '平台服务', app: '应用接入' };
const LAYER_ICONS: Record<string, any> = { infra: Cpu, core: Layers, platform: Shield, app: Activity };

const Doctor: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [runningSmoke, setRunningSmoke] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [showActions, setShowActions] = useState(false);

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
    return () => { mounted = false; };
  }, []);

  const jsonText = useMemo(() => JSON.stringify(data || {}, null, 2), [data]);

  const copyReport = async () => {
    try { await navigator.clipboard.writeText(jsonText); } catch (e) { console.error(e); }
  };

  const downloadReport = () => {
    const blob = new Blob([jsonText], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `doctor-report-${Date.now()}.json`; a.click();
    URL.revokeObjectURL(url);
  };

  const runSmoke = async () => {
    setRunningSmoke(true);
    try { await diagnosticsApi.runE2ESmoke({}); await refresh(); }
    catch (e) { console.error(e); }
    finally { setRunningSmoke(false); }
  };

  // ── Derived data ──
  const health = data?.health || {};
  const layers = ['infra', 'core', 'platform', 'app'] as const;
  const layerStatuses = layers.map(l => ({ key: l, status: health[l]?.status || 'unknown', data: health[l] }));
  const unhealthyCount = layerStatuses.filter(l => l.status !== 'healthy').length;

  const layerChecks = (l: string) => {
    const checks = health[l]?.checks || [];
    const healthy = checks.filter((c: any) => c.status === 'healthy').length;
    return { total: checks.length, healthy };
  };

  const infraDigest = () => {
    const h = health.infra;
    if (!h) return null;
    const models = h.checks?.find((c: any) => c.component === 'model')?.details?.total_models || 0;
    const services = h.checks?.find((c: any) => c.component === 'service')?.details?.running_services || 0;
    const alerts = h.checks?.find((c: any) => c.component === 'monitoring')?.details?.active_alerts || 0;
    return `${models} 模型 · ${services} 服务 · ${alerts} 告警`;
  };

  const coreDigest = () => {
    const ck = health.core?.checks?.[0]?.details?.checks || {};
    const ok = Object.entries(ck).filter(([_, v]: [string, any]) => v?.ok).length;
    return `${ok}/${Object.keys(ck).length} 检查通过`;
  };

  const recs = (data?.recommendations || []) as any[];
  const issues = recs.map((r: any) => ({
    severity: r.severity || 'info',
    code: r.code || '',
    message: r.message || '',
    action: r.actions ? Object.keys(r.actions)[0] : null,
    actionData: r.actions ? Object.values(r.actions)[0] : null,
  }));

  const getStatusIcon = (status: string) => {
    if (status === 'healthy') return <CheckCircle size={16} className="text-green-400" />;
    if (status === 'degraded') return <AlertTriangle size={16} className="text-yellow-400" />;
    return <XCircle size={16} className="text-red-400" />;
  };

  const getBannerColor = () => {
    if (unhealthyCount === 0) return 'from-green-900/30 to-green-900/10 border-green-500/30';
    if (unhealthyCount <= 2) return 'from-yellow-900/30 to-yellow-900/10 border-yellow-500/30';
    return 'from-red-900/30 to-red-900/10 border-red-500/30';
  };

  return (
    <div className="space-y-6">
      {/* ═══ Summary Banner ═══ */}
      <div className={`bg-gradient-to-br ${getBannerColor()} border rounded-xl p-5`}>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-semibold text-gray-200">系统诊断 Doctor</h1>
            <p className="text-sm text-gray-400 mt-1">
              {unhealthyCount === 0
                ? '✅ 四层架构全部健康，系统运行正常'
                : `⚠️ ${unhealthyCount} 层状态异常，建议查看详情`}
            </p>
            <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
              <span>{data?.adapters?.total || 0} 个适配器</span>
              <span>{data?.prompts?.templates?.total || 0} 个 Prompt 模板</span>
              <span>autosmoke: {data?.autosmoke?.enabled ? '已开启' : '未开启'}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Link to="/onboarding" className="px-3 py-2 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-sm">去初始化向导</Link>
            <button onClick={runSmoke} disabled={runningSmoke} className="px-3 py-2 rounded-lg bg-primary text-white hover:opacity-90 disabled:opacity-60 text-sm transition-colors">
              {runningSmoke ? '运行中…' : '一键跑 Smoke'}
            </button>
            <button onClick={copyReport} className="px-3 py-2 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-sm">复制报告</button>
            <button onClick={downloadReport} className="px-3 py-2 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-sm">下载 JSON</button>
            <button onClick={refresh} className="px-3 py-2 rounded-lg bg-dark-hover text-gray-200 hover:bg-dark-border transition-colors text-sm">刷新</button>
          </div>
        </div>
      </div>

      <Link to="/diagnostics" className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 transition-colors mb-4">
        <ArrowLeft className="w-3 h-3" />返回诊断中心
      </Link>

      {error && <div className="text-sm text-error bg-error-light border border-dark-border rounded-lg p-3">{error}</div>}

      {/* ═══ Layer Health Cards ═══ */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {layerStatuses.map(({ key, status }) => {
          const Icon = LAYER_ICONS[key] || Activity;
          const ck = layerChecks(key);
          const digest = key === 'infra' ? infraDigest() : key === 'core' ? coreDigest() : null;
          return (
            <Card key={key} className={status === 'healthy' ? 'border-green-500/30' : status === 'degraded' ? 'border-yellow-500/30' : 'border-red-500/30'}>
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Icon size={18} className={status === 'healthy' ? 'text-green-400' : status === 'degraded' ? 'text-yellow-400' : 'text-red-400'} />
                    <span className="text-sm font-medium text-gray-200">{LAYER_LABELS[key] || key}</span>
                  </div>
                  {getStatusIcon(status)}
                </div>
                <div className="space-y-1">
                  <div className="text-xs text-gray-500">
                    <span className={status === 'healthy' ? 'text-green-400' : status === 'degraded' ? 'text-yellow-400' : 'text-red-400'}>
                      {ck.healthy}/{ck.total} 检查正常
                    </span>
                  </div>
                  {digest && <div className="text-xs text-gray-500">{digest}</div>}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* ═══ Issues & Recommendations ═══ */}
      {issues.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">诊断建议</div>
              <Badge variant={issues.filter(i => i.severity === 'error').length > 0 ? 'error' : 'warning'}>
                {issues.length} 条
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {issues.map((iss: any, i: number) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-dark-hover border border-dark-border">
                  <span className="mt-0.5">
                    {iss.severity === 'error' ? <XCircle size={16} className="text-red-400" />
                      : iss.severity === 'warn' ? <AlertTriangle size={16} className="text-yellow-400" />
                        : <Info size={16} className="text-blue-400" />}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-gray-200">{iss.message}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{iss.code}</div>
                  </div>
                </div>
              ))}
            </div>
            {issues.length > 3 && (
              <div className="mt-3">
                <ActionableFixes actions={data?.actions} recommendations={data?.recommendations} onAfterAction={refresh} />
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ═══ 自学习产出 ═══ */}
      {data?.learning && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">自学习产出</div>
              <div className="flex items-center gap-2">
                {(data.learning.crystallized > 0) && <Badge variant="success">{data.learning.crystallized} 晶体化</Badge>}
                {(data.learning.evolution?.total_evolutions > 0) && <Badge variant="info">{data.learning.evolution.total_evolutions} 进化</Badge>}
                {(data.learning.ab_scores?.total_evals > 0) && <Badge variant="warning">{data.learning.ab_scores.templates} 模板A/B</Badge>}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Task Skills */}
              <div className="p-3 rounded-lg bg-dark-hover border border-dark-border">
                <div className="text-xs text-gray-500 mb-1">流水线晶体化</div>
                <div className="text-sm text-gray-200">{data.learning.crystallized || 0} 个可复用 TaskSkill</div>
                <div className="text-xs text-gray-500 mt-1">
                  {data.learning.crystallized > 0
                    ? '成功流水线自动固化为技能，下次可直接复用'
                    : '尚未有流水线完成执行'}
                </div>
              </div>
              {/* Evolution */}
              <div className="p-3 rounded-lg bg-dark-hover border border-dark-border">
                <div className="text-xs text-gray-500 mb-1">技能进化</div>
                <div className="text-sm text-gray-200">
                  {data.learning.evolution?.total_evolutions || 0} 次进化
                  {data.learning.evolution?.total_rollbacks > 0 && (
                    <span className="text-amber-400"> · {data.learning.evolution.total_rollbacks} 次回滚</span>
                  )}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  {data.learning.evolution?.total_evolutions > 0
                    ? '失败触发修复→新版本→A/B对比→自动回滚退化版本'
                    : '尚未触发技能进化（需流水线执行）'}
                </div>
              </div>
              {/* A/B */}
              <div className="p-3 rounded-lg bg-dark-hover border border-dark-border">
                <div className="text-xs text-gray-500 mb-1">Prompt A/B 优化</div>
                <div className="text-sm text-gray-200">
                  {data.learning.ab_scores?.total_evals > 0
                    ? `${data.learning.ab_scores.total_evals} 次评分 · ${data.learning.ab_scores.templates} 个模板 · 均分 ${data.learning.ab_scores.avg_score}`
                    : '尚无评分数据'}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  {data.learning.ab_scores?.total_evals > 0
                    ? '评分自动收集，流水线完成时权重自动向高分版本收敛'
                    : '需有 rollout 配置的 Prompt 模板参与流水线'}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ═══ Quick Actions (collapsible) ═══ */}
      {data?.actions && Object.keys(data.actions).length > 0 && (
        <Card>
          <CardHeader>
            <button onClick={() => setShowActions(!showActions)} className="flex items-center justify-between w-full">
              <div className="text-sm font-semibold text-gray-200">快速操作</div>
              {showActions ? <ChevronDown size={16} className="text-gray-400" /> : <ChevronRight size={16} className="text-gray-400" />}
            </button>
          </CardHeader>
          {showActions && (
            <CardContent>
              <ActionableFixes actions={data.actions} recommendations={data.recommendations} onAfterAction={refresh} />
            </CardContent>
          )}
        </Card>
      )}

      {/* ═══ Configuration Overview (collapsible) ═══ */}
      <Card>
        <CardHeader>
          <button onClick={() => setShowConfig(!showConfig)} className="flex items-center justify-between w-full">
            <div className="text-sm font-semibold text-gray-200">配置概览</div>
            {showConfig ? <ChevronDown size={16} className="text-gray-400" /> : <ChevronRight size={16} className="text-gray-400" />}
          </button>
        </CardHeader>
        {showConfig && (
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div className="text-xs text-gray-500 mb-1">适配器</div>
                <div className="text-sm text-gray-200">{data?.adapters?.total || 0} 个</div>
                {(data?.adapters?.adapters || []).map((a: any, i: number) => (
                  <div key={i} className="text-xs text-gray-400 mt-0.5">{a.name} ({a.provider}) — {a.status}</div>
                ))}
              </div>
              <div>
                <div className="text-xs text-gray-500 mb-1">Prompt 模板</div>
                <div className="text-sm text-gray-200">{data?.prompts?.templates?.total || 0} 个模板</div>
              </div>
              <div>
                <div className="text-xs text-gray-500 mb-1">Context 引擎</div>
                <div className="text-sm text-gray-200">{data?.context?.context_engine || '-'}</div>
                <div className="text-xs text-gray-400">注入检测: {data?.context?.security?.has_injection_detection ? '✅ 已启用' : '❌ 未启用'}</div>
                <div className="text-xs text-gray-400">跨会话检索: {data?.context?.enable_session_search ? '已开启' : '未开启'}</div>
              </div>
              <div>
                <div className="text-xs text-gray-500 mb-1">Autosmoke</div>
                <div className="text-sm text-gray-200">{data?.autosmoke?.enabled ? '✅ 已启用' : '未启用'}</div>
                <div className="text-xs text-gray-400">强制门禁: {data?.autosmoke?.enforce ? '是' : '否'}</div>
                <div className="text-xs text-gray-400">去重窗口: {data?.autosmoke?.dedup_seconds || '-'}s</div>
              </div>
              <div>
                <div className="text-xs text-gray-500 mb-1">Strong Gate</div>
                <div className="text-sm text-gray-200">{data?.strong_gate?.enabled ? '⚠️ 已启用' : '未启用'}</div>
              </div>
              <div>
                <div className="text-xs text-gray-500 mb-1">Secrets</div>
                <div className="text-sm text-gray-200">{data?.secrets?.total || 0} 个</div>
                <div className="text-xs text-gray-400">加密: {data?.secrets?.encrypted || 0} · 明文: {data?.secrets?.plaintext || 0}</div>
              </div>
            </div>
          </CardContent>
        )}
      </Card>

      {/* ═══ Technical Details (collapsible, hidden by default) ═══ */}
      <Card>
        <CardHeader>
          <button onClick={() => setShowRaw(!showRaw)} className="flex items-center justify-between w-full">
            <div className="text-sm font-semibold text-gray-200">技术细节（原始数据）</div>
            {showRaw ? <ChevronDown size={16} className="text-gray-400" /> : <ChevronRight size={16} className="text-gray-400" />}
          </button>
        </CardHeader>
        {showRaw && (
          <CardContent>
            <Button variant="secondary" icon={<Copy size={14} />} onClick={copyReport} className="mb-3">复制报告</Button>
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto max-h-[600px]">
              {jsonText}
            </pre>
          </CardContent>
        )}
      </Card>
    </div>
  );
};

export default Doctor;
