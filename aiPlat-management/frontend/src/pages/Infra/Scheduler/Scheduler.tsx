import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Plus, RotateCw, Cpu } from 'lucide-react';
import { Table, Button, toast } from '../../../components/ui';
import PageHeader from '../../../components/common/PageHeader';
import { QuotaModal, PolicyModal } from '../../../components/infra';
import { schedulerApi, type Quota, type Task, type Policy } from '../../../services';

interface ModelResource {
  name: string;
  provider: string;
  source: string;
  enabled: boolean;
  size_bytes: number;
  size_gb: number;
  is_downloaded: boolean;
  supports_gpu: boolean;
  quantization: string;
}

interface QuotaFormValues {
  name: string;
  gpuQuota: number;
  team: string;
}

interface PolicyFormValues {
  name: string;
  type: 'default' | 'high-priority' | 'batch';
  priority: number;
  nodeSelector: Record<string, string>;
  enabled: boolean;
}

const Scheduler: React.FC = () => {
  const [quotas, setQuotas] = useState<Quota[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [modelResources, setModelResources] = useState<{ models: ModelResource[]; ram_gb: number; vram_gb: number; gpu_vendor: string; ollama_running: boolean } | null>(null);
  const [loading, setLoading] = useState(false);
  const [quotaModalOpen, setQuotaModalOpen] = useState(false);
  const [policyModalOpen, setPolicyModalOpen] = useState(false);
  const [editingQuota, setEditingQuota] = useState<Partial<Quota> | undefined>();
  const [editingPolicy, setEditingPolicy] = useState<Partial<Policy> | undefined>();
  const [activeTab, setActiveTab] = useState('quotas');

  const fetchData = async () => {
    setLoading(true);
    try {
      const [quotasData, tasksData, policiesData] = await Promise.all([
        schedulerApi.listQuotas(),
        schedulerApi.listTasks(),
        schedulerApi.listPolicies(),
      ]);
      setQuotas(quotasData || []);
      setTasks(tasksData || []);
      setPolicies(policiesData || []);
      // 获取模型资源占用
      try {
        const res = await fetch('/api/infra/scheduler/model-resources');
        if (res.ok) setModelResources(await res.json());
      } catch {}
    } catch (error) {
      toast.error('获取调度数据失败');
      console.error('Failed to fetch scheduler data:', error);
      setQuotas([]);
      setTasks([]);
      setPolicies([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCreateQuota = () => {
    setEditingQuota(undefined);
    setQuotaModalOpen(true);
  };

  const handleEditQuota = (quota: Quota) => {
    setEditingQuota(quota);
    setQuotaModalOpen(true);
  };

  const handleQuotaOk = async (values: QuotaFormValues) => {
    try {
      if (editingQuota?.id) {
        await schedulerApi.updateQuota(editingQuota.id, values);
      } else {
        await schedulerApi.createQuota(values);
      }
      setQuotaModalOpen(false);
      fetchData();
    } catch (error) {
      throw error;
    }
  };

  const handleDeleteQuota = async (quotaId: string) => {
    if (!window.confirm('确定删除此配额？')) return;
    try {
      await schedulerApi.deleteQuota(quotaId);
      toast.success('配额删除成功');
      fetchData();
    } catch (error) {
      toast.error('删除配额失败');
    }
  };

  const handleCreatePolicy = () => {
    setEditingPolicy(undefined);
    setPolicyModalOpen(true);
  };

  const handleEditPolicy = (policy: Policy) => {
    setEditingPolicy(policy);
    setPolicyModalOpen(true);
  };

  const handlePolicyOk = async (values: PolicyFormValues) => {
    try {
      if (editingPolicy?.id) {
        await schedulerApi.updatePolicy(editingPolicy.id, values);
      } else {
        await schedulerApi.createPolicy(values);
      }
      setPolicyModalOpen(false);
      fetchData();
    } catch (error) {
      throw error;
    }
  };

  const handleDeletePolicy = async (policyId: string) => {
    if (!window.confirm('确定删除此策略？')) return;
    try {
      await schedulerApi.deletePolicy(policyId);
      toast.success('策略删除成功');
      fetchData();
    } catch (error) {
      toast.error('删除策略失败');
    }
  };

  const handleRefresh = () => {
    fetchData();
  };

  const totalQuota = quotas.reduce((sum, q) => sum + q.gpuQuota, 0);
  const totalUsed = quotas.reduce((sum, q) => sum + q.gpuUsed, 0);
  const availableGpu = totalQuota - totalUsed;
  const quotaUsage = totalQuota > 0 ? Math.round((totalUsed / totalQuota) * 100) : 0;

  const quotaColumns = [
    { key: 'name', title: '配额名称', dataIndex: 'name' },
    { key: 'gpuQuota', title: 'GPU配额', render: (_: unknown, record: Quota) => `${record.gpuQuota}卡` },
    { key: 'gpuUsed', title: '已使用', render: (_: unknown, record: Quota) => `${record.gpuUsed}卡` },
    { key: 'team', title: '团队/用户', dataIndex: 'team' },
    {
      key: 'status',
      title: '状态',
      render: (_: unknown, record: Quota) => (
        <span className={`px-2 py-1 rounded-md text-xs font-medium ${record.gpuUsed >= record.gpuQuota ? 'bg-warning-light text-amber-300' : 'bg-success-light text-green-300'}`}>
          {record.gpuUsed >= record.gpuQuota ? '满额' : '正常'}
        </span>
      ),
    },
    {
      key: 'action',
      title: '操作',
      align: 'center' as const,
      render: (_: unknown, record: Quota) => (
        <div className="flex items-center justify-center gap-2">
          <button className="text-primary hover:text-primary-hover" onClick={() => handleEditQuota(record)}>编辑</button>
          <button className="text-error hover:text-red-600" onClick={() => handleDeleteQuota(record.id)}>删除</button>
        </div>
      ),
    },
  ];

  const policyColumns = [
    { key: 'name', title: '策略名称', dataIndex: 'name' },
    { key: 'type', title: '类型', dataIndex: 'type' },
    { key: 'priority', title: '优先级', dataIndex: 'priority' },
    {
      key: 'status',
      title: '状态',
      render: (_: unknown, record: Policy) => (
        <span className={`px-2 py-1 rounded-md text-xs font-medium ${record.status === 'enabled' ? 'bg-success-light text-green-300' : 'bg-dark-hover text-gray-300'}`}>
          {record.status === 'enabled' ? '已启用' : '已禁用'}
        </span>
      ),
    },
    {
      key: 'action',
      title: '操作',
      align: 'center' as const,
      render: (_: unknown, record: Policy) => (
        <div className="flex items-center justify-center gap-2">
          <button className="text-primary hover:text-primary-hover" onClick={() => handleEditPolicy(record)}>编辑</button>
          <button className="text-error hover:text-red-600" onClick={() => handleDeletePolicy(record.id)}>删除</button>
        </div>
      ),
    },
  ];

  const taskColumns = [
    { key: 'name', title: '任务名称', dataIndex: 'name' },
    { key: 'gpu', title: 'GPU需求', render: (_: unknown, record: Task) => `${record.gpuCount}卡${record.gpuType}` },
    { key: 'queue', title: '队列', dataIndex: 'queue' },
    { key: 'priority', title: '优先级', dataIndex: 'priority' },
    { key: 'submitter', title: '提交者', dataIndex: 'submitter' },
    {
      key: 'status',
      title: '状态',
      render: (_: unknown, record: Task) => {
        switch (record.status) {
          case 'running':
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-success-light text-green-300">执行中</span>;
          case 'pending':
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-warning-light text-amber-300">等待中</span>;
          case 'completed':
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-primary-light text-blue-300">已完成</span>;
          case 'failed':
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-error-light text-red-300">失败</span>;
          default:
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-dark-hover text-gray-300">{record.status}</span>;
        }
      },
    },
    {
      key: 'action',
      title: '操作',
      align: 'center' as const,
      render: (_: unknown, record: Task) => (
        record.status === 'pending' && (
          <button
            className="text-error hover:text-red-600"
            onClick={async () => {
              try {
                await schedulerApi.cancelTask(record.id);
                toast.success('任务已取消');
                fetchData();
              } catch (error) {
                toast.error('取消任务失败');
              }
            }}
          >
            取消
          </button>
        )
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="算力调度"
        description="GPU 资源调度与任务队列管理"
        extra={
          <div className="flex items-center gap-3">
            <Button icon={<RotateCw size={16} />} onClick={handleRefresh} loading={loading}>
              刷新
            </Button>
          </div>
        }
      />

      <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group mb-3">
        <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
          <div className="text-gray-300 font-medium md:col-span-2 border-b border-dark-border pb-1 mb-0.5">资源配额</div>
          <div><span className="text-gray-300">配额名称/GPU配额/已使用</span><span className="ml-2 text-gray-600">分配/已用 GPU 数</span></div>
          <div><span className="text-gray-300">团队/用户</span><span className="ml-2 text-gray-600">配额归属</span></div>
          <div><span className="text-gray-300">状态</span><span className="ml-2 text-gray-600"><span className="text-red-400">满额</span> 已用尽 · <span className="text-green-400">正常</span></span></div>
          <div className="text-gray-300 font-medium md:col-span-2 border-b border-dark-border pb-1 mb-0.5 mt-1">调度策略</div>
          <div><span className="text-gray-300">策略名称/类型/优先级</span><span className="ml-2 text-gray-600">策略标识 + 类型 + 优先级</span></div>
          <div><span className="text-gray-300">状态</span><span className="ml-2 text-gray-600"><span className="text-green-400">已启用</span> · <span className="text-gray-500">已禁用</span></span></div>
          <div className="text-gray-300 font-medium md:col-span-2 border-b border-dark-border pb-1 mb-0.5 mt-1">任务队列</div>
          <div><span className="text-gray-300">任务名称/GPU需求/队列/优先级</span><span className="ml-2 text-gray-600">任务详情</span></div>
          <div><span className="text-gray-300">提交者</span><span className="ml-2 text-gray-600">提交用户</span></div>
          <div><span className="text-gray-300">状态</span><span className="ml-2 text-gray-600"><span className="text-blue-400">执行中</span> · <span className="text-yellow-400">等待中</span> · <span className="text-green-400">已完成</span> · <span className="text-red-400">失败</span></span></div>
        </div>
      </details>

      <div className="grid grid-cols-4 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">总GPU配额</div>
          <div className="text-2xl font-semibold text-gray-100">{totalQuota}<span className="text-sm text-gray-500 ml-1">卡</span></div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">已分配</div>
          <div className="text-2xl font-semibold text-gray-100">{totalUsed}<span className="text-sm text-gray-500 ml-1">卡</span></div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">可用GPU</div>
          <div className="text-2xl font-semibold text-success">{availableGpu}<span className="text-sm text-gray-500 ml-1">卡</span></div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">配额使用率</div>
          <div className="text-2xl font-semibold text-gray-100">{quotaUsage}<span className="text-sm text-gray-500 ml-1">%</span></div>
        </motion.div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="bg-dark-card rounded-xl border border-dark-border overflow-hidden"
      >
        <div className="flex border-b border-dark-border">
          <button
            onClick={() => { setActiveTab('quotas'); }}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${activeTab === 'quotas' ? 'text-primary' : 'text-gray-500 hover:text-gray-300'}`}
          >
            资源配额
            {activeTab === 'quotas' && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
          </button>
          <button
            onClick={() => { setActiveTab('policies'); }}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${activeTab === 'policies' ? 'text-primary' : 'text-gray-500 hover:text-gray-300'}`}
          >
            调度策略
            {activeTab === 'policies' && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
          </button>
          <button
            onClick={() => { setActiveTab('tasks'); }}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${activeTab === 'tasks' ? 'text-primary' : 'text-gray-500 hover:text-gray-300'}`}
          >
            任务队列
            {activeTab === 'tasks' && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
          </button>
        </div>

        <div className="p-4">
          {activeTab === 'quotas' && (
            <div className="mb-4 flex justify-end">
              <Button variant="primary" icon={<Plus size={16} />} onClick={handleCreateQuota}>
                创建配额
              </Button>
            </div>
          )}
          {activeTab === 'policies' && (
            <div className="mb-4 flex justify-end">
              <Button variant="primary" icon={<Plus size={16} />} onClick={handleCreatePolicy}>
                创建策略
              </Button>
            </div>
          )}
          <Table
            columns={(activeTab === 'quotas' ? quotaColumns : activeTab === 'policies' ? policyColumns : taskColumns) as any}
            data={(activeTab === 'quotas' ? quotas : activeTab === 'policies' ? policies : tasks) as any}
            rowKey={activeTab === 'quotas' || activeTab === 'policies' ? 'id' : 'name'}
            loading={loading}
            emptyText={activeTab === 'quotas' ? '暂无配额数据' : activeTab === 'policies' ? '暂无策略数据' : '暂无任务数据'}
          />
        </div>
      </motion.div>

      {modelResources && modelResources.models.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="bg-dark-card rounded-xl border border-dark-border overflow-hidden"
        >
          <div className="px-4 py-3 border-b border-dark-border flex items-center justify-between">
            <div>
              <h3 className="text-sm font-medium text-gray-200">模型资源占用</h3>
              <p className="text-xs text-gray-500 mt-0.5">
                Ollama: {modelResources.ollama_running ? '运行中' : '未运行'} · 
                GPU: {modelResources.gpu_vendor || 'N/A'} · 
                RAM: {modelResources.ram_gb}GB · 
                VRAM: {modelResources.vram_gb}GB
              </p>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-dark-border bg-dark-hover">
                  <th className="text-left px-3 py-2 text-gray-400 font-medium">模型名称</th>
                  <th className="text-left px-2 py-2 text-gray-400 font-medium">来源</th>
                  <th className="text-right px-2 py-2 text-gray-400 font-medium">大小</th>
                  <th className="text-center px-2 py-2 text-gray-400 font-medium">量化</th>
                  <th className="text-center px-2 py-2 text-gray-400 font-medium">GPU</th>
                  <th className="text-center px-2 py-2 text-gray-400 font-medium">状态</th>
                </tr>
              </thead>
              <tbody>
                {modelResources.models.map((m: ModelResource) => (
                  <tr key={m.name} className="border-b border-dark-border/50 hover:bg-dark-hover/50">
                    <td className="px-3 py-2 text-gray-200 font-medium">{m.name}</td>
                    <td className="px-2 py-2">
                      <span className={`px-1.5 py-0.5 rounded text-xs ${
                        m.source === 'local' ? 'bg-green-900/50 text-green-300' :
                        m.source === 'external' ? 'bg-blue-900/50 text-blue-300' :
                        'bg-gray-800 text-gray-400'
                      }`}>{m.source === 'local' ? '本地' : m.source === 'external' ? '外部' : m.source}</span>
                    </td>
                    <td className="px-2 py-2 text-right text-gray-300">{m.size_gb}GB</td>
                    <td className="px-2 py-2 text-center text-gray-400 text-xs">{m.quantization || '—'}</td>
                    <td className="px-2 py-2 text-center">
                      {m.supports_gpu ? <span className="text-green-400">✓</span> : <span className="text-gray-600">—</span>}
                    </td>
                    <td className="px-2 py-2 text-center">
                      {m.enabled ? (
                        m.is_downloaded ? <span className="text-green-400">可用</span> : <span className="text-yellow-400">未下载</span>
                      ) : (
                        <span className="text-gray-500">禁用</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>
      )}

      <QuotaModal
        open={quotaModalOpen}
        onCancel={() => setQuotaModalOpen(false)}
        onOk={handleQuotaOk}
        mode={editingQuota ? 'edit' : 'create'}
        initialValues={editingQuota}
      />

      <PolicyModal
        open={policyModalOpen}
        onCancel={() => setPolicyModalOpen(false)}
        onOk={handlePolicyOk}
        mode={editingPolicy ? 'edit' : 'create'}
        initialValues={editingPolicy}
      />
    </div>
  );
};

export default Scheduler;
