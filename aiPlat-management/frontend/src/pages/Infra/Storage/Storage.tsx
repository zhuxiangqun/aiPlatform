import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Plus, RotateCw } from 'lucide-react';
import { Table, Button } from '../../../components/ui';
import PageHeader from '../../../components/common/PageHeader';
import { PVCModal, CollectionModal } from '../../../components/infra';
import { storageApi, modelApi, type VectorCollection, type PVC } from '../../../services';

interface PVCFormValues {
  name: string;
  namespace: string;
  size: number;
  storageClass?: string;
  accessMode?: 'ReadWriteOnce' | 'ReadWriteMany' | 'ReadOnlyMany';
}

const Storage: React.FC = () => {
  const [collections, setCollections] = useState<VectorCollection[]>([]);
  const [pvcs, setPVCs] = useState<PVC[]>([]);
  const [modelCount, setModelCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [pvcModalOpen, setPvcModalOpen] = useState(false);
  const [collectionModalOpen, setCollectionModalOpen] = useState(false);
  const [editingPVC, setEditingPVC] = useState<Partial<PVCFormValues> | undefined>();
  const [pvcMode, setPvcMode] = useState<'create' | 'expand'>('create');
  const [activeTab, setActiveTab] = useState('collections');

  const fetchData = async () => {
    setLoading(true);
    try {
      const [collectionsData, pvcsData, modelsData] = await Promise.all([
        storageApi.listCollections(),
        storageApi.listPVCs(),
        modelApi.list(),
      ]);
      setCollections(collectionsData || []);
      setPVCs(pvcsData || []);
      setModelCount(modelsData?.models?.length || 0);
    } catch (error) {
      alert('获取存储数据失败');
      console.error('Failed to fetch storage data:', error);
      setCollections([]);
      setPVCs([]);
      setModelCount(0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCreatePVC = () => {
    setEditingPVC(undefined);
    setPvcMode('create');
    setPvcModalOpen(true);
  };

  const handleExpandPVC = (pvc: PVC) => {
    setEditingPVC({
      name: pvc.name,
      namespace: pvc.namespace,
      size: parseInt(pvc.size) || 10,
    });
    setPvcMode('expand');
    setPvcModalOpen(true);
  };

  const handlePVCOk = async (values: any) => {
    try {
      if (pvcMode === 'create') {
        await storageApi.createPVC(values);
      } else if (editingPVC?.name) {
        await storageApi.expandPVC(editingPVC.name, `${values.size}GB`);
      }
      setPvcModalOpen(false);
      fetchData();
    } catch (error) {
      throw error;
    }
  };

  const handleDeletePVC = async (pvcName: string) => {
    try {
      await storageApi.deletePVC(pvcName);
      alert('PVC 删除成功');
      fetchData();
    } catch (error) {
      alert('删除 PVC 失败');
    }
  };

  const handleCreateCollection = () => {
    setCollectionModalOpen(true);
  };

  const handleCollectionOk = async (values: any) => {
    try {
      await storageApi.createCollection(values);
      setCollectionModalOpen(false);
      fetchData();
    } catch (error) {
      throw error;
    }
  };

  const handleDeleteCollection = async (name: string) => {
    try {
      await storageApi.deleteCollection(name);
      alert('Collection 删除成功');
      fetchData();
    } catch (error) {
      alert('删除 Collection 失败');
    }
  };

  const handleRefresh = () => {
    fetchData();
  };

  const totalVectors = collections.reduce((sum, c) => sum + c.vectors, 0);

  const collectionColumns = [
    { key: 'name', title: 'Collection', dataIndex: 'name' },
    { key: 'vectors', title: '向量数量', render: (_: unknown, record: VectorCollection) => record.vectors?.toLocaleString() ?? '-' },
    { key: 'dimension', title: '维度', dataIndex: 'dimension' },
    { key: 'size', title: '存储大小', dataIndex: 'size' },
    {
      key: 'status',
      title: '状态',
      render: (_: unknown, record: VectorCollection) => {
        switch (record.status) {
          case 'green':
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-success-light text-green-300">健康</span>;
          case 'yellow':
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-warning-light text-amber-300">警告</span>;
          case 'red':
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-error-light text-red-300">异常</span>;
          default:
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-dark-hover text-gray-300">{record.status}</span>;
        }
      },
    },
    {
      key: 'action',
      title: '操作',
      align: 'center' as const,
      render: (_: unknown, record: VectorCollection) => (
        <div className="flex items-center justify-center gap-2">
          <button className="text-primary hover:text-primary-hover" onClick={() => console.log('Detail', record)}>详情</button>
          <button className="text-error hover:text-red-600" onClick={() => handleDeleteCollection(record.name)}>删除</button>
        </div>
      ),
    },
  ];

  const pvcColumns = [
    { key: 'name', title: 'PVC名称', dataIndex: 'name' },
    { key: 'namespace', title: '命名空间', dataIndex: 'namespace' },
    { key: 'size', title: '大小', dataIndex: 'size' },
    { key: 'used', title: '已用', dataIndex: 'used' },
    { key: 'storageClass', title: '存储类', dataIndex: 'storageClass' },
    {
      key: 'status',
      title: '状态',
      render: (_: unknown, record: PVC) => {
        switch (record.status) {
          case 'Bound':
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-success-light text-green-300">已绑定</span>;
          case 'Pending':
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-warning-light text-amber-300">等待中</span>;
          case 'Lost':
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-error-light text-red-300">丢失</span>;
          default:
            return <span className="px-2 py-1 rounded-md text-xs font-medium bg-dark-hover text-gray-300">{record.status}</span>;
        }
      },
    },
    {
      key: 'action',
      title: '操作',
      align: 'center' as const,
      render: (_: unknown, record: PVC) => (
        <div className="flex items-center justify-center gap-2">
          <button className="text-primary hover:text-primary-hover" onClick={() => console.log('Detail', record)}>详情</button>
          <button className="text-primary hover:text-primary-hover" onClick={() => handleExpandPVC(record)}>扩容</button>
          <button className="text-error hover:text-red-600" onClick={() => handleDeletePVC(record.name)}>删除</button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="存储管理"
        description="向量存储、模型存储、PVC 生命周期管理"
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
          <div className="text-sm text-gray-500 mb-1">向量总数</div>
          <div className="text-2xl font-semibold text-gray-100">{totalVectors.toLocaleString()}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">Collection数</div>
          <div className="text-2xl font-semibold text-gray-100">{collections.length}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">模型数量</div>
          <div className="text-2xl font-semibold text-gray-100">{modelCount}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">PVC数量</div>
          <div className="text-2xl font-semibold text-gray-100">{pvcs.length}</div>
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
            onClick={() => { setActiveTab('collections'); }}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${activeTab === 'collections' ? 'text-primary' : 'text-gray-500 hover:text-gray-300'}`}
          >
            向量存储
            {activeTab === 'collections' && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
          </button>
          <button
            onClick={() => { setActiveTab('pvcs'); }}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${activeTab === 'pvcs' ? 'text-primary' : 'text-gray-500 hover:text-gray-300'}`}
          >
            PVC 管理
            {activeTab === 'pvcs' && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
          </button>
        </div>

        <div className="p-4">
          {activeTab === 'collections' && (
            <div className="mb-4 flex justify-end">
              <Button variant="primary" icon={<Plus size={16} />} onClick={handleCreateCollection}>
                创建 Collection
              </Button>
            </div>
          )}
          {activeTab === 'pvcs' && (
            <div className="mb-4 flex justify-end">
              <Button variant="primary" icon={<Plus size={16} />} onClick={handleCreatePVC}>
                创建 PVC
              </Button>
            </div>
          )}
          <Table
            columns={activeTab === 'collections' ? collectionColumns : pvcColumns as any}
            data={activeTab === 'collections' ? collections : pvcs as any}
            rowKey="id"
            loading={loading}
            emptyText={activeTab === 'collections' ? '暂无向量存储数据' : '暂无PVC数据'}
          />
        </div>
      </motion.div>

      <PVCModal
        open={pvcModalOpen}
        onCancel={() => setPvcModalOpen(false)}
        onOk={handlePVCOk}
        mode={pvcMode}
        initialValues={editingPVC}
      />

      <CollectionModal
        open={collectionModalOpen}
        onCancel={() => setCollectionModalOpen(false)}
        onOk={handleCollectionOk}
      />
    </div>
  );
};

export default Storage;
