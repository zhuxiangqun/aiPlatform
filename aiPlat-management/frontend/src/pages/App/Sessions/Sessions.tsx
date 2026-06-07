import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { RotateCw, MessageCircle, Square } from 'lucide-react';
import { Table, Button, Modal, Select, toast } from '../../../components/ui';
import PageHeader from '../../../components/common/PageHeader';
import { appSessionApi } from '../../../services';
import type { AppSession } from '../../../services';

const sessionStatusConfig: Record<string, { bg: string; text: string; label: string }> = {
  active: { bg: 'bg-success-light', text: 'text-green-300', label: '活跃' },
  ended: { bg: 'bg-dark-hover', text: 'text-gray-300', label: '已结束' },
  timeout: { bg: 'bg-warning-light', text: 'text-amber-300', label: '超时' },
};

const channelTypeConfig: Record<string, { bg: string; text: string; label: string }> = {
  telegram: { bg: 'bg-blue-50', text: 'text-blue-300', label: 'Telegram' },
  slack: { bg: 'bg-purple-50', text: 'text-purple-300', label: 'Slack' },
  webchat: { bg: 'bg-green-50', text: 'text-green-300', label: 'WebChat' },
  api: { bg: 'bg-orange-50', text: 'text-orange-300', label: 'API' },
  wechat: { bg: 'bg-cyan-50', text: 'text-cyan-300', label: '微信' },
};

const shortText = (v: any, n: number) => {
  const s = String(v || '');
  return s ? (s.length > n ? `${s.slice(0, n)}...` : s) : '-';
};

