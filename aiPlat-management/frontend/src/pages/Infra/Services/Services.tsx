import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Plus, RotateCw } from 'lucide-react';
import { Table, Button, toast } from '../../../components/ui';
import PageHeader from '../../../components/common/PageHeader';
import { serviceApi, type Service } from '../../../services';

const Services: React.FC = () => {
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchServices = async () => {
    setLoading(true);
    try {
      const response = await serviceApi.list();
      setServices(response?.services || []);
    } catch (error) {
      toast.error('获取服务列表失败');
      console.error('Failed to fetch services:', error);
      setServices([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchServices();
  }, []);

  const handleDeploy = () => {
    toast.info('部署服务功能开发中');
  };

  const handleScale = async (serviceName: string) => {
    toast.info(`扩缩容功能开发中: ${serviceName}`);
  };

  const handleViewLogs = async (serviceName: string) => {
    try {
      const logs = await serviceApi.getLogs(serviceName, 100);
      console.log('Logs:', logs);
      toast.info('日志功能开发中');
    } catch (error) {
      toast.error('获取日志失败');
    }
  };

  const handleRefresh = () => {
    fetchServices();
  };

  const getStatusTag = (status: string) => {
    switch (status) {
      case 'Running':
        return <span className="px-2 py-1 rounded-md text-xs font-medium bg-success-light text-green-300">运行中</span>;
      case 'Pending':
        return <span className="px-2 py-1 rounded-md text-xs font-medium bg-warning-light text-amber-300">部署中</span>;
      case 'Failed':
        return <span className="px-2 py-1 rounded-md text-xs font-medium bg-error-light text-red-300">失败</span>;
      default:
        return <span className="px-2 py-1 rounded-md text-xs font-medium bg-dark-hover text-gray-300">{status}</span>;
    }
  };

  const runningCount = services.filter((s) => s.status === 'Running').length;
  const pendingCount = services.filter((s) => s.status === 'Pending').length;
  const totalGpuCount = services.reduce((sum, s) => sum + s.gpuCount, 0);

  const columns = [
    { key: 'name', title: '服务名称', dataIndex: 'name' },
    { key: 'type', title: '类型', dataIndex: 'type' },
    { key: 'replicas', title: '实例数', render: (_: unknown, record: Service) => `${record.readyReplicas}/${record.replicas}` },
    { key: 'gpu', title: 'GPU占用', render: (_: unknown, record: Service) => record.gpuCount > 0 ? `${record.gpuCount}卡${record.gpuType}` : '-' },
    { key: 'status', title: '状态', render: (_: unknown, record: Service) => getStatusTag(record.status) },
    {
      key: 'action',
      title: '操作',
      align: 'center' as const,
      render: (_: unknown, record: Service) => (
        <div className="flex items-center justify-center gap-2">
          <button className="text-primary hover:text-primary-hover" onClick={() => console.log('Detail', record)}>详情</button>
          <button className="text-primary hover:text-primary-hover" onClick={() => handleScale(record.name)}>扩缩容</button>
          <button className="text-primary hover:text-primary-hover" onClick={() => handleViewLogs(record.name)}>日志</button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="服务管理"
        description="AI 推理服务的完整生命周期管理"
        extra={
          <div className="flex items-center gap-3">
            <Button icon={<RotateCw size={16} />} onClick={handleRefresh} loading={loading}>
              刷新
            </Button>
            <Button variant="primary" icon={<Plus size={16} />} onClick={handleDeploy}>
              部署新服务
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-6 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">总服务数</div>
          <div className="text-2xl font-semibold text-gray-100">{services.length}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">运行中</div>
          <div className="text-2xl font-semibold text-success">{runningCount}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">部署中</div>
          <div className="text-2xl font-semibold" style={{ color: '#f59e0b' }}>{pendingCount}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">总GPU占用</div>
          <div className="text-2xl font-semibold text-gray-100">{totalGpuCount}<span className="text-sm text-gray-500 ml-1">卡</span></div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">总GPU</div>
          <div className="text-2xl font-semibold text-gray-100">{services.reduce((s, svc) => s + (svc.gpuCount || 0), 0)}<span className="text-sm text-gray-500 ml-1">卡</span></div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">总副本</div>
          <div className="text-2xl font-semibold text-gray-100">{services.reduce((s, svc) => s + (svc.replicas || 0), 0)}</div>
        </motion.div>
      </div>

      <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group mb-3">
        <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
          <div><span className="text-gray-300">服务名称</span><span className="ml-2 text-gray-600">kubernetes service 名称</span></div>
          <div><span className="text-gray-300">类型</span><span className="ml-2 text-gray-600">服务类型标签</span></div>
          <div><span className="text-gray-300">实例数</span><span className="ml-2 text-gray-600">就绪副本/总副本数</span></div>
          <div><span className="text-gray-300">GPU占用</span><span className="ml-2 text-gray-600">已用 GPU 数量 + 型号</span></div>
          <div><span className="text-gray-300">状态</span><span className="ml-2 text-gray-600">运行中 / 部署中 / 失败</span></div>
          <div><span className="text-gray-300">操作</span><span className="ml-2 text-gray-600">详情/扩缩容/日志</span></div>
        </div>
      </details>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="bg-dark-card rounded-xl border border-dark-border overflow-hidden"
      >
        <Table columns={columns} data={services} rowKey="id" loading={loading} emptyText="暂无服务数据" />
      </motion.div>
    </div>
  );
};

export default Services;
