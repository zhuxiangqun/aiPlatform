import React, { useEffect, useState } from 'react';
import { ExternalLink, RotateCw } from 'lucide-react';
import { Modal, Button, Table } from '../ui';
import { workspaceSkillApi } from '../../services/coreApi';

interface SkillExecutionsModalProps {
  open: boolean;
  skill: { id: string; name: string } | null;
  onClose: () => void;
}

const SkillExecutionsModal: React.FC<SkillExecutionsModalProps> = ({ open, skill, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [executions, setExecutions] = useState<any[]>([]);

  const refresh = async () => {
    if (!skill) return;
    setLoading(true);
    try {
      const res = await workspaceSkillApi.listExecutions(skill.id, { limit: 50, offset: 0 });
      setExecutions((res as any).executions || []);
    } catch {
      setExecutions([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && skill) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, skill?.id]);

  const columns = [
    { title: 'execution_id', dataIndex: 'execution_id', key: 'execution_id', render: (v: string) => <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{String(v || '').slice(0, 10)}</code> },
    { title: 'status', dataIndex: 'status', key: 'status', width: 120, render: (v: string) => <span className="text-gray-400">{v || '-'}</span> },
    { title: 'duration_ms', dataIndex: 'duration_ms', key: 'duration_ms', width: 120, render: (v: any) => <span className="text-gray-400">{v ?? '-'}</span> },
    { title: 'start_time', dataIndex: 'start_time', key: 'start_time', width: 200, render: (v: any) => <span className="text-gray-500">{v || '-'}</span> },
    {
      title: '链接',
      key: 'links',
      width: 90,
      render: (_: unknown, r: any) => (
        <a className="inline-flex items-center gap-1 text-primary hover:underline" href={`/diagnostics/links?execution_id=${encodeURIComponent(String(r.execution_id || r.id || ''))}`}>
          <ExternalLink className="w-4 h-4" />
        </a>
      ),
    },
  ];

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`执行历史：${skill?.name || ''}`}
      width={860}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            关闭
          </Button>
          <Button icon={<RotateCw className="w-4 h-4" />} onClick={refresh} loading={loading}>
            刷新
          </Button>
        </>
      }
    >
      <Table columns={columns as any} data={executions} rowKey={(r: any) => String(r.execution_id || r.id)} loading={loading} emptyText="暂无执行记录" />
    </Modal>
  );
};

export default SkillExecutionsModal;

