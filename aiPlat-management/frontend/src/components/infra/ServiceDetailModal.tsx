import React, { useMemo } from 'react';
import { RotateCw } from 'lucide-react';

import { Badge, Button, Modal, Table, Tabs } from '../ui';

interface ServiceDetailModalProps {
  open: boolean;
  service: ServiceData | null;
  onCancel: () => void;
  onRestart?: () => void;
  onScale?: () => void;
}

interface ServiceData {
  id: string;
  name: string;
  namespace: string;
  type: string;
  image: string;
  imageTag?: string;
  replicas: number;
  ready_replicas: number;
  gpu_count: number;
  gpu_type: string;
  status: string;
  created_at?: string;
  config?: Record<string, any>;
  pods?: PodData[];
}

interface PodData {
  name: string;
  node: string;
  status: string;
  ready: string;
  restarts: number;
  cpu_usage?: number;
  memory_usage?: number;
  gpu_usage?: number;
}

const statusVariant = (s: string) => {
  if (s === 'Running') return 'success';
  if (s === 'Pending') return 'warning';
  if (s === 'Failed') return 'error';
  return 'default';
};

const ServiceDetailModal: React.FC<ServiceDetailModalProps> = ({ open, service, onCancel, onRestart, onScale }) => {
  const pods = service?.pods || [];

  const podColumns = useMemo(
    () => [
      { key: 'name', title: 'pod', dataIndex: 'name' },
      { key: 'node', title: 'node', dataIndex: 'node' },
      { key: 'status', title: 'status', dataIndex: 'status', render: (v: string) => <Badge variant={statusVariant(v) as any}>{v}</Badge> },
      { key: 'ready', title: 'ready', dataIndex: 'ready' },
      { key: 'restarts', title: 'restarts', dataIndex: 'restarts', align: 'right' as const },
    ],
    []
  );

  if (!service) return null;

  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={`服务详情: ${service.name}`}
      width={980}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>关闭</Button>
          <Button variant="secondary" onClick={onScale}>扩缩容</Button>
          <Button variant="primary" onClick={onRestart} icon={<RotateCw size={16} />}>重启服务</Button>
        </>
      }
    >
      <Tabs
        tabs={[
          {
            key: 'overview',
            label: '概览',
            children: (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="p-3 bg-dark-bg rounded-lg border border-dark-border">
                  <div className="text-xs text-gray-500">服务名称</div>
                  <div className="text-sm text-gray-100">{service.name}</div>
                </div>
                <div className="p-3 bg-dark-bg rounded-lg border border-dark-border">
                  <div className="text-xs text-gray-500">命名空间</div>
                  <div className="text-sm text-gray-100">{service.namespace}</div>
                </div>
                <div className="p-3 bg-dark-bg rounded-lg border border-dark-border">
                  <div className="text-xs text-gray-500">类型</div>
                  <div className="text-sm text-gray-100">{service.type}</div>
                </div>
                <div className="p-3 bg-dark-bg rounded-lg border border-dark-border">
                  <div className="text-xs text-gray-500">状态</div>
                  <div className="text-sm text-gray-100">
                    <Badge variant={statusVariant(service.status) as any}>{service.status}</Badge>
                  </div>
                </div>
                <div className="p-3 bg-dark-bg rounded-lg border border-dark-border md:col-span-2">
                  <div className="text-xs text-gray-500">镜像</div>
                  <div className="text-sm text-gray-100 break-all">
                    {service.image}:{service.imageTag || 'latest'}
                  </div>
                </div>
                <div className="p-3 bg-dark-bg rounded-lg border border-dark-border">
                  <div className="text-xs text-gray-500">副本数</div>
                  <div className="text-sm text-gray-100">
                    {service.ready_replicas} / {service.replicas}
                  </div>
                </div>
                <div className="p-3 bg-dark-bg rounded-lg border border-dark-border">
                  <div className="text-xs text-gray-500">GPU</div>
                  <div className="text-sm text-gray-100">
                    {service.gpu_count} × {service.gpu_type}
                  </div>
                </div>
                <div className="p-3 bg-dark-bg rounded-lg border border-dark-border md:col-span-2">
                  <div className="text-xs text-gray-500">创建时间</div>
                  <div className="text-sm text-gray-100">{service.created_at || '-'}</div>
                </div>
              </div>
            ),
          },
          {
            key: 'pods',
            label: `Pods (${pods.length})`,
            children: <Table columns={podColumns as any} data={pods} rowKey="name" />,
          },
          {
            key: 'config',
            label: 'Config',
            children: (
              <pre className="text-xs text-gray-200 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
                {JSON.stringify(service.config || {}, null, 2)}
              </pre>
            ),
          },
        ]}
      />
    </Modal>
  );
};

export default ServiceDetailModal;

