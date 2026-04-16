import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Plus, RotateCw, Network, Settings, Trash2, Laptop } from 'lucide-react';
import { Table, Button, Modal, Select, toast } from '../../../components/ui';
import PageHeader from '../../../components/common/PageHeader';
import AddModelModal from '../../../components/infra/AddModelModal';
import { modelApi, type Model, type Provider } from '../../../services';

const sourceConfig: Record<string, { bg: string; text: string; label: string }> = {
  config: { bg: 'bg-blue-50', text: 'text-blue-300', label: '内置' },
  local: { bg: 'bg-green-50', text: 'text-green-300', label: '本地' },
  external: { bg: 'bg-orange-50', text: 'text-orange-300', label: '自定义' },
};

const statusConfig: Record<string, { bg: string; text: string; label: string }> = {
  available: { bg: 'bg-success-light', text: 'text-green-300', label: '可用' },
  unavailable: { bg: 'bg-warning-light', text: 'text-amber-300', label: '不可用' },
  error: { bg: 'bg-error-light', text: 'text-red-300', label: '错误' },
  not_configured: { bg: 'bg-dark-hover', text: 'text-gray-300', label: '未配置' },
};

const Models: React.FC = () => {
  const [models, setModels] = useState<Model[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(false);
  const [sourceFilter, setSourceFilter] = useState<string | undefined>();
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [searchText, setSearchText] = useState('');
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [deleteModal, setDeleteModal] = useState<{ open: boolean; model: Model | null }>({ open: false, model: null });

  const fetchModels = async () => {
    setLoading(true);
    try {
      const [modelsRes, providersRes] = await Promise.all([
        modelApi.list({ source: sourceFilter, status: statusFilter }),
        modelApi.getProviders(),
      ]);
      setModels(modelsRes.models || []);
      setProviders(providersRes.providers || []);
    } catch (error) {
      toast.error('获取模型列表失败');
      console.error('Failed to fetch models:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchModels();
  }, [sourceFilter, statusFilter]);

  const handleEnable = async (model: Model, enabled: boolean) => {
    try {
      if (enabled) {
        await modelApi.enable(model.id);
        toast.success(`模型 ${model.name} 已启用`);
      } else {
        await modelApi.disable(model.id);
        toast.success(`模型 ${model.name} 已禁用`);
      }
      fetchModels();
    } catch (error) {
      toast.error('操作失败');
    }
  };

  const handleDelete = async () => {
    if (!deleteModal.model) return;
    try {
      await modelApi.delete(deleteModal.model.id);
      toast.success('模型已删除');
      setDeleteModal({ open: false, model: null });
      fetchModels();
    } catch (error) {
      toast.error('删除失败');
    }
  };

  const handleTestConnectivity = async (model: Model) => {
    try {
      const result = await modelApi.testConnectivity(model.id);
      if (result.success) {
        toast.success('连通性测试通过');
      } else {
        toast.error('连通性测试失败', String(result.error || ''));
      }
    } catch (error) {
      toast.error('测试失败');
    }
  };

  const handleScanLocal = async () => {
    try {
      const result = await modelApi.scanLocal();
      toast.success(`发现 ${result.total} 个本地模型`);
      fetchModels();
    } catch (error) {
      toast.error('扫描失败，请确保 Ollama 正在运行');
    }
  };

  const filteredModels = models.filter(m =>
    !searchText ||
    m.name.toLowerCase().includes(searchText.toLowerCase()) ||
    m.displayName?.toLowerCase().includes(searchText.toLowerCase())
  );

  const columns = [
    {
      key: 'name',
      title: '模型名称',
      render: (_: unknown, record: Model) => (
        <div className="space-y-1">
          <div className="font-medium text-gray-100">{record.displayName || record.name}</div>
          <div className="text-xs text-gray-500">{record.name}</div>
        </div>
      ),
    },
    {
      key: 'type',
      title: '类型',
      render: (_: unknown, record: Model) => (
        <span className="px-2 py-1 rounded-md text-xs font-medium bg-dark-hover text-gray-300">{record.type.toUpperCase()}</span>
      ),
    },
    {
      key: 'source',
      title: '来源',
      render: (_: unknown, record: Model) => {
        const config = sourceConfig[record.source] || { bg: 'bg-dark-hover', text: 'text-gray-300', label: record.source };
        return (
          <span className={`inline-flex px-2 py-1 rounded-md text-xs font-medium ${config.bg} ${config.text}`}>
            {config.label}
          </span>
        );
      },
    },
    { key: 'provider', title: 'Provider', dataIndex: 'provider' },
    {
      key: 'status',
      title: '状态',
      render: (_: unknown, record: Model) => {
        const config = statusConfig[record.status] || { bg: 'bg-dark-hover', text: 'text-gray-300', label: record.status };
        return (
          <span className={`inline-flex px-2 py-1 rounded-md text-xs font-medium ${config.bg} ${config.text}`}>
            {config.label}
          </span>
        );
      },
    },
    {
      key: 'enabled',
      title: '启用',
      render: (_: unknown, record: Model) => (
        <input
          type="checkbox"
          checked={record.enabled}
          onChange={(e) => handleEnable(record, e.target.checked)}
          disabled={record.source === 'config'}
          className="w-4 h-4 text-primary bg-dark-card border-dark-border rounded focus:ring-primary disabled:opacity-50"
        />
      ),
    },
    {
      key: 'action',
      title: '操作',
      align: 'center' as const,
      render: (_: unknown, record: Model) => (
        <div className="flex items-center justify-center gap-1">
          <button
            className="p-1.5 rounded-lg text-gray-500 hover:bg-dark-hover transition-colors"
            title="测试连通性"
            onClick={() => handleTestConnectivity(record)}
          >
            <Network size={16} />
          </button>
          {record.source === 'external' && (
            <>
              <button
                className="p-1.5 rounded-lg text-gray-500 hover:bg-dark-hover transition-colors"
                title="配置"
              >
                <Settings size={16} />
              </button>
              <button
                className="p-1.5 rounded-lg text-error hover:bg-error-light transition-colors"
                title="删除"
                onClick={() => setDeleteModal({ open: true, model: record })}
              >
                <Trash2 size={16} />
              </button>
            </>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="模型管理"
        description="管理 AI 模型配置，包括配置文件模型、本地 Ollama 模型和自定义模型"
        extra={
          <div className="flex items-center gap-3">
            <Button icon={<Laptop size={16} />} onClick={handleScanLocal}>
              扫描本地模型
            </Button>
            <Button icon={<RotateCw size={16} />} onClick={fetchModels} loading={loading}>
              刷新
            </Button>
            <Button variant="primary" icon={<Plus size={16} />} onClick={() => setAddModalOpen(true)}>
              添加模型
            </Button>
          </div>
        }
      />

      <AddModelModal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onSuccess={fetchModels}
        providers={providers}
      />

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-dark-card rounded-xl border border-dark-border overflow-hidden"
      >
        <div className="p-4 flex flex-wrap items-center gap-4 border-b border-gray-100">
          <Select
            value={sourceFilter}
            onChange={(v) => setSourceFilter(v || undefined)}
            options={[
              { value: 'config', label: '内置' },
              { value: 'local', label: '本地' },
              { value: 'external', label: '自定义' },
            ]}
            placeholder="来源筛选"
          />
          <Select
            value={statusFilter}
            onChange={(v) => setStatusFilter(v || undefined)}
            options={[
              { value: 'available', label: '可用' },
              { value: 'unavailable', label: '不可用' },
              { value: 'error', label: '错误' },
              { value: 'not_configured', label: '未配置' },
            ]}
            placeholder="状态筛选"
          />
          <input
            type="text"
            placeholder="搜索模型..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 w-48"
          />
        </div>

        <Table columns={columns} data={filteredModels} rowKey="id" loading={loading} emptyText="暂无模型数据" />

        <div className="p-4 mt-4 border-t border-gray-100 text-xs text-gray-500 space-y-1">
          <p className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-full bg-blue-500"></span>
            内置模型：配置文件中定义，只读
          </p>
          <p className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-full bg-green-500"></span>
            本地模型：Ollama 自动扫描，点击"扫描本地模型"刷新
          </p>
          <p className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-full bg-orange-500"></span>
            自定义模型：用户添加，可编辑删除
          </p>
        </div>
      </motion.div>

      <Modal
        open={deleteModal.open}
        onClose={() => setDeleteModal({ open: false, model: null })}
        title="确认删除"
        footer={
          <>
            <Button onClick={() => setDeleteModal({ open: false, model: null })}>
              取消
            </Button>
            <Button variant="danger" onClick={handleDelete}>
              删除
            </Button>
          </>
        }
      >
        <p className="text-gray-600">
          确定要删除模型 {deleteModal.model?.name} 吗？此操作不可恢复。
        </p>
      </Modal>
    </div>
  );
};

export default Models;
