import React from 'react';
import { Modal, Form, Input, Switch, message } from 'antd';

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
  const [form] = Form.useForm();
  const [loading, setLoading] = React.useState(false);
  const [enableTls, setEnableTls] = React.useState(false);

  React.useEffect(() => {
    if (open && initialValues) {
      form.setFieldsValue(initialValues);
      setEnableTls(initialValues.tls || false);
    } else if (open) {
      form.resetFields();
      setEnableTls(false);
    }
  }, [open, initialValues, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      await onOk(values);
      form.resetFields();
      message.success(mode === 'create' ? 'Ingress 创建成功' : 'Ingress 更新成功');
    } catch (error) {
      if (error instanceof Error) {
        message.error(error.message);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    form.resetFields();
    setEnableTls(false);
    onCancel();
  };

  return (
    <Modal
      title={mode === 'create' ? '创建 Ingress' : '编辑 Ingress'}
      open={open}
      onCancel={handleCancel}
      onOk={handleOk}
      confirmLoading={loading}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label="Ingress 名称"
          rules={[{ required: true, message: '请输入 Ingress 名称' }]}
        >
          <Input placeholder="例如: api-ing" disabled={mode === 'edit'} />
        </Form.Item>
        <Form.Item
          name="namespace"
          label="命名空间"
          rules={[{ required: true, message: '请选择命名空间' }]}
          initialValue="ai-prod"
        >
          <Input placeholder="例如: ai-prod" disabled={mode === 'edit'} />
        </Form.Item>
        <Form.Item
          name="host"
          label="域名"
          rules={[{ required: true, message: '请输入域名' }]}
        >
          <Input placeholder="例如: api.ai.com" />
        </Form.Item>
        <Form.Item
          name="path"
          label="路径"
          initialValue="/"
        >
          <Input placeholder="例如: / 或 /api" />
        </Form.Item>
        <Form.Item
          name="backend"
          label="后端服务"
          rules={[{ required: true, message: '请输入后端服务' }]}
        >
          <Input placeholder="例如: gpt4-api:8080" />
        </Form.Item>
        <Form.Item
          name="tls"
          label="启用 TLS"
          valuePropName="checked"
        >
          <Switch onChange={setEnableTls} />
        </Form.Item>
        {enableTls && (
          <Form.Item
            name="tlsSecret"
            label="TLS Secret"
            rules={[{ required: enableTls, message: '请输入 TLS Secret 名称' }]}
          >
            <Input placeholder="例如: api-tls-secret" />
          </Form.Item>
        )}
      </Form>
    </Modal>
  );
};

export default IngressModal;