import React, { useState } from 'react';
import { RotateCw, PlayCircle, PauseCircle, Trash2, Zap, Pencil, MessageSquare } from 'lucide-react';
import { motion } from 'framer-motion';
import { Table, Select, Button, Modal, toast } from '../../../components/ui';
import { EditAgentModal, ExecuteAgentModal, AgentDetailModal, ChatPanel } from '../../../components/core';
import { getSourceLabel, extractProvenance } from '../../../utils/sourceLabel';
import { useAgentStore } from '../../../stores';
import { agentApi, type Agent } from '../../../services';

const Agents: React.FC = () => {
  const { agents, loading, fetchAgents, startAgent, stopAgent, deleteAgent } = useAgentStore();
  const [typeFilter, setTypeFilter] = useState<string | undefined>();
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [chatAgent, setChatAgent] = useState<Agent | null>(null);
  const [testAllRunning, setTestAllRunning] = useState(false);
  const [testAllResults, setTestAllResults] = useState<{ agentId: string; status: string; ok: boolean }[]>([]);
  const [testAllOpen, setTestAllOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; agent: Agent | null }>({ open: false, agent: null });

  React.useEffect(() => {
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
        const r: any = await agentApi.execute(a.id, { input: { message: 'Say hello in one sentence.' } });
        results.push({ agentId: a.display_name || a.name || a.id, status: (r as any)?.status || '?', ok: (r as any)?.status === 'completed' });
      } catch (e: any) {
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

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: Agent) => (
        <button
          onClick={() => { setSelectedAgent(record); setDetailModalOpen(true); }}
          className="text-primary hover:text-primary-hover font-medium cursor-pointer"
          title="查看详情"
        >
          {name}
        </button>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 70,
      render: (cat: string) => (
        <span className="text-xs text-gray-400">{cat || '-'}</span>
      ),
    },
    {
      title: '来源',
      key: 'source',
      width: 80,
      render: (_: unknown, record: Agent) => (
        <span className="text-gray-400 text-xs">{getSourceLabel(extractProvenance(record))}</span>
      ),
    },
    {
      title: '功能描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (desc: string) => (
        <span className="text-xs text-gray-500">{desc || '-'}</span>
      ),
    },
    {
      title: '治理',
      key: 'governance',
      width: 90,
      render: (_: unknown, record: Agent) => {
        const prov: any = (record.metadata as any)?.provenance || {};
        if (prov?.signature_verified) return <span className="text-xs text-green-400">已验签</span>;
        if (prov?.signature) return <span className="text-xs text-blue-400">已签名</span>;
        return <span className="text-xs text-gray-500">未签名</span>;
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      align: 'center' as const,
      render: (_: unknown, record: Agent) => {
        const isProtected = Boolean((record as any)?.metadata?.protected === true || (record as any)?.protected === true);
        return (
        <div className="flex items-center justify-center gap-1">
          <button
            onClick={() => handleChatOpen(record)}
            className="p-1.5 rounded-lg text-blue-400 hover:bg-blue-500/10 transition-colors"
            title="打开对话"
          >
            <MessageSquare className="w-4 h-4" />
          </button>
          {!isProtected && (
            <button
              onClick={() => { setSelectedAgent(record); setEditModalOpen(true); }}
              className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
              title="编辑"
            >
              <Pencil className="w-4 h-4" />
            </button>
          )}
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
          {!isProtected && (
            <button
              onClick={() => setDeleteConfirm({ open: true, agent: record })}
              className="p-1.5 rounded-lg text-error hover:bg-error-light transition-colors"
              title="删除"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
        );
      },
    },
  ];

  const filteredAgents = agents.filter(a => {
    if (typeFilter && a.agent_type !== typeFilter) return false;
    if (statusFilter && a.status !== statusFilter) return false;
    return true;
  });

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* Left: Agent List */}
      <div className="flex-1 overflow-y-auto space-y-6 p-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">Agent管理</h1>
          <p className="text-sm text-gray-400 mt-1">管理AI代理的创建、配置、启停与执行</p>
        </div>
        <div className="flex items-center gap-3">
          <Button icon={<Zap className="w-4 h-4" />} onClick={handleTestAll} loading={testAllRunning} variant="primary">
            {testAllRunning ? '测试中...' : '测试全部 Agent'}
          </Button>
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
        </div>
      </div>

      <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group mb-3">
        <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
          <div><span className="text-gray-300">名称</span><span className="ml-2 text-gray-600">AGENT.md 的 display_name，点击打开对话</span></div>
          <div><span className="text-gray-300">分类</span><span className="ml-2 text-gray-600">Agent 的功能分类标签</span></div>
          <div><span className="text-gray-300">模型</span><span className="ml-2 text-gray-600">config.model，调用的 LLM 模型</span></div>
          <div><span className="text-gray-300">功能描述</span><span className="ml-2 text-gray-600">AGENT.md 的 description</span></div>
          <div><span className="text-gray-300">ID</span><span className="ml-2 text-gray-600">Agent 唯一标识符</span></div>
          <div><span className="text-gray-300">操作</span><span className="ml-2 text-gray-600">对话/编辑/启动/停止/执行/删除。受保护的 Agent 不可编辑和删除</span></div>
        </div>
      </details>

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
      </div>

      {/* Right: Chat Panel */}
      {chatAgent && (
        <ChatPanel agent={chatAgent} onClose={() => setChatAgent(null)} />
      )}
    </div>
  );
};

export default Agents;
