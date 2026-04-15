import React from 'react';
import { Modal, Form, InputNumber, Input, Select, message } from 'antd';

const { Option } = Select;

interface QuotaModalProps {
  open: boolean;
  onCancel: () => void;
  onOk: (values: QuotaFormValues) => Promise<void>;
  initialValues?: Partial<QuotaFormValues>;
  mode: 'create' | 'edit';
}

interface QuotaFormValues {
  name: string;
  gpuQuota: number;
  team: string;
}

const QuotaModal: React.FC<QuotaModalProps> = ({ open, onCancel, onOk, initialValues, mode }) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (open && initialValues) {
      form.setFieldsValue(initialValues);
    } else if (open) {
      form.resetFields();
    }
  }, [open, initialValues, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      await onOk(values);
      form.resetFields();
      message.success(mode === 'create' ? '配额创建成功' : '配额更新成功');
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

  return (
    <Modal
      title={mode === 'create' ? '创建资源配额' : '编辑资源配额'}
      open={open}
      onCancel={handleCancel}
      onOk={handleOk}
      confirmLoading={loading}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label="配额名称"
          rules={[{ required: true, message: '请输入配额名称' }]}
        >
          <Input placeholder="例如: prod-team" disabled={mode === 'edit'} />
        </Form.Item>
        <Form.Item
          name="team"
          label="团队/用户"
          rules={[{ required: true, message: '请选择团队或用户' }]}
        >
          <Select placeholder="选择团队或用户">
            <Option value="prod-team">生产团队</Option>
            <Option value="dev-team">开发团队</Option>
            <Option value="research">研究中心</Option>
            <Option value="ml-team">算法团队</Option>
          </Select>
        </Form.Item>
        <Form.Item
          name="gpuQuota"
          label="GPU 配额"
          rules={[{ required: true, message: '请输入 GPU 配额' }]}
          initialValue={1}
        >
          <InputNumber min={1} max={64} style={{ width: '100%' }} suffix="卡" />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default QuotaModal;