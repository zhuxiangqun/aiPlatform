import React, { useEffect, useState } from 'react';
import { Alert, Button, Input, Modal, Select, toast } from '../ui';

interface AddNodeModalProps {
  open: boolean;
  onCancel: () => void;
  onOk: (values: NodeFormValues) => void;
}

interface NodeFormValues {
  name: string;
  ip: string;
  provider: string;
  instanceType: string;
  gpuModel: string;
  gpuCount: number;
  driverVersion: string;
  labels: Record<string, string>;
}

const AddNodeModal: React.FC<AddNodeModalProps> = ({ open, onCancel, onOk }) => {
  const [values, setValues] = useState<NodeFormValues>({
    name: '',
    ip: '',
    provider: '',
    instanceType: '',
    gpuModel: 'A100',
    gpuCount: 4,
    driverVersion: '535.54.03',
    labels: {},
  });

  useEffect(() => {
    if (open) {
      setValues({
        name: '',
        ip: '',
        provider: '',
        instanceType: '',
        gpuModel: 'A100',
        gpuCount: 4,
        driverVersion: '535.54.03',
        labels: {},
      });
    }
  }, [open]);

  const submit = () => {
    if (!values.name.trim()) return toast.error('请输入节点名称');
    if (!/^(\d{1,3}\.){3}\d{1,3}$/.test(values.ip.trim())) return toast.error('请输入有效的 IP 地址');
    if (!values.gpuModel) return toast.error('请选择 GPU 型号');
    if (!values.driverVersion) return toast.error('请选择驱动版本');
    onOk({ ...values, name: values.name.trim(), ip: values.ip.trim() });
  };

  return (
    <Modal
      open={open}
      onClose={onCancel}
      title="添加节点"
      width={680}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>取消</Button>
          <Button variant="primary" onClick={submit}>确定</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="节点名称" value={values.name} onChange={(e: any) => setValues((v) => ({ ...v, name: e.target.value }))} placeholder="例如: node-01" />
        <Input label="IP 地址" value={values.ip} onChange={(e: any) => setValues((v) => ({ ...v, ip: e.target.value }))} placeholder="例如: 10.0.0.101" />

        <Select
          label="云厂商（可选）"
          value={values.provider}
          onChange={(v) => setValues((x) => ({ ...x, provider: v }))}
          options={[
            { value: '', label: '未选择' },
            { value: 'aws', label: 'AWS' },
            { value: 'azure', label: 'Azure' },
            { value: 'gcp', label: 'Google Cloud' },
            { value: 'aliyun', label: '阿里云' },
            { value: 'huawei', label: '华为云' },
            { value: 'self-hosted', label: '自建机房' },
          ]}
        />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Select
            label="GPU 型号"
            value={values.gpuModel}
            onChange={(v) => setValues((x) => ({ ...x, gpuModel: v }))}
            options={[
              { value: 'A100', label: 'NVIDIA A100' },
              { value: 'H100', label: 'NVIDIA H100' },
              { value: 'V100', label: 'NVIDIA V100' },
              { value: 'A10', label: 'NVIDIA A10' },
              { value: 'T4', label: 'NVIDIA T4' },
            ]}
          />
          <Input
            label="GPU 数量"
            type="number"
            min={1}
            max={8}
            value={String(values.gpuCount)}
            onChange={(e: any) => setValues((x) => ({ ...x, gpuCount: Number(e.target.value || 0) }))}
          />
        </div>

        <Select
          label="NVIDIA 驱动版本"
          value={values.driverVersion}
          onChange={(v) => setValues((x) => ({ ...x, driverVersion: v }))}
          options={[
            { value: '535.54.03', label: '535.54.03 (CUDA 12.2)' },
            { value: '535.104.05', label: '535.104.05 (CUDA 12.2)' },
            { value: '545.23.06', label: '545.23.06 (CUDA 12.3)' },
            { value: '550.40.07', label: '550.40.07 (CUDA 12.4)' },
          ]}
        />

        <Alert type="warning" title="注意">
          安装/升级 NVIDIA 驱动需要重启节点，请确保节点上的服务已安全迁移。
        </Alert>
      </div>
    </Modal>
  );
};

export default AddNodeModal;
