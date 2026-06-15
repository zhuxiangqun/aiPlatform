import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { overviewApi } from '../../services';
import { RefreshCw, Server, Cpu, Bot, Globe, MessageSquare, Database, Zap, Brain, AlertTriangle } from 'lucide-react';
import DiagnosticTrendChart from './DiagnosticTrendChart';

const SystemOverview: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [diagSummary, setDiagSummary] = useState<any>(null);

  const fetchData = async (force = false) => {
    setLoading(true);
    try {
      const overview = await overviewApi.getOverview(force);
      try {
        overview.codebase_stats = await overviewApi.getKnowledgeGraphStats();
      } catch { }
      setData(overview);
    } catch { }
    finally { setLoading(false); }
  };

  const fetchHistory = async () => {
    try {
      const h = await overviewApi.getDiagnosticsHistory();
      setHistory(h.history || []);
    } catch { }
  };

  const fetchSummary = async () => {
    try {
      const ds = await overviewApi.getDiagnosticsSummary();
      setDiagSummary(ds);
    } catch { }
  };

  useEffect(() => {
    fetchData(false);
    fetchHistory();
    fetchSummary();
  }, []);

  const infra = data?.infra || {};
  const core = data?.core || {};
  const platform = data?.platform || {};
  const app = data?.app || {};

  const statusColor = (status: string) =>
    status === 'healthy' ? 'text-green-400' : status === 'degraded' ? 'text-yellow-400' : 'text-red-400';
  const statusBg = (status: string) =>
    status === 'healthy' ? 'bg-green-900/20 border-green-500/20' : status === 'degraded' ? 'bg-yellow-900/20 border-yellow-500/20' : 'bg-red-900/20 border-red-500/20';
  const statusLabel = (status: string) =>
    status === 'healthy' ? '健康' : status === 'degraded' ? '部分可用' : '异常';
  const serversUp = () => Object.values(infra.servers || {}).filter((v: any) => v === 'up').length;
  const serversTotal = () => Object.keys(infra.servers || {}).length;

  const MetricRow = ({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) => (
    <div className="flex justify-between">
      <span className="text-gray-500">{label}</span>
      <div className="text-right">
        <span className="text-gray-300">{value ?? '—'}</span>
        {sub && <div className="text-gray-500 text-[10px]">{sub}</div>}
      </div>
    </div>
  );

  const StorageStatus = ({ item }: { item: any }) => {
    if (!item) return null;
    if (item.error) return <span className="text-red-400">❌</span>;
    if (item.status === 'disabled') return <span className="text-yellow-400">⚠️</span>;
    if (item.note) return <span className="text-gray-500">—</span>;
    return <span className="text-green-400">✅</span>;
  };

  const PillTag = ({ label, count, ok }: { label: string; count: number; ok?: boolean }) => (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] ${
      ok ? 'bg-green-900/20 text-green-300 border border-green-500/20' : 'bg-dark-bg text-gray-400 border border-dark-border'
    }`}>
      {label} <span className="text-gray-300">{count}</span>
    </span>
  );

  return (
    <div className="space-y-4 p-4">
       <div className="flex items-center justify-between">
         <div>
           <h1 className="text-lg font-semibold text-gray-100">系统概览</h1>
            <p className="text-xs text-gray-500 mt-0.5">
              四层架构运行状态 · 手动刷新
              <span className="text-gray-600 ml-2">「健康」= 服务存活，详细评分见诊断中心</span>
             {diagSummary?.last_run && (
               <span className="text-gray-600"> · 诊断 {diagSummary.last_run}</span>
             )}
           </p>
         </div>
         <div className="flex items-center gap-3">
           {diagSummary && (diagSummary.fail > 0 || diagSummary.warn > 0) && (
              <a href="/diagnostics" className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium bg-red-900/20 text-red-300 hover:bg-red-900/30 transition-colors border border-red-500/20">
               <AlertTriangle className="w-3 h-3" />
               {diagSummary.fail > 0 && <span>{diagSummary.fail} 项失败</span>}
               {diagSummary.fail > 0 && diagSummary.warn > 0 && <span>·</span>}
               {diagSummary.warn > 0 && <span>{diagSummary.warn} 项警告</span>}
             </a>
           )}
           {diagSummary && diagSummary.fail === 0 && diagSummary.warn === 0 && diagSummary.pass > 0 && (
             <span className="text-[10px] text-green-400 bg-green-900/20 px-2 py-1 rounded border border-green-500/20">✅ 全部通过</span>
           )}
           <Button variant="ghost" size="sm" onClick={() => { fetchData(true); fetchHistory(); fetchSummary(); }} loading={loading}>
           <RefreshCw className="w-3 h-3 mr-1" />刷新
         </Button>
         </div>
        </div>

      {/* Compact status summary — details in Diagnostics Center */}
      {data && (
        <div className="flex items-center gap-3 text-xs text-gray-400 mb-2">
          {data.codebase_stats && (
            <span className={data.codebase_stats.health_score >= 75 ? 'text-green-400' : data.codebase_stats.health_score >= 50 ? 'text-yellow-400' : 'text-red-400'}>
              架构 {(data.codebase_stats.health_score ?? '?')}/{data.codebase_stats.health_grade ?? '?'} ({(data.codebase_stats.cycles ?? 0)} 环)
            </span>
          )}
          {core.governance && !core.governance.error && (
            <span className={core.governance.has_trusted_keys ? 'text-green-400' : 'text-red-400'}>
              治理: {core.governance.has_trusted_keys ? '✅' : '⚠️ 未配置'}
            </span>
          )}
          {core.skills?.lint && (
            <span className={(core.skills.lint.errors ?? 0) > 0 ? 'text-red-400' : 'text-green-400'}>
              Lint: {(core.skills.lint.errors ?? 0) > 0 ? '⚠️' : '✅'}
            </span>
          )}
          <span className="text-gray-600 text-[10px]">详查→诊断中心</span>
        </div>
      )}

      {/* ═══ DIAGNOSTIC TREND CHART ═══ */}
      <DiagnosticTrendChart history={history} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* ═══ INFRA — Layer 0 ═══ */}
        <Card className={statusBg(infra.status || 'healthy')}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
                <Server className="w-4 h-4 text-cyan-400" />
                基础设施层 <span className="text-[10px] text-gray-500">Layer 0</span>
                <span className="text-[9px] text-gray-600 ml-2">模型 · 服务 · 存储</span>
              </div>
              <span className={`text-xs font-medium ${statusColor(infra.status || 'healthy')}`}>
                {statusLabel(infra.status || 'healthy')}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-xs">
              {/* Models */}
              <div className="pb-1.5 border-b border-dark-border/50">
                <div className="flex items-center gap-1.5 text-gray-400 font-medium mb-1">
                  <Zap className="w-3 h-3" />模型
                </div>
                <MetricRow
                  label="可用"
                  value={<>{infra.models?.available ?? '—'}<span className="text-gray-500">/{infra.models?.total ?? '—'}</span></>}
                  sub={infra.models?.by_type && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      <PillTag label="chat" count={infra.models.by_type.chat ?? 0} ok={infra.models.by_type.chat > 0} />
                      <PillTag label="embed" count={infra.models.by_type.embedding ?? 0} ok={infra.models.by_type.embedding > 0} />
                      <PillTag label="rerank" count={infra.models.by_type.reranker ?? 0} ok={infra.models.by_type.reranker > 0} />
                      <PillTag label="audio" count={infra.models.by_type.audio ?? 0} ok={infra.models.by_type.audio > 0} />
                      <PillTag label="ocr" count={infra.models.by_type.ocr ?? 0} ok={infra.models.by_type.ocr > 0} />
                    </div>
                  )}
                />
                {infra.models?.providers?.length > 0 && (
                  <div className="text-gray-500 mt-1">providers: {infra.models.providers.join(', ')}</div>
                )}
              </div>

              {/* LLM */}
              {!infra.llm?.error && (
                <div className="pb-1.5 border-b border-dark-border/50">
                  <div className="flex items-center gap-1.5 text-gray-400 font-medium mb-1">
                    <Brain className="w-3 h-3" />LLM 调用 (24h)
                  </div>
                  <MetricRow label="请求" value={infra.llm?.requests_24h != null ? `${infra.llm.requests_24h.toLocaleString()} 次` : '—'} />
                  <MetricRow label="成功率" value={infra.llm?.success_rate != null ? `${infra.llm.success_rate}%` : '—'} />
                  <MetricRow label="平均延迟" value={infra.llm?.avg_latency_ms ? `${infra.llm.avg_latency_ms}ms` : '—'} />
                  <MetricRow label="Token 消耗" value={infra.llm?.total_tokens_24h != null ? `${(infra.llm.total_tokens_24h / 1000).toFixed(1)}K` : '—'} />
                  {infra.llm?.error_count_24h > 0 && (
                    <MetricRow label="错误" value={<span className="text-red-400">{infra.llm.error_count_24h} 次</span>} />
                  )}
                  {infra.llm?.hourly_trend && infra.llm.hourly_trend.length > 0 && (
                    <div className="mt-1.5 flex items-end gap-0.5 h-8">
                      {infra.llm.hourly_trend.map((h: any) => {
                        const max = Math.max(...infra.llm.hourly_trend.map((x: any) => x.count), 1);
                        const pct = (h.count / max) * 100;
                        const color = h.latency_ms > 2000 ? 'bg-red-500/60' : h.latency_ms > 1000 ? 'bg-yellow-500/60' : 'bg-green-500/50';
                         return (
                           <div key={h.hour} className="flex-1 relative group" title={`${h.hour}h: ${h.count} req, ${h.latency_ms}ms`}>
                             <div className={`w-full rounded-t-sm ${color}`} style={{ height: `${Math.max(pct, 5)}%` }} />
                           </div>
                         );
                       })}
                     </div>
                   )}
                 </div>
               )}

              {/* Servers */}
              <div className="pb-1.5 border-b border-dark-border/50">
                <MetricRow
                  label="服务"
                  value={<>{serversUp()}/{serversTotal()} 在线</>}
                  sub={
                    <div className="flex flex-wrap gap-1 mt-1">
                      {Object.entries(infra.servers || {}).map(([name, status]: [string, any]) => (
                        <span key={name} className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] ${
                          status === 'up' ? 'bg-green-900/20 text-green-300 border border-green-500/20' : 'bg-red-900/20 text-red-300 border border-red-500/20'
                        }`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${status === 'up' ? 'bg-green-400' : 'bg-red-400'}`} />
                          {name}
                        </span>
                      ))}
                    </div>
                  }
                />
              </div>

              {/* Storage */}
              <div>
                <div className="flex items-center gap-1.5 text-gray-400 font-medium mb-1">
                  <Database className="w-3 h-3" />存储
                </div>
                {infra.storage?.database && (
                  <div className="text-gray-500">
                    DB: <StorageStatus item={infra.storage.database} />
                    {infra.storage.database.connections ? ` (${infra.storage.database.connections} conn)` : ''}
                  </div>
                )}
                {infra.storage?.vector && (
                  <div className="text-gray-500">
                    Vector: <StorageStatus item={infra.storage.vector} />
                    {infra.storage.vector.collections != null ? ` (${infra.storage.vector.collections} coll)` : ''}
                  </div>
                )}
                {infra.storage?.cache && (
                  <div className="text-gray-500">
                    Cache: <StorageStatus item={infra.storage.cache} />
                    {infra.storage.cache.hits != null ? ` (${infra.storage.cache.hits} hits)` : ''}
                  </div>
                )}
              </div>

              {infra.models?.error && <div className="text-red-400 mt-1">{infra.models.error}</div>}
            </div>
            <details className="bg-dark-bg border border-dark-border rounded px-2 py-1 text-[10px] text-gray-500 cursor-pointer group mt-2">
              <summary className="text-gray-500 hover:text-gray-300 select-none">📖 表头说明</summary>
              <div className="mt-1 text-gray-600">⚠️ 表示连接异常 · 检查对应端口是否在监听(8000-8004) · 模型可用=已部署且在线 · Chat/Embed/Rerank/Audio/OCR各司其职</div>
            </details>
          </CardContent>
        </Card>

        {/* ═══ CORE — Layer 1 ═══ */}
        <Card className="bg-dark-card">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
                <Cpu className="w-4 h-4 text-violet-400" />
                AI 中台 <span className="text-[10px] text-gray-500">Layer 1</span>
                <span className="text-[9px] text-gray-600 ml-2">Agent · Skill · Tool · MCP</span>
              </div>
              <span className={`text-xs font-medium ${statusColor(core.status || 'healthy')}`}>
                {statusLabel(core.status || 'healthy')}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-xs">
              {/* Agents */}
              <div className="pb-1.5 border-b border-dark-border/50">
                <div className="flex items-center gap-1.5 text-gray-400 font-medium mb-1">
                  <Bot className="w-3 h-3" />Agent
                </div>
                <MetricRow
                  label="总计"
                  value={core.agents?.total ?? '—'}
                  sub={<>引擎 {core.agents?.engine ?? 0} · 工作区 {core.agents?.workspace ?? 0}</>}
                />
                {core.agents?.by_type && Object.keys(core.agents.by_type).length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {Object.entries(core.agents.by_type).map(([type, count]: [string, any]) => (
                      <PillTag key={type} label={type} count={count as number} />
                    ))}
                  </div>
                )}
              </div>

              {/* Skills & Lint */}
              <div className="pb-1.5 border-b border-dark-border/50">
                <div className="flex justify-between">
                  <span className="text-gray-500">Skill</span>
                  <span className="text-gray-300">
                    {core.skills?.total ?? '—'}
                    {core.skills?.lint && (
                      <span className={core.skills.lint.errors > 0 ? 'text-red-400 ml-1' : 'text-green-400 ml-1'}>
                        {core.skills.lint.errors > 0 ? '⚠️' : '✅'}
                      </span>
                    )}
                  </span>
                </div>
              </div>

              {/* Tools / MCP / Workflows */}
              <div className="pb-1.5 border-b border-dark-border/50 space-y-1.5">
                <MetricRow label="Tool" value={core.tools ?? '—'} />
                {typeof core.mcp_servers === 'object' ? (
                    <MetricRow
                      label="MCP 服务器"
                      value={
                        <span>
                          {core.mcp_servers.total ?? '—'}
                          {core.mcp_servers.alive != null && (
                            <span className={core.mcp_servers.alive ? 'text-green-400 ml-1' : 'text-red-400 ml-1'}>
                              ({core.mcp_servers.alive ? '在线' : '断连'})
                            </span>
                          )}
                        </span>
                      }
                    />
                  ) : (
                    <MetricRow label="MCP 服务器" value={core.mcp_servers ?? '—'} />
                  )}
                <MetricRow label="Workflow" value={core.workflows ?? '—'} />
              </div>

              {/* Pipeline */}
              <div className="pb-1.5 border-b border-dark-border/50">
                <MetricRow
                  label="Pipeline"
                  value={<>{core.pipeline?.active ?? '—'} 活跃</>}
                  sub={core.pipeline?.completed != null ? `已完成 ${core.pipeline.completed}` : undefined}
                />
              </div>

              {/* Memory & Syscalls */}
              <div className="pb-1.5 border-b border-dark-border/50">
                <div className="flex justify-between">
                  <span className="text-gray-500">Memory</span>
                  <span className="text-gray-300 text-[10px]">
                    {core.memory?.working_tokens != null ? `${core.memory.working_tokens}tok` : '—'}
                    {' · '}
                    {core.memory?.episodic_count != null ? `ep${core.memory.episodic_count}` : '—'}
                    {' · '}
                    {core.memory?.semantic_count != null ? `sm${core.memory.semantic_count}` : '—'}
                  </span>
                </div>
                <div className="flex justify-between mt-0.5">
                  <span className="text-gray-500">Syscall (1h)</span>
                  <span className="text-gray-300 text-[10px]">
                    llm:{core.syscalls?.llm_1h ?? '—'}
                    {' '}tool:{core.syscalls?.tool_1h ?? '—'}
                    {' '}skill:{core.syscalls?.skill_1h ?? '—'}
                  </span>
                </div>
              </div>

              {/* Governance */}
              {core.governance && !core.governance.error && (
                <div className="pb-1.5 border-b border-dark-border/50">
                  <div className="flex justify-between">
                    <span className="text-gray-500">治理</span>
                    <span className={core.governance.has_trusted_keys ? 'text-green-400' : 'text-red-400'}>
                      {core.governance.has_trusted_keys ? '✅' : '⚠️ 未配置'}
                    </span>
                  </div>
                </div>
              )}

              {/* Capability Health */}
              <div>
                <div className="flex justify-between">
                  <span className="text-gray-500">能力健康</span>
                  <span className="text-gray-300">
                    {core.capability_health?.score != null
                      ? <>{core.capability_health.score}<span className="text-gray-500">/{core.capability_health.grade}</span></>
                      : '—'}
                  </span>
                </div>
              </div>
            </div>
            <details className="bg-dark-bg border border-dark-border rounded px-2 py-1 text-[10px] text-gray-500 cursor-pointer group mt-2">
              <summary className="text-gray-500 hover:text-gray-300 select-none">📖 表头说明</summary>
              <div className="mt-1 text-gray-600">Lint健康: E=错误(必须修) W=警告(建议修) · 能力健康=Agent/Skill/Tool配置质量 · Syscall统计近1h调用 · Memory=三层记忆</div>
            </details>
          </CardContent>
        </Card>

        {/* ═══ PLATFORM — Layer 2 ═══ */}
        <Card className="bg-dark-card">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
                <Globe className="w-4 h-4 text-emerald-400" />
                平台服务层 <span className="text-[10px] text-gray-500">Layer 2</span>
                <span className="text-[9px] text-gray-600 ml-2">网关 · 用户 · 知识库</span>
              </div>
              <span className={`text-xs font-medium ${statusColor(platform.status || 'healthy')}`}>
                {statusLabel(platform.status || 'healthy')}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-xs">
              {/* Gateway & Users & Tenants */}
              <div className="pb-1.5 border-b border-dark-border/50 space-y-1.5">
                <MetricRow label="网关路由" value={platform.gateway?.routes ?? '—'} />
                <MetricRow label="用户" value={platform.users?.count ?? '—'} />
                <MetricRow label="租户" value={platform.tenants?.count ?? '—'} />
              </div>

              {/* Knowledge Base */}
              <div className="pb-1.5 border-b border-dark-border/50">
                <div className="flex items-center gap-1.5 text-gray-400 font-medium mb-1">
                  <Database className="w-3 h-3" />知识库
                </div>
                <div className="flex flex-wrap gap-x-3 text-gray-300">
                  <span>集合 <span className="text-gray-300">{platform.knowledge_base?.collections ?? '—'}</span></span>
                  <span>文档 <span className="text-gray-300">{platform.knowledge_base?.documents ?? '—'}</span></span>
                  <span>元素 <span className="text-gray-300">{platform.knowledge_base?.elements ?? '—'}</span></span>
                  <span>嵌入 <span className="text-gray-300">{platform.knowledge_base?.embeddings ?? '—'}</span></span>
                </div>
              </div>

              {/* Builder & Approvals */}
              <div className="pb-1.5 border-b border-dark-border/50 space-y-1.5">
                <MetricRow label="Builder 项目" value={platform.builder?.projects ?? '—'} />
                <MetricRow label="待审批" value={platform.approvals?.pending ?? '—'} />
              </div>

              {/* Sessions */}
              <div>
                <MetricRow
                  label="会话"
                  value={<>{platform.sessions?.active ?? '—'} 活跃</>}
                  sub={<>总计 {platform.sessions?.total ?? '—'}</>}
                />
              </div>

              {(platform.gateway?.error || platform.users?.error) && (
                <div className="text-yellow-400 text-[10px] mt-1">Platform 服务未响应</div>
              )}
            </div>
            <details className="bg-dark-bg border border-dark-border rounded px-2 py-1 text-[10px] text-gray-500 cursor-pointer group mt-2">
              <summary className="text-gray-500 hover:text-gray-300 select-none">📖 表头说明</summary>
              <div className="mt-1 text-gray-600">服务未响应=端口未监听/服务未启动 · 网关路由=API访问入口 · 知识库集合=已创建的向量存储空间</div>
            </details>
          </CardContent>
        </Card>

        {/* ═══ APP — Layer 3 ═══ */}
        <Card className="bg-dark-card">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
                <MessageSquare className="w-4 h-4 text-orange-400" />
                应用接入层 <span className="text-[10px] text-gray-500">Layer 3</span>
                <span className="text-[9px] text-gray-600 ml-2">渠道 · 会话 · Apps</span>
              </div>
              <span className={`text-xs font-medium ${statusColor(app.status || 'healthy')}`}>
                {statusLabel(app.status || 'healthy')}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-xs">
              {/* Channels */}
              <div className="pb-1.5 border-b border-dark-border/50">
                <MetricRow
                  label="渠道"
                  value={app.channels?.total ?? '—'}
                  sub={app.channels?.by_type && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {Object.entries(app.channels.by_type).map(([type, count]: [string, any]) => (
                        <PillTag key={type} label={type} count={count as number} />
                      ))}
                    </div>
                  )}
                />
              </div>

              {/* Conversations */}
              <div className="pb-1.5 border-b border-dark-border/50">
                <MetricRow label="对话" value={app.conversations?.total ?? '—'} />
              </div>

              {/* Sessions */}
              <div className="pb-1.5 border-b border-dark-border/50">
                <MetricRow
                  label="会话"
                  value={<>{app.sessions?.active ?? '—'} 活跃</>}
                  sub={<>总计 {app.sessions?.total ?? '—'}</>}
                />
              </div>

              {/* Apps */}
              <div>
                <MetricRow label="Apps" value={app.apps?.count ?? '—'} />
              </div>

              {app.channels?.error && app.sessions?.error && (
                <div className="text-yellow-400 text-[10px] mt-1">App 服务未响应</div>
              )}
            </div>
            <details className="bg-dark-bg border border-dark-border rounded px-2 py-1 text-[10px] text-gray-500 cursor-pointer group mt-2">
              <summary className="text-gray-500 hover:text-gray-300 select-none">📖 表头说明</summary>
              <div className="mt-1 text-gray-600">渠道=外部接入方式(Slack/Telegram等) · 会话=用户对话上下文 · Apps=已发布的应用 · 能力健康同AI中台评分</div>
            </details>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default SystemOverview;
