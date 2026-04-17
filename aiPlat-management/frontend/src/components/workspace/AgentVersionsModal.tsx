import React, { useEffect, useState } from 'react';
import { Modal, Button, Table, Textarea, toast } from '../ui';
import { workspaceAgentApi } from '../../services/coreApi';
import type { Agent } from '../../services';

interface AgentVersionsModalProps {
  open: boolean;
  agent: Agent | null;
  onClose: () => void;
}

const AgentVersionsModal: React.FC<AgentVersionsModalProps> = ({ open, agent, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [versions, setVersions] = useState<Array<{ version: string; status: string; created_at: string; changes: string }>>([]);
  const [changes, setChanges] = useState('');

  const refresh = async () => {
    if (!agent) return;
    setLoading(true);
    try {
      const res = await workspaceAgentApi.getVersions(agent.id);
      setVersions((res as any).versions || []);
    } catch {
      setVersions([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && agent) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, agent?.id]);

  const handleCreate = async () => {
    if (!agent) return;
    try {
      await workspaceAgentApi.createVersion(agent.id, changes || '');
      toast.success('已创建版本');
      setChanges('');
      await refresh();
    } catch {
      toast.error('创建失败');
    }
  };

  const handleRollback = async (version: string) => {
    if (!agent) return;
    try {
      await workspaceAgentApi.rollbackVersion(agent.id, version);
      toast.success('已回滚');
      await refresh();
    } catch {
      toast.error('回滚失败');
    }
  };

  const columns = [
    { title: 'version', dataIndex: 'version', key: 'version', width: 120 },
    { title: 'status', dataIndex: 'status', key: 'status', width: 120, render: (v: string) => <span className="text-gray-400">{v}</span> },
    { title: 'created_at', dataIndex: 'created_at', key: 'created_at', width: 200, render: (v: string) => <span className="text-gray-500">{v}</span> },
    { title: 'changes', dataIndex: 'changes', key: 'changes', render: (v: string) => <span className="text-gray-400">{v || '-'}</span> },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: unknown, r: any) => (
        <Button size="sm" variant="secondary" onClick={() => handleRollback(String(r.version))}>
          回滚
        </Button>
      ),
    },
  ];

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`版本管理：${agent?.name || ''}`}
      width={920}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            关闭
          </Button>
          <Button variant="primary" onClick={refresh} loading={loading}>
            刷新
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <div className="bg-dark-bg border border-dark-border rounded-lg p-3">
          <div className="text-sm text-gray-300 mb-2">创建版本（changes）</div>
          <Textarea rows={3} value={changes} onChange={(e: any) => setChanges(e.target.value)} placeholder="可填写本次变更说明" />
          <div className="flex justify-end mt-2">
            <Button size="sm" onClick={handleCreate} disabled={loading}>
              创建版本
            </Button>
          </div>
        </div>
        <Table columns={columns as any} data={versions} rowKey="version" loading={loading} emptyText="暂无版本记录" />
      </div>
    </Modal>
  );
};

export default AgentVersionsModal;

