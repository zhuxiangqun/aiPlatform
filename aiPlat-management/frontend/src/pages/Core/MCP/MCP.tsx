import React, { useEffect, useState } from 'react';
import { Copy, Info, RotateCw } from 'lucide-react';
import { motion } from 'framer-motion';
import { Badge, Table, Switch, Button, Modal, toast } from '../../../components/ui';
import { useMcpStore } from '../../../stores';
import type { McpServer } from '../../../services/coreApi';

const MCP: React.FC = () => {
  const { servers, loading, fetchServers, setServerEnabled } = useMcpStore();
  const [detailModal, setDetailModal] = useState<{ open: boolean; server: McpServer | null }>({ open: false, server: null });

  useEffect(() => {
    fetchServers();
  }, [fetchServers]);

  const copyText = async (text: string) => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      toast.success('已复制');
    } catch {
      toast.error('复制失败');
    }
  };

  const handleToggle = async (s: McpServer) => {
    try {
      await setServerEnabled(s.name, !s.enabled);
      toast.success(!s.enabled ? '已启用' : '已禁用');
    } catch {
      toast.error('操作失败');
    }
  };

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: McpServer) => (
        <button
          className="font-medium text-gray-100 text-left hover:underline"
          onClick={() => setDetailModal({ open: true, server: record })}
          title="查看详情"
        >
          {name}
        </button>
      ),
    },
    {
      title: 'Transport',
      dataIndex: 'transport',
      key: 'transport',
      width: 120,
      render: (v: string) => <span className="text-gray-400">{v || '-'}</span>,
    },
    {
      title: 'risk_level',
      key: 'risk_level',
      width: 120,
      render: (_: unknown, record: McpServer) => {
        const pol: any = (record as any)?.metadata?.policy || {};
        const v = pol?.risk_level;
        return <span className="text-gray-400">{v || '-'}</span>;
      },
    },
    {
      title: 'approval',
      key: 'approval',
      width: 120,
      align: 'center' as const,
      render: (_: unknown, record: McpServer) => {
        const pol: any = (record as any)?.metadata?.policy || {};
        const v = pol?.approval_required;
        return <span className="text-gray-400">{v === true ? 'required' : v === false ? 'no' : '-'}</span>;
      },
    },
    {
      title: 'prod_allowed',
      key: 'prod_allowed',
      width: 120,
      align: 'center' as const,
      render: (_: unknown, record: McpServer) => {
        const pol: any = (record as any)?.metadata?.policy || {};
        const v = pol?.prod_allowed;
        return <span className="text-gray-400">{v === true ? 'true' : v === false ? 'false' : '-'}</span>;
      },
    },
    {
      title: '状态',
      key: 'enabled',
      width: 160,
      align: 'center' as const,
      render: (_: unknown, record: McpServer) => (
        <div className="flex items-center justify-center gap-2">
          <Badge variant={(record.enabled ? 'success' : 'warning') as any}>{record.enabled ? 'enabled' : 'disabled'}</Badge>
          <Switch checked={record.enabled} onChange={() => handleToggle(record)} />
        </div>
      ),
    },
    {
      title: 'allowed_tools',
      key: 'allowed_tools',
      width: 140,
      align: 'center' as const,
      render: (_: unknown, record: McpServer) => (
        <span className="text-gray-400">{(record.allowed_tools || []).length}</span>
      ),
    },
    {
      title: 'tool_risk',
      key: 'tool_risk',
      width: 120,
      align: 'center' as const,
      render: (_: unknown, record: McpServer) => {
        const pol: any = (record as any)?.metadata?.policy || {};
        const tr = pol?.tool_risk;
        const count = tr && typeof tr === 'object' ? Object.keys(tr).length : 0;
        return <span className="text-gray-400">{count || '-'}</span>;
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      align: 'center' as const,
      render: (_: unknown, record: McpServer) => (
        <button
          onClick={() => setDetailModal({ open: true, server: record })}
          className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
          title="详情"
        >
          <Info className="w-4 h-4" />
        </button>
      ),
    },
  ];

  const server = detailModal.server as any;
  const fs = server?.metadata?.filesystem || {};
  const pol = server?.metadata?.policy || {};

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">MCP 管理</h1>
          <p className="text-sm text-gray-500 mt-1">管理 MCP Server（目录化配置：server.yaml / policy.yaml）</p>
        </div>
        <div className="flex items-center gap-3">
          <Button icon={<RotateCw className="w-4 h-4" />} onClick={fetchServers} loading={loading}>
            刷新
          </Button>
        </div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-dark-card rounded-xl border border-dark-border overflow-hidden"
      >
        <Table
          columns={columns}
          data={servers}
          rowKey="name"
          loading={loading}
          emptyText="暂无 MCP Server"
        />
      </motion.div>

      <Modal
        open={detailModal.open}
        onClose={() => setDetailModal({ open: false, server: null })}
        title={`MCP Server 详情：${detailModal.server?.name || ''}`}
        width={860}
        footer={<Button onClick={() => setDetailModal({ open: false, server: null })}>关闭</Button>}
      >
        <div className="space-y-3 text-sm text-gray-300">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-gray-500">name</div>
              <div className="flex items-center justify-between gap-2">
                <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded break-all">{String(detailModal.server?.name || '-')}</code>
                {detailModal.server?.name && (
                  <Button variant="ghost" icon={<Copy className="w-4 h-4" />} onClick={() => copyText(String(detailModal.server?.name || ''))}>
                    复制
                  </Button>
                )}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">enabled</div>
              <div>{detailModal.server?.enabled ? 'true' : 'false'}</div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-gray-500">transport</div>
              <div>{detailModal.server?.transport || '-'}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">url</div>
              <div className="break-all">{detailModal.server?.url || '-'}</div>
            </div>
          </div>

          <div>
            <div className="text-xs text-gray-500">allowed_tools</div>
            <div className="text-gray-400 break-all">{(detailModal.server?.allowed_tools || []).join(', ') || '-'}</div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="p-3 bg-dark-bg rounded-lg">
              <div className="text-xs text-gray-400 mb-1">policy.risk_level</div>
              <div className="text-sm text-gray-200">{String(pol?.risk_level ?? '-')}</div>
            </div>
            <div className="p-3 bg-dark-bg rounded-lg">
              <div className="text-xs text-gray-400 mb-1">policy.approval_required</div>
              <div className="text-sm text-gray-200">{pol?.approval_required === true ? 'true' : pol?.approval_required === false ? 'false' : '-'}</div>
            </div>
            <div className="p-3 bg-dark-bg rounded-lg">
              <div className="text-xs text-gray-400 mb-1">policy.prod_allowed</div>
              <div className="text-sm text-gray-200">{pol?.prod_allowed === true ? 'true' : pol?.prod_allowed === false ? 'false' : '-'}</div>
            </div>
            <div className="p-3 bg-dark-bg rounded-lg">
              <div className="text-xs text-gray-400 mb-1">policy.tool_risk</div>
              <pre className="text-xs bg-dark-hover rounded p-2 overflow-auto max-h-40">{JSON.stringify(pol?.tool_risk || {}, null, 2)}</pre>
            </div>
          </div>

          <div>
            <div className="text-xs text-gray-500">filesystem.server_dir</div>
            <div className="flex items-center justify-between gap-2">
              <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded break-all">{String(fs.server_dir || '-')}</code>
              {fs.server_dir && (
                <Button variant="ghost" icon={<Copy className="w-4 h-4" />} onClick={() => copyText(String(fs.server_dir))}>
                  复制
                </Button>
              )}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500">filesystem.server_yaml</div>
            <div className="flex items-center justify-between gap-2">
              <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded break-all">{String(fs.server_yaml || '-')}</code>
              {fs.server_yaml && (
                <Button variant="ghost" icon={<Copy className="w-4 h-4" />} onClick={() => copyText(String(fs.server_yaml))}>
                  复制
                </Button>
              )}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500">filesystem.policy_yaml</div>
            <div className="flex items-center justify-between gap-2">
              <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded break-all">{String(fs.policy_yaml || '-')}</code>
              {fs.policy_yaml && (
                <Button variant="ghost" icon={<Copy className="w-4 h-4" />} onClick={() => copyText(String(fs.policy_yaml))}>
                  复制
                </Button>
              )}
            </div>
          </div>

          <div>
            <div className="text-xs text-gray-500">原始 metadata</div>
            <pre className="text-xs bg-dark-hover rounded p-2 overflow-auto max-h-48">{JSON.stringify(detailModal.server?.metadata || {}, null, 2)}</pre>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default MCP;
