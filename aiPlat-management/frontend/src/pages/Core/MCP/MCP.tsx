import React, { useState, useEffect } from 'react';
import { RotateCw, Server, Wrench, Power, PowerOff, Eye, Copy } from 'lucide-react';
import { Button, Modal, toast, Table, Switch, Badge } from '../../../components/ui';
import { mcpApi } from '../../../services';
import { toastGateError } from '../../../components/ui';
import { getSourceLabel, extractProvenance } from '../../../utils/sourceLabel';

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
  transport?: string;
  command?: string;
  args?: string[];
  metadata?: Record<string, unknown>;
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
      const res = await (mcpApi as any).discoverTools?.(srv.name) ||
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
        <Table
          rowKey="name"
          loading={loading}
          data={servers}
          columns={[
            {
              title: '名称', dataIndex: 'name', key: 'name',
              render: (name: string, record: MCPServer) => (
                <button onClick={() => handleDiscover(record)}
                  className="text-primary hover:text-primary-hover font-medium">{name}</button>
              ),
            },
            {
              title: 'Transport', key: 'transport', width: 80,
              render: (_: unknown, record: MCPServer) => (
                <span className="text-xs text-gray-400 font-mono">{(record as any).transport || '-'}</span>
              ),
            },
            {
              title: '来源', key: 'source', width: 80,
              render: (_: unknown, record: MCPServer) => (
                <span className="text-gray-400 text-xs">{getSourceLabel(extractProvenance(record))}</span>
              ),
            },
            {
              title: '描述', key: 'description', width: 220,
              render: (_: unknown, record: MCPServer) => (
                <span className="text-xs text-gray-500 truncate block max-w-[200px]">
                  {(record as any)?.metadata?.description || (record as any)?.description || '-'}
                </span>
              ),
            },
            {
              title: '启用', key: 'enabled', width: 100, align: 'center' as const,
              render: (_: unknown, record: MCPServer) => (
                <div className="flex items-center gap-2 justify-center">
                  <Badge variant={record.enabled ? 'success' as any : 'warning' as any}>{record.enabled ? 'enabled' : 'disabled'}</Badge>
                  <Switch checked={record.enabled} onChange={() => handleToggle(record)} />
                </div>
              ),
            },
            {
              title: '工具数', key: 'tool_count', width: 65, align: 'center' as const,
              render: (_: unknown, record: MCPServer) => (
                <span className="text-xs text-gray-400">{(record as any).allowed_tools?.length || (record as any).tools?.length || 0}</span>
              ),
            },
            {
              title: '操作', key: 'actions', width: 160, align: 'center' as const,
              render: (_: unknown, record: MCPServer) => (
                <div className="flex items-center justify-center gap-1">
                  <button onClick={() => handleToggle(record)} className="p-1.5 rounded hover:bg-dark-hover" title={record.enabled ? '禁用' : '启用'}>
                    {record.enabled ? <PowerOff className="w-4 h-4 text-amber-400" /> : <Power className="w-4 h-4 text-green-400" />}
                  </button>
                  <button onClick={() => handleDiscover(record)} className="p-1.5 rounded hover:bg-dark-hover" title="发现工具">
                    <Wrench className="w-4 h-4 text-gray-400" />
                  </button>
                  <button onClick={() => setConfigModal({ open: true, server: record })} className="p-1.5 rounded hover:bg-dark-hover" title="查看配置">
                    <Eye className="w-4 h-4 text-gray-400" />
                  </button>
                </div>
              ),
            },
          ]}
        />
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
            }} icon={<Copy className="w-4 h-4" />}>复制 JSON</Button>
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
