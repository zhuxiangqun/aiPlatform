import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Plus, RotateCw, Trash2, Link, Zap } from 'lucide-react';
import { Table, Button, Modal, Select } from '../../../components/ui';
import PageHeader from '../../../components/common/PageHeader';
import { channelApi } from '../../../services';
import type { Channel } from '../../../services';

const typeConfig: Record<string, { bg: string; text: string; label: string }> = {
  telegram: { bg: 'bg-blue-50', text: 'text-blue-300', label: 'Telegram' },
  slack: { bg: 'bg-purple-50', text: 'text-purple-300', label: 'Slack' },
  webchat: { bg: 'bg-green-50', text: 'text-green-300', label: 'WebChat' },
  api: { bg: 'bg-orange-50', text: 'text-orange-300', label: 'API' },
  wechat: { bg: 'bg-cyan-50', text: 'text-cyan-300', label: '微信' },
};

const channelStatusConfig: Record<string, { bg: string; text: string; label: string }> = {
  connected: { bg: 'bg-success-light', text: 'text-green-300', label: '已连接' },
  disconnected: { bg: 'bg-dark-hover', text: 'text-gray-300', label: '未连接' },
  error: { bg: 'bg-error-light', text: 'text-red-300', label: '异常' },
};

const Channels: React.FC = () => {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(false);
  const [typeFilter, setTypeFilter] = useState<string | undefined>();
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [deleteModal, setDeleteModal] = useState<{ open: boolean; channel: Channel | null }>({ open: false, channel: null });

  const fetchChannels = useCallback(async () => {
    setLoading(true);
    try {
      const res = await channelApi.list({ type: typeFilter || undefined, status: statusFilter || undefined });
      setChannels(res.channels || []);
    } catch {
      alert('获取渠道列表失败');
      setChannels([]);
    } finally {
      setLoading(false);
    }
  }, [typeFilter, statusFilter]);

  useEffect(() => {
    fetchChannels();
  }, [fetchChannels]);

  const handleDelete = async () => {
    if (!deleteModal.channel) return;
    try {
      await channelApi.delete(deleteModal.channel.id);
      alert('渠道已删除');
      setDeleteModal({ open: false, channel: null });
      fetchChannels();
    } catch {
      alert('删除失败');
    }
  };

  const handleTest = async (channel: Channel) => {
    try {
      const res = await channelApi.test(channel.id);
      if (res.success) {
        alert(`渠道 "${channel.name}" 连接正常`);
      } else {
        alert(`渠道 "${channel.name}" 连接失败: ${res.message}`);
      }
    } catch {
      alert(`渠道 "${channel.name}" 测试请求失败`);
    }
  };

  const filteredChannels = channels.filter(c => {
    if (typeFilter && c.type !== typeFilter) return false;
    if (statusFilter && c.status !== statusFilter) return false;
    return true;
  });

  const columns = [
    {
      key: 'name',
      title: '渠道名称',
      render: (_: unknown, record: Channel) => (
        <span className="font-medium text-gray-100">{record.name}</span>
      ),
    },
    {
      key: 'type',
      title: '类型',
      render: (_: unknown, record: Channel) => {
        const cfg = typeConfig[record.type] || { bg: 'bg-dark-hover', text: 'text-gray-300', label: record.type };
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
      render: (_: unknown, record: Channel) => {
        const cfg = channelStatusConfig[record.status] || { bg: 'bg-dark-hover', text: 'text-gray-300', label: record.status };
        return (
          <span className={`inline-flex px-2 py-1 rounded-md text-xs font-medium ${cfg.bg} ${cfg.text}`}>
            {cfg.label}
          </span>
        );
      },
    },
    {
      key: 'message_count',
      title: '消息数',
      render: (_: unknown, record: Channel) => record.message_count.toLocaleString(),
    },
    {
      key: 'last_message_at',
      title: '最近消息',
      render: (_: unknown, record: Channel) => (
        record.last_message_at ? new Date(record.last_message_at).toLocaleString('zh-CN') : <span className="text-gray-400">-</span>
      ),
    },
    {
      key: 'actions',
      title: '操作',
      align: 'center' as const,
      render: (_: unknown, record: Channel) => (
        <div className="flex items-center justify-center gap-1">
          <button
            className="p-1.5 rounded-lg text-gray-500 hover:bg-dark-hover transition-colors"
            title="测试连接"
            onClick={() => handleTest(record)}
          >
            <Zap size={14} />
          </button>
          <button
            className="p-1.5 rounded-lg text-error hover:bg-error-light transition-colors"
            title="删除"
            onClick={() => setDeleteModal({ open: true, channel: record })}
          >
            <Trash2 size={14} />
          </button>
        </div>
      ),
    },
  ];

  const connectedCount = channels.filter(c => c.status === 'connected').length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="渠道管理"
        description="管理多渠道消息适配器，包括Telegram、Slack、WebChat、API接入等"
        extra={
          <div className="flex items-center gap-3">
            <Select
              value={typeFilter}
              onChange={(v) => setTypeFilter(v || undefined)}
              options={Object.entries(typeConfig).map(([k, v]) => ({ value: k, label: v.label }))}
              placeholder="类型筛选"
            />
            <Select
              value={statusFilter}
              onChange={(v) => setStatusFilter(v || undefined)}
              options={Object.entries(channelStatusConfig).map(([k, v]) => ({ value: k, label: v.label }))}
              placeholder="状态筛选"
            />
            <Button
              icon={<RotateCw className="w-4 h-4" />}
              onClick={fetchChannels}
              loading={loading}
            >
              刷新
            </Button>
            <Button
              variant="primary"
              icon={<Plus className="w-4 h-4" />}
            >
              添加渠道
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
          <div className="text-sm text-gray-500 mb-1">总渠道</div>
          <div className="flex items-center gap-2">
            <Link size={16} className="text-gray-400" />
            <span className="text-2xl font-semibold text-gray-100">{channels.length}</span>
          </div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">已连接</div>
          <div className="text-2xl font-semibold text-success">{connectedCount}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">总消息量</div>
          <div className="text-2xl font-semibold text-gray-100">{channels.reduce((s, c) => s + c.message_count, 0).toLocaleString()}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">异常渠道</div>
          <div className="text-2xl font-semibold" style={{ color: channels.filter(c => c.status === 'error').length > 0 ? '#ef4444' : undefined }}>
            {channels.filter(c => c.status === 'error').length}
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
          data={filteredChannels}
          rowKey="id"
          loading={loading}
          emptyText="暂无渠道数据"
        />
      </motion.div>

      <Modal
        open={deleteModal.open}
        onClose={() => setDeleteModal({ open: false, channel: null })}
        title="确认删除"
        footer={
          <>
            <Button onClick={() => setDeleteModal({ open: false, channel: null })}>
              取消
            </Button>
            <Button variant="danger" onClick={handleDelete}>
              确认删除
            </Button>
          </>
        }
      >
        <p className="text-gray-400">
          确定要删除渠道 "{deleteModal.channel?.name}" 吗？此操作不可撤销。
        </p>
      </Modal>
    </div>
  );
};

export default Channels;
