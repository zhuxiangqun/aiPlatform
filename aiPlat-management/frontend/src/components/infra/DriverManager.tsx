import React, { useState, useEffect } from 'react';
import { Modal, Table, Button, Space, Tag, message, Form, Select, Checkbox, Card } from 'antd';
import { RotateCw, Upload, Undo2, Info } from 'lucide-react';

const { Column } = Table;

interface Driver {
  version: string;
  node_count: number;
  nodes: string[];
  gpu_models: string[];
}

interface DriverManagerProps {
  visible?: boolean;
  onCancel?: () => void;
  embedded?: boolean;
}

const DriverManager: React.FC<DriverManagerProps> = ({ visible, onCancel, embedded = false }) => {
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [loading, setLoading] = useState(false);
  const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
  const [rollbackModalOpen, setRollbackModalOpen] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState<string>('');
  const [selectedNodes, setSelectedNodes] = useState<string[]>([]);
  const [operating, setOperating] = useState(false);

  const fetchDrivers = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/infra/drivers');
      const data = await response.json();
      setDrivers(data.drivers || []);
    } catch (error) {
      message.error('获取驱动列表失败');
      console.error('Failed to fetch drivers:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (visible || embedded) {
      fetchDrivers();
    }
  }, [visible, embedded]);

  const handleUpgrade = async () => {
    if (!selectedVersion) {
      message.warning('请输入新版本号');
      return;
    }

    setOperating(true);
    try {
      const response = await fetch('/api/infra/drivers/upgrade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          version: selectedVersion,
          nodes: selectedNodes.length > 0 ? selectedNodes : undefined,
        }),
      });

      if (response.ok) {
        message.success('驱动升级任务已启动');
        setUpgradeModalOpen(false);
        setSelectedVersion('');
        setSelectedNodes([]);
        fetchDrivers();
      } else {
        message.error('驱动升级失败');
      }
    } catch (error) {
      message.error('驱动升级失败');
    } finally {
      setOperating(false);
    }
  };

  const handleRollback = async () => {
    if (!selectedVersion) {
      message.warning('请选择回滚版本');
      return;
    }

    setOperating(true);
    try {
      const response = await fetch('/api/infra/drivers/rollback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          version: selectedVersion,
          nodes: selectedNodes.length > 0 ? selectedNodes : undefined,
        }),
      });

      if (response.ok) {
        message.success('驱动回滚任务已启动');
        setRollbackModalOpen(false);
        setSelectedVersion('');
        setSelectedNodes([]);
        fetchDrivers();
      } else {
        message.error('驱动回滚失败');
      }
    } catch (error) {
      message.error('驱动回滚失败');
    } finally {
      setOperating(false);
    }
  };

  const allNodes = [...new Set(drivers.flatMap(d => d.nodes))];

  const content = (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<RotateCw size={16} />} onClick={fetchDrivers} loading={loading}>
          刷新
        </Button>
        <Button
          type="primary"
          icon={<Upload size={16} />}
          onClick={() => {
            setSelectedVersion('');
            setSelectedNodes([]);
            setUpgradeModalOpen(true);
          }}
        >
          升级驱动
        </Button>
        <Button
          icon={<Undo2 size={16} />}
          onClick={() => {
            setSelectedVersion('');
            setSelectedNodes([]);
            setRollbackModalOpen(true);
          }}
        >
          回滚驱动
        </Button>
      </Space>

      <Card style={{ marginBottom: 16 }}>
        <Space>
          <Info style={{ color: '#1890ff' }} />
          <span>驱动管理功能用于管理和升级 GPU 驱动版本。升级前请确保工作负载已迁移。</span>
        </Space>
      </Card>

      <Table
        dataSource={drivers}
        loading={loading}
        rowKey="version"
        pagination={false}
      >
        <Column
          title="驱动版本"
          dataIndex="version"
          key="version"
          render={(version: string) => <Tag color="blue">{version}</Tag>}
        />
        <Column
          title="节点数量"
          dataIndex="node_count"
          key="node_count"
          render={(count: number) => <Tag color={count > 0 ? 'green' : 'default'}>{count}</Tag>}
        />
        <Column
          title="节点列表"
          dataIndex="nodes"
          key="nodes"
          render={(nodes: string[]) => nodes.join(', ') || '-'}
        />
        <Column
          title="GPU 型号"
          dataIndex="gpu_models"
          key="gpu_models"
          render={(models: string[]) => models.join(', ') || '-'}
        />
      </Table>

      {/* 升级弹窗 */}
      <Modal
        title="升级 GPU 驱动"
        open={upgradeModalOpen}
        onCancel={() => setUpgradeModalOpen(false)}
        onOk={handleUpgrade}
        confirmLoading={operating}
        okText="开始升级"
      >
        <Form layout="vertical">
          <Form.Item label="新驱动版本" required>
            <Select
              placeholder="选择或输入驱动版本"
              value={selectedVersion}
              onChange={setSelectedVersion}
              showSearch
              allowClear
              options={[
                { value: '545.23.08', label: '545.23.08 (Latest)' },
                { value: '535.154.05', label: '535.154.05 (Stable)' },
                { value: '535.104.05', label: '535.104.05' },
                { value: '525.89.02', label: '525.89.02 (Legacy)' },
              ]}
            />
          </Form.Item>
          <Form.Item label="目标节点">
            <Checkbox.Group
              value={selectedNodes}
              onChange={(values) => setSelectedNodes(values as string[])}
              options={allNodes.map(n => ({ label: n, value: n }))}
            />
            <div style={{ color: '#999', fontSize: 12, marginTop: 8 }}>
              不选择则升级所有节点
            </div>
          </Form.Item>
        </Form>
      </Modal>

      {/* 回滚弹窗 */}
      <Modal
        title="回滚 GPU 驱动"
        open={rollbackModalOpen}
        onCancel={() => setRollbackModalOpen(false)}
        onOk={handleRollback}
        confirmLoading={operating}
        okText="开始回滚"
      >
        <Form layout="vertical">
          <Form.Item label="回滚到版本" required>
            <Select
              placeholder="选择历史版本"
              value={selectedVersion}
              onChange={setSelectedVersion}
              options={drivers.map(d => ({ value: d.version, label: d.version }))}
            />
          </Form.Item>
          <Form.Item label="目标节点">
            <Checkbox.Group
              value={selectedNodes}
              onChange={(values) => setSelectedNodes(values as string[])}
              options={allNodes.map(n => ({ label: n, value: n }))}
            />
            <div style={{ color: '#999', fontSize: 12, marginTop: 8 }}>
              不选择则回滚所有节点
            </div>
          </Form.Item>
        </Form>
      </Modal>
    </>
  );

  if (embedded) {
    return content;
  }

  return (
    <Modal
      title="驱动管理"
      open={visible}
      onCancel={onCancel}
      footer={null}
      width={800}
    >
      {content}
    </Modal>
  );
};

export default DriverManager;