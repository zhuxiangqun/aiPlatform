import React from 'react';

import { Button, Input, Modal, Switch, toast } from '../ui';

interface IngressModalProps {
  open: boolean;
  onCancel: () => void;
  onOk: (values: IngressFormValues) => Promise<void>;
  initialValues?: Partial<IngressFormValues>;
  mode: 'create' | 'edit';
}

interface IngressFormValues {
  name: string;
  namespace: string;
  host: string;
  path: string;
  backend: string;
  tls: boolean;
  tlsSecret: string;
}

const IngressModal: React.FC<IngressModalProps> = ({ open, onCancel, onOk, initialValues, mode }) => {
  const [loading, setLoading] = React.useState(false);
  const [name, setName] = React.useState('');
  const [namespace, setNamespace] = React.useState('ai-prod');
  const [host, setHost] = React.useState('');
  const [path, setPath] = React.useState('/');
  const [backend, setBackend] = React.useState('');
  const [tls, setTls] = React.useState(false);
  const [tlsSecret, setTlsSecret] = React.useState('');

  React.useEffect(() => {
    if (!open) return;
    if (initialValues) {
      setName(initialValues.name || '');
      setNamespace(initialValues.namespace || 'ai-prod');
      setHost(initialValues.host || '');
      setPath(initialValues.path || '/');
      setBackend(initialValues.backend || '');
      setTls(Boolean(initialValues.tls));
      setTlsSecret(initialValues.tlsSecret || '');
    } else {
      setName('');
      setNamespace('ai-prod');
      setHost('');
      setPath('/');
      setBackend('');
      setTls(false);
      setTlsSecret('');
    }
  }, [open, initialValues]);

  const submit = async () => {
    if (!name.trim()) return toast.error('请输入 Ingress 名称');
    if (!namespace.trim()) return toast.error('请输入命名空间');
    if (!host.trim()) return toast.error('请输入域名');
    if (!backend.trim()) return toast.error('请输入后端服务');
    if (tls && !tlsSecret.trim()) return toast.error('请输入 TLS Secret');

    setLoading(true);
    try {
      await onOk({
        name: name.trim(),
        namespace: namespace.trim(),
        host: host.trim(),
        path: path.trim() || '/',
        backend: backend.trim(),
        tls,
        tlsSecret: tls ? tlsSecret.trim() : '',
      });
      toast.success(mode === 'create' ? 'Ingress 创建成功' : 'Ingress 更新成功');
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
      title={mode === 'create' ? '创建 Ingress' : '编辑 Ingress'}
      width={640}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={loading}>取消</Button>
          <Button variant="primary" onClick={submit} loading={loading}>保存</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="Ingress 名称" value={name} onChange={(e: any) => setName(e.target.value)} placeholder="例如: api-ing" disabled={mode === 'edit'} />
        <Input label="命名空间" value={namespace} onChange={(e: any) => setNamespace(e.target.value)} placeholder="例如: ai-prod" disabled={mode === 'edit'} />
        <Input label="域名" value={host} onChange={(e: any) => setHost(e.target.value)} placeholder="例如: api.ai.com" />
        <Input label="路径" value={path} onChange={(e: any) => setPath(e.target.value)} placeholder="例如: / 或 /api" />
        <Input label="后端服务" value={backend} onChange={(e: any) => setBackend(e.target.value)} placeholder="例如: gpt4-api:8080" />
        <div className="flex items-center gap-3">
          <div className="text-sm text-gray-300">启用 TLS</div>
          <Switch checked={tls} onChange={setTls} size="sm" />
        </div>
        {tls && <Input label="TLS Secret" value={tlsSecret} onChange={(e: any) => setTlsSecret(e.target.value)} placeholder="例如: api-tls-secret" />}
      </div>
    </Modal>
  );
};

export default IngressModal;

