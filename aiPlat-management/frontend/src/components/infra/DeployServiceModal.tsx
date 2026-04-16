import React, { useEffect, useState } from 'react';

import { Button, Input, Modal, Select, Switch, toast } from '../ui';

interface DeployServiceModalProps {
  open: boolean;
  onCancel: () => void;
  onOk: (values: ServiceFormValues) => void;
}

interface ServiceFormValues {
  name: string;
  namespace: string;
  type: string;
  image: string;
  imageTag: string;
  replicas: number;
  gpuCount: number;
  gpuType: string;
  model: string;
  maxTokens: number;
  temperature: number;
  enableIngress: boolean;
  ingressHost: string;
}

const DeployServiceModal: React.FC<DeployServiceModalProps> = ({ open, onCancel, onOk }) => {
  const [values, setValues] = useState<ServiceFormValues>({
    name: '',
    namespace: 'ai-prod',
    type: 'LLM',
    image: '',
    imageTag: 'latest',
    replicas: 1,
    gpuCount: 0,
    gpuType: 'A100',
    model: '',
    maxTokens: 2048,
    temperature: 0.7,
    enableIngress: false,
    ingressHost: '',
  });

  useEffect(() => {
    if (!open) return;
    setValues((v) => ({ ...v, name: '', image: '', model: '', ingressHost: '' }));
  }, [open]);

  const submit = () => {
    if (!values.name.trim()) return toast.error('请输入服务名称');
    if (!values.image.trim()) return toast.error('请输入镜像名称');
    if (values.enableIngress && !values.ingressHost.trim()) return toast.error('请输入 Ingress Host');
    onOk({ ...values, name: values.name.trim(), image: values.image.trim(), model: values.model.trim(), ingressHost: values.ingressHost.trim() });
  };

  return (
    <Modal
      open={open}
      onClose={onCancel}
      title="部署服务"
      width={760}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>取消</Button>
          <Button variant="primary" onClick={submit}>部署</Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input label="服务名称" value={values.name} onChange={(e: any) => setValues((v) => ({ ...v, name: e.target.value }))} placeholder="例如: gpt4-api" />
          <Select
            label="命名空间"
            value={values.namespace}
            onChange={(v) => setValues((x) => ({ ...x, namespace: v }))}
            options={[
              { value: 'ai-prod', label: 'ai-prod' },
              { value: 'ai-dev', label: 'ai-dev' },
              { value: 'default', label: 'default' },
            ]}
          />
        </div>

        <Select
          label="服务类型"
          value={values.type}
          onChange={(v) => setValues((x) => ({ ...x, type: v }))}
          options={[
            { value: 'LLM', label: 'LLM 推理服务' },
            { value: 'Embed', label: 'Embedding 服务' },
            { value: 'Vector', label: '向量数据库' },
            { value: 'Cache', label: '缓存服务' },
            { value: 'DB', label: '数据库' },
          ]}
        />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input label="镜像名称" value={values.image} onChange={(e: any) => setValues((v) => ({ ...v, image: e.target.value }))} placeholder="例如: vllm/vllm-openai" />
          <Input label="镜像标签" value={values.imageTag} onChange={(e: any) => setValues((v) => ({ ...v, imageTag: e.target.value }))} placeholder="例如: latest" />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Input label="replicas" type="number" min={1} max={100} value={String(values.replicas)} onChange={(e: any) => setValues((v) => ({ ...v, replicas: Number(e.target.value || 1) }))} />
          <Input label="gpuCount" type="number" min={0} max={16} value={String(values.gpuCount)} onChange={(e: any) => setValues((v) => ({ ...v, gpuCount: Number(e.target.value || 0) }))} />
          <Select
            label="gpuType"
            value={values.gpuType}
            onChange={(v) => setValues((x) => ({ ...x, gpuType: v }))}
            options={[
              { value: 'A100', label: 'A100' },
              { value: 'H100', label: 'H100' },
              { value: 'V100', label: 'V100' },
              { value: 'A10', label: 'A10' },
              { value: 'T4', label: 'T4' },
            ]}
          />
        </div>

        <div className="border-t border-dark-border pt-4">
          <div className="text-sm font-semibold text-gray-200 mb-3">模型参数（可选）</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Input label="model" value={values.model} onChange={(e: any) => setValues((v) => ({ ...v, model: e.target.value }))} />
            <Input label="maxTokens" type="number" min={1} max={32768} value={String(values.maxTokens)} onChange={(e: any) => setValues((v) => ({ ...v, maxTokens: Number(e.target.value || 2048) }))} />
            <Input label="temperature" type="number" min={0} max={2} value={String(values.temperature)} onChange={(e: any) => setValues((v) => ({ ...v, temperature: Number(e.target.value || 0.7) }))} />
          </div>
        </div>

        <div className="border-t border-dark-border pt-4">
          <div className="flex items-center gap-3">
            <div className="text-sm text-gray-300">启用 Ingress</div>
            <Switch checked={values.enableIngress} onChange={(v) => setValues((x) => ({ ...x, enableIngress: v }))} size="sm" />
          </div>
          {values.enableIngress && (
            <div className="mt-3">
              <Input label="Ingress Host" value={values.ingressHost} onChange={(e: any) => setValues((v) => ({ ...v, ingressHost: e.target.value }))} placeholder="例如: api.ai.com" />
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
};

export default DeployServiceModal;

