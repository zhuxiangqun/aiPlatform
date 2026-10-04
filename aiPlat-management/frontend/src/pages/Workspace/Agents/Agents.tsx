import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, RotateCw, Upload, Key, Search, Zap, ShieldCheck } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Table, Select, Button, Modal, toast, Input } from '../../../components/ui';
import { useWorkspaceAgentStore } from '../../../stores';
import { workspaceAgentApi, type Agent } from '../../../services';
import AddAgentModal from '../../../components/workspace/AddAgentModal';
import AgentChatCreateModal from '../../../components/workspace/AgentChatCreateModal';
import WorkspacePageGuide from '../../../components/workspace/WorkspacePageGuide';
import EditAgentModal from '../../../components/workspace/EditAgentModal';
import ExecuteAgentModal from '../../../components/ExecuteAgentModal';
import AgentDetailModal from '../../../components/workspace/AgentDetailModal';
import AgentVersionsModal from '../../../components/workspace/AgentVersionsModal';
import AgentHistoryModal from '../../../components/workspace/AgentHistoryModal';
import AgentRowActions from '../../../components/workspace/AgentRowActions';
import AssetStatusLegend from '../../../components/workspace/AssetStatusLegend';
import ImportBar from '../../../components/workspace/ImportBar';
import { ChatPanel } from '../../../components/core';
import { getSourceLabel, extractProvenance } from '../../../utils/sourceLabel';
import { StatusBadge } from '../../../utils/statusLabel';
import { reportPageData, clearPageData } from '../../../lib/pageDataBridge';

