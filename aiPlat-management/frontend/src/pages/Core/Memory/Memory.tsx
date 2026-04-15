import React, { useState, useEffect } from 'react';
import { Plus, RotateCw, Search } from 'lucide-react';
import { motion } from 'framer-motion';
import { Table, Button, Modal } from '../../../components/ui';
import { CreateSessionModal, SessionDetailModal, SearchMemoryModal } from '../../../components/core';
import { useMemoryStore } from '../../../stores';
import type { MemorySession } from '../../../services';

const Memory: React.FC = () => {
  const { sessions, loading, selectedSession, fetchSessions, getDetail, deleteSession, clearSelectedSession, clearSearchResults } = useMemoryStore();
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [searchModalOpen, setSearchModalOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; sessionId: string | null }>({ open: false, sessionId: null });

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleViewDetail = async (sessionId: string) => {
    try {
      await getDetail(sessionId);
      setDetailModalOpen(true);
    } catch {
      alert('获取详情失败');
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm.sessionId) return;
    try {
      await deleteSession(deleteConfirm.sessionId);
      alert('会话已删除');
      setDeleteConfirm({ open: false, sessionId: null });
    } catch {
      alert('删除失败');
    }
  };

  const columns = [
    {
      title: '会话ID',
      dataIndex: 'session_id',
      key: 'session_id',
      render: (id: string) => (
        <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{id.slice(0, 16)}...</code>
      ),
    },
    {
      title: '消息数',
      dataIndex: 'message_count',
      key: 'message_count',
      width: 120,
      align: 'center' as const,
      render: (count: number) => count ?? '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_: unknown, record: MemorySession) => (
        <div className="flex items-center gap-1">
          <button
            onClick={() => handleViewDetail(record.session_id)}
            className="px-2 py-1 rounded-lg text-sm text-primary hover:bg-primary-light transition-colors"
          >
            详情
          </button>
          <button
            onClick={() => setDeleteConfirm({ open: true, sessionId: record.session_id })}
            className="px-2 py-1 rounded-lg text-sm text-error hover:bg-error-light transition-colors"
          >
            删除
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">Memory管理</h1>
          <p className="text-sm text-gray-500 mt-1">管理AI代理的对话记忆与会话上下文</p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            icon={<Search className="w-4 h-4" />}
            onClick={() => setSearchModalOpen(true)}
          >
            搜索
          </Button>
          <Button
            icon={<RotateCw className="w-4 h-4" />}
            onClick={fetchSessions}
            loading={loading}
          >
            刷新
          </Button>
          <Button
            variant="primary"
            icon={<Plus className="w-4 h-4" />}
            onClick={() => setAddModalOpen(true)}
          >
            创建会话
          </Button>
        </div>
      </div>

      {/* Table Card */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-dark-card rounded-xl border border-dark-border overflow-hidden"
      >
        <Table
          columns={columns}
          data={sessions}
          rowKey="session_id"
          loading={loading}
          emptyText="暂无会话数据"
        />
      </motion.div>

      {/* Delete Confirmation Modal */}
      <Modal
        open={deleteConfirm.open}
        onClose={() => setDeleteConfirm({ open: false, sessionId: null })}
        title="确认删除"
        footer={
          <>
            <Button onClick={() => setDeleteConfirm({ open: false, sessionId: null })}>
              取消
            </Button>
            <Button variant="danger" onClick={handleDelete}>
              确认删除
            </Button>
          </>
        }
      >
        <p className="text-gray-400">
          确定要删除会话 "{deleteConfirm.sessionId?.slice(0, 16)}..." 吗？此操作不可撤销，请谨慎操作。
        </p>
      </Modal>

      <CreateSessionModal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onSuccess={fetchSessions}
      />

      <SessionDetailModal
        open={detailModalOpen}
        session={selectedSession}
        onClose={() => { setDetailModalOpen(false); clearSelectedSession(); }}
      />

      <SearchMemoryModal
        open={searchModalOpen}
        onClose={() => { setSearchModalOpen(false); clearSearchResults(); }}
      />
    </div>
  );
};

export default Memory;
