import React, { useEffect, useState } from 'react';
import { Plus, RotateCw, PlayCircle, PauseCircle, Trash2, Info, Pencil, Zap, Layers, Clock, MessageSquare } from 'lucide-react';
import { motion } from 'framer-motion';
import { Table, Select, Button, Modal, toast } from '../../../components/ui';
import { useWorkspaceAgentStore } from '../../../stores';
import { workspaceAgentApi, type Agent } from '../../../services';
import AddAgentModal from '../../../components/workspace/AddAgentModal';
import EditAgentModal from '../../../components/workspace/EditAgentModal';
import ExecuteAgentModal from '../../../components/workspace/ExecuteAgentModal';
import AgentDetailModal from '../../../components/workspace/AgentDetailModal';
import AgentVersionsModal from '../../../components/workspace/AgentVersionsModal';
import AgentHistoryModal from '../../../components/workspace/AgentHistoryModal';
import ImportBar from '../../../components/workspace/ImportBar';
import { ChatPanel } from '../../../components/core';

const WorkspaceAgents: React.FC = () => {
  const { agents, loading, fetchAgents, startAgent, stopAgent, deleteAgent } = useWorkspaceAgentStore();
  const [typeFilter, setTypeFilter] = useState<string | undefined>();
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [versionsModalOpen, setVersionsModalOpen] = useState(false);
  const [historyModalOpen, setHistoryModalOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; agent: Agent | null }>({ open: false, agent: null });
  const [testAllRunning, setTestAllRunning] = useState(false);
  const [testAllResults, setTestAllResults] = useState<{ agentId: string; status: string; ok: boolean }[]>([]);
  const [testAllOpen, setTestAllOpen] = useState(false);
  const [chatAgent, setChatAgent] = useState<Agent | null>(null);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const handleChatOpen = (agent: Agent) => {
    setChatAgent(agent);
    setSelectedAgent(agent);
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

  const handleDelete = async () => {
    if (!deleteConfirm.agent) return;
    try {
      await deleteAgent(deleteConfirm.agent.id);
      toast.success('Agent已删除');
      setDeleteConfirm({ open: false, agent: null });
    } catch {
      toast.error('删除失败');
    }
  };

  const filteredAgents = agents.filter(a => {
    if (typeFilter && a.agent_type !== typeFilter) return false;
    if (statusFilter && a.status !== statusFilter) return false;
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
          {name}
        </button>
      ),
    },
    { title: '类型', dataIndex: 'agent_type', key: 'agent_type', width: 100, render: (t: string) => <span className="text-gray-400">{t}</span> },
    {
      title: '模型',
      dataIndex: 'config',
      key: 'model',
      width: 140,
      render: (cfg: Record<string, any>) => (
        <span className="text-xs text-gray-300 font-mono">{(cfg as any)?.model || (cfg?.model) || '-'}</span>
      ),
    },
    {
      title: '上架状态',
      dataIndex: 'status',
      key: 'listing_status',
      width: 130,
      render: (s: string) => {
        const labels: Record<string, string> = { draft: '草稿', ready: '待审核', published: '已发布', listed: '已上架', deprecated: '已废弃' };
        const colors: Record<string, string> = { draft: '#888', ready: '#f59e0b', published: '#3b82f6', listed: '#10b981', deprecated: '#6b7280' };
        if (s === 'initializing') return <span className="text-xs" style={{ color: '#888' }}>启动中</span>;
        return <span className="text-xs" style={{ color: colors[s] || '#888' }}>{labels[s] || s}</span>;
      },
    },
    {
      title: '启用',
      dataIndex: 'status',
      key: 'enabled',
      width: 100,
      render: (_s: string, record: Agent) => {
        const enabled = (record as any).enabled !== false;
        return (
          <button onClick={async () => {
            try {
              const r: any = await workspaceAgentApi.toggleEnabled(record.id);
              toast.success(r.enabled ? `${record.name} 已启用` : `${record.name} 已禁用`);
              fetchAgents({ agent_type: typeFilter, status: statusFilter });
            } catch { toast.error('切换失败'); }
          }} className={`text-xs px-1.5 py-0.5 rounded ${enabled ? 'bg-green-500/10 text-green-400' : 'bg-dark-bg text-gray-600'}`}>
            {enabled ? '已启用' : '已禁用'}
          </button>
        );
      },
    },
    { title: 'ID', dataIndex: 'id', key: 'id', width: 160, render: (id: string) => <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{id}</code> },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      align: 'center' as const,
      render: (_: unknown, record: Agent) => (
        <div className="flex items-center justify-center gap-1">
          <button
            onClick={() => handleChatOpen(record)}
            className="p-1.5 rounded-lg text-blue-400 hover:bg-blue-500/10 transition-colors"
            title="打开对话"
          >
            <MessageSquare className="w-4 h-4" />
          </button>
          <button
            onClick={() => { setSelectedAgent(record); setVersionsModalOpen(true); }}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
            title="版本"
          >
            <Layers className="w-4 h-4" />
          </button>
          <button
            onClick={() => { setSelectedAgent(record); setHistoryModalOpen(true); }}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
            title="历史"
          >
            <Clock className="w-4 h-4" />
          </button>
          <button
            onClick={() => { setSelectedAgent(record); setExecuteModalOpen(true); }}
            className="p-1.5 rounded-lg text-primary hover:bg-primary-light transition-colors"
            title="执行"
          >
            <Zap className="w-4 h-4" />
          </button>
          <button
            onClick={() => { setSelectedAgent(record); setEditModalOpen(true); }}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
            title="编辑/绑定"
          >
            <Pencil className="w-4 h-4" />
          </button>
          <button
            onClick={async () => {
              try {
                const res = await fetch(`/api/core/entropy/eval/generate/${record.id}`, { method: 'POST' });
                const data = await res.json();
                toast.info(data.message || '评估检查完成');
              } catch { toast.error('检查失败'); }
            }}
            className="p-1.5 rounded-lg text-blue-400 hover:bg-blue-900/30 transition-colors"
            title="生成评估指标"
          >
            <span className="text-xs">📊</span>
          </button>
          <button onClick={() => handleStart(record)} className="p-1.5 rounded-lg text-success hover:bg-success-light transition-colors" title="启动">
            <PlayCircle className="w-4 h-4" />
          </button>
          <button onClick={() => handleStop(record)} className="p-1.5 rounded-lg text-warning hover:bg-warning-light transition-colors" title="停止">
            <PauseCircle className="w-4 h-4" />
          </button>
          <button onClick={() => setDeleteConfirm({ open: true, agent: record })} className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors" title="删除">
            <Trash2 className="w-4 h-4" />
          </button>
          <button
            onClick={() => { setSelectedAgent(record); setDetailModalOpen(true); }}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
            title="详情"
          >
            <Info className="w-4 h-4" />
          </button>
        </div>
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

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      <div className="flex-1 overflow-y-auto space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">应用库 Agent</h1>
          <p className="text-sm text-gray-500 mt-1">来自 ~/.aiplat/agents（可编辑、可删除）</p>
        </div>
        <div className="flex items-center gap-3">
          <Button icon={<Plus className="w-4 h-4" />} onClick={() => setAddModalOpen(true)}>创建</Button>
          <Button icon={<Zap className="w-4 h-4" />} onClick={handleTestAll} loading={testAllRunning} variant="primary">
            {testAllRunning ? '测试中...' : '测试全部'}
          </Button>
          <Button icon={<RotateCw className="w-4 h-4" />} onClick={() => fetchAgents({ agent_type: typeFilter, status: statusFilter })} loading={loading}>刷新</Button>
        </div>
      </div>

      <ImportBar assetType="agents" alsoScan={['skills', 'mcps']} onImported={() => fetchAgents({})} />

      <div className="flex flex-wrap items-center gap-4">
        <div className="w-44">
          <Select value={typeFilter || ''} onChange={(v: string) => { setTypeFilter(v || undefined); fetchAgents({ agent_type: v || undefined, status: statusFilter }); }} options={typeOptions} />
        </div>
        <div className="w-44">
          <Select value={statusFilter || ''} onChange={(v: string) => { setStatusFilter(v || undefined); fetchAgents({ agent_type: typeFilter, status: v || undefined }); }} options={statusOptions} />
        </div>
      </div>

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
        onClose={() => setEditModalOpen(false)}
        onSuccess={() => fetchAgents({ agent_type: typeFilter, status: statusFilter })}
      />

      <ExecuteAgentModal
        open={executeModalOpen}
        agent={selectedAgent}
        onClose={() => setExecuteModalOpen(false)}
      />

      <Modal
        open={deleteConfirm.open}
        onClose={() => setDeleteConfirm({ open: false, agent: null })}
        title="确认删除"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleteConfirm({ open: false, agent: null })}>
              取消
            </Button>
            <Button variant="primary" onClick={handleDelete}>
              确认
            </Button>
          </>
        }
      >
        <div className="text-sm text-gray-300">确认删除 Agent “{deleteConfirm.agent?.name}”？（将删除 ~/.aiplat/agents 下对应目录）</div>
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

      <AddAgentModal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onSuccess={() => fetchAgents({ agent_type: typeFilter, status: statusFilter })}
      />
      </div>
      {chatAgent && <ChatPanel agent={chatAgent} onClose={() => setChatAgent(null)} />}
    </div>
  );
};

export default WorkspaceAgents;
