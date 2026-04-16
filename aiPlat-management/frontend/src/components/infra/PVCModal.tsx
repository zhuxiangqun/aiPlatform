import React from 'react';
import { Button, Input, Modal, Select, toast } from '../ui';

interface PVCModalProps {
  open: boolean;
  onCancel: () => void;
  onOk: (values: PVCFormValues) => Promise<void>;
  initialValues?: Partial<PVCFormValues>;
  mode: 'create' | 'expand';
}

interface PVCFormValues {
  name: string;
  namespace: string;
  size: number;
  storageClass: string;
  accessMode: 'ReadWriteOnce' | 'ReadWriteMany' | 'ReadOnlyMany';
}

interface PVCFormValues {
  name: string;
  namespace: string;
  size: number;
  storageClass: string;
  accessMode: 'ReadWriteOnce' | 'ReadWriteMany' | 'ReadOnlyMany';
}

const PVCModal: React.FC<PVCModalProps> = ({ open, onCancel, onOk, initialValues, mode }) => {
  const [loading, setLoading] = React.useState(false);
  const [name, setName] = React.useState('');
  const [namespace, setNamespace] = React.useState('ai-prod');
  const [size, setSize] = React.useState('10');
  const [storageClass, setStorageClass] = React.useState('standard');
  const [accessMode, setAccessMode] = React.useState<'ReadWriteOnce' | 'ReadWriteMany' | 'ReadOnlyMany'>('ReadWriteOnce');

  React.useEffect(() => {
    if (open && initialValues) {
      setName(initialValues.name || '');
      setNamespace((initialValues.namespace as any) || 'ai-prod');
      setSize(initialValues.size != null ? String(initialValues.size) : '10');
      setStorageClass((initialValues.storageClass as any) || 'standard');
      setAccessMode((initialValues.accessMode as any) || 'ReadWriteOnce');
    } else if (open) {
      setName('');
      setNamespace('ai-prod');
      setSize('10');
      setStorageClass('standard');
      setAccessMode('ReadWriteOnce');
    }
  }, [open, initialValues]);

  const handleOk = async () => {
    try {
      if (!name.trim()) return toast.error('请输入 PVC 名称');
      if (!namespace) return toast.error('请选择命名空间');
      if (!size) return toast.error('请输入存储大小');
      setLoading(true);
      await onOk({
        name: name.trim(),
        namespace,
        size: Number(size),
        storageClass,
        accessMode,
      });
      toast.success(mode === 'create' ? 'PVC 创建成功' : 'PVC 扩容成功');
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
      title={mode === 'create' ? '创建 PVC' : '扩容 PVC'}
      width={560}
      footer={
        <>
          <Button variant="secondary" onClick={handleCancel} disabled={loading}>取消</Button>
          <Button variant="primary" onClick={handleOk} loading={loading}>保存</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="PVC 名称" value={name} onChange={(e: any) => setName(e.target.value)} placeholder="例如: model-cache" disabled={mode === 'expand'} />
        <Select
          label="命名空间"
          value={namespace}
          onChange={(v) => setNamespace(v)}
          options={[
            { value: 'ai-prod', label: 'ai-prod' },
            { value: 'ai-dev', label: 'ai-dev' },
            { value: 'default', label: 'default' },
          ]}
          disabled={mode === 'expand'}
        />
        <Input label="存储大小（GB）" type="number" min={1} max={10000} value={size} onChange={(e: any) => setSize(e.target.value)} />
        {mode === 'create' && (
          <>
            <Select
              label="存储类"
              value={storageClass}
              onChange={(v) => setStorageClass(v)}
              options={[
                { value: 'standard', label: 'standard' },
                { value: 'fast', label: 'fast (SSD)' },
                { value: 'slow', label: 'slow (HDD)' },
              ]}
            />
            <Select
              label="访问模式"
              value={accessMode}
              onChange={(v) => setAccessMode(v as any)}
              options={[
                { value: 'ReadWriteOnce', label: 'ReadWriteOnce' },
                { value: 'ReadWriteMany', label: 'ReadWriteMany' },
                { value: 'ReadOnlyMany', label: 'ReadOnlyMany' },
              ]}
            />
          </>
        )}
      </div>
    </Modal>
  );
};

export default PVCModal;
