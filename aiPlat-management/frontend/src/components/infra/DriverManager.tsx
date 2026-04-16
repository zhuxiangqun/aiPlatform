import React, { useEffect, useMemo, useState } from 'react';
import { RotateCw, Upload, Undo2 } from 'lucide-react';

import { Alert, Button, Card, Input, Modal, Select, Table, toast } from '../ui';

interface Driver {
  version: string;
  node_count: number;
  nodes: string[];
  gpu_models: string[];
}

interface DriverManagerProps {
  visible?: boolean;
  onCancel?: () => void;
  embedded?: boolean;
}

const DriverManager: React.FC<DriverManagerProps> = ({ visible, onCancel, embedded = false }) => {
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [loading, setLoading] = useState(false);
  const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
  const [rollbackModalOpen, setRollbackModalOpen] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState<string>('');
  const [selectedNodes, setSelectedNodes] = useState<string[]>([]);
  const [operating, setOperating] = useState(false);

  const fetchDrivers = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/infra/drivers');
      const data = await response.json();
      setDrivers(data.drivers || []);
    } catch (error) {
      toast.error('获取驱动列表失败');
      console.error('Failed to fetch drivers:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (visible || embedded) fetchDrivers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, embedded]);

  const allNodes = useMemo(() => [...new Set(drivers.flatMap((d) => d.nodes))], [drivers]);

  const submitUpgrade = async () => {
    if (!selectedVersion.trim()) return toast.warning('请输入新版本号');
    setOperating(true);
    try {
      const response = await fetch('/api/infra/drivers/upgrade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          version: selectedVersion.trim(),
          nodes: selectedNodes.length > 0 ? selectedNodes : undefined,
        }),
      });
      if (response.ok) {
        toast.success('驱动升级任务已启动');
        setUpgradeModalOpen(false);
        setSelectedVersion('');
        setSelectedNodes([]);
        fetchDrivers();
      } else {
        toast.error('驱动升级失败');
      }
    } finally {
      setOperating(false);
    }
  };

  const submitRollback = async () => {
    if (!selectedVersion.trim()) return toast.warning('请选择回滚版本');
    setOperating(true);
    try {
      const response = await fetch('/api/infra/drivers/rollback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          version: selectedVersion.trim(),
          nodes: selectedNodes.length > 0 ? selectedNodes : undefined,
        }),
      });
      if (response.ok) {
        toast.success('驱动回滚任务已启动');
        setRollbackModalOpen(false);
        setSelectedVersion('');
        setSelectedNodes([]);
        fetchDrivers();
      } else {
        toast.error('驱动回滚失败');
      }
    } finally {
      setOperating(false);
    }
  };

  const columns = useMemo(
    () => [
      { key: 'version', title: '驱动版本', dataIndex: 'version' },
      { key: 'node_count', title: '节点数量', dataIndex: 'node_count', align: 'right' as const },
      {
        key: 'gpu_models',
        title: 'GPU 型号',
        dataIndex: 'gpu_models',
        render: (models: string[]) => (models || []).join(', ') || '-',
      },
      {
        key: 'nodes',
        title: '节点列表',
        dataIndex: 'nodes',
        render: (nodes: string[]) => (nodes || []).slice(0, 6).join(', ') + ((nodes || []).length > 6 ? ` …(+${nodes.length - 6})` : ''),
      },
    ],
    []
  );

  const content = (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button variant="secondary" icon={<RotateCw size={16} />} onClick={fetchDrivers} loading={loading}>
          刷新
        </Button>
        <Button variant="primary" icon={<Upload size={16} />} onClick={() => setUpgradeModalOpen(true)}>
          升级驱动
        </Button>
        <Button variant="secondary" icon={<Undo2 size={16} />} onClick={() => setRollbackModalOpen(true)}>
          回滚驱动
        </Button>
      </div>

      <Alert type="info" title="驱动管理说明">
        升级/回滚会在后台异步执行，并可能导致节点重启。建议在维护窗口操作。
      </Alert>

      <Table columns={columns as any} data={drivers} rowKey="version" loading={loading} />

      <Modal
        open={upgradeModalOpen}
        onClose={() => { setUpgradeModalOpen(false); setSelectedVersion(''); setSelectedNodes([]); }}
        title="升级驱动"
        width={560}
        footer={
          <>
            <Button variant="secondary" onClick={() => { setUpgradeModalOpen(false); setSelectedVersion(''); setSelectedNodes([]); }}>
              取消
            </Button>
            <Button variant="primary" onClick={submitUpgrade} loading={operating}>
              确认
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input label="新版本号" value={selectedVersion} onChange={(e: any) => setSelectedVersion(e.target.value)} placeholder="例如: 550.40.07" />
          <div>
            <div className="text-sm font-medium text-gray-300 mb-2">指定节点（可选，多选）</div>
            <select
              multiple
              value={selectedNodes}
              onChange={(e) => setSelectedNodes(Array.from(e.target.selectedOptions).map((o) => o.value))}
              className="w-full h-28 px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
            >
              {allNodes.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            <div className="text-xs text-gray-500 mt-1">不选择则对所有节点生效</div>
          </div>
        </div>
      </Modal>

      <Modal
        open={rollbackModalOpen}
        onClose={() => { setRollbackModalOpen(false); setSelectedVersion(''); setSelectedNodes([]); }}
        title="回滚驱动"
        width={560}
        footer={
          <>
            <Button variant="secondary" onClick={() => { setRollbackModalOpen(false); setSelectedVersion(''); setSelectedNodes([]); }}>
              取消
            </Button>
            <Button variant="danger" onClick={submitRollback} loading={operating}>
              确认回滚
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Select
            label="回滚版本"
            value={selectedVersion}
            onChange={(v) => setSelectedVersion(v)}
            options={drivers.map((d) => ({ value: d.version, label: d.version }))}
            placeholder="选择驱动版本"
          />
          <div>
            <div className="text-sm font-medium text-gray-300 mb-2">指定节点（可选，多选）</div>
            <select
              multiple
              value={selectedNodes}
              onChange={(e) => setSelectedNodes(Array.from(e.target.selectedOptions).map((o) => o.value))}
              className="w-full h-28 px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
            >
              {allNodes.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Modal>
    </div>
  );

  if (embedded) {
    return (
      <Card>
        <div className="p-2">
          <div className="text-sm font-semibold text-gray-200 mb-3">驱动管理</div>
          {content}
        </div>
      </Card>
    );
  }

  return (
    <Modal open={!!visible} onClose={onCancel || (() => {})} title="驱动管理" width={980} footer={null}>
      {content}
    </Modal>
  );
};

export default DriverManager;

