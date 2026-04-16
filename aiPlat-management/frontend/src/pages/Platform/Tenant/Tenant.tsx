import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Plus, RotateCcw, Trash2, Users, PauseCircle, PlayCircle } from 'lucide-react';
import { Table, Button, Modal, Select, toast } from '../../../components/ui';
import PageHeader from '../../../components/common/PageHeader';
import { tenantApi } from '../../../services';
import type { TenantInfo } from '../../../services';

const statusConfig: Record<string, { bg: string; text: string; label: string }> = {
  active: { bg: 'bg-success-light', text: 'text-green-300', label: '活跃' },
  suspended: { bg: 'bg-error-light', text: 'text-red-300', label: '已暂停' },
  pending: { bg: 'bg-warning-light', text: 'text-amber-300', label: '待审核' },
};

const Tenant: React.FC = () => {
  const [tenants, setTenants] = useState<TenantInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [deleteModal, setDeleteModal] = useState<{ open: boolean; tenant: TenantInfo | null }>({ open: false, tenant: null });

  const fetchTenants = useCallback(async () => {
    setLoading(true);
    try {
      const res = await tenantApi.list({ status: statusFilter || undefined });
      setTenants(res.tenants || []);
    } catch {
      toast.error('获取租户列表失败');
      setTenants([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchTenants();
  }, [fetchTenants]);

  const handleDelete = async () => {
    if (!deleteModal.tenant) return;
    try {
      await tenantApi.delete(deleteModal.tenant.id);
      toast.success('租户已删除');
      setDeleteModal({ open: false, tenant: null });
      fetchTenants();
    } catch {
      toast.error('删除失败');
    }
  };

  const handleToggleSuspend = async (tenant: TenantInfo) => {
    try {
      if (tenant.status === 'suspended') {
        await tenantApi.resume(tenant.id);
        toast.success(`租户 "${tenant.name}" 已恢复`);
      } else {
        await tenantApi.suspend(tenant.id);
        toast.success(`租户 "${tenant.name}" 已暂停`);
      }
      fetchTenants();
    } catch {
      toast.error('操作失败');
    }
  };

  const filteredTenants = tenants.filter(t => {
    if (statusFilter && t.status !== statusFilter) return false;
    return true;
  });

  const columns = [
    {
      key: 'name',
      title: '租户名称',
      render: (_: unknown, record: TenantInfo) => (
        <span className="font-medium text-gray-100">{record.name}</span>
      ),
    },
    {
      key: 'description',
      title: '描述',
      render: (_: unknown, record: TenantInfo) => (
        <span className="text-gray-500">{record.description}</span>
      ),
    },
    {
      key: 'status',
      title: '状态',
      render: (_: unknown, record: TenantInfo) => {
        const cfg = statusConfig[record.status] || { bg: 'bg-dark-hover', text: 'text-gray-300', label: record.status };
        return (
          <span className={`inline-flex px-2 py-1 rounded-md text-xs font-medium ${cfg.bg} ${cfg.text}`}>
            {cfg.label}
          </span>
        );
      },
    },
    {
      key: 'gpu',
      title: 'GPU配额',
      render: (_: unknown, record: TenantInfo) => `${record.quota.gpu_limit}`,
    },
    {
      key: 'storage',
      title: '存储配额',
      render: (_: unknown, record: TenantInfo) => `${record.quota.storage_limit_gb} GB`,
    },
    {
      key: 'user_count',
      title: '用户数',
      render: (_: unknown, record: TenantInfo) => (
        <div className="flex items-center gap-1">
          <Users size={14} className="text-gray-400" />
          <span>{record.user_count}</span>
        </div>
      ),
    },
    {
      key: 'actions',
      title: '操作',
      align: 'center' as const,
      render: (_: unknown, record: TenantInfo) => (
        <div className="flex items-center justify-center gap-1">
          <button
            className="p-1.5 rounded-lg text-gray-500 hover:bg-dark-hover transition-colors"
            title={record.status === 'suspended' ? '恢复' : '暂停'}
            onClick={() => handleToggleSuspend(record)}
          >
            {record.status === 'suspended' ? <PlayCircle size={16} /> : <PauseCircle size={16} />}
          </button>
          <button
            className="p-1.5 rounded-lg text-error hover:bg-error-light transition-colors"
            title="删除"
            onClick={() => setDeleteModal({ open: true, tenant: record })}
          >
            <Trash2 size={16} />
          </button>
        </div>
      ),
    },
  ];

  const activeCount = tenants.filter(t => t.status === 'active').length;
  const totalGpu = tenants.reduce((s, t) => s + t.quota.gpu_limit, 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="多租户"
        description="管理租户资源配额、隔离策略与访问权限"
        extra={
          <div className="flex items-center gap-3">
            <Select
              value={statusFilter}
              onChange={(v) => setStatusFilter(v || undefined)}
              options={Object.entries(statusConfig).map(([k, v]) => ({ value: k, label: v.label }))}
              placeholder="状态筛选"
            />
            <Button
              icon={<RotateCcw className="w-4 h-4" />}
              onClick={fetchTenants}
              loading={loading}
            >
              刷新
            </Button>
            <Button
              variant="primary"
              icon={<Plus className="w-4 h-4" />}
            >
              创建租户
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
          <div className="text-sm text-gray-500 mb-1">总租户</div>
          <div className="text-2xl font-semibold text-gray-100">{tenants.length}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">活跃租户</div>
          <div className="text-2xl font-semibold text-success">{activeCount}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">总GPU配额</div>
          <div className="text-2xl font-semibold text-gray-100">{totalGpu}<span className="text-sm text-gray-500 ml-1">卡</span></div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">总用户</div>
          <div className="flex items-center gap-2">
            <Users size={18} className="text-gray-400" />
            <span className="text-2xl font-semibold text-gray-100">{tenants.reduce((s, t) => s + t.user_count, 0)}</span>
          </div>
        </motion.div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="bg-dark-card rounded-xl border border-dark-border overflow-hidden"
      >
        <Table
          columns={columns}
          data={filteredTenants}
          rowKey="id"
          loading={loading}
          emptyText="暂无租户数据"
        />
      </motion.div>

      <Modal
        open={deleteModal.open}
        onClose={() => setDeleteModal({ open: false, tenant: null })}
        title="确认删除"
        footer={
          <>
            <Button onClick={() => setDeleteModal({ open: false, tenant: null })}>
              取消
            </Button>
            <Button variant="danger" onClick={handleDelete}>
              确认删除
            </Button>
          </>
        }
      >
        <p className="text-gray-400">
          确定要删除租户 "{deleteModal.tenant?.name}" 吗？此操作不可撤销。
        </p>
      </Modal>
    </div>
  );
};

export default Tenant;
