import React from 'react';

import { Button, Input, Modal, Select, Switch, toast } from '../ui';

interface AlertRuleModalProps {
  open: boolean;
  onCancel: () => void;
  onOk: (values: AlertRuleFormValues) => Promise<void>;
  initialValues?: { name?: string; type?: string; condition?: string; threshold?: number; duration?: number; severity?: string; status?: string; enabled?: boolean };
  mode: 'create' | 'edit';
}

interface AlertRuleFormValues {
  name: string;
  type: 'system' | 'gpu' | 'service' | 'network';
  condition: string;
  threshold: number;
  duration: number;
  severity: 'info' | 'warning' | 'critical';
  enabled: boolean;
}

const conditionOptions: Record<string, string[]> = {
  system: ['CPU > 80%', 'Memory > 90%', 'Disk > 85%'],
  gpu: ['GPU > 95%', 'Temperature > 85', 'Memory > 90%', 'Power > 350W'],
  service: ['Response Time > 1s', 'Error Rate > 5%', 'QPS < 100'],
  network: ['Latency > 100ms', 'Packet Loss > 1%', 'Bandwidth > 90%'],
};

const AlertRuleModal: React.FC<AlertRuleModalProps> = ({ open, onCancel, onOk, initialValues, mode }) => {
  const [loading, setLoading] = React.useState(false);
  const [type, setType] = React.useState<'system' | 'gpu' | 'service' | 'network'>('system');
  const [name, setName] = React.useState('');
  const [condition, setCondition] = React.useState('');
  const [threshold, setThreshold] = React.useState('80');
  const [duration, setDuration] = React.useState('60');
  const [severity, setSeverity] = React.useState<'info' | 'warning' | 'critical'>('warning');
  const [enabled, setEnabled] = React.useState(true);

  React.useEffect(() => {
    if (!open) return;
    if (initialValues) {
      setName(initialValues.name || '');
      setType((initialValues.type as any) || 'system');
      setCondition(initialValues.condition || '');
      setThreshold(initialValues.threshold != null ? String(initialValues.threshold) : '80');
      setDuration(initialValues.duration != null ? String(initialValues.duration) : '60');
      setSeverity((initialValues.severity as any) || 'warning');
      setEnabled(initialValues.enabled ?? (initialValues.status === 'enabled'));
    } else {
      setName('');
      setType('system');
      setCondition('');
      setThreshold('80');
      setDuration('60');
      setSeverity('warning');
      setEnabled(true);
    }
  }, [open, initialValues]);

  const submit = async () => {
    if (!name.trim()) return toast.error('请输入规则名称');
    if (!condition) return toast.error('请选择条件');
    setLoading(true);
    try {
      await onOk({
        name: name.trim(),
        type,
        condition,
        threshold: Number(threshold),
        duration: Number(duration),
        severity,
        enabled,
      });
      toast.success(mode === 'create' ? '告警规则创建成功' : '告警规则更新成功');
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
      title={mode === 'create' ? '创建告警规则' : '编辑告警规则'}
      width={640}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={loading}>取消</Button>
          <Button variant="primary" onClick={submit} loading={loading}>保存</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="规则名称" value={name} onChange={(e: any) => setName(e.target.value)} placeholder="例如: cpu-high" disabled={mode === 'edit'} />
        <Select
          label="告警类型"
          value={type}
          onChange={(v) => { setType(v as any); setCondition(''); }}
          options={[
            { value: 'system', label: '系统告警' },
            { value: 'gpu', label: 'GPU 告警' },
            { value: 'service', label: '服务告警' },
            { value: 'network', label: '网络告警' },
          ]}
        />
        <Select
          label="条件"
          value={condition}
          onChange={(v) => setCondition(v)}
          options={(conditionOptions[type] || []).map((x) => ({ value: x, label: x }))}
        />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input label="阈值" type="number" value={threshold} onChange={(e: any) => setThreshold(e.target.value)} />
          <Input label="持续时间（秒）" type="number" value={duration} onChange={(e: any) => setDuration(e.target.value)} />
        </div>
        <Select
          label="严重程度"
          value={severity}
          onChange={(v) => setSeverity(v as any)}
          options={[
            { value: 'info', label: 'info' },
            { value: 'warning', label: 'warning' },
            { value: 'critical', label: 'critical' },
          ]}
        />
        <div className="flex items-center gap-3">
          <div className="text-sm text-gray-300">启用状态</div>
          <Switch checked={enabled} onChange={setEnabled} size="sm" />
        </div>
      </div>
    </Modal>
  );
};

export default AlertRuleModal;

