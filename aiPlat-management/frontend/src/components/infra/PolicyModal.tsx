import React from 'react';
import { Modal, Form, Input, Select, InputNumber, Switch, message } from 'antd';

const { Option } = Select;

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
  const [form] = Form.useForm();
  const [loading, setLoading] = React.useState(false);
  const [nodeSelectorStr, setNodeSelectorStr] = React.useState('');

  React.useEffect(() => {
    if (open && initialValues) {
      form.setFieldsValue({
        name: initialValues.name,
        type: initialValues.type,
        priority: initialValues.priority,
        enabled: initialValues.status === 'enabled',
      });
      if (initialValues.nodeSelector) {
        setNodeSelectorStr(
          Object.entries(initialValues.nodeSelector)
            .map(([k, v]) => `${k}=${v}`)
            .join(',')
        );
      }
    } else if (open) {
      form.resetFields();
      setNodeSelectorStr('');
    }
  }, [open, initialValues, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      const nodeSelector: Record<string, string> = {};
      if (nodeSelectorStr) {
        nodeSelectorStr.split(',').forEach((pair) => {
          const [key, value] = pair.split('=');
          if (key && value) {
            nodeSelector[key.trim()] = value.trim();
          }
        });
      }
      setLoading(true);
      await onOk({
        ...values,
        nodeSelector,
      });
      form.resetFields();
      setNodeSelectorStr('');
      message.success(mode === 'create' ? '策略创建成功' : '策略更新成功');
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
    setNodeSelectorStr('');
    onCancel();
  };

  return (
    <Modal
      title={mode === 'create' ? '创建调度策略' : '编辑调度策略'}
      open={open}
      onCancel={handleCancel}
      onOk={handleOk}
      confirmLoading={loading}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label="策略名称"
          rules={[{ required: true, message: '请输入策略名称' }]}
        >
          <Input placeholder="例如: gpu-intensive" disabled={mode === 'edit'} />
        </Form.Item>
        <Form.Item
          name="type"
          label="策略类型"
          rules={[{ required: true, message: '请选择策略类型' }]}
          initialValue="default"
        >
          <Select placeholder="选择策略类型">
            <Option value="default">默认策略</Option>
            <Option value="high-priority">高优先级</Option>
            <Option value="batch">批处理</Option>
          </Select>
        </Form.Item>
        <Form.Item
          name="priority"
          label="优先级"
          rules={[{ required: true, message: '请输入优先级' }]}
          initialValue={50}
          tooltip="数值越高优先级越高，范围 0-100"
        >
          <InputNumber min={0} max={100} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="节点选择器" tooltip="格式: key1=value1,key2=value2">
          <Input
            placeholder="例如: gpu-type=a100,zone=cn-east"
            value={nodeSelectorStr}
            onChange={(e) => setNodeSelectorStr(e.target.value)}
          />
        </Form.Item>
        <Form.Item
          name="enabled"
          label="启用策略"
          valuePropName="checked"
          initialValue={true}
        >
          <Switch />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default PolicyModal;