const WorkspaceAgents: React.FC = () => {
  const navigate = useNavigate();
  const { agents, loading, fetchAgents, startAgent, stopAgent, deleteAgent } = useWorkspaceAgentStore();
  const [typeFilter, setTypeFilter] = useState<string | undefined>();
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [search, setSearch] = useState('');
  const [seedsModalOpen, setSeedsModalOpen] = useState(false);
  const [seeds, setSeeds] = useState<any[]>([]);
  const [seedsLoading, setSeedsLoading] = useState(false);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [addMode, setAddMode] = useState<'manual' | 'auto'>('manual');
  const [chatCreateOpen, setChatCreateOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [editInitialTab, setEditInitialTab] = useState('basic');
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [versionsModalOpen, setVersionsModalOpen] = useState(false);
  const [historyModalOpen, setHistoryModalOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; agent: Agent | null; hard: boolean }>({ open: false, agent: null, hard: false });
  const [deleting, setDeleting] = useState(false);
  const [testAllRunning, setTestAllRunning] = useState(false);
  const [testAllResults, setTestAllResults] = useState<{ agentId: string; status: string; ok: boolean }[]>([]);
  const [testAllOpen, setTestAllOpen] = useState(false);
  const [chatAgent, setChatAgent] = useState<Agent | null>(null);
  const [deduping, setDeduping] = useState(false);

  // Batch signing state
  const [batchSignOpen, setBatchSignOpen] = useState(false);
  const [batchSignKey, setBatchSignKey] = useState('');
  const [batchSigning, setBatchSigning] = useState(false);
  const [batchResult, setBatchResult] = useState<{ total: number; signed: number; failed: number } | null>(null);

  // ── Smart Agent Router ──
  const [routeInput, setRouteInput] = useState('');
  const [routeResult, setRouteResult] = useState<{ intent: string; confidence: number; target: string; has_data: boolean } | null>(null);
  const [routeLoading, setRouteLoading] = useState(false);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const handleChatOpen = (agent: Agent) => {
    setChatAgent(agent);
    setSelectedAgent(agent);
  };

  const handleRoute = async () => {
    if (!routeInput.trim()) return;
    setRouteLoading(true);
    setRouteResult(null);
    try {
      const res: any = await workspaceAgentApi.classify({ message: routeInput });
      setRouteResult({ intent: res.intent, confidence: res.confidence, target: res.primary_route?.target || '', has_data: true });
      // Auto-select matching agent
      const match = agents.find(a => a.name === res.primary_route?.target || a.display_name === res.primary_route?.target);
      if (match) {
        setSelectedAgent(match);
        setExecuteModalOpen(true);
        setRouteInput('');
        toast.success(`已匹配: ${match.name}`);
      }
    } catch {
      toast.error('路由服务不可用');
    } finally {
      setRouteLoading(false);
    }
  };

  const handleTestAll = async () => {
    setTestAllRunning(true);
    setTestAllOpen(true);
    setTestAllResults([]);
    const runnable = agents.filter(a => a.status === 'running' || a.status === 'ready');
    const results: { agentId: string; status: string; ok: boolean }[] = [];
    for (const a of runnable) {
      try {
        const r: any = await workspaceAgentApi.execute(a.id, { input: { message: 'Say hello in one sentence.' } });
        results.push({ agentId: a.display_name || a.name || a.id, status: (r as any)?.status || '?', ok: (r as any)?.status === 'completed' });
      } catch {
        results.push({ agentId: a.display_name || a.name || a.id, status: 'error', ok: false });
      }
      setTestAllResults([...results]);
    }
    setTestAllRunning(false);
  };

  const handleStart = async (agent: Agent) => {
    try {
      await startAgent(agent.id);
      toast.success(`Agent "${agent.name}" 已启动`);
    } catch {
      toast.error('启动失败');
    }
  };

  const handleStop = async (agent: Agent) => {
    try {
      await stopAgent(agent.id);
      toast.success(`Agent "${agent.name}" 已停止`);
    } catch {
      toast.error('停止失败');
    }
  };

  const handleExportPlugin = async (agent: any) => {
    try {
      const name = (agent.name || agent.id || 'agent').replace(/\s+/g, '_');
      const res = await fetch('/api/core/workspace/packages/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          version: '0.1.0',
          description: (agent as any).metadata?.description || agent.description || '',
          resources: [{ kind: 'agent', id: agent.id }],
        }),
      });
      if (!res.ok) { toast.error('导出失败'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `${name}.zip`; a.click();
      URL.revokeObjectURL(url);
      toast.success(`已导出 ${name}`);
    } catch (e: any) { toast.error(`导出失败: ${e?.message || ''}`); }
  };

  const handleDelete = async () => {
    if (!deleteConfirm.agent || deleting) return;
    setDeleting(true);
    try {
      if (deleteConfirm.hard) {
        await deleteAgent(deleteConfirm.agent.id);
        toast.success('Agent已删除');
      } else {
        await workspaceAgentApi.deprecate(deleteConfirm.agent.id);
        toast.success(`Agent "${deleteConfirm.agent.name}" 已标记为废弃`);
        fetchAgents({ agent_type: typeFilter, status: statusFilter });
      }
      setDeleteConfirm({ open: false, agent: null, hard: false });
    } catch (e: any) {
      toast.error('操作失败', e?.message || String(e));
    } finally {
      setDeleting(false);
    }
  };

  const handleDedupe = async () => {
    if (deduping) return;
    setDeduping(true);
    try {
      const r: any = await workspaceAgentApi.dedupe();
      const n = Number(r?.removed_count ?? 0);
      toast.success(
        n > 0
          ? `已清理 ${n} 个重复 Agent，保留 ${r?.remaining ?? '?'} 个`
          : '没有发现可合并的重复 Agent',
      );
      fetchAgents({ agent_type: typeFilter, status: statusFilter });
    } catch (e: any) {
      toast.error('清理失败', e?.detail || e?.message || String(e));
    } finally {
      setDeduping(false);
    }
  };

  const handleSubmitForReview = async (agent: Agent) => {
    try {
      await workspaceAgentApi.submitForReview(agent.id);
      toast.success(`Agent "${agent.name}" 已提交审批`);
      fetchAgents({ agent_type: typeFilter, status: statusFilter });
    } catch (e: any) {
      toast.error('提交失败', e?.message || String(e));
    }
  };

  const handleRestore = async (agent: Agent) => {
    try {
      await workspaceAgentApi.restore(agent.id);
      toast.success(`Agent "${agent.name}" 已恢复`);
      fetchAgents({ agent_type: typeFilter, status: statusFilter });
    } catch (e: any) {
      toast.error('恢复失败', e?.message || String(e));
    }
  };

  const handleBatchSign = async () => {
    if (!batchSignKey.trim()) return;
    setBatchSigning(true);
    setBatchResult(null);
    let signed = 0;
    let failed = 0;
    const signable = agents.filter(a => {
      const meta = (a as any)?.metadata || {};
      const prov = meta?.provenance || {};
      if (prov?.signature_verified) return false;
      return true;
    });
    const total = signable.length;

    for (const agent of signable) {
      try {
        await workspaceAgentApi.sign(agent.id, { private_key: batchSignKey.trim() });
        signed++;
      } catch {
        failed++;
      }
    }
    setBatchResult({ total, signed, failed });
    setBatchSigning(false);
    if (failed === 0 && total > 0) toast.success(`批量签名完成：${signed}/${total}`);
    else if (total > 0) toast.warning(`批量签名：${signed} 成功, ${failed} 失败`);
    fetchAgents({ agent_type: typeFilter, status: statusFilter });
  };

  const loadSeeds = async () => {
    setSeedsLoading(true);
    try {
      const r = await workspaceAgentApi.listSeeds();
      setSeeds(r.seeds || []);
    } catch { setSeeds([]); }
    finally { setSeedsLoading(false); }
  };

  const installSeed = async (seedId: string) => {
    try {
      await workspaceAgentApi.installSeed(seedId);
      toast.success(`已安装：${seedId}`);
      loadSeeds();
      fetchAgents();
    } catch (e: any) { toast.error('安装失败', e?.message || String(e)); }
  };

  const filteredAgents = agents.filter(a => {
    if (typeFilter && a.agent_type !== typeFilter) return false;
    if (statusFilter && a.status !== statusFilter) return false;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      const hay = `${a.id || ''} ${a.name || ''} ${(a as any).display_name || ''} ${a.description || ''} ${a.agent_type || ''}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: Agent) => (
        <button
          onClick={() => { setSelectedAgent(record); setDetailModalOpen(true); }}
          className="text-primary hover:text-primary-hover font-medium"
        >
          {(record as any).display_name || name}
        </button>
      ),
    },
    { title: '类型', dataIndex: 'agent_type', key: 'agent_type', width: 100, render: (t: string) => <span className="text-gray-400">{t}</span> },
    {
      title: '来源',
      key: 'source',
      width: 80,
      render: (_: unknown, record: Agent) => (
        <span className="text-gray-400 text-xs">{getSourceLabel(extractProvenance(record))}</span>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      width: 280,
      ellipsis: true,
      render: (desc: string) => (
        <span className="text-xs text-gray-500 line-clamp-2" title={desc || undefined}>
          {desc || '-'}
        </span>
      ),
    },
    {
      title: (
        <span title="生命周期：草稿→待审核→已发布→已上架。草稿也可本机执行。">上架状态</span>
      ),
      key: 'status',
      width: 100,
      render: (_: unknown, record: Agent) => <StatusBadge status={record.status} />,
    },
    {
      title: (
        <span title="签名轨：未签名→已签名→已验签。与上架无关。">治理</span>
      ),
      key: 'governance',
      width: 100,
      render: (_: unknown, record: Agent) => {
        const prov: any = (record.metadata as any)?.provenance || {};
        if (prov?.signature_verified) {
          return <span className="text-xs text-green-400" title="签名已通过可信公钥校验">已验签</span>;
        }
        if (prov?.signature) {
          return <span className="text-xs text-blue-400" title="已写入 Ed25519 签名，尚未验签">已签名</span>;
        }
        return (
          <span className="text-xs text-gray-500" title="未签名不影响本地执行；生产启用可能要求签名">
            未签名
          </span>
        );
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      align: 'right' as const,
      sticky: 'right' as const,
      render: (_: unknown, record: Agent) => (
        <AgentRowActions
          agent={record}
          onChat={handleChatOpen}
          onExecute={(a) => { setSelectedAgent(a); setExecuteModalOpen(true); }}
          onEdit={(a) => { setSelectedAgent(a); setEditInitialTab('basic'); setEditModalOpen(true); }}
          onDetail={(a) => { setSelectedAgent(a); setDetailModalOpen(true); }}
          onStart={handleStart}
          onStop={handleStop}
          onVersions={(a) => { setSelectedAgent(a); setVersionsModalOpen(true); }}
          onHistory={(a) => { setSelectedAgent(a); setHistoryModalOpen(true); }}
          onSubmitReview={handleSubmitForReview}
          onOpenApproval={() => navigate('/approval?type=agent&status=ready')}
          onExport={handleExportPlugin}
          onDelete={(a) =>
            setDeleteConfirm({
              open: true,
              agent: a,
              // 已废弃再点删除 → 默认硬删（软删已无意义）
              hard: String(a.status || '').toLowerCase() === 'deprecated',
            })
          }
          onRestore={handleRestore}
        />
      ),
    },
  ];

  const typeOptions = [
    { value: '', label: '全部类型' },
    { value: 'react', label: 'react' },
    { value: 'plan', label: 'plan' },
    { value: 'tool', label: 'tool' },
    { value: 'rag', label: 'rag' },
    { value: 'conversational', label: 'conversational' },
  ];

  const statusOptions = [
    { value: '', label: '全部状态' },
    { value: 'draft', label: '草稿 (draft)' },
    { value: 'ready', label: '待审核 (ready)' },
    { value: 'published', label: '已发布 (published)' },
    { value: 'listed', label: '已上架 (listed)' },
    { value: 'deprecated', label: '已废弃 (deprecated)' },
  ];

  // P2-4: 向数字人上报 Agent 管理页实时状态
  useEffect(() => {
    const statusCount: Record<string, number> = {};
    agents.forEach(a => { statusCount[a.status] = (statusCount[a.status] || 0) + 1; });
    reportPageData('/workspace/agents', {
      totalAgents: agents.length,
      statusCount,
      running: statusCount['running'] || 0,
      ready: statusCount['ready'] || 0,
      error: (statusCount['error'] || 0) + (statusCount['failed'] || 0),
    });
    return () => clearPageData('/workspace/agents');
  }, [agents]);

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      <div className="flex-1 overflow-y-auto space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">应用库 Agent</h1>
          <p className="text-sm text-gray-500 mt-1">
            来自 ~/.aiplat/agents（可编辑、可删除）
            <span className="text-gray-400 ml-2">· {agents.length} 个 agent</span>
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button icon={<Plus className="w-4 h-4" />} onClick={() => { setAddMode('manual'); setAddModalOpen(true); }}>创建</Button>
          <Button variant="secondary" onClick={() => setChatCreateOpen(true)}>对话创建</Button>
          <Button variant="secondary" loading={deduping} onClick={handleDedupe} title="合并同名且技能/工具相同的重复 Agent">
            清理重复
          </Button>
          <Button variant="secondary" icon={<Upload className="w-4 h-4" />} onClick={() => { loadSeeds(); setSeedsModalOpen(true); }}>从模板安装</Button>
          <Button variant="secondary" icon={<Key className="w-4 h-4" />} onClick={() => setBatchSignOpen(true)}>批量签名</Button>
          <Button variant="secondary" icon={<ShieldCheck className="w-4 h-4" />} onClick={() => navigate('/approval?type=agent&status=ready')}>
            资产审批
          </Button>
          <Button icon={<Zap className="w-4 h-4" />} onClick={handleTestAll} loading={testAllRunning} variant="primary">
            {testAllRunning ? '测试中...' : '测试全部'}
          </Button>
          <Button icon={<RotateCw className="w-4 h-4" />} onClick={() => fetchAgents({ agent_type: typeFilter, status: statusFilter })} loading={loading}>刷新</Button>
        </div>
      </div>

      <WorkspacePageGuide
        steps={[
          { title: '创建 / 对话创建', detail: '得到草稿 draft，可先「对话 / 执行」自测' },
          { title: '提交审批', detail: '行内「更多 → 提交审批」：draft → 待审核(ready)' },
          { title: '资产审批', detail: '管理员在「资产审批」点通过 → 已发布；再点上架 → 已上架' },
        ]}
        tip="「待审核」不能在本页点通过。请用顶部「资产审批」（或更多 → 去资产审批）。签名是另一条治理线，本地执行一般不强制。"
      />

      <ImportBar assetType="agents" alsoScan={['skills', 'mcps']} onImported={() => fetchAgents({})} />

      {/* ── Smart Agent Router ── */}
      <div className="flex items-center gap-3 p-3 bg-dark-card border border-dark-border rounded-lg">
        <Search className="w-4 h-4 text-gray-500 shrink-0" />
        <input
          type="text"
          value={routeInput}
          onChange={(e) => setRouteInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleRoute()}
          placeholder="输入需求，自动匹配 Agent（如：设计一个订单系统架构 / 审查代码安全漏洞 / 我是 VIP 订单没收到）"
          className="flex-1 bg-transparent text-sm text-gray-200 placeholder-gray-500 outline-none"
        />
        <Button onClick={handleRoute} loading={routeLoading} disabled={!routeInput.trim()}>
          🤖 推荐 Agent
        </Button>
        {routeResult?.has_data && (
          <span className={`text-xs px-2 py-0.5 rounded whitespace-nowrap ${
            routeResult.confidence >= 0.8 ? 'bg-green-900/40 text-green-300' : 'bg-blue-900/40 text-blue-300'
          }`}>
            {routeResult.intent} ({Math.round(routeResult.confidence * 100)}%)
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <div className="w-44">
          <Select value={typeFilter || ''} onChange={(v: string) => { setTypeFilter(v || undefined); fetchAgents({ agent_type: v || undefined, status: statusFilter }); }} options={typeOptions} />
        </div>
        <div className="w-44">
          <Select value={statusFilter || ''} onChange={(v: string) => { setStatusFilter(v || undefined); fetchAgents({ agent_type: typeFilter, status: v || undefined }); }} options={statusOptions} />
        </div>
        <div className="flex-1 min-w-[200px] max-w-md">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索名称、ID 或描述..." />
        </div>
      </div>

      <AssetStatusLegend kind="agent" howToSubmit="更多 → 提交审批" />

      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
        <Table columns={columns} data={filteredAgents} rowKey="id" loading={loading} emptyText="暂无 Agent" />
      </motion.div>

      <AgentDetailModal
        open={detailModalOpen}
        agent={selectedAgent}
        onClose={() => setDetailModalOpen(false)}
      />

      <AgentVersionsModal
        open={versionsModalOpen}
        agent={selectedAgent}
        onClose={() => setVersionsModalOpen(false)}
      />

      <AgentHistoryModal
        open={historyModalOpen}
        agent={selectedAgent}
        onClose={() => setHistoryModalOpen(false)}
      />

      <EditAgentModal
        open={editModalOpen}
        agent={selectedAgent}
        initialTab={editInitialTab}
        onClose={() => { setEditModalOpen(false); setEditInitialTab('basic'); }}
        onSuccess={() => fetchAgents({ agent_type: typeFilter, status: statusFilter })}
      />

      <ExecuteAgentModal
        open={executeModalOpen}
        agent={selectedAgent}
        onClose={() => setExecuteModalOpen(false)}
        onEditSop={() => {
          if (!selectedAgent) return;
          setEditInitialTab('advanced');
          setExecuteModalOpen(false);
          setEditModalOpen(true);
        }}
      />

      <Modal
        open={deleteConfirm.open}
        onClose={() => setDeleteConfirm({ open: false, agent: null, hard: false })}
        title="删除 Agent"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleteConfirm({ open: false, agent: null, hard: false })} disabled={deleting}>
              取消
            </Button>
            <Button variant="danger" onClick={handleDelete} loading={deleting}>
              确认
            </Button>
          </>
        }
      >
        <div className="text-sm text-gray-300 space-y-3">
          <p>将对 Agent "{deleteConfirm.agent?.name}" 执行删除操作：</p>
          {String(deleteConfirm.agent?.status || '').toLowerCase() === 'deprecated' ? (
            <p className="text-xs text-amber-300/90">
              该 Agent 已是「已废弃」。确认将<strong>硬删除</strong>目录，从列表与磁盘移除（不可恢复）。
            </p>
          ) : (
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-400">删除方式</span>
              <Select
                value={deleteConfirm.hard ? 'hard' : 'soft'}
                onChange={(v: string) => setDeleteConfirm({ ...deleteConfirm, hard: v === 'hard' })}
                options={[
                  { value: 'soft', label: '软删除 (仅标废弃，列表仍可见)' },
                  { value: 'hard', label: '硬删除 (删除目录，不可撤销)' },
                ]}
              />
            </div>
          )}
        </div>
      </Modal>

      <Modal open={testAllOpen} onClose={() => { setTestAllOpen(false); setTestAllResults([]); }} title="Agent 批量测试结果" width={600}
        footer={<Button onClick={() => { setTestAllOpen(false); setTestAllResults([]); }}>关闭</Button>}>
        <div className="space-y-1 max-h-96 overflow-auto">
          {testAllResults.map((r, i) => (
            <div key={i} className="flex items-center justify-between py-1.5 px-2 rounded text-sm bg-dark-card border border-dark-border">
              <span className="text-gray-300">{r.agentId}</span>
              <span className={`text-xs px-2 py-0.5 rounded ${r.ok ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>{r.status}</span>
            </div>
          ))}
          {testAllRunning && <div className="text-xs text-gray-500 py-2 text-center">⏳ 测试中...</div>}
          {!testAllRunning && testAllResults.length > 0 && (
            <div className="text-xs text-gray-500 pt-2">
              {testAllResults.filter(r => r.ok).length}/{testAllResults.length} 通过
            </div>
          )}
        </div>
      </Modal>

      {/* Batch Sign Modal */}
      <Modal open={batchSignOpen} onClose={() => { setBatchSignOpen(false); setBatchResult(null); }}
        title="批量签名" width={500}
        footer={
          <div className="flex gap-2 justify-end">
            <Button variant="secondary" onClick={() => { setBatchSignOpen(false); setBatchResult(null); }}>关闭</Button>
            <Button variant="primary" onClick={handleBatchSign} loading={batchSigning} disabled={!batchSignKey.trim()}>
              {batchSigning ? '签名中...' : '一键签名'}
            </Button>
          </div>
        }>
        <div className="space-y-3 text-sm text-gray-300">
          <p className="text-xs text-gray-500">输入 Ed25519 私钥，一键为所有未验签的 Agent 签名。</p>
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

      <AddAgentModal
        open={addModalOpen}
        initialMode={addMode}
        onClose={() => setAddModalOpen(false)}
        onSuccess={() => fetchAgents({ agent_type: typeFilter, status: statusFilter })}
      />

      <AgentChatCreateModal
        open={chatCreateOpen}
        onClose={() => setChatCreateOpen(false)}
        onSuccess={() => fetchAgents({ agent_type: typeFilter, status: statusFilter })}
      />

      <Modal
        open={seedsModalOpen}
        onClose={() => setSeedsModalOpen(false)}
        title="从模板安装 Agent"
        width={600}
        footer={<Button onClick={() => setSeedsModalOpen(false)}>关闭</Button>}
      >
        <div className="space-y-3 text-sm text-gray-300">
          <p className="text-xs text-gray-500">选择一个模板安装到 workspace。模板来自 workspace_seeds，安装后可自由编辑。</p>
          {seedsLoading ? (
            <div className="text-gray-500 text-center py-4">加载中...</div>
          ) : seeds.length === 0 ? (
            <div className="text-gray-500 text-center py-4">
              暂无可用模板
              <div className="text-[10px] text-gray-600 mt-1">将 AGENT.md 放入 aiPlat-core/core/workspace_seeds/agents/&lt;id&gt;/ 即可作为模板</div>
            </div>
          ) : (
            seeds.map((s: any) => (
              <div key={s.id} className="flex items-center justify-between p-3 rounded border border-dark-border bg-dark-bg">
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-gray-200">{s.name}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{s.description}</div>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {s.category && <span className="text-[10px] px-1.5 py-0.5 rounded bg-dark-hover text-gray-400">{s.category}</span>}
                    {(s.tags || []).slice(0, 3).map((t: string) => (
                      <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-dark-hover text-gray-500">{t}</span>
                    ))}
                  </div>
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
      {chatAgent && (
        <AnimatePresence>
          <ChatPanel agent={chatAgent} onClose={() => setChatAgent(null)} />
        </AnimatePresence>
      )}
    </div>
  );
};

export default WorkspaceAgents;
