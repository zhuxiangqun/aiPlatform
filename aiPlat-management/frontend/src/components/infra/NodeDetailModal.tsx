import React from 'react';
import { RotateCw, Zap, Trash2, Cpu, Thermometer } from 'lucide-react';
import { Modal, Button, Tabs } from '../ui';

interface NodeDetailModalProps {
  open: boolean;
  node: NodeData | null;
  onCancel: () => void;
  onDrain?: () => void;
  onRestart?: () => void;
}

interface NodeData {
  name: string;
  ip: string;
  gpu_model: string;
  gpu_count: number;
  driver_version: string;
  status: string;
  gpus: GPUData[];
  labels: Record<string, string>;
}

interface GPUData {
  id: string;
  utilization: number;
  temperature: number;
  memory_shared?: boolean;
}

const NodeDetailModal: React.FC<NodeDetailModalProps> = ({
  open,
  node,
  onCancel,
  onDrain,
  onRestart,
}) => {
  if (!node) return null;

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'Ready':
        return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-success-light text-green-700">健康</span>;
      case 'NotReady':
        return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-error-light text-red-700">离线</span>;
      case 'Draining':
        return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-warning-light text-amber-300">驱逐中</span>;
      default:
        return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-dark-hover text-gray-300">{status}</span>;
    }
  };

  const getGpuStatusColor = (utilization: number, temperature: number) => {
    if (utilization > 95 || temperature > 85) return '#EF4444';
    if (utilization > 80 || temperature > 75) return '#F59E0B';
    return '#10B981';
  };

  const tabs = [
    {
      key: 'overview',
      label: '概览',
      children: (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="p-3 bg-dark-bg rounded-lg">
              <div className="text-xs text-gray-400 mb-1">节点名称</div>
              <div className="text-sm font-medium text-gray-100">{node.name}</div>
            </div>
            <div className="p-3 bg-dark-bg rounded-lg">
              <div className="text-xs text-gray-400 mb-1">状态</div>
              <div>{getStatusBadge(node.status)}</div>
            </div>
            <div className="p-3 bg-dark-bg rounded-lg">
              <div className="text-xs text-gray-400 mb-1">IP 地址</div>
              <div className="text-sm font-medium text-gray-100">{node.ip}</div>
            </div>
            <div className="p-3 bg-dark-bg rounded-lg">
              <div className="text-xs text-gray-400 mb-1">GPU 型号</div>
              <div className="text-sm font-medium text-gray-100">{node.gpu_model || '-'}</div>
            </div>
            <div className="p-3 bg-dark-bg rounded-lg">
              <div className="text-xs text-gray-400 mb-1">GPU 数量</div>
              <div className="text-sm font-medium text-gray-100">{node.gpu_count || 0} 卡</div>
            </div>
            <div className="p-3 bg-dark-bg rounded-lg">
              <div className="text-xs text-gray-400 mb-1">驱动版本</div>
              <div className="text-sm font-medium text-gray-100">{node.driver_version || '-'}</div>
            </div>
          </div>

          <div className="bg-dark-bg rounded-xl p-4">
            <h4 className="text-sm font-medium text-gray-100 mb-3">GPU 使用情况</h4>
            {node.gpus && node.gpus.length > 0 ? (
              <div className="space-y-3">
                {node.gpus.map((gpu) => (
                  <div key={gpu.id} className="flex items-center gap-4">
                    <div className="flex items-center gap-2 w-20">
                      <Cpu className="w-4 h-4 text-gray-400" />
                      <span className="text-sm text-gray-300">{gpu.id}</span>
                    </div>
                    <div className="flex-1">
                      <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{ width: `${gpu.utilization || 0}%`, backgroundColor: getGpuStatusColor(gpu.utilization || 0, gpu.temperature || 0) }}
                        />
                      </div>
                    </div>
                    <div className="flex items-center gap-1 w-16">
                      <Thermometer className="w-3 h-3 text-gray-400" />
                      <span className="text-xs text-gray-400">{gpu.temperature || 0}°C</span>
                    </div>
                    <div className="w-24 text-xs text-gray-400">
                      {gpu.memory_shared ? '统一内存' : '独立显存'}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-6 text-gray-400">暂无GPU信息</div>
            )}
          </div>
        </div>
      ),
    },
    {
      key: 'labels',
      label: '标签',
      children: (
        <div className="space-y-2">
          {Object.entries(node.labels).map(([key, value]) => (
            <div key={key} className="flex items-center gap-2 p-2 bg-dark-bg rounded-lg">
              <span className="text-sm text-gray-400">{key}</span>
              <span className="text-gray-300">:</span>
              <span className="px-2 py-0.5 bg-primary-light text-primary text-xs rounded">{value}</span>
            </div>
          ))}
        </div>
      ),
    },
    {
      key: 'actions',
      label: '操作',
      children: (
        <div className="space-y-4">
          <div className="p-3 bg-warning-light rounded-lg border border-warning/20">
            <div className="text-sm font-medium text-amber-300 mb-1">危险操作</div>
            <div className="text-xs text-amber-400">以下操作可能影响节点上运行的服务，请谨慎操作。</div>
          </div>

          <div className="p-4 bg-dark-bg rounded-xl">
            <div className="text-sm font-medium text-gray-100 mb-1">驱逐Pod</div>
            <div className="text-xs text-gray-400 mb-3">驱逐节点上的所有 Pod，使节点进入维护模式。</div>
            <Button icon={<Zap className="w-4 h-4" />} onClick={onDrain} disabled={node.status !== 'Ready'}>
              驱逐所有 Pod
            </Button>
          </div>

          <div className="p-4 bg-dark-bg rounded-xl">
            <div className="text-sm font-medium text-gray-100 mb-1">重启节点</div>
            <div className="text-xs text-gray-400 mb-3">重启节点操作系统，所有 Pod 将被迁移到其他节点。</div>
            <Button variant="danger" icon={<RotateCw className="w-4 h-4" />} onClick={onRestart}>
              重启节点
            </Button>
          </div>

          <div className="p-4 bg-dark-bg rounded-xl">
            <div className="text-sm font-medium text-gray-100 mb-1">删除节点</div>
            <div className="text-xs text-gray-400 mb-3">从集群中移除节点，此操作不可恢复。</div>
            <Button variant="danger" icon={<Trash2 className="w-4 h-4" />}>
              删除节点
            </Button>
          </div>
        </div>
      ),
    },
  ];

  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={`节点详情: ${node.name}`}
      width={800}
      footer={
        <Button onClick={onCancel}>关闭</Button>
      }
    >
      <Tabs tabs={tabs} defaultActiveKey="overview" />
    </Modal>
  );
};

export default NodeDetailModal;
