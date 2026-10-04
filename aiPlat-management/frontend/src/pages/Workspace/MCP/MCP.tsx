import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Copy, Info, Pencil, Plus, RotateCw, ShieldCheck, Zap, Play, Trash2, Upload } from 'lucide-react';
import { motion } from 'framer-motion';
import { Badge, Table, Switch, Button, Modal, toast, Input } from '../../../components/ui';
import { useWorkspaceMcpStore } from '../../../stores';
import type { McpServer } from '../../../services';
import { workspaceMcpApi, mcpApi } from '../../../services';
import { ExecutionViewer } from '../../../components/ExecutionViewer';
import ExecuteResultPanel from '../../../components/execution/ExecuteResultPanel';
import ExecuteFlowFullscreen from '../../../components/execution/ExecuteFlowFullscreen';
import { RunVerdictBanner, deriveRunVerdict, outputAsText } from '../../../components/execution/runVerdict';
import AddMcpModal from '../../../components/workspace/AddMcpModal';
import McpChatCreateModal from '../../../components/workspace/McpChatCreateModal';
import WorkspacePageGuide from '../../../components/workspace/WorkspacePageGuide';
import EditMcpModal from '../../../components/workspace/EditMcpModal';
import { toastGateError } from '../../../components/ui';
import ImportBar from '../../../components/workspace/ImportBar';
import AssetStatusLegend from '../../../components/workspace/AssetStatusLegend';
import { getSourceLabel, extractProvenance } from '../../../utils/sourceLabel';
import { StatusBadge } from '../../../utils/statusLabel';
import { buildFormParamsFromSchema, buildParamSmokeExamples } from '../../../utils/executionSamples';

const MCP_TEMPLATES = [
  { id: 'http_bridge', name: 'HTTP API 桥接', icon: '🌐', desc: '调用任何 REST/HTTP API', tools: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] },
  { id: 'shell_executor', name: 'Shell 命令执行', icon: '⚡', desc: '每个允许的命令生成独立工具', tools: ['ls', 'cat', 'grep', 'curl', 'ps', '…'] },
  { id: 'file_ops', name: '文件操作', icon: '📁', desc: '读写本地文件系统', tools: ['读', '写', '追', '删', '列', '查'] },
  { id: 'db_query', name: '数据库查询', icon: '🗄️', desc: '查询 SQLite/PostgreSQL/MySQL', tools: ['查询', '列表', '写操作'] },
];

