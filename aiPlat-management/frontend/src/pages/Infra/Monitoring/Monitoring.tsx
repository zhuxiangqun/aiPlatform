import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { RotateCw } from 'lucide-react';
import { Table, Button, toast } from '../../../components/ui';
import PageHeader from '../../../components/common/PageHeader';
import { monitoringApi, type GPUMetrics, type ClusterMetrics } from '../../../services';

const Monitoring: React.FC = () => {
  const [clusterMetrics, setClusterMetrics] = useState<ClusterMetrics | null>(null);
  const [gpuMetrics, setGpuMetrics] = useState<GPUMetrics[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [metricsData, gpuData] = await Promise.all([
        monitoringApi.getClusterMetrics(),
        monitoringApi.getGPUMetrics(),
      ]);
      setClusterMetrics(metricsData || null);
      setGpuMetrics(gpuData || []);
    } catch (error) {
      toast.error('获取监控数据失败');
      console.error('Failed to fetch monitoring data:', error);
      setClusterMetrics(null);
      setGpuMetrics([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const gpuColumns = [
    { key: 'nodeId', title: '节点', dataIndex: 'nodeId' },
    { key: 'gpuIndex', title: 'GPU', render: (_: unknown, record: GPUMetrics) => `GPU-${record.gpuIndex}` },
    { key: 'utilization', title: '利用率', render: (_: unknown, record: GPUMetrics) => `${record.utilization}%` },
    { key: 'memory', title: '显存', render: (_: unknown, record: GPUMetrics) => `${record.memoryUsed}/${record.memoryTotal}GB` },
    { key: 'temperature', title: '温度', render: (_: unknown, record: GPUMetrics) => `${record.temperature}°C` },
    { key: 'power', title: '功耗', render: (_: unknown, record: GPUMetrics) => `${record.powerDraw}W / ${record.powerLimit}W` },
    {
      key: 'status',
      title: '状态',
      render: (_: unknown, record: GPUMetrics) => {
        switch (record.status) {
          case 'healthy':
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-success-light text-green-300">正常</span>;
          case 'warning':
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-warning-light text-amber-300">警告</span>;
          case 'critical':
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-error-light text-red-300">告警</span>;
          default:
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-dark-hover text-gray-300">{record.status}</span>;
        }
      },
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="监控告警"
        description="集群与 GPU 指标监控"
        extra={
          <div className="flex items-center gap-3">
            <Button icon={<RotateCw size={16} />} onClick={fetchData} loading={loading}>
              刷新
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-4 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">节点数</div>
          <div className="text-2xl font-semibold text-gray-100">{clusterMetrics?.totalNodes || 0}<span className="text-sm text-gray-500 ml-1">/ {clusterMetrics?.healthyNodes || 0} 健康</span></div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">CPU使用率</div>
          <div className="text-2xl font-semibold text-gray-100">{clusterMetrics?.cpuUsage || 0}<span className="text-sm text-gray-500 ml-1">%</span></div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">内存使用率</div>
          <div className="text-2xl font-semibold text-gray-100">{clusterMetrics?.memoryUsage || 0}<span className="text-sm text-gray-500 ml-1">%</span></div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">GPU使用率</div>
          <div className="text-2xl font-semibold text-gray-100">{clusterMetrics?.gpuUsage || 0}<span className="text-sm text-gray-500 ml-1">%</span></div>
        </motion.div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="bg-dark-card rounded-xl border border-dark-border overflow-hidden"
      >
        <div className="flex border-b border-dark-border">
          <span className="px-4 py-2.5 text-sm font-medium text-primary">GPU 监控</span>
        </div>

        <div className="p-4">
          <Table
            columns={gpuColumns}
            data={gpuMetrics}
            rowKey={(r: GPUMetrics) => `${r.nodeId}-${r.gpuIndex}`}
            loading={loading}
            emptyText="暂无GPU监控数据"
          />
        </div>
      </motion.div>
    </div>
  );
};

export default Monitoring;
