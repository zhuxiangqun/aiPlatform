import React, { useEffect, useState } from 'react';
import { Copy, Info, Pencil, Plus, RotateCw } from 'lucide-react';
import { motion } from 'framer-motion';
import { Badge, Table, Switch, Button, Modal, toast } from '../../../components/ui';
import { useWorkspaceMcpStore } from '../../../stores';
import type { McpServer } from '../../../services';
import AddMcpModal from '../../../components/workspace/AddMcpModal';
import EditMcpModal from '../../../components/workspace/EditMcpModal';
import { toastGateError } from '../../../components/ui';
import ImportBar from '../../../components/workspace/ImportBar';

const WorkspaceMCP: React.FC = () => {
  const { servers, loading, fetchServers, setServerEnabled } = useWorkspaceMcpStore();
  const [detailModal, setDetailModal] = useState<{ open: boolean; server: McpServer | null }>({ open: false, server: null });
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editServer, setEditServer] = useState<McpServer | null>(null);

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
    } catch (e: any) {
      toastGateError(e, '操作失败');
    }
  };

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: McpServer) => (
        <button className="font-medium text-gray-100 text-left hover:underline" onClick={() => setDetailModal({ open: true, server: record })}>
          {name}
        </button>
      ),
    },
    { title: 'Transport', dataIndex: 'transport', key: 'transport', width: 120, render: (v: string) => <span className="text-gray-400">{v || '-'}</span> },
    {
      title: '上架状态',
      dataIndex: 'status',
      key: 'listing_status',
      width: 120,
      align: 'center' as const,
      render: (s: string) => {
        const labels: Record<string, string> = { draft: '草稿', ready: '待审核', published: '已发布', listed: '已上架', deprecated: '已废弃' };
        const colors: Record<string, string> = { draft: '#888', ready: '#f59e0b', published: '#3b82f6', listed: '#10b981', deprecated: '#6b7280' };
        return <span className="text-xs" style={{ color: colors[s] || '#888' }}>{labels[s] || s || '-'}</span>;
      },
    },
    {
      title: '启用',
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
      render: (_: unknown, record: McpServer) => <span className="text-gray-400">{(record.allowed_tools || []).length}</span>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      align: 'center' as const,
      render: (_: unknown, record: McpServer) => (
        <div className="flex items-center justify-center gap-1">
          <button
            onClick={() => setDetailModal({ open: true, server: record })}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
            title="详情"
          >
            <Info className="w-4 h-4" />
          </button>
          <button
            onClick={() => { setEditServer(record); setEditOpen(true); }}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
            title="编辑"
          >
            <Pencil className="w-4 h-4" />
          </button>
        </div>
      ),
    },
  ];

  const server = detailModal.server as any;
  const fs = server?.metadata?.filesystem || {};

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">应用库 MCP</h1>
          <p className="text-sm text-gray-500 mt-1">来自 ~/.aiplat/mcps（可编辑）</p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="primary" icon={<Plus className="w-4 h-4" />} onClick={() => setAddOpen(true)}>
            新增
          </Button>
          <Button icon={<RotateCw className="w-4 h-4" />} onClick={fetchServers} loading={loading}>
            刷新
          </Button>
        </div>
      </div>

      <ImportBar assetType="mcps" alsoScan={['agents', 'skills']} onImported={() => fetchServers()} />

      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
        <Table columns={columns} data={servers} rowKey="name" loading={loading} emptyText="暂无 MCP Server" />
      </motion.div>

      <Modal
        open={detailModal.open}
        onClose={() => setDetailModal({ open: false, server: null })}
        title={`MCP Server 详情：${detailModal.server?.name || ''}`}
        width={860}
        footer={<Button onClick={() => setDetailModal({ open: false, server: null })}>关闭</Button>}
      >
        <div className="space-y-3 text-sm text-gray-300">
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
            <div className="text-xs text-gray-500">原始 metadata</div>
            <pre className="text-xs bg-dark-hover rounded p-2 overflow-auto max-h-48">{JSON.stringify(detailModal.server?.metadata || {}, null, 2)}</pre>
          </div>
        </div>
      </Modal>

      <AddMcpModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onSuccess={fetchServers}
      />

      <EditMcpModal
        open={editOpen}
        server={editServer}
        onClose={() => setEditOpen(false)}
        onSuccess={fetchServers}
      />
    </div>
  );
};

export default WorkspaceMCP;
