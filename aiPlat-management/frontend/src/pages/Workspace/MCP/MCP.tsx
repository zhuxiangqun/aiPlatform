import React, { useEffect, useState } from 'react';
import { Copy, Info, Pencil, Plus, RotateCw, ShieldCheck, Zap, Play, Trash2, Upload } from 'lucide-react';
import { motion } from 'framer-motion';
import { Badge, Table, Switch, Button, Modal, toast } from '../../../components/ui';
import { useWorkspaceMcpStore } from '../../../stores';
import type { McpServer } from '../../../services';
import { workspaceMcpApi, mcpApi } from '../../../services';
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
  const [signing, setSigning] = useState(false);
  const [signKey, setSignKey] = useState('');
  const [signResult, setSignResult] = useState<string | null>(null);
  const [seedsModalOpen, setSeedsModalOpen] = useState(false);
  const [seeds, setSeeds] = useState<any[]>([]);
  const [seedsLoading, setSeedsLoading] = useState(false);
  const [testRunId, setTestRunId] = useState('');
  const [testServerName, setTestServerName] = useState('');
  const [testModal, setTestModal] = useState(false);

  // Test config panel state
  const [testConfigOpen, setTestConfigOpen] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [testToolName, setTestToolName] = useState('');
  const [testToolArgs, setTestToolArgs] = useState('{}');
  const [testAllowedTools, setTestAllowedTools] = useState<string[]>([]);
  const [testToolSchemas, setTestToolSchemas] = useState<Record<string, any>>({});
  const [testToolParams, setTestToolParams] = useState<Record<string, any>>({});

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

  const handleSign = async () => {
    if (!detailModal.server?.name || !signKey.trim()) return;
    setSigning(true);
    setSignResult(null);
    try {
      const res = await mcpApi.signServer(detailModal.server.name, { private_key: signKey.trim() });
      setSignResult(res.signature);
      toast.success('MCP 签名成功');
      setSignKey('');
    } catch (e: any) {
      toastGateError(e, '签名失败');
      setSignResult(null);
    } finally {
      setSigning(false);
    }
  };

  const loadSeeds = async () => {
    setSeedsLoading(true);
    try {
      const r = await mcpApi.listSeeds();
      setSeeds(r.seeds || []);
    } catch { setSeeds([]); }
    finally { setSeedsLoading(false); }
  };

  const installSeed = async (seedId: string) => {
    try {
      await mcpApi.installSeed(seedId);
      toast.success(`已安装：${seedId}`);
      await loadSeeds();
      fetchServers();
    } catch (e: any) { toast.error('安装失败', e?.message || String(e)); }
  };

  const handleToggle = async (s: McpServer) => {
    try {
      await setServerEnabled(s.name, !s.enabled);
      toast.success(!s.enabled ? '已启用' : '已禁用');
    } catch (e: any) {
      toastGateError(e, '操作失败');
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
    setTestServerName(s.name);
    const allowed = s.allowed_tools || [];
    setTestAllowedTools(allowed);
    setTestToolName(allowed.length > 0 ? allowed[0] : '');
    setTestToolArgs('{}');
    setTestToolParams({});
    setTestToolSchemas({});

    // Fetch tool schemas: internal via discover, external via MCP tools/list
    if (s.source === 'internal') {
      try {
        const r = await fetch('/api/core/workspace/tools/discover', { method: 'POST' });
        const data = await r.json();
        const schemas: Record<string, any> = {};
        for (const t of data.tools || []) { schemas[t.name] = t.parameters || {}; }
        setTestToolSchemas(schemas);
      } catch { }
    } else {
      try {
        const r = await fetch(`/api/core/workspace/mcp/servers/${s.name}/tools?timeout_seconds=10`);
        const data = await r.json();
        const schemas: Record<string, any> = {};
        for (const t of data.tools || []) { schemas[t.name] = t.inputSchema || {}; }
        setTestToolSchemas(schemas);
      } catch { }
    }
    setTestConfigOpen(true);
  };

  const handleStartTest = async () => {
    const srvName = testServerName;
    if (!srvName) return;
    setTestConfigOpen(false);
    setTestModal(true);
    setTestRunId('');
    // Use schema-based params if available, otherwise JSON textarea
    const schema = testToolSchemas[testToolName];
    let args: any;
    if (schema?.properties && Object.keys(schema.properties).length > 0) {
      args = testToolParams;
    } else {
      try { args = JSON.parse(testToolArgs); } catch { args = {}; }
    }
    try {
      const body: any = {};
      if (testToolName.trim()) body.tool = testToolName.trim();
      if (Object.keys(args).length > 0) body.arguments = args;
      const res = await fetch(`/api/core/workspace/mcp/servers/${srvName}/test-invoke`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        toast.error(`${srvName}: ${data.detail || data.message || `HTTP ${res.status}`}`);
        setTestModal(false);
        return;
      }
      setTestRunId(data.run_id);
    } catch (e: any) {
      toast.error(`测试请求失败: ${e?.message || ''}`);
      setTestModal(false);
    }
  };

  const handleDelete = async (s: McpServer) => {
    if (deleting) return;
    if (!window.confirm(`确定要删除 MCP "${s.name}" 吗？此操作不可撤销，将删除整个配置目录。`)) return;
    setDeleting(s.id);
    try {
      await workspaceMcpApi.deleteServer(s.name);
      toast.success(`已删除 "${s.name}"`);
      fetchServers();
    } catch (e: any) {
      toastGateError(e, '删除失败');
    } finally {
      setDeleting(null);
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
          resources: [{ kind: 'mcp', id: (s as any).id || s.name }],
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
    { title: 'Transport', dataIndex: 'transport', key: 'transport', width: 80, render: (v: string) => <span className="text-gray-400 text-xs">{v || '-'}</span> },
    {
      title: '来源', key: 'source', width: 70, align: 'center' as const,
      render: (_: unknown, record: McpServer) => {
        const isInternal = record.source === 'internal';
        return (
          <span className={`inline-flex px-1.5 py-0.5 rounded text-xs font-medium ${
            isInternal ? 'bg-blue-500/15 text-blue-300 border border-blue-500/25' : 'bg-dark-hover text-gray-400 border border-dark-border'
          }`}>
            {isInternal ? '内部' : '外部'}
          </span>
        );
      },
    },
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
      title: '治理',
      key: 'governance',
      width: 90,
      render: (_: unknown, record: McpServer) => {
        const prov: any = (record as any)?.provenance || {};
        if (prov?.signature_verified) return <span className="text-xs text-green-400">已验签</span>;
        if (prov?.signature) return <span className="text-xs text-blue-400">已签名</span>;
        return <span className="text-xs text-gray-500">未签名</span>;
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
            disabled={!!deleting}
            className="p-1.5 rounded-lg text-red-400 hover:bg-red-400/10 transition-colors disabled:opacity-40"
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
          <Button variant="secondary" icon={<Upload className="w-4 h-4" />} onClick={() => { loadSeeds(); setSeedsModalOpen(true); }}>
            从模板安装
          </Button>
          <Button variant="secondary" size="sm" icon={<Zap className="w-4 h-4" />} onClick={() => setTemplateModal(true)}>
            从模板创建
          </Button>
          <Button icon={<RotateCw className="w-4 h-4" />} onClick={fetchServers} loading={loading}>
            刷新
          </Button>
        </div>
      </div>

      <ImportBar assetType="mcps" alsoScan={['agents', 'skills']} onImported={() => fetchServers()} />

      <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group mb-3">
        <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
          <div><span className="text-gray-300">名称</span><span className="ml-2 text-gray-600">MCP Server 名称，点击查看详情</span></div>
          <div><span className="text-gray-300">Transport</span><span className="ml-2 text-gray-600">传输方式：stdio / sse / http</span></div>
          <div><span className="text-gray-300">来源</span><span className="ml-2 text-gray-600"><span className="text-blue-300">内部</span> 本地工作台工具 · <span className="text-gray-300">外部</span> 第三方 MCP Server</span></div>
          <div><span className="text-gray-300">描述</span><span className="ml-2 text-gray-600">metadata.description，功能说明</span></div>
          <div><span className="text-gray-300">上架状态</span><span className="ml-2 text-gray-600"><span className="text-gray-400">draft</span> 开发中 · <span className="text-yellow-400">ready</span> 待审 · <span className="text-blue-400">published</span> 已发布 · <span className="text-green-400">listed</span> 上架 · <span className="text-red-400">deprecated</span> 废弃</span></div>
          <div><span className="text-gray-300">启用</span><span className="ml-2 text-gray-600">开关控制 MCP Server 是否可用。禁用后不可调用</span></div>
          <div><span className="text-gray-300">allowed_tools</span><span className="ml-2 text-gray-600">该 MCP Server 提供的工具数量</span></div>
          <div><span className="text-gray-300">操作</span><span className="ml-2 text-gray-600">测试/详情/编辑/审批/删除/导出</span></div>
        </div>
      </details>

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
            <div className="text-xs text-gray-500 mb-1">签名</div>
            {signResult ? (
              <div className="flex items-center gap-2 text-green-400 text-xs">
                <ShieldCheck size={14} />
                <span className="font-mono">{signResult.slice(0, 16)}...</span>
                <button onClick={() => setSignResult(null)} className="text-gray-500 hover:text-gray-300 ml-2">重新签名</button>
              </div>
            ) : (
              <div className="flex items-start gap-2">
                <textarea
                  className="flex-1 h-14 px-3 py-2 bg-dark-hover border border-dark-border rounded text-xs text-gray-200 placeholder-gray-500 font-mono resize-none"
                  placeholder="粘贴 Ed25519 私钥 PEM"
                  value={signKey}
                  onChange={(e) => setSignKey(e.target.value)}
                />
                <div className="flex flex-col gap-1">
                  <Button variant="primary" size="sm" onClick={handleSign} loading={signing} disabled={!signKey.trim() || signing}>
                    签名
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => { try { window.open('/onboarding', '_blank', 'noopener,noreferrer'); } catch {} }}>
                    生成密钥
                  </Button>
                </div>
              </div>
            )}
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

      {/* Test Config Panel */}
      <Modal
        open={testConfigOpen}
        onClose={() => setTestConfigOpen(false)}
        title={`测试 MCP: ${testServerName}`}
        width={500}
        footer={
          <>
            <Button variant="secondary" onClick={() => setTestConfigOpen(false)}>取消</Button>
            <Button variant="primary" onClick={handleStartTest}>开始测试</Button>
          </>
        }
      >
        <div className="space-y-4 text-sm text-gray-300">
          {testAllowedTools.length > 0 ? (
            <div>
              <label className="block text-xs text-gray-400 mb-1">调用工具</label>
              <select
                value={testToolName}
                onChange={(e) => { setTestToolName(e.target.value); setTestToolParams({}); }}
                className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-200"
              >
                {testAllowedTools.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
          ) : (
            <div>
              <label className="block text-xs text-gray-400 mb-1">调用工具</label>
              <input
                className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-200 placeholder-gray-500"
                value={testToolName}
                onChange={(e) => setTestToolName(e.target.value)}
                placeholder="输入工具名称（留空则默认第一个）"
              />
            </div>
          )}

          {/* Schema-based fields or JSON fallback */}
          {(() => {
            const schema = testToolSchemas[testToolName];
            const props = schema?.properties;
            const required: string[] = schema?.required || [];

            if (props && Object.keys(props).length > 0) {
              return (
                <div className="space-y-3">
                  <label className="block text-xs text-gray-400">参数</label>
                  {Object.entries(props as Record<string, any>).map(([name, spec]: [string, any]) => {
                    const isRequired = required.includes(name);
                    const fieldType = spec.type || 'string';
                    const label = `${name}${isRequired ? ' *' : ''}`;
                    if (fieldType === 'integer' || fieldType === 'number') {
                      return (
                        <div key={name}>
                          <div className="text-xs text-gray-400 mb-1">{label}</div>
                          <input
                            type="number"
                            className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-200"
                            value={testToolParams[name] ?? ''}
                            onChange={(e) => setTestToolParams(p => ({ ...p, [name]: e.target.value === '' ? '' : Number(e.target.value) }))}
                            placeholder={spec.description || `输入 ${name}`}
                          />
                          {spec.description && <div className="text-xs text-gray-500 mt-0.5">{spec.description}</div>}
                        </div>
                      );
                    }
                    return (
                      <div key={name}>
                        <div className="text-xs text-gray-400 mb-1">{label}</div>
                        <input
                          className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-200"
                          value={testToolParams[name] ?? ''}
                          onChange={(e) => setTestToolParams(p => ({ ...p, [name]: e.target.value }))}
                          placeholder={spec.description || `输入 ${name}`}
                        />
                        {spec.description && <div className="text-xs text-gray-500 mt-0.5">{spec.description}</div>}
                      </div>
                    );
                  })}
                </div>
              );
            }

            // Fallback: JSON textarea
            return (
              <div>
                <label className="block text-xs text-gray-400 mb-1">参数（JSON）</label>
                <textarea
                  className="w-full h-24 px-3 py-2 bg-dark-hover border border-dark-border rounded text-xs text-gray-200 placeholder-gray-500 font-mono resize-none"
                  value={testToolArgs}
                  onChange={(e) => setTestToolArgs(e.target.value)}
                  placeholder='{"num": 5}'
                />
                <p className="text-xs text-gray-500 mt-1">留空或 `{}` 表示不传参数</p>
              </div>
            );
          })()}
        </div>
      </Modal>

      {/* Test Execution Viewer Modal */}
      <Modal
        open={testModal}
        onClose={() => { setTestModal(false); setTestRunId(''); }}
        title={`测试 MCP: ${testServerName}`}
        width={900}
        footer={<Button onClick={() => { setTestModal(false); setTestRunId(''); }}>关闭</Button>}
      >
        {testRunId ? (
          <ExecutionViewer
            title={testServerName}
            live
            runId={testRunId}
            height={420}
          />
        ) : (
          <div className="text-sm text-gray-400 text-center py-8">正在启动测试...</div>
        )}
      </Modal>

      <Modal
        open={seedsModalOpen}
        onClose={() => setSeedsModalOpen(false)}
        title="从模板安装 MCP"
        width={600}
        footer={<Button onClick={() => setSeedsModalOpen(false)}>关闭</Button>}
      >
        <div className="space-y-3 text-sm text-gray-300">
          <p className="text-xs text-gray-500">选择一个模板安装到 workspace。安装后可自由编辑配置。</p>
          {seedsLoading ? (
            <div className="text-gray-500 text-center py-4">加载中...</div>
          ) : seeds.length === 0 ? (
            <div className="text-gray-500 text-center py-4">
              暂无可用模板
              <div className="text-[10px] text-gray-600 mt-1">将 server.yaml + policy.yaml 放入 aiPlat-core/core/workspace_seeds/mcps/&lt;id&gt;/ 即可作为模板</div>
            </div>
          ) : (
            seeds.map((s: any) => (
              <div key={s.id} className="flex items-center justify-between p-3 rounded border border-dark-border bg-dark-bg">
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-gray-200">{s.name}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{s.description || s.id}</div>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-dark-hover text-gray-400 mt-1 inline-block">
                    {s.transport || 'sse'}
                  </span>
                </div>
                {s.installed ? (
                  <span className="text-xs text-green-400 ml-3">已安装</span>
                ) : (
                  <Button variant="primary" size="sm" onClick={() => installSeed(s.id)}>安装</Button>
                )}
              </div>
            ))
          )}
        </div>
      </Modal>
    </div>
  );
};

export default WorkspaceMCP;
