import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { RotateCw, AlertTriangle, CheckCircle } from 'lucide-react';
import { Table, Button, Modal, toast } from '../../components/ui';
import PageHeader from '../../components/common/PageHeader';
import { alertingApi } from '../../services';

interface Alert {
  id: string;
  name: string;
  severity: 'critical' | 'warning' | 'info';
  status: 'firing' | 'resolved';
  source: string;
  layer: string;
  component: string;
  message: string;
  timestamp: string;
}

interface AlertRule {
  id: string;
  name: string;
  type: string;
  condition: string;
  threshold: number;
  duration: number;
  severity: 'critical' | 'warning' | 'info';
  enabled: boolean;
}

const Alerts: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [activeTab, setActiveTab] = useState('alerts');

  const fetchData = async () => {
    setLoading(true);
    try {
      const [alertsData, rulesData] = await Promise.all([
        alertingApi.getAlerts(),
        alertingApi.getRules(),
      ]);
      setAlerts((alertsData as any).alerts || []);
      setRules((rulesData as any).rules || []);
    } catch (error) {
      console.error('Failed to fetch alerts:', error);
      toast.error('获取告警数据失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleAcknowledge = (_alertId: string) => {
    toast.success('告警已确认');
    fetchData();
  };

  const handleToggleRule = (_ruleId: string, enabled: boolean) => {
    toast.success(enabled ? '规则已停用' : '规则已启用');
    fetchData();
  };

  const getSeverityTag = (severity: string) => {
    switch (severity) {
      case 'critical':
        return <span className="px-2 py-1 rounded-md text-xs font-medium bg-error-light text-red-300">高</span>;
      case 'warning':
        return <span className="px-2 py-1 rounded-md text-xs font-medium bg-warning-light text-amber-300">中</span>;
      default:
        return <span className="px-2 py-1 rounded-md text-xs font-medium bg-primary-light text-blue-300">低</span>;
    }
  };

  const getStatusTag = (status: string) => {
    return status === 'firing'
      ? <span className="px-2 py-1 rounded-md text-xs font-medium bg-error-light text-red-300">告警中</span>
      : <span className="px-2 py-1 rounded-md text-xs font-medium bg-success-light text-green-300">已恢复</span>;
  };

  const alertColumns = [
    {
      key: 'severity',
      title: '严重程度',
      width: 80,
      render: (_: unknown, record: Alert) => getSeverityTag(record.severity),
    },
    {
      key: 'name',
      title: '告警名称',
      width: 200,
    },
    {
      key: 'source',
      title: '来源',
      width: 150,
    },
    {
      key: 'layer',
      title: '层级',
      width: 80,
    },
    {
      key: 'status',
      title: '状态',
      width: 100,
      render: (_: unknown, record: Alert) => getStatusTag(record.status),
    },
    {
      key: 'timestamp',
      title: '时间',
      width: 150,
    },
    {
      key: 'action',
      title: '操作',
      width: 150,
      render: (_: unknown, record: Alert) => (
        <div className="flex items-center gap-2">
          <button
            className="text-primary hover:text-primary-hover"
            onClick={() => { setSelectedAlert(record); setDetailModalVisible(true); }}
          >
            详情
          </button>
          {record.status === 'firing' && (
            <button
              className="text-primary hover:text-primary-hover"
              onClick={() => handleAcknowledge(record.id)}
            >
              确认
            </button>
          )}
        </div>
      ),
    },
  ];

  const ruleColumns = [
    {
      key: 'name',
      title: '规则名称',
      width: 200,
    },
    {
      key: 'type',
      title: '类型',
      width: 80,
    },
    {
      key: 'condition',
      title: '条件',
      width: 150,
    },
    {
      key: 'threshold',
      title: '阈值',
      width: 80,
    },
    {
      key: 'duration',
      title: '持续时间',
      width: 100,
      render: (_: unknown, record: AlertRule) => `${record.duration}s`,
    },
    {
      key: 'severity',
      title: '严重程度',
      width: 80,
      render: (_: unknown, record: AlertRule) => getSeverityTag(record.severity),
    },
    {
      key: 'enabled',
      title: '状态',
      width: 80,
      render: (_: unknown, record: AlertRule) => (
        <span className={`px-2 py-1 rounded-md text-xs font-medium ${record.enabled ? 'bg-success-light text-green-300' : 'bg-dark-hover text-gray-300'}`}>
          {record.enabled ? '已启用' : '已停用'}
        </span>
      ),
    },
    {
      key: 'action',
      title: '操作',
      width: 100,
      render: (_: unknown, record: AlertRule) => (
        <button
          className="text-primary hover:text-primary-hover"
          onClick={() => handleToggleRule(record.id, record.enabled)}
        >
          {record.enabled ? '停用' : '启用'}
        </button>
      ),
    },
  ];

  const filteredAlerts = severityFilter === 'all'
    ? alerts
    : alerts.filter(a => a.severity === severityFilter);

  const criticalCount = alerts.filter(a => a.severity === 'critical' && a.status === 'firing').length;
  const warningCount = alerts.filter(a => a.severity === 'warning' && a.status === 'firing').length;
  const infoCount = alerts.filter(a => a.severity === 'info' && a.status === 'firing').length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="告警中心"
        description="系统告警监控与处理"
        extra={
          <Button icon={<RotateCw size={16} />} onClick={fetchData} loading={loading}>
            刷新
          </Button>
        }
      />

      <div className="grid grid-cols-4 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">高危告警</div>
          <div className="flex items-center gap-2">
            {criticalCount > 0 ? <AlertTriangle size={18} className="text-error" /> : <CheckCircle size={18} className="text-success" />}
            <span className="text-2xl font-semibold" style={{ color: criticalCount > 0 ? '#ef4444' : undefined }}>{criticalCount}</span>
          </div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">中危告警</div>
          <div className="text-2xl font-semibold" style={{ color: warningCount > 0 ? '#f59e0b' : undefined }}>{warningCount}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">低危告警</div>
          <div className="text-2xl font-semibold text-gray-100">{infoCount}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">告警规则</div>
          <div className="text-2xl font-semibold text-gray-100">{rules.length}</div>
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
            onClick={() => { setActiveTab('alerts'); }}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${activeTab === 'alerts' ? 'text-primary' : 'text-gray-500 hover:text-gray-300'}`}
          >
            告警列表 ({alerts.filter(a => a.status === 'firing').length})
            {activeTab === 'alerts' && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
          </button>
          <button
            onClick={() => { setActiveTab('rules'); }}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${activeTab === 'rules' ? 'text-primary' : 'text-gray-500 hover:text-gray-300'}`}
          >
            告警规则 ({rules.length})
            {activeTab === 'rules' && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
          </button>
        </div>

        <div className="p-4">
          {activeTab === 'alerts' && (
            <>
              <div className="flex items-center gap-2 mb-4">
                <span className="text-sm text-gray-500">筛选：</span>
                <button
                  className={`px-3 py-1 rounded-md text-xs font-medium ${severityFilter === 'all' ? 'bg-primary text-white' : 'bg-dark-hover text-gray-300 hover:bg-gray-200'}`}
                  onClick={() => setSeverityFilter('all')}
                >
                  全部
                </button>
                <button
                  className={`px-3 py-1 rounded-md text-xs font-medium ${severityFilter === 'critical' ? 'bg-error text-white' : 'bg-error-light text-red-300 hover:bg-red-100'}`}
                  onClick={() => setSeverityFilter('critical')}
                >
                  高危
                </button>
                <button
                  className={`px-3 py-1 rounded-md text-xs font-medium ${severityFilter === 'warning' ? 'bg-warning text-white' : 'bg-warning-light text-amber-300 hover:bg-amber-100'}`}
                  onClick={() => setSeverityFilter('warning')}
                >
                  中危
                </button>
              </div>
              <Table
                columns={alertColumns}
                data={filteredAlerts}
                rowKey="id"
                loading={loading}
                emptyText="暂无告警数据"
              />
            </>
          )}

          {activeTab === 'rules' && (
            <Table
              columns={ruleColumns}
              data={rules}
              rowKey="id"
              loading={loading}
              emptyText="暂无规则数据"
            />
          )}
        </div>
      </motion.div>

      <Modal
        open={detailModalVisible}
        onClose={() => setDetailModalVisible(false)}
        title="告警详情"
        width={600}
        footer={
          <Button onClick={() => setDetailModalVisible(false)}>
            关闭
          </Button>
        }
      >
        {selectedAlert && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-500">告警名称</span>
              <span className="text-sm text-gray-100">{selectedAlert.name}</span>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-500">严重程度</span>
                {getSeverityTag(selectedAlert.severity)}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-500">状态</span>
                {getStatusTag(selectedAlert.status)}
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-500">来源</span>
              <span className="text-sm text-gray-100">{selectedAlert.source}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-500">层级</span>
              <span className="text-sm text-gray-100">{selectedAlert.layer}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-500">组件</span>
              <span className="text-sm text-gray-100">{selectedAlert.component}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-500">时间</span>
              <span className="text-sm text-gray-100">{selectedAlert.timestamp}</span>
            </div>
            <div>
              <span className="text-sm font-medium text-gray-500">消息</span>
              <p className="text-sm text-gray-100 mt-1">{selectedAlert.message}</p>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default Alerts;