const WorkspaceMCP: React.FC = () => {
  const navigate = useNavigate();
  const { servers, loading, fetchServers, setServerEnabled } = useWorkspaceMcpStore();
  const [search, setSearch] = useState('');
  const [detailModal, setDetailModal] = useState<{ open: boolean; server: McpServer | null }>({ open: false, server: null });
  const [addOpen, setAddOpen] = useState(false);
  const [chatCreateOpen, setChatCreateOpen] = useState(false);
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
  const [testFlowFullscreen, setTestFlowFullscreen] = useState(false);
  const [testResult, setTestResult] = useState<{
    status: string;
    run_id?: string;
    output?: unknown;
    error?: unknown;
    duration_ms?: number;
  } | null>(null);

  // Test config panel state
  const [testConfigOpen, setTestConfigOpen] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [mcpDelete, setMcpDelete] = useState<{ open: boolean; server: any; hard: boolean }>({ open: false, server: null, hard: true });
  const [testToolName, setTestToolName] = useState('');
  const [testToolArgs, setTestToolArgs] = useState('{}');
  const [testAllowedTools, setTestAllowedTools] = useState<string[]>([]);
  const [testToolSchemas, setTestToolSchemas] = useState<Record<string, any>>({});
  const [testToolParams, setTestToolParams] = useState<Record<string, any>>({});

  useEffect(() => {
    fetchServers();
  }, [fetchServers]);

  const filteredServers = servers.filter((s) => {
    if (!search.trim()) return true;
    const q = search.trim().toLowerCase();
    const hay = `${s.name || ''} ${(s as any).display_name || ''} ${s.description || ''} ${(s as any).transport || ''}`.toLowerCase();
    return hay.includes(q);
  });

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
    setTestResult({ status: 'running' });
    setTestFlowFullscreen(true);
    // Use schema-based params if available, otherwise JSON textarea
    const schema = testToolSchemas[testToolName];
    let args: any;
    if (schema?.properties && Object.keys(schema.properties).length > 0) {
      args = { ...testToolParams };
      for (const [k, spec] of Object.entries(schema.properties as Record<string, any>)) {
        const t = String(spec?.type || '').toLowerCase();
        if ((t === 'object' || t === 'array') && typeof args[k] === 'string' && args[k].trim()) {
          try { args[k] = JSON.parse(args[k]); } catch { /* keep string */ }
        }
      }
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
        setTestResult({ status: 'failed', error: data.detail || data.message || `HTTP ${res.status}` });
        setTestFlowFullscreen(false);
        return;
      }
      setTestRunId(data.run_id);
      setTestResult({ status: 'running', run_id: data.run_id });
    } catch (e: any) {
      toast.error(`测试请求失败: ${e?.message || ''}`);
      setTestResult({ status: 'failed', error: e?.message || '测试请求失败' });
      setTestFlowFullscreen(false);
    }
  };

  const finalizeMcpTest = async (runId: string) => {
    try {
      const resp = await fetch(`/api/core/syscalls/events?run_id=${encodeURIComponent(runId)}&limit=50`);
      const data = await resp.json();
      const items = data?.items || data?.events || [];
      const failed = items.find((e: any) => e.status === 'failed' || e.status === 'error');
      const invoke = [...items].reverse().find((e: any) => e.kind === 'mcp' || e.name === 'invoke' || e.result);
      if (failed) {
        setTestResult({
          status: 'failed',
          run_id: runId,
          error: failed.error || failed.result || '测试失败',
          duration_ms: failed.duration_ms,
        });
        return;
      }
      const out = invoke?.result ?? invoke?.result_json ?? items[items.length - 1]?.result;
      setTestResult({
        status: 'completed',
        run_id: runId,
        output: out ?? { message: '测试流程已结束，详见执行轨迹节点。' },
        duration_ms: invoke?.duration_ms,
      });
    } catch {
      setTestResult((prev) => ({
        status: 'completed',
        run_id: runId,
        output: prev?.output ?? { message: '实时事件已结束；若需细节请打开诊断详情。' },
      }));
    }
  };

  const testVerdict = testResult
    ? deriveRunVerdict({
        status: testResult.status,
        error: testResult.error,
        outputText: outputAsText(testResult.output),
      })
    : null;

  const handleDeleteConfirm = async () => {
    const s = mcpDelete.server;
    if (!s || deleting) return;
    setDeleting(s.id);
    try {
      await workspaceMcpApi.deleteServer(s.name);
      toast.success(`已删除 "${s.name}"`);
      setMcpDelete({ open: false, server: null, hard: true });
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
      title: '来源', key: 'source', width: 80, align: 'center' as const,
      render: (_: unknown, record: McpServer) => (
        <span className="text-gray-400 text-xs">{getSourceLabel(extractProvenance(record))}</span>
      ),
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
      key: 'status',
      width: 100,
      render: (_: unknown, record: McpServer) => {
        const st = String((record as any).status || '').toLowerCase();
        return (
          <div className="flex flex-col gap-0.5">
            <StatusBadge status={(record as any).status} />
            {(st === 'draft' || st === 'enabled') && (
              <span className="text-[10px] text-gray-500">盾牌图标 → 提交审批</span>
            )}
          </div>
        );
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
            onClick={() => setMcpDelete({ open: true, server: record, hard: true })}
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
          <p className="text-sm text-gray-500 mt-1">来自 ~/.aiplat/mcps（可编辑；启用前请核对 transport / 策略）</p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="primary" icon={<Plus className="w-4 h-4" />} onClick={() => setAddOpen(true)}>
            创建
          </Button>
          <Button variant="secondary" onClick={() => setChatCreateOpen(true)}>
            对话创建
          </Button>
          <Button variant="secondary" icon={<Upload className="w-4 h-4" />} onClick={() => { loadSeeds(); setSeedsModalOpen(true); }}>
            从模板安装
          </Button>
          <Button variant="secondary" size="sm" icon={<Zap className="w-4 h-4" />} onClick={() => setTemplateModal(true)}>
            从模板创建
          </Button>
          <Button variant="secondary" icon={<ShieldCheck className="w-4 h-4" />} onClick={() => navigate('/approval?type=mcp&status=ready')}>
            资产审批
          </Button>
          <Button icon={<RotateCw className="w-4 h-4" />} onClick={fetchServers} loading={loading}>
            刷新
          </Button>
        </div>
      </div>

      <WorkspacePageGuide
        steps={[
          { title: '创建 / 对话创建', detail: '得到草稿 draft（默认未启用）' },
          { title: '提交审批', detail: '行内盾牌图标：draft → 待审核(ready)' },
          { title: '资产审批', detail: '管理员在「资产审批」点通过 → 已发布；再点上架 → 已上架' },
        ]}
        tip="「待审核」不能在本页点通过。请用顶部「资产审批」（或更多 → 去资产审批）。启用开关与上架状态是两条线。"
      />

      <ImportBar assetType="mcps" alsoScan={['agents', 'skills']} onImported={() => fetchServers()} />

      <div className="flex flex-wrap items-center gap-4">
        <div className="flex-1 min-w-[200px] max-w-md">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索名称或描述..." />
        </div>
      </div>

      <AssetStatusLegend
        kind="mcp"
        howToSubmit="行内盾牌 → 提交审批"
        extraNote="「启用」开关与上架状态独立：禁用后不可测试/调用。"
      />

      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
        <Table columns={columns} data={filteredServers} rowKey="name" loading={loading} emptyText="暂无 MCP Server" />
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
                  <Button variant="ghost" size="sm" onClick={() => { try { window.open('/onboarding?step=sign_keys', '_blank', 'noopener,noreferrer'); } catch {} }}>
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

      <McpChatCreateModal
        open={chatCreateOpen}
        onClose={() => setChatCreateOpen(false)}
        onSuccess={fetchServers}
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
        width={720}
        footer={
          <>
            <Button variant="secondary" onClick={() => setTestConfigOpen(false)}>取消</Button>
            <Button variant="primary" onClick={handleStartTest}>开始测试</Button>
          </>
        }
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-gray-300">
          <div className="space-y-4">
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
                  <div className="text-xs text-gray-500">点右侧「填入」按 inputSchema 写入测试参数，再点「开始测试」。</div>
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
                    if (fieldType === 'object' || fieldType === 'array') {
                      return (
                        <div key={name}>
                          <div className="text-xs text-gray-400 mb-1">{label}</div>
                          <textarea
                            className="w-full h-20 px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-xs text-gray-200 font-mono resize-none"
                            value={typeof testToolParams[name] === 'string' ? testToolParams[name] : (testToolParams[name] != null ? JSON.stringify(testToolParams[name], null, 2) : '')}
                            onChange={(e) => setTestToolParams(p => ({ ...p, [name]: e.target.value }))}
                            placeholder={spec.description || `输入 ${name}（JSON）`}
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
                  placeholder='点右侧「填入」加载测试用例，或直接输入 JSON'
                />
                <p className="text-xs text-gray-500 mt-1">留空或 `{}` 表示不传参数；有 Schema 时请用右侧「填入」。</p>
              </div>
            );
          })()}
          </div>

          <div className="border border-dark-border rounded-lg bg-dark-card p-3 space-y-3">
            <div className="text-sm font-medium text-gray-200">使用说明 / 测试用例</div>
            <div className="text-xs text-gray-400 leading-relaxed whitespace-pre-wrap">
{`### 如何填写
- 选择工具后，点「填入」写入主路径 / 边界异常 / 复杂全量用例。
- 「边界/异常」含空值、不可达 URL 等，用于验收校验与失败路径。`}
            </div>
            {(() => {
              const schema = testToolSchemas[testToolName];
              if (!schema) {
                return <div className="text-xs text-gray-500">暂无 Schema（可手动填写 JSON）。</div>;
              }
              const smoke = buildParamSmokeExamples(schema, testToolName || 'tool', {
                skillHint: `${testToolName || ''} ${testServerName || ''}`,
              });
              return (
                <div className="space-y-2">
                  <div className="text-xs font-medium text-gray-300">测试用例 — 点「填入」写入左侧参数</div>
                  {smoke.map((ex) => (
                    <div key={ex.title} className="flex flex-col gap-1">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-xs text-gray-300 truncate font-medium">{ex.title}</div>
                        <div className="flex gap-2">
                          <Button
                            variant="secondary"
                            onClick={() => {
                              try {
                                const obj = JSON.parse(ex.content);
                                setTestToolParams(buildFormParamsFromSchema(schema, { includeOptional: true }));
                                const flat = (schema as any)?.properties || {};
                                const next: Record<string, any> = {};
                                if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
                                  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
                                    const typ = String(flat[k]?.type || '').toLowerCase();
                                    if ((typ === 'object' || typ === 'array') && typeof v === 'object' && v !== null) {
                                      next[k] = JSON.stringify(v, null, 2);
                                    } else {
                                      next[k] = v;
                                    }
                                  }
                                  setTestToolParams(next);
                                  setTestToolArgs(ex.content);
                                }
                              } catch {
                                setTestToolArgs(ex.content);
                              }
                            }}
                          >
                            填入
                          </Button>
                          <Button variant="secondary" onClick={() => copyText(ex.content)}>复制</Button>
                        </div>
                      </div>
                      <div className="text-xs text-gray-500 truncate" style={{ fontFamily: 'monospace' }}>
                        {ex.content.length > 80 ? `${ex.content.slice(0, 80)}…` : ex.content}
                      </div>
                    </div>
                  ))}
                  <pre className="text-xs text-gray-300 overflow-auto max-h-40 bg-dark-bg border border-dark-border rounded-lg p-3">
                    {smoke.find((e) => e.title.includes('复杂') || e.title.includes('全量'))?.content || smoke[0]?.content || '{}'}
                  </pre>
                </div>
              );
            })()}
          </div>
        </div>
      </Modal>

      {/* Test result + flow (Agent-aligned) */}
      <Modal
        open={testModal}
        onClose={() => { setTestModal(false); setTestRunId(''); setTestResult(null); setTestFlowFullscreen(false); }}
        title={`测试 MCP: ${testServerName}`}
        width={980}
        footer={<Button onClick={() => { setTestModal(false); setTestRunId(''); setTestResult(null); setTestFlowFullscreen(false); }}>关闭</Button>}
      >
        {!testFlowFullscreen && testResult && (
          <ExecuteResultPanel
            result={testResult}
            onOpenFlow={testRunId ? () => setTestFlowFullscreen(true) : undefined}
          />
        )}
        {!testFlowFullscreen && testRunId && !testResult?.output && testResult?.status === 'running' && (
          <div className="mt-3">
            <ExecutionViewer title={testServerName} live runId={testRunId} height={360} />
            <div className="mt-3">
              <Button variant="primary" onClick={() => setTestFlowFullscreen(true)}>▶ 查看执行流程（全屏）</Button>
            </div>
          </div>
        )}
        {!testRunId && testResult?.status === 'running' && (
          <div className="text-sm text-gray-400 text-center py-8">正在启动测试...</div>
        )}
        {!testFlowFullscreen && testResult?.status === 'failed' && !testRunId && (
          <div className="text-sm text-red-300 py-4">{String(testResult.error || '测试失败')}</div>
        )}
      </Modal>

      <ExecuteFlowFullscreen
        open={!!(testFlowFullscreen && testRunId)}
        runId={testRunId}
        title={`MCP 测试流程 · ${testServerName}`}
        verdict={testVerdict}
        status={testResult?.status}
        running={testResult?.status === 'running'}
        onClose={() => setTestFlowFullscreen(false)}
        onLiveStatusChange={async (st) => {
          if (st !== 'done' || !testRunId) return;
          if (testResult?.status === 'completed' || testResult?.status === 'failed') return;
          await finalizeMcpTest(testRunId);
        }}
        footer={
          testResult && testVerdict ? (
            <div className="space-y-2">
              <RunVerdictBanner verdict={testVerdict} />
              {outputAsText(testResult.output) ? (
                <pre className="text-xs text-gray-300 overflow-auto max-h-40 bg-dark-bg border border-dark-border rounded-lg p-3 whitespace-pre-wrap">
                  {outputAsText(testResult.output).slice(0, 4000)}
                </pre>
              ) : null}
            </div>
          ) : null
        }
      />

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
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {seeds.map((s: any) => {
              const icon = s.metadata?.icon || s.id;
              const desc = s.metadata?.description || s.description || s.id;
              const config = s.metadata?.config || {};
              const installCmd = s.metadata?.install_command || '';
              return (
                <div key={s.id} className="flex flex-col p-3 rounded border border-dark-border bg-dark-bg hover:border-primary/30 transition-colors">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-lg">{icon === 'notion' ? '📋' : icon === 'feishu' ? '🐦' : icon === 'github' ? '🐙' : '📦'}</span>
                    <span className="font-medium text-gray-200 text-sm">{s.name}</span>
                  </div>
                  <div className="text-xs text-gray-500 mb-2 min-h-[32px]">{desc}</div>
                  {Object.keys(config).length > 0 && (
                    <div className="text-[10px] text-gray-600 mb-2 space-y-0.5">
                      {Object.entries(config).map(([k, v]: [string, any]) => (
                        <div key={k} className="flex items-center gap-1">
                          <span className="text-gray-500">{v.label || k}</span>
                          <span className={`px-1 rounded ${v.required ? 'bg-red-900/20 text-red-400' : 'bg-gray-800 text-gray-500'}`}>
                            {v.required ? '必填' : '可选'}
                          </span>
                          {v.type === 'secret' && <span className="text-gray-600">🔒</span>}
                        </div>
                      ))}
                    </div>
                  )}
                  {installCmd && (
                    <div className="text-[10px] text-gray-600 font-mono bg-dark-hover rounded px-1.5 py-0.5 mb-2 truncate">{installCmd}</div>
                  )}
                  <div className="flex gap-2 mt-auto pt-2 border-t border-dark-border/50">
                    {s.installed ? (
                      <span className="text-xs text-green-400">✅ 已安装</span>
                    ) : (
                      <Button variant="primary" size="sm" className="text-xs flex-1" onClick={() => installSeed(s.id)}>
                        ▶ 一键安装
                      </Button>
                    )}
                    <Button variant="ghost" size="sm" className="text-xs" onClick={async () => {
                      try {
                        if (!s.installed) await installSeed(s.id);
                        const r = await workspaceMcpApi.discoverTools(s.id);
                        toast.success(`${s.name}: ${r.tools?.length || 0} 个工具可用`);
                      } catch { toast.error(`${s.name}: 连接失败`); }
                    }}>
                      🔌 测试
                    </Button>
                  </div>
                </div>
              );
            })}
            </div>
          )}
        </div>
      </Modal>

      <Modal open={mcpDelete.open} onClose={() => setMcpDelete({ open: false, server: null, hard: true })} title="确认删除"
        footer={
          <>
            <Button onClick={() => setMcpDelete({ open: false, server: null, hard: true })}>取消</Button>
            <Button variant="danger" onClick={handleDeleteConfirm} loading={!!deleting}>确认删除</Button>
          </>
        }>
        <p className="text-sm text-gray-300 mb-3">将对 MCP "{mcpDelete.server?.name}" 执行删除操作：</p>
        <p className="text-xs text-gray-500 mb-2">此操作不可撤销，将删除整个配置目录。</p>
      </Modal>
    </div>
  );
};

export default WorkspaceMCP;
