import React, { useEffect, useState } from 'react';
import { Copy, Info, Pencil, Plus, RotateCw, ShieldCheck, Zap, Play, Trash2, Upload } from 'lucide-react';
import { motion } from 'framer-motion';
import { Badge, Table, Switch, Button, Modal, toast } from '../../../components/ui';
import { useWorkspaceMcpStore } from '../../../stores';
import type { McpServer } from '../../../services';
import { workspaceMcpApi } from '../../../services';
import { ExecutionViewer } from '../../../components/ExecutionViewer';
import AddMcpModal from '../../../components/workspace/AddMcpModal';
import EditMcpModal from '../../../components/workspace/EditMcpModal';
import { toastGateError } from '../../../components/ui';
import ImportBar from '../../../components/workspace/ImportBar';

const MCP_TEMPLATES = [
  { id: 'http_bridge', name: 'HTTP API 桥接', icon: '🌐', desc: '调用任何 REST/HTTP API', tools: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] },
  { id: 'shell_executor', name: 'Shell 命令执行', icon: '⚡', desc: '每个允许的命令生成独立工具', tools: ['ls', 'cat', 'grep', 'curl', 'ps', '…'] },
  { id: 'file_ops', name: '文件操作', icon: '📁', desc: '读写本地文件系统', tools: ['读', '写', '追', '删', '列', '查'] },
  { id: 'db_query', name: '数据库查询', icon: '🗄️', desc: '查询 SQLite/PostgreSQL/MySQL', tools: ['查询', '列表', '写操作'] },
];