const Sessions: React.FC = () => {
  const [sessions, setSessions] = useState<AppSession[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [channelFilter, setChannelFilter] = useState<string | undefined>();
  const [endModal, setEndModal] = useState<{ open: boolean; session: AppSession | null }>({ open: false, session: null });

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    try {
      const res = await appSessionApi.list({ status: statusFilter || undefined, channel: channelFilter || undefined });
      setSessions(res.sessions || []);
    } catch {
      toast.error('获取会话列表失败');
      setSessions([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, channelFilter]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleEnd = async () => {
    if (!endModal.session) return;
    try {
      await appSessionApi.end(endModal.session.id);
      toast.success('会话已结束');
      setEndModal({ open: false, session: null });
      fetchSessions();
    } catch {
      toast.error('结束会话失败');
    }
  };

  const filteredSessions = sessions.filter(s => {
    if (statusFilter && s.status !== statusFilter) return false;
    if (channelFilter && s.channel_type !== channelFilter) return false;
    return true;
  });

  const columns = [
    {
      key: 'id',
      title: '会话ID',
      render: (_: unknown, record: AppSession) => (
        <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded text-gray-300">{shortText(record.id, 12)}</code>
      ),
    },
    {
      key: 'channel_type',
      title: '渠道',
      render: (_: unknown, record: AppSession) => {
        const cfg = channelTypeConfig[record.channel_type] || { bg: 'bg-dark-hover', text: 'text-gray-300', label: record.channel_type };
        return (
          <span className={`inline-flex px-2 py-1 rounded-md text-xs font-medium ${cfg.bg} ${cfg.text}`}>
            {cfg.label}
          </span>
        );
      },
    },
    {
      key: 'user_id',
      title: '用户',
      render: (_: unknown, record: AppSession) => (
        <span className="text-gray-500">{String(record.user_id || '-')}</span>
      ),
    },
    {
      key: 'agent_id',
      title: 'Agent',
      render: (_: unknown, record: AppSession) => (
        <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded text-gray-300">{shortText(record.agent_id, 16)}</code>
      ),
    },
    {
      key: 'message_count',
      title: '消息数',
      render: (_: unknown, record: AppSession) => (
        <div className="flex items-center gap-1">
          <MessageCircle size={14} className="text-gray-400" />
          <span>{record.message_count}</span>
        </div>
      ),
    },
    {
      key: 'status',
      title: '状态',
      render: (_: unknown, record: AppSession) => {
        const cfg = sessionStatusConfig[record.status] || { bg: 'bg-dark-hover', text: 'text-gray-300', label: record.status };
        return (
          <span className={`inline-flex px-2 py-1 rounded-md text-xs font-medium ${cfg.bg} ${cfg.text}`}>
            {cfg.label}
          </span>
        );
      },
    },
    {
      key: 'created_at',
      title: '创建时间',
      render: (_: unknown, record: AppSession) => (record.created_at ? new Date(record.created_at).toLocaleString('zh-CN') : '-'),
    },
    {
      key: 'actions',
      title: '操作',
      align: 'center' as const,
      render: (_: unknown, record: AppSession) => (
        record.status === 'active' ? (
          <Button
            variant="danger"
            size="sm"
            icon={<Square size={14} />}
            onClick={() => setEndModal({ open: true, session: record })}
          >
            结束
          </Button>
        ) : null
      ),
    },
  ];

  const activeCount = sessions.filter(s => s.status === 'active').length;
  const totalMessages = sessions.reduce((s, ses) => s + ses.message_count, 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="会话管理"
        description="管理跨渠道的用户对话会话，查看会话状态与消息统计"
        extra={
          <div className="flex items-center gap-3">
            <Select
              value={channelFilter}
              onChange={(v) => setChannelFilter(v || undefined)}
              options={Object.entries(channelTypeConfig).map(([k, v]) => ({ value: k, label: v.label }))}
              placeholder="渠道筛选"
            />
            <Select
              value={statusFilter}
              onChange={(v) => setStatusFilter(v || undefined)}
              options={Object.entries(sessionStatusConfig).map(([k, v]) => ({ value: k, label: v.label }))}
              placeholder="状态筛选"
            />
            <Button
              icon={<RotateCw className="w-4 h-4" />}
              onClick={fetchSessions}
              loading={loading}
            >
              刷新
            </Button>
          </div>
        }
      />

      <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group mb-3">
        <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
          <div><span className="text-gray-300">会话ID</span><span className="ml-2 text-gray-600">会话唯一标识，截断显示前 12 位</span></div>
          <div><span className="text-gray-300">渠道</span><span className="ml-2 text-gray-600">Telegram / Slack / WebChat / API / 微信</span></div>
          <div><span className="text-gray-300">用户</span><span className="ml-2 text-gray-600">发起会话的用户 ID</span></div>
          <div><span className="text-gray-300">Agent</span><span className="ml-2 text-gray-600">处理该会话的 Agent ID</span></div>
          <div><span className="text-gray-300">消息数</span><span className="ml-2 text-gray-600">该会话的消息总数</span></div>
          <div><span className="text-gray-300">状态</span><span className="ml-2 text-gray-600">活跃 / 已结束 / 超时</span></div>
          <div><span className="text-gray-300">创建时间</span><span className="ml-2 text-gray-600">会话创建的时间</span></div>
          <div><span className="text-gray-300">操作</span><span className="ml-2 text-gray-600">结束活跃会话</span></div>
        </div>
      </details>

      <div className="grid grid-cols-4 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">总会话</div>
          <div className="text-2xl font-semibold text-gray-100">{sessions.length}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">活跃会话</div>
          <div className="text-2xl font-semibold text-success">{activeCount}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">总消息量</div>
          <div className="flex items-center gap-2">
            <MessageCircle size={16} className="text-gray-400" />
            <span className="text-2xl font-semibold text-gray-100">{totalMessages}</span>
          </div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-500 mb-1">超时会话</div>
          <div className="text-2xl font-semibold" style={{ color: sessions.some(s => s.status === 'timeout') ? '#f59e0b' : undefined }}>
            {sessions.filter(s => s.status === 'timeout').length}
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
          data={filteredSessions}
          rowKey="id"
          loading={loading}
          emptyText="暂无会话数据"
        />
      </motion.div>

      <Modal
        open={endModal.open}
        onClose={() => setEndModal({ open: false, session: null })}
        title="结束会话"
        footer={
          <>
            <Button onClick={() => setEndModal({ open: false, session: null })}>
              取消
            </Button>
            <Button variant="danger" onClick={handleEnd}>
              确认结束
            </Button>
          </>
        }
      >
        <p className="text-gray-400">
          确定要结束会话 "{endModal.session?.id}" 吗？
        </p>
      </Modal>
    </div>
  );
};

export default Sessions;
