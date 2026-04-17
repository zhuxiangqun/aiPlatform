import React, { useEffect, useState } from 'react';
import { Modal, Button, Table, toast } from '../ui';
import { workspaceSkillApi } from '../../services/coreApi';

interface SkillVersionsModalProps {
  open: boolean;
  skill: { id: string; name: string } | null;
  onClose: () => void;
}

const SkillVersionsModal: React.FC<SkillVersionsModalProps> = ({ open, skill, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [versions, setVersions] = useState<Array<{ version: string; is_active: boolean }>>([]);
  const [activeVersion, setActiveVersion] = useState<string | null>(null);

  const refresh = async () => {
    if (!skill) return;
    setLoading(true);
    try {
      const [v, a] = await Promise.all([workspaceSkillApi.getVersions(skill.id), workspaceSkillApi.getActiveVersion(skill.id)]);
      setVersions((v as any).versions || []);
      setActiveVersion((a as any).active_version ?? null);
    } catch {
      setVersions([]);
      setActiveVersion(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && skill) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, skill?.id]);

  const handleRollback = async (version: string) => {
    if (!skill) return;
    try {
      await workspaceSkillApi.rollbackVersion(skill.id, version);
      toast.success('已回滚');
      await refresh();
    } catch {
      toast.error('回滚失败');
    }
  };

  const columns = [
    { title: 'version', dataIndex: 'version', key: 'version' },
    { title: 'active', dataIndex: 'is_active', key: 'is_active', width: 90, render: (v: boolean) => (v ? 'YES' : '') },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: unknown, r: any) => (
        <Button size="sm" variant="secondary" onClick={() => handleRollback(String(r.version))} disabled={Boolean(r.is_active)}>
          回滚
        </Button>
      ),
    },
  ];

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`版本管理：${skill?.name || ''}`}
      width={720}
      footer={
        <>
          <div className="text-xs text-gray-500 mr-auto">当前 active_version: {activeVersion || '-'}</div>
          <Button variant="secondary" onClick={onClose}>
            关闭
          </Button>
          <Button variant="primary" onClick={refresh} loading={loading}>
            刷新
          </Button>
        </>
      }
    >
      <Table columns={columns as any} data={versions} rowKey="version" loading={loading} emptyText="暂无版本记录" />
    </Modal>
  );
};

export default SkillVersionsModal;

