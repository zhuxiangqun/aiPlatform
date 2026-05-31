import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { RotateCw, Server, Wrench, Power, PowerOff, Eye, Clipboard } from 'lucide-react';
import { Button, Modal, toast, Badge } from '../../../components/ui';
import { mcpApi } from '../../../services';
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
  const [configModal, setConfigModal] = useState<{ open: boolean; server: MCPServer | null }>({ open: false, server: null });

  const fetchServers = async () => {
    setLoading(true);
    try {
      await mcpApi.reloadServers().catch(() => {});
      const res = await mcpApi.listServers().catch(() => ({ servers: [] }));
      setServers((res as any)?.servers || []);
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
      const res = await mcpApi.discoverTools ? mcpApi.discoverTools(srv.name) :
        (await fetch(`/api/core/mcp/servers/${srv.name}/tools`)).json();
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
          <p className="text-sm text-gray-400 mt-1">管理引擎内置 MCP (Model Context Protocol) 服务器 — 连接外部工具到 Agent 和工作流</p>
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
          <p className="text-sm">暂无引擎内置 MCP 服务器</p>
          <p className="text-xs text-gray-600 mt-1">用户自定义 MCP 请到 应用能力层 → MCP 库 管理</p>
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
                    <span className="text-[10px] text-gray-500 bg-dark-bg px-1.5 py-0.5 rounded font-mono">{(srv as any).transport || '?'}</span>
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
                    <button onClick={() => setConfigModal({ open: true, server: srv })} className="p-1.5 rounded hover:bg-dark-hover" title="查看配置">
                      <Eye className="w-4 h-4 text-gray-400" />
                    </button>
                  </div>
                </div>
                {srv.url && <div className="text-xs text-gray-500 mb-1 font-mono truncate">{srv.url}</div>}
                {(srv as any).command && <div className="text-xs text-gray-600 mb-1 font-mono truncate">{(srv as any).command} {[...((srv as any).args || [])].join(' ')}</div>}
                {(srv as any).metadata?.description && <div className="text-xs text-gray-600 mb-1 truncate">{((srv as any).metadata as any).description}</div>}
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

      {/* Config Viewer Modal */}
      <Modal
        open={configModal.open}
        onClose={() => setConfigModal({ open: false, server: null })}
        title={`${configModal.server?.name || ''} — 配置详情`}
        width={700}
        footer={
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => {
              navigator.clipboard.writeText(JSON.stringify(configModal.server, null, 2));
              toast.success('已复制配置 JSON');
            }} icon={<Clipboard className="w-4 h-4" />}>复制 JSON</Button>
            <Button onClick={() => setConfigModal({ open: false, server: null })}>关闭</Button>
          </div>
        }
      >
        <div className="space-y-3 text-sm">
          {[
            ['名称', configModal.server?.name],
            ['状态', configModal.server?.enabled ? '已启用' : '已禁用'],
            ['传输协议', (configModal.server as any)?.transport],
            ['URL', configModal.server?.url],
            ['命令', (configModal.server as any)?.command],
            ['参数', ((configModal.server as any)?.args || []).join(' ')],
            ['认证', (configModal.server as any)?.auth ? JSON.stringify((configModal.server as any)?.auth) : '—'],
            ['允许工具数', ((configModal.server as any)?.allowed_tools || []).length],
          ].map(([label, value]) => (
            <div key={label as string} className="flex gap-3">
              <span className="text-gray-500 w-20 flex-shrink-0 text-xs">{label}</span>
              <span className="text-gray-200 font-mono text-xs break-all">{value != null ? String(value) : '—'}</span>
            </div>
          ))}
          <div>
            <div className="text-xs text-gray-500 mb-1">Metadata</div>
            <pre className="text-[10px] bg-dark-bg rounded-lg p-3 overflow-auto max-h-48 text-gray-300">
              {JSON.stringify((configModal.server as any)?.metadata || {}, null, 2)}
            </pre>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default MCP;
