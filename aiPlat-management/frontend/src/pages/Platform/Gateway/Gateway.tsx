import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Plus, RotateCcw, Trash2, Globe, Zap } from 'lucide-react';
import { Table, Button, Modal, Switch, toast } from '../../../components/ui';
import PageHeader from '../../../components/common/PageHeader';
import { gatewayApi } from '../../../services';
import type { GatewayRoute } from '../../../services';

const methodColors: Record<string, { bg: string; text: string }> = {
  GET: { bg: 'bg-green-50', text: 'text-green-300' },
  POST: { bg: 'bg-blue-50', text: 'text-blue-300' },
  PUT: { bg: 'bg-orange-50', text: 'text-orange-300' },
  DELETE: { bg: 'bg-red-50', text: 'text-red-300' },
  PATCH: { bg: 'bg-purple-50', text: 'text-purple-300' },
};

const Gateway: React.FC = () => {
  const [routes, setRoutes] = useState<GatewayRoute[]>([]);
  const [loading, setLoading] = useState(false);
  const [deleteModal, setDeleteModal] = useState<{ open: boolean; route: GatewayRoute | null }>({ open: false, route: null });

  const fetchRoutes = useCallback(async () => {
    setLoading(true);
    try {
      const res = await gatewayApi.list();
      setRoutes(res.routes || []);
    } catch {
      toast.error('获取路由列表失败');
      setRoutes([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRoutes();
  }, [fetchRoutes]);

  const handleToggle = async (route: GatewayRoute) => {
    try {
      await gatewayApi.update(route.id, { enabled: !route.enabled });
      toast.success(`路由 "${route.name}" 已${route.enabled ? '禁用' : '启用'}`);
      fetchRoutes();
    } catch {
      toast.error('操作失败');
    }
  };

  const handleDelete = async () => {
    if (!deleteModal.route) return;
    try {
      await gatewayApi.delete(deleteModal.route.id);
      toast.success('路由已删除');
      setDeleteModal({ open: false, route: null });
      fetchRoutes();
    } catch {
      toast.error('删除失败');
    }
  };

  const columns = [
    {
      key: 'name',
      title: '路由名称',
      render: (_: unknown, record: GatewayRoute) => (
        <span className="font-medium text-gray-100">{record.name}</span>
      ),
    },
    {
      key: 'path',
      title: '路径',
      render: (_: unknown, record: GatewayRoute) => (
        <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded text-gray-300">{record.path}</code>
      ),
    },
    {
      key: 'backend',
      title: '后端服务',
      render: (_: unknown, record: GatewayRoute) => (
        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium bg-dark-hover text-gray-300">
          <Globe size={12} />
          {record.backend}
        </span>
      ),
    },
    {
      key: 'methods',
      title: '方法',
      render: (_: unknown, record: GatewayRoute) => (
        <div className="flex flex-wrap gap-1">
          {record.methods.map((m: string) => {
            const colors = methodColors[m] || { bg: 'bg-dark-hover', text: 'text-gray-300' };
            return (
              <span key={m} className={`px-2 py-0.5 rounded text-xs font-medium ${colors.bg} ${colors.text}`}>
                {m}
              </span>
            );
          })}
        </div>
      ),
    },
    {
      key: 'rate_limit',
      title: '限流',
      render: (_: unknown, record: GatewayRoute) => `${record.rate_limit}/min`,
    },
    {
      key: 'enabled',
      title: '状态',
      render: (_: unknown, record: GatewayRoute) => (
        <Switch
          checked={record.enabled}
          onChange={() => handleToggle(record)}
        />
      ),
    },
    {
      key: 'actions',
      title: '操作',
      align: 'center' as const,
      render: (_: unknown, record: GatewayRoute) => (
        <div className="flex items-center justify-center gap-1">
          <button
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
            title="测试"
          >
            <Zap size={16} />
          </button>
          <button
            className="p-1.5 rounded-lg text-error hover:bg-error-light transition-colors"
            title="删除"
            onClick={() => setDeleteModal({ open: true, route: record })}
          >
            <Trash2 size={16} />
          </button>
        </div>
      ),
    },
  ];

  const enabledCount = routes.filter(r => r.enabled).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="API网关"
        description="管理API路由、限流、熔断与负载均衡策略"
        extra={
          <div className="flex items-center gap-3">
            <Button
              icon={<RotateCcw className="w-4 h-4" />}
              onClick={fetchRoutes}
              loading={loading}
            >
              刷新
            </Button>
            <Button
              variant="primary"
              icon={<Plus className="w-4 h-4" />}
            >
              创建路由
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
          <div className="text-sm text-gray-400 mb-1">总路由数</div>
          <div className="text-2xl font-semibold text-gray-100">{routes.length}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-400 mb-1">已启用</div>
          <div className="text-2xl font-semibold text-success">{enabledCount}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-400 mb-1">总限流</div>
          <div className="text-2xl font-semibold text-gray-100">{routes.reduce((s, r) => s + r.rate_limit, 0)}<span className="text-sm text-gray-400 ml-1">/min</span></div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-400 mb-1">平均超时</div>
          <div className="text-2xl font-semibold text-gray-100">
            {routes.length > 0 ? Math.round(routes.reduce((s, r) => s + r.timeout, 0) / routes.length) : 0}
            <span className="text-sm text-gray-400 ml-1">s</span>
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
          data={routes}
          rowKey="id"
          loading={loading}
          emptyText="暂无路由数据"
        />
      </motion.div>

      <Modal
        open={deleteModal.open}
        onClose={() => setDeleteModal({ open: false, route: null })}
        title="确认删除"
        footer={
          <>
            <Button onClick={() => setDeleteModal({ open: false, route: null })}>
              取消
            </Button>
            <Button variant="danger" onClick={handleDelete}>
              确认删除
            </Button>
          </>
        }
      >
        <p className="text-gray-600">
          确定要删除路由 "{deleteModal.route?.name}" 吗？此操作不可撤销。
        </p>
      </Modal>
    </div>
  );
};

export default Gateway;
