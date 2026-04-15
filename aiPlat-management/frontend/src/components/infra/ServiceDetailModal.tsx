import React from 'react';
import { Modal, Descriptions, Tag, Tabs, Table, Progress, Button } from 'antd';
import { RotateCw } from 'lucide-react';

const { Column } = Table;

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

const ServiceDetailModal: React.FC<ServiceDetailModalProps> = ({
  open,
  service,
  onCancel,
  onRestart,
  onScale,
}) => {
  if (!service) return null;

  const getStatusTag = (status: string) => {
    switch (status) {
      case 'Running':
        return <Tag color="green">运行中</Tag>;
      case 'Pending':
        return <Tag color="orange">等待中</Tag>;
      case 'Failed':
        return <Tag color="red">失败</Tag>;
      case 'Unknown':
        return <Tag color="default">未知</Tag>;
      default:
        return <Tag>{status}</Tag>;
    }
  };

  const getTypeTag = (type: string) => {
    const colors: Record<string, string> = {
      LLM: 'blue',
      Embed: 'green',
      Vector: 'purple',
      Cache: 'orange',
      DB: 'cyan',
    };
    return <Tag color={colors[type] || 'default'}>{type}</Tag>;
  };

  return (
    <Modal
      title={`服务详情: ${service.name}`}
      open={open}
      onCancel={onCancel}
      width={900}
      footer={[
        <Button key="cancel" onClick={onCancel}>
          关闭
        </Button>,
        <Button key="scale" onClick={onScale}>
          扩缩容
        </Button>,
        <Button key="restart" icon={<RotateCw size={16} />} onClick={onRestart}>
          重启服务
        </Button>,
      ]}
    >
      <Tabs
        defaultActiveKey="overview"
        items={[
          {
            key: 'overview',
            label: '概览',
            children: (
              <>
                <Descriptions bordered column={2} size="small">
                  <Descriptions.Item label="服务名称">{service.name}</Descriptions.Item>
                  <Descriptions.Item label="命名空间">{service.namespace}</Descriptions.Item>
                  <Descriptions.Item label="类型">{getTypeTag(service.type)}</Descriptions.Item>
                  <Descriptions.Item label="状态">{getStatusTag(service.status)}</Descriptions.Item>
                  <Descriptions.Item label="镜像">
                    {service.image}
                    {service.imageTag && <Tag style={{ marginLeft: 8 }}>{service.imageTag}</Tag>}
                  </Descriptions.Item>
                  <Descriptions.Item label="副本数">
                    {service.ready_replicas} / {service.replicas}
                  </Descriptions.Item>
                  <Descriptions.Item label="GPU 类型">{service.gpu_type}</Descriptions.Item>
                  <Descriptions.Item label="GPU 数量">{service.gpu_count}</Descriptions.Item>
                  <Descriptions.Item label="创建时间" span={2}>
                    {service.created_at || '-'}
                  </Descriptions.Item>
                </Descriptions>

                <div style={{ marginTop: 16 }}>
                  <div style={{ marginBottom: 8, fontWeight: 500 }}>副本状态</div>
                  <Progress
                    percent={Math.round((service.ready_replicas / service.replicas) * 100)}
                    status={service.ready_replicas === service.replicas ? 'success' : 'normal'}
                    format={() => `${service.ready_replicas}/${service.replicas}`}
                  />
                </div>
              </>
            ),
          },
          {
            key: 'pods',
            label: 'Pod 实例',
            children: (
              <Table
                dataSource={service.pods || []}
                rowKey="name"
                size="small"
                pagination={false}
              >
                <Column title="Pod 名称" dataIndex="name" key="name" />
                <Column title="节点" dataIndex="node" key="node" />
                <Column
                  title="状态"
                  dataIndex="status"
                  key="status"
                  render={(status: string) => getStatusTag(status)}
                />
                <Column title="就绪" dataIndex="ready" key="ready" />
                <Column title="重启次数" dataIndex="restarts" key="restarts" />
                <Column
                  title="CPU"
                  dataIndex="cpu_usage"
                  key="cpu_usage"
                  render={(val: number) => val ? `${val.toFixed(1)}%` : '-'}
                />
                <Column
                  title="内存"
                  dataIndex="memory_usage"
                  key="memory_usage"
                  render={(val: number) => val ? `${(val / 1024 / 1024).toFixed(1)}Mi` : '-'}
                />
                <Column
                  title="GPU"
                  dataIndex="gpu_usage"
                  key="gpu_usage"
                  render={(val: number) => val ? `${val.toFixed(1)}%` : '-'}
                />
              </Table>
            ),
          },
          {
            key: 'config',
            label: '配置',
            children: (
              <Descriptions bordered column={1} size="small">
                {service.config && Object.entries(service.config).map(([key, value]) => (
                  <Descriptions.Item key={key} label={key}>
                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                  </Descriptions.Item>
                ))}
                {!service.config && <Descriptions.Item label="配置">暂无配置信息</Descriptions.Item>}
              </Descriptions>
            ),
          },
        ]}
      />
    </Modal>
  );
};

export default ServiceDetailModal;