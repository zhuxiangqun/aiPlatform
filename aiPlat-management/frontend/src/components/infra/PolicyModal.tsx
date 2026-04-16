import React from 'react';

import { Button, Input, Modal, Select, Switch, toast } from '../ui';

interface PolicyModalProps {
  open: boolean;
  onCancel: () => void;
  onOk: (values: PolicyFormValues) => Promise<void>;
  initialValues?: { name?: string; type?: string; priority?: number; nodeSelector?: Record<string, string>; status?: string; enabled?: boolean };
  mode: 'create' | 'edit';
}

interface PolicyFormValues {
  name: string;
  type: 'default' | 'high-priority' | 'batch';
  priority: number;
  nodeSelector: Record<string, string>;
  enabled: boolean;
}

const PolicyModal: React.FC<PolicyModalProps> = ({ open, onCancel, onOk, initialValues, mode }) => {
  const [loading, setLoading] = React.useState(false);
  const [name, setName] = React.useState('');
  const [type, setType] = React.useState<'default' | 'high-priority' | 'batch'>('default');
  const [priority, setPriority] = React.useState('50');
  const [nodeSelectorStr, setNodeSelectorStr] = React.useState('');
  const [enabled, setEnabled] = React.useState(true);

  React.useEffect(() => {
    if (!open) return;
    if (initialValues) {
      setName(initialValues.name || '');
      setType((initialValues.type as any) || 'default');
      setPriority(initialValues.priority != null ? String(initialValues.priority) : '50');
      setEnabled(initialValues.enabled ?? (initialValues.status === 'enabled'));
      if (initialValues.nodeSelector) {
        setNodeSelectorStr(
          Object.entries(initialValues.nodeSelector)
            .map(([k, v]) => `${k}=${v}`)
            .join(',')
        );
      } else {
        setNodeSelectorStr('');
      }
    } else {
      setName('');
      setType('default');
      setPriority('50');
      setNodeSelectorStr('');
      setEnabled(true);
    }
  }, [open, initialValues]);

  const submit = async () => {
    if (!name.trim()) return toast.error('请输入策略名称');
    const nodeSelector: Record<string, string> = {};
    if (nodeSelectorStr.trim()) {
      nodeSelectorStr.split(',').forEach((pair) => {
        const [k, v] = pair.split('=');
        if (k && v) nodeSelector[k.trim()] = v.trim();
      });
    }
    setLoading(true);
    try {
      await onOk({
        name: name.trim(),
        type,
        priority: Number(priority),
        nodeSelector,
        enabled,
      });
      toast.success(mode === 'create' ? '策略创建成功' : '策略更新成功');
    } catch (e: any) {
      toast.error(e?.message || '操作失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={mode === 'create' ? '创建调度策略' : '编辑调度策略'}
      width={640}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={loading}>取消</Button>
          <Button variant="primary" onClick={submit} loading={loading}>保存</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="策略名称" value={name} onChange={(e: any) => setName(e.target.value)} placeholder="例如: gpu-intensive" disabled={mode === 'edit'} />
        <Select
          label="策略类型"
          value={type}
          onChange={(v) => setType(v as any)}
          options={[
            { value: 'default', label: '默认策略' },
            { value: 'high-priority', label: '高优先级' },
            { value: 'batch', label: '批处理' },
          ]}
        />
        <Input label="优先级（0-100）" type="number" min={0} max={100} value={priority} onChange={(e: any) => setPriority(e.target.value)} />
        <Input label="节点选择器（key=value,key=value）" value={nodeSelectorStr} onChange={(e: any) => setNodeSelectorStr(e.target.value)} placeholder="例如: gpu-type=a100,zone=cn-east" />
        <div className="flex items-center gap-3">
          <div className="text-sm text-gray-300">启用策略</div>
          <Switch checked={enabled} onChange={setEnabled} size="sm" />
        </div>
      </div>
    </Modal>
  );
};

export default PolicyModal;

