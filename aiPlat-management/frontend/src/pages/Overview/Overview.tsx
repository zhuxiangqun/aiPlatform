import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { RotateCw, AlertTriangle, CheckCircle, Clock, ChevronRight, BarChart3 } from 'lucide-react';
import { dashboardApi, alertingApi } from '../../services';

interface LayerStatus {
  status: 'healthy' | 'degraded' | 'unhealthy' | 'reserved';
  score: number;
  components: Record<string, { status: string; message?: string }>;
}

interface OverviewData {
  layers: {
    infra: LayerStatus;
    core: LayerStatus;
    platform: LayerStatus;
    app: LayerStatus;
  };
  resources: {
    gpu: { used: number; total: number; percent: number };
    memory: { used: number; total: number; percent: number };
    storage: { used: number; total: number; percent: number };
  } | null;
  alerts: {
    critical: number;
    warning: number;
    total: number;
  };
}

interface AlertData {
  id: string;
  severity: 'critical' | 'warning' | 'info';
  title: string;
  source: string;
  timestamp: string;
  status: string;
}

const Overview: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [overviewData, setOverviewData] = useState<OverviewData | null>(null);
  const [recentAlerts, setRecentAlerts] = useState<AlertData[]>([]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [statusData, metricsData, alertsData] = await Promise.all([
        dashboardApi.getStatus(),
        dashboardApi.getMetrics(),
        alertingApi.getAlerts(),
      ]);
      
      const infraMetrics = (metricsData as any)?.infra || {};
      const compute = infraMetrics?.compute || {};
      const memory = compute?.memory || infraMetrics?.memory || {};
      const storage = infraMetrics?.storage?.space || {};
      const gpu = compute?.gpu || {};
      
      const memoryTotalGB = Math.round((memory.total_bytes || 0) / (1024 * 1024 * 1024));
      const memoryUsedGB = Math.round((memory.used_bytes || 0) / (1024 * 1024 * 1024));
      const storageTotalGB = Math.round((storage.total_bytes || 0) / (1024 * 1024 * 1024));
      const storageUsedGB = Math.round((storage.used_bytes || 0) / (1024 * 1024 * 1024));
      
      const overview: OverviewData = {
        layers: {
          infra: {
            status: (statusData as any).layers?.infra?.status || 'reserved',
            score: (statusData as any).layers?.infra?.score || 0,
            components: (statusData as any).layers?.infra?.components || {},
          },
          core: {
            status: (statusData as any).layers?.core?.status || 'reserved',
            score: (statusData as any).layers?.core?.score || 0,
            components: (statusData as any).layers?.core?.components || {},
          },
          platform: {
            status: (statusData as any).layers?.platform?.status || 'reserved',
            score: (statusData as any).layers?.platform?.score || 0,
            components: (statusData as any).layers?.platform?.components || {},
          },
          app: {
            status: (statusData as any).layers?.app?.status || 'reserved',
            score: (statusData as any).layers?.app?.score || 0,
            components: (statusData as any).layers?.app?.components || {},
          },
        },
        resources: memoryTotalGB > 0 ? {
          gpu: {
            used: gpu.used || 0,
            total: gpu.total || 0,
            percent: gpu.utilization_percent || 0,
          },
          memory: {
            used: memoryUsedGB,
            total: memoryTotalGB,
            percent: memory.usage_percent || 0,
          },
          storage: {
            used: Number((storageUsedGB / 1024).toFixed(2)),
            total: Number((storageTotalGB / 1024).toFixed(2)),
            percent: storage.usage_percent || 0,
          },
        } : null,
        alerts: {
          critical: (alertsData as any)?.alerts?.filter((a: any) => a.severity === 'critical' && a.status === 'firing').length || 0,
          warning: (alertsData as any)?.alerts?.filter((a: any) => a.severity === 'warning' && a.status === 'firing').length || 0,
          total: (alertsData as any)?.total || 0,
        },
      };
      
      setOverviewData(overview);
      setRecentAlerts(((alertsData as any)?.alerts || []).slice(0, 5));
    } catch (err) {
      console.error('Failed to fetch overview data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle className="w-6 h-6 text-success" />;
      case 'degraded':
        return <AlertTriangle className="w-6 h-6 text-warning" />;
      case 'unhealthy':
        return <AlertTriangle className="w-6 h-6 text-error" />;
      default:
        return <Clock className="w-6 h-6 text-gray-300" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy': return 'bg-success-light text-success border-success/20';
      case 'degraded': return 'bg-warning-light text-amber-300 border-warning/20';
      case 'unhealthy': return 'bg-error-light text-red-300 border-error/20';
      default: return 'bg-dark-hover text-gray-500 border-dark-border';
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'healthy': return '健康';
      case 'degraded': return '部分可用';
      case 'unhealthy': return '异常';
      default: return '预留';
    }
  };

  const getSeverityTag = (severity: string) => {
    switch (severity) {
      case 'critical':
        return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-error-light text-red-300">高</span>;
      case 'warning':
        return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-warning-light text-amber-300">中</span>;
      default:
        return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-primary-light text-blue-300">低</span>;
    }
  };

  const layers = [
    { key: 'infra', name: '基础设施层', desc: 'Layer 0 · GPU节点、服务、存储', path: '/infra/nodes' },
    { key: 'core', name: '核心能力层', desc: 'Layer 1 · Agent、Skill、Memory', path: null },
    { key: 'platform', name: '平台服务层', desc: 'Layer 2 · 网关、认证、租户', path: null },
    { key: 'app', name: '应用接入层', desc: 'Layer 3 · 渠道、会话、用户', path: null },
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">平台总览</h1>
          <p className="text-sm text-gray-500 mt-1">四层架构健康状态与资源概览</p>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-gray-400 bg-dark-card border border-dark-border hover:bg-dark-hover disabled:opacity-50 transition-colors"
        >
          <RotateCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      {/* Layer Cards */}
      <div className="grid grid-cols-4 gap-4">
        {layers.map((layer, index) => {
          const status = overviewData?.layers[layer.key as keyof typeof overviewData.layers];
          const isClickable = !!layer.path;
          
          return (
            <motion.div
              key={layer.key}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
              className={`
                bg-dark-card rounded-xl border border-dark-border p-5
                ${isClickable ? 'cursor-pointer hover:shadow-md transition-shadow' : ''}
                ${!isClickable ? 'opacity-60' : ''}
              `}
              onClick={() => layer.path && navigate(layer.path)}
            >
              <div className="flex items-center gap-3 mb-3">
                {getStatusIcon(status?.status || 'reserved')}
                <h3 className="font-semibold text-gray-100">{layer.name}</h3>
              </div>
              <div className="mb-3">
                <span className={`inline-flex px-2.5 py-1 rounded-full text-xs font-medium border ${getStatusColor(status?.status || 'reserved')}`}>
                  {getStatusText(status?.status || 'reserved')}
                </span>
                {status?.score !== undefined && (
                  <span className="ml-2 text-sm text-gray-400">
                    {status.score}% 可用
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-400">{layer.desc}</p>
            </motion.div>
          );
        })}
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 gap-6">
        {/* Resource Overview */}
        <div className="bg-dark-card rounded-xl border border-dark-border p-5">
          <h3 className="font-semibold text-gray-100 mb-4">资源概览</h3>
          {overviewData?.resources ? (
            <div className="space-y-4">
              {[
                { label: 'GPU', used: overviewData.resources.gpu.used, total: overviewData.resources.gpu.total, unit: '卡', percent: overviewData.resources.gpu.percent },
                { label: '内存使用', used: overviewData.resources.memory.used, total: overviewData.resources.memory.total, unit: 'GB', percent: overviewData.resources.memory.percent },
                { label: '存储使用', used: overviewData.resources.storage.used, total: overviewData.resources.storage.total, unit: 'TB', percent: overviewData.resources.storage.percent },
              ].map((item) => (
                <div key={item.label}>
                  <div className="flex justify-between text-sm mb-1.5">
                    <span className="font-medium text-gray-300">{item.label}</span>
                    <span className="text-gray-500">{item.used}/{item.total} {item.unit}</span>
                  </div>
                  <div className="h-2 bg-dark-hover rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-300 ${
                        item.percent > 80 ? 'bg-error' : 'bg-primary'
                      }`}
                      style={{ width: `${Math.min(100, item.percent)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-8 text-gray-400">
              <BarChart3 className="w-8 h-8 mb-2" />
              <p className="text-sm">暂无资源数据</p>
            </div>
          )}
        </div>

        {/* Recent Alerts */}
        <div className="bg-dark-card rounded-xl border border-dark-border p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-gray-100">最近告警 ({overviewData?.alerts?.total || 0})</h3>
            <button
              onClick={() => navigate('/alerts')}
              className="text-sm text-primary hover:text-primary-hover flex items-center gap-1"
            >
              查看全部 <ChevronRight className="w-4 h-4" />
            </button>
          </div>
          {recentAlerts.length > 0 ? (
            <div className="space-y-3">
              {recentAlerts.map((alert) => (
                <div
                  key={alert.id}
                  className="flex items-start gap-3 p-3 rounded-lg bg-dark-bg hover:bg-dark-hover transition-colors cursor-pointer"
                  onClick={() => navigate('/alerts')}
                >
                  {getSeverityTag(alert.severity)}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-100 truncate">{alert.title}</div>
                    <div className="text-xs text-gray-400">{alert.source}</div>
                  </div>
                  <div className="text-xs text-gray-400 whitespace-nowrap">{alert.timestamp}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-8">
              <CheckCircle className="w-12 h-12 text-success mb-2" />
              <p className="text-sm text-gray-500">暂无告警</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Overview;
