import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { RefreshCw, Server, Cpu, Bot, Network, Shield, MessageSquare, Database, Layers, Globe } from 'lucide-react';

const SystemOverview: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/core/overview');
      setData(await r.json());
    } catch { }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchData(); const t = setInterval(fetchData, 30000); return () => clearInterval(t); }, []);

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

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">系统概览</h1>
          <p className="text-xs text-gray-500 mt-0.5">四层架构运行状态</p>
        </div>
        <Button variant="ghost" size="sm" onClick={fetchData} loading={loading}>
          <RefreshCw className="w-3 h-3 mr-1" />刷新
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* ═══ INFRA — Layer 0 ═══ */}
        <Card className={statusBg(infra.status || 'healthy')}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
                <Server className="w-4 h-4 text-cyan-400" />
                基础设施层 <span className="text-[10px] text-gray-500">Layer 0</span>
              </div>
              <span className={`text-xs font-medium ${statusColor(infra.status || 'healthy')}`}>
                {statusLabel(infra.status || 'healthy')}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-xs">
              {/* Models */}
              <div className="flex justify-between">
                <span className="text-gray-500">模型</span>
                <span className="text-gray-300">
                  {infra.models?.available ?? '—'}/{infra.models?.total ?? '—'} 可用
                  {infra.models?.types && (
                    <span className="text-gray-500 ml-1">
                      (chat:{infra.models.types.chat || 0} emb:{infra.models.types.embedding || 0})
                    </span>
                  )}
                </span>
              </div>
              {/* Servers */}
              <div className="flex justify-between">
                <span className="text-gray-500">服务</span>
                <span className="text-gray-300">{serversUp()}/{serversTotal()} 在线</span>
              </div>
              <div className="flex flex-wrap gap-1.5 mt-2">
                {Object.entries(infra.servers || {}).map(([name, status]: [string, any]) => (
                  <span key={name} className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] ${
                    status === 'up' ? 'bg-green-900/20 text-green-300 border border-green-500/20' : 'bg-red-900/20 text-red-300 border border-red-500/20'
                  }`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${status === 'up' ? 'bg-green-400' : 'bg-red-400'}`} />
                    {name}
                  </span>
                ))}
              </div>
              {infra.models?.error && <div className="text-red-400 mt-1">{infra.models.error}</div>}
            </div>
          </CardContent>
        </Card>

        {/* ═══ CORE — Layer 1 ═══ */}
        <Card className="bg-dark-card">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
                <Cpu className="w-4 h-4 text-violet-400" />
                AI 中台 <span className="text-[10px] text-gray-500">Layer 1</span>
              </div>
              <span className={`text-xs font-medium ${statusColor(core.status || 'healthy')}`}>
                {statusLabel(core.status || 'healthy')}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-gray-500">Agent</span>
                <span className="text-gray-300">
                  {core.agents?.total ?? '—'}
                  <span className="text-gray-500 ml-1">(引擎 {core.agents?.engine ?? 0} + 应用 {core.agents?.workspace ?? 0})</span>
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Skill</span>
                <span className="text-gray-300">{core.skills?.total ?? '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Tool</span>
                <span className="text-gray-300">{core.tools ?? '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">MCP 服务器</span>
                <span className="text-gray-300">{core.mcp_servers ?? '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Pipeline</span>
                <span className="text-gray-300">
                  {core.pipeline?.active !== undefined ? `${core.pipeline.active} 活跃` : '—'}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ═══ PLATFORM — Layer 2 ═══ */}
        <Card className="bg-dark-card">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
                <Globe className="w-4 h-4 text-emerald-400" />
                平台服务层 <span className="text-[10px] text-gray-500">Layer 2</span>
              </div>
              <span className={`text-xs font-medium ${statusColor(platform.status || 'healthy')}`}>
                {statusLabel(platform.status || 'healthy')}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-gray-500">网关路由</span>
                <span className="text-gray-300">{platform.gateway?.routes ?? '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">用户</span>
                <span className="text-gray-300">{platform.auth?.users ?? '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">租户</span>
                <span className="text-gray-300">{platform.tenant?.tenants ?? '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">知识库</span>
                <span className="text-gray-300">集合 {platform.knowledge_base?.collections ?? '—'}</span>
              </div>
              {platform.gateway?.error && platform.auth?.error && (
                <div className="text-yellow-400 text-[10px] mt-1">Platform 服务未响应</div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* ═══ APP — Layer 3 ═══ */}
        <Card className="bg-dark-card">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
                <MessageSquare className="w-4 h-4 text-orange-400" />
                应用接入层 <span className="text-[10px] text-gray-500">Layer 3</span>
              </div>
              <span className={`text-xs font-medium ${statusColor(app.status || 'healthy')}`}>
                {statusLabel(app.status || 'healthy')}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-gray-500">渠道</span>
                <span className="text-gray-300">{app.channels?.count ?? '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">会话</span>
                <span className="text-gray-300">
                  {app.sessions?.active ?? '—'} 活跃 / {app.sessions?.total ?? '—'} 总计
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Apps</span>
                <span className="text-gray-300">{app.apps?.count ?? '—'}</span>
              </div>
              {app.channels?.error && app.sessions?.error && (
                <div className="text-yellow-400 text-[10px] mt-1">App 服务未响应</div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default SystemOverview;
