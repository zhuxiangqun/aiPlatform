import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Plus, RotateCw, Settings } from 'lucide-react';
import { Table, Button } from '../../../components/ui';
import PageHeader from '../../../components/common/PageHeader';
import AddNodeModal from '../../../components/infra/AddNodeModal';
import NodeDetailModal from '../../../components/infra/NodeDetailModal';
import DriverManager from '../../../components/infra/DriverManager';
import { nodeApi, type Node } from '../../../services';

const Nodes: React.FC = () => {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [loading, setLoading] = useState(false);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [driverModalOpen, setDriverModalOpen] = useState(false);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);

  const fetchNodes = async () => {
    setLoading(true);
    try {
      const response = await nodeApi.list();
      setNodes(response?.nodes || []);
    } catch (error) {
      alert('获取节点列表失败');
      console.error('Failed to fetch nodes:', error);
      setNodes([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNodes();
  }, []);

  const handleAddNode = async (values: any) => {
    try {
      await nodeApi.add(values);
      alert('节点添加成功');
      setAddModalOpen(false);
      fetchNodes();
    } catch (error) {
      alert('节点添加失败');
      console.error('Failed to add node:', error);
    }
  };

  const handleViewDetail = (node: Node) => {
    setSelectedNode(node);
    setDetailModalOpen(true);
  };

  const handleRefresh = () => {
    fetchNodes();
  };

  const handleDrain = async (node: Node) => {
    try {
      await nodeApi.drain(node.name);
      alert(`节点 ${node.name} 已开始驱逐`);
      setDetailModalOpen(false);
      fetchNodes();
    } catch (error) {
      alert('驱逐节点失败');
      console.error('Failed to drain node:', error);
    }
  };

  const handleRestart = async (node: Node) => {
    try {
      await nodeApi.restart(node.name);
      alert(`节点 ${node.name} 已开始重启`);
      setDetailModalOpen(false);
      fetchNodes();
    } catch (error) {
      alert('重启节点失败');
      console.error('Failed to restart node:', error);
    }
  };

  const getStatusTag = (status: string) => {
    switch (status) {
      case 'Ready':
        return <span className="px-2 py-1 rounded-md text-xs font-medium bg-success-light text-green-300">健康</span>;
      case 'NotReady':
        return <span className="px-2 py-1 rounded-md text-xs font-medium bg-error-light text-red-300">离线</span>;
      default:
        return <span className="px-2 py-1 rounded-md text-xs font-medium bg-dark-hover text-gray-300">{status}</span>;
    }
  };

  const columns = [
    { key: 'name', title: '节点名称', dataIndex: 'name' },
    { key: 'ip', title: 'IP地址', dataIndex: 'ip' },
    { key: 'gpu_model', title: 'GPU型号', render: (_: unknown, record: Node) => record.gpu_model || '-' },
    { key: 'gpu_count', title: 'GPU数量', render: (_: unknown, record: Node) => record.gpu_count || 0 },
    { key: 'driver_version', title: '驱动版本', render: (_: unknown, record: Node) => record.driver_version || '-' },
    { key: 'status', title: '状态', render: (_: unknown, record: Node) => getStatusTag(record.status) },
    {
      key: 'action',
      title: '操作',
      align: 'center' as const,
      render: (_: unknown, record: Node) => (
        <div className="flex items-center justify-center gap-2">
          <button className="text-primary hover:text-primary-hover" onClick={() => handleViewDetail(record)}>详情</button>
          <button className="text-primary hover:text-primary-hover" onClick={() => handleDrain(record)}>驱逐</button>
        </div>
      ),
    },
  ];

  const healthyCount = nodes.filter((n) => n.status === 'Ready').length;
  const unhealthyCount = nodes.filter((n) => n.status !== 'Ready').length;
  const totalGpu = nodes.reduce((sum, n) => sum + (n.gpu_count || 0), 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="节点管理"
        description="GPU 物理节点或 K8s 工作节点的完整生命周期管理"
        extra={
          <div className="flex items-center gap-3">
            <Button icon={<Settings size={16} />} onClick={() => setDriverModalOpen(true)}>
              驱动管理
            </Button>
            <Button icon={<RotateCw size={16} />} onClick={handleRefresh} loading={loading}>
              刷新
            </Button>
            <Button variant="primary" icon={<Plus size={16} />} onClick={() => setAddModalOpen(true)}>
              添加节点
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
          <div className="text-sm text-gray-500 mb-1">总节点数</div>
          <div className="text-2xl font-semibold text-gray-100">{nodes.length}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">健康节点</div>
          <div className="text-2xl font-semibold text-success">{healthyCount}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">GPU总数</div>
          <div className="text-2xl font-semibold text-gray-100">{totalGpu}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">异常节点</div>
          <div className="text-2xl font-semibold" style={{ color: unhealthyCount > 0 ? '#ef4444' : undefined }}>{unhealthyCount}</div>
        </motion.div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="bg-dark-card rounded-xl border border-dark-border overflow-hidden"
      >
        <Table columns={columns} data={nodes} rowKey="name" loading={loading} emptyText="暂无节点数据" />
      </motion.div>

      <AddNodeModal
        open={addModalOpen}
        onCancel={() => setAddModalOpen(false)}
        onOk={handleAddNode}
      />

      <NodeDetailModal
        open={detailModalOpen}
        node={selectedNode}
        onCancel={() => setDetailModalOpen(false)}
        onDrain={() => selectedNode && handleDrain(selectedNode)}
        onRestart={() => selectedNode && handleRestart(selectedNode)}
      />

      <DriverManager
        visible={driverModalOpen}
        onCancel={() => setDriverModalOpen(false)}
      />
    </div>
  );
};

export default Nodes;
