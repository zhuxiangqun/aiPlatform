import React from 'react';
import { Modal, Form, Input, Select, InputNumber, Switch, message } from 'antd';

const { Option } = Select;

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
  const [form] = Form.useForm();
  const [loading, setLoading] = React.useState(false);
  const [alertType, setAlertType] = React.useState<string>('system');

  React.useEffect(() => {
    if (open && initialValues) {
      form.setFieldsValue({
        name: initialValues.name,
        type: initialValues.type,
        condition: initialValues.condition,
        threshold: initialValues.threshold,
        duration: initialValues.duration,
        severity: initialValues.severity,
        enabled: initialValues.status === 'enabled',
      });
      setAlertType(initialValues.type || 'system');
    } else if (open) {
      form.resetFields();
      setAlertType('system');
    }
  }, [open, initialValues, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      await onOk(values);
      form.resetFields();
      message.success(mode === 'create' ? '告警规则创建成功' : '告警规则更新成功');
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
    onCancel();
  };

  const handleTypeChange = (type: string) => {
    setAlertType(type);
    form.setFieldsValue({ condition: undefined });
  };

  return (
    <Modal
      title={mode === 'create' ? '创建告警规则' : '编辑告警规则'}
      open={open}
      onCancel={handleCancel}
      onOk={handleOk}
      confirmLoading={loading}
      destroyOnHidden
      width={600}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label="规则名称"
          rules={[{ required: true, message: '请输入规则名称' }]}
        >
          <Input placeholder="例如: cpu-high" disabled={mode === 'edit'} />
        </Form.Item>
        <Form.Item
          name="type"
          label="告警类型"
          rules={[{ required: true, message: '请选择告警类型' }]}
          initialValue="system"
        >
          <Select placeholder="选择告警类型" onChange={handleTypeChange}>
            <Option value="system">系统告警</Option>
            <Option value="gpu">GPU 告警</Option>
            <Option value="service">服务告警</Option>
            <Option value="network">网络告警</Option>
          </Select>
        </Form.Item>
        <Form.Item
          name="condition"
          label="条件"
          rules={[{ required: true, message: '请选择或输入条件' }]}
        >
          <Select placeholder="选择条件">
            {(conditionOptions[alertType] || []).map((opt) => (
              <Option key={opt} value={opt}>
                {opt}
              </Option>
            ))}
          </Select>
        </Form.Item>
        <Form.Item
          name="threshold"
          label="阈值"
          rules={[{ required: true, message: '请输入阈值' }]}
          initialValue={80}
          tooltip="触发告警的阈值，根据条件类型可能是百分比或具体数值"
        >
          <InputNumber min={0} max={100} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item
          name="duration"
          label="持续时间"
          rules={[{ required: true, message: '请输入持续时间' }]}
          initialValue={300}
          tooltip="条件持续多久后触发告警，单位：秒"
        >
          <InputNumber min={10} max={3600} style={{ width: '100%' }} suffix="秒" />
        </Form.Item>
        <Form.Item
          name="severity"
          label="严重性"
          rules={[{ required: true, message: '请选择严重性' }]}
          initialValue="warning"
        >
          <Select placeholder="选择严重性">
            <Option value="info">信息</Option>
            <Option value="warning">警告</Option>
            <Option value="critical">严重</Option>
          </Select>
        </Form.Item>
        <Form.Item
          name="enabled"
          label="启用规则"
          valuePropName="checked"
          initialValue={true}
        >
          <Switch />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default AlertRuleModal;