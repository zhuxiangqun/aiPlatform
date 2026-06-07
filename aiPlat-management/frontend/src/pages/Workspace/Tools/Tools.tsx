import React, { useEffect, useState, useCallback } from 'react';
import { Plus, RotateCw, Trash2, Pencil, Play, Key, Download, Clock, RefreshCw } from 'lucide-react';
import { Badge, Table, Button, Modal, toast, Select } from '../../../components/ui';
import { toastGateError } from '../../../components/ui';
import { useWorkspaceToolStore } from '../../../stores';
import { ToolDetailModal, ExecuteToolModal } from '../../../components/core';
import AddToolModal from '../../../components/workspace/AddToolModal';
import { workspaceToolApi, toolApi } from '../../../services';
import type { ToolInfo } from '../../../services';
import { getSourceLabel, extractProvenance } from '../../../utils/sourceLabel';
import { TOOL_CATEGORIES } from '../../../utils/categoryConfig';

const governanceBadge = (record: any) => {
  const prov = record?.provenance || {};
  if (prov?.signature_verified === true) return <Badge variant={'success' as any}>已验签</Badge>;
  if (prov?.signature) return <Badge variant={'info' as any}>已签名</Badge>;
  return <Badge variant={'default' as any}>未签名</Badge>;
};

const TOOL_CATEGORY_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'general', label: '通用' },
  { value: 'execution', label: '执行' },
  { value: 'retrieval', label: '检索' },
  { value: 'analysis', label: '分析' },
  { value: 'generation', label: '生成' },
];

