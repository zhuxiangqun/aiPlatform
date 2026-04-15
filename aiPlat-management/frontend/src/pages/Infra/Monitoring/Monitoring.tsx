import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Plus, RotateCw } from 'lucide-react';
import { Table, Button } from '../../../components/ui';
import PageHeader from '../../../components/common/PageHeader';
import { AlertRuleModal } from '../../../components/infra';
import { monitoringApi, type AlertRule, type GPUMetrics, type ClusterMetrics } from '../../../services';

const Monitoring: React.FC = () => {
  const [clusterMetrics, setClusterMetrics] = useState<ClusterMetrics | null>(null);
  const [gpuMetrics, setGpuMetrics] = useState<GPUMetrics[]>([]);
  const [alertRules, setAlertRules] = useState<AlertRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [alertModalOpen, setAlertModalOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<Partial<AlertRule> | undefined>();
  const [activeTab, setActiveTab] = useState('gpu');

  const fetchData = async () => {
    setLoading(true);
    try {
      const [metricsData, gpuData, rulesData] = await Promise.all([
        monitoringApi.getClusterMetrics(),
        monitoringApi.getGPUMetrics(),
        monitoringApi.listAlertRules(),
      ]);
      setClusterMetrics(metricsData || null);
      setGpuMetrics(gpuData || []);
      setAlertRules(rulesData || []);
    } catch (error) {
      alert('获取监控数据失败');
      console.error('Failed to fetch monitoring data:', error);
      setClusterMetrics(null);
      setGpuMetrics([]);
      setAlertRules([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCreateRule = () => {
    setEditingRule(undefined);
    setAlertModalOpen(true);
  };

  const handleEditRule = (rule: AlertRule) => {
    setEditingRule(rule);
    setAlertModalOpen(true);
  };

  const handleRuleOk = async (values: any) => {
    try {
      if (editingRule?.id) {
        await monitoringApi.updateAlertRule(editingRule.id, values);
      } else {
        await monitoringApi.createAlertRule(values);
      }
      setAlertModalOpen(false);
      fetchData();
    } catch (error) {
      throw error;
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    try {
      await monitoringApi.deleteAlertRule(ruleId);
      alert('规则删除成功');
      fetchData();
    } catch (error) {
      alert('删除规则失败');
    }
  };

  const handleToggleRule = async (ruleId: string, enabled: boolean) => {
    try {
      if (enabled) {
        await monitoringApi.disableAlertRule(ruleId);
        alert('规则已停用');
      } else {
        await monitoringApi.enableAlertRule(ruleId);
        alert('规则已启用');
      }
      fetchData();
    } catch (error) {
      alert('操作失败');
    }
  };

  const handleRefresh = () => {
    fetchData();
  };

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

  const ruleColumns = [
    { key: 'name', title: '规则名称', dataIndex: 'name' },
    { key: 'type', title: '类型', dataIndex: 'type' },
    { key: 'condition', title: '条件', dataIndex: 'condition' },
    { key: 'threshold', title: '阈值', dataIndex: 'threshold' },
    {
      key: 'severity',
      title: '严重性',
      render: (_: unknown, record: AlertRule) => {
        const colorMap: Record<string, string> = {
          critical: 'bg-error-light text-red-300',
          warning: 'bg-warning-light text-amber-300',
          info: 'bg-primary-light text-blue-300',
        };
        return <span className={`px-2 py-1 rounded-md text-xs font-medium ${colorMap[record.severity] || 'bg-dark-hover text-gray-300'}`}>{record.severity}</span>;
      },
    },
    {
      key: 'status',
      title: '状态',
      render: (_: unknown, record: AlertRule) => (
        <span className={`px-2 py-1 rounded-md text-xs font-medium ${record.status === 'enabled' ? 'bg-success-light text-green-300' : 'bg-dark-hover text-gray-300'}`}>
          {record.status === 'enabled' ? '已启用' : '已停用'}
        </span>
      ),
    },
    {
      key: 'action',
      title: '操作',
      align: 'center' as const,
      render: (_: unknown, record: AlertRule) => (
        <div className="flex items-center justify-center gap-2">
          <button className="text-primary hover:text-primary-hover" onClick={() => handleEditRule(record)}>编辑</button>
          <button className="text-primary hover:text-primary-hover" onClick={() => handleToggleRule(record.id, record.status === 'enabled')}>
            {record.status === 'enabled' ? '停用' : '启用'}
          </button>
          <button className="text-error hover:text-red-600" onClick={() => handleDeleteRule(record.id)}>删除</button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="监控告警"
        description="指标监控、告警规则、审计日志管理"
        extra={
          <div className="flex items-center gap-3">
            <Button icon={<RotateCw size={16} />} onClick={handleRefresh} loading={loading}>
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
          <button
            onClick={() => { setActiveTab('gpu'); }}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${activeTab === 'gpu' ? 'text-primary' : 'text-gray-500 hover:text-gray-300'}`}
          >
            GPU 监控
            {activeTab === 'gpu' && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
          </button>
          <button
            onClick={() => { setActiveTab('alerts'); }}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${activeTab === 'alerts' ? 'text-primary' : 'text-gray-500 hover:text-gray-300'}`}
          >
            告警规则
            {activeTab === 'alerts' && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
          </button>
        </div>

        <div className="p-4">
          {activeTab === 'alerts' && (
            <div className="mb-4 flex justify-end">
              <Button variant="primary" icon={<Plus size={16} />} onClick={handleCreateRule}>
                创建规则
              </Button>
            </div>
          )}
          <Table
            columns={activeTab === 'gpu' ? gpuColumns : ruleColumns as any}
            data={activeTab === 'gpu' ? gpuMetrics : alertRules as any}
            rowKey={activeTab === 'gpu' ? ((r: GPUMetrics) => `${r.nodeId}-${r.gpuIndex}`) as any : 'id'}
            loading={loading}
            emptyText={activeTab === 'gpu' ? '暂无GPU监控数据' : '暂无告警规则'}
          />
        </div>
      </motion.div>

      <AlertRuleModal
        open={alertModalOpen}
        onCancel={() => setAlertModalOpen(false)}
        onOk={handleRuleOk}
        mode={editingRule ? 'edit' : 'create'}
        initialValues={editingRule}
      />
    </div>
  );
};

export default Monitoring;
