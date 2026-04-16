import React from 'react';
import { Button, Input, Modal, Select, toast } from '../ui';

interface QuotaModalProps {
  open: boolean;
  onCancel: () => void;
  onOk: (values: QuotaFormValues) => Promise<void>;
  initialValues?: Partial<QuotaFormValues>;
  mode: 'create' | 'edit';
}

interface QuotaFormValues {
  name: string;
  gpuQuota: number;
  team: string;
}

const QuotaModal: React.FC<QuotaModalProps> = ({ open, onCancel, onOk, initialValues, mode }) => {
  const [loading, setLoading] = React.useState(false);
  const [name, setName] = React.useState('');
  const [team, setTeam] = React.useState('');
  const [gpuQuota, setGpuQuota] = React.useState('1');

  React.useEffect(() => {
    if (open && initialValues) {
      setName(initialValues.name || '');
      setTeam(initialValues.team || '');
      setGpuQuota(initialValues.gpuQuota != null ? String(initialValues.gpuQuota) : '1');
    } else if (open) {
      setName('');
      setTeam('');
      setGpuQuota('1');
    }
  }, [open, initialValues]);

  const handleOk = async () => {
    try {
      if (!name.trim()) return toast.error('请输入配额名称');
      if (!team) return toast.error('请选择团队或用户');
      setLoading(true);
      await onOk({ name: name.trim(), team, gpuQuota: Number(gpuQuota || 0) });
      toast.success(mode === 'create' ? '配额创建成功' : '配额更新成功');
    } catch (error) {
      if (error instanceof Error) toast.error(error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    onCancel();
  };

  return (
    <Modal
      open={open}
      onClose={handleCancel}
      title={mode === 'create' ? '创建资源配额' : '编辑资源配额'}
      width={560}
      footer={
        <>
          <Button variant="secondary" onClick={handleCancel} disabled={loading}>取消</Button>
          <Button variant="primary" onClick={handleOk} loading={loading}>保存</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="配额名称" value={name} onChange={(e: any) => setName(e.target.value)} placeholder="例如: prod-team" disabled={mode === 'edit'} />
        <Select
          label="团队/用户"
          value={team}
          onChange={(v) => setTeam(v)}
          placeholder="选择团队或用户"
          options={[
            { value: 'prod-team', label: '生产团队' },
            { value: 'dev-team', label: '开发团队' },
            { value: 'research', label: '研究中心' },
            { value: 'ml-team', label: '算法团队' },
          ]}
        />
        <Input label="GPU 配额（卡）" type="number" min={1} max={64} value={gpuQuota} onChange={(e: any) => setGpuQuota(e.target.value)} />
      </div>
    </Modal>
  );
};

export default QuotaModal;