const WorkspaceTools: React.FC = () => {
  const { tools, loading, fetchTools, deleteTool, signTool, reloadTool, saveSource } = useWorkspaceToolStore();
  const [categoryFilter, setCategoryFilter] = useState<string>('');

  const [detailTool, setDetailTool] = useState<ToolInfo | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const [addModalOpen, setAddModalOpen] = useState(false);

  const [executeTool, setExecuteTool] = useState<ToolInfo | null>(null);
  const [executeOpen, setExecuteOpen] = useState(false);

  // Edit modal state
  const [editTool, setEditTool] = useState<ToolInfo | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [editSource, setEditSource] = useState('');
  const [editLoading, setEditLoading] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editSyntaxError, setEditSyntaxError] = useState<string | null>(null);

  // Execution history modal state
  const [historyTool, setHistoryTool] = useState<ToolInfo | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyStats, setHistoryStats] = useState<any>(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Sign modal state
  const [signModal, setSignModal] = useState<{ open: boolean; tool: ToolInfo | null }>({ open: false, tool: null });
  const [signKey, setSignKey] = useState('');
  const [signing, setSigning] = useState(false);

  const [batchSignOpen, setBatchSignOpen] = useState(false);
  const [batchSignKey, setBatchSignKey] = useState('');
  const [batchSigning, setBatchSigning] = useState(false);
  const [batchResult, setBatchResult] = useState<{ total: number; signed: number; failed: number } | null>(null);

  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; tool: ToolInfo | null }>({ open: false, tool: null });

  const [seedsModalOpen, setSeedsModalOpen] = useState(false);
  const [seeds, setSeeds] = useState<any[]>([]);
  const [seedsLoading, setSeedsLoading] = useState(false);
  const [installingSeed, setInstallingSeed] = useState<string | null>(null);

  useEffect(() => { fetchTools(); }, [fetchTools]);

  // --- Handlers ---

  const handleDelete = async () => {
    if (!deleteConfirm.tool?.name) return;
    try {
      await deleteTool(deleteConfirm.tool.name);
      toast.success('已删除');
      setDeleteConfirm({ open: false, tool: null });
    } catch (e: any) { toast.error('删除失败', e?.detail || String(e)); }
  };

  const handleSign = async () => {
    if (!signModal.tool?.name || !signKey.trim()) return;
    setSigning(true);
    try {
      await signTool(signModal.tool.name, signKey.trim());
      toast.success('签名成功');
      setSignKey('');
      setSignModal({ open: false, tool: null });
    } catch (e: any) {
      toastGateError(e, '签名失败');
    } finally { setSigning(false); }
  };

  const handleBatchSign = async () => {
    if (!batchSignKey.trim()) return;
    setBatchSigning(true);
    setBatchResult(null);
    let signed = 0;
    let failed = 0;
    const total = tools.filter(t => !t.provenance?.signature_verified).length;

    for (const tool of tools) {
      if (tool.provenance?.signature_verified) continue;
      try {
        await signTool(tool.name, batchSignKey.trim());
        signed++;
      } catch {
        failed++;
      }
    }
    setBatchResult({ total, signed, failed });
    setBatchSigning(false);
    if (failed === 0 && total > 0) toast.success(`批量签名完成：${signed}/${total}`);
    else if (total > 0) toast.warning(`批量签名：${signed} 成功, ${failed} 失败`);
  };

  // Open edit modal — fetch source code from server
  const handleOpenEdit = async (record: ToolInfo) => {
    setEditTool(record);
    setEditOpen(true);
    setEditSource('');
    setEditSyntaxError(null);
    setEditLoading(true);
    try {
      const r = await workspaceToolApi.getSource(record.name);
      setEditSource(r.source || '');
    } catch {
      setEditSource(`# Failed to load source for ${record.name}\n# Please check file permissions.`);
    } finally { setEditLoading(false); }
  };

  // Validate source before save
  const handleEditSave = async () => {
    if (!editTool?.name) return;
    setEditSyntaxError(null);
    setEditSaving(true);
    try {
      await saveSource(editTool.name, editSource);
      toast.success('已保存并重新注册');
      setEditOpen(false);
      setEditTool(null);
      fetchTools();
    } catch (e: any) {
      const detail = e?.detail || String(e);
      if (detail.includes('SyntaxError') || detail.includes('syntax error') || detail.includes('line')) {
        setEditSyntaxError(detail);
      } else {
        toast.error('保存失败', detail);
      }
    } finally { setEditSaving(false); }
  };

  // Open execution history modal
  const handleOpenHistory = async (record: ToolInfo) => {
    setHistoryTool(record);
    setHistoryOpen(true);
    setHistoryStats(null);
    setHistoryLoading(true);
    try {
      const stats = await toolApi.getStats();
      setHistoryStats(stats?.[record.name] || null);
    } catch {
      setHistoryStats(null);
    } finally { setHistoryLoading(false); }
  };

  // Export tool source file
  const handleExport = (record: ToolInfo) => {
    const filePath = record.provenance?.tool_path;
    if (!filePath) {
      toast.error('无法定位文件路径');
      return;
    }
    // trigger download directly via API
    workspaceToolApi.getSource(record.name).then(r => {
      const blob = new Blob([r.source], { type: 'text/x-python' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${record.name}.py`;
      a.click();
      URL.revokeObjectURL(url);
    }).catch(() => toast.error('导出失败'));
  };

  // Reload tool from disk
  const handleReload = async (record: ToolInfo) => {
    try {
      await reloadTool(record.name);
      toast.success(`${record.name} 已重载`);
    } catch (e: any) {
      toast.error('重载失败', e?.detail || String(e));
    }
  };

  const loadSeeds = useCallback(async () => {
    setSeedsLoading(true);
    try {
      const res = await toolApi.list({ limit: 200 });
      const engineTools = (res.tools || []).filter((t: any) => t.protected === true || t.scope === 'engine');
      setSeeds(engineTools);
    } catch {
      setSeeds([]);
    } finally { setSeedsLoading(false); }
  }, []);

  const installSeed = async (seed: any) => {
    setInstallingSeed(seed.name);
    try {
      const code = `# ${seed.name} - installed from template
# Description: ${seed.description || 'N/A'}

TOOL_DEF = {
    "id": "${seed.name}",
    "name": "${seed.name}",
    "description": "${seed.description || ''}",
    "parameters": {},
    "execute": None,  # TODO: implement execute function
}
`;
      await toolApi.create({ name: seed.name, description: seed.description || '', code });
      toast.success(`已安装: ${seed.name}`);
    } catch (e: any) {
      if (String(e?.detail || '').includes('already exists')) {
        toast.warning(`${seed.name} 已存在`);
      } else {
        toast.error(`安装失败: ${e?.detail || String(e)}`);
      }
    } finally { setInstallingSeed(null); }
  };

  const filteredTools = tools.filter(t => {
    if (categoryFilter && t.category !== categoryFilter) return false;
    return true;
  });

  const unsignedCount = tools.filter(t => !t.provenance?.signature_verified).length;

  const columns = [
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (name: string, record: ToolInfo) => (
        <button onClick={() => { setDetailTool(record); setDetailOpen(true); }}
          className="text-primary hover:text-primary-hover font-medium text-left">{name}</button>
      ),
    },
    {
      title: '分类', dataIndex: 'category', key: 'category', width: 90,
      render: (v: string) => {
        const cfg = TOOL_CATEGORIES[v];
        return v ? <span className={`px-1.5 py-0.5 rounded text-xs border ${cfg?.color || 'bg-dark-hover text-gray-300'}`}>{cfg?.text || v}</span> : <span className="text-gray-500 text-xs">-</span>;
      },
    },
    { title: '描述', dataIndex: 'description', key: 'description', render: (v: string) => <span className="text-gray-400 text-xs truncate block max-w-[200px]">{v || '-'}</span> },
    {
      title: '来源', key: 'source', width: 80,
      render: (_: unknown, record: ToolInfo) => (
        <span className="text-gray-400 text-xs">{getSourceLabel(extractProvenance(record))}</span>
      ),
    },
    {
      title: '上架状态', key: 'status', width: 80,
      render: (_: unknown, record: any) => {
        if (record.available === false) return <Badge variant={'error' as any}>不可用</Badge>;
        return <Badge variant={'success' as any}>可用</Badge>;
      },
    },
    {
      title: '治理', key: 'governance', width: 90, render: (_: unknown, record: any) => governanceBadge(record),
    },
    {
      title: '操作', key: 'actions', width: 160, align: 'center' as const,
      render: (_: unknown, record: ToolInfo) => (
        <div className="flex items-center justify-center gap-0.5">
          <button onClick={() => { setExecuteTool(record); setExecuteOpen(true); }}
            className="p-1.5 rounded-lg text-success hover:bg-success-light transition-colors" title="执行">
            <Play size={14} />
          </button>
          <button onClick={() => handleOpenEdit(record)}
            className="p-1.5 rounded-lg text-blue-400 hover:bg-dark-hover transition-colors" title="编辑源码">
            <Pencil size={14} />
          </button>
          <button onClick={() => handleOpenHistory(record)}
            className="p-1.5 rounded-lg text-amber-400 hover:bg-amber-400/10 transition-colors" title="执行历史">
            <Clock size={14} />
          </button>
          <button onClick={() => handleReload(record)}
            className="p-1.5 rounded-lg text-teal-400 hover:bg-teal-400/10 transition-colors" title="重载">
            <RefreshCw size={14} />
          </button>
          <button onClick={() => handleExport(record)}
            className="p-1.5 rounded-lg text-purple-400 hover:bg-purple-400/10 transition-colors" title="导出为.py文件">
            <Download size={14} />
          </button>
          <button onClick={() => setSignModal({ open: true, tool: record })}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors" title="签名">
            <Key size={14} />
          </button>
          <button onClick={() => setDeleteConfirm({ open: true, tool: record })}
            className="p-1.5 rounded-lg text-error hover:bg-error-light transition-colors" title="删除">
            <Trash2 size={14} />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">应用库 Tool</h1>
          <p className="text-sm text-gray-500 mt-1">来自 ~/.aiplat/tools（可编辑源码、在线执行、签名管理）</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Select
              placeholder="分类筛选"
              value={categoryFilter}
              onChange={(v: string) => setCategoryFilter(v)}
              options={TOOL_CATEGORY_OPTIONS}
              className="w-28"
            />
          </div>
          <Button icon={<Plus className="w-4 h-4" />} variant="primary" onClick={() => setAddModalOpen(true)}>创建</Button>
          <Button variant="secondary" onClick={() => { setSeedsModalOpen(true); if (seeds.length === 0) loadSeeds(); }}>从模板安装</Button>
          {unsignedCount > 0 && (
            <Button variant="secondary" onClick={() => setBatchSignOpen(true)}>批量签名 ({unsignedCount})</Button>
          )}
          <Button icon={<RotateCw className="w-4 h-4" />} onClick={() => fetchTools()} loading={loading}>刷新</Button>
        </div>
      </div>

      {/* Table */}
      <div className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
        <Table columns={columns} data={filteredTools} rowKey="name" loading={loading} emptyText="暂无 workspace 工具，点击「创建」或「从模板安装」添加" />
      </div>

      {/* Detail Modal */}
      <ToolDetailModal open={detailOpen} tool={detailTool} onClose={() => { setDetailOpen(false); setDetailTool(null); }} />

      {/* Execute Modal */}
      <ExecuteToolModal open={executeOpen} tool={executeTool} onClose={() => { setExecuteOpen(false); setExecuteTool(null); }} />

      {/* ============================== EDIT MODAL ============================== */}
      <Modal open={editOpen} onClose={() => { setEditOpen(false); setEditTool(null); }}
        title={`编辑源码：${editTool?.name || ''}`} width={850}
        footer={
          <div className="flex gap-2 justify-between items-center w-full">
            {editSyntaxError ? (
              <span className="text-xs text-error truncate max-w-[400px]">{editSyntaxError}</span>
            ) : (
              <span className="text-xs text-gray-500">编辑 Python 源码，保存时自动校验语法并重新注册</span>
            )}
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => setEditOpen(false)}>取消</Button>
              <Button variant="primary" onClick={handleEditSave} loading={editSaving} disabled={!editSource.trim()}>
                保存 & 重载
              </Button>
            </div>
          </div>
        }>
        <div className="space-y-3 text-sm text-gray-300">
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <label className="block text-xs text-gray-400 mb-1">名称（只读）</label>
              <input className="w-full px-3 py-2 bg-dark-bg border border-dark-border rounded text-sm text-gray-400 cursor-not-allowed"
                value={editTool?.name || ''} readOnly />
            </div>
            <div className="w-40">
              <label className="block text-xs text-gray-400 mb-1">分类</label>
              <Select
                value={editTool?.category || 'general'}
                onChange={(v: string) => { if (editTool) setEditTool({ ...editTool, category: v }); }}
                options={TOOL_CATEGORY_OPTIONS.filter(c => c.value !== '')}
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Python 源码
              {editLoading && <span className="text-gray-500 ml-2">加载中...</span>}
            </label>
            <textarea
              className={`w-full h-[420px] px-4 py-3 bg-dark-bg border rounded text-sm font-mono leading-relaxed resize-none
                ${editSyntaxError ? 'border-error text-gray-200' : 'border-dark-border text-gray-200'}
                placeholder-gray-600`}
              value={editSource}
              onChange={(e) => { setEditSource(e.target.value); setEditSyntaxError(null); }}
              placeholder="# 加载中..."
              spellCheck={false}
            />
            {editSyntaxError && (
              <div className="mt-2 p-2 bg-red-900/20 border border-red-800/40 rounded text-xs text-red-300 font-mono whitespace-pre-wrap">
                {editSyntaxError}
              </div>
            )}
          </div>
        </div>
      </Modal>

      {/* ============================== EXECUTION HISTORY MODAL ============================== */}
      <Modal open={historyOpen} onClose={() => { setHistoryOpen(false); setHistoryTool(null); }}
        title={`执行历史：${historyTool?.name || ''}`} width={560}
        footer={<Button onClick={() => { setHistoryOpen(false); setHistoryTool(null); }}>关闭</Button>}>
        <div className="space-y-4 text-sm text-gray-300">
          {historyLoading ? (
            <p className="text-gray-500 text-center py-6">加载中...</p>
          ) : historyStats ? (
            <div className="grid grid-cols-3 gap-3">
              <div className="text-center p-3 rounded bg-dark-hover border border-dark-border">
                <div className="text-lg font-semibold text-success">{historyStats.call_count ?? 0}</div>
                <div className="text-xs text-gray-500 mt-1">总调用</div>
              </div>
              <div className="text-center p-3 rounded bg-dark-hover border border-dark-border">
                <div className="text-lg font-semibold text-blue-400">{historyStats.success_count ?? 0}</div>
                <div className="text-xs text-gray-500 mt-1">成功</div>
              </div>
              <div className="text-center p-3 rounded bg-dark-hover border border-dark-border">
                <div className="text-lg font-semibold text-error">{historyStats.error_count ?? 0}</div>
                <div className="text-xs text-gray-500 mt-1">失败</div>
              </div>
            </div>
          ) : (
            <p className="text-gray-500 text-center py-6">暂无执行记录</p>
          )}
          {historyStats && (
            <div className="grid grid-cols-2 gap-3">
              <div className="text-center p-3 rounded bg-dark-hover border border-dark-border">
                <div className="text-sm font-semibold text-gray-200">{historyStats.avg_latency != null ? historyStats.avg_latency.toFixed(1) + 'ms' : '-'}</div>
                <div className="text-xs text-gray-500 mt-1">平均延迟</div>
              </div>
              <div className="text-center p-3 rounded bg-dark-hover border border-dark-border">
                <div className="text-sm font-semibold text-gray-200">{historyStats.total_latency != null ? (historyStats.total_latency / 1000).toFixed(1) + 's' : '-'}</div>
                <div className="text-xs text-gray-500 mt-1">累计耗时</div>
              </div>
            </div>
          )}
        </div>
      </Modal>

      {/* Sign Modal */}
      <Modal open={signModal.open} onClose={() => setSignModal({ open: false, tool: null })}
        title={`签名：${signModal.tool?.name || ''}`} width={500}
        footer={<Button onClick={() => setSignModal({ open: false, tool: null })}>关闭</Button>}>
        <div className="space-y-3 text-sm text-gray-300">
          <p className="text-xs text-gray-500">粘贴 Ed25519 私钥为 Tool 签名。签名后系统会在注册时自动验签。</p>
          <div className="flex items-start gap-2">
            <textarea className="flex-1 h-20 px-3 py-2 bg-dark-hover border border-dark-border rounded text-xs text-gray-200 placeholder-gray-500 font-mono resize-none"
              placeholder="粘贴 Ed25519 私钥 PEM" value={signKey} onChange={(e) => setSignKey(e.target.value)} />
            <Button variant="primary" size="sm" onClick={handleSign} loading={signing} disabled={!signKey.trim() || signing}>签名</Button>
          </div>
        </div>
      </Modal>

      {/* Batch Sign Modal */}
      <Modal open={batchSignOpen} onClose={() => { setBatchSignOpen(false); setBatchResult(null); }}
        title="批量签名" width={500}
        footer={
          <div className="flex gap-2 justify-end">
            <Button variant="secondary" onClick={() => { setBatchSignOpen(false); setBatchResult(null); }}>关闭</Button>
            <Button variant="primary" onClick={handleBatchSign} loading={batchSigning} disabled={!batchSignKey.trim()}>
              {batchSigning ? '签名中...' : `一键签名 (${tools.filter(t => !t.provenance?.signature_verified).length})`}
            </Button>
          </div>
        }>
        <div className="space-y-3 text-sm text-gray-300">
          <p className="text-xs text-gray-500">输入 Ed25519 私钥，一键为所有未验签的工具签名。</p>
          <textarea className="w-full h-24 px-3 py-2 bg-dark-hover border border-dark-border rounded text-xs text-gray-200 placeholder-gray-500 font-mono resize-none"
            placeholder="粘贴 Ed25519 私钥 PEM" value={batchSignKey} onChange={(e) => setBatchSignKey(e.target.value)} />
          {batchResult && (
            <div className="p-3 rounded bg-dark-hover border border-dark-border">
              <p className="text-xs text-gray-400">结果：<span className="text-success">{batchResult.signed} 成功</span>
                {batchResult.failed > 0 && <span className="text-error ml-2">{batchResult.failed} 失败</span>}
                <span className="text-gray-500 ml-2">/ 总计 {batchResult.total}</span></p>
            </div>
          )}
        </div>
      </Modal>

      {/* Delete Confirm Modal */}
      <Modal open={deleteConfirm.open} onClose={() => setDeleteConfirm({ open: false, tool: null })}
        title="确认删除" width={440}
        footer={
          <div className="flex gap-2 justify-end">
            <Button variant="secondary" onClick={() => setDeleteConfirm({ open: false, tool: null })}>取消</Button>
            <Button variant="danger" onClick={handleDelete}>确认删除</Button>
          </div>
        }>
        <p className="text-gray-400 text-sm">确定要删除 Tool "{deleteConfirm.tool?.name}" 吗？将删除对应的 .py 文件，不可撤销。</p>
      </Modal>

      {/* Seeds/Install from Template Modal */}
      <Modal open={seedsModalOpen} onClose={() => setSeedsModalOpen(false)}
        title="从模板安装" width={680}
        footer={<Button variant="secondary" onClick={() => setSeedsModalOpen(false)}>关闭</Button>}>
        <div className="space-y-3">
          <p className="text-xs text-gray-500">从引擎内置工具中选择安装到 workspace。安装后可在 workspace 中编辑和管理。</p>
          {seedsLoading ? (
            <p className="text-gray-400 text-sm py-4 text-center">加载中...</p>
          ) : seeds.length === 0 ? (
            <p className="text-gray-500 text-sm py-4 text-center">暂无可安装的模板</p>
          ) : (
            <div className="max-h-80 overflow-y-auto space-y-2">
              {seeds.map((seed: any) => (
                <div key={seed.name} className="flex items-center justify-between p-3 bg-dark-hover border border-dark-border rounded">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-200 font-medium">{seed.name}</p>
                    <p className="text-xs text-gray-500 truncate">{seed.description || '-'}</p>
                  </div>
                  <Button size="sm" variant="primary" loading={installingSeed === seed.name}
                    onClick={() => installSeed(seed)} disabled={installingSeed !== null}>
                    安装
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>

      <AddToolModal open={addModalOpen} onClose={() => setAddModalOpen(false)}
        onSuccess={() => { fetchTools(); setAddModalOpen(false); }} />
    </div>
  );
};

export default WorkspaceTools;
