import React from 'react';
import { Modal, Form, Input, Select, InputNumber, message } from 'antd';

const { Option } = Select;

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
  const [form] = Form.useForm();
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (open && initialValues) {
      form.setFieldsValue({
        name: initialValues.name,
        namespace: initialValues.namespace,
        size: initialValues.size,
        storageClass: initialValues.storageClass,
        accessMode: initialValues.accessMode,
      });
    } else if (open) {
      form.resetFields();
    }
  }, [open, initialValues, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      await onOk({
        ...values,
        size: values.size,
      });
      form.resetFields();
      message.success(mode === 'create' ? 'PVC 创建成功' : 'PVC 扩容成功');
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
      title={mode === 'create' ? '创建 PVC' : '扩容 PVC'}
      open={open}
      onCancel={handleCancel}
      onOk={handleOk}
      confirmLoading={loading}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label="PVC 名称"
          rules={[{ required: true, message: '请输入 PVC 名称' }]}
        >
          <Input placeholder="例如: model-cache" disabled={mode === 'expand'} />
        </Form.Item>
        <Form.Item
          name="namespace"
          label="命名空间"
          rules={[{ required: true, message: '请选择命名空间' }]}
          initialValue="ai-prod"
        >
          <Select placeholder="选择命名空间" disabled={mode === 'expand'}>
            <Option value="ai-prod">ai-prod</Option>
            <Option value="ai-dev">ai-dev</Option>
            <Option value="default">default</Option>
          </Select>
        </Form.Item>
        <Form.Item
          name="size"
          label="存储大小"
          rules={[{ required: true, message: '请输入存储大小' }]}
          initialValue={10}
        >
          <InputNumber min={1} max={10000} style={{ width: '100%' }} suffix="GB" />
        </Form.Item>
        {mode === 'create' && (
          <>
            <Form.Item
              name="storageClass"
              label="存储类"
              rules={[{ required: true, message: '请选择存储类' }]}
              initialValue="standard"
            >
              <Select placeholder="选择存储类">
                <Option value="standard">standard</Option>
                <Option value="fast">fast (SSD)</Option>
                <Option value="slow">slow (HDD)</Option>
              </Select>
            </Form.Item>
            <Form.Item
              name="accessMode"
              label="访问模式"
              rules={[{ required: true, message: '请选择访问模式' }]}
              initialValue="ReadWriteOnce"
            >
              <Select placeholder="选择访问模式">
                <Option value="ReadWriteOnce">ReadWriteOnce (单节点读写)</Option>
                <Option value="ReadWriteMany">ReadWriteMany (多节点读写)</Option>
                <Option value="ReadOnlyMany">ReadOnlyMany (多节点只读)</Option>
              </Select>
            </Form.Item>
          </>
        )}
      </Form>
    </Modal>
  );
};

export default PVCModal;