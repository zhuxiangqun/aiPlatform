import React, { useEffect, useState } from 'react';
import { Plus, RotateCw, PlayCircle, PauseCircle, Trash2, Info, Pencil, Zap, Layers, Clock } from 'lucide-react';
import { motion } from 'framer-motion';
import { Table, Select, Button, Modal, toast } from '../../../components/ui';
import { useWorkspaceAgentStore } from '../../../stores';
import type { Agent } from '../../../services';
import AddAgentModal from '../../../components/workspace/AddAgentModal';
import EditAgentModal from '../../../components/workspace/EditAgentModal';
import ExecuteAgentModal from '../../../components/workspace/ExecuteAgentModal';
import AgentDetailModal from '../../../components/workspace/AgentDetailModal';
import AgentVersionsModal from '../../../components/workspace/AgentVersionsModal';
import AgentHistoryModal from '../../../components/workspace/AgentHistoryModal';

const statusConfig: Record<string, { color: string; text: string }> = {
  running: { color: 'success', text: '运行中' },
  idle: { color: 'default', text: '空闲' },
  stopped: { color: 'error', text: '已停止' },
  error: { color: 'error', text: '错误' },
  ready: { color: 'default', text: '就绪' },
};

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

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

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
    { title: '类型', dataIndex: 'agent_type', key: 'agent_type', width: 120, render: (t: string) => <span className="text-gray-400">{t}</span> },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (s: string) => <span className="text-gray-400">{(statusConfig[s] || { text: s }).text}</span>,
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
    { value: 'ready', label: 'ready' },
    { value: 'running', label: 'running' },
    { value: 'idle', label: 'idle' },
    { value: 'stopped', label: 'stopped' },
    { value: 'error', label: 'error' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">应用库 Agent</h1>
          <p className="text-sm text-gray-500 mt-1">来自 ~/.aiplat/agents（可编辑、可删除）</p>
        </div>
        <div className="flex items-center gap-3">
          <Button icon={<Plus className="w-4 h-4" />} onClick={() => setAddModalOpen(true)}>
            创建
          </Button>
          <Button icon={<RotateCw className="w-4 h-4" />} onClick={() => fetchAgents({ agent_type: typeFilter, status: statusFilter })} loading={loading}>
            刷新
          </Button>
        </div>
      </div>

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

      <AddAgentModal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onSuccess={() => fetchAgents({ agent_type: typeFilter, status: statusFilter })}
      />
    </div>
  );
};

export default WorkspaceAgents;
