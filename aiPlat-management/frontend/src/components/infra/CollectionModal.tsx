import React from 'react';
import { Modal, Form, Input, InputNumber, Select, message } from 'antd';

const { Option } = Select;

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
  const [form] = Form.useForm();
  const [loading, setLoading] = React.useState(false);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      await onOk(values);
      form.resetFields();
      message.success('Collection 创建成功');
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
      title="创建向量 Collection"
      open={open}
      onCancel={handleCancel}
      onOk={handleOk}
      confirmLoading={loading}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label="Collection 名称"
          rules={[{ required: true, message: '请输入 Collection 名称' }]}
        >
          <Input placeholder="例如: docs-emb" />
        </Form.Item>
        <Form.Item
          name="dimension"
          label="向量维度"
          rules={[{ required: true, message: '请输入向量维度' }]}
          initialValue={768}
        >
          <InputNumber min={1} max={65536} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item
          name="metricType"
          label="度量类型"
          rules={[{ required: true, message: '请选择度量类型' }]}
          initialValue="Cosine"
        >
          <Select placeholder="选择度量类型">
            <Option value="Cosine">Cosine (余弦相似度)</Option>
            <Option value="Euclidean">Euclidean (欧氏距离)</Option>
            <Option value="InnerProduct">InnerProduct (内积)</Option>
          </Select>
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default CollectionModal;