import React, { useState, useEffect } from 'react';
import { Plus, RotateCw, PlayCircle, PauseCircle, Trash2, Zap, Pencil } from 'lucide-react';
import { motion } from 'framer-motion';
import { Table, Select, Button, Modal } from '../../../components/ui';
import { AddAgentModal, EditAgentModal, ExecuteAgentModal, AgentDetailModal } from '../../../components/core';
import { useAgentStore } from '../../../stores';
import type { Agent } from '../../../services';

const statusConfig: Record<string, { color: string; text: string }> = {
  running: { color: 'success', text: '运行中' },
  idle: { color: 'default', text: '空闲' },
  stopped: { color: 'error', text: '已停止' },
  error: { color: 'error', text: '错误' },
};

const typeConfig: Record<string, { color: string; text: string }> = {
  base: { color: 'bg-blue-50 text-blue-700 border-blue-200', text: '基础' },
  react: { color: 'bg-green-50 text-green-300 border-green-200', text: 'ReAct' },
  plan: { color: 'bg-amber-50 text-amber-700 border-amber-200', text: '规划型' },
  tool: { color: 'bg-purple-50 text-purple-700 border-purple-200', text: '工具型' },
};

const Agents: React.FC = () => {
  const { agents, loading, fetchAgents, startAgent, stopAgent, deleteAgent } = useAgentStore();
  const [typeFilter, setTypeFilter] = useState<string | undefined>();
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; agent: Agent | null }>({ open: false, agent: null });

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const handleStart = async (agent: Agent) => {
    try {
      await startAgent(agent.id);
      alert(`Agent "${agent.name}" 已启动`);
    } catch {
      alert('启动失败');
    }
  };

  const handleStop = async (agent: Agent) => {
    try {
      await stopAgent(agent.id);
      alert(`Agent "${agent.name}" 已停止`);
    } catch {
      alert('停止失败');
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm.agent) return;
    try {
      await deleteAgent(deleteConfirm.agent.id);
      alert('Agent已删除');
      setDeleteConfirm({ open: false, agent: null });
    } catch {
      alert('删除失败');
    }
  };

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
    {
      title: '类型',
      dataIndex: 'agent_type',
      key: 'agent_type',
      width: 100,
      render: (type: string) => {
        const cfg = typeConfig[type] || { color: 'bg-dark-hover text-gray-300', text: type };
        return (
          <span className={`inline-flex px-2 py-1 rounded-md text-xs font-medium border ${cfg.color}`}>
            {cfg.text}
          </span>
        );
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const cfg = statusConfig[status] || { color: 'bg-dark-hover text-gray-300', text: status };
        const colorClass = cfg.color === 'success' ? 'bg-success-light text-green-300' :
          cfg.color === 'error' ? 'bg-error-light text-red-300' :
            'bg-dark-hover text-gray-300';
        return (
          <span className={`inline-flex px-2 py-1 rounded-md text-xs font-medium ${colorClass}`}>
            {cfg.text}
          </span>
        );
      },
    },
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 120,
      render: (id: string) => (
        <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{id.slice(0, 8)}</code>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      align: 'center' as const,
      render: (_: unknown, record: Agent) => (
        <div className="flex items-center justify-center gap-1">
          <button
            onClick={() => { setSelectedAgent(record); setEditModalOpen(true); }}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
            title="编辑"
          >
            <Pencil className="w-4 h-4" />
          </button>
          <button
            onClick={() => handleStart(record)}
            className="p-1.5 rounded-lg text-success hover:bg-success-light transition-colors"
            title="启动"
          >
            <PlayCircle className="w-4 h-4" />
          </button>
          <button
            onClick={() => handleStop(record)}
            className="p-1.5 rounded-lg text-warning hover:bg-warning-light transition-colors"
            title="停止"
          >
            <PauseCircle className="w-4 h-4" />
          </button>
          <button
            onClick={() => { setSelectedAgent(record); setExecuteModalOpen(true); }}
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
            title="执行"
          >
            <Zap className="w-4 h-4" />
          </button>
          <button
            onClick={() => setDeleteConfirm({ open: true, agent: record })}
            className="p-1.5 rounded-lg text-error hover:bg-error-light transition-colors"
            title="删除"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      ),
    },
  ];

  const filteredAgents = agents.filter(a => {
    if (typeFilter && a.agent_type !== typeFilter) return false;
    if (statusFilter && a.status !== statusFilter) return false;
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">Agent管理</h1>
          <p className="text-sm text-gray-400 mt-1">管理AI代理的创建、配置、启停与执行</p>
        </div>
        <div className="flex items-center gap-3">
          <Select
            value={typeFilter}
            onChange={(v) => setTypeFilter(v || undefined)}
            options={[
              { value: 'base', label: '基础' },
              { value: 'react', label: 'ReAct' },
              { value: 'plan', label: '规划型' },
              { value: 'tool', label: '工具型' },
            ]}
            placeholder="类型筛选"
          />
          <Select
            value={statusFilter}
            onChange={(v) => setStatusFilter(v || undefined)}
            options={[
              { value: 'running', label: '运行中' },
              { value: 'idle', label: '空闲' },
              { value: 'stopped', label: '已停止' },
            ]}
            placeholder="状态筛选"
          />
          <Button
            icon={<RotateCw className="w-4 h-4" />}
            onClick={fetchAgents}
            loading={loading}
          >
            刷新
          </Button>
          <Button
            variant="primary"
            icon={<Plus className="w-4 h-4" />}
            onClick={() => setAddModalOpen(true)}
          >
            创建Agent
          </Button>
        </div>
      </div>

      {/* Table Card */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-dark-card rounded-xl border border-dark-border overflow-hidden"
      >
        <Table
          columns={columns}
          data={filteredAgents}
          rowKey="id"
          loading={loading}
          emptyText="暂无Agent数据"
        />
      </motion.div>

      {/* Delete Confirmation Modal */}
      <Modal
        open={deleteConfirm.open}
        onClose={() => setDeleteConfirm({ open: false, agent: null })}
        title="确认删除"
        footer={
          <>
            <Button onClick={() => setDeleteConfirm({ open: false, agent: null })}>
              取消
            </Button>
            <Button variant="danger" onClick={handleDelete}>
              确认删除
            </Button>
          </>
        }
      >
        <p className="text-gray-400">
          确定要删除Agent "{deleteConfirm.agent?.name}" 吗？此操作不可撤销，请谨慎操作。
        </p>
      </Modal>

      <AddAgentModal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onSuccess={fetchAgents}
      />

      <EditAgentModal
        open={editModalOpen}
        agent={selectedAgent}
        onClose={() => { setEditModalOpen(false); }}
        onSuccess={fetchAgents}
      />

      <ExecuteAgentModal
        open={executeModalOpen}
        agent={selectedAgent}
        onClose={() => setExecuteModalOpen(false)}
      />

      <AgentDetailModal
        open={detailModalOpen}
        agent={selectedAgent}
        onClose={() => setDetailModalOpen(false)}
      />
    </div>
  );
};

export default Agents;
