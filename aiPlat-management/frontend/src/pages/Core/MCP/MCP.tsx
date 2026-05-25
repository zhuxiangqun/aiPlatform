import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { RotateCw, Server, Wrench, Power, PowerOff } from 'lucide-react';
import { Button, Modal, toast, Badge } from '../../../components/ui';
import { mcpApi, workspaceMcpApi } from '../../../services';
import { toastGateError } from '../../../components/ui';

interface MCPTool {
  name: string;
  description?: string;
  input_schema?: Record<string, unknown>;
}

interface MCPServer {
  name: string;
  url?: string;
  enabled: boolean;
  tools?: MCPTool[];
}

const MCP: React.FC = () => {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [loading, setLoading] = useState(false);
  const [detailServer, setDetailServer] = useState<MCPServer | null>(null);
  const [detailTools, setDetailTools] = useState<MCPTool[]>([]);
  const [toolsLoading, setToolsLoading] = useState(false);

  const fetchServers = async () => {
    setLoading(true);
    try {
      const [engineRes, wsRes] = await Promise.all([
        mcpApi.listServers().catch(() => ({ servers: [] })),
        workspaceMcpApi.listServers().catch(() => ({ servers: [] })),
      ]);
      const engineServers = ((engineRes as any)?.servers || []).map((s: any) => ({ ...s, scope: 'engine' }));
      const wsServers = ((wsRes as any)?.servers || []).map((s: any) => ({ ...s, scope: 'workspace' }));
      setServers([...engineServers, ...wsServers]);
    } catch {
      setServers([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchServers(); }, []);

  const handleToggle = async (srv: MCPServer) => {
    try {
      if (srv.enabled) {
        await mcpApi.disableServer(srv.name);
      } else {
        await mcpApi.enableServer(srv.name);
      }
      toast.success(srv.enabled ? '已禁用' : '已启用');
      fetchServers();
    } catch (e: any) {
      toastGateError(e, '操作失败');
    }
  };

  const handleDiscover = async (srv: MCPServer) => {
    setDetailServer(srv);
    setToolsLoading(true);
    try {
      const res = await workspaceMcpApi.discoverTools(srv.name);
      setDetailTools((res as any)?.tools || []);
    } catch {
      setDetailTools([]);
    } finally {
      setToolsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">MCP 管理</h1>
          <p className="text-sm text-gray-400 mt-1">管理 MCP (Model Context Protocol) 服务器 — 连接外部工具到 Agent 和工作流</p>
        </div>
        <Button icon={<RotateCw className="w-4 h-4" />} onClick={fetchServers} loading={loading}>
          刷新
        </Button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-500">加载中...</div>
      ) : servers.length === 0 ? (
        <div className="text-center py-12 text-gray-500 border border-dashed border-dark-border rounded-xl">
          <Server className="w-12 h-12 mx-auto mb-3 text-gray-600" />
          <p className="text-sm">暂无 MCP 服务器</p>
          <p className="text-xs text-gray-600 mt-1">MCP 服务器通过配置文件定义，添加后在此管理启用/禁用和工具发现</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {servers.map((srv) => (
            <motion.div
              key={srv.name}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="p-4 rounded-xl bg-dark-card border border-dark-border hover:border-primary/30 transition-colors"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Server className="w-5 h-5 text-blue-400" />
                  <span className="text-sm font-medium text-gray-100">{srv.name}</span>
                  <span className="text-[10px] text-gray-600 bg-dark-bg px-1.5 py-0.5 rounded">{(srv as any).scope || 'engine'}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded text-xs ${srv.enabled ? 'bg-green-900/50 text-green-300' : 'bg-gray-700/50 text-gray-400'}`}>
                    {srv.enabled ? '已启用' : '已禁用'}
                  </span>
                  <button onClick={() => handleToggle(srv)} className="p-1.5 rounded hover:bg-dark-hover" title={srv.enabled ? '禁用' : '启用'}>
                    {srv.enabled ? <PowerOff className="w-4 h-4 text-amber-400" /> : <Power className="w-4 h-4 text-green-400" />}
                  </button>
                  <button onClick={() => handleDiscover(srv)} className="p-1.5 rounded hover:bg-dark-hover" title="发现工具">
                    <Wrench className="w-4 h-4 text-gray-400" />
                  </button>
                </div>
              </div>
              {srv.url && <div className="text-xs text-gray-500 mb-2 font-mono truncate">{srv.url}</div>}
              {srv.tools && srv.tools.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {srv.tools.slice(0, 6).map((t) => (
                    <Badge key={t.name} variant="default" className="text-[10px]">{t.name}</Badge>
                  ))}
                </div>
              )}
            </motion.div>
          ))}
        </div>
      )}

      {/* Detail Modal */}
      <Modal
        open={!!detailServer}
        onClose={() => { setDetailServer(null); setDetailTools([]); }}
        title={`${detailServer?.name || ''} — 工具列表`}
        width={700}
        footer={<Button onClick={() => { setDetailServer(null); setDetailTools([]); }}>关闭</Button>}
      >
        {toolsLoading ? (
          <div className="text-center py-8 text-gray-500">发现工具中...</div>
        ) : detailTools.length > 0 ? (
          <div className="space-y-2">
            {detailTools.map((t, i) => (
              <div key={i} className="p-3 rounded-lg bg-dark-bg border border-dark-border">
                <div className="flex items-center gap-2">
                  <Wrench className="w-4 h-4 text-amber-400" />
                  <span className="text-sm text-gray-100 font-medium">{t.name}</span>
                </div>
                {t.description && <p className="text-xs text-gray-400 mt-1">{t.description}</p>}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-gray-500 py-4 text-center">暂无工具 — 服务器可能未连接或未配置工具</div>
        )}
      </Modal>
    </div>
  );
};

export default MCP;
