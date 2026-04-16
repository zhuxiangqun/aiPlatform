import React from 'react';

import { Button, Input, Modal, Select, toast } from '../ui';

interface CollectionModalProps {
  open: boolean;
  onCancel: () => void;
  onOk: (values: CollectionFormValues) => Promise<void>;
}

interface CollectionFormValues {
  name: string;
  dimension: number;
  metricType: 'Cosine' | 'Euclidean' | 'InnerProduct';
}

const CollectionModal: React.FC<CollectionModalProps> = ({ open, onCancel, onOk }) => {
  const [loading, setLoading] = React.useState(false);
  const [name, setName] = React.useState('');
  const [dimension, setDimension] = React.useState('768');
  const [metricType, setMetricType] = React.useState<'Cosine' | 'Euclidean' | 'InnerProduct'>('Cosine');

  React.useEffect(() => {
    if (!open) return;
    setName('');
    setDimension('768');
    setMetricType('Cosine');
  }, [open]);

  const submit = async () => {
    if (!name.trim()) return toast.error('请输入 Collection 名称');
    setLoading(true);
    try {
      await onOk({ name: name.trim(), dimension: Number(dimension), metricType });
      toast.success('Collection 创建成功');
    } catch (e: any) {
      toast.error(e?.message || '创建失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onCancel}
      title="创建向量 Collection"
      width={560}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={loading}>取消</Button>
          <Button variant="primary" onClick={submit} loading={loading}>创建</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="Collection 名称" value={name} onChange={(e: any) => setName(e.target.value)} placeholder="例如: docs-emb" />
        <Input label="向量维度" type="number" min={1} max={65536} value={dimension} onChange={(e: any) => setDimension(e.target.value)} />
        <Select
          label="度量类型"
          value={metricType}
          onChange={(v) => setMetricType(v as any)}
          options={[
            { value: 'Cosine', label: 'Cosine (余弦相似度)' },
            { value: 'Euclidean', label: 'Euclidean (欧氏距离)' },
            { value: 'InnerProduct', label: 'InnerProduct (内积)' },
          ]}
        />
      </div>
    </Modal>
  );
};

export default CollectionModal;

