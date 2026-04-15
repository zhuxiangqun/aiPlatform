import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Plus, RotateCw } from 'lucide-react';
import { Table, Button } from '../../../components/ui';
import PageHeader from '../../../components/common/PageHeader';
import { IngressModal } from '../../../components/infra';
import { networkApi, type ServiceEndpoint, type Ingress, type NetworkPolicy } from '../../../services';

const Network: React.FC = () => {
  const [services, setServices] = useState<ServiceEndpoint[]>([]);
  const [ingresses, setIngresses] = useState<Ingress[]>([]);
  const [policies, setPolicies] = useState<NetworkPolicy[]>([]);
  const [loading, setLoading] = useState(false);
  const [ingressModalOpen, setIngressModalOpen] = useState(false);
  const [editingIngress, setEditingIngress] = useState<Partial<Ingress> | undefined>();
  const [activeTab, setActiveTab] = useState('services');

  const fetchData = async () => {
    setLoading(true);
    try {
      const [servicesData, ingressesData, policiesData] = await Promise.all([
        networkApi.listServices(),
        networkApi.listIngresses(),
        networkApi.listNetworkPolicies(),
      ]);
      setServices(servicesData || []);
      setIngresses(ingressesData || []);
      setPolicies(policiesData || []);
    } catch (error) {
      alert('获取网络数据失败');
      console.error('Failed to fetch network data:', error);
      setServices([]);
      setIngresses([]);
      setPolicies([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCreateIngress = () => {
    setEditingIngress(undefined);
    setIngressModalOpen(true);
  };

  const handleEditIngress = (ingress: Ingress) => {
    setEditingIngress(ingress);
    setIngressModalOpen(true);
  };

  const handleIngressOk = async (values: any) => {
    try {
      if (editingIngress?.name) {
        await networkApi.updateIngress(editingIngress.name, values);
      } else {
        await networkApi.createIngress(values);
      }
      setIngressModalOpen(false);
      fetchData();
    } catch (error) {
      throw error;
    }
  };

  const handleDeleteIngress = async (ingressName: string) => {
    try {
      await networkApi.deleteIngress(ingressName);
      alert('Ingress 删除成功');
      fetchData();
    } catch (error) {
      alert('删除 Ingress 失败');
    }
  };

  const handleRefresh = () => {
    fetchData();
  };

  const clusterIpCount = services.filter((s) => s.type === 'ClusterIP').length;

  const serviceColumns = [
    { key: 'name', title: '服务名称', dataIndex: 'name' },
    { key: 'namespace', title: '命名空间', dataIndex: 'namespace' },
    {
      key: 'type',
      title: '类型',
      render: (_: unknown, record: ServiceEndpoint) => {
        const colorMap: Record<string, string> = {
          ClusterIP: 'bg-blue-50 text-blue-300',
          NodePort: 'bg-green-50 text-green-300',
          LoadBalancer: 'bg-purple-50 text-purple-300',
        };
        const colorClass = colorMap[record.type] || 'bg-dark-hover text-gray-300';
        return <span className={`px-2 py-1 rounded-md text-xs font-medium ${colorClass}`}>{record.type}</span>;
      },
    },
    { key: 'clusterIP', title: 'ClusterIP', dataIndex: 'clusterIP' },
    {
      key: 'ports',
      title: '端口',
      render: (_: unknown, record: ServiceEndpoint) => record.ports?.map((p) => `${p.port}/${p.protocol}`).join(', ') || '-',
    },
    {
      key: 'status',
      title: '状态',
      render: (_: unknown, record: ServiceEndpoint) => (
        <span className={`px-2 py-1 rounded-md text-xs font-medium ${record.status === 'Active' ? 'bg-success-light text-green-300' : 'bg-dark-hover text-gray-300'}`}>
          {record.status}
        </span>
      ),
    },
  ];

  const ingressColumns = [
    { key: 'name', title: 'Ingress名称', dataIndex: 'name' },
    { key: 'host', title: '域名', dataIndex: 'host' },
    { key: 'path', title: '路径', dataIndex: 'path' },
    {
      key: 'tls',
      title: 'TLS',
      render: (_: unknown, record: Ingress) => (
        <span className={`px-2 py-1 rounded-md text-xs font-medium ${record.tls ? 'bg-success-light text-green-300' : 'bg-dark-hover text-gray-300'}`}>
          {record.tls ? '已启用' : '未启用'}
        </span>
      ),
    },
    { key: 'backend', title: '后端服务', dataIndex: 'backend' },
    {
      key: 'status',
      title: '状态',
      render: (_: unknown, record: Ingress) => (
        <span className={`px-2 py-1 rounded-md text-xs font-medium ${record.status === 'Active' ? 'bg-success-light text-green-300' : 'bg-dark-hover text-gray-300'}`}>
          {record.status}
        </span>
      ),
    },
    {
      key: 'action',
      title: '操作',
      align: 'center' as const,
      render: (_: unknown, record: Ingress) => (
        <div className="flex items-center justify-center gap-2">
          <button className="text-primary hover:text-primary-hover" onClick={() => handleEditIngress(record)}>编辑</button>
          <button className="text-error hover:text-red-600" onClick={() => handleDeleteIngress(record.name)}>删除</button>
        </div>
      ),
    },
  ];

  const policyColumns = [
    { key: 'name', title: '策略名称', dataIndex: 'name' },
    { key: 'namespace', title: '命名空间', dataIndex: 'namespace' },
    {
      key: 'type',
      title: '类型',
      render: (_: unknown, record: NetworkPolicy) => (
        <span className={`px-2 py-1 rounded-md text-xs font-medium ${record.type === 'Ingress' ? 'bg-blue-50 text-blue-300' : 'bg-orange-50 text-orange-300'}`}>
          {record.type}
        </span>
      ),
    },
    {
      key: 'selector',
      title: '选择器',
      render: (_: unknown, record: NetworkPolicy) => {
        const selector = (record as any).selector || {};
        return Object.entries(selector).map(([k, v]) => `${k}=${v}`).join(', ') || '-';
      },
    },
    {
      key: 'status',
      title: '状态',
      render: (_: unknown, record: NetworkPolicy) => (
        <span className={`px-2 py-1 rounded-md text-xs font-medium ${(record.status === 'Enabled' || record.status === 'Disabled') ? 'bg-success-light text-green-300' : 'bg-dark-hover text-gray-300'}`}>
          {record.status}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="网络管理"
        description="服务发现、负载均衡、网络策略管理"
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
          <div className="text-sm text-gray-500 mb-1">总服务数</div>
          <div className="text-2xl font-semibold text-gray-100">{services.length}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">ClusterIP</div>
          <div className="text-2xl font-semibold text-gray-100">{clusterIpCount}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">Ingress数</div>
          <div className="text-2xl font-semibold text-gray-100">{ingresses.length}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">网络策略</div>
          <div className="text-2xl font-semibold text-gray-100">{policies.length}</div>
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
            onClick={() => { setActiveTab('services'); }}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${activeTab === 'services' ? 'text-primary' : 'text-gray-500 hover:text-gray-300'}`}
          >
            服务发现
            {activeTab === 'services' && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
          </button>
          <button
            onClick={() => { setActiveTab('ingresses'); }}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${activeTab === 'ingresses' ? 'text-primary' : 'text-gray-500 hover:text-gray-300'}`}
          >
            Ingress
            {activeTab === 'ingresses' && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
          </button>
          <button
            onClick={() => { setActiveTab('policies'); }}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${activeTab === 'policies' ? 'text-primary' : 'text-gray-500 hover:text-gray-300'}`}
          >
            网络策略
            {activeTab === 'policies' && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
          </button>
        </div>

        <div className="p-4">
          {activeTab === 'ingresses' && (
            <div className="mb-4 flex justify-end">
              <Button variant="primary" icon={<Plus size={16} />} onClick={handleCreateIngress}>
                创建 Ingress
              </Button>
            </div>
          )}
          <Table
            columns={(activeTab === 'services' ? serviceColumns : activeTab === 'ingresses' ? ingressColumns : policyColumns) as any}
            data={(activeTab === 'services' ? services : activeTab === 'ingresses' ? ingresses : policies) as any}
            rowKey={activeTab === 'services' || activeTab === 'ingresses' ? 'id' : 'name'}
            loading={loading}
            emptyText={activeTab === 'services' ? '暂无服务数据' : activeTab === 'ingresses' ? '暂无Ingress数据' : '暂无策略数据'}
          />
        </div>
      </motion.div>

      <IngressModal
        open={ingressModalOpen}
        onCancel={() => setIngressModalOpen(false)}
        onOk={handleIngressOk}
        mode={editingIngress ? 'edit' : 'create'}
        initialValues={editingIngress}
      />
    </div>
  );
};

export default Network;
