import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Plus, RotateCcw, Trash2, Lock, Unlock, User } from 'lucide-react';
import { Table, Button, Modal, Select, toast } from '../../../components/ui';
import PageHeader from '../../../components/common/PageHeader';
import { authApi } from '../../../services';
import type { AuthUser } from '../../../services';

const roleConfig: Record<string, { bg: string; text: string; label: string }> = {
  admin: { bg: 'bg-red-50', text: 'text-red-300', label: '管理员' },
  operator: { bg: 'bg-blue-50', text: 'text-blue-300', label: '运维' },
  developer: { bg: 'bg-green-50', text: 'text-green-300', label: '开发者' },
  viewer: { bg: 'bg-dark-hover', text: 'text-gray-300', label: '只读' },
};

const statusConfig: Record<string, { bg: string; text: string; label: string }> = {
  active: { bg: 'bg-success-light', text: 'text-green-300', label: '活跃' },
  inactive: { bg: 'bg-dark-hover', text: 'text-gray-300', label: '未激活' },
  locked: { bg: 'bg-error-light', text: 'text-red-300', label: '锁定' },
};

const Auth: React.FC = () => {
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [roleFilter, setRoleFilter] = useState<string | undefined>();
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [deleteModal, setDeleteModal] = useState<{ open: boolean; user: AuthUser | null }>({ open: false, user: null });
  const [deleting, setDeleting] = useState(false);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await authApi.list({ role: roleFilter || undefined, status: statusFilter || undefined });
      setUsers(res.users || []);
    } catch {
      toast.error('获取用户列表失败');
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, [roleFilter, statusFilter]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleDelete = async () => {
    if (!deleteModal.user || deleting) return;
    try {
      setDeleting(true);
      await authApi.delete(deleteModal.user.id);
      toast.success('用户已删除');
      setDeleteModal({ open: false, user: null });
      fetchUsers();
    } catch {
      toast.error('删除失败');
    }
    finally { setDeleting(false); }
  };

  const handleToggleLock = async (user: AuthUser) => {
    const newStatus = user.status === 'locked' ? 'active' : 'locked';
    try {
      await authApi.update(user.id, { status: newStatus });
      toast.success(`用户 "${user.username}" 已${newStatus === 'locked' ? '锁定' : '解锁'}`);
      fetchUsers();
    } catch {
      toast.error('操作失败');
    }
  };

  const filteredUsers = users.filter(u => {
    if (roleFilter && u.role !== roleFilter) return false;
    if (statusFilter && u.status !== statusFilter) return false;
    return true;
  });

  const columns = [
    {
      key: 'username',
      title: '用户名',
      render: (_: unknown, record: AuthUser) => (
        <div className="flex items-center gap-2">
          <User size={16} className="text-gray-400" />
          <span className="font-medium text-gray-100">{record.username}</span>
        </div>
      ),
    },
    {
      key: 'email',
      title: '邮箱',
      render: (_: unknown, record: AuthUser) => (
        <span className="text-gray-500">{record.email}</span>
      ),
    },
    {
      key: 'role',
      title: '角色',
      render: (_: unknown, record: AuthUser) => {
        const cfg = roleConfig[record.role] || { bg: 'bg-dark-hover', text: 'text-gray-300', label: record.role };
        return (
          <span className={`inline-flex px-2 py-1 rounded-md text-xs font-medium ${cfg.bg} ${cfg.text}`}>
            {cfg.label}
          </span>
        );
      },
    },
    {
      key: 'status',
      title: '状态',
      render: (_: unknown, record: AuthUser) => {
        const cfg = statusConfig[record.status] || { bg: 'bg-dark-hover', text: 'text-gray-300', label: record.status };
        return (
          <span className={`inline-flex px-2 py-1 rounded-md text-xs font-medium ${cfg.bg} ${cfg.text}`}>
            {cfg.label}
          </span>
        );
      },
    },
    {
      key: 'last_login',
      title: '最近登录',
      render: (_: unknown, record: AuthUser) => (
        record.last_login ? new Date(record.last_login).toLocaleString('zh-CN') : <span className="text-gray-400">-</span>
      ),
    },
    {
      key: 'actions',
      title: '操作',
      align: 'center' as const,
      render: (_: unknown, record: AuthUser) => (
        <div className="flex items-center justify-center gap-1">
          <button
            className="p-1.5 rounded-lg text-gray-500 hover:bg-dark-hover transition-colors"
            title={record.status === 'locked' ? '解锁' : '锁定'}
            onClick={() => handleToggleLock(record)}
          >
            {record.status === 'locked' ? <Unlock size={16} /> : <Lock size={16} />}
          </button>
          <button
            className="p-1.5 rounded-lg text-error hover:bg-error-light transition-colors"
            title="删除"
            onClick={() => setDeleteModal({ open: true, user: record })}
          >
            <Trash2 size={16} />
          </button>
        </div>
      ),
    },
  ];

  const activeCount = users.filter(u => u.status === 'active').length;
  const lockedCount = users.filter(u => u.status === 'locked').length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="认证鉴权"
        description="管理用户身份认证、角色权限与访问控制策略"
        extra={
          <div className="flex items-center gap-3">
            <Select
              value={roleFilter}
              onChange={(v) => setRoleFilter(v || undefined)}
              options={Object.entries(roleConfig).map(([k, v]) => ({ value: k, label: v.label }))}
              placeholder="角色筛选"
            />
            <Select
              value={statusFilter}
              onChange={(v) => setStatusFilter(v || undefined)}
              options={Object.entries(statusConfig).map(([k, v]) => ({ value: k, label: v.label }))}
              placeholder="状态筛选"
            />
            <Button
              icon={<RotateCcw className="w-4 h-4" />}
              onClick={fetchUsers}
              loading={loading}
            >
              刷新
            </Button>
            <Button
              variant="primary"
              icon={<Plus className="w-4 h-4" />}
            >
              添加用户
            </Button>
          </div>
        }
      />

      <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group mb-3">
        <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
          <div><span className="text-gray-300">用户名</span><span className="ml-2 text-gray-600">登录用的唯一用户名</span></div>
          <div><span className="text-gray-300">邮箱</span><span className="ml-2 text-gray-600">用户绑定的邮箱地址</span></div>
          <div><span className="text-gray-300">角色</span><span className="ml-2 text-gray-600">管理员 / 运维 / 开发者 / 只读，决定操作权限</span></div>
          <div><span className="text-gray-300">状态</span><span className="ml-2 text-gray-600">活跃 / 未激活 / 锁定。锁定后无法登录</span></div>
          <div><span className="text-gray-300">最近登录</span><span className="ml-2 text-gray-600">用户最后一次登录的时间戳</span></div>
          <div><span className="text-gray-300">操作</span><span className="ml-2 text-gray-600">锁定/解锁/删除。锁定后用户无法访问系统</span></div>
        </div>
      </details>

      <div className="grid grid-cols-3 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">总用户</div>
          <div className="flex items-center gap-2">
            <User size={18} className="text-gray-400" />
            <span className="text-2xl font-semibold text-gray-100">{users.length}</span>
          </div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">活跃用户</div>
          <div className="text-2xl font-semibold text-success">{activeCount}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">锁定用户</div>
          <div className="text-2xl font-semibold" style={{ color: lockedCount > 0 ? '#ef4444' : undefined }}>{lockedCount}</div>
        </motion.div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="bg-dark-card rounded-xl border border-dark-border overflow-hidden"
      >
        <Table
          columns={columns}
          data={filteredUsers}
          rowKey="id"
          loading={loading}
          emptyText="暂无用户数据"
        />
      </motion.div>

      <Modal
        open={deleteModal.open}
        onClose={() => setDeleteModal({ open: false, user: null })}
        title="确认删除"
        footer={
          <>
            <Button disabled={deleting} onClick={() => setDeleteModal({ open: false, user: null })}>
              取消
            </Button>
            <Button variant="danger" loading={deleting} onClick={handleDelete}>
              确认删除
            </Button>
          </>
        }
      >
        <p className="text-gray-400">
          确定要删除用户 "{deleteModal.user?.username}" 吗？此操作不可撤销。
        </p>
      </Modal>
    </div>
  );
};

export default Auth;
