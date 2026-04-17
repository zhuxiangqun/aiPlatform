import React, { useEffect, useState } from 'react';
import { ExternalLink, RotateCw } from 'lucide-react';
import { Modal, Button, Table } from '../ui';
import { workspaceAgentApi } from '../../services/coreApi';
import type { Agent } from '../../services';

interface AgentHistoryModalProps {
  open: boolean;
  agent: Agent | null;
  onClose: () => void;
}

const AgentHistoryModal: React.FC<AgentHistoryModalProps> = ({ open, agent, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<any[]>([]);

  const refresh = async () => {
    if (!agent) return;
    setLoading(true);
    try {
      const res = await workspaceAgentApi.getHistory(agent.id, { limit: 50, offset: 0 });
      setHistory((res as any).history || []);
    } catch {
      setHistory([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && agent) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, agent?.id]);

  const columns = [
    { title: 'execution_id', dataIndex: 'execution_id', key: 'execution_id', render: (v: any, r: any) => <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{String(v || r.id || '').slice(0, 10)}</code> },
    { title: 'status', dataIndex: 'status', key: 'status', width: 120, render: (v: any) => <span className="text-gray-400">{String(v || '-')}</span> },
    { title: 'start_time', dataIndex: 'start_time', key: 'start_time', width: 200, render: (v: any) => <span className="text-gray-500">{String(v || '-')}</span> },
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
      title={`执行历史：${agent?.name || ''}`}
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
      <Table columns={columns as any} data={history} rowKey={(r: any) => String(r.execution_id || r.id)} loading={loading} emptyText="暂无执行记录" />
    </Modal>
  );
};

export default AgentHistoryModal;