const WorkspaceMCP: React.FC = () => {
  const { servers, loading, fetchServers, setServerEnabled } = useWorkspaceMcpStore();
  const [detailModal, setDetailModal] = useState<{ open: boolean; server: McpServer | null }>({ open: false, server: null });
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editServer, setEditServer] = useState<McpServer | null>(null);
  const [autoDiscover, setAutoDiscover] = useState(false);
  const [templateModal, setTemplateModal] = useState(false);
  const [templateName, setTemplateName] = useState('');
  const [templateId, setTemplateId] = useState('');
  const [templateCreating, setTemplateCreating] = useState(false);
  const [testRunId, setTestRunId] = useState('');
  const [testServerName, setTestServerName] = useState('');
  const [testModal, setTestModal] = useState(false);

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
      toastGateError(e);
    }
  };

  const handleSubmitForReview = async (s: McpServer) => {
    try {
      await workspaceMcpApi.submitForReview(s.name);
      toast.success(`MCP "${s.name}" 已提交审批`);
      fetchServers();
    } catch (e: any) {
      toast.error('提交失败', e?.message || String(e));
    }
  };

  const handleTest = async (s: McpServer) => {
    if (!s.enabled) { toast.error('请先启用 MCP 再进行测试'); return; }
    try {
      const res = await fetch(`/api/core/workspace/mcp/servers/${s.name}/test-invoke`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (!res.ok) {
        toast.error(`${s.name}: ${data.detail || data.message || `HTTP ${res.status}`}`);
        return;
      }
      // Open ExecutionViewer live mode
      setTestRunId(data.run_id);
      setTestServerName(s.name);
      setTestModal(true);
    } catch (e: any) {
      toast.error(`测试请求失败: ${e?.message || ''}`);
    }
  };

  const handleDelete = async (s: McpServer) => {
    if (!window.confirm(`确定要删除 MCP "${s.name}" 吗？此操作不可撤销，将删除整个配置目录。`)) return;
    try {
      await workspaceMcpApi.deleteServer(s.name);
      toast.success(`已删除 "${s.name}"`);
      fetchServers();
    } catch (e: any) {
      toastGateError(e, '删除失败');
    }
  };

  const handleExportPlugin = async (s: McpServer) => {
    try {
      const res = await fetch('/api/core/workspace/packages/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: s.name,
          version: '0.1.0',
          description: (s.metadata as any)?.description || '',
          resources: [{ kind: 'mcp', id: s.name }],
        }),
      });
      if (!res.ok) { toast.error('导出失败'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${s.name}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`已导出 ${s.name}`);
    } catch (e: any) {
      toast.error(`导出失败: ${e?.message || ''}`);
    }
  };

  const handleTemplateCreate = async () => {
    if (!templateName.trim()) { toast.error('请输入 MCP 名称'); return; }
    if (!templateId) { toast.error('请选择模板'); return; }
    setTemplateCreating(true);
    try {
      await workspaceMcpApi.createFromTemplate(templateId, {
        name: templateName.trim(),
        description: MCP_TEMPLATES.find(t => t.id === templateId)?.desc || '',
      });
      await workspaceMcpApi.reloadServers();
      setTemplateModal(false);
      setTemplateName('');
      setTemplateId('');
      fetchServers();
      toast.success(`MCP "${templateName.trim()}" 从模板创建成功`);
    } catch (e: any) {
      toastGateError(e, '创建失败');
    } finally {
      setTemplateCreating(false);
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
    { title: 'Transport', dataIndex: 'transport', key: 'transport', width: 100, render: (v: string) => <span className="text-gray-400">{v || '-'}</span> },
    {
      title: '描述',
      key: 'description',
      width: 220,
      render: (_: unknown, record: McpServer) => {
        const desc = ((record.metadata as any)?.description || '').trim();
        return desc
          ? <span className="text-xs text-gray-400 truncate block max-w-[220px]" title={desc}>{desc}</span>
          : <span className="text-xs text-gray-600">—</span>;
      },
    },
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
      width: 160,
      align: 'center' as const,
      render: (_: unknown, record: McpServer) => (
        <div className="flex items-center justify-center gap-1">
          <button
            onClick={() => handleTest(record)}
            className={`p-1.5 rounded-lg transition-colors ${record.enabled ? 'text-green-400 hover:bg-green-400/10' : 'text-gray-600 cursor-not-allowed'}`}
            title={record.enabled ? '测试调用' : '请先启用'}
            disabled={!record.enabled}
          >
            <Play className="w-4 h-4" />
          </button>
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
          {(record.status || '').toLowerCase() === 'draft' || (record.status || '').toLowerCase() === 'enabled' ? (
            <button
              onClick={() => handleSubmitForReview(record)}
              className="p-1.5 rounded-lg text-amber-400 hover:bg-amber-400/10 transition-colors"
              title="提交审批"
            >
              <ShieldCheck className="w-4 h-4" />
            </button>
          ) : null}
          <button
            onClick={() => handleDelete(record)}
            className="p-1.5 rounded-lg text-red-400 hover:bg-red-400/10 transition-colors"
            title="删除"
          >
            <Trash2 className="w-4 h-4" />
          </button>
          <button
            onClick={() => handleExportPlugin(record)}
            className="p-1.5 rounded-lg text-purple-400 hover:bg-purple-400/10 transition-colors"
            title="导出为插件"
          >
            <Upload className="w-4 h-4" />
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
          <Button variant="outline" size="sm" icon={<Zap className="w-4 h-4" />} onClick={() => setTemplateModal(true)}>
            从模板创建
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
        onCreated={(name) => {
          setAddOpen(false);
          setEditServer({ name, enabled: true } as McpServer);
          setAutoDiscover(true);
          setEditOpen(true);
        }}
      />

      <EditMcpModal
        open={editOpen}
        server={editServer}
        onClose={() => { setEditOpen(false); setAutoDiscover(false); }}
        onSuccess={fetchServers}
        autoDiscover={autoDiscover}
      />

      {/* Template Creation Modal */}
      <Modal
        open={templateModal}
        onClose={() => { setTemplateModal(false); setTemplateId(''); }}
        title="从模板创建 MCP"
        width={650}
        footer={
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => { setTemplateModal(false); setTemplateId(''); }}>取消</Button>
            <Button variant="primary" onClick={handleTemplateCreate} loading={templateCreating} disabled={!templateId}>创建</Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <div className="text-xs text-gray-500 mb-1">名称</div>
            <input
              value={templateName}
              onChange={e => setTemplateName(e.target.value)}
              placeholder="my_mcp_server"
              className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-sm text-gray-200"
            />
          </div>
          <div>
            <div className="text-xs text-gray-500 mb-2">选择模板</div>
            <div className="grid grid-cols-2 gap-3">
              {MCP_TEMPLATES.map(t => (
                <div
                  key={t.id}
                  onClick={() => setTemplateId(t.id)}
                  className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                    templateId === t.id
                      ? 'border-primary/50 bg-primary/10'
                      : 'border-dark-border bg-dark-bg hover:border-dark-border/80'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-lg">{t.icon}</span>
                    <span className="text-sm font-semibold text-gray-100">{t.name}</span>
                  </div>
                  <div className="text-xs text-gray-500 mb-2">{t.desc}</div>
                  <div className="flex flex-wrap gap-1">
                    {t.tools.map(tool => (
                      <Badge key={tool} variant="default" className="text-[10px]">{tool}</Badge>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="text-xs text-gray-600 bg-dark-bg rounded-lg p-3">
            <Zap className="w-3 h-3 inline mr-1 text-yellow-400" />
            创建后默认为<b>禁用</b>状态。编辑 <code>~/.aiplat/mcps/{'{name}'}/server.yaml</code> 修改配置，再启用。
          </div>
        </div>
      </Modal>

      {/* Test Execution Viewer Modal */}
      <Modal
        open={testModal}
        onClose={() => setTestModal(false)}
        title={`测试 MCP: ${testServerName}`}
        width={900}
        footer={<Button onClick={() => setTestModal(false)}>关闭</Button>}
      >
        <ExecutionViewer
          title={testServerName}
          live
          runId={testRunId}
          height={420}
        />
      </Modal>
    </div>
  );
};

export default WorkspaceMCP;